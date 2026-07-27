"""RED specification for the tool/server surface of the managed lifecycle.

Contract under specification:

* ``kvm_connect`` takes **no** required arguments; it is an override, not a
  precondition. A call that matches a live session returns ``reused=True``
  without touching Doppler; ``force_reconnect=True`` replaces the session.
* ``kvm_status`` reports ``default_host`` / ``default_username`` /
  ``default_target`` / ``auto_connect`` on a cold runtime and never connects.
* ``kvm_release_all`` on a cold runtime is an honest no-op.
* ``kvm_select_target("default")`` works cold; a named target cold still errors.
* Every device tool routes through ``await runtime.ensure_connected()`` — a
  failed ensure never reaches the device, and a mid-call device failure is not
  replayed.
* ``src.kvm_core.server.mcp.instructions`` teaches the managed lifecycle.
* ``bios_observe_state`` auto-connects a cold KVM runtime.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional
from unittest.mock import patch

import pytest

import src.kvm_core.doppler_credentials as doppler_credentials
import src.kvm_core.runtime as runtime_mod
import src.kvm_core.tools as kvm_tools
from src.bios_sidecar.mcp import server as bios_server
from src.kvm_core.runtime import KVMRuntime, TargetRuntime
from src.kvm_core.server import mcp
from tests.bios_test_helpers import (
    ConnectableScriptedClient,
    build_runtime,
    cleanup_runtime,
    installed_bios_runtime,
    installed_kvm_runtime,
)

DEFAULT_HOST = "192.168.0.126"
DEFAULT_USERNAME = "admin"

TOOLS_RUNTIME_PATH = "src.kvm_core.tools_core.get_kvm_runtime"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clean_client_counters():
    ConnectableScriptedClient.reset()
    yield
    ConnectableScriptedClient.reset()


class ManagedRuntimeStub:
    """Runtime double that only supports the managed (ensure_connected) path.

    ``get_client()`` raises loudly so any tool still using the legacy
    "connect first, then fetch the client" path names the missing feature.
    """

    def __init__(
        self,
        client: Optional[ConnectableScriptedClient] = None,
        *,
        connected: bool = True,
        ensure_error: Optional[BaseException] = None,
    ) -> None:
        self.client = client
        self.selected_target = "default"
        self.targets: dict[str, Any] = {}
        self.ensure_calls: list[Optional[str]] = []
        self.connect_attempts: list[dict[str, Any]] = []
        self.disconnect_calls: list[Optional[str]] = []
        self._connected = connected
        self._ensure_error = ensure_error
        if client is not None and connected:
            self.targets["default"] = TargetRuntime("default", client)

    # ── managed surface ────────────────────────────────────────────
    async def ensure_connected(self, target: Optional[str] = None):
        self.ensure_calls.append(target)
        if self._ensure_error is not None:
            raise self._ensure_error
        if self.client is None:
            raise RuntimeError("ManagedRuntimeStub has no client to hand out")
        return self.client

    def is_connected(self, target: Optional[str] = None) -> bool:
        if target is None or target == "default":
            return self._connected and self.client is not None
        return False

    # ── legacy surface: must not be used by device tools ───────────
    def get_client(self, target: Optional[str] = None):
        raise RuntimeError(
            "legacy get_client() was called — device tools must go through "
            "await KVMRuntime.ensure_connected()"
        )

    async def connect(self, host, username="admin", password="", target="default", select=True):
        self.connect_attempts.append(
            {"host": host, "username": username, "password": password, "target": target}
        )
        client = ConnectableScriptedClient(
            host=host, username=username, password=password, target_id=target
        )
        await client.connect()
        self.client = client
        self.targets[target] = TargetRuntime(target, client)
        self._connected = True
        return True

    async def disconnect(self, target: Optional[str] = None) -> None:
        self.disconnect_calls.append(target)
        self.targets.pop(target or "default", None)
        self._connected = False

    def select_target(self, target: str) -> str:
        if target != "default" and target not in self.targets:
            raise ValueError(f"Unknown target '{target}'. Connected: {sorted(self.targets)}")
        self.selected_target = target
        return target

    def list_targets(self) -> list[dict]:
        return [
            {
                "target": tid,
                "host": entry.client.base_url,
                "connected": entry.client.is_connected(),
                "selected": tid == self.selected_target,
                "capabilities": entry.client.capabilities,
            }
            for tid, entry in self.targets.items()
        ]


def tool_schema(name: str) -> dict:
    tools = run(mcp.list_tools())
    tool = next((t for t in tools if t.name == name), None)
    assert tool is not None, f"{name} tool is not registered"
    return tool.inputSchema


# ---------------------------------------------------------------------------
# kvm_connect: optional override, not a precondition
# ---------------------------------------------------------------------------


def test_kvm_connect_schema_requires_no_arguments():
    schema = tool_schema("kvm_connect")
    required = set(schema.get("required", []))
    assert required == set(), (
        "kvm_connect must be an optional override under the managed lifecycle: "
        f"no argument may be required, got {sorted(required)}"
    )
    properties = schema.get("properties", {})
    assert properties.get("password", {}).get("default") is None, (
        "kvm_connect must expose no non-null password default"
    )
    assert properties.get("username", {}).get("default") is None, (
        "kvm_connect username must default to null so the resolved default "
        "username is used; got "
        f"{properties.get('username', {}).get('default')!r}"
    )
    assert "force_reconnect" in properties, (
        "kvm_connect must expose force_reconnect to replace a live session"
    )


def test_connect_matching_live_session_returns_reused_true_without_doppler(monkeypatch):
    client = ConnectableScriptedClient(host=DEFAULT_HOST, connected=True)
    stub = ManagedRuntimeStub(client)

    def boom(*args, **kwargs):
        raise AssertionError(
            "kvm_connect must not consult Doppler when the live session already "
            "matches the requested target"
        )

    monkeypatch.setattr(doppler_credentials, "resolve_comet_password", boom)

    with patch(TOOLS_RUNTIME_PATH, return_value=stub):
        result = run(kvm_tools.kvm_connect(host=DEFAULT_HOST))

    assert result["reused"] is True, (
        "kvm_connect against a matching live session must report reused=True "
        "instead of tearing the session down"
    )
    assert result["connected"] is True
    assert stub.connect_attempts == [], (
        "a matching live session must not be reconnected"
    )


def test_force_reconnect_replaces_live_session(monkeypatch):
    client = ConnectableScriptedClient(host=DEFAULT_HOST, connected=True)
    stub = ManagedRuntimeStub(client)
    monkeypatch.setattr(
        doppler_credentials, "resolve_comet_password", lambda *a, **k: "secret"
    )

    with patch(TOOLS_RUNTIME_PATH, return_value=stub):
        try:
            result = run(kvm_tools.kvm_connect(host=DEFAULT_HOST, force_reconnect=True))
        except TypeError as exc:
            raise AssertionError(
                "kvm_connect must accept force_reconnect: bool = False to "
                f"replace a live session; got {exc}"
            ) from exc

    assert result["reused"] is False, (
        "force_reconnect=True must rebuild the session, not reuse it"
    )
    assert len(stub.connect_attempts) == 1, (
        f"force_reconnect must perform exactly one reconnect; got "
        f"{stub.connect_attempts}"
    )
    assert stub.client is not client


# ---------------------------------------------------------------------------
# kvm_status / kvm_release_all / kvm_select_target on a cold runtime
# ---------------------------------------------------------------------------


def test_status_reports_defaults_autoconnect_and_capture_state(tmp_path):
    runtime = KVMRuntime(screenshot_cache=str(tmp_path / "shots"))

    with installed_kvm_runtime(runtime):
        with patch(TOOLS_RUNTIME_PATH, return_value=runtime):
            result = run(kvm_tools.kvm_status())

    assert result["connected"] is False
    for key in ("default_host", "default_username", "default_target", "auto_connect"):
        assert key in result, (
            f"cold kvm_status must report {key!r} so the agent knows the "
            f"managed default; got keys {sorted(result)}"
        )
    assert result["default_host"] == DEFAULT_HOST
    assert result["default_username"] == DEFAULT_USERNAME
    assert result["default_target"] == "default"
    assert result["auto_connect"] is True
    assert "capture" in result, (
        "kvm_status must report capture state (503 retry/capture health); got "
        f"keys {sorted(result)}"
    )
    assert runtime.targets == {}, "kvm_status must never connect"
    assert ConnectableScriptedClient.connect_total == 0


def test_release_all_cold_is_honest_noop():
    stub = ManagedRuntimeStub(client=None, connected=False)

    with patch(TOOLS_RUNTIME_PATH, return_value=stub):
        try:
            result = run(kvm_tools.kvm_release_all())
        except Exception as exc:  # noqa: BLE001 - spec message matters
            raise AssertionError(
                "kvm_release_all on a cold runtime must succeed as a no-op "
                "without demanding (or establishing) a session; got "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    assert result["released"] == [], (
        "kvm_release_all on a cold runtime must be an honest no-op returning "
        f"an empty released list; got {result}"
    )
    assert stub.ensure_calls == [], (
        "kvm_release_all must not trigger a connect just to release nothing; "
        f"ensure_connected calls: {stub.ensure_calls}"
    )
    assert stub.connect_attempts == []


def test_select_target_default_works_cold(tmp_path):
    runtime = KVMRuntime(screenshot_cache=str(tmp_path / "shots"))

    with installed_kvm_runtime(runtime):
        with patch(TOOLS_RUNTIME_PATH, return_value=runtime):
            try:
                result = run(kvm_tools.kvm_select_target("default"))
            except Exception as exc:  # noqa: BLE001 - spec message matters
                raise AssertionError(
                    "kvm_select_target('default') must work on a cold runtime "
                    "(it only sets a preference for the managed default); got "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

    assert result["selected_target"] == "default"
    assert runtime.selected_target == "default"


def test_select_named_target_cold_fails(tmp_path):
    runtime = KVMRuntime(screenshot_cache=str(tmp_path / "shots"))

    with installed_kvm_runtime(runtime):
        with patch(TOOLS_RUNTIME_PATH, return_value=runtime):
            with pytest.raises(ValueError, match="lab"):
                run(kvm_tools.kvm_select_target("lab"))


# ---------------------------------------------------------------------------
# Device tools route through ensure_connected
# ---------------------------------------------------------------------------


def test_mutation_with_failed_ensure_never_reaches_device():
    client = ConnectableScriptedClient(host=DEFAULT_HOST, connected=True)
    stub = ManagedRuntimeStub(
        client, ensure_error=RuntimeError("ensure_connected failed: no route to host")
    )

    error: BaseException | None = None
    with patch(TOOLS_RUNTIME_PATH, return_value=stub):
        try:
            run(kvm_tools.kvm_send_keys("Escape"))
        except BaseException as exc:  # noqa: BLE001
            error = exc

    assert error is not None, (
        "kvm_send_keys did not route through KVMRuntime.ensure_connected() — a "
        "failing ensure produced no error"
    )
    assert stub.ensure_calls, (
        "kvm_send_keys must call await ensure_connected() before touching the "
        f"device; got error {type(error).__name__}: {error}"
    )
    assert client.sent_combos == [], (
        "a failed ensure_connected must never reach the device; recorded "
        f"{client.sent_combos}"
    )


def test_mutation_not_replayed_after_midcall_failure():
    attempts: list[str] = []

    class FailingClient(ConnectableScriptedClient):
        async def send_combo(self, combo: str) -> dict:
            attempts.append(combo)
            raise RuntimeError("WS disconnected mid-combo")

    client = FailingClient(host=DEFAULT_HOST, connected=True)
    stub = ManagedRuntimeStub(client)

    error: BaseException | None = None
    with patch(TOOLS_RUNTIME_PATH, return_value=stub):
        try:
            run(kvm_tools.kvm_send_keys("Enter"))
        except BaseException as exc:  # noqa: BLE001
            error = exc

    assert stub.ensure_calls, (
        "kvm_send_keys must obtain its client via await ensure_connected(); got "
        f"{type(error).__name__}: {error}"
    )
    assert error is not None
    assert attempts == ["Enter"], (
        "a mutation that fails mid-call must NOT be replayed by the managed "
        f"lifecycle; recorded attempts {attempts}"
    )


def test_atx_disabled_power_state_carries_warning():
    """A live finding: ATX ``enabled: false`` reports ``power: "off"`` on a
    running host. ``comet_power_state`` must flag that the field is not
    meaningful so agents classify machine state from the console instead."""

    class AtxDisabledClient(ConnectableScriptedClient):
        async def atx_state(self) -> dict:
            return {
                "busy": False,
                "enabled": False,
                "leds": {"hdd": False, "power": False},
                "power": "off",
            }

    client = AtxDisabledClient(host=DEFAULT_HOST, connected=True)
    stub = ManagedRuntimeStub(client)

    with patch(TOOLS_RUNTIME_PATH, return_value=stub):
        result = run(kvm_tools.comet_power_state())

    assert result["enabled"] is False
    warning = result.get("warning", "")
    assert warning and "atx" in warning.lower(), (
        "comet_power_state must carry a warning when the ATX subsystem is "
        "disabled — power:'off' with enabled:false is meaningless (observed "
        f"live on a running host); got {result}"
    )


# ---------------------------------------------------------------------------
# Server instructions
# ---------------------------------------------------------------------------


def test_server_instructions_teach_managed_lifecycle():
    instructions = getattr(mcp, "instructions", None)
    assert instructions, (
        "src.kvm_core.server.mcp must ship non-empty instructions teaching the "
        "managed connection lifecycle"
    )
    text = instructions.lower()
    assert "kvm_connect" in text, (
        "instructions must mention kvm_connect (as an optional override)"
    )
    assert ("automatic" in text) or ("managed" in text), (
        "instructions must say the connection is automatic/managed"
    )
    assert "503" in text, (
        "instructions must give 503 capture guidance"
    )
    assert "disconnect" in text, (
        "instructions must explain disconnect semantics"
    )


# ---------------------------------------------------------------------------
# BIOS sidecar attaches to a cold runtime
# ---------------------------------------------------------------------------


def test_bios_attach_autoconnects_cold_runtime(tmp_path, monkeypatch):
    runtime, _client = build_runtime(tmp_path)
    try:
        # Cold KVM core: no client, no targets. The managed lifecycle must
        # auto-connect when the sidecar attaches.
        runtime.kvm.client = None
        runtime.kvm.targets.clear()
        monkeypatch.setattr(runtime_mod, "CometClient", ConnectableScriptedClient)
        monkeypatch.setattr(
            doppler_credentials, "resolve_comet_password", lambda *a, **k: "secret",
            raising=False,
        )
        monkeypatch.setattr(
            runtime_mod, "resolve_comet_password", lambda *a, **k: "secret",
            raising=False,
        )

        with installed_kvm_runtime(runtime.kvm):
            with installed_bios_runtime(runtime):
                try:
                    result = run(bios_server.bios_observe_state())
                except RuntimeError as exc:
                    raise AssertionError(
                        "bios_observe_state on a COLD runtime must auto-connect "
                        "via KVMRuntime.ensure_connected() instead of telling "
                        f"the agent to call kvm_connect; got {exc}"
                    ) from exc

        assert isinstance(result, dict)
        assert "state_id" in result
        assert ConnectableScriptedClient.connect_total == 1, (
            "the sidecar attach must trigger exactly one managed connect; "
            f"connects={ConnectableScriptedClient.connect_total}"
        )
    finally:
        cleanup_runtime(runtime)
