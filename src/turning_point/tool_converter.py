"""Convert MCP tool schemas to Ollama-compatible format.

This module provides a pure conversion layer between the MCP tool
schema format and the Ollama function-calling format. Separated
for testability and clarity.
"""

from typing import Any


def mcp_tool_to_ollama(tool: Any) -> dict:
    """Convert a single MCP tool to Ollama function-calling format.

    Args:
        tool: An MCP tool object with .name, .description,
              and .input_schema attributes.

    Returns:
        A dict in Ollama's function-calling tool format.
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema or {},
        },
    }


def convert_all_tools(mcp_tools: list[Any]) -> list[dict]:
    """Convert a list of MCP tools to Ollama format.

    Args:
        mcp_tools: List of MCP tool objects.

    Returns:
        List of Ollama-compatible tool dicts.
    """
    return [mcp_tool_to_ollama(tool) for tool in mcp_tools]


def extract_tool_names(mcp_tools: list[Any]) -> list[str]:
    """Extract just the names from a list of MCP tools.

    Args:
        mcp_tools: List of MCP tool objects.

    Returns:
        List of tool name strings.
    """
    return [tool.name for tool in mcp_tools]
