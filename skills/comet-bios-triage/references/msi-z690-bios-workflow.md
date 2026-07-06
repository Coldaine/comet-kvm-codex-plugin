# MSI Z690 BIOS Workflow

Initial target settings for CPU thermal triage:

- `CPU Cooler Tuning`
- `PL1`
- `PL2`
- `ICCMAX`
- `CPU Lite Load Control`
- `CPU Lite Load` mode
- LLC mode
- CEP state

First safe run:

- `PL1 = 125 W`
- `PL2 = 253 W`
- `ICCMAX = 307 A`
- CPU ratios Auto
- LLC Auto/default
- no voltage offset

Lite Load sweep after baseline:

- Keep CPU ratios Auto.
- Keep LLC Auto/default.
- Keep CEP enabled initially.
- Test `Mode 12`, `11`, `10`, `9`, `8`, then `7`.

Stop immediately on:

- WHEA errors,
- crash or reboot,
- failed workload,
- performance collapse,
- effective clocks far below reported clocks,
- uncontrolled thermals.
