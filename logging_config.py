"""
Logging configuration for the trading bot.
Sets up structured logging to both console and a rotating log file.
"""

import logging
import logging.handlers
import os
from pathlib import Path


LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "trading_bot.log"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Configure root logger with:
      - StreamHandler  → console (WARNING and above)
      - RotatingFileHandler → logs/trading_bot.log (all levels)
    Returns the package-level logger.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger("trading_bot")
    root_logger.setLevel(logging.DEBUG)  # capture everything; handlers filter

    if root_logger.handlers:
        # Already configured (e.g. during testing)
        return root_logger

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # --- Console handler ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(fmt)

    # --- File handler ---
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(fmt)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'trading_bot' namespace."""
    return logging.getLogger(f"trading_bot.{name}")
