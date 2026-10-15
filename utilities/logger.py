"""
HospitalRobotNav — Structured Logging Utility
==============================================
Provides a unified, colored, structured logger for the entire system.

Design:
    - Single factory function `get_logger()` — call once per module.
    - Uses Python's `logging` + `rich.Console` for colored terminal output.
    - Log levels: DEBUG → INFO → WARNING → ERROR → CRITICAL
    - All loggers write to both console and a rotating file.
    - Log file stored at: logs/hospital_robot.log

ROS2 Note:
    Replace calls to `get_logger()` with `self.get_logger()` from the
    rclpy.node.Node base class when deploying as a ROS2 node.

Usage:
    from utilities.logger import get_logger
    log = get_logger(__name__)
    log.info("Robot initialized at (%d, %d)", x, y)
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# ANSI Color Codes for console output (fallback if rich is unavailable)
# ─────────────────────────────────────────────────────────────────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_COLORS = {
    "DEBUG":    "\033[36m",    # Cyan
    "INFO":     "\033[32m",    # Green
    "WARNING":  "\033[33m",    # Yellow
    "ERROR":    "\033[31m",    # Red
    "CRITICAL": "\033[35m",    # Magenta
}


class _ColorFormatter(logging.Formatter):
    """Custom formatter that adds color to log level names."""

    FMT = "{color}[{levelname:<8}]{reset} {bold}{name}{reset} — {message}"

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, _RESET)
        record.color = color
        record.reset = _RESET
        record.bold = _BOLD
        formatter = logging.Formatter(
            fmt=self.FMT.format(
                color=color,
                reset=_RESET,
                bold=_BOLD,
                levelname="{levelname}",
                name="{name}",
                message="{message}",
            ),
            style="{",
            datefmt="%H:%M:%S",
        )
        res = formatter.format(record)
        if sys.platform == "win32":
            enc = getattr(sys.stdout, "encoding", None) or "utf-8"
            return res.encode(enc, errors="replace").decode(enc)
        return res


class _PlainFormatter(logging.Formatter):
    """Plain formatter for file output (no ANSI codes)."""

    def __init__(self) -> None:
        super().__init__(
            fmt="[%(asctime)s] [%(levelname)-8s] %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Logger Registry — ensures one logger per module name
# ─────────────────────────────────────────────────────────────────────────────

_loggers: dict[str, logging.Logger] = {}
_initialized: bool = False
_log_level: int = logging.INFO


def _ensure_log_dir() -> str:
    """Create logs/ directory next to the project root."""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


class WindowsSafeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """
    RotatingFileHandler subclass that gracefully handles Windows file locking
    (WinError 32) when multiple processes (e.g. uvicorn reloader and worker processes)
    have the log file open simultaneously.
    """

    def doRollover(self):
        try:
            if self.stream:
                self.stream.close()
                self.stream = None
            super().doRollover()
        except (PermissionError, OSError):
            # On Windows, if another process has the log file open, renaming fails.
            # Silently retain existing file and continue writing to it.
            pass
        finally:
            if not self.stream:
                self.stream = self._open()


def initialize_logging(level: str = "INFO") -> None:
    """
    Initialize the root logging configuration.

    Must be called once at application startup (main.py).
    Subsequent calls are no-ops.

    Args:
        level: Log level string — "DEBUG", "INFO", "WARNING", "ERROR"
    """
    global _initialized, _log_level

    if _initialized:
        return

    _log_level = getattr(logging, level.upper(), logging.INFO)

    # ── Root logger ───────────────────────────────────────────────────────────
    root = logging.getLogger("HospitalRobotNav")
    root.setLevel(_log_level)
    root.propagate = False

    # ── Console handler ───────────────────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(_log_level)
    console_handler.setFormatter(_ColorFormatter())
    root.addHandler(console_handler)

    # ── Rotating file handler ─────────────────────────────────────────────────
    try:
        log_dir = _ensure_log_dir()
        log_file = os.path.join(log_dir, "hospital_robot.log")
        file_handler = WindowsSafeRotatingFileHandler(
            log_file,
            maxBytes=20 * 1024 * 1024,  # 20 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(_PlainFormatter())
        root.addHandler(file_handler)
    except (OSError, PermissionError) as e:
        root.warning("Could not create log file: %s", e)

    _initialized = True
    root.info("━" * 60)
    root.info("  Hospital Robot Navigation System — Logging Initialized")
    root.info("━" * 60)


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Retrieve or create a named logger for a module.

    Args:
        name:  Module name, typically `__name__`. Used as the logger name.
        level: Optional override for this logger's level.

    Returns:
        A configured `logging.Logger` instance.

    Example:
        log = get_logger(__name__)
        log.info("Planner initialized: %s", planner_name)
    """
    if not _initialized:
        initialize_logging()

    # Normalize: strip leading package path for display
    short_name = name.split(".")[-1] if "." in name else name
    full_name = f"HospitalRobotNav.{short_name}"

    if full_name not in _loggers:
        logger = logging.getLogger(full_name)
        if level:
            logger.setLevel(getattr(logging, level.upper(), _log_level))
        _loggers[full_name] = logger

    return _loggers[full_name]
