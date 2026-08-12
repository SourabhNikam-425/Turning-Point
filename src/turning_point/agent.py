import json
from .config import load_config
from .llm_service import LLMService
from .logger import get_logger
from .mcp_client import connect, discover_tools, execute_tool
from .prompts import build_error_context, build_system_prompt
from .tool_converter import convert_all_tools, extract_tool_names

log = get_logger("agent")


async def _handle_tool_calls(
    session,
    llm: LLMService,
    tool_calls,
) -> None:
    """Process tool calls from the LLM response.

    Executes each tool via MCP and feeds results back to the LLM.

    Args:
        session: The MCP ClientSession.
        llm: The LLM service instance.
        tool_calls: The tool calls from the LLM response.
    """
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        arguments = tool_call.function.arguments

        log.info("Tool requested: %s", tool_name)
        log.debug("Arguments: %s", json.dumps(arguments))

        # Execute via MCP
        result = await execute_tool(
            session, tool_name, arguments
        )

        # Check if the result is an error
        if result.startswith("Tool '") and "failed:" in result:
            # Feed error context to help the LLM respond
            error_context = build_error_context(
                tool_name, result
            )
            llm.add_tool_result(tool_name, error_context)
            log.warning(
                "Tool '%s' returned an error", tool_name
            )
        else:
            llm.add_tool_result(tool_name, result)


async def _agent_loop(
    session,
    llm: LLMService,
    ollama_tools: list[dict],
) -> None:
    """The main interactive agent loop.

    Reads user input, sends to LLM, handles tool calls,
    and prints responses until the user exits.

    Args:
        session: The MCP ClientSession.
        llm: The LLM service instance.
        ollama_tools: Ollama-formatted tool definitions.
    """
    print(
        "\n╔══════════════════════════════════════════╗"
        "\n║    TurningPoint — Solace MCP Agent       ║"
        "\n║    Type 'exit' or 'quit' to stop.        ║"
        "\n╚══════════════════════════════════════════╝\n"
    )

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        if not user_input:
            continue

        llm.add_user_message(user_input)

        # Inner loop: handle multi-step tool calls
        while True:
            try:
                response = await llm.chat(tools=ollama_tools)
            except Exception as e:
                log.error("LLM call failed: %s", e)
                print(
                    f"\n[Error] LLM call failed: {e}\n"
                    "Please try again.\n"
                )
                break

            # No tool calls → final text response
            if not response.message.tool_calls:
                llm.add_assistant_message(response.message)
                print(
                    f"\nAssistant: "
                    f"{response.message.content}\n"
                )
                break

            # LLM requested tool calls
            llm.add_assistant_message(response.message)

            await _handle_tool_calls(
                session, llm, response.message.tool_calls
            )


async def run_agent() -> None:
    """Entry point — wire everything together and start the agent.

    Loads config, connects to MCP, initializes the LLM, and
    runs the interactive agent loop.
    """
    # Load configuration
    config = load_config()

    # Connect to MCP and run agent
    async with connect(config.mcp) as session:

        # Discover tools
        mcp_tools = await discover_tools(session)
        ollama_tools = convert_all_tools(mcp_tools)
        tool_names = extract_tool_names(mcp_tools)

        # Log discovered tools
        log.info("Tools available to the model:")
        for i, name in enumerate(tool_names, start=1):
            log.info("  %d. %s", i, name)

        # Initialize LLM with system prompt
        llm = LLMService(
            host=config.ollama_host,
            model_config=config.model,
        )

        system_prompt = build_system_prompt(tool_names)
        llm.set_system_prompt(system_prompt)

        # Run the interactive loop
        await _agent_loop(session, llm, ollama_tools)
