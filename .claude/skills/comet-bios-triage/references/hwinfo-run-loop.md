# HWiNFO Run Loop

Read this file only when the user explicitly requests HWiNFO-backed validation.
This plugin does not provide HWiNFO control, a Windows transport, a workload
runner, or an external analysis project. Confirm those mechanisms and all file
destinations before starting.

After one verified BIOS change:

1. Boot Windows.
2. Start HWiNFO sensor logging through the available Windows control path.
3. Run the same named workload, duration, and configuration used for the
   baseline.
4. Stop logging.
5. Preserve the CSV at the user-selected destination.
6. Analyze it with tools or scripts that are confirmed to exist in the current
   environment.
7. Record maximum CPU package temperature, package power, Vcore or VR VOUT,
   effective clocks, throttle indicators, workload result, and WHEA errors.

Use the same sensor set and aggregation rules across runs. Stop the experiment
after WHEA errors, a crash or reboot, workload failure, performance collapse,
severe throttling, clock-stretching, missing logs, or incomparable run
conditions.

Do not claim a firmware change is stable from a successful boot alone. Report
the exact workload evidence, the log location, comparison limitations, and the
last verified stable firmware state.
