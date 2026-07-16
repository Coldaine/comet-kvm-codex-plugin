# GLKVM API corpus

This directory is the reproducible, source-derived inventory for the native
GLKVM HTTP and WebSocket surface. It is evidence for documentation and contract
tests, not an OpenAPI specification and not proof that optional hardware is
present on a connected appliance.

## Artifacts

| File | Role |
|---|---|
| [`sources.json`](sources.json) | Immutable upstream source identities and licensing notes |
| [`http-endpoints.csv`](http-endpoints.csv) | 200 HTTP method/path registrations, including handlers in `api/*.py` and `server.py` |
| [`websocket-events.csv`](websocket-events.csv) | 12 inbound WebSocket event registrations, including binary opcodes |
| [`project-endpoint-coverage.csv`](project-endpoint-coverage.csv) | Native endpoints used by this repo's production client, mapped to methods, tools, tests, and live status |

The complete inventories are generated from
[`gl-inet/glkvm@9bd8ad11`](https://github.com/gl-inet/glkvm/tree/9bd8ad11ba03d220401b0b6a4208bbfd84ed6107)
by `scripts/generate_glkvm_api_inventory.py`. GLKVM source is linked under its
GPL-3.0-or-later license; it is not vendored here.

Regenerate from a checkout whose `HEAD` is the pinned commit:

```powershell
python scripts/generate_glkvm_api_inventory.py `
  --source-root C:\path\to\glkvm `
  --commit 9bd8ad11ba03d220401b0b6a4208bbfd84ed6107 `
  --output-dir docs/reference/glkvm-api
```

## Status model

The generated inventories establish that a handler is present in the pinned
source. The project coverage record deliberately keeps separate fields for:

- `handler_present`: a source handler was extracted;
- `registration`: whether server registration is unconditional or conditional;
- `discovered`: durable evidence that the route was observed on the live unit;
- `exercised`: the degree to which the route was actually called on live hardware;
- `hardware_required`: the physical or optional subsystem needed for a useful effect;
- contract-test and live-qualification status.

Handler presence must not be promoted to physical capability or live
qualification. The connected unit remains authoritative for its model,
firmware, wiring, and enabled subsystems.

## OCR surfaces

Keep these three surfaces distinct:

1. `/api/streamer/ocr` and snapshot `ocr=true` are inherited server-OCR handlers.
2. GL.iNet firmware 1.9 Text Recognition runs Tesseract.js/WASM in the controlling browser.
3. This MCP's `kvm_ocr_*` tools run host Tesseract in the MCP process.

The product UI's browser worker is not a native device OCR API and is not
available intrinsically to this MCP.
