"""MCP server exposing the OLX tools to Claude apps (Claude Code, Cowork, Claude Desktop).

The app's own Claude does the reasoning, so this runs within a Claude subscription and needs no API key. The tools
are the same objects the API agent uses: their names, descriptions and JSON schemas come from `build_tools`.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

import anyio
import anyio.to_thread
import mcp_types as types
from anthropic.lib.tools import ToolError
from mcp.server.lowlevel.server import Server
from mcp.server.stdio import stdio_server

from . import __version__
from .config import Config
from .images import ImageBudget
from .olx_client import OlxClient
from .prompts import MCP_INSTRUCTIONS
from .tools import ToolContext, build_tools
from .tracker import Tracker

# Tools that only read: from OLX (open world) or from the local tracker.
_READ_ONLY = {
    "search_listings",
    "get_listing",
    "view_listing_photos",
    "zoom_listing_photo",
    "view_image",
    "market_price_stats",
    "get_seller_profile",
    "compare_listings",
    "buying_guide",
    "show_tracker",
}
_LOCAL_ONLY = {"buying_guide", "show_tracker", "track_listing", "log_conversation", "remember_preferences", "view_image"}

Content = list[types.TextContent | types.ImageContent]


def to_mcp_content(result: Any) -> Content:
    """Tool output (a string or Anthropic-style text/image blocks) as MCP content."""
    if isinstance(result, str):
        return [types.TextContent(type="text", text=result)]
    content: Content = []
    for block in result:
        if block.get("type") == "image":
            source = block["source"]
            content.append(types.ImageContent(type="image", data=source["data"], mime_type=source["media_type"]))
        elif block.get("type") == "text":
            content.append(types.TextContent(type="text", text=block["text"]))
    return content


def _error(text: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=True)


def build_server(
    config: Optional[Config] = None, *, olx: Optional[OlxClient] = None, tracker: Optional[Tracker] = None
) -> Server:
    config = config or Config()
    olx = olx or OlxClient(config)
    tracker = tracker or Tracker(config.state_path)
    tools = {t.name: t for t in build_tools(ToolContext(config, olx, tracker, ImageBudget(config.image_budget_bytes)))}
    # Tools share the HTTP throttle and the tracker file, so calls run one at a time.
    lock = threading.Lock()

    def definition(name: str) -> types.Tool:
        tool = tools[name]
        return types.Tool(
            name=name,
            description=tool.description,
            input_schema=tool.input_schema,
            annotations=types.ToolAnnotations(
                read_only_hint=name in _READ_ONLY,
                destructive_hint=False,
                open_world_hint=name not in _LOCAL_ONLY,
            ),
        )

    async def list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[definition(name) for name in tools])

    def run(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        with lock:
            try:
                return types.CallToolResult(content=to_mcp_content(tools[name].call(arguments)))
            except ToolError as exc:
                return types.CallToolResult(content=to_mcp_content(exc.content), is_error=True)
            except ValueError as exc:
                # Argument validation errors carry the pydantic details in their cause.
                return _error(f"{exc}: {exc.__cause__}" if exc.__cause__ else str(exc))
            except Exception as exc:  # report, don't crash the server
                return _error(f"Błąd narzędzia {name}: {exc!r}")

    async def call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        if params.name not in tools:
            return _error(f"Nieznane narzędzie: {params.name}")
        return await anyio.to_thread.run_sync(run, params.name, dict(params.arguments or {}))

    return Server(
        "olx",
        version=__version__,
        instructions=MCP_INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def main() -> None:
    server = build_server()

    async def serve() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(serve)


if __name__ == "__main__":
    main()
