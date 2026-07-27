# AGENTS.md

Read [`docs/NORTH_STAR.md`](docs/NORTH_STAR.md) first. Do not infer intent from code alone.

Authority on conflict: `docs/NORTH_STAR.md` > `docs/decisions.md` > `docs/architecture.md` > `docs/kvm-core.md` / `docs/reference/` > this file.

Skills under `.claude/skills/` are the runtime driver contract (how to **use** the product). They are not part of the developer authority ladder above.

Route by task:
- Intent, scope, boundaries → `docs/NORTH_STAR.md`
- Implementation decisions (incl. host-only OCR) → `docs/decisions.md`
- System shape / KVM vs BIOS → `docs/architecture.md`, `docs/kvm-core.md`
- Comet HTTP/WS/OCR API facts → `docs/reference/comet-api.md`
- Ordinary Comet operation and recovery → `.claude/skills/comet-kvm-operations/`
- Firmware-only work → `.claude/skills/comet-bios-triage/` and its focused references
- Live hardware qualification → `docs/workflows/live-hardware-qualification.md`
- Current work → GitHub Issues and/or `docs/plans/`

The universal KVM core is the product's primary path. BIOS cartography, board
tuning, and HWiNFO analysis are an optional specialist lane; do not make an
ordinary console, recovery, power, media, or appliance task depend on them.

Never commit credentials, screenshots, HWiNFO logs, or live-state files. Resolve
the Comet password from Doppler when an operation needs it; query the appliance
for present state instead of writing a live-state file into the repository.

Device tools auto-connect to the managed default Comet on first use; `kvm_connect`
is an optional override for a non-default host, explicit credentials, or a named
multi-target session — do not treat it as a required first step.

The locked launcher is `uv run --locked --python 3.13 python ./glkvm_mcp.py`; do
not use `uv run --script`, which bypasses `uv.lock`. The only Comet secret is
Doppler `GLCOMET_ADMIN_PASSWORD` (`doppler.yaml` → `homelab`/`dev`); host
(`192.168.0.126`) and username (`admin`) are non-sensitive. Live Comet
verification requires explicit `RUN_LIVE_COMET_SMOKE=1`.

If a task crosses a goal, anti-goal, or invariant: stop and surface it. Do not
invent device OCR or bypass the authority docs.
