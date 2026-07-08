# R6 — Adapters Never Wired

**Severity:** 🟡 High
**Filed against:** PR #12 (`feat/bios-sidecar-runtime`)
**Design section:** §15 — MSI Z690 adapter

---

## The gap

The `MsiClickBiosAdapter` class at `src/bios_sidecar/adapters/msi_click_bios.py` is fully implemented with:

- `vendor = "msi"`, `families = ["click_bios", "click_bios_5"]`
- 6 known modules: `SETTINGS`, `OC`, `M-FLASH`, `OC PROFILE`, `HARDWARE MONITOR`, `BOARD EXPLORER`
- 6 hard-block keywords
- 5 known capability mappings (`cpu_lite_load_mode`, `pl1`, `pl2`, `icccmax`, `cep`)

But **it is never imported or instantiated** by any runtime code. The design plan says the adapter's job is to:

1. **Normalize labels** — `normalize_bios_state()` in `perception/normalize.py` hardcodes MSI detection by string-matching the screen title (`"msi" in title.lower()`) instead of using the adapter
2. **Identify MSI modules** — `parse_state_kind()` doesn't use `MsiClickBiosAdapter.known_modules` to validate the top_module
3. **Classify hazards** — `HazardDetector` in `policy/hazards.py` uses its own hardcoded `BLOCKLIST_KEYWORDS` list instead of consulting the active adapter's `hard_block_keywords`
4. **Resolve capability aliases** — `CapabilityIndex` pre-loads MSI priors directly without consulting the adapter's `known_capabilities`

---

## Remediation

Wire the adapter pattern through `StatefulBiosRuntime`:

```python
# In runtime.py
from src.bios_sidecar.adapters.msi_click_bios import MsiClickBiosAdapter
from src.bios_sidecar.adapters.generic_uefi import GenericUefiAdapter

class StatefulBiosRuntime:
    def __init__(self, ...):
        self.adapter: Optional[BiosAdapter] = None

    async def detect_and_load_adapter(self, state: BiosState):
        vendor = state.bios.vendor
        family = state.bios.family
        if vendor == "msi" and "click_bios" in family:
            self.adapter = MsiClickBiosAdapter()
        else:
            self.adapter = GenericUefiAdapter()
```

Then pass `self.adapter` to:
- `normalize_bios_state()` → uses `adapter.normalize_label()`, `adapter.identify_module()`
- `HazardDetector.__init__()` → uses `adapter.hard_block_keywords` as blocklist
- `CapabilityIndex.__init__()` → uses `adapter.known_capabilities` for priors
- `PolicyEngine` → uses `adapter.known_capabilities` for risk classification

---

## Remediation checklist

- [ ] Add `detect_and_load_adapter()` to `StatefulBiosRuntime`
- [ ] Call it after the first `observe_state()` which returns vendor info
- [ ] Thread adapter through the normalizer, hazard detector, and capability index
- [ ] Rename `GenericUefiAdapter` (or create it) as the null/default adapter
- [ ] Test with mock MSI state to verify adapter is loaded correctly
