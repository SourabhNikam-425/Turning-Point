"""LLM service — manages Ollama interaction and message history.

Wraps the Ollama AsyncClient with proper model parameter support
and message management.
"""

from typing import Any

from ollama import AsyncClient

from .config import ModelConfig
from .logger import get_logger

log = get_logger("llm")


class LLMService:
    """Manages Ollama LLM interactions with configurable parameters.

    Attributes:
        client: The Ollama AsyncClient instance.
        model_config: Model generation parameters.
        messages: The conversation message history.
    """

    def __init__(
        self,
        host: str,
        model_config: ModelConfig,
    ) -> None:
        """Initialize the LLM service.

        Args:
            host: The Ollama server URL.
            model_config: Model generation parameters.
        """
        self.client = AsyncClient(host=host)
        self.model_config = model_config
        self.messages: list[dict[str, Any]] = []

        log.info("LLM service initialized")
        log.info("Model: %s", model_config.model)
        log.info(
            "Parameters: temp=%.2f top_p=%.2f top_k=%d "
            "ctx=%d predict=%d repeat=%.2f",
            model_config.temperature,
            model_config.top_p,
            model_config.top_k,
            model_config.num_ctx,
            model_config.num_predict,
            model_config.repeat_penalty,
        )

    def set_system_prompt(self, prompt: str) -> None:
        """Set the system prompt as the first message.

        Args:
            prompt: The system prompt text.
        """
        self.messages = [
            {"role": "system", "content": prompt}
        ]
        log.debug("System prompt set (%d chars)", len(prompt))

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation history.

        Args:
            content: The user's message text.
        """
        self.messages.append(
            {"role": "user", "content": content}
        )

    def add_assistant_message(self, message: Any) -> None:
        """Add the assistant's response to the history.

        Args:
            message: The Ollama message object or dict.
        """
        self.messages.append(message)

    def add_tool_result(
        self,
        tool_name: str,
        content: str,
    ) -> None:
        """Add a tool result to the conversation history.

        Args:
            tool_name: The name of the tool that was called.
            content: The tool's result text.
        """
        self.messages.append(
            {
                "role": "tool",
                "tool_name": tool_name,
                "content": content,
            }
        )

    async def chat(
        self,
        tools: list[dict] | None = None,
    ) -> Any:
        """Send the current message history to the model.

        Args:
            tools: Optional list of Ollama-formatted tool dicts.

        Returns:
            The Ollama chat response object.

        Raises:
            Exception: If the Ollama API call fails.
        """
        options = self.model_config.to_ollama_options()

        log.debug(
            "Sending %d messages to model (with %d tools)",
            len(self.messages),
            len(tools) if tools else 0,
        )

        try:
            response = await self.client.chat(
                model=self.model_config.model,
                messages=self.messages,
                tools=tools or [],
                options=options,
            )
            return response

        except Exception as e:
            log.error(
                "Ollama API error: %s: %s",
                type(e).__name__,
                e,
            )
            raise
