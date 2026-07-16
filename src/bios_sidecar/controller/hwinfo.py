import csv
from pathlib import Path
from typing import Dict, Any

def parse_hwinfo_csv(csv_path: str) -> Dict[str, Any]:
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
    if not rows:
        return {}

    # Extract max limits across all rows for thermal, power, voltage, clocks, whea 
    max_temp = 0.0
    max_power = 0.0
    max_voltage = 0.0
    max_clock = 0.0
    throttling = False
    whea_count = 0
    
    for row in rows:
        for k, v in row.items():
            if not v: continue
            try:
                val = float(v)
            except ValueError:
                continue
                
            kl = k.lower()
            if "cpu package" in kl and "°c" in kl:
                max_temp = max(max_temp, val)
            elif "cpu package power" in kl:
                max_power = max(max_power, val)
            elif "vcore" in kl or "vr vout" in kl:
                max_voltage = max(max_voltage, val)
            elif "effective clock" in kl and "avg" not in kl:
                max_clock = max(max_clock, val)
            elif "thermal throttling" in kl and val > 0:
                throttling = True
            elif "whea" in kl or "windows hardware error" in kl:
                whea_count = max(whea_count, val)

    return {
        "max_temperature_c": max_temp,
        "max_power_w": max_power,
        "max_voltage_v": max_voltage,
        "max_effective_clock_mhz": max_clock,
        "throttled": throttling,
        "whea_errors": int(whea_count)
    }

def discover_hwinfo_csv(search_dir: str) -> str:
    path = Path(search_dir)
    files = list(path.glob("*.csv"))
    if not files:
        raise FileNotFoundError("No HWiNFO CSV logs found in directory.")
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return str(files[0])
