"""Runtime configuration, read from environment variables with sensible defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Config:
    # Claude
    model: str = field(default_factory=lambda: os.environ.get("OLX_AGENT_MODEL", "claude-opus-5-5"))
    effort: str = field(default_factory=lambda: os.environ.get("OLX_AGENT_EFFORT", "medium"))
    max_tokens: int = field(default_factory=lambda: _env_int("OLX_AGENT_MAX_TOKENS", 64000))
    # Server-side fallback when a safety classifier declines a (benign) request.
    use_fallbacks: bool = field(default_factory=lambda: os.environ.get("OLX_AGENT_FALLBACKS", "1") != "0")
    # Progress notes between tool calls, shown in the CLI.
    show_progress: bool = field(default_factory=lambda: os.environ.get("OLX_AGENT_PROGRESS", "1") != "0")
    # The SDK tool runner can keep the conversation in a server-side message thread (beta) so each request sends
    # only new messages. Off by default: every request then carries the full history, which works everywhere.
    use_threads: bool = field(default_factory=lambda: os.environ.get("OLX_AGENT_THREADS", "0") == "1")

    # OLX
    olx_base_url: str = field(default_factory=lambda: os.environ.get("OLX_BASE_URL", "https://www.olx.pl"))
    request_interval_s: float = 0.6
    http_timeout_s: float = 20.0

    # Images sent to Claude
    image_max_edge: int = field(default_factory=lambda: _env_int("OLX_AGENT_IMAGE_MAX_EDGE", 1024))
    zoom_max_edge: int = 1568
    jpeg_quality: int = 82
    # Requests to the Messages API are capped at 32 MB and every turn re-sends the history,
    # so the session stops adding photos once their encoded size reaches this budget.
    image_budget_bytes: int = field(default_factory=lambda: _env_int("OLX_AGENT_IMAGE_BUDGET_MB", 22) * 1024 * 1024)

    # Local state (tracker, preferences)
    home: Path = field(
        default_factory=lambda: Path(os.environ.get("OLX_AGENT_HOME", str(Path.home() / ".olx-agent")))
    )

    @property
    def state_path(self) -> Path:
        return self.home / "state.json"
