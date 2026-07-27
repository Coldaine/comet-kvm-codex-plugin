# BIOS Handoff

Read this file when the user explicitly wants firmware semantics rather than
generic KVM transport.

Use `comet-bios-triage` for inspecting or changing a BIOS setting, mapping
firmware menus, navigating to a stored firmware capability, verifying a staged
mutation, saving to NVRAM, or explicit MSI firmware tuning.

Stay in general Comet operations for showing or reading a POST or BIOS screen
without firmware inspection, pressing a setup or boot-menu key as part of
another workflow, selecting one-time boot media, reading a POST error, recovering
a hung machine, mounting an installer, or ordinary console, power, recording,
and Tailscale work.

A screen being pre-boot does not by itself make the task BIOS triage. The
intended outcome must be firmware inspection, mapping, or modification.

The general skill establishes the target and transport, while the BIOS skill
chooses semantic firmware observation and actions. After the firmware-specific
portion, return to the general route for boot observation, service recovery,
media cleanup, or further physical-machine operation.

Do not apply MSI tuning assumptions to unrelated BIOS work.
