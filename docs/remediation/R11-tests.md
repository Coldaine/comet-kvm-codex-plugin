# R11 — Test Suite Is Inadequate

**Severity:** 🔴 Critical
**Filed against:** PR #12 (`feat/mcp-tool-surface`)
**Design section:** All

---

## The gap

Total test count: **21 tests across 7 files**. For a system with ~50 source modules implementing a stateful BIOS runtime with graph storage, policy engine, VLM perception pipeline, MCP façade, and event-sourced tracing, this is critically low.

### What's tested (21 tests)

| Test file | Tests | What they validate |
|---|---|---|
| `test_smoke.py` | 3 | Module imports, tool registration count, `kvm_connect` signature |
| `test_policy_engine.py` | 7 | Arrow nav allowed, observe-only block, Enter on submenu/setting, F10 gate, hazard block |
| `test_state_identity.py` | 3 | Visual phash differentiation, OCR hash ordering stability, semantic hash case-insensitivity |
| `test_graph_transitions.py` | 2 | BFS shortest path on 3-node graph, cycle detection on 2-node back-edge |
| `test_vlm_contract.py` | 2 | Mock VLM stability, schema validation |
| `test_capability_index.py` | 3 | Priors auto-load, alias resolution, new setting registration |
| `test_trace_events.py` | 1 | (if it exists — not seen in tree) |

### What's **not** tested (estimate: ~200+ missing tests)

| Module | What's missing |
|---|---|
| `controller/runtime.py` | Entire runtime lifecycle: connect → observe → crawl → navigate → mutate → recover |
| `controller/observe.py` | StateObserver pipeline with mocked CometClient, OCR, VLM |
| `controller/crawl.py` | Crawl step execution, edge creation, capability registration |
| `controller/navigate.py` | Path traversal with intermediate verification, drift detection |
| `controller/mutate.py` | Full mutation flow: propose → approval → apply → verify |
| `controller/recover.py` | Emergency recovery, multi-Escape backout |
| `controller/settle.py` | Screen settle detection with phash convergence |
| `mcp/server.py` | All `bios_*` tools, MCP resource URIs, tool parameter validation |
| `state/matcher.py` | Multi-phase matching: semantic → phash → OCR fallback |
| `state/sync.py` | Sync alignment, desync detection |
| `state/graph.py` | Edge deduplication, missing-node edge handling, large-graph BFS |
| `state/store.py` | All CRUD operations, concurrent access, schema migration |
| `perception/normalize.py` | State normalization from VLM output, state kind parsing |
| `perception/ocr.py` | OCR output parsing with various image qualities |
| `comet/client.py` | Connection lifecycle, key mapping, watchdog behavior |
| `trace/ledger.py` | Event persistence, export formatting |
| **Integration** | End-to-end: CometClient mock → observe → normalize → store → graph → policy → MCP tool |

---

## Why it matters

The current tests validate data-class constructors and trivial helper logic. They do **not** validate:

- That the runtime state machine correctly transitions between states
- That the crawl planner actually explores a multi-level BIOS tree
- That the policy engine's Enter gating works on mixed submenu/setting screens
- That the mutation flow correctly navigates to a setting, changes its value, and verifies
- That the MCP tools return correct responses under various inputs
- That the system survives failure modes (connection drop, parse failure, bad OCR)

A deployment based on these tests alone would discover bugs at runtime — as the R1 bugs (resolution type, ActionPolicies default, matrix.yaml dead) already demonstrate.

---

## Remediation: integration test pattern

The user explicitly requested **integration tests, not unit tests**. Here is the recommended pattern:

```python
# tests/integration/test_runtime_lifecycle.py

class FakeCometClient:
    """A CometClient that returns canned responses without real hardware."""

    async def get_screenshot(self, ...) -> bytes:
        # Return a known test JPEG fixture
        with open("tests/fixtures/screenshots/ez-mode.jpg", "rb") as f:
            return f.read()

    async def send_combo(self, combo: str) -> dict:
        # Record what was sent for later assertion
        self.sent_combos.append(combo)
        return {"sent": combo, "modifiers": [], "key": combo}

    def is_connected(self) -> bool:
        return True

class TestRuntimeLifecycle(unittest.TestCase):
    """Tests the full runtime lifecycle with a fake CometClient."""

    def setUp(self):
        self.runtime = StatefulBiosRuntime(db_path=":memory:")
        # Inject fake client instead of real connection
        self.fake_client = FakeCometClient()
        self.runtime.client = self.fake_client
        self.runtime.state = RuntimeState.CONNECTED

    async def test_observe_crawl_cycle(self):
        """Observe a BIOS screen, crawl one step, verify edge created."""
        state = await self.runtime.observe_state()
        self.assertIsNotNone(state)
        self.assertEqual(self.runtime.state, RuntimeState.SYNCED)

        state2, edge, rec = await self.runtime.crawl_step()
        self.assertIsNotNone(edge)
        self.assertIn(rec, ("continue", "backtrack", "stop"))

    async def test_invalid_transition_raises(self):
        """Calling crawl_step from DISCONNECTED raises RuntimeError."""
        self.runtime.state = RuntimeState.DISCONNECTED
        with self.assertRaises(RuntimeError):
            await self.runtime.crawl_step()
```

### Required fixture files

Create `tests/fixtures/` with:
- `tests/fixtures/screenshots/ez-mode.jpg` — Known MSI EZ Mode screenshot (redacted/synthetic)
- `tests/fixtures/screenshots/advanced-home.jpg` — Known Advanced mode screenshot
- `tests/fixtures/screenshots/setting-list.jpg` — Known setting list screen
- `tests/fixtures/screenshots/password-prompt.jpg` — Known dangerous screen
- `tests/fixtures/vlm/ez-mode.json` — Expected VLM parse output for EZ Mode
- `tests/fixtures/vlm/advanced-home.json` — Expected VLM parse for Advanced
- `tests/fixtures/vlm/invalid.json` — Malformed VLM output for retry testing

---

## Minimum target

| Area | Current | Target |
|---|---|---|
| Total tests | 21 | 50+ |
| Integration tests | 0 | 8-10 |
| Fixture screenshots | 0 | 4-5 |
| Coverage of modules | ~20% | >70% |
