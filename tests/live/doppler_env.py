from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOPPLER_YAML = _REPO_ROOT / "doppler.yaml"


def doppler_project_config() -> tuple[str, str]:
    """Return (project, config) from doppler.yaml, with repo defaults."""
    project = "secrets_managment"
    config = "dev"
    if not _DOPPLER_YAML.is_file():
        return project, config
    try:
        import yaml  # optional; fall back to defaults if unavailable
    except ImportError:
        text = _DOPPLER_YAML.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("project:"):
                project = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("config:"):
                config = stripped.split(":", 1)[1].strip()
        return project, config

    data = yaml.safe_load(_DOPPLER_YAML.read_text(encoding="utf-8")) or {}
    setup = data.get("setup") or {}
    return str(setup.get("project") or project), str(setup.get("config") or config)


def _doppler_get_plain(name: str, project: str, config: str) -> Optional[str]:
    """Fetch one secret via Doppler CLI. Never logs the value."""
    try:
        completed = subprocess.run(
            [
                "doppler",
                "secrets",
                "get",
                name,
                "--plain",
                "-p",
                project,
                "-c",
                config,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            cwd=str(_REPO_ROOT),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if completed.returncode != 0:
        return None
    value = (completed.stdout or "").strip()
    return value or None


def resolve_comet_password() -> Optional[str]:
    """Resolve Comet password from env, else Doppler CLI (doppler.yaml project/config)."""
    existing = os.environ.get("COMET_PASSWORD") or os.environ.get("GLCOMET_ADMIN_PASSWORD")
    if existing:
        return existing

    project, config = doppler_project_config()
    for name in ("COMET_PASSWORD", "GLCOMET_ADMIN_PASSWORD"):
        value = _doppler_get_plain(name, project, config)
        if value:
            # Inject for the rest of this process so CometClient/tools see it.
            os.environ[name] = value
            return value
    return None
