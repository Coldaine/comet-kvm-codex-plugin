# MSI Z690 BIOS Workflow

Read this file only for an explicitly identified MSI Z690-family board. Confirm
the exact motherboard, CPU, firmware revision, cooling configuration, current
values, and user-requested target before changing anything. Do not infer that a
power, current, voltage, Lite Load, LLC, or CEP value is universally safe.

## Establish the baseline

Record the visible current value of each setting relevant to the requested
experiment, which may include:

- `CPU Cooler Tuning`
- `PL1`
- `PL2`
- `ICCMAX`
- `CPU Lite Load Control`
- `CPU Lite Load` mode
- LLC mode
- CEP state

Use values supplied or explicitly approved for the exact hardware. When
isolating Lite Load behavior, hold unrelated ratios, LLC, voltage offsets,
power limits, and CEP state constant unless changing one of them is the stated
experiment.

Change one variable, save only after verifying the staged value, boot the
intended workload environment, and compare against the recorded baseline before
planning another change.

Stop immediately on:

- WHEA errors,
- crash or reboot,
- failed workload,
- performance collapse,
- effective clocks far below reported clocks,
- uncontrolled thermals.

Return to the last known stable firmware value through a separately observed
and verified BIOS run. Do not continue a sweep merely because the machine
reached the operating system.
