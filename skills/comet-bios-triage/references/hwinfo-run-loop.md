# HWiNFO Run Loop

After each BIOS change:

1. Boot Windows.
2. Start HWiNFO sensor logging.
3. Run the same workload used for the prior run.
4. Stop logging.
5. Copy the CSV into `D:\_projects\hwinfo-cpu-triage\raw`.
6. Rebuild exports using the existing HWiNFO triage scripts.
7. Record max CPU package temperature, package power, Vcore/VR VOUT, effective clocks, throttle rows, and WHEA errors in the run ledger.

Existing analysis project:

- `D:\_projects\hwinfo-cpu-triage`
- `scripts\export_hwinfo_cpu.py`
- `scripts\build_duckdb_exports.py`
- `docs\triage-playbook.md`
