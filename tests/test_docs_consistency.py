from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCKED_LAUNCHER = "uv run --locked --python 3.13 python ./glkvm_mcp.py"
LAUNCHER_DOCS = [
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "architecture.md",
    REPO_ROOT / "docs" / "decisions.md",
    REPO_ROOT / "docs" / "kvm-core.md",
    REPO_ROOT / "docs" / "reference" / "comet-api.md",
]
TEXT_SURFACES = LAUNCHER_DOCS + [
    REPO_ROOT / "docs" / "workflows" / "live-hardware-qualification.md",
    REPO_ROOT / "docs" / "plans" / "02-mcp-v2-migration-evaluation.md",
    REPO_ROOT / "scripts" / "comet_smoke_test.py",
]


def _requirement_name(requirement: str) -> str:
    return re.split(r"\[|<|>|=|!|~|;", requirement, maxsplit=1)[0].strip().lower()


def _pep_723_dependencies() -> list[str]:
    text = (REPO_ROOT / "glkvm_mcp.py").read_text(encoding="utf-8")
    match = re.search(r"# dependencies = \[\n(?P<body>.*?)# \]", text, flags=re.DOTALL)
    assert match is not None
    dependencies = []
    for raw_line in match.group("body").splitlines():
        line = raw_line.strip()
        if line.startswith("#     "):
            dependencies.append(line.removeprefix("#     ").strip().strip('",'))
    return dependencies


def test_current_docs_use_lockfile_backed_launcher_not_script_resolver():
    stale_launcher_patterns = [
        "intended to run from `glkvm_mcp.py` with `uv run --script`",
        "launched via `uv run --script",
        "uses `doppler run -p homelab -c dev -- uv run --script",
    ]
    for path in LAUNCHER_DOCS:
        text = path.read_text(encoding="utf-8")
        assert LOCKED_LAUNCHER in text
        for stale_pattern in stale_launcher_patterns:
            assert stale_pattern not in text


def test_script_metadata_matches_project_runtime_dependencies_by_name():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_names = {_requirement_name(dep) for dep in pyproject["project"]["dependencies"]}
    script_names = {_requirement_name(dep) for dep in _pep_723_dependencies()}

    assert script_names == project_names


def test_text_surfaces_use_canonical_comet_secret_name():
    stale_secret_patterns = [
        "Doppler `COMET_PASSWORD`",
        "fetches `COMET_PASSWORD` from Doppler CLI",
        "fetched from Doppler CLI (`COMET_PASSWORD`)",
        "COMET_PASSWORD from Doppler CLI",
        "injected into the MCP process as `COMET_PASSWORD`",
        "injected into MCP process as `COMET_PASSWORD`",
    ]
    for path in TEXT_SURFACES:
        text = path.read_text(encoding="utf-8")
        assert "GLCOMET_ADMIN_PASSWORD" in text
        for stale_pattern in stale_secret_patterns:
            assert stale_pattern not in text
