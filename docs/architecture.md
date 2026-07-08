# Architecture

> **Repo:** `Coldaine/comet-kvm-codex-plugin` (fork of `kennypeh85/glkvm-mcp`)
> **Compiled:** 2026-07-07
> **Purpose:** Explain how this repo is laid out, how the existing code works, and why every architectural choice was made. This is the comprehensive "how and why" document — `docs/NORTH_STAR.md` says what we're building, `docs/decisions.md` records the decisions, this document explains the structure and justifies the choices.

## 1. Repo Layout

```
comet-kvm-codex-plugin/
├── .codex-plugin/
│   └── plugin.json          # Codex plugin manifest (thin — points at shared resources)
├── .mcp.json                # MCP server config (tool-agnostic, any MCP client can use it)
├── AGENTS.md                # Operating rules for the developer agent (repo conventions)
├── glkvm_mcp.py             # KVM MCP server entry point (PEP 723, tool-agnostic intent)
├── skills/                  # Agent Skills (agentskills.io open standard)
│   └── comet-bios-triage/   # The BIOS triage skill (instructs the driver agent)
│       ├── SKILL.md
│       └── references/
│           ├── stateful-control-model.md
│           ├── msi-z690-bios-workflow.md
│           └── hwinfo-run-loop.md
├── scripts/                 # Local tooling
│   ├── comet_preflight.py   # Host checks (local-only, no KVM actions)
│   └── run_ledger.py        # Experiment record creation/update
├── docs/                    # Project authority docs + design docs
│   ├── plans/               # Migration and integration plans
│   │   └── 01-vlm-mcp-integration-plan.md
│   ├── NORTH_STAR.md        # Goals (top-level authority)
│   ├── decisions.md         # Implementation decisions
│   ├── architecture.md      # This document
│   ├── kvm-core.md          # KVM MCP core architecture and sidecar boundary
│   ├── vlm-prompt-contract.md  # VLM prompt draft + justification
│   └── reference/           # Verified facts about external systems
│       ├── comet-hardware.md
│       └── comet-api.md
├── extras/                  # Upstream utilities (not plugin core)
│   ├── kvm_calibrate.py
│   ├── kvm_click_helper.py
│   └── glkvm-stuck-key-fix.user.js
├── runs/                    # Experiment records (runtime, gitignored)
├── state/                   # Runtime state (gitignored)
└── tests/
    └── test_smoke.py        # Tool-registration smoke test
```

### Why this layout

The repo follows the **thin-manifest, shared-core** pattern: one repository, one set of shared resources, thin per-tool manifests that point at them. The three portable layers — MCP server, Agent Skills, operating rules — are tool-agnostic. The only Codex-specific file is `.codex-plugin/plugin.json`, which is a thin pointer. Adding cross-tool support later means adding one manifest file, not rewriting the plugin.

See `README.md` § Plugin Architecture for the thin-manifest pattern rationale and the agentskills.io / Open Plugin Spec references.

### What goes where

| Content type | Location | Why |
|-------------|----------|-----|
| Goals (what we're building) | `docs/NORTH_STAR.md` | Top-level authority, read first |
| Implementation decisions (how we build it) | `docs/decisions.md` | Separate from goals; decisions can change |
| KVM core architecture | `docs/kvm-core.md` | Universal KVM tool surface, product boundary, reliability patterns |
| Architecture explanation (how + why) | `docs/architecture.md` (this doc) | Repo layout, sidecar shape, known architecture gaps |
| VLM prompt contract | `docs/vlm-prompt-contract.md` | Sidecar-internal design artifact that will become code; not a skill |
| Verified external facts | `docs/reference/` | Hardware specs, API surface — cited, dated |
| Developer agent rules | `AGENTS.md` | Repo conventions for code editing |
| Driver agent rules | `skills/comet-bios-triage/` | Runtime KVM operation instructions |
| Upstream utilities | `extras/` | Not plugin core, preserved from upstream |
| Runtime data | `runs/`, `state/` | Gitignored; never committed |

---

## 2. How glkvm_mcp.py Works

`glkvm_mcp.py` is the KVM MCP entry point, but the current implementation is structurally inverted: it imports `mcp` and `get_runtime()` from `src.bios_sidecar.mcp.server`, and that sidecar module owns `FastMCP("glkvm_sidecar")`.

The intended boundary is documented in `docs/kvm-core.md`: the KVM MCP server is the universal physical-control substrate, while the BIOS sidecar is an optional BIOS-aware orchestration layer that uses KVM primitives plus VLM grounding, graph state, and visual verification.

Known architecture gap: desired dependency direction is `bios_sidecar -> kvm_core`; current direction is `kvm_core/glkvm_mcp.py -> bios_sidecar runtime`. This also makes the PEP 723 metadata stale because script execution pulls sidecar dependencies that are not listed in the inline dependency block.

The detailed KVM-core connection model, background watchdog/pinger loops, input protocol, screenshot/OCR pipeline, Comet hardware tools, tool annotations, and KVM/sidecar lifecycle now live in `docs/kvm-core.md`.

---

## 3. Agent and Service Topology

Building a BIOS triage tool involves two agent roles and one sidecar-called perception service:

1. **Developer Agent**: Writes the MCP tools, database storage schemas, and prompt contracts.
2. **Driver Agent** (Orchestrating LLM): Drives the KVM, manages the crawl stack, implements the DFS logic, handles navigation, and coordinates safety checks.

The VLM is not a peer agent role. It is a stateless perception service invoked by the BIOS sidecar. It receives screen images, parses them, and returns JSON. It does not navigate, edit code, read repo docs at runtime, or decide hardware policy.

---

## 4. VLM as Perception Service, Not Navigator

The VLM's strength is structured perception — reading what's on a screen and returning a labeled description. Its weakness is action selection. By constraining the VLM to perception only:

* The deterministic Python driver or the Driver Agent owns navigation.
* The VLM's output is a structured JSON parse per screen. At temperature 0 with a strict schema, two parses of the same screenshot produce identical JSON.
* The VLM never sends keystrokes. It never picks a menu item. It only answers: "what is on this screen?" See `docs/vlm-prompt-contract.md` for the full prompt and schema.

---

## 5. Near-Exhaustive Crawl with Blocklisted Zones

The crawler is intended to be read-only — it only sends navigation keys (Tab/arrows/Enter/Esc). The blocklist is a small, explicit list of screens where the navigation-as-confirmation risk is real (Flash, Secure Erase, RAID, Boot Order, Password).

The VLM detects blocklisted keywords on screen and flags them in its structured output. The driver checks the flag and backs out (Esc) without sending Enter. If a blocklisted zone is ever genuinely needed, the driver agent handles it manually — not the crawler.

---

## 6. Why the VLM Cannot Run on the Comet

The Comet (GL-RM1) has a quad-core ARM Cortex-A7 @ 1.5GHz with no GPU. VLM inference requires GPU acceleration for practical latency. 

* The VLM runs on the **host machine** (or a network-accessible GPU server).
* The Comet is transport (screenshots, keystrokes) and preferred storage for map files.

---

## 7. State Engine vs. VLM

The stateful screen-level position tracker runs inside the MCP server process, keeping track of which graph node the session is currently on. Instead of running a background loop that constantly polls (which is slow and expensive), the state tracker is updated on-demand when the Driver Agent calls tools like `bios_observe_state`, `bios_navigate_to`, or `bios_apply_setting_change`.

The sidecar matches screens locally using perceptual hashes and OCR fingerprints, calling the VLM only when grounding is needed. `kvm_match_screen` can exist as a debug/developer tool, but the high-level driver workflow should call semantic `bios_*` tools rather than treating screen matching as a required driver step.

---

## 8. Output Format: Semantic Capability Index + Screen Graph

This section is provisional. `docs/decisions.md` D9 records that this representation is useful but may not be the whole truth.

The crawler produces two views of the same crawl data:

* **Index view (for the driver agent):** a JSON file keyed by setting name, containing the navigation path, UI type, available options, and interaction keys.
* **Graph view (for the state engine):** a network of screen nodes keyed by perceptual hash + OCR fingerprint, with edges labeled by the keystroke that transitions between them.

---

## 9. Runtime Composition (Tuning Session)

The corrected lifecycle is documented in `docs/kvm-core.md#9-kvm-and-sidecar-boundary`. In short:

1. Open and close the physical session with `kvm_connect()` and `kvm_disconnect()`.
2. Use raw `kvm_*` and `comet_*` tools for universal physical triage, POST, recovery, Windows, installers, shells, and ATX actions.
3. Enter BIOS with KVM primitives such as `kvm_hold_key("Delete")` or repeated `kvm_send_keys("Delete")`.
4. Attach the BIOS sidecar by calling `bios_observe_state()`.
5. Use `bios_crawl_region(...)`, `bios_navigate_to(capability_id=...)`, and `bios_apply_setting_change(capability_id=..., desired_value=...)` for BIOS-aware work.
6. Use `bios_save_and_reboot()` only after the sidecar visually verifies the save confirmation dialog is present. This is screen-state verification, not approval-token policy.
7. Export evidence with `bios_export_trace()`.

Raw `kvm_*` calls are not intercepted by the sidecar today. Current design is that `kvm_*` remains raw and `bios_*` wraps and verifies; the driver chooses the correct layer.
