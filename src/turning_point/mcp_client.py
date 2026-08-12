"""MCP client — manages the Solace Event Portal MCP server connection.

Handles server lifecycle, tool discovery, and tool execution with
proper error handling and structured result extraction.
"""

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import MCPConfig
from .logger import get_logger

log = get_logger("mcp")


def _build_server_params(config: MCPConfig) -> StdioServerParameters:
    """Build the MCP server parameters from config.

    Args:
        config: The MCP configuration.

    Returns:
        StdioServerParameters for the Solace MCP server.
    """
    return StdioServerParameters(
        command=config.command,
        args=[
            "--from",
            config.package,
            config.executable,
        ],
        env={
            **os.environ,
            "SOLACE_API_TOKEN": config.api_token,
        },
    )


@asynccontextmanager
async def connect(
    config: MCPConfig,
) -> AsyncGenerator[ClientSession, None]:
    """Connect to the Solace MCP server and yield a session.

    Usage:
        async with connect(mcp_config) as session:
            tools = await discover_tools(session)

    Args:
        config: MCP connection configuration.

    Yields:
        An initialized MCP ClientSession.
    """
    server_params = _build_server_params(config)

    log.info("Connecting to Solace MCP server...")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            log.info("Connected and initialized successfully")
            yield session


async def discover_tools(session: ClientSession) -> list[Any]:
    """Discover all available tools from the MCP server.

    Args:
        session: An initialized MCP ClientSession.

    Returns:
        List of MCP tool objects.
    """
    response = await session.list_tools()
    tools = response.tools

    log.info("Discovered %d tools", len(tools))

    for i, tool in enumerate(tools, start=1):
        log.debug("  %d. %s", i, tool.name)

    return tools


async def execute_tool(
    session: ClientSession,
    tool_name: str,
    arguments: dict,
) -> str:
    """Execute an MCP tool and return the result as text.

    Handles error cases gracefully — returns an error message
    string instead of raising, so the agent loop can continue.

    Args:
        session: An initialized MCP ClientSession.
        tool_name: The name of the tool to call.
        arguments: The arguments dict for the tool.

    Returns:
        The tool result as a text string, or an error message.
    """
    try:
        log.info("Executing tool: %s", tool_name)
        log.debug("Arguments: %s", arguments)

        result = await session.call_tool(
            tool_name,
            arguments=arguments,
        )

        # Extract text from MCP content parts
        result_parts = []
        for content in result.content:
            if hasattr(content, "text"):
                result_parts.append(content.text)
            else:
                result_parts.append(str(content))

        tool_result = "\n".join(result_parts)

        log.info("Tool '%s' executed successfully", tool_name)
        log.debug(
            "Result preview: %s",
            tool_result[:200] + "..."
            if len(tool_result) > 200
            else tool_result,
        )

        return tool_result

    except Exception as e:
        error_msg = (
            f"Tool '{tool_name}' failed: {type(e).__name__}: {e}"
        )
        log.error(error_msg)
        return error_msg
