# AGENTS.md

Read [`docs/NORTH_STAR.md`](docs/NORTH_STAR.md) first. Do not infer intent from code alone.

Authority on conflict: `docs/NORTH_STAR.md` > `docs/decisions.md` > `docs/architecture.md` > `docs/kvm-core.md` / `docs/reference/` > this file.

Skills under `skills/` are the runtime driver contract (how to **use** the product). They are not part of the developer authority ladder above.

Route by task:
- Intent, scope, boundaries → `docs/NORTH_STAR.md`
- Implementation decisions (incl. host-only OCR) → `docs/decisions.md`
- System shape / KVM vs BIOS → `docs/architecture.md`, `docs/kvm-core.md`
- Comet HTTP/WS/OCR API facts → `docs/reference/comet-api.md`
- Ordinary Comet operation and recovery → `skills/comet-kvm-operations/`
- Firmware-only work → `skills/comet-bios-triage/` and its focused references
- Live hardware qualification → `docs/workflows/live-hardware-qualification.md`
- Current work → GitHub Issues and/or `docs/plans/`

The universal KVM core is the product's primary path. BIOS cartography, board
tuning, and HWiNFO analysis are an optional specialist lane; do not make an
ordinary console, recovery, power, media, or appliance task depend on them.

Never commit credentials, screenshots, HWiNFO logs, or live-state files. Resolve
the Comet password from Doppler when an operation needs it; query the appliance
for present state instead of writing a live-state file into the repository.

If a task crosses a goal, anti-goal, or invariant: stop and surface it. Do not
invent device OCR or bypass the authority docs.
