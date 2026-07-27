# Appliance Diagnostics

Read this file when the object of diagnosis is the Comet appliance or its
management path rather than the attached computer.

Use `comet_capabilities` and `comet_sysinfo` to identify model, firmware, and
supported subsystems. Refresh capabilities only after firmware, hardware, or
configuration changes.

Use `comet_streamer_state` to inspect capture and stream parameters. Call
`comet_streamer_set_params` only to address an observed video problem, retain
the prior values for rollback, and verify the console afterward.

For bounded evidence collection, check `comet_recorder_state`, call
`comet_recorder_start` immediately before the diagnostic window, call
`comet_recorder_stop` afterward, and inspect state again. Do not leave recording
running without a defined purpose.

Use `comet_metrics` for appliance telemetry and `comet_tailscale_status` for the
Comet's overlay state. Tailscale reachability is not evidence that the attached
host is healthy. This plugin reports Tailscale status; it does not configure
exit nodes or subnet routes.

Separate authentication, transport, video capture, appliance health, overlay
networking, and attached-machine failures in the result.
