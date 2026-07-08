# R1 — Runtime Bugs That Will Crash in Production

**Severity:** 🔴 Critical
**Status:** R1a ✅ FIXED | R1b ✅ FIXED | R1c ⬜ Open | R1d ✅ FIXED

---

## R1a — `resolution` type mismatch in observe pipeline ✅

**Fixed.** `controller/observe.py` already passes `resolution=[ocr_res.get("width", 1920), ocr_res.get("height", 1080)]` as a list.

---

## R1b — `ActionPolicies` default factory uses `list` not `ActionPolicies` ✅

**Fixed.** `domain/models.py` already uses `field(default_factory=ActionPolicies)`.

---

## R1c — `bios://screen/current` MCP resource returns `bytes` instead of `str` ⬜

**File:** `src/bios_sidecar/mcp/server.py`, lines 37–45

```python
@mcp.resource("bios://screen/current")
def get_current_screen() -> bytes:
```

**Problem:** MCP resources are text-oriented by convention in the FastMCP framework. Returning `bytes` from a resource handler is not a supported pattern for most MCP clients. Binary content should be served via a tool, not a resource.

**Remediation:** Replace the resource with a tool, e.g. `bios_get_current_screenshot() -> Image`. Or convert the resource to return a base64 data URI string.

---

## R1d — Policy engine had dangling syntax error

**File:** `src/bios_sidecar/policy/engine.py`, line 238 (fixed)

```python
 mix = evaluate = None
```

**Problem:** This dangling line broke module import. The test suite could not load any module that transitively imported `policy/engine.py`. This was caught and fixed during review but indicates no linter or CI import check was run before the commit.

**Remediation:** Add a compile-all step to CI:
```yaml
- run: python -m compileall glkvm_mcp.py src/
```

---

## Order of remediation

1. ✅ R1a (resolution type) — was already fixed in `controller/observe.py`
2. ✅ R1b (ActionPolicies default) — was already fixed in `domain/models.py`
3. ⬜ R1c (screen resource to tool) — moderate refactor in `mcp/server.py`
4. ⬜ R1d compile check to CI — 1-line addition to CI workflow
