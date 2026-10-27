"""The agent loop: Claude + OLX tools via the SDK tool runner, with an append-only conversation history."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Union

import anthropic

from .config import Config
from .images import ImageBudget
from .olx_client import OlxClient
from .prompts import SYSTEM_PROMPT, session_context
from .tools import ToolContext, build_tools
from .tracker import Tracker

# Server-side refusal fallbacks ("default" routing) and progress-update thinking display are model-gated.
_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
_PROGRESS_MODELS = {"claude-fable-5-1", "claude-fable-5", "claude-opus-5-5", "claude-sonnet-5-5"}
MAX_STEPS_PER_TURN = 40
# Without streaming the SDK refuses requests that could outlast its HTTP timeout.
NON_STREAMING_MAX_TOKENS = 16000

UserContent = Union[str, list[dict[str, Any]]]


class AgentEvents:
    """Callbacks for rendering a turn as it happens. The default implementation ignores everything."""

    def on_text(self, text: str) -> None: ...

    def on_progress(self, text: str) -> None: ...

    def on_block_end(self, block_type: Optional[str]) -> None: ...

    def on_tool_call(self, name: str, args: dict[str, Any]) -> None: ...

    def on_tool_result(self, name: str, is_error: bool, summary: str) -> None: ...


@dataclass
class TurnResult:
    text: str
    stop_reason: Optional[str]
    notices: list[str] = field(default_factory=list)


def _first_line(text: str, limit: int) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def _tool_result_summary(content: Any) -> str:
    if isinstance(content, str):
        return _first_line(content, 160)
    if isinstance(content, list):
        images = sum(1 for b in content if isinstance(b, dict) and b.get("type") == "image")
        texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        first = _first_line(texts[0], 120) if texts else ""
        return f"{first} [{images} obraz(y)]" if images else first
    return ""


class OlxAgent:
    def __init__(
        self,
        config: Optional[Config] = None,
        *,
        client: Optional[anthropic.Anthropic] = None,
        olx: Optional[OlxClient] = None,
        tracker: Optional[Tracker] = None,
        events: Optional[AgentEvents] = None,
    ) -> None:
        self.config = config or Config()
        self.client = client or anthropic.Anthropic()
        self.olx = olx or OlxClient(self.config)
        self.tracker = tracker or Tracker(self.config.state_path)
        self.images = ImageBudget(self.config.image_budget_bytes)
        self.events = events or AgentEvents()
        # Tools and system prompt are fixed for the whole session so the cached prefix stays valid.
        self.tools = build_tools(ToolContext(self.config, self.olx, self.tracker, self.images))
        self.history: list[Any] = []
        self.usage: Counter[str] = Counter()

    def reset(self) -> None:
        self.history = []
        self.images.reset()

    def request_params(self) -> dict[str, Any]:
        model = self.config.model
        thinking: dict[str, Any] = {"type": "adaptive"}
        betas: list[str] = []
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": self.config.max_tokens,
            "system": [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            "tools": self.tools,
            "output_config": {"effort": self.config.effort},
            "cache_control": {"type": "ephemeral"},
        }
        if self.config.show_progress and model in _PROGRESS_MODELS:
            thinking["display"] = "updates"
            betas.append("thinking-display-updates-2026-08-18")
        if self.config.use_fallbacks and model in _FALLBACK_MODELS:
            params["fallbacks"] = "default"
            betas.append("server-side-fallback-2026-07-01")
        params["thinking"] = thinking
        if betas:
            params["betas"] = betas
        if not self.config.use_threads:
            params["thread"] = False
        return params

    # --- one user turn -------------------------------------------------------------

    def ask(self, content: UserContent, *, stream: bool = True) -> TurnResult:
        blocks: list[dict[str, Any]] = [{"type": "text", "text": content}] if isinstance(content, str) else list(content)
        if not self.history:
            context = session_context(date.today().isoformat(), self.tracker.render_summary())
            blocks.insert(0, {"type": "text", "text": context})

        checkpoint, images_checkpoint = len(self.history), self.images.used
        for block in blocks:
            if block.get("type") == "image" and block.get("source", {}).get("type") == "base64":
                self.images.add(len(block["source"]["data"]))
        self.history.append({"role": "user", "content": blocks})
        params = self.request_params()
        if not stream:
            params["max_tokens"] = min(params["max_tokens"], NON_STREAMING_MAX_TOKENS)
        final = None
        try:
            runner = self.client.beta.messages.tool_runner(
                messages=list(self.history), stream=stream, max_iterations=MAX_STEPS_PER_TURN, **params
            )
            for item in runner:
                message = self._consume_stream(item) if stream else item
                final = message
                self._record_usage(message)
                self.history.append(message.to_param())
                # Tools run only for a completed tool_use turn; a truncated or refused turn runs nothing.
                if message.stop_reason != "tool_use":
                    continue
                names = {}
                for block in message.content:
                    if block.type == "tool_use":
                        names[block.id] = block.name
                        self.events.on_tool_call(block.name, dict(block.input or {}))
                response = runner.generate_tool_call_response()
                if response is not None:
                    self.history.append(response)
                    for result in response["content"]:
                        self.events.on_tool_result(
                            names.get(result.get("tool_use_id"), "?"),
                            bool(result.get("is_error")),
                            _tool_result_summary(result.get("content")),
                        )
        except BaseException:
            # Drop the unfinished turn so the history stays a valid, append-only conversation.
            del self.history[checkpoint:]
            self.images.used = images_checkpoint
            raise
        return self._finish(final, checkpoint, images_checkpoint)

    def _finish(self, final: Any, checkpoint: int, images_checkpoint: int) -> TurnResult:
        if final is None:
            del self.history[checkpoint:]
            self.images.used = images_checkpoint
            return TurnResult("", None, ["Brak odpowiedzi modelu."])
        text = "".join(b.text for b in final.content if b.type == "text").strip()
        notices: list[str] = []
        stop = final.stop_reason
        if stop == "refusal":
            del self.history[checkpoint:]
            self.images.used = images_checkpoint
            notices.append("Model odmówił odpowiedzi na to polecenie. Spróbuj sformułować prośbę inaczej.")
        elif stop == "tool_use":
            notices.append(
                f"Osiągnięto limit {MAX_STEPS_PER_TURN} kroków w jednej odpowiedzi — napisz „kontynuuj”, by agent pracował dalej."
            )
        elif stop == "max_tokens":
            notices.append("Odpowiedź została ucięta (limit długości). Napisz „kontynuuj”.")
        elif stop == "model_context_window_exceeded":
            notices.append("Rozmowa przekroczyła okno kontekstu — zacznij nową komendą /nowa (tracker zostaje).")
        if stop not in ("tool_use", "refusal"):
            self._close_dangling_tool_uses(final)
        return TurnResult(text, stop, notices)

    def _close_dangling_tool_uses(self, final: Any) -> None:
        """A truncated turn can end on a tool call that never ran; answer it so the next request is valid."""
        dangling = [b for b in final.content if b.type == "tool_use"]
        if dangling:
            self.history.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": b.id,
                            "content": "Nie wykonano: odpowiedź została ucięta przed końcem wywołania.",
                            "is_error": True,
                        }
                        for b in dangling
                    ],
                }
            )

    def _consume_stream(self, stream: Any) -> Any:
        block_type: Optional[str] = None
        for event in stream:
            etype = getattr(event, "type", None)
            if etype == "content_block_start":
                block_type = event.content_block.type
            elif etype == "content_block_delta":
                delta = event.delta
                if delta.type == "text_delta":
                    self.events.on_text(delta.text)
                elif delta.type == "thinking_delta" and delta.thinking:
                    self.events.on_progress(delta.thinking)
            elif etype == "content_block_stop":
                self.events.on_block_end(block_type)
                block_type = None
        return stream.get_final_message()

    def _record_usage(self, message: Any) -> None:
        usage = getattr(message, "usage", None)
        if usage is None:
            return
        for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            value = getattr(usage, key, None)
            if isinstance(value, int):
                self.usage[key] += value
        self.usage["requests"] += 1
