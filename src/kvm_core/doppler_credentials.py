from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from collections.abc import Callable
from typing import Optional

LOG = logging.getLogger("kvm_core.doppler")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOPPLER_YAML = _REPO_ROOT / "doppler.yaml"
_PASSWORD_SECRET_NAMES = (
    "GLCOMET_ADMIN_PASSWORD",
    "COMET_ADMIN_PASSWORD",
    "COMET_PASSWORD",
)


class DopplerAuthError(RuntimeError):
    """Doppler CLI is missing, not logged in, or cannot read the configured project."""


def doppler_project_config() -> tuple[str, str]:
    """Return (project, config) from doppler.yaml."""
    project = "homelab"
    config = "dev"
    if not _DOPPLER_YAML.is_file():
        return project, config
    text = _DOPPLER_YAML.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("project:"):
            project = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("config:"):
            config = stripped.split(":", 1)[1].strip()
    return project, config


def doppler_cli_available() -> bool:
    try:
        completed = subprocess.run(
            ["doppler", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def assert_doppler_authenticated(project: str | None = None, config: str | None = None) -> None:
    """Fail fast unless the Doppler CLI can access the repo's project/config."""
    if not doppler_cli_available():
        raise DopplerAuthError(
            "Doppler CLI not found on PATH. Install Doppler and run `doppler login`."
        )
    if project is None or config is None:
        default_project, default_config = doppler_project_config()
        project = project or default_project
        config = config or default_config
    # names-only probe — never prints secret values
    try:
        completed = subprocess.run(
            ["doppler", "secrets", "--only-names", "-p", project, "-c", config],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
            cwd=str(_REPO_ROOT),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DopplerAuthError(f"Doppler CLI probe failed: {exc}") from exc
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise DopplerAuthError(
            f"Doppler CLI is not authenticated for {project}/{config}. "
            f"Run `doppler login` and ensure access to that project. ({err[:200]})"
        )


def _doppler_get_plain(name: str, project: str, config: str) -> Optional[str]:
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
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
            cwd=str(_REPO_ROOT),
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise DopplerAuthError(f"Doppler CLI unavailable: {exc}") from exc
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        # Missing secret name is not an auth failure — return None so caller can try aliases.
        if "Could not find requested secret" in err or "404" in err:
            return None
        raise DopplerAuthError(
            f"Doppler could not read {name} from {project}/{config}: {err[:200]}"
        )
    value = (completed.stdout or "").strip()
    return value or None


def _resolve_password_from_reader(
    reader: Callable[[str, str, str], Optional[str]],
    project: str,
    config: str,
    *,
    require: bool,
) -> Optional[str]:
    for name in _PASSWORD_SECRET_NAMES:
        value = reader(name, project, config)
        if value:
            LOG.debug("Resolved Comet password from Doppler secret %s (%s/%s)", name, project, config)
            return value
    if require:
        raise DopplerAuthError(
            f"Doppler project {project}/{config} has no GLCOMET_ADMIN_PASSWORD "
            "(or legacy COMET_ADMIN_PASSWORD / COMET_PASSWORD) secret."
        )
    return None


def resolve_comet_password(*, require: bool = True) -> Optional[str]:
    """Always fetch the Comet admin password from Doppler CLI. Never reads process env.

    Canonical Doppler secret: GLCOMET_ADMIN_PASSWORD (homelab/dev).
    COMET_ADMIN_PASSWORD and COMET_PASSWORD are accepted as legacy aliases.

    The only blocker is Doppler CLI install + authentication to doppler.yaml's
    project/config. Explicit passwords passed to kvm_connect() are separate.
    """
    project, config = doppler_project_config()
    assert_doppler_authenticated(project, config)

    return _resolve_password_from_reader(
        _doppler_get_plain,
        project,
        config,
        require=require,
    )
