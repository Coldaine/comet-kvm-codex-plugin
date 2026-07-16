from __future__ import annotations
from src.bios_sidecar.adapters.base import BiosAdapter
from src.bios_sidecar.domain.enums import RiskClass

class MsiClickBiosAdapter(BiosAdapter):
    vendor = "msi"
    families = ["click_bios", "click_bios_5"]
    known_modules = [
        "SETTINGS",
        "OC",
        "M-FLASH",
        "OC PROFILE",
        "HARDWARE MONITOR",
        "BOARD EXPLORER"
    ]
    hard_block_keywords = [
        "M-FLASH",
        "Secure Erase",
        "BIOS Update",
        "Password",
        "Load Optimized Defaults",
        "Save Changes and Reboot"
    ]
    known_capabilities = {
        "cpu_lite_load_mode": {
            "canonical_name": "CPU Lite Load Mode",
            "aliases": ["CPU Lite Load", "CPU Lite Load Control", "CPU Lite Load Mode"],
            "risk": RiskClass.MEDIUM,
            "mutation_policy": "supervised_one_setting"
        },
        "pl1": {
            "canonical_name": "Power Limit 1",
            "aliases": ["Long Duration Power Limit (W)", "PL1", "Power Limit 1"],
            "risk": RiskClass.HIGH,
            "mutation_policy": "supervised_one_setting"
        },
        "pl2": {
            "canonical_name": "Power Limit 2",
            "aliases": ["Short Duration Power Limit (W)", "PL2", "Power Limit 2"],
            "risk": RiskClass.HIGH,
            "mutation_policy": "supervised_one_setting"
        },
        "cpu_cooler_tuning": {
            "canonical_name": "CPU Cooler Tuning",
            "aliases": ["CPU Cooler Tuning", "Cooler Type"],
            "risk": RiskClass.MEDIUM,
            "mutation_policy": "supervised_one_setting"
        },
        "icccmax": {
            "canonical_name": "CPU Current Limit",
            "aliases": ["CPU Current Limit (A)", "ICCMAX"],
            "risk": RiskClass.HIGH,
            "mutation_policy": "supervised_one_setting"
        },
        "cep": {
            "canonical_name": "IA CEP Support",
            "aliases": ["IA CEP Support", "GT CEP Support"],
            "risk": RiskClass.HIGH,
            "mutation_policy": "supervised_one_setting"
        }
    }
