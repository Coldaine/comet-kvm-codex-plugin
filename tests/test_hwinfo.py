from src.bios_sidecar.controller.hwinfo import parse_hwinfo_csv
import tempfile
import os

def test_parse_hwinfo():
    csv_data = """Time,CPU Package [°C],CPU Package Power [W],Vcore [V],Core 0 T0 Effective Clock [MHz],Core Thermal Throttling [Yes/No],Windows Hardware Errors (WHEA) [Errors]
0:00,35.0,20.5,1.1,4000.0,0,0
0:01,89.0,150.0,1.35,5200.0,1,0
0:02,91.0,155.0,1.36,5200.0,0,2
"""
    with tempfile.TemporaryDirectory() as tmp:
        fpath = os.path.join(tmp, "log.csv")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(csv_data)
        
        res = parse_hwinfo_csv(fpath)
        assert res["max_temperature_c"] == 91.0
        assert res["max_power_w"] == 155.0
        assert res["max_voltage_v"] == 1.36
        assert res["max_effective_clock_mhz"] == 5200.0
        assert res["throttled"] is True
        assert res["whea_errors"] == 2
