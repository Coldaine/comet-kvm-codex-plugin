from __future__ import annotations
from src.bios_sidecar.adapters.base import BiosAdapter

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
        "cpu_lite_load_mode": ["CPU Lite Load", "CPU Lite Load Control"],
        "pl1": ["Long Duration Power Limit (W)", "PL1"],
        "pl2": ["Short Duration Power Limit (W)", "PL2"],
        "icccmax": ["CPU Current Limit (A)", "ICCMAX"],
        "cep": ["IA CEP Support", "GT CEP Support"]
    }
