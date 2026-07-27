# MCP Session Lifecycle Hardening Design

## Problem

Agents repeatedly treat Comet tools as independent requests. They call device
tools before `kvm_connect`, reconnect an already-connected target, disconnect
between investigative reads, or interpret a transient snapshot HTTP 503 as an
authentication or OCR failure.

The MCP already owns an in-process HTTP/WebSocket session, but its contracts do
not fully enforce that lifecycle. In particular, reconnecting the same target
tears down the `stream=true` WebSocket, `kvm_connect` does not report whether the
snapshot path is ready, and screenshot/OCR tools expose a raw transient 503.

## Goals

- Make a repeated same-target `kvm_connect` call idempotent without restarting
  the streamer.
- Give the streamer a bounded opportunity to become capture-ready after a new
  connection.
- Absorb short-lived snapshot 503s inside the MCP with bounded retries.
- Report connection and capture state in terms an agent can act on.
- Put the session lifecycle in the general Comet operations skill and core
  architecture documentation.
- Preserve existing tool names, arguments, multi-target behavior, credential
  handling, and safety annotations.

## Non-goals

- Do not auto-connect to an inferred host. The portable and multi-target server
  cannot safely assume which physical KVM an agent intends to operate.
- Do not keep an OCR or screenshot polling loop running in the background.
- Do not turn capture failure into evidence that HID, ATX, or media control is
  safe or working.
- Do not change hardware state, add an HTTP service, or add dependencies.

## Design

### 1. Idempotent session reuse

`KVMRuntime.connect` will normalize the requested host and inspect the existing
entry for the requested target. When that entry is connected and its host and
username match, the runtime will reuse it rather than disconnecting and creating
a new `CometClient`. A changed host or username will retain today's explicit
replace behavior.

The return path will distinguish `reused: true` from a newly established
session. Reuse must not perform a second login, open a second WebSocket, rerun
capability discovery, or tear down the streamer.

### 2. Bounded capture readiness

After a new `stream=true` WebSocket connection is established, the client will
probe the snapshot route through a shared capture helper. HTTP 503 means the
streamer is not ready yet and is retryable. The helper will retry with short,
bounded backoff until a small deadline expires. Other HTTP failures remain
immediate errors.

Capture readiness is not a prerequisite for an authenticated KVM session: a
powered-off target or absent HDMI signal may legitimately lack a frame. Thus
`kvm_connect` will still return `connected: true`, accompanied by a `capture`
object describing `ready`, attempts, and a safe error category. It will not
return raw response bodies or credentials.

All screenshot-backed tools will use the same helper. A transient 503 that
recovers is invisible to callers. Exhaustion raises an actionable error stating
that the Comet session remains connected and that the failure is confined to
the capture path.

### 3. Observable runtime state

The client will retain only small diagnostic fields: latest capture readiness,
last successful capture timestamp, last failure category, and retry count. It
will not retain image bytes or OCR text beyond existing screenshot-cache rules.

`kvm_connect` and `kvm_status` will expose this state. The disconnected status
and `_require_client` error will instruct callers to connect once and keep the
session open across related operations. They will not imply that agents should
reconnect after a capture-only failure.

### 4. Agent guidance

The general Comet operations skill will define this sequence:

1. Check `kvm_status` when connection state is unknown.
2. Call `kvm_connect` once for the intended target.
3. Perform the bounded observation or operation series while that session stays
   open.
4. Treat exhausted snapshot retries as capture-path unavailability; inspect
   `kvm_status` or `comet_streamer_state` without reconnecting.
5. Call `kvm_disconnect` once when no continuing observation is needed.

The core architecture and API reference will document session reuse, streamer
warm-up, and retry semantics. Tool docstrings will carry the minimum actionable
contract because clients may show schemas without loading repository docs or
skills.

## Error handling

- Retry only HTTP 503 from `/api/streamer/snapshot`.
- Use a deadline and capped delay; never retry indefinitely.
- Stop retrying if the WebSocket/session closes.
- Preserve the original status for non-503 HTTP failures.
- Keep the authenticated session registered when capture readiness expires.
- Do not classify missing host Tesseract as a capture failure; OCR availability
  remains independently reported by `kvm_ocr_status`.

## Verification

Offline tests will cover:

- repeated same-target/same-host connect reuses one client and one WebSocket;
- changed host or username replaces the session;
- snapshot 503 followed by JPEG succeeds within the retry bound;
- permanent snapshot 503 produces the new capture-only error;
- connect remains successful when initial capture readiness expires;
- status reports capture diagnostics without image or OCR content;
- disconnected errors provide the intended lifecycle instruction;
- tool schemas and existing multi-target contracts remain compatible.

Existing stdio/list-tools, protocol, OCR, packaging, and documentation tests
must remain green. A live verification, when explicitly enabled, will be
read-only: connect, capture/OCR, repeated same-target connect, capture again,
and one final disconnect. It will not send HID, ATX, WOL, recorder, or media
actions.

## Compatibility and rollout

This is backward compatible at the MCP surface: existing clients may continue
calling `kvm_connect` and reading existing response fields. New response fields
are additive. Explicit disconnect retains its current meaning. No persistent
credentials or cross-process sessions are introduced; state remains scoped to
the running MCP server process.
