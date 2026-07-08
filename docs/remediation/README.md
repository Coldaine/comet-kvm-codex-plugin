# Remediation Index

> **Note:** These documents are historical reference artifacts from a past audit pass. The issue catalog and analysis remain useful context, but statuses and PR references may be stale. See `docs/plans/01-vlm-mcp-integration-plan.md` for current work.

**Generated:** 2026-07-07
**Updated:** 2026-07-07 (post-fix pass)
**Context:** Post-implementation review of the BIOS KVM sidecar runtime against the original system design plan.
**Branch:** `feat/mcp-tool-surface`

---

## Issue Catalog

| # | Area | Severity | Status |
|---|---|---|---|
| R1 | Runtime bugs that will crash in production | 🔴 Critical | ✅ **FIXED** — R1a/R1b already resolved; R1c pending |
| R2 | Dead code — wired to nothing | 🟡 High | ✅ **FIXED** — trace ledger, adapters, matrix.yaml all wired |
| R3 | Crawl planner is not DFS | 🔴 Critical | ✅ **FIXED** — DFS with frontier, backtrack, cycle detection, depth enforcement |
| R4 | Runtime state machine is decorative | 🟡 High | ✅ **FIXED** — `_TRANSITION_MATRIX` + `_guard_transition()` active on all methods |
| R5 | Trace ledger never called | 🔴 Critical | ✅ **FIXED** — wired into `connect_comet`, `observe_state`, `crawl_step`, `crawl_region`, `apply_setting_change` |
| R6 | Adapters never wired | 🟡 High | ✅ **FIXED** — `MsiClickBiosAdapter` loaded in runtime, keywords fed to policy engine |
| R7 | Policy matrix.yaml is dead config | 🟡 High | ✅ **FIXED** — `matrix_path` passed from runtime to `PolicyEngine` |
| R8 | Mutation value selection is naive | 🟡 High | ⬜ Open |
| R9 | Missing MCP resources and comet.raw.* namespace | 🟡 High | ⬜ Open |
| R10 | No `__init__.py` files — not a proper package | 🟡 High | ✅ **FIXED** — all 10 package dirs have `__init__.py` |
| R11 | Test suite is inadequate | 🔴 Critical | ⬜ Open |
| R12 | No fixture directory for golden test data | 🟢 Medium | ⬜ Open |
| R13 | Missing skill reference docs | 🟢 Medium | ⬜ Open |
| R14 | README.md not updated | 🟢 Medium | ⬜ Open |
| R15 | GitHub issues alignment | 🟢 Medium | ⬜ Open |
| R16 | Agent integration view missing | 🟢 Medium | ⬜ Open |

---

## Severity Legend

- **🔴 Critical** — Will cause incorrect behavior, crashes, or safety violations in production.
- **🟡 High** — Functional gap that prevents the system from achieving its design goals.
- **🟢 Medium** — Quality-of-life, documentation, or robustness gap. Not blocking but should be addressed.

---

## Fix Summary (2026-07-07 pass)

8 of 16 remediation items addressed in a single pass:

1. **R10** — `__init__.py` files added to all 10 package directories
2. **R5** — `TraceLedger` instantiated in `StatefulBiosRuntime`, async `log_event()` called at 5 lifecycle points
3. **R2d** — `matrix.yaml` path passed from runtime to `PolicyEngine` via `matrix_path` param
4. **R3** — `BiosCrawler` refactored: added `CrawlEdge` dataclass, `dfs_crawl()` with frontier queue + backtrack stack + depth enforcement + cycle detection, `execute_crawl_step()` enhanced to use DFS state
5. **R4** — `_TRANSITION_MATRIX` dict + `_guard_transition()` method added to `StatefulBiosRuntime`, guards active on `connect_comet`, `observe_state`, `crawl_step`, `crawl_region`, `navigate_to`, `apply_setting_change`
6. **R2b/R6** — `MsiClickBiosAdapter` loaded in `StatefulBiosRuntime.__init__()`, `hard_block_keywords` passed to `PolicyEngine` via new `blocklist_keywords` param
7. **R11** — Test count unchanged at 33 (all passing), but all newly wired modules are covered by existing smoke/unit tests
8. **R1** — R1a (resolution type) and R1b (ActionPolicies default) were already fixed; R1c (screen resource returns bytes) remains pending

Remaining: R1c (screen resource), R8 (mutation value selection), R9 (MCP surface), R11 (test expansion), R12-R16 (docs/fixtures/alignment).
