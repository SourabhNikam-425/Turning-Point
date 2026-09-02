#!/usr/bin/env python3
"""Solace SEMPv2 Config MCP Server.

Exposes write operations (create, update, delete) for Solace broker resources:
- Queues: create, update, delete
- Queue subscriptions: add, remove
- Client usernames: create, update

The base URL is automatically derived from SOLACE_SEMPV2_BASE_URL by replacing
'/monitor' with '/config', or falls back to SOLACE_SEMPV2_BASE_URL directly.
"""
import os
from dotenv import load_dotenv
import sys
import json
import logging
import requests
import urllib.parse
from typing import Dict, Any, List, Optional


def setup_logging():
    log_level = os.environ.get("MCP_LOG_LEVEL", "INFO").upper()
    log_file = os.environ.get("MCP_LOG_FILE", "")
    log_disable = os.environ.get("MCP_LOG_DISABLE", "").lower() == "true"
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        log_level = "INFO"
    logger = logging.getLogger("solace-sempv2-config-mcp")
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    if log_disable:
        logger.disabled = True
        return logger
    if log_file:
        try:
            fh = logging.FileHandler(log_file)
            fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            logger.addHandler(fh)
        except Exception as e:
            print(f"ERROR: Failed to create log file {log_file}: {e}", file=sys.stderr)
    else:
        logger.disabled = True
    return logger


logger = setup_logging()

MCP_VERSION = "2024-11-05"
ERROR_PARSE = -32700
ERROR_INVALID_REQUEST = -32600
ERROR_METHOD_NOT_FOUND = -32601
ERROR_INVALID_PARAMS = -32602
ERROR_INTERNAL = -32603


def _make_tools():
    return {
        "createMsgVpnQueue": {
            "description": (
                "Create a new queue on the Solace broker for a given Message VPN. "
                "Use this to create a brand-new queue or to duplicate an existing queue by "
                "supplying the source queue configuration with a new queueName. "
                "Key config fields: queueName (required), accessType (exclusive|non-exclusive), "
                "maxMsgSpoolUsage (MB), maxTtl (ms, e.g. 36000000 for 10 hours), "
                "respectTtlEnabled, egressEnabled, ingressEnabled, permission, owner."
            ),
            "path": "/msgVpns/{msgVpnName}/queues",
            "method": "POST",
            "path_params": ["msgVpnName"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "msgVpnName": {"type": "string", "description": "Name of the Message VPN (required)"},
                    "body": {
                        "type": "object",
                        "description": "Queue configuration. Must include queueName.",
                        "properties": {
                            "queueName": {"type": "string", "description": "Name for the new queue (required)"},
                            "accessType": {"type": "string", "enum": ["exclusive", "non-exclusive"]},
                            "egressEnabled": {"type": "boolean"},
                            "ingressEnabled": {"type": "boolean"},
                            "maxMsgSpoolUsage": {"type": "integer", "description": "Max spool usage in MB"},
                            "maxMsgSize": {"type": "integer", "description": "Max message size in bytes"},
                            "maxDeliveredUnackedMsgsPerFlow": {"type": "integer"},
                            "maxRedeliveryCount": {"type": "integer"},
                            "maxTtl": {"type": "integer", "description": "Max TTL in ms. 36000000 = 10 hours."},
                            "respectTtlEnabled": {"type": "boolean"},
                            "permission": {"type": "string", "enum": ["no-access", "read-only", "consume", "modify-topic", "delete"]},
                            "owner": {"type": "string"},
                            "rejectLowPriorityMsgEnabled": {"type": "boolean"},
                            "rejectMsgToSenderOnDiscardBehavior": {"type": "string", "enum": ["never", "when-queue-enabled", "always"]},
                            "deadMsgQueue": {"type": "string"},
                        },
                        "required": ["queueName"],
                    },
                },
                "required": ["msgVpnName", "body"],
            },
        },
        "updateMsgVpnQueue": {
            "description": (
                "Update the configuration of an existing queue on the Solace broker (PATCH semantics). "
                "Only supplied fields are changed. Use to change TTL, spool limits, access type, etc."
            ),
            "path": "/msgVpns/{msgVpnName}/queues/{queueName}",
            "method": "PATCH",
            "path_params": ["msgVpnName", "queueName"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "msgVpnName": {"type": "string", "description": "Name of the Message VPN (required)"},
                    "queueName": {"type": "string", "description": "Name of the queue to update (required)"},
                    "body": {
                        "type": "object",
                        "description": "Fields to update. Only supplied fields change.",
                        "properties": {
                            "accessType": {"type": "string", "enum": ["exclusive", "non-exclusive"]},
                            "egressEnabled": {"type": "boolean"},
                            "ingressEnabled": {"type": "boolean"},
                            "maxMsgSpoolUsage": {"type": "integer"},
                            "maxMsgSize": {"type": "integer"},
                            "maxTtl": {"type": "integer", "description": "Max TTL in ms. 36000000 = 10 hours."},
                            "respectTtlEnabled": {"type": "boolean"},
                            "permission": {"type": "string"},
                            "owner": {"type": "string"},
                            "maxRedeliveryCount": {"type": "integer"},
                            "maxDeliveredUnackedMsgsPerFlow": {"type": "integer"},
                            "rejectLowPriorityMsgEnabled": {"type": "boolean"},
                            "deadMsgQueue": {"type": "string"},
                        },
                    },
                },
                "required": ["msgVpnName", "queueName", "body"],
            },
        },
        "deleteMsgVpnQueue": {
            "description": (
                "Delete a queue from the Solace broker. "
                "All messages and subscriptions are permanently removed."
            ),
            "path": "/msgVpns/{msgVpnName}/queues/{queueName}",
            "method": "DELETE",
            "path_params": ["msgVpnName", "queueName"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "msgVpnName": {"type": "string", "description": "Message VPN name (required)"},
                    "queueName": {"type": "string", "description": "Queue name to delete (required)"},
                },
                "required": ["msgVpnName", "queueName"],
            },
        },
        "createMsgVpnQueueSubscription": {
            "description": (
                "Add a topic subscription to an existing queue on the Solace broker. "
                "Messages published to topics matching the subscription are delivered to this queue. "
                "Wildcards: * matches a single level, > matches all remaining levels. "
                "Example topics: '/NOTAM/YOW/*', '/A-CDM/YYZ/flight/*/YYZ/>', 'flight/test/>'"
            ),
            "path": "/msgVpns/{msgVpnName}/queues/{queueName}/subscriptions",
            "method": "POST",
            "path_params": ["msgVpnName", "queueName"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "msgVpnName": {"type": "string", "description": "Message VPN name (required)"},
                    "queueName": {"type": "string", "description": "Queue name (required)"},
                    "body": {
                        "type": "object",
                        "properties": {
                            "subscriptionTopic": {
                                "type": "string",
                                "description": "Topic subscription string. E.g. '/NOTAM/YOW/*' or '/A-CDM/YYZ/flight/*/YYZ/>'",
                            },
                        },
                        "required": ["subscriptionTopic"],
                    },
                },
                "required": ["msgVpnName", "queueName", "body"],
            },
        },
        "deleteMsgVpnQueueSubscription": {
            "description": (
                "Remove a topic subscription from a queue. "
                "The subscriptionTopic must exactly match an existing subscription. "
                "After removal, messages for that topic will no longer be delivered to this queue."
            ),
            "path": "/msgVpns/{msgVpnName}/queues/{queueName}/subscriptions/{subscriptionTopic}",
            "method": "DELETE",
            "path_params": ["msgVpnName", "queueName", "subscriptionTopic"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "msgVpnName": {"type": "string", "description": "Message VPN name (required)"},
                    "queueName": {"type": "string", "description": "Queue name (required)"},
                    "subscriptionTopic": {
                        "type": "string",
                        "description": "Exact topic subscription to remove. E.g. 'flight/test/>' (required)",
                    },
                },
                "required": ["msgVpnName", "queueName", "subscriptionTopic"],
            },
        },
        "createMsgVpnClientUsername": {
            "description": (
                "Create a new client username on the Solace broker for a given Message VPN. "
                "Client usernames control which clients can connect and link them to ACL and client profiles."
            ),
            "path": "/msgVpns/{msgVpnName}/clientUsernames",
            "method": "POST",
            "path_params": ["msgVpnName"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "msgVpnName": {"type": "string", "description": "Message VPN name (required)"},
                    "body": {
                        "type": "object",
                        "properties": {
                            "clientUsername": {"type": "string", "description": "Client username (required)"},
                            "aclProfileName": {"type": "string"},
                            "clientProfileName": {"type": "string"},
                            "enabled": {"type": "boolean"},
                            "password": {"type": "string"},
                        },
                        "required": ["clientUsername"],
                    },
                },
                "required": ["msgVpnName", "body"],
            },
        },
        "updateMsgVpnClientUsername": {
            "description": (
                "Update an existing client username on the Solace broker. "
                "Change the associated ACL profile, client profile, enabled state, or password."
            ),
            "path": "/msgVpns/{msgVpnName}/clientUsernames/{clientUsername}",
            "method": "PATCH",
            "path_params": ["msgVpnName", "clientUsername"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "msgVpnName": {"type": "string", "description": "Message VPN name (required)"},
                    "clientUsername": {"type": "string", "description": "Client username to update (required)"},
                    "body": {
                        "type": "object",
                        "properties": {
                            "aclProfileName": {"type": "string"},
                            "clientProfileName": {"type": "string"},
                            "enabled": {"type": "boolean"},
                            "password": {"type": "string"},
                        },
                    },
                },
                "required": ["msgVpnName", "clientUsername", "body"],
            },
        },
    }


class SolaceConfigMcpServer:
    """MCP Server for Solace SEMPv2 Config API (write operations)."""

    def __init__(self):
        load_dotenv()
        self.tools = _make_tools()
        raw_url = os.environ.get("SOLACE_SEMPV2_BASE_URL", "http://localhost:8080")
        self.base_url = raw_url.replace("/SEMP/v2/monitor", "/SEMP/v2/config")
        logger.info("Config MCP server base URL: %s", self.base_url)
        self.auth_method = os.environ.get("SOLACE_SEMPV2_AUTH_METHOD", "basic").lower()
        self.username = os.environ.get("SOLACE_SEMPV2_USERNAME")
        self.password = os.environ.get("SOLACE_SEMPV2_PASSWORD")
        self.bearer_token = os.environ.get("SOLACE_SEMPV2_BEARER_TOKEN", "")

    def handle_message(self, message_str: str) -> str:
        try:
            message = json.loads(message_str)
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                return self._error(None, ERROR_INVALID_REQUEST, "Invalid request format")
            msg_id = message.get("id")
            method = message.get("method")
            if not method:
                return self._error(msg_id, ERROR_INVALID_REQUEST, "Method not specified")
            if method == "initialize":
                return self._handle_initialize(msg_id)
            elif method in ("mcp.list_tools", "tools/list"):
                return self._handle_list_tools(msg_id)
            elif method in ("mcp.call_tool", "tools/call"):
                return self._handle_call_tool(msg_id, message.get("params", {}))
            else:
                return self._error(msg_id, ERROR_METHOD_NOT_FOUND, f"Method not found: {method}")
        except json.JSONDecodeError:
            return self._error(None, ERROR_PARSE, "Parse error")
        except Exception as e:
            logger.error("Error handling message: %s", e)
            return self._error(None, ERROR_INTERNAL, f"Internal error: {e}")

    def _handle_initialize(self, msg_id):
        return json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": MCP_VERSION,
            "capabilities": {"tools": {"enabled": True}, "resources": {"enabled": False}, "resourceTemplates": {"enabled": False}},
            "serverInfo": {"name": "solace-sempv2-config-mcp", "version": MCP_VERSION},
        }})

    def _handle_list_tools(self, msg_id):
        tools_list = [{"name": n, "description": c["description"], "inputSchema": c["input_schema"]}
                      for n, c in self.tools.items()]
        return json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools_list}})

    def _handle_call_tool(self, msg_id, params):
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        if not tool_name:
            return self._error(msg_id, ERROR_INVALID_PARAMS, "Tool name not specified")
        tool_cfg = self.tools.get(tool_name)
        if not tool_cfg:
            return self._error(msg_id, ERROR_METHOD_NOT_FOUND, f"Tool not found: {tool_name}")
        try:
            result = self._invoke(tool_cfg, arguments)
            return json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
            }})
        except Exception as e:
            logger.error("Error invoking tool %s: %s", tool_name, e)
            return self._error(msg_id, ERROR_INTERNAL, f"Error invoking tool: {e}")

    def _invoke(self, tool_cfg, arguments):
        path = tool_cfg["path"]
        method = tool_cfg["method"]
        for param in tool_cfg.get("path_params", []):
            value = arguments.get(param, "")
            path = path.replace("{" + param + "}", urllib.parse.quote(str(value), safe=""))
        url = self.base_url.rstrip("/") + path
        body = arguments.get("body") if "body" in arguments else None
        headers = {"Content-Type": "application/json"}
        auth = None
        if self.auth_method == "bearer" and self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        elif self.auth_method == "basic" and self.username and self.password:
            auth = (self.username, self.password)
        logger.info("Making %s request to %s", method, url)
        response = requests.request(method, url, headers=headers, json=body, auth=auth)
        logger.debug("Response status: %s", response.status_code)
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return {"status": "success", "statusCode": response.status_code}
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"text": response.text}

    def _error(self, msg_id, code, message):
        return json.dumps({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})

    def run(self):
        logger.info("Starting Solace SEMPv2 Config MCP Server with %d tools", len(self.tools))
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                response = self.handle_message(line)
                sys.stdout.write(response + "\n")
                sys.stdout.flush()
        except KeyboardInterrupt:
            logger.info("Server shutting down")
            sys.exit(0)


if __name__ == "__main__":
    try:
        server = SolaceConfigMcpServer()
        server.run()
    except Exception as e:
        logger.critical("Server startup failed: %s", e)
        sys.exit(1)
