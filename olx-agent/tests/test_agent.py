"""End-to-end agent loop against a scripted fake of the Messages API (no network, no API key)."""

import base64
import io
import json

import anthropic
import httpx2
import pytest
from PIL import Image

from olx_agent.agent import AgentEvents, OlxAgent

from conftest import load_offer


def _msg(msg_id, content, stop_reason):
    return {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1000, "output_tokens": 50, "cache_read_input_tokens": 800},
    }


TOOL_TURN = _msg(
    "msg_1",
    [
        {"type": "thinking", "thinking": "Obejrzę zdjęcia.", "signature": "sig-1"},
        {"type": "tool_use", "id": "toolu_1", "name": "view_listing_photos", "input": {"listing": "912345678", "max_photos": 2}},
    ],
    "tool_use",
)
FINAL_TURN = _msg("msg_2", [{"type": "text", "text": "Na zdjęciu 2 widać rysę ekranu."}], "end_turn")


def _sse(message):
    """The server-sent events stream the API would send for `message`."""
    events = [("message_start", {"type": "message_start", "message": {**message, "content": [], "stop_reason": None}})]
    for i, block in enumerate(message["content"]):
        if block["type"] == "text":
            start, deltas = {"type": "text", "text": ""}, [{"type": "text_delta", "text": block["text"]}]
        elif block["type"] == "thinking":
            start = {"type": "thinking", "thinking": "", "signature": ""}
            deltas = [
                {"type": "thinking_delta", "thinking": block["thinking"]},
                {"type": "signature_delta", "signature": block["signature"]},
            ]
        else:
            start = {**block, "input": {}}
            deltas = [{"type": "input_json_delta", "partial_json": json.dumps(block["input"])}]
        events.append(("content_block_start", {"type": "content_block_start", "index": i, "content_block": start}))
        events += [("content_block_delta", {"type": "content_block_delta", "index": i, "delta": d}) for d in deltas]
        events.append(("content_block_stop", {"type": "content_block_stop", "index": i}))
    events.append(
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": message["stop_reason"], "stop_sequence": None},
                           "usage": {"output_tokens": 50}})
    )
    events.append(("message_stop", {"type": "message_stop"}))
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)


class FakeMessagesApi:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request):
        body = json.loads(request.content)
        self.requests.append({"headers": dict(request.headers), "body": body})
        reply = self.replies.pop(0)
        if isinstance(reply, int):
            return httpx2.Response(reply, json={"type": "error", "error": {"type": "api_error", "message": "boom"}})
        if body.get("stream"):
            return httpx2.Response(200, text=_sse(reply), headers={"content-type": "text/event-stream"})
        return httpx2.Response(200, json=reply)


class RecordingEvents(AgentEvents):
    def __init__(self):
        self.log = []

    def on_text(self, text):
        self.log.append(("text", text))

    def on_progress(self, text):
        self.log.append(("progress", text))

    def on_tool_call(self, name, args):
        self.log.append(("call", name, args))

    def on_tool_result(self, name, is_error, summary):
        self.log.append(("result", name, is_error, summary))


@pytest.fixture
def make_agent(config, olx, fake_olx):
    fake_olx.offers["912345678"] = load_offer()

    def build(replies):
        api = FakeMessagesApi(replies)
        client = anthropic.Anthropic(
            api_key="test-key",
            base_url="http://anthropic.test",
            http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(api)),
            max_retries=0,
        )
        events = RecordingEvents()
        return OlxAgent(config, client=client, olx=olx, events=events), api, events

    return build


def _image_blocks(tool_result_message):
    result = tool_result_message["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "toolu_1"
    return [b for b in result["content"] if b["type"] == "image"]


@pytest.mark.parametrize("stream", [False, True])
def test_agent_sends_listing_photos_to_claude_as_images(make_agent, stream):
    agent, api, events = make_agent([TOOL_TURN, FINAL_TURN])

    result = agent.ask("Oceń stan telefonu z ogłoszenia 912345678", stream=stream)

    assert result.text == "Na zdjęciu 2 widać rysę ekranu."
    assert result.stop_reason == "end_turn" and result.notices == []
    assert len(api.requests) == 2

    # The follow-up request carries the photos as base64 image blocks inside the tool result.
    second = api.requests[1]["body"]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert second[1]["content"][0] == {"type": "thinking", "thinking": "Obejrzę zdjęcia.", "signature": "sig-1"}
    images = _image_blocks(second[2])
    assert len(images) == 2
    decoded = Image.open(io.BytesIO(base64.b64decode(images[0]["source"]["data"])))
    assert decoded.format == "JPEG" and max(decoded.size) <= 1024

    assert ("call", "view_listing_photos", {"listing": "912345678", "max_photos": 2}) in events.log
    assert any(e[0] == "result" and not e[2] and "[2 obraz(y)]" in e[3] for e in events.log)
    if stream:
        assert ("progress", "Obejrzę zdjęcia.") in events.log
        assert ("text", "Na zdjęciu 2 widać rysę ekranu.") in events.log
    assert len(agent.history) == 4


def test_request_parameters(make_agent):
    agent, api, _ = make_agent([FINAL_TURN])
    agent.ask("Cześć", stream=True)

    request = api.requests[0]
    body = request["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["max_tokens"] == 64000 and body["stream"] is True
    assert body["thinking"] == {"type": "adaptive", "display": "updates"}
    assert body["output_config"] == {"effort": "medium"}
    assert body["fallbacks"] == "default"
    assert body["cache_control"] == {"type": "ephemeral"}
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "thread" not in body
    betas = request["headers"]["anthropic-beta"].split(",")
    assert "server-side-fallback-2026-07-01" in betas and "thinking-display-updates-2026-08-18" in betas
    tools = {t["name"]: t for t in body["tools"]}
    assert len(tools) == 13 and all(t["eager_input_streaming"] for t in tools.values())
    # Per-session context goes into the first user turn, not the cached system prompt.
    first_user = body["messages"][0]["content"]
    assert first_user[0]["text"].startswith("[Kontekst sesji — dzisiejsza data:")
    assert first_user[1]["text"] == "Cześć"


def test_history_is_append_only_across_turns(make_agent):
    agent, api, _ = make_agent([TOOL_TURN, FINAL_TURN, _msg("msg_3", [{"type": "text", "text": "OK"}], "end_turn")])
    agent.ask("Pierwsze", stream=False)
    agent.ask("Drugie", stream=False)

    first_turn_messages = api.requests[1]["body"]["messages"]
    third = api.requests[2]["body"]["messages"]
    assert third[: len(first_turn_messages)] == first_turn_messages
    assert [m["role"] for m in third] == ["user", "assistant", "user", "assistant", "user"]
    assert third[-1]["content"] == [{"type": "text", "text": "Drugie"}]


def test_failed_turn_is_rolled_back(make_agent):
    agent, api, _ = make_agent([TOOL_TURN, 500])
    with pytest.raises(anthropic.InternalServerError):
        agent.ask("Oceń zdjęcia", stream=False)
    assert agent.history == []
    assert agent.images.used == 0


def test_truncated_tool_call_is_answered_so_history_stays_valid(make_agent):
    truncated = _msg("msg_1", [{"type": "tool_use", "id": "toolu_9", "name": "get_listing", "input": {}}], "max_tokens")
    agent, _, events = make_agent([truncated])
    result = agent.ask("x", stream=False)

    assert any("ucięta" in n for n in result.notices)
    assert not [e for e in events.log if e[0] == "call"]  # nothing executed
    last = agent.history[-1]
    assert last["role"] == "user" and last["content"][0]["tool_use_id"] == "toolu_9"
    assert last["content"][0]["is_error"] is True


def test_refusal_rolls_back_turn(make_agent):
    agent, _, _ = make_agent([_msg("msg_1", [], "refusal")])
    result = agent.ask("x", stream=False)
    assert agent.history == [] and any("odmówił" in n for n in result.notices)


def test_fallbacks_and_progress_are_skipped_for_unsupported_models(make_agent):
    agent, api, _ = make_agent([FINAL_TURN])
    agent.config.model = "claude-haiku-4-5"
    agent.ask("x", stream=False)
    body = api.requests[0]["body"]
    assert "fallbacks" not in body and body["thinking"] == {"type": "adaptive"}
    assert "anthropic-beta" not in api.requests[0]["headers"]
