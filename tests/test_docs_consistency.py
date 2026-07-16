from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCKED_LAUNCHER = "uv run --locked --python 3.13 python ./glkvm_mcp.py"
CURRENT_DOCS = [
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "decisions.md",
    REPO_ROOT / "docs" / "kvm-core.md",
    REPO_ROOT / "docs" / "reference" / "comet-api.md",
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
        "uses `doppler run -p secrets_managment -c dev -- uv run --script",
    ]
    for path in CURRENT_DOCS:
        text = path.read_text(encoding="utf-8")
        assert LOCKED_LAUNCHER in text
        for stale_pattern in stale_launcher_patterns:
            assert stale_pattern not in text


def test_script_metadata_matches_project_runtime_dependencies_by_name():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_names = {_requirement_name(dep) for dep in pyproject["project"]["dependencies"]}
    script_names = {_requirement_name(dep) for dep in _pep_723_dependencies()}

    assert script_names == project_names
