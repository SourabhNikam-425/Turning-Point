"""Structured logging for the TurningPoint MCP agent."""

import logging
import sys


# ANSI color codes for console output
_COLORS = {
    "DEBUG": "\033[36m",     # Cyan
    "INFO": "\033[32m",      # Green
    "WARNING": "\033[33m",   # Yellow
    "ERROR": "\033[31m",     # Red
    "CRITICAL": "\033[35m",  # Magenta
    "RESET": "\033[0m",
}

# Module-specific prefixes for clarity
PREFIXES = {
    "mcp": "[MCP]",
    "llm": "[LLM]",
    "agent": "[AGENT]",
    "config": "[CONFIG]",
    "tools": "[TOOLS]",
}


class ColoredFormatter(logging.Formatter):
    """A log formatter that adds ANSI colors and module prefixes."""

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, "")
        reset = _COLORS["RESET"]

        # Add color to the level name
        record.levelname = f"{color}{record.levelname:<8}{reset}"

        return super().format(record)


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Create a configured logger with colored console output.

    Args:
        name: Logger name — use one of the PREFIXES keys
              (e.g., "mcp", "llm", "agent") for consistent labeling.
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(f"turning_point.{name}")

    # Prevent duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    # Console handler with color
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)

    prefix = PREFIXES.get(name, f"[{name.upper()}]")
    formatter = ColoredFormatter(
        fmt=f"%(levelname)s {prefix} %(message)s",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
