"""RED specification for the MCP-managed Comet connection lifecycle.

Contract under specification:

* ``src.kvm_core.runtime.resolve_default_target()`` -> ``(host, username)``,
  sourced from ``COMET_HOST`` / ``COMET_USERNAME`` and otherwise hardcoded to
  ``192.168.0.126`` / ``admin``. Doppler is *never* consulted for the host.
* ``await KVMRuntime.ensure_connected(target=None)`` connects the default
  target on demand, reuses a live session, and fails closed for any named
  target it does not own.
* ``KVMRuntime._connection_lock`` collapses concurrent cold ensures into a
  single connect; ``KVMRuntime._operation_lock`` serializes disconnect/reconnect
  against in-flight operations without deadlocking an ensure.
* ``resolve_comet_password`` is cached in-process (``_clear_password_cache()``
  is the test hook), so reconnects never re-shell out to Doppler.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

import src.kvm_core.doppler_credentials as doppler_credentials
import src.kvm_core.runtime as runtime_mod
from src.kvm_core.runtime import KVMRuntime, TargetRuntime
from tests.bios_test_helpers import ConnectableScriptedClient

DEFAULT_HOST = "192.168.0.126"
DEFAULT_USERNAME = "admin"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clean_lifecycle_state(monkeypatch):
    """Fresh client counters and a cold password cache around every test."""
    ConnectableScriptedClient.reset()
    monkeypatch.delenv("COMET_HOST", raising=False)
    monkeypatch.delenv("COMET_USERNAME", raising=False)
    # The cache hook does not exist yet; test_doppler_password_resolved_once
    # asserts on it directly so the other specs report their own gaps.
    clear = getattr(doppler_credentials, "_clear_password_cache", None)
    if clear is not None:
        clear()
    yield
    ConnectableScriptedClient.reset()
    clear = getattr(doppler_credentials, "_clear_password_cache", None)
    if clear is not None:
        clear()


class CountingPassword:
    """Stub for resolve_comet_password that records how often it is consulted."""

    def __init__(self, value: str = "secret-from-doppler") -> None:
        self.value = value
        self.calls = 0

    def __call__(self, *args, **kwargs) -> str:
        self.calls += 1
        return self.value


def install_fakes(monkeypatch) -> CountingPassword:
    """Wire ensure_connected's seams: client factory + password resolver."""
    monkeypatch.setattr(runtime_mod, "CometClient", ConnectableScriptedClient)
    password = CountingPassword()
    # Patch both the source module and the runtime module binding so the
    # implementation is free to import the symbol either way.
    monkeypatch.setattr(
        doppler_credentials, "resolve_comet_password", password, raising=False
    )
    monkeypatch.setattr(
        runtime_mod, "resolve_comet_password", password, raising=False
    )
    return password


def fresh_runtime(tmp_path) -> KVMRuntime:
    return KVMRuntime(screenshot_cache=str(tmp_path / "shots"))


def require_ensure(runtime: KVMRuntime):
    ensure = getattr(runtime, "ensure_connected", None)
    assert ensure is not None, (
        "KVMRuntime.ensure_connected() is missing — the managed connection "
        "lifecycle is not implemented"
    )
    return ensure


# ---------------------------------------------------------------------------
# Default target resolution
# ---------------------------------------------------------------------------


def test_default_target_resolves_env_then_hardcoded(monkeypatch):
    resolver = getattr(runtime_mod, "resolve_default_target", None)
    assert resolver is not None, (
        "src.kvm_core.runtime.resolve_default_target() is missing — there is no "
        "module-level default (host, username) resolution"
    )

    assert resolver() == (DEFAULT_HOST, DEFAULT_USERNAME), (
        "with no environment override the default target must be the hardcoded "
        f"{DEFAULT_HOST}/{DEFAULT_USERNAME}"
    )

    monkeypatch.setenv("COMET_HOST", "10.0.0.9")
    monkeypatch.setenv("COMET_USERNAME", "operator")
    assert resolver() == ("10.0.0.9", "operator"), (
        "COMET_HOST/COMET_USERNAME must override the hardcoded default target"
    )


def test_default_host_resolution_never_calls_doppler_for_host(monkeypatch):
    resolver = getattr(runtime_mod, "resolve_default_target", None)
    assert resolver is not None, (
        "src.kvm_core.runtime.resolve_default_target() is missing — cannot "
        "prove the host tier skips Doppler"
    )

    calls: list[str] = []

    def boom(*args, **kwargs):
        calls.append("doppler")
        raise AssertionError("Doppler must not be consulted for the default host")

    monkeypatch.setattr(doppler_credentials, "resolve_comet_password", boom)
    monkeypatch.setattr(doppler_credentials, "doppler_cli_available", boom)
    monkeypatch.setattr(doppler_credentials, "assert_doppler_authenticated", boom)
    monkeypatch.setattr(doppler_credentials, "_doppler_get_plain", boom)

    assert resolver() == (DEFAULT_HOST, DEFAULT_USERNAME)
    assert calls == [], "host resolution must have no Doppler tier"


# ---------------------------------------------------------------------------
# ensure_connected — cold connect, reuse, concurrency
# ---------------------------------------------------------------------------


def test_cold_ensure_connects_once_then_reuses(tmp_path, monkeypatch):
    password = install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)
    ensure = require_ensure(runtime)

    async def scenario():
        first = await ensure()
        second = await ensure()
        return first, second

    first, second = run(scenario())

    assert first is second, "a live default session must be reused, not rebuilt"
    assert ConnectableScriptedClient.connect_total == 1, (
        "a warm default target must not reconnect; connects="
        f"{ConnectableScriptedClient.connect_total}"
    )
    assert first.host == DEFAULT_HOST
    assert first.username == DEFAULT_USERNAME
    assert runtime.is_connected("default") is True
    assert password.calls == 1, (
        "the password must be resolved once for the cold connect only"
    )


def test_default_password_resolution_runs_off_event_loop(tmp_path, monkeypatch):
    """A slow Doppler CLI call must not freeze the stdio MCP event loop."""
    monkeypatch.setattr(runtime_mod, "CometClient", ConnectableScriptedClient)
    main_thread = threading.current_thread()

    def password(*args, **kwargs):
        assert threading.current_thread() is not main_thread, (
            "Doppler password resolution ran on the asyncio event-loop thread"
        )
        return "secret-from-doppler"

    monkeypatch.setattr(runtime_mod, "resolve_comet_password", password)
    runtime = fresh_runtime(tmp_path)

    client = run(runtime.ensure_connected())

    assert client.is_connected()


def test_concurrent_cold_ensures_perform_one_connect(tmp_path, monkeypatch):
    install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)
    ensure = require_ensure(runtime)

    lock = getattr(runtime, "_connection_lock", None)
    assert isinstance(lock, asyncio.Lock), (
        "KVMRuntime._connection_lock must be an asyncio.Lock so concurrent cold "
        f"ensures collapse into one connect; got {lock!r}"
    )

    async def scenario():
        gate = asyncio.Event()
        ConnectableScriptedClient.gate = gate
        first = asyncio.create_task(ensure())
        second = asyncio.create_task(ensure())
        # Let both tasks reach the connection lock before the connect completes.
        for _ in range(5):
            await asyncio.sleep(0)
        gate.set()
        return await asyncio.wait_for(asyncio.gather(first, second), timeout=5)

    try:
        clients = run(scenario())
    finally:
        ConnectableScriptedClient.gate = None

    assert clients[0] is clients[1], "both ensures must share one client"
    assert ConnectableScriptedClient.connect_total == 1, (
        "concurrent cold ensures must perform exactly ONE connect; connects="
        f"{ConnectableScriptedClient.connect_total}"
    )


def test_ensure_during_inflight_operation_does_not_deadlock(tmp_path, monkeypatch):
    install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)
    ensure = require_ensure(runtime)

    operation_lock = getattr(runtime, "_operation_lock", None)
    assert operation_lock is not None, (
        "KVMRuntime._operation_lock is missing — disconnect/reconnect cannot be "
        "fenced against in-flight operations"
    )

    async def scenario():
        # Simulate an in-flight device operation holding the operation fence.
        async with operation_lock:
            return await asyncio.wait_for(ensure(), timeout=5)

    client = run(scenario())
    assert client is not None
    assert ConnectableScriptedClient.connect_total == 1


# ---------------------------------------------------------------------------
# ensure_connected — target scoping / fail closed
# ---------------------------------------------------------------------------


def test_ensure_manages_only_default_target(tmp_path, monkeypatch):
    install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)
    ensure = require_ensure(runtime)

    async def scenario():
        implicit = await ensure()
        explicit = await ensure("default")
        return implicit, explicit

    implicit, explicit = run(scenario())

    assert implicit is explicit, (
        "target=None and target='default' must resolve to the same managed session"
    )
    assert ConnectableScriptedClient.connect_total == 1
    assert set(runtime.targets) == {"default"}, (
        "ensure_connected must only ever auto-manage the 'default' target; "
        f"got {sorted(runtime.targets)}"
    )


def test_known_disconnected_named_target_fails_closed(tmp_path, monkeypatch):
    install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)
    ensure = require_ensure(runtime)

    lab = ConnectableScriptedClient(host="10.1.2.3", target_id="lab", connected=False)
    runtime.targets["lab"] = TargetRuntime("lab", lab)

    with pytest.raises(RuntimeError) as raised:
        run(ensure("lab"))

    message = str(raised.value)
    assert "lab" in message, (
        f"the fail-closed error must name the target; got {message!r}"
    )
    assert "connect" in message.lower(), (
        "the fail-closed error must tell the caller to connect explicitly to "
        f"that target; got {message!r}"
    )
    assert lab.connect_calls == 0, "a named target must never be auto-connected"


def test_unknown_named_target_fails_closed(tmp_path, monkeypatch):
    install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)
    ensure = require_ensure(runtime)

    with pytest.raises(RuntimeError) as raised:
        run(ensure("ghost"))

    assert "ghost" in str(raised.value)
    assert ConnectableScriptedClient.connect_total == 0, (
        "an unknown named target must fail closed without connecting anything"
    )


def test_implicit_ensure_uses_the_selected_named_target(tmp_path, monkeypatch):
    """Targetless device tools must honour an explicitly selected named target."""
    install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)

    async def scenario():
        await runtime.connect(host=DEFAULT_HOST, password="x", target="default")
        await runtime.connect(host="10.1.2.3", password="x", target="lab")
        runtime.select_target("lab")
        return await runtime.ensure_connected()

    client = run(scenario())

    assert client is runtime.targets["lab"].client
    assert client.target_id == "lab"
    assert runtime.targets["default"].client is not client


def test_selected_disconnected_named_target_never_falls_back_to_default(tmp_path, monkeypatch):
    """A selected named target must fail closed rather than redirecting HID to default."""
    install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)
    runtime.targets["lab"] = TargetRuntime(
        "lab", ConnectableScriptedClient(host="10.1.2.3", target_id="lab", connected=False)
    )
    runtime.selected_target = "lab"

    with pytest.raises(RuntimeError, match="lab"):
        run(runtime.ensure_connected())

    assert "default" not in runtime.targets
    assert ConnectableScriptedClient.connect_total == 0


# ---------------------------------------------------------------------------
# disconnect semantics
# ---------------------------------------------------------------------------


def test_disconnect_is_not_sticky_next_ensure_reconnects(tmp_path, monkeypatch):
    install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)
    ensure = require_ensure(runtime)

    async def scenario():
        first = await ensure()
        await runtime.disconnect("default")
        second = await ensure()
        return first, second

    first, second = run(scenario())

    assert first.disconnect_calls == 1
    assert ConnectableScriptedClient.connect_total == 2, (
        "kvm_disconnect must not be sticky — the next ensure_connected has to "
        f"reconnect; connects={ConnectableScriptedClient.connect_total}"
    )
    assert second.is_connected() is True
    assert runtime.is_connected("default") is True


def test_disconnect_no_arg_disconnects_all_targets(tmp_path, monkeypatch):
    install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)

    async def scenario():
        await runtime.connect(host=DEFAULT_HOST, password="x", target="default")
        await runtime.connect(host="10.1.2.3", password="x", target="lab")
        assert runtime.is_connected("default") and runtime.is_connected("lab")
        await runtime.disconnect()
        return list(runtime.targets)

    remaining = run(scenario())

    assert remaining == [], (
        f"kvm_disconnect with no target must drop every target; left {remaining}"
    )
    assert all(not c.is_connected() for c in ConnectableScriptedClient.instances)
    assert runtime.client is None


def test_disconnect_no_arg_releases_direct_compatibility_client(tmp_path):
    """Legacy sidecar-installed clients must not survive disconnect-all."""
    runtime = fresh_runtime(tmp_path)
    direct = ConnectableScriptedClient(host=DEFAULT_HOST, connected=True)
    runtime.client = direct

    run(runtime.disconnect())

    assert direct.disconnect_calls == 1
    assert runtime.client is None


def test_disconnect_no_arg_releases_direct_client_alongside_targets(tmp_path, monkeypatch):
    """The direct client is captured before target disconnects rebind self.client."""
    install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)
    direct = ConnectableScriptedClient(host="10.9.9.9", connected=True)

    async def scenario():
        await runtime.connect(host=DEFAULT_HOST, password="x", target="default")
        runtime.client = direct
        await runtime.disconnect()

    run(scenario())

    assert direct.disconnect_calls == 1
    assert runtime.client is None


def test_shutdown_releases_direct_compatibility_client(tmp_path, monkeypatch):
    """Shutdown must release keys held by a legacy sidecar-installed client."""
    from src.kvm_core.server import _shutdown_cleanup

    runtime = fresh_runtime(tmp_path)
    direct = ConnectableScriptedClient(host=DEFAULT_HOST, connected=True)
    runtime.client = direct
    monkeypatch.setattr(runtime_mod, "_runtime", runtime)

    run(_shutdown_cleanup())

    assert direct.release_calls == 1
    assert direct.disconnect_calls == 1


# ---------------------------------------------------------------------------
# explicit connect — atomic idempotence
# ---------------------------------------------------------------------------


def test_connect_reuses_matching_host_and_username(tmp_path, monkeypatch):
    install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)

    async def scenario():
        first = await runtime.connect(
            host=DEFAULT_HOST, username="operator", password="x", target="lab"
        )
        second = await runtime.connect(
            host=f"https://{DEFAULT_HOST}/", username="operator", password="x", target="lab"
        )
        return first, second

    first, second = run(scenario())

    assert first == (True, False)
    assert second == (True, True)
    assert ConnectableScriptedClient.connect_total == 1


def test_connect_replaces_same_host_when_username_changes(tmp_path, monkeypatch):
    install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)

    async def scenario():
        await runtime.connect(host=DEFAULT_HOST, username="admin", password="x", target="lab")
        original = runtime.targets["lab"].client
        result = await runtime.connect(
            host=DEFAULT_HOST, username="operator", password="x", target="lab"
        )
        return original, result, runtime.targets["lab"].client

    original, result, replacement = run(scenario())

    assert result == (True, False)
    assert replacement is not original
    assert original.disconnect_calls == 1
    assert replacement.username == "operator"


def test_concurrent_matching_connects_share_one_session(tmp_path, monkeypatch):
    install_fakes(monkeypatch)
    runtime = fresh_runtime(tmp_path)

    async def scenario():
        gate = asyncio.Event()
        ConnectableScriptedClient.gate = gate
        first = asyncio.create_task(
            runtime.connect(host=DEFAULT_HOST, username="admin", password="x", target="lab")
        )
        second = asyncio.create_task(
            runtime.connect(host=DEFAULT_HOST, username="admin", password="x", target="lab")
        )
        for _ in range(5):
            await asyncio.sleep(0)
        gate.set()
        return await asyncio.wait_for(asyncio.gather(first, second), timeout=5)

    try:
        results = run(scenario())
    finally:
        ConnectableScriptedClient.gate = None

    assert results == [(True, False), (True, True)]
    assert ConnectableScriptedClient.connect_total == 1


# ---------------------------------------------------------------------------
# Doppler password caching
# ---------------------------------------------------------------------------


def test_doppler_password_resolved_once_across_reconnects(tmp_path, monkeypatch):
    clear = getattr(doppler_credentials, "_clear_password_cache", None)
    assert clear is not None, (
        "src.kvm_core.doppler_credentials._clear_password_cache() is missing — "
        "there is no in-process password cache (or no test hook for it)"
    )
    clear()

    # Stub the Doppler CLI layer, NOT resolve_comet_password itself — the cache
    # under specification lives inside resolve_comet_password.
    monkeypatch.setattr(runtime_mod, "CometClient", ConnectableScriptedClient)
    monkeypatch.setattr(
        doppler_credentials, "assert_doppler_authenticated", lambda *a, **k: None
    )
    reads: list[str] = []

    def fake_secret_read(name, project, config):
        reads.append(name)
        return "secret-from-doppler"

    monkeypatch.setattr(doppler_credentials, "_doppler_get_plain", fake_secret_read)

    runtime = fresh_runtime(tmp_path)
    ensure = require_ensure(runtime)

    async def scenario():
        await ensure()
        await runtime.disconnect("default")
        await ensure()

    run(scenario())

    assert ConnectableScriptedClient.connect_total == 2
    assert len(reads) == 1, (
        "resolve_comet_password must be served from the in-process cache on "
        f"reconnect; the Doppler CLI was read {len(reads)} times ({reads})"
    )
