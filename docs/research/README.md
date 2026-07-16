# Research docs

Working notes that are **not** project authority. Prefer [`docs/NORTH_STAR.md`](../NORTH_STAR.md), [`docs/decisions.md`](../decisions.md), and [`docs/kvm-core.md`](../kvm-core.md) for binding design. Prefer [`docs/reference/`](../reference/) for project-facing summaries that agents and humans open first.

## Research vs reference

| Tree | Role |
|------|------|
| `docs/reference/` | Curated, project-facing facts this MCP depends on (auth, ATX/MSD contracts, hardware, verification status, MCP tool map) |
| `docs/research/` | Fuller inventories, deployment judgment, and dated audit snapshots — explicit homes so facts, vision, and critique stay separable |

## Index

| Doc | Kind | Open when you need… |
|-----|------|---------------------|
| [`glkvm-api-surface.md`](glkvm-api-surface.md) | **Upstream API facts** | Endpoint inventory, request shapes, auth methods, discovery GETs, source links into `gl-inet/glkvm` |
| [`oob-proxmox-tailscale-vision.md`](oob-proxmox-tailscale-vision.md) | **Ops vision / judgment** | Comet as OOB control plane with Proxmox + Tailscale; recovery ladder; agent permissions; phases |
| [`glkvm-client-audit-2026-07-15.md`](glkvm-client-audit-2026-07-15.md) | **Dated audit snapshot** | What a 2026-07-15 source review claimed about this repo vs firmware (no fixes in that file) |

Project-facing companions:

- [`docs/reference/comet-api.md`](../reference/comet-api.md) — summary of contracts this repo cares about + MCP tools + live verification status
- [`docs/reference/comet-hardware.md`](../reference/comet-hardware.md) — RM1 / PoE / Pro hardware facts

## Homes map (facts vs vision vs audit)

```text
Pasted writeup / research dump
├── Upstream facts ────────► glkvm-api-surface.md
│                            (+ summarized in reference/comet-api.md,
│                             hardware in reference/comet-hardware.md)
├── Ops judgment ──────────► oob-proxmox-tailscale-vision.md
└── Repo-vs-firmware audit ► glkvm-client-audit-2026-07-15.md

Already owned elsewhere (cross-link, do not fork):
  architecture.md / kvm-core.md / decisions.md / skills / NORTH_STAR
```

**Do not mix** API contracts, Tailscale/Proxmox deployment advice, and client-audit remediation into one document. Do not promote ops vision into `NORTH_STAR` until an explicit decision says so.
