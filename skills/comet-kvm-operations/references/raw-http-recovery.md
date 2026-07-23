# Raw HTTP Recovery (MCP unavailable)

Read this file only when the `comet-kvm` MCP server is unavailable and you must
drive the Comet directly over HTTP/WebSocket to recover a network-isolated host.
When the MCP is available, use it instead — it owns authentication, wire
contracts, retries, streaming, and response normalization. Do not reproduce
these raw requests while the MCP path is healthy.

## Do not drive the browser UI

The Comet ships a self-signed certificate. Navigating a browser to its HTTPS
URL lands on Chrome's certificate interstitial, which is not
automation-attachable (`Cannot attach to this target`; `screenshot`/`read_page`
fail with `Frame … showing error page`). The `thisisunsafe` bypass needs a
focused, typeable page, which cannot exist when attach fails. Use `curl -k`
or the WebSocket API. If a browser is genuinely required, pre-trust the Comet
certificate in the profile first and cross-check its fingerprint.

## Authenticate

The Comet firmware is a PiKVM fork. The login route is `POST /api/auth/login`,
not `/api/login` — plain-REST login-path guesses (`/api/login`, `/api/auth`,
`/api/session`, `/api/user/login`, `/api/v1/login`, `/rpc`, `/cgi-bin/api`,
`/api/system`) return 404, while the protected subsystem endpoints (`/api/hid`,
`/api/streamer`, `/api/info`) return 401 pre-auth.

```sh
curl -k -i -c /tmp/comet.cookie -X POST "https://192.168.0.126/api/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "user=admin" --data-urlencode "passwd=$PASSWORD" --data-urlencode "expire=0"
```

- Success returns `result.token` and sets the `auth_token` cookie. The response
  may instead return `two_step_required` / `two_step_token` when two-step login
  is enabled.
- On subsequent HTTP requests, send the token as the `Token: <token>` header
  (preferred) or rely on the `auth_token` cookie.
- Close the session with `POST /api/auth/logout`; check state with
  `GET /api/auth/check`. The password comes from Doppler (`GLCOMET_ADMIN_PASSWORD`);
  never place it on a command line in a way that is logged — feed it to the
  process that performs the request.

## Bring up video before snapshots

Open the authenticated control WebSocket before requesting a snapshot, or the
snapshot returns HTTP 503:

- `WSS /api/ws?stream=true` keeps the HDMI streamer process alive so that
  `GET /api/streamer/snapshot` returns a JPEG. Authenticate the WebSocket with
  `Cookie: auth_token=<token>` plus the `Token: <token>` header (not a
  query-string token, which leaks into logs).
- `stream=false` is HID-only and leaves `result.streamer` null, so
  `/api/streamer/snapshot` returns 503. This is the same quirk the MCP control
  socket exhibits when it uses `stream=false`.

## Recovery sequence

1. `POST /api/auth/login` → capture `token` + `auth_token` cookie.
2. Open `WSS /api/ws?stream=true` (cookie + `Token` header) and wait for the
   streamer object plus HDMI signal.
3. `GET /api/streamer/snapshot` → confirm a current frame before any input.
4. `GET /api/hid` → require target-side connection and an online keyboard.
5. Send one bounded input, then capture the result. For credentials, send only
   the username first, verify the password prompt, then inject the secret
   without printing it.
6. If power action is needed: `POST /api/atx/power?action=on|off|off_hard|reset_hard`
   or `POST /api/atx/click?button=power|power_long|reset` (requires the ATX
   add-on board; firmware uses query parameters, not JSON bodies).
7. `POST /api/auth/logout` when finished. Release all held HID keys after any
   interrupted sequence.

Stop when there is no current frame, keyboard HID remains offline, the visible
prompt is ambiguous, or input produces no visible result.

## Source

Auth contract: pinned
[`kvmd/apps/kvmd/api/auth.py`](https://github.com/gl-inet/glkvm/blob/9bd8ad11ba03d220401b0b6a4208bbfd84ed6107/kvmd/apps/kvmd/api/auth.py);
client implementation `src/kvm_core/comet/client.py` (`CometClient.connect` /
`disconnect`). Full endpoint inventory: [comet-api.md](../../../docs/reference/comet-api.md).
