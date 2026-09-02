"""MCP client — manages connections to one or more Solace MCP servers.

Handles server lifecycles, aggregated tool discovery across multiple servers,
and tool execution routing with proper error handling.
"""

import os
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import MCPConfig, MCPServerConfig
from .logger import get_logger

log = get_logger("mcp")


def _build_server_params_from_config(
    server_config: MCPServerConfig,
) -> StdioServerParameters:
    """Build StdioServerParameters from an MCPServerConfig."""
    env = {**os.environ}
    if server_config.env:
        env.update(server_config.env)

    return StdioServerParameters(
        command=server_config.command,
        args=server_config.args,
        env=env,
    )


def _build_server_params(config: MCPConfig) -> StdioServerParameters:
    """Build the MCP server parameters from legacy config.

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


class MultiServerSessionManager:
    """Manages sessions across multiple MCP servers and routes tool calls."""

    def __init__(self) -> None:
        self.sessions: Dict[str, ClientSession] = {}
        self.tool_to_server_map: Dict[str, str] = {}
        self.all_tools: List[Any] = []

    def add_session(self, server_name: str, session: ClientSession) -> None:
        """Register a session with a given server name."""
        self.sessions[server_name] = session

    async def discover_tools(self) -> List[Any]:
        """Discover tools from all registered MCP server sessions.

        Aggregates tools into a single list and builds a routing map
        from tool_name -> server_name.

        Returns:
            List of all discovered MCP tool objects across all servers.
        """
        self.all_tools = []
        self.tool_to_server_map = {}

        for server_name, session in self.sessions.items():
            try:
                response = await session.list_tools()
                server_tools = response.tools
                log.info(
                    "Discovered %d tools from server '%s'",
                    len(server_tools),
                    server_name,
                )

                for tool in server_tools:
                    if tool.name in self.tool_to_server_map:
                        log.warning(
                            "Duplicate tool name '%s' from server '%s' (already registered to '%s')",
                            tool.name,
                            server_name,
                            self.tool_to_server_map[tool.name],
                        )
                    else:
                        self.tool_to_server_map[tool.name] = server_name

                    self.all_tools.append(tool)

            except Exception as e:
                log.error(
                    "Failed to discover tools from server '%s': %s",
                    server_name,
                    e,
                )

        log.info("Total discovered tools across all servers: %d", len(self.all_tools))
        return self.all_tools

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool by routing it to its owner MCP server session.

        Args:
            tool_name: The name of the tool to execute.
            arguments: Arguments dict for the tool call.

        Returns:
            The tool result string, or error message.
        """
        server_name = self.tool_to_server_map.get(tool_name)

        if not server_name and self.sessions:
            # Fallback to first session if not in routing map
            server_name = next(iter(self.sessions.keys()))
            log.warning(
                "Tool '%s' not in routing map, falling back to server '%s'",
                tool_name,
                server_name,
            )

        if not server_name or server_name not in self.sessions:
            return f"Error: MCP server for tool '{tool_name}' not available"

        session = self.sessions[server_name]
        return await execute_tool_on_session(session, tool_name, arguments)


@asynccontextmanager
async def connect_all(
    config: MCPConfig,
) -> AsyncGenerator[MultiServerSessionManager, None]:
    """Connect to all enabled Solace MCP servers defined in config.

    Usage:
        async with connect_all(mcp_config) as manager:
            tools = await manager.discover_tools()

    Args:
        config: MCP connection configuration.

    Yields:
        MultiServerSessionManager containing initialized sessions.
    """
    manager = MultiServerSessionManager()

    servers_to_connect = config.servers if config.servers else []

    if not servers_to_connect:
        # Fallback to single legacy server configuration
        log.info("No explicit server list found, falling back to default EP Designer server...")
        async with connect(config) as session:
            manager.add_session("default", session)
            yield manager
        return

    log.info("Connecting to %d MCP server(s)...", len(servers_to_connect))

    async with AsyncExitStack() as stack:
        for server in servers_to_connect:
            if not server.enabled:
                continue

            try:
                server_params = _build_server_params_from_config(server)
                log.info("Starting MCP server process '%s' (%s)...", server.name, server.command)
                
                client_stdio = await stack.enter_async_context(stdio_client(server_params))
                read, write = client_stdio
                
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                
                log.info("Server '%s' connected and initialized successfully", server.name)
                manager.add_session(server.name, session)

            except Exception as e:
                log.error("Failed to initialize MCP server '%s': %s", server.name, e)

        yield manager


@asynccontextmanager
async def connect(
    config: MCPConfig,
) -> AsyncGenerator[ClientSession, None]:
    """Connect to a single Solace MCP server and yield a session (backward compatibility)."""
    server_params = _build_server_params(config)

    log.info("Connecting to Solace MCP server...")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            log.info("Connected and initialized successfully")
            yield session


async def discover_tools(target: Union[ClientSession, MultiServerSessionManager]) -> list[Any]:
    """Discover available tools from a ClientSession or MultiServerSessionManager.

    Args:
        target: An initialized MCP ClientSession or MultiServerSessionManager.

    Returns:
        List of MCP tool objects.
    """
    if isinstance(target, MultiServerSessionManager):
        return await target.discover_tools()

    response = await target.list_tools()
    tools = response.tools

    log.info("Discovered %d tools", len(tools))
    for i, tool in enumerate(tools, start=1):
        log.debug("  %d. %s", i, tool.name)

    return tools


async def execute_tool_on_session(
    session: ClientSession,
    tool_name: str,
    arguments: dict,
) -> str:
    """Execute an MCP tool on a single ClientSession."""
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
        error_msg = f"Tool '{tool_name}' failed: {type(e).__name__}: {e}"
        log.error(error_msg)
        return error_msg


async def execute_tool(
    target: Union[ClientSession, MultiServerSessionManager],
    tool_name: str,
    arguments: dict,
) -> str:
    """Execute an MCP tool and return the result as text.

    Args:
        target: An initialized MCP ClientSession or MultiServerSessionManager.
        tool_name: The name of the tool to call.
        arguments: The arguments dict for the tool.

    Returns:
        The tool result as a text string, or an error message.
    """
    if isinstance(target, MultiServerSessionManager):
        return await target.execute_tool(tool_name, arguments)

    return await execute_tool_on_session(target, tool_name, arguments)

