from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


def create_run(run_id: str, target: str, setting: str, old_value: str, new_value: str) -> Path:
    run_dir = RUNS / run_id
    screenshots = run_dir / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
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
    path = RUNS / run_id / "run.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["phase"] = phase
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

    args = parser.parse_args()
    if args.cmd == "create":
        path = create_run(args.run_id, args.target, args.setting, args.old_value, args.new_value)
    else:
        path = set_phase(args.run_id, args.phase)
    print(path)


if __name__ == "__main__":
    main()
