from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: str | Path | None = None, level: str | None = None) -> Path:
    """Configure stderr plus a small rotating file log for the MCP process."""
    destination = Path(log_dir or os.environ.get("COMET_LOG_DIR", "state/logs"))
    destination.mkdir(parents=True, exist_ok=True)
    log_path = destination / "comet-kvm.log"

    level_name = (level or os.environ.get("COMET_LOG_LEVEL", "INFO")).upper()
    log_level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    stderr = logging.StreamHandler()
    stderr.setFormatter(formatter)
    logfile = RotatingFileHandler(
        log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    logfile.setFormatter(formatter)

    logging.basicConfig(level=log_level, handlers=[stderr, logfile], force=True)
    # Avoid verbose protocol internals and authenticated WebSocket URLs at DEBUG.
    logging.getLogger("websockets").setLevel(logging.WARNING)
    return log_path
