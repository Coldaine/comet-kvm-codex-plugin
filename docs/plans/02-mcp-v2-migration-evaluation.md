# Plan 02: MCP v2 (MCPServer) Migration Evaluation

> **Status:** Evaluation / not scheduled
> **Tracking:** [issue #24](https://github.com/Coldaine/comet-kvm-codex-plugin/issues/24)

## Context

The project pins `mcp[cli]>=1.28,<2` and uses `FastMCP` from the 1.x Python SDK (see `docs/decisions.md` D-K8). MCP v2 renames `FastMCP` to `MCPServer` with breaking API changes, but adds protocol features that map directly to this repo's open problems.

This plan evaluates whether and when to migrate — not an implementation schedule.

## Features that matter for this repo

| v2 feature | Problem it solves here |
|---|---|
| **Elicitation (URL mode)** | Collect `COMET_PASSWORD` out-of-band instead of hardcoding Doppler in `.mcp.json` for plugin distribution |
| **Progress notifications** (`ctx.report_progress`) | Long `bios_crawl_region`, observe, and VLM tool calls give clients real progress instead of silent multi-minute waits |
| **Resource subscriptions** (`notify_resource_updated`) | Agents subscribe to `bios://state/current`, `bios://graph/current`, `bios://capabilities/current` instead of polling `bios_observe_state` |
| **Structured `MCPError` in tools** | Policy blocks, crawl failures, and sync drift surfaced as typed errors |

## Migration cost (breaking changes)

- `FastMCP` → `MCPServer`; import path changes (`mcp.server.mcpserver`)
- Transport params (`host`, `port`, `json_response`) move from constructor to `run()` / `sse_app()` / `streamable_http_app()`
- Handler signature changes in some tool/resource decorators
- `ProgressContext` / `progress()` context manager removed — use `ctx.report_progress()` instead
- Codex plugin host must speak the newer spec for elicitation/subscriptions to be useful

## Go / no-go gates

Migrate only when **all** of the following are satisfied:

1. **Client support confirmed** — Codex (primary target) supports elicitation and/or progress for stdio-launched servers, or we accept streamable HTTP deployment
2. **Spike passes** — one tool migrated (e.g. `bios_crawl_region` with progress) on a test client without regressing stdio KVM tools
3. **Launcher strategy decided** — elicitation replaces or complements Doppler/env injection (see issue #24 `.mcp.json` item)
4. **Cost justified** — at least one v2 feature is blocked on 1.x, not just the rename

## Explicit non-goals

- Do not migrate for the `FastMCP` → `MCPServer` rename alone
- Do not adopt streamable HTTP unless stdio limitations block a required v2 feature
- Do not bundle v2 migration with the BIOS cartography live-hardware spike

## References

- [MCP Python SDK v2 migration guide](https://py.sdk.modelcontextprotocol.io/v2/migration)
- Current pin: `pyproject.toml`, `glkvm_mcp.py` PEP 723 metadata
- Decision: `docs/decisions.md` D-K8
