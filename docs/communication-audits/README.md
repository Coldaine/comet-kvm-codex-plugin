# Communication Audit: BIOS Sidecar Discovery

> **Date:** 2026-07-07
> **Scope:** Repo-grounded audit of the Comet KVM BIOS/UEFI sidecar skill/tooling bundle.
> **Method:** Evidence-only answers from current repository files. Proposed or missing items are labeled as such.

> **Status:** Historical and superseded for product framing. Use these audits as evidence snapshots only; `docs/kvm-core.md` and `docs/decisions.md` supersede any policy/approval or VLM-as-peer-agent framing.

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
