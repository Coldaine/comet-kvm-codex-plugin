# Raw HTTP recovery and known agent failure modes

Prefer the `comet-kvm` MCP when it is available — it owns authentication, wire
contracts, retries, streaming, and response normalization. Read this when the
MCP is unavailable, or when an agent is about to guess login URLs / drive the
web UI and needs the facts that a real recovery run already proved.

The Comet is a **portable** console appliance (LAN `192.168.0.126` in this
estate). It is not dedicated to one host; whichever machine it is currently
cabled to is the console target.

## Failure mode 1 — browser path blocked by the self-signed cert

Navigating to `https://192.168.0.126` lands on Chrome's certificate interstitial.
Browser automation **cannot attach** to that interstitial (`Cannot attach to
this target`; `screenshot` and `read_page` fail with
`Frame … showing error page`). The usual `thisisunsafe` bypass needs the page
focused and typeable, which cannot happen when attach fails.

So "just use the web UI through the browser" is not reliable for an agent.
Default to the API over `curl -k`, or use this MCP (TLS verification is already
disabled for the Comet). If a human browser session is required, pre-trust the
Comet certificate in that profile first.

## Failure mode 2 — login is not a guessed `/api/login`

The playbook-level mistake is saying "authenticate" without the route. Probing
showed:

| Path | Result |
|---|---|
| `/api/login`, `/api/auth`, `/api/session`, `/api/user/login`, `/api/v1/login`, `/rpc`, `/cgi-bin/api`, `/api/system` | **404** |
| `/api/hid`, `/api/streamer`, `/api/info` | **401** (real protected endpoints; reachable, not logged in) |

The real handshake (PiKVM-fork form POST — not a nonce/challenge-hash):

```
POST /api/auth/login
Form body: user=admin&passwd=<password>&expire=0
→ result.token + auth_token cookie
```

Subsequent HTTP: `Token: <token>` header (preferred) or `auth_token` cookie.  
WebSocket `/api/ws`: `Cookie: auth_token=<token>` plus `Token` header (not a
query-string token).  
Logout: `POST /api/auth/logout`. Check: `GET /api/auth/check`.

Password from Doppler `GLCOMET_ADMIN_PASSWORD`. Retain the token only in
process memory.

Example (password already in the environment of the process, not pasted into
shell history casually):

```sh
curl -k -i -c comet.cookie -X POST "https://192.168.0.126/api/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "user=admin" --data-urlencode "passwd=$PASSWORD" --data-urlencode "expire=0"
```

## Stream quirk — `stream=true` before snapshots

`/api/streamer` needs an authenticated WebSocket with `stream=true` or video
does not stay up:

- `WSS /api/ws?stream=true` keeps the HDMI streamer alive so
  `GET /api/streamer/snapshot` returns JPEG.
- `stream=false` is HID-only: `result.streamer` stays null → snapshot **503**.

This MCP client opens the control socket with `stream=true` (see
`src/kvm_core/comet/client.py`). Do not assume `stream=false` activates video.

## Minimal raw sequence (MCP unavailable)

1. `POST /api/auth/login` → capture token + cookie.
2. Open `WSS /api/ws?stream=true` (cookie + `Token` header); wait for streamer
   + HDMI.
3. `GET /api/streamer/snapshot` → confirm a current frame before input.
4. `GET /api/hid` → require target-side connection and an online keyboard.
5. One bounded input, then capture the result. For credentials: username first,
   verify the password prompt, then inject the secret without printing it.
6. `POST /api/auth/logout` when finished. Release held HID keys after any
   interrupted sequence.

Stop when there is no current frame, keyboard HID remains offline, the visible
prompt is ambiguous, or input produces no visible result.

ATX power/click routes and the full endpoint inventory live in
[comet-api.md](../../../docs/reference/comet-api.md) — use them only when that
action is actually required (ATX add-on board must be present).

## Source

Auth contract: pinned
[`kvmd/apps/kvmd/api/auth.py`](https://github.com/gl-inet/glkvm/blob/9bd8ad11ba03d220401b0b6a4208bbfd84ed6107/kvmd/apps/kvmd/api/auth.py);
client: `src/kvm_core/comet/client.py`. Endpoint map:
[comet-api.md](../../../docs/reference/comet-api.md).
