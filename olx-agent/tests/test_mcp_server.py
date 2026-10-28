"""The MCP server that Claude apps (Claude Code, Cowork, Claude Desktop) start from the plugin."""

import base64
import io
import json
import os
import sys
from pathlib import Path

import anyio
import mcp_types as types
import pytest
from mcp import Client, StdioServerParameters
from PIL import Image

from olx_agent.mcp_server import build_server
from olx_agent.tracker import Tracker

from conftest import load_offer

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def server(config, olx, fake_olx):
    fake_olx.offers["912345678"] = load_offer()
    return build_server(config, olx=olx, tracker=Tracker(config.state_path))


def _with_client(server, fn):
    async def main():
        # "legacy" is the initialize handshake that current Claude apps use.
        async with Client(server, mode="legacy") as client:
            return await fn(client)

    return anyio.run(main)


def test_lists_all_tools_with_schemas_and_hints(server):
    async def go(client):
        return client.instructions, await client.list_tools()

    instructions, result = _with_client(server, go)
    tools = {t.name: t for t in result.tools}

    assert len(tools) == 13
    assert "skill olx-zakupy" in instructions
    search = tools["search_listings"]
    assert search.input_schema["required"] == ["query"]
    assert "price_max" in search.input_schema["properties"]
    assert search.annotations.read_only_hint is True and search.annotations.open_world_hint is True
    assert tools["track_listing"].annotations.read_only_hint is False
    assert tools["buying_guide"].annotations.open_world_hint is False


def test_photos_reach_the_app_as_image_content(server):
    result = _with_client(server, lambda c: c.call_tool("view_listing_photos", {"listing": "912345678", "max_photos": 2}))

    assert not result.is_error
    images = [c for c in result.content if isinstance(c, types.ImageContent)]
    assert len(images) == 2
    assert images[0].mime_type == "image/jpeg"
    decoded = Image.open(io.BytesIO(base64.b64decode(images[0].data)))
    assert max(decoded.size) <= 1024
    assert isinstance(result.content[0], types.TextContent) and "iPhone 13" in result.content[0].text


def test_tool_errors_are_reported_not_raised(server):
    async def go(client):
        missing = await client.call_tool("get_listing", {"listing": "111111111"})
        invalid = await client.call_tool("buying_guide", {"topic": "nieistniejący"})
        unknown = await client.call_tool("no_such_tool", {})
        return missing, invalid, unknown

    missing, invalid, unknown = _with_client(server, go)
    assert missing.is_error and "404" in missing.content[0].text
    assert invalid.is_error and "buying_guide" in invalid.content[0].text
    assert unknown.is_error


def test_stdio_subprocess_end_to_end(tmp_path):
    """Starts the server the way a Claude app does: a subprocess speaking MCP over stdin/stdout."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "olx_agent.mcp_server"],
        env={**os.environ, "OLX_AGENT_HOME": str(tmp_path)},
    )

    async def main():
        async with Client(params, mode="legacy") as client:
            tools = await client.list_tools()
            guide = await client.call_tool("buying_guide", {"topic": "olx_delivery"})
            saved = await client.call_tool("remember_preferences", {"text": "Budżet do 2000 zł"})
            return tools, guide, saved

    tools, guide, saved = anyio.run(main)
    assert len(tools.tools) == 13
    assert "Przesyłka OLX" in guide.content[0].text
    assert not saved.is_error
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["preferences"][0]["text"] == "Budżet do 2000 zł"


def test_plugin_files_point_at_the_server_and_skill():
    plugin = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    mcp_config = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    marketplace = json.loads((PLUGIN_ROOT.parent / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))

    server = mcp_config["mcpServers"]["olx"]
    assert server["args"][-1] == "olx-mcp" and "${CLAUDE_PLUGIN_ROOT}" in server["args"]
    for skills_dir in plugin["skills"]:
        assert (PLUGIN_ROOT / skills_dir / "olx-zakupy" / "SKILL.md").is_file()
    entry = next(p for p in marketplace["plugins"] if p["name"] == plugin["name"])
    assert (PLUGIN_ROOT.parent / entry["source"]).resolve() == PLUGIN_ROOT
    pyproject = (PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'olx-mcp = "olx_agent.mcp_server:main"' in pyproject
    assert f'version = "{plugin["version"]}"' in pyproject
