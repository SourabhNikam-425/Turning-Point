"""Unit tests for Multi-Server MCP client configuration and session management."""

import asyncio
import unittest
from src.turning_point.config import MCPConfig, MCPServerConfig
from src.turning_point.mcp_client import MultiServerSessionManager


class MockSession:
    def __init__(self, tools):
        self._tools = tools

    async def list_tools(self):
        class Response:
            def __init__(self, tools):
                self.tools = tools
        return Response(self._tools)

    async def call_tool(self, name, arguments):
        class Content:
            def __init__(self, text):
                self.text = text
        class Result:
            def __init__(self, content):
                self.content = content
        return Result([Content(f"Executed {name} with {arguments}")])


class TestMCPClient(unittest.TestCase):

    def test_multi_server_session_manager_discovery(self):
        async def run_test():
            manager = MultiServerSessionManager()

            class Tool:
                def __init__(self, name):
                    self.name = name

            session1 = MockSession([Tool("tool_ep_1"), Tool("tool_ep_2")])
            session2 = MockSession([Tool("tool_mon_1"), Tool("tool_mon_2")])

            manager.add_session("server_ep", session1)
            manager.add_session("server_mon", session2)

            discovered = await manager.discover_tools()

            self.assertEqual(len(discovered), 4)
            self.assertEqual(manager.tool_to_server_map["tool_ep_1"], "server_ep")
            self.assertEqual(manager.tool_to_server_map["tool_mon_1"], "server_mon")

        asyncio.run(run_test())

    def test_multi_server_session_manager_execution(self):
        async def run_test():
            manager = MultiServerSessionManager()

            class Tool:
                def __init__(self, name):
                    self.name = name

            session1 = MockSession([Tool("getApplications")])
            session2 = MockSession([Tool("getMsgVpnQueues")])

            manager.add_session("ep", session1)
            manager.add_session("mon", session2)

            await manager.discover_tools()

            res1 = await manager.execute_tool("getApplications", {"domainId": "123"})
            res2 = await manager.execute_tool("getMsgVpnQueues", {"count": "10"})

            self.assertIn("Executed getApplications", res1)
            self.assertIn("Executed getMsgVpnQueues", res2)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
