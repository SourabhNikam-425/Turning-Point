# TurningPoint — Solace Event Portal MCP Agent

An AI-powered agent that connects to the **Solace Event Portal** via the **Model Context Protocol (MCP)**, enabling natural language interaction with your event-driven architecture.

Ask questions, explore applications, events, schemas, and domains — all through conversation.

## Architecture

```
main.py                          ← Thin entry point
└── src/turning_point/
    ├── config.py                ← Centralized config + model params
    ├── prompts.py               ← System prompts (ReAct pattern)
    ├── mcp_client.py            ← MCP server connection & tool execution
    ├── llm_service.py           ← Ollama LLM interaction layer
    ├── tool_converter.py        ← MCP → Ollama schema conversion
    ├── agent.py                 ← Agentic loop orchestration
    └── logger.py                ← Structured colored logging
```

## Prerequisites

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager
- **[Ollama](https://ollama.com/)** — running locally with a model pulled
- **Solace Event Portal** account with an API token

## Setup

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd TurningPoint

# 2. Create your environment file
cp .env.example .env
# Edit .env and add your SOLACE_API_TOKEN

# 3. Install dependencies
uv sync

# 4. Pull the Ollama model (if not already)
ollama pull gemma4:e4b

# 5. Run the agent
uv run python main.py
```

## Configuration

All settings are configurable via the `.env` file. See [`.env.example`](.env.example) for the full list.

### Model Parameters

These parameters control how the LLM generates responses. They are tuned for **tool-calling accuracy** by default:

| Parameter | Default | Description |
|:---|:---|:---|
| `OLLAMA_TEMPERATURE` | `0.2` | Creativity (lower = more precise) |
| `OLLAMA_TOP_P` | `0.85` | Nucleus sampling threshold |
| `OLLAMA_TOP_K` | `40` | Token selection breadth |
| `OLLAMA_NUM_CTX` | `8192` | Context window (tokens) |
| `OLLAMA_NUM_PREDICT` | `2048` | Max output tokens |
| `OLLAMA_REPEAT_PENALTY` | `1.1` | Repetition penalty |
| `OLLAMA_SEED` | _(unset)_ | Set for reproducible outputs |

### Tips

- **For debugging**, set `LOG_LEVEL=DEBUG` to see full tool arguments and results.
- **For reproducibility**, set `OLLAMA_SEED=42` (or any integer).
- **For more creative responses**, increase `OLLAMA_TEMPERATURE` to `0.7`.

## Usage

```
You: List all applications in the event portal
Assistant: I'll use the list_applications tool to fetch that for you...

You: What events does the "OrderService" application publish?
Assistant: Let me look up the events for OrderService...

You: exit
Goodbye!
```

## Running Tests

```bash
uv pip install -e ".[dev]"
uv run pytest tests/ -v
```

## License

Private — internal use only.
