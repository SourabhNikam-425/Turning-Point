# TurningPoint - POC Progress Tracker

**Project**: EventFlow AI - AI-Powered Event Lifecycle and Governance Management
**LLM**: Gemma 4 (`gemma4:e4b`) via Ollama
**MCP Server**: `solace-event-portal-designer-mcp` via `uvx`

---

## Phase 1 & 2: Multi-MCP Server & Tool Optimization Integration

| Task | Status | Note |
| :--- | :--- | :--- |
| Choose open-weight LLM | Done | Selected Gemma 4 (`gemma4:e4b`) via Ollama |
| Connect Gemma 4 to Ollama | Done | Gemma 4 successfully responds at `http://localhost:11434` |
| Gemma 4 tool/function calling | Done | Generates structured tool calls using Ollama function-calling format |
| Clone/setup Solace MCP | Done | `solace-event-portal-designer-mcp` + `solace-monitoring-mcp-server` configured |
| Authenticate with Solace | Done | `SOLACE_API_TOKEN` and SEMPv2 credentials configured in `.env` |
| Multi-MCP server startup | Done | Concurrently launches Event Portal Designer and PubSub+ Monitoring MCP servers |
| Multi-MCP client manager | Done | `MultiServerSessionManager` handles concurrent stdio sessions & tool routing |
| Discover Solace tools | Done | 260+ tools discovered across Event Portal & SEMPv2 broker monitoring |
| Dynamic Tool Selection Optimization Layer | Done | `tool_selector.py` dynamically filters top 20-30 tools per query to keep prompt lean |
| Execute Solace MCP tool | Done | End-to-end tool discovery, prompt filtering, and execution working |


---

## Known Limitation: Gemma 4 and Event Mutation

Gemma 4 (`gemma4:e4b`) currently does not reliably generate the correct tool call arguments for write/mutation operations such as `createEvent`, `updateEvent`, or `deleteEvent`.

**What works:**
- Read-only API operations (`getApplicationDomains`, `getApplications`, `getEvents`, `getSchemas`, etc.) execute correctly end-to-end.
- The full pipeline - natural language input to Gemma 4, to MCP tool call, to Solace Event Portal API, back to user - is functional for all GET-class operations.

**What does not work:**
- Gemma 4 does not consistently produce well-formed arguments for write operations that require nested JSON payloads (e.g., event body schemas, version metadata).
- When prompted to create an event, the model either omits required fields, hallucinates parameter names, or produces malformed JSON that the MCP server rejects.

**Root cause assessment:**
- Gemma 4 function-calling capability at this model size (`e4b` quantization) is constrained for complex nested argument generation.
- The `createEvent` and related mutation tools have deep, multi-field required schemas that exceed the reliable structured output capability of `gemma4:e4b` at `temperature=0.2`.

**Planned remediation (Phase 2):**
- Evaluate larger quantization or a different model (e.g., `gemma4:27b` or `qwen3:8b`) for mutation operations.
- Implement argument validation and a pre-call schema-filling prompt chain to guide the model through required fields one at a time.
- Consider a structured form-based fallback in the CLI for complex create/update operations.

---

## Phase 3: Enterprise Readiness (Planned)

| Task | Status | Note |
| :--- | :--- | :--- |
| PubSub+ runtime management (queues, ACLs, subscriptions) | Planned | Custom MCP extensions needed; SEMP v2 REST integration |
| Backstage Developer Portal plugin | Planned | FastAPI backend + Backstage chat plugin frontend |
| Access control and role-based governance | Planned | Map Backstage credentials to Solace ACL profiles |

---

## Architecture Reference

```
TurningPoint/
    src/
        turning_point/
            config.py          - Centralized config; ModelConfig tuned for Gemma 4
            prompts.py         - ReAct system prompt engineering
            mcp_client.py      - Stdio MCP connection, tool discovery, tool execution
            llm_service.py     - Ollama AsyncClient wrapper
            tool_converter.py  - MCP JSON Schema to Ollama function definition converter
            agent.py           - Conversational agent loop and tool calling logic
            logger.py          - Colored structured console logger
    tests/                     - 16 unit tests (pytest)
    main.py                    - Entry point
    .env                       - SOLACE_API_TOKEN and Ollama config
```

---

## LLM Configuration (Tuned for Tool Calling)

| Parameter | Value | Rationale |
| :--- | :--- | :--- |
| Model | `gemma4:e4b` | Open-weight, runs locally via Ollama |
| Temperature | `0.2` | Low randomness for deterministic tool selection |
| Top-P | `0.85` | Constrained sampling to prevent invalid arguments |
| Top-K | `40` | Limits vocabulary breadth during argument generation |
| Context Window | `8192` tokens | Fits 35+ tool schemas plus conversation history |
| Repeat Penalty | `1.1` | Prevents looping on failed tool calls |

---

Last updated: 2026-08-12
