import json
from .config import AppConfig, load_config
from .llm_service import LLMService
from .logger import get_logger
from .mcp_client import connect_all, discover_tools, execute_tool
from .prompts import build_error_context, build_system_prompt
from .tool_converter import extract_tool_names
from .tool_selector import select_relevant_tools

log = get_logger("agent")


async def _handle_tool_calls(
    session,
    llm: LLMService,
    tool_calls,
) -> set[str]:
    """Process tool calls from the LLM response.

    Executes each tool via MCP and feeds results back to the LLM.

    Args:
        session: The MCP session manager.
        llm: The LLM service instance.
        tool_calls: The tool calls from the LLM response.

    Returns:
        Set of tool names executed in this step.
    """
    executed_tools = set()
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        arguments = tool_call.function.arguments

        log.info("Tool requested: %s", tool_name)
        log.debug("Arguments: %s", json.dumps(arguments))
        executed_tools.add(tool_name)

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

    return executed_tools


async def _agent_loop(
    session,
    llm: LLMService,
    all_mcp_tools: list,
    config: AppConfig,
) -> None:
    """The main interactive agent loop.

    Reads user input, sends to LLM, handles tool calls,
    and prints responses until the user exits.

    Args:
        session: The MCP session manager.
        llm: The LLM service instance.
        all_mcp_tools: Full list of discovered MCP tool objects.
        config: Application configuration.
    """
    print(
        "\n╔══════════════════════════════════════════╗"
        "\n║    TurningPoint — Solace MCP Agent       ║"
        "\n║    Type 'exit' or 'quit' to stop.        ║"
        "\n╚══════════════════════════════════════════╝\n"
    )

    history_tool_names: set[str] = set()

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
            # Dynamic Tool Selection Optimization Layer
            ollama_tools, _ = select_relevant_tools(
                all_tools=all_mcp_tools,
                user_query=user_input,
                max_tools=config.max_tools_per_query,
                history_tool_names=history_tool_names,
            )

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

            executed = await _handle_tool_calls(
                session, llm, response.message.tool_calls
            )
            history_tool_names.update(executed)


async def run_agent() -> None:
    """Entry point — wire everything together and start the agent.

    Loads config, connects to MCP servers, initializes the LLM, and
    runs the interactive agent loop.
    """
    # Load configuration
    config = load_config()

    # Connect to MCP servers and run agent
    async with connect_all(config.mcp) as session:

        # Discover tools across all servers
        mcp_tools = await discover_tools(session)
        tool_names = extract_tool_names(mcp_tools)

        # Log discovered tools summary
        log.info("Total %d MCP tools available across servers", len(tool_names))
        log.info("Dynamic Tool Selection Optimization Layer active (max %d tools per query)", config.max_tools_per_query)

        # Initialize LLM with system prompt
        llm = LLMService(
            host=config.ollama_host,
            model_config=config.model,
        )

        system_prompt = build_system_prompt(tool_names)
        llm.set_system_prompt(system_prompt)

        # Run the interactive loop
        await _agent_loop(session, llm, mcp_tools, config)

