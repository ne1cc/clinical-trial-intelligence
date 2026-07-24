import os
import sys

from loguru import logger

_CONFIGURED = False


def setup_logging():
    """Configure the shared loguru logger once. Level comes from CTI_LOG_LEVEL (default INFO)."""
    global _CONFIGURED
    if not _CONFIGURED:
        logger.remove()
        logger.add(
            sys.stderr,
            level=os.getenv("CTI_LOG_LEVEL", "INFO").upper(),
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS!UTC}Z</green> "
                "| <level>{level: <8}</level> | {name}:{function} - <level>{message}</level>"
            ),
        )
        _CONFIGURED = True
    return logger
