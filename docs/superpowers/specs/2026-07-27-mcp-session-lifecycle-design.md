# MCP Session Lifecycle Hardening Design

> **Status:** Implemented.
> **Source:** `src/kvm_core/runtime.py`, `src/kvm_core/server.py`, `src/kvm_core/tools_core.py`, `src/kvm_core/comet/client.py`, `src/kvm_core/doppler_credentials.py`.

## Problem

Agents repeatedly treated Comet tools as independent requests. They called device
tools before `kvm_connect`, reconnected an already-connected target, disconnected
between investigative reads, or interpreted a transient snapshot HTTP 503 as an
authentication or OCR failure.

The MCP already owned an in-process HTTP/WebSocket session, but its contracts did
not enforce that lifecycle. Reconnecting the same target tore down the
`stream=true` WebSocket, `kvm_connect` required an explicit host on every call,
and screenshot/OCR tools exposed a raw transient 503 as a hard error.

## Goals

- Device tools connect the managed default Comet on demand; an agent should not
  need to call `kvm_connect` before an ordinary screenshot, OCR, or HID action.
- Make a repeated same-target `kvm_connect` call idempotent without restarting
  the streamer.
- Absorb short-lived snapshot 503s inside the MCP with bounded retries.
- Report connection and capture state in terms an agent can act on.
- Cache the Doppler-resolved password in-process so repeated connects don't
  re-shell to the Doppler CLI.
- Preserve existing tool names, multi-target behavior for named targets, and
  safety annotations.

## The overturned non-goal

The original version of this design carried a non-goal: *"Do not auto-connect
to an inferred host. The portable and multi-target server cannot safely assume
which physical KVM an agent intends to operate."* The shipped design deliberately
overturns that position for the **default** target only.

**Why we reversed this:**

- In practice there is one known homelab appliance (`192.168.0.126`, overridable
  via `COMET_HOST`/`COMET_USERNAME`). "Which KVM does the agent mean" was a
  theoretical multi-tenant concern this deployment doesn't have.
- Tool docstrings and server `instructions` reach every client that connects to
  this MCP, including ones that never load repository docs or skill files.
  Ritual ordering ("call `kvm_connect` first") could only be enforced by every
  client reading and obeying prose — it wasn't.
- Docs-only fixes were tried first and demonstrably failed: agents still called
  device tools cold, still reconnected healthy sessions, and still treated a
  streamer-warmup 503 as an auth failure. The fix had to live in the code path,
  not in another paragraph of guidance.

Named (non-default) targets keep the old fail-closed behavior: they are the
caller's to explicitly connect and are never auto-managed. Auto-connect is a
default-target-only concession, not a general relaxation of "know what you're
operating."

## Design

### 1. `ensure_connected` + single-flight connection lock

`KVMRuntime.ensure_connected(target=None)` is the entry point every device tool
now routes through (`tools_core._managed_client`). For the default target, it
returns the live client if one is already connected; otherwise it takes
`KVMRuntime._connection_lock`, re-checks under the lock (so concurrent cold
calls collapse into one connect rather than racing), resolves the default host
and password, and connects. For a named target, `ensure_connected` never
dials — a target that isn't already connected raises immediately, telling the
caller to `kvm_connect(host=..., target=...)` explicitly.

### 2. Lock ordering: fence outermost, then connection lock

`tools_core._operation_fence` (backed by `KVMRuntime._operation_lock`) serializes
every mutating tool and `kvm_connect`/`kvm_disconnect` against each other. The
invariant is strict: **the operation fence is always acquired before the
runtime's `_connection_lock`, and a runtime lock is never awaited while holding
`CometClient.send_lock`.** `ensure_connected` itself does not take the operation
fence — an in-flight mutating operation holding the fence cannot deadlock a
concurrent `ensure_connected` read. `CometClient.connect()` takes `send_lock`
internally only while already inside the connection-lock scope, never around
it.

### 3. Default-only management, named targets fail closed

Only `target=None`/`"default"` is auto-managed. `resolve_default_target()` in
`runtime.py` returns `(COMET_HOST or "192.168.0.126", COMET_USERNAME or
"admin")` — environment overrides win, otherwise the homelab Comet is
hardcoded. Doppler is never consulted for host or username here, only for the
password (see the divergence note below). A named target that is not already
connected raises a `RuntimeError` naming the target and telling the caller to
connect it explicitly; it is never silently dialled.

### 4. Doppler password cache

`resolve_comet_password()` in `doppler_credentials.py` caches the resolved
value in a module-level `_password_cache` for the life of the process. The
first resolution shells out to the Doppler CLI (`GLCOMET_ADMIN_PASSWORD`,
falling back to legacy `COMET_ADMIN_PASSWORD`/`COMET_PASSWORD`); every
subsequent connect — whether from `ensure_connected` or an explicit
`kvm_connect()` — reuses the cached value. `_clear_password_cache()` is a test
hook only. A `kvm_connect` call that reuses a matching live session (see next
section) skips Doppler entirely, cached or not.

### 5. `kvm_connect` as a zero-argument override

`kvm_connect(host=None, password=None, username=None, target="default",
force_reconnect=False)` requires no arguments. Omitted `host`/`username`
resolve to the managed default. Before touching Doppler or the network, it
checks whether the requested target already has a live session whose host
matches the resolved host: if so, it returns `reused: true` and does not call
Doppler, log in again, or reopen the WebSocket. `force_reconnect=True` skips
that check and replaces the session unconditionally (equivalent to the old
always-reconnect behavior). A non-matching host, or a first connect, resolves
the password (explicit arg, else Doppler) and connects normally.

### 6. `kvm_status` never connects

`kvm_status(target=None)` reads `_live_client()` — a lookup that never dials —
and reports the managed defaults (`default_host`, `default_username`,
`default_target`, `auto_connect: true`) alongside capture diagnostics,
regardless of whether a session exists. A cold call returns `connected: false`
with the same managed-default fields; it does not warm anything up.

### 7. `kvm_disconnect` is non-sticky

`kvm_disconnect(target=None)` closes one target's session, or all sessions when
`target` is omitted (legacy behavior preserved). It is not required cleanup:
the next device operation reconnects the default automatically through
`ensure_connected`. Disconnecting mid-investigation is no longer a state an
agent needs to avoid.

### 8. Snapshot 503 retry

`CometClient.get_screenshot()` retries only HTTP 503 from
`/api/streamer/snapshot`, using the fixed backoff schedule
`CAPTURE_BACKOFF_SCHEDULE = (0.1, 0.2, 0.4, 0.8)` (five attempts total: the
initial try plus four retries). Any other HTTP status is raised immediately —
503 is the only retryable outcome, because it's the one status that means "the
streamer hasn't come up yet" rather than "something is actually wrong." If the
session dies during a backoff sleep (`is_connected()` goes false), capture
aborts immediately with a session-death message instead of continuing to
retry against a session that's gone. If all retries are exhausted while the
session stayed alive, the tool raises `CometCaptureError` with a message that
explicitly states the session and credentials remain valid — this is a
streamer fault, not an authentication failure. Every outcome is recorded via
`_record_capture()` (`last_capture_ok`, `last_capture_error`, `last_capture_at`,
`capture_retry_count`) for `kvm_status` to surface.

### 9. Lifespan: no connect at startup, cleanup at shutdown

`server.py` wires a `managed_session_lifespan` into the `FastMCP` constructor.
It performs no connection work on entry — the server can start with zero
Comet credentials reachable and zero network access, and still list tools and
answer `kvm_status`. On shutdown it best-effort releases any held keys and
disconnects every live target, reading the process-global runtime directly
(not through `get_kvm_runtime()`, so shutdown never *creates* a runtime it then
has to tear down) and swallowing all exceptions.

### 10. Server `instructions`

`FastMCP("comet-kvm", instructions=INSTRUCTIONS, lifespan=...)` carries the
contract in the one channel every client sees regardless of whether it reads
repo docs: the server auto-manages the default session; `kvm_connect` is
optional; `kvm_status` never connects; `kvm_disconnect` isn't required
cleanup; a snapshot 503 is a capture-path condition, not an auth failure, and
is retried automatically; ATX `enabled: false` means no ATX header is
attached, not that the machine is off; and automatic connection covers
transport only — actions execute exactly once and are never replayed after a
failure.

## What stays true

- **Capture readiness is not a session precondition.** A powered-off target or
  an absent HDMI signal may legitimately produce no frame. `kvm_connect` still
  returns `connected: true` for an authenticated session even if the streamer
  hasn't produced a frame yet; frame absence is a capture-path fact, not proof
  the session is unhealthy.
- **503 is the only retried capture status.** Non-503 HTTP failures (401, 500,
  etc.) raise on the first attempt, exactly as before — the retry loop exists
  specifically for the streamer-warmup window, not as a general resilience
  layer.
- **Mutations are never auto-replayed.** The managed-connection machinery
  covers transport (getting a live client) only. If a mutating tool call fails
  partway through after obtaining a connected client, the MCP does not retry
  or replay that action — a failed keystroke or click is not silently resent.

## Host-resolution divergence (intentional)

`runtime.resolve_default_target()` has **no Doppler tier**: it checks
`COMET_HOST`/`COMET_USERNAME` and otherwise hardcodes the LAN default. This is
deliberately different from `scripts/comet_smoke_test.py` and
`tests/live/test_live_smoke.py`, both of which additionally fall back to a
Doppler `COMET_HOST`/`COMET_ADMIN_USERNAME` secret before the hardcoded
default. The MCP runtime path is the one every tool call goes through and is
optimized for zero extra CLI shell-outs on the common case (env override or
the hardcoded homelab IP); the smoke script and live test lane are
operator-invoked, run less often, and accept the extra Doppler round-trip in
exchange for not hardcoding a host in a script that might run against a
different Comet. Do not "fix" this by adding a Doppler host tier to
`runtime.py`, and do not remove the Doppler tier from the smoke script/live
tests to "match" the runtime — the divergence is intentional, not drift.

## Verification

The implementation was built red-specs-first: `tests/test_capture_retry.py`,
`tests/test_session_lifecycle.py`, and `tests/test_lifecycle_tools.py` encode
the managed-connection contract (`ensure_connected`, lock ordering, the 503
retry schedule, the Doppler cache, zero-argument `kvm_connect`, cold no-ops,
no-replay, BIOS sidecar cold-attach, server instructions) as tests that failed
before the corresponding feature commit and pass after it. A handful of
additional tests pin behavior that must not regress: non-503 statuses are
never retried, `kvm_disconnect()` with no target still disconnects everything,
a cold named-target call still fails closed, and VLM routing guard shape is
unchanged.

`tests/test_smoke.py` imports the server module without launching the stdio
loop and asserts the expected tools register and `kvm_connect`'s schema
requires no arguments — this doubles as a scrubbed-environment smoke: nothing
in module import touches the network or Doppler, so a clean process with no
Comet reachable still starts and lists tools. It is the standing proof that
startup never connects.

Live verification is opt-in and read-only: `tests/live/test_live_smoke.py`
skips before touching credentials or the network unless
`RUN_LIVE_COMET_SMOKE=1` is set explicitly. When enabled it connects, reads
capabilities/ATX/MSD state, captures one screenshot, checks WebSocket pong
health, and disconnects — it never sends HID, ATX, WOL, recorder, or media
mutations.
