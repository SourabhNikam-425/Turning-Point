"""Centralized configuration for the TurningPoint MCP agent.

All configuration is loaded from environment variables with sensible
defaults. Model parameters are tuned for tool-calling accuracy.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from .logger import get_logger

load_dotenv()

log = get_logger("config")


@dataclass(frozen=True)
class ModelConfig:
    """Ollama model generation parameters.

    Defaults are tuned for reliable tool-calling with Gemma 4.
    Lower temperature + constrained sampling = precise function calls.
    """

    model: str = "gemma4:e2b"
    temperature: float = 0.2
    top_p: float = 0.85
    top_k: int = 40
    num_ctx: int = 16384
    num_predict: int = 2048
    repeat_penalty: float = 1.1
    seed: int | None = None

    def to_ollama_options(self) -> dict:
        """Convert to Ollama-compatible options dict."""
        options = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
            "repeat_penalty": self.repeat_penalty,
        }
        if self.seed is not None:
            options["seed"] = self.seed
        return options


@dataclass(frozen=True)
class MCPConfig:
    """Solace MCP server connection settings."""

    api_token: str = ""
    api_base_url: str = "https://api.solacecloud.eu"
    command: str = "uvx"
    package: str = "solace-event-portal-designer-mcp"
    executable: str = "solace-ep-designer-mcp"


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    ollama_host: str = "http://localhost:11434"
    log_level: str = "INFO"
    mcp: MCPConfig = field(default_factory=MCPConfig)
    model: ModelConfig = field(default_factory=ModelConfig)


def load_config() -> AppConfig:
    """Load configuration from environment variables.

    Environment variables override the dataclass defaults.
    Model parameters can be set via OLLAMA_* env vars.

    Returns:
        A fully populated AppConfig instance.

    Raises:
        RuntimeError: If SOLACE_API_TOKEN is not set.
    """
    solace_token = os.getenv("SOLACE_API_TOKEN")
    if not solace_token:
        raise RuntimeError(
            "SOLACE_API_TOKEN is not set. "
            "Add it to your .env file or export it."
        )

    mcp_config = MCPConfig(
        api_token=solace_token,
        api_base_url=os.getenv(
            "SOLACE_API_BASE_URL",
            MCPConfig.api_base_url,
        ),
    )

    # Parse seed — None means non-deterministic
    raw_seed = os.getenv("OLLAMA_SEED")
    seed = int(raw_seed) if raw_seed else None

    model_config = ModelConfig(
        model=os.getenv("OLLAMA_MODEL", ModelConfig.model),
        temperature=float(
            os.getenv("OLLAMA_TEMPERATURE", ModelConfig.temperature)
        ),
        top_p=float(
            os.getenv("OLLAMA_TOP_P", ModelConfig.top_p)
        ),
        top_k=int(
            os.getenv("OLLAMA_TOP_K", ModelConfig.top_k)
        ),
        num_ctx=int(
            os.getenv("OLLAMA_NUM_CTX", ModelConfig.num_ctx)
        ),
        num_predict=int(
            os.getenv("OLLAMA_NUM_PREDICT", ModelConfig.num_predict)
        ),
        repeat_penalty=float(
            os.getenv("OLLAMA_REPEAT_PENALTY", ModelConfig.repeat_penalty)
        ),
        seed=seed,
    )

    config = AppConfig(
        ollama_host=os.getenv("OLLAMA_HOST", AppConfig.ollama_host),
        log_level=os.getenv("LOG_LEVEL", AppConfig.log_level),
        mcp=mcp_config,
        model=model_config,
    )

    log.info("Configuration loaded successfully")
    log.debug("Model: %s", config.model.model)
    log.debug(
        "Temperature: %.2f | Top-P: %.2f | Top-K: %d",
        config.model.temperature,
        config.model.top_p,
        config.model.top_k,
    )
    log.debug("Context window: %d tokens", config.model.num_ctx)

    return config
