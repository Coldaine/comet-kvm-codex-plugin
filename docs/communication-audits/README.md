# Communication Audit: BIOS Sidecar Discovery

> **WARNING — STALE SNAPSHOT (2026-07-07).** This audit predates the BIOS sidecar implementation. Rows marked **"Missing"** (VLM client, cartographer, state engine, policy engine, trace ledger) are **out of date** — those modules now exist under `src/bios_sidecar/`. **Do not use this folder for current-state decisions.**

> **WARNING — STALE `file:line` CITATIONS.** All `file:line` citations in `01-04` are stale after the `kvm_core` / `bios_sidecar` refactor. The codebase was split from a single-file `glkvm_mcp.py` into `src/kvm_core/` + `src/bios_sidecar/` (for example, claims like `glkvm_mcp.py:283-904` no longer apply — that file is now a short composition entrypoint). **Do not trust any line number in these audit files.**

> **Date:** 2026-07-07
> **Scope:** Repo-grounded audit of the Comet KVM BIOS/UEFI sidecar skill/tooling bundle.
> **Method:** Evidence-only answers from current repository files. Proposed or missing items are labeled as such.

> **Status:** Historical and superseded for product framing. For current state use [`docs/architecture.md`](../architecture.md), [`docs/kvm-core.md`](../kvm-core.md), and [`docs/decisions.md`](../decisions.md). These audits supersede any policy/approval or VLM-as-peer-agent framing from the original audit pass.

## Documents

- [`01-executive-summary.md`](01-executive-summary.md) — short answer, current-state inventory, missing pieces, recommended next PR, and open experiments.
- [`02-current-implementation-inventory.md`](02-current-implementation-inventory.md) — authoritative docs, skill boundaries, MCP/API implementation, runtime scripts, tests, and fixtures.
- [`03-gap-analysis-and-next-pr.md`](03-gap-analysis-and-next-pr.md) — gap table and the smallest safe implementation/documentation PR.
- [`04-question-by-question-answers.md`](04-question-by-question-answers.md) — direct answers to all 45 discovery questions.

## Audit Rules Used

- Do not invent files.
- Distinguish existing architecture, intended architecture, proposed architecture, missing implementation, and unknowns.
- Include file path and line references for material claims.
- Prefer exact implementation evidence over broad architecture summaries.
- Treat `docs/NORTH_STAR.md` as highest authority, then `docs/decisions.md`, then `docs/architecture.md`, per `docs/NORTH_STAR.md:24-34`.
