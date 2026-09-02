"""Unit tests for the Dynamic Tool Selection Optimization Layer."""

import unittest
from dataclasses import dataclass
from typing import List, Optional

from src.turning_point.tool_selector import score_tool, select_relevant_tools, _tokenize


@dataclass
class MockMCPTool:
    name: str
    description: str = ""
    tags: Optional[List[str]] = None
    input_schema: Optional[dict] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.input_schema is None:
            self.input_schema = {"type": "object", "properties": {}}


class TestToolSelector(unittest.TestCase):

    def test_tokenize(self):
        tokens = _tokenize("getMsgVpnQueues")
        self.assertIn("get", tokens)
        self.assertIn("msg", tokens)
        self.assertIn("vpn", tokens)
        self.assertIn("queues", tokens)

    def test_score_tool_keyword_match(self):
        tool = MockMCPTool(
            name="getMsgVpnQueues",
            description="Get list of message queues on a MsgVpn",
            tags=["queue", "msgVpn"],
        )

        query_tokens = _tokenize("show me message queues")
        score = score_tool(tool, query_tokens, "show me message queues", set())

        self.assertGreater(score, 50.0)

    def test_score_tool_history_boost(self):
        tool = MockMCPTool(name="getApplications", description="Get applications")
        query_tokens = _tokenize("some query")

        score_without_history = score_tool(tool, query_tokens, "some query", set())
        score_with_history = score_tool(tool, query_tokens, "some query", {"getApplications"})

        self.assertGreaterEqual(score_with_history, score_without_history + 1000.0)

    def test_select_relevant_tools_within_limit(self):
        tools = [
            MockMCPTool(name="tool1"),
            MockMCPTool(name="tool2"),
        ]

        ollama_tools, selected_mcp = select_relevant_tools(tools, "test query", max_tools=10)
        self.assertEqual(len(selected_mcp), 2)
        self.assertEqual(len(ollama_tools), 2)

    def test_select_relevant_tools_filtering(self):
        tools = [
            MockMCPTool(name="getMsgVpnQueues", description="Get message queues"),
            MockMCPTool(name="createMsgVpnQueue", description="Create message queue"),
            MockMCPTool(name="getMsgVpnClients", description="Get connected clients"),
            MockMCPTool(name="getApplicationDomains", description="Get EP application domains"),
            MockMCPTool(name="getEvents", description="Get design events"),
            MockMCPTool(name="getCertAuthorities", description="Get certificate authorities"),
        ]

        ollama_tools, selected = select_relevant_tools(
            tools, "Show me all message queues on the broker", max_tools=2
        )

        self.assertEqual(len(selected), 2)
        selected_names = [t.name for t in selected]
        self.assertIn("getMsgVpnQueues", selected_names)

    def test_select_event_api_products(self):
        tools = [
            MockMCPTool(name="createEvent", description="Create an event"),
            MockMCPTool(name="createEventApi", description="Create an Event API"),
            MockMCPTool(name="createEventApiProduct", description="Create an Event API Product"),
            MockMCPTool(name="getEventApiProducts", description="Get Event API Products"),
            MockMCPTool(name="getEvents", description="Get events"),
        ]

        query = "Create Event API Products for the Airport domain"
        ollama_tools, selected = select_relevant_tools(tools, query, max_tools=2)
        selected_names = [t.name for t in selected]
        self.assertIn("createEventApiProduct", selected_names)
        self.assertNotIn("createEvent", selected_names)


if __name__ == "__main__":
    unittest.main()
