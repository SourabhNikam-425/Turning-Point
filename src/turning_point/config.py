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
class MCPServerConfig:
    """Configuration for an individual MCP server."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


@dataclass(frozen=True)
class MCPConfig:
    """Solace MCP server connection settings supporting multiple servers."""

    servers: list[MCPServerConfig] = field(default_factory=list)
    api_token: str = ""
    api_base_url: str = "https://api.solace.cloud"
    command: str = "uvx"
    package: str = "solace-event-portal-designer-mcp"
    executable: str = "solace-ep-designer-mcp"


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    ollama_host: str = "http://localhost:11434"
    log_level: str = "INFO"
    max_tools_per_query: int = 30
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

    servers: list[MCPServerConfig] = []

    # 1. Solace Event Portal Designer MCP Server
    ep_enabled = os.getenv("ENABLE_SOLACE_EP_DESIGNER_MCP", "true").lower() == "true"
    if ep_enabled:
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        ep_dir = os.path.join(
            base_dir,
            "solace-platform-mcp-main",
            "solace-event-portal-designer-mcp",
        )
        if os.path.exists(ep_dir):
            ep_command = os.getenv("SOLACE_EP_COMMAND", "uv")
            ep_args = [
                "run",
                "--project",
                ep_dir,
                "solace-ep-designer-mcp",
            ]
        else:
            ep_command = os.getenv("SOLACE_EP_COMMAND", "uvx")
            ep_args = [
                "--from",
                os.getenv("SOLACE_EP_PACKAGE", "solace-event-portal-designer-mcp"),
                os.getenv("SOLACE_EP_EXECUTABLE", "solace-ep-designer-mcp"),
            ]

        ep_server = MCPServerConfig(
            name="ep-designer",
            command=ep_command,
            args=ep_args,
            env={
                "SOLACE_API_TOKEN": solace_token,
                "SOLACE_API_BASE_URL": os.getenv(
                    "SOLACE_API_BASE_URL", "https://api.solace.cloud"
                ),
            },
            enabled=True,
        )
        servers.append(ep_server)

    # 2. Solace Monitoring MCP Server
    monitoring_enabled = (
        os.getenv("ENABLE_SOLACE_MONITORING_MCP", "true").lower() == "true"
    )
    if monitoring_enabled:
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        monitoring_script = os.path.join(
            base_dir,
            "solace-platform-mcp-main",
            "solace-monitoring-mcp-server",
            "solace_monitoring_mcp_server.py",
        )
        swagger_spec = os.path.join(
            base_dir,
            "solace-platform-mcp-main",
            "solace-monitoring-mcp-server",
            "semp-v2-swagger-monitor.json",
        )

        # The monitoring server needs the /SEMP/v2/monitor endpoint.
        # If SOLACE_SEMPV2_BASE_URL points to /config, auto-derive /monitor.
        config_base_url = os.getenv("SOLACE_SEMPV2_BASE_URL", "http://localhost:8080")
        monitor_base_url = os.getenv(
            "SOLACE_SEMPV2_MONITOR_BASE_URL",
            config_base_url.replace("/SEMP/v2/config", "/SEMP/v2/monitor"),
        )

        monitoring_env = {
            "OPENAPI_SPEC": os.getenv("OPENAPI_SPEC", swagger_spec),
            "SOLACE_SEMPV2_BASE_URL": monitor_base_url,
            "SOLACE_SEMPV2_AUTH_METHOD": os.getenv(
                "SOLACE_SEMPV2_AUTH_METHOD", "basic"
            ),
            "SOLACE_SEMPV2_USERNAME": os.getenv("SOLACE_SEMPV2_USERNAME", "admin"),
            "SOLACE_SEMPV2_PASSWORD": os.getenv("SOLACE_SEMPV2_PASSWORD", "admin"),
            "MCP_API_INCLUDE_PATHS": os.getenv(
                "MCP_API_INCLUDE_PATHS",
                "/queues,/clients,/clientUsernames,/aclProfiles",
            ),
        }
        if os.getenv("SOLACE_SEMPV2_BEARER_TOKEN"):
            monitoring_env["SOLACE_SEMPV2_BEARER_TOKEN"] = os.getenv(
                "SOLACE_SEMPV2_BEARER_TOKEN"
            )
        if os.getenv("MCP_API_INCLUDE_TOOLS"):
            monitoring_env["MCP_API_INCLUDE_TOOLS"] = os.getenv(
                "MCP_API_INCLUDE_TOOLS"
            )
        if os.getenv("MCP_API_INCLUDE_TAGS"):
            monitoring_env["MCP_API_INCLUDE_TAGS"] = os.getenv(
                "MCP_API_INCLUDE_TAGS"
            )

        import sys
        monitoring_server = MCPServerConfig(
            name="solace-monitoring",
            command=os.getenv("SOLACE_MONITORING_COMMAND", sys.executable),
            args=[monitoring_script],
            env=monitoring_env,
            enabled=True,
        )
        servers.append(monitoring_server)

    # 3. Solace Config MCP Server (SEMPv2 write operations: queues, subscriptions)
    config_mcp_enabled = (
        os.getenv("ENABLE_SOLACE_CONFIG_MCP", "true").lower() == "true"
    )
    if config_mcp_enabled:
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        config_script = os.path.join(
            base_dir,
            "solace-platform-mcp-main",
            "solace-monitoring-mcp-server",
            "solace_config_mcp_server.py",
        )

        config_sempv2_url = os.getenv("SOLACE_SEMPV2_BASE_URL", "http://localhost:8080")
        # Ensure we're pointing at the /config endpoint, not /monitor
        if "/SEMP/v2/monitor" in config_sempv2_url:
            config_sempv2_url = config_sempv2_url.replace("/SEMP/v2/monitor", "/SEMP/v2/config")

        config_mcp_env = {
            "SOLACE_SEMPV2_BASE_URL": config_sempv2_url,
            "SOLACE_SEMPV2_AUTH_METHOD": os.getenv("SOLACE_SEMPV2_AUTH_METHOD", "basic"),
            "SOLACE_SEMPV2_USERNAME": os.getenv("SOLACE_SEMPV2_USERNAME", "admin"),
            "SOLACE_SEMPV2_PASSWORD": os.getenv("SOLACE_SEMPV2_PASSWORD", "admin"),
        }
        if os.getenv("SOLACE_SEMPV2_BEARER_TOKEN"):
            config_mcp_env["SOLACE_SEMPV2_BEARER_TOKEN"] = os.getenv("SOLACE_SEMPV2_BEARER_TOKEN")

        import sys as _sys
        config_server = MCPServerConfig(
            name="solace-config",
            command=os.getenv("SOLACE_CONFIG_COMMAND", _sys.executable),
            args=[config_script],
            env=config_mcp_env,
            enabled=True,
        )
        servers.append(config_server)

    mcp_config = MCPConfig(
        servers=servers,
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

    max_tools = int(os.getenv("OLLAMA_MAX_TOOLS_PER_QUERY", "30"))

    config = AppConfig(
        ollama_host=os.getenv("OLLAMA_HOST", AppConfig.ollama_host),
        log_level=os.getenv("LOG_LEVEL", AppConfig.log_level),
        max_tools_per_query=max_tools,
        mcp=mcp_config,
        model=model_config,
    )

    log.info("Configuration loaded successfully with %d MCP server(s)", len(servers))
    log.debug("Model: %s", config.model.model)
    log.debug(
        "Temperature: %.2f | Top-P: %.2f | Top-K: %d",
        config.model.temperature,
        config.model.top_p,
        config.model.top_k,
    )
    log.debug("Context window: %d tokens | Max tools per query: %d", config.model.num_ctx, config.max_tools_per_query)

    return config

