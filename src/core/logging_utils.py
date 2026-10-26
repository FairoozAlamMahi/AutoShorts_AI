"""Structured logging utilities with thread-safe UI log buffer."""
import logging
import sys
from collections import deque
from pathlib import Path
from typing import List, Optional

_UI_LOG_BUFFER: deque[str] = deque(maxlen=500)


class UILogHandler(logging.Handler):
    """Custom logging handler that buffers log records for the Gradio dashboard."""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            _UI_LOG_BUFFER.append(msg)
        except Exception:
            self.handleError(record)


def setup_logger(name: str = "shorts_factory", log_dir: Optional[Path] = None, level: int = logging.INFO) -> logging.Logger:
    """Configures and returns the application logger."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # UI buffer handler
    ui_handler = UILogHandler()
    ui_handler.setFormatter(formatter)
    logger.addHandler(ui_handler)

    # File handler if log_dir provided
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "shorts_factory.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_ui_logs(max_lines: int = 100) -> List[str]:
    """Returns the latest log lines from the UI buffer."""
    return list(_UI_LOG_BUFFER)[-max_lines:]


def clear_ui_logs() -> None:
    """Clears the UI log buffer."""
    _UI_LOG_BUFFER.clear()
