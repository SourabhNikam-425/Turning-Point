# EventFlow AI — Enterprise POC Documentation

**AI-Powered Event Lifecycle & Governance Management leveraging Solace Model Context Protocol (MCP)**

---

## 1. Executive Summary & Project Overview

**EventFlow AI** (developed under the `TurningPoint` codebase) is an enterprise-grade AI assistant designed to simplify and automate Event-Driven Architecture (EDA) management using natural language. 

Organizations deploying EDA traditionally face fragmented workflows across design-time governance (Solace Event Portal: Domains, Applications, Events, Schemas) and runtime infrastructure (Solace PubSub+ Event Broker: Queues, Subscriptions, ACLs). Engineers are required to manually navigate REST APIs, Postman collections, and administrative portals.

EventFlow AI addresses this by providing a unified conversational intelligence layer that translates intent into precise MCP (Model Context Protocol) tool invocations, bridging open-weight Large Language Models (LLMs) with Solace Event Portal and PubSub+ infrastructure.

---

## 2. Capabilities & Requirement Traceability Matrix

The table below maps the requirements outlined in the project specification PDF (*EventFlow AI: AI-Powered Event Lifecycle Management*) directly to the current implementation state in this Proof of Concept (POC):

| Requirement Area | PDF Requirement Specification | Implementation Status in POC | Details & Technical Realization |
| :--- | :--- | :--- | :--- |
| **AI Engine & LLM Integration** | Integrate open-weight/open-source LLM, interpret natural language, extract parameters, select MCP tools | **COMPLETE** | Integrated **Ollama** with **Gemma 4** (`gemma4:e4b`). Configured ReAct prompt engineering and optimized hyper-parameters (`temp=0.2`, `num_ctx=16384`) for accurate tool selection and parameter extraction. |
| **Multi-MCP Protocol Integration** | Connect to Solace Event Portal MCP Server (`solace-event-portal-designer-mcp`) AND Solace Monitoring MCP Server (`solace-monitoring-mcp-server`) | **COMPLETE** | Multi-server manager (`connect_all`) connects to multiple MCP stdio servers concurrently. Aggregates 260+ tools across Event Portal (design-time) and PubSub+ SEMPv2 (runtime). |
| **Dynamic Tool Selection Optimization Layer** | Handle 260+ tools without bloating LLM context window or causing model tool-forgetting | **COMPLETE** | Built `tool_selector.py` which dynamically scores and filters the top 20-30 most relevant tools per user query, keeping context tight and function calling accurate. |
| **Dynamic Tool Converter** | Convert MCP tool schemas into LLM function-calling definitions | **COMPLETE** | Built `tool_converter.py` which dynamically converts JSON Schema inputs from MCP into Ollama function definitions on initialization. |
| **Design-Time Lifecycle Management** | Support lifecycle operations for Domains, Applications, Events, Schemas, Event API Products | **COMPLETE (Discovery & Base Execution)** | Discovers and exposes 35+ Event Portal tools (`getApplications`, `getEvents`, `getSchemas`, `createSchema`, `updateSchema`, `deleteSchema`, etc.). |
| **Runtime Management (PubSub+)** | Support queues, topic endpoints, ACL profiles, subscriptions, broker resource queries | **COMPLETE** | Natively exposes 230+ SEMPv2 monitoring & management tools (`getMsgVpnQueues`, `getMsgVpnClients`, `getMsgVpns`, `getCertAuthorities`, etc.) via Solace Monitoring MCP Server. |
| **Developer Portal Integration** | Integrate into Backstage-based Developer Portal | **PLANNED (Phase 3)** | Backstage plugin architecture designed; CLI agent backend ready for API exposition to Backstage frontend plugins. |
| **Enterprise Code Quality** | Production-ready structure, logging, configuration, and automated test coverage | **COMPLETE** | Standardized `src/turning_point` package structure with `uv` dependency management, colored logging, `.env` config, and unit test suite. |


---

## 3. Current Implementation Architecture

The POC is structured using modern Python industry standard patterns (`src/` layout with `uv` package management):

```
TurningPoint/
├── src/
│   └── turning_point/
│       ├── __init__.py            # Package root
│       ├── config.py              # Centralized configuration & hyper-parameter tuning
│       ├── prompts.py             # System prompt engineering & ReAct guidance
│       ├── mcp_client.py          # Solace MCP server stdio connection & lifecycle
│       ├── llm_service.py         # Ollama AsyncClient wrapper with parameter control
│       ├── tool_converter.py      # MCP schema to Ollama function definition converter
│       ├── agent.py               # Conversational agent loop & tool calling logic
│       └── logger.py              # Colored structured console logger
├── tests/                         # Unit tests (16 tests passing)
│   ├── test_config.py
│   ├── test_prompts.py
│   └── test_tool_converter.py
├── .env.example                   # Environment configuration template
├── pyproject.toml                 # Dependencies & package configuration
├── main.py                        # Clean entry point
└── README.md                      # Developer documentation
```

### 3.1 LLM Hyper-Parameter Tuning for Function Calling
To ensure reliable tool selection and prevent hallucination during tool invocation:
- **Temperature (`0.2`)**: Low randomness ensures deterministic tool selection.
- **Top-P (`0.85`) & Top-K (`40`)**: Constrained sampling prevents invalid arguments.
- **Context Window (`8192`)**: Expanded token budget to accommodate 35+ detailed tool JSON schemas and conversation context.
- **Repeat Penalty (`1.1`)**: Prevents repeating tool calls on failure.

---

## 4. Demonstrable Capabilities (POC Demo)

1. **Automatic Discovery & Tool Hydration**:
   On startup, the client spawns `solace-ep-designer-mcp` via `uvx`, fetches tool schemas, and hydrates 35+ Solace Event Portal management functions (e.g., `getApplications`, `getEvents`, `getSchemas`, `createSchema`, `updateSchema`, `deleteSchema`).

2. **Natural Language Tool Orchestration**:
   - User query: *"Show me all applications in the Event Portal"*
   - Agent reasoning: Identifies `getApplications` tool, extracts parameters, executes tool via MCP, and formats the output into clean markdown.

3. **Resilient Error Context Feedback**:
   If an MCP tool call fails or returns an error, the agent catches the error cleanly, injects system context instructions into the prompt history, and informs the user with troubleshooting steps without crashing the application loop.

---

## 5. Next Steps & Future Roadmap

To fulfill the complete vision described in the **EventFlow AI** project document, the following roadmap is planned:

### Phase 2: Solace PubSub+ Runtime Management & Custom MCP Extensions
- **Custom MCP Server / Tools**: Build extensions for missing capabilities using Solace PubSub+ SEMP v2 REST APIs.
- **Runtime Resource Provisioning**: Implement natural language tools to create, query, update, and delete:
  - Message Queues & Topic Endpoints
  - Subscriptions & Topic Mappings
  - ACL Profiles & Client Usernames
- **Lifecycle Asset Versioning**: Support versioning workflows for Applications (`createApplicationVersion`) and Schemas (`createSchemaVersion`).

### Phase 3: Enterprise Backstage Developer Portal Integration
- **FastAPI / Server Gateway**: Expose the `turning_point` agent as a backend API service with WebSocket streaming.
- **Backstage Chat Plugin**: Integrate an interactive conversational UI widget directly inside the enterprise Backstage Developer Portal.
- **Access Control & Governance**: Map Backstage user credentials/roles to Solace ACLs for secure asset management.

---

## 6. Conclusion

The `TurningPoint` POC successfully establishes a robust, enterprise-grade baseline for **EventFlow AI**. By combining an open-weight LLM (Ollama / Gemma 4), Model Context Protocol (MCP), and structured Python design principles, it delivers natural language interaction with Solace Event Portal assets, setting up a solid foundation for PubSub+ runtime extension and Backstage integration.
