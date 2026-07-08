# R7 — Policy Matrix YAML Is Dead Config

**Severity:** 🟡 High
**Filed against:** PR #12 (`feat/bios-sidecar-runtime`)
**Design section:** §9 — Safety policy design

---

## The gap

`policy/matrix.yaml` contains the full action matrix for all 4 policy profiles. But `PolicyEngine.__init__()` only loads it if `matrix_path` is explicitly passed. `StatefulBiosRuntime.__init__()` never passes one, so the hardcoded Python dict in `_load_default_matrix()` is always used.

This means:
- Changing policy requires editing `engine.py` — a code change — instead of editing `matrix.yaml`
- The YAML file is misleading — anyone reading it would think it governs behavior
- The policy config and the implementation are in two different places with no synchronization

---

## Remediation

Wire the YAML loading in `StatefulBiosRuntime.__init__()`:

```python
import os

class StatefulBiosRuntime:
    def __init__(self, ...):
        # ...
        matrix_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "policy", "matrix.yaml"
        )
        self.policy_engine = PolicyEngine(
            approval_tracker=self.approval_tracker,
            matrix_path=matrix_path
        )
```

Also add `pyyaml` to `pyproject.toml` dependencies since `PolicyEngine._load_default_matrix()` silently falls back to the hardcoded dict if `import yaml` fails.

---

## Remediation checklist

- [ ] Add `pyyaml` to `pyproject.toml` dependencies
- [ ] Pass `matrix_path` to `PolicyEngine` constructor in `runtime.py`
- [ ] Remove the hardcoded `_load_default_matrix()` fallback and let it fail if YAML is missing
- [ ] Verify that editing `matrix.yaml` changes policy behavior without code changes
