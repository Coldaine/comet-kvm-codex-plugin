from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
ALLOWED_PHASES = {
    "planned",
    "preflight",
    "bios-entry",
    "bios-read",
    "bios-edit",
    "save-confirm",
    "windows-boot",
    "hwinfo-log",
    "analysis",
    "done",
    "blocked",
}


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id must be 1-128 characters: letters, numbers, dot, underscore, or hyphen")
    return run_id


def validate_phase(phase: str) -> str:
    if phase not in ALLOWED_PHASES:
        allowed = ", ".join(sorted(ALLOWED_PHASES))
        raise ValueError(f"phase must be one of: {allowed}")
    return phase


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def create_run(run_id: str, target: str, setting: str, old_value: str, new_value: str) -> Path:
    run_id = validate_run_id(run_id)
    run_dir = RUNS / run_id
    screenshots = run_dir / "screenshots"
    if run_dir.exists():
        raise FileExistsError(f"Run already exists: {run_id}")
    screenshots.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "created_at": now_utc(),
        "target": target,
        "phase": "planned",
        "planned_change": {
            "setting": setting,
            "old_value": old_value,
            "new_value": new_value,
        },
        "bios_evidence": {},
        "windows_evidence": {},
        "result": {
            "status": "pending",
            "notes": "",
        },
    }
    path = run_dir / "run.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def set_phase(run_id: str, phase: str) -> Path:
    run_id = validate_run_id(run_id)
    phase = validate_phase(phase)
    path = RUNS / run_id / "run.json"
    if not path.exists():
        raise FileNotFoundError(f"Run ledger not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["phase"] = phase
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def attach_hwinfo_evidence(run_id: str, search_dir: str) -> Path:
    from src.bios_sidecar.controller.hwinfo import discover_hwinfo_csv, parse_hwinfo_csv
    run_id = validate_run_id(run_id)
    path = RUNS / run_id / "run.json"
    if not path.exists():
        raise FileNotFoundError(f"Run ledger not found: {path}")
        
    csv_file = discover_hwinfo_csv(search_dir)
    metrics = parse_hwinfo_csv(csv_file)
    
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["windows_evidence"] = metrics
    
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path

def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create")
    create.add_argument("--run-id", required=True)
    create.add_argument("--target", required=True)
    create.add_argument("--setting", required=True)
    create.add_argument("--old-value", required=True)
    create.add_argument("--new-value", required=True)

    phase = sub.add_parser("phase")
    phase.add_argument("--run-id", required=True)
    phase.add_argument("--phase", required=True)
    
    hwinfo = sub.add_parser("hwinfo")
    hwinfo.add_argument("--run-id", required=True)
    hwinfo.add_argument("--search-dir", required=True)

    args = parser.parse_args()
    try:
        if args.cmd == "create":
            path = create_run(args.run_id, args.target, args.setting, args.old_value, args.new_value)
        elif args.cmd == "phase":
            path = set_phase(args.run_id, args.phase)
        elif args.cmd == "hwinfo":
            path = attach_hwinfo_evidence(args.run_id, args.search_dir)
    except (FileExistsError, FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2) from exc
    print(path)


if __name__ == "__main__":
    main()
