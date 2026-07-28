# BIOS Settings Transcription

**Motherboard:** MPG Z690 CARBON EK X  
**CPU:** Intel(R) Core(TM) i9-14900K  
**Memory Size:** 65536MB (64GB)  
**BIOS Version:** E7D30IMS.1K0  
**BIOS Build Date:** 10/01/2024  
**BIOS Mode:** CSM/UEFI

---

## System Information (from header)

- **CPU Core Temperature:** 28-29°C
- **Motherboard Temperature:** 39°C
- **VCore:** 0.918V
- **CPU Speed:** 3.20 GHz
- **Memory Speed:** 4800 MHz
- **XMP Profile:** 1 (user)

---

## Settings\Advanced\PCIe/PCI Sub-system Settings

| Setting | Value |
|---------|-------|
| M2_1 Gen Mode | [Auto] |
| M2_2 Gen Mode | [Auto] |
| M2_3 Gen Mode | [Auto] |
| M2_4 Gen Mode | [Auto] |
| M2_5 Gen Mode | [Auto] |
| PCI_E1 Gen Mode | [Auto] |
| PCI_E2 Gen Mode | [Auto] |
| CPU PCIe Lanes Configuration | [Auto] |
| PCI Latency Timer | [32 PCI Bus Clocks] |
| Above 4G memory/Crypto Currency mining | [Enabled] |
| Max TOLUD | [Dynamic] |
| Re-Size BAR Support | [Enabled] |
| PCIe Native Power Management | [Enabled] |
| Native ASPM | [Disabled] |

### PCIe/PCI ASPM Settings (sub-menu)

| Setting | Value |
|---------|-------|
| PEG 0 ASPM | [Disabled] |
| PEG 1 ASPM | [Disabled] |
| PEG 2 ASPM | [Disabled] |
| PCI Express Root Port 5 ASPM | [Disabled] |

---

## Settings\Advanced\Integrated Peripherals

### Onboard LAN Configuration

| Setting | Value |
|---------|-------|
| VGA Detection | [Auto] |
| Onboard LAN Controller | [Enabled] |
| LAN Option ROM | [Disabled] |
| Network stack | [Disabled] |
| Onboard Wi-Fi/BT Module Control | [Auto] |
| BT Tile Mode | [Disabled] |
| Onboard CNVi Module Control | [Auto Detection] |

### SATA Configuration

| Setting | Value |
|---------|-------|
| RAID Configuration (Intel VMD) | > (sub-menu) |
| SATA5 Hot Plug | [Disabled] |
| SATA6 Hot Plug | [Disabled] |
| SATA7 Hot Plug | [Disabled] |
| SATA8 Hot Plug | [Disabled] |
| External SATA 6GB/s Controller Mode | [AHCI Mode] |
| SATAA Hot Plug | [Disabled] |
| SATAB Hot Plug | [Disabled] |

### Audio Configuration

| Setting | Value |
|---------|-------|
| HD Audio Controller | [Enabled] |

---

## Settings\Advanced\Intel(R) Thunderbolt

| Setting | Value |
|---------|-------|
| PCIE Tunneling over USB4 | [Enabled] |
| Discrete Thunderbolt(TM) Support | [Disabled] |

---

## Settings\Advanced\Wake Up Event Setup

### Setup Wake Up Configuration

| Setting | Value |
|---------|-------|
| Wake Up Event By | [BIOS] |
| Resume By RTC Alarm | [Disabled] |
| Resume By PCI-E/Networking Device | [Disabled] |
| Resume By Intel CNVi | [Disabled] |
| Resume By USB Device | [Disabled] |

---

## Settings\Boot

### Boot Configuration

| Setting | Value |
|---------|-------|
| Full Screen Logo Display | [Enabled] |
| GO2BIOS | [Enabled] |
| Bootup NumLock State | [On] |
| Info Block effect | [Unlock] |
| POST Beep | [Disabled] |
| MSI Fast Boot | [Disabled] |
| Fast Boot | [Disabled] |
| Post Screen Delay | [Auto] |

### Boot mode select

| Setting | Value |
|---------|-------|
| Boot mode select | [UEFI] |

### FIXED BOOT ORDER Priorities

| Priority | Device |
|----------|--------|
| Boot Option #1 | [UEFI Network] |
| Boot Option #2 | [UEFI Hard Disk:F...] |
| Boot Option #3 | [UEFI CD/DVD] |
| Boot Option #4 | [UEFI USB Hard Di...] |
| Boot Option #5 | [UEFI USB CD/DVD] |
| Boot Option #6 | [UEFI USB Key] |
| Boot Option #7 | [UEFI USB Floppy] |

### Additional Boot Sub-menus

- UEFI Hard Disk Drive BBS Priorities >
- UEFI USB Hard Disk Drive BBS Priorities >

---

## Settings\Security

| Setting | Value |
|---------|-------|
| Administrator Password | Not Installed |
| User Password | Not Installed |
| U-Key | Not Installed |

### U-Key

| Setting | Value |
|---------|-------|
| Make U-Key at | [Disabled] |
| U-Key Execution Level | [Normal] |

### Additional Security Sub-menus

- Trusted Computing >
- Chassis Intrusion Configuration >
- Secure Boot >

---

## Settings\Security\Secure Boot

| Setting | Value |
|---------|-------|
| System Mode | User |
| Secure Boot | [Disabled] |
| Secure Boot Mode | [Standard] |
| Secure Boot Preset | [Hardware/OS Compatibility] |

### Sub-menu

- Key Management >

---

## Boot Priority bar (Settings\Boot header)

Same order as **FIXED BOOT ORDER Priorities** above (icons in the Settings\Boot header bar, from IMG_5882):

1. UEFI Network
2. UEFI Hard Disk
3. UEFI CD/DVD
4. UEFI USB Hard Disk
5. UEFI USB CD/DVD
6. UEFI USB Key
7. UEFI USB Floppy

Other corpus photos may show a shorter icon strip when Network is not emphasized; treat the Settings\Boot fixed-priority table as authoritative.

---

## Hot Keys

| Key | Function |
|-----|----------|
| ↑↓ | Move |
| Enter | Select |
| +/- | Value |
| ESC | Exit |
| F1 | General Help |
