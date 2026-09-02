"""Web application server for EventFlow Assistant / TurningPoint.

Serves the Backstage-inspired web UI on http://localhost:8000 and connects
interactive user requests directly to the multi-MCP server backend and Ollama LLM.
"""

import json
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from .config import AppConfig, load_config
from .llm_service import LLMService
from .logger import get_logger
from .mcp_client import MultiServerSessionManager, connect_all, discover_tools, execute_tool
from .prompts import build_error_context, build_system_prompt
from .tool_converter import extract_tool_names
from .tool_selector import select_relevant_tools

log = get_logger("server")

# Global state holders for application lifecycle
state = {
    "config": None,
    "session_manager": None,
    "all_mcp_tools": [],
    "llm": None,
    "history_tool_names": set(),
}


@asynccontextmanager
async def lifespan(app: Starlette):
    """Manage lifecycle of MCP connection manager and LLM service."""
    log.info("Starting EventFlow Assistant Web Server...")
    config = load_config()
    state["config"] = config

    # Connect to MCP servers
    async with connect_all(config.mcp) as session_manager:
        state["session_manager"] = session_manager

        # Discover tools across servers
        mcp_tools = await discover_tools(session_manager)
        tool_names = extract_tool_names(mcp_tools)
        state["all_mcp_tools"] = mcp_tools

        log.info(
            "Discovered %d MCP tools across servers. Tool Optimization active.",
            len(tool_names),
        )

        # Initialize LLM
        llm = LLMService(
            host=config.ollama_host,
            model_config=config.model,
        )
        system_prompt = build_system_prompt(tool_names)
        llm.set_system_prompt(system_prompt)
        state["llm"] = llm

        log.info("EventFlow Assistant Web Server ready on http://localhost:8000")
        yield

    log.info("EventFlow Assistant Web Server shut down cleanly")


async def index(request):
    """Serve the single-page HTML frontend."""
    html_path = os.path.join(os.path.dirname(__file__), "web_index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content)
    return HTMLResponse("<h1>EventFlow Assistant Backend Running</h1>", status_code=200)


async def chat_api(request):
    """Handle chat messages from the web frontend and execute MCP tools."""
    try:
        data = await request.json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return JSONResponse({"error": "Empty message"}, status_code=400)

        llm: LLMService = state["llm"]
        session_manager: MultiServerSessionManager = state["session_manager"]
        all_tools = state["all_mcp_tools"]
        config: AppConfig = state["config"]

        llm.add_user_message(user_message)
        executed_tool_calls = []

        # Inner loop: handle multi-step tool calls
        while True:
            # Dynamic Tool Selection Optimization Layer
            ollama_tools, _ = select_relevant_tools(
                all_tools=all_tools,
                user_query=user_message,
                max_tools=config.max_tools_per_query,
                history_tool_names=state["history_tool_names"],
            )

            response = await llm.chat(tools=ollama_tools)

            if not response.message.tool_calls:
                llm.add_assistant_message(response.message)
                return JSONResponse(
                    {
                        "content": response.message.content,
                        "tool_calls": executed_tool_calls,
                    }
                )

            # LLM requested tool calls
            llm.add_assistant_message(response.message)

            for tool_call in response.message.tool_calls:
                t_name = tool_call.function.name
                t_args = tool_call.function.arguments

                log.info("Web user requested tool: %s", t_name)
                state["history_tool_names"].add(t_name)

                result = await execute_tool(session_manager, t_name, t_args)

                executed_tool_calls.append(
                    {
                        "name": t_name,
                        "arguments": t_args,
                        "result_preview": result[:150] if result else "",
                    }
                )

                if result.startswith("Tool '") and "failed:" in result:
                    err_ctx = build_error_context(t_name, result)
                    llm.add_tool_result(t_name, err_ctx)
                else:
                    llm.add_tool_result(t_name, result)

    except Exception as e:
        log.error("Chat API error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


routes = [
    Route("/", index, methods=["GET"]),
    Route("/api/chat", chat_api, methods=["POST"]),
]

app = Starlette(debug=True, routes=routes, lifespan=lifespan)


def run_web_server():
    """Start uvicorn server serving the Starlette application."""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    run_web_server()
