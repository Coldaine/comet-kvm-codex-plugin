# AGENTS.md

Read [`docs/NORTH_STAR.md`](docs/NORTH_STAR.md) first. Do not infer intent from code alone.

Authority on conflict: `docs/NORTH_STAR.md` > `docs/decisions.md` > `docs/architecture.md` > `docs/kvm-core.md` / `docs/reference/` > this file.

Skills under `skills/` are the runtime driver contract (how to **use** the product). They are not part of the developer authority ladder above.

Route by task:
- Intent, scope, boundaries → `docs/NORTH_STAR.md`
- Implementation decisions (incl. host-only OCR) → `docs/decisions.md`
- System shape / KVM vs BIOS → `docs/architecture.md`, `docs/kvm-core.md`
- Comet HTTP/WS/OCR API facts → `docs/reference/comet-api.md`
- Live hardware qualification → `docs/workflows/live-hardware-qualification.md`
- Driver ops (runtime) → `skills/comet-kvm-operations/`, `skills/comet-bios-triage/`
- Current work → GitHub Issues and/or `docs/plans/`

If a task crosses a goal, anti-goal, or invariant: stop and surface it. Do not invent device OCR or bypass the authority docs.
