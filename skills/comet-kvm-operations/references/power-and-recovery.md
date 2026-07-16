# Power and Recovery

Read this file when the physical host is off, hung, boot-looping, unreachable,
or requires a power transition.

## Classify before escalating

Check another available native management path when appropriate, then call
`comet_power_state` and inspect the live console. Distinguish powered off,
network-unreachable, operating-system hang, crash screen, POST stall, boot loop,
and unknown or no video. Use the least disruptive effective recovery path.

## Choose the transition

When Wake-on-LAN is expected to work, inspect `comet_wol_list` or
`comet_wol_scan`, then call `comet_wol_wake` for the intended MAC. Verify power
and video progression.

When ATX control is available:

- call `comet_atx_power` with `on` for a powered-off machine;
- prefer a graceful operating-system shutdown through another available exact
  interface when the system still responds;
- use `comet_atx_click` with the normal power button when a physical button
  action is appropriate;
- use `comet_atx_power` with `reset_hard` only for a confirmed hang, explicit
  hardware-reset request, or bounded boot retry;
- use `comet_atx_power` with `off_hard` only when softer recovery cannot advance
  the machine or the user explicitly requests forced power-off.

Use `comet_redfish_power` only when Redfish is the requested or established
management interface.

## Verify the transition

Do not treat an HTTP success as recovery. Verify the power state, video change,
POST progression, intended boot target, or recovery of another exact service.
If the machine remains stuck, recapture the console before choosing the next
escalation. Do not repeat hard resets without new evidence.

For an intermittent boot loop, use a bounded recording through
`comet_recorder_start` and `comet_recorder_stop`, then verify recording state
with `comet_recorder_state`.
