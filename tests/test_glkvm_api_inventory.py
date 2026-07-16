from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import generate_glkvm_api_inventory as inventory


COMMIT = "a" * 40
OTHER_COMMIT = "b" * 40


def _write_source_tree(
    root: Path,
    *,
    api_modules: dict[str, str] | None = None,
    server_source: str | None = None,
) -> Path:
    api_directory = root / "kvmd" / "apps" / "kvmd" / "api"
    api_directory.mkdir(parents=True)
    modules = api_modules or {
        "alpha.py": """\
class AlphaApi:
    @exposed_http("POST", "/override", False, False, ["/bin/z", "/bin/a"])
    async def override(self, request):
        pass

    @exposed_http("GET", "/status")
    async def status(self, request):
        pass
""",
        "zeta.py": """\
class ZetaApi:
    @exposed_http(
        http_method="PATCH",
        path="/redfish/v1/Systems/0",
        allowed_exe_paths=("/usr/bin/redfish-helper",),
    )
    async def redfish_reset(self, request):
        pass

    @exposed_ws(7)
    async def binary_key(self, websocket, payload):
        pass
""",
    }
    for name, source in modules.items():
        (api_directory / name).write_text(source, encoding="utf-8")

    server_file = root / "kvmd" / "apps" / "kvmd" / "server.py"
    server_file.write_text(
        server_source
        or """\
class KvmdServer:
    @exposed_http("GET", "/ws", auth_required=False)
    async def websocket(self, request):
        pass

    @exposed_ws("ping")
    async def ping(self, websocket, event):
        pass
""",
        encoding="utf-8",
    )
    return root


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def test_inventory_extracts_defaults_overrides_paths_and_source_metadata(tmp_path: Path):
    source_root = _write_source_tree(tmp_path / "glkvm")
    http_path, websocket_path = inventory.generate_inventory(
        source_root,
        COMMIT,
        tmp_path / "output",
    )

    http_rows = _read_csv(http_path)
    by_handler = {row["handler"]: row for row in http_rows}

    status = by_handler["AlphaApi.status"]
    assert status["method"] == "GET"
    assert status["path"] == "/api/status"
    assert status["auth_required"] == "true"
    assert status["allow_usc"] == "true"
    assert json.loads(status["allowed_exe_paths"]) == []

    override = by_handler["AlphaApi.override"]
    assert override["path"] == "/api/override"
    assert override["auth_required"] == "false"
    assert override["allow_usc"] == "false"
    assert json.loads(override["allowed_exe_paths"]) == ["/bin/z", "/bin/a"]

    redfish = by_handler["ZetaApi.redfish_reset"]
    assert redfish["path"] == "/redfish/v1/Systems/0"
    assert redfish["auth_required"] == "true"
    assert redfish["allow_usc"] == "true"
    assert json.loads(redfish["allowed_exe_paths"]) == ["/usr/bin/redfish-helper"]
    assert redfish["source_file"] == "kvmd/apps/kvmd/api/zeta.py"
    assert redfish["source_line"].isdigit()
    assert redfish["source_url"] == (
        f"https://github.com/gl-inet/glkvm/blob/{COMMIT}/"
        f"{redfish['source_file']}#L{redfish['source_line']}"
    )

    server = by_handler["KvmdServer.websocket"]
    assert server["path"] == "/api/ws"
    assert server["auth_required"] == "false"
    assert server["allow_usc"] == "true"
    assert server["source_file"] == "kvmd/apps/kvmd/server.py"

    websocket_rows = _read_csv(websocket_path)
    by_event = {row["event_type"]: row for row in websocket_rows}
    assert by_event["7"]["binary"] == "true"
    assert by_event["7"]["handler"] == "ZetaApi.binary_key"
    assert by_event["ping"]["binary"] == "false"
    assert by_event["ping"]["handler"] == "KvmdServer.ping"
    assert by_event["ping"]["source_url"].startswith(
        f"https://github.com/gl-inet/glkvm/blob/{COMMIT}/"
    )


def test_inventory_output_is_sorted_and_byte_deterministic(tmp_path: Path):
    source_root = _write_source_tree(tmp_path / "glkvm")
    first_http, first_ws = inventory.generate_inventory(
        source_root,
        COMMIT,
        tmp_path / "first",
    )
    second_http, second_ws = inventory.generate_inventory(
        source_root,
        COMMIT.upper(),
        tmp_path / "second",
    )

    assert first_http.read_bytes() == second_http.read_bytes()
    assert first_ws.read_bytes() == second_ws.read_bytes()

    http_rows = _read_csv(first_http)
    http_keys = [(row["path"], row["method"], row["handler"]) for row in http_rows]
    assert http_keys == sorted(http_keys)

    websocket_rows = _read_csv(first_ws)
    websocket_keys = [
        (row["event_type"], row["binary"], row["handler"]) for row in websocket_rows
    ]
    assert websocket_keys == sorted(websocket_keys)


def test_git_head_mismatch_is_rejected_and_cli_override_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    source_root = _write_source_tree(tmp_path / "glkvm")
    monkeypatch.setattr(inventory, "_git_head", lambda _source_root: OTHER_COMMIT)

    with pytest.raises(inventory.InventoryError, match="does not match requested commit"):
        inventory.generate_inventory(source_root, COMMIT, tmp_path / "rejected")

    output_dir = tmp_path / "allowed"
    result = inventory.main(
        [
            "--source-root",
            str(source_root),
            "--commit",
            COMMIT,
            "--output-dir",
            str(output_dir),
            "--allow-head-mismatch",
        ]
    )
    assert result == 0
    assert (output_dir / inventory.HTTP_OUTPUT_NAME).is_file()
    assert (output_dir / inventory.WEBSOCKET_OUTPUT_NAME).is_file()


@pytest.mark.parametrize(
    ("decorator", "message"),
    [
        ('@exposed_http(METHOD, "/dynamic")', "method must be a literal"),
        ('@exposed_http("GET")', "requires literal method and path"),
        (
            '@exposed_http("GET", "/dynamic", allowed_exe_paths=PATHS)',
            "allowed_exe_paths must be a literal",
        ),
        ("@exposed_http", "exposed_http must be called"),
        ("@exposed_ws(EVENT)", "event_type must be a literal"),
        ('@exposed_ws("ping", "extra")', "requires exactly one literal event type"),
    ],
)
def test_malformed_or_dynamic_decorators_are_rejected(
    decorator: str,
    message: str,
    tmp_path: Path,
):
    source_root = _write_source_tree(
        tmp_path / "glkvm",
        api_modules={
            "broken.py": f"""\
class BrokenApi:
    {decorator}
    async def handler(self, request):
        pass
""",
        },
        server_source="class KvmdServer:\n    pass\n",
    )

    with pytest.raises(inventory.InventoryError, match=message):
        inventory.generate_inventory(source_root, COMMIT, tmp_path / "output")
