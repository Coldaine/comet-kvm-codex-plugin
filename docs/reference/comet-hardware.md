# Comet KVM Hardware & Platform Reference

> **Repo:** `Coldaine/comet-kvm-codex-plugin` (fork of `kennypeh85/glkvm-mcp`)
> **Status:** Verified from public datasheets, GL.iNet docs, and GitHub issues.
> **Compiled:** 2026-07-07 · **Revised:** 2026-07-15 (RM1 vs Pro facts)
> **Purpose:** Hardware facts for map storage, packaging, and model differences. No network-ops or Tailscale topology advice (see [`docs/research/oob-proxmox-tailscale-vision.md`](../research/oob-proxmox-tailscale-vision.md) if needed).

## Device Family

GL.iNet sells three Comet KVM variants, all running a PiKVM-fork Linux firmware (`kvmd`):

| Model | SKU | CPU | RAM | Storage | Network | Key Differentiator |
|-------|-----|-----|-----|---------|---------|---------------------|
| Comet | GL-RM1 | Quad-core ARM Cortex-A7 @ 1.5GHz | 1GB DDR3 | 8GB eMMC | Gigabit Ethernet | Base model, smallest |
| Comet PoE | GL-RM1PE | Quad-core ARM Cortex-A7 | 1GB DDR3 | 32GB eMMC | Gigabit Ethernet (PoE) | Power-over-Ethernet, larger storage |
| Comet Pro | GL-RM10 | Quad-core ARM Cortex-A53 | 1GB DDR3L | 32GB eMMC | Wi-Fi 6 + Ethernet | Touchscreen, Wi-Fi, 4K@30fps capture class |

**This project’s documented LAN target is the base Comet (GL-RM1)** at `192.168.0.126` unless otherwise noted. The same `/api` surface applies across the family; optional hardware (ATX board, Fingerbot, Wi-Fi, touchscreen) and storage size differ by SKU. Prefer `GET /api/system/capability` and `/api/upgrade/version` to learn the connected unit.

### RM1 vs RM10 (facts only)

| Fact | GL-RM1 (Comet) | GL-RM10 (Comet Pro) |
|------|----------------|---------------------|
| SoC class | Cortex-A7 | Cortex-A53 |
| eMMC | 8GB | 32GB |
| Usable media storage (order of magnitude) | ~5–6GB free on `/userdata/media` in a documented root `df` (see below) | Reviewers commonly report roughly mid-20s GB usable for ISOs after system overhead — confirm with `df` / `GET /api/msd` on the unit |
| Wireless | Ethernet primary (no Wi-Fi 6 SKU claim on base) | Wi-Fi 6 + Ethernet |
| Local UI | No built-in touchscreen | Touchscreen (setup, status, lock) |
| HDMI capture class | 1080p-class product positioning | Product materials cite 4K@30fps-class capture |
| Access modes | Browser UI; cloud / app options per GL.iNet docs | Same family APIs; product materials emphasize Tailscale among remote-access options |

> **Sources:**
> - GL-RM1 datasheet (PDF): `static.gl-inet.com/www/images/products/datasheet/rm1_datasheet_20250616.pdf` — accessed 2026-07-07
> - GL-RM1 product page: `gl-inet.com/en-us/products/gl-rm1` — accessed 2026-07-07
> - Comet PoE datasheet (PDF): `static.gl-inet.com/www/images/products/datasheet/rm1pe_datasheet_20251110.pdf` — accessed 2026-07-07
> - Comet Pro product page: `gl-inet.com/en-us/products/gl-rm10` — accessed 2026-07-07
> - GL.iNet KVM Docs — Comet Pro overview: `docs.gl-inet.com/kvm/en/user_guide/gl-rm10/product_overview/` — accessed 2026-07-15
> - CNX Software review (2025-07-13): `cnx-software.com/2025/07/13/review-of-gl-inet-comet-gl-rm1-kvm-over-ip-solution-and-atx-power-control-board/`

## Physical Interfaces (GL-RM1)

- 1x Gigabit Ethernet (10/100/1000Mbps, DHCP)
- 1x HDMI-IN
- 1x HDMI-OUT (video passthrough)
- 1x USB 2.0 Type-A (for external extension / mass storage)
- 1x USB 2.0 Type-C (keyboard/mouse emulation to target — **not for power**)
- 1x USB Type-C power input (5V/2A, **not PD-compatible** on base model)
- 1x Reset button

**Critical warning from GL.iNet docs:** The USB-C data port is for keyboard/mouse signal only. Do not connect it to a Thunderbolt host via USB-C to USB-C — reverse current injection may permanently damage the KVM hardware.

> **Source:** GL.iNet KVM Docs — Comet (GL-RM1) Product Overview: `docs.gl-inet.com/kvm/en/user_guide/gl-rm1/product_overview/` — accessed 2026-07-07

## Physical Interfaces (GL-RM10 / Comet Pro)

Product package and overview materials list Ethernet, HDMI cables, USB-A↔C and USB-C↔C cables, USB-A power adapter, touchscreen, Wi-Fi setup, cloud/network status on the home screen, and a factory-reset pinhole. Same KVM role as RM1 (HDMI capture + USB HID to target) with larger eMMC, wireless, and a local display. ATX control still requires the separate ATX add-on board wired to the target motherboard.

> **Source:** GL.iNet KVM Docs — Comet Pro (GL-RM10) Product Overview — accessed 2026-07-15

## Operating System & Firmware

- **OS:** Linux 6.1 (PiKVM-fork, `kvmd` daemon)
- **Firmware line:** 1.x family; discover exact build via `GET /api/upgrade/version` and `GET /api/info` on the unit (do not pin a triple as client authority)
- **Web access:** Browser-based UI; GL.iNet also documents cloud service (`glkvm.com`), mobile/app access, and overlay-network options depending on model/firmware
- **Self-signed certificate:** Device ships with a self-signed cert; this MCP’s httpx client uses `verify=False`

> **Sources:**
> - `src/kvm_core/comet/client.py` (`httpx.AsyncClient(verify=False, ...)`) — verified on main 2026-07-15
> - Product pages / GL.iNet KVM docs for access modes
> - CVE-2026-32291 (CVE.report): `cve.report/CVE-2026-32291` — firmware version context for UART issue (fixed in 1.8.2)

## On-Device Storage Layout (Verified)

This is the critical section for the map-store design decision. A real root shell session on the Comet (GL-RM1, 8GB) was documented in a GitHub issue, confirming the filesystem layout:

```
[root@glkvm:/]# df
Filesystem      1K-blocks   Used   Available  Use%  Mounted on
/dev/root        185216     185216 0          100%  /rom
devtmpfs         374884     0      374884     0%    /dev
tmpfs            375396     88     375308     1%    /dev/shm
tmpfs            375396     28     375368     1%    /tmp
tmpfs            375396     284    375112     1%    /run
/dev/mmcblk0p7   192061     4800   179266     3%    /oem        (ext4)
/dev/mmcblk0p8   1032088    1516   978144     1%    /userdata   (ext2)
overlay:/overlay 1032088    1516   978144     1%    /
/dev/mmcblk0p10  6011072    691552 5319520    12%   /userdata/media
/dev/sda1        120655104  19931904 100723200 17%  /media/usb1  (exFAT, external USB)
```

**Key findings:**

| Mount point | Device | FS | Size | Free | Use case |
|-------------|--------|----|------|------|----------|
| `/` (overlay) | overlay:/overlay | overlayfs | ~1GB | ~978MB | Root filesystem (read-only base + writable overlay) |
| `/oem` | mmcblk0p7 | ext4 | ~192MB | ~179MB | OEM config |
| `/userdata` | mmcblk0p8 | ext2 | ~1GB | ~978MB | User data |
| `/userdata/media` | mmcblk0p10 | exFAT | ~6GB | ~5.3GB | **Virtual media / mass storage — primary writable space** |
| `/media/usb1` | sda1 | exFAT | (external) | — | USB-A mounted external drive |

**Implication for this project:** `/userdata/media` has ~5.3GB free on the base 8GB model. A BIOS map for a single board is ~300-400 screens × ~100KB JPEG = ~30-40MB, plus graph metadata in KB. The Comet has **two orders of magnitude more storage than needed** for map persistence. Even with screenshot TTL retention (~30 days), the device can hold dozens of board maps.

**Root access is confirmed.** The issue shows a `[root@glkvm:/]#` shell prompt, meaning SSH or serial console provides root-level access to the Linux userspace. Config changes are made via `/etc/kvmd/override.yaml`.

> **Sources:**
> - GitHub issue `gl-inet/glkvm#14` (2025-05-11): `github.com/gl-inet/glkvm/issues/14` — full `df` and `blkid` output from a root session, USB drive mounting instructions, `kvmd` override config. Accessed 2026-07-07.
> - EnosTech review (2025-07-07): `enostech.com/gl-inet-comet-remote-kvm-review/` — confirms 8GB eMMC, notes space constraints for ISO mounting, mentions USB expansion. Accessed 2026-07-07.

## External Storage Expansion

The USB-A 2.0 port can mount external exFAT drives, expanding available storage arbitrarily:

- Format USB drive as exFAT (other formats may cause issues)
- Insert into USB-A port
- Device auto-mounts at `/media/usbN`
- Can be configured as virtual media source via `/etc/kvmd/override.yaml`:
  ```yaml
  kvmd:
    msd:
      partition_device: /dev/disk/by-uuid/<UUID>
  ```
- USB hub supported — ATX board and mass storage can coexist on the USB-A port

> **Source:** GitHub issue `gl-inet/glkvm#14` — explicit instructions and confirmation from GL.iNet staff. Accessed 2026-07-07.

## GPU / Compute Constraints

**No GPU.** The Comet uses a Cortex-A7 (GL-RM1) or Cortex-A53 (GL-RM10) — ARM cores with no GPU acceleration suitable for ML inference.

**Implication:** Any VLM (Vision-Language Model) interpretation of BIOS screenshots must run on the **host machine**, not on the Comet device. The Comet is transport and storage only; perception stays on the host. This is a hard constraint, not a preference.

## Known Security Considerations

| Issue | Severity | Status | Details |
|-------|----------|--------|---------|
| UART unauthenticated root | High | Fixed in firmware 1.8.2 | CVE-2026-32291: physical access to UART pins gave root shell before 1.8.2. Requires opening the device. |
| Self-signed TLS cert | Low (by design) | N/A | Client must disable TLS verification. Intended for LAN use only. |
| LAN-only design | Informational | N/A | Device is designed for trusted local networks. Do not expose to untrusted networks without VPN (Tailscale supported). |

> **Sources:**
> - CVE-2026-32291: `cve.report/CVE-2026-32291` — accessed 2026-07-07
> - `glkvm_mcp.py` docstring (lines 27-29): "Scope: LAN only. TLS verification is disabled because the device ships a self-signed certificate." — verified 2026-07-07

## What This Project Exercises on the Device

Primary live path (see [`comet-api.md` verification status](comet-api.md#verification-status)):

1. `POST /api/auth/login` — authentication
2. `WSS /api/ws` with `stream=false` — keyboard/mouse input over WebSocket
3. `GET /api/streamer/snapshot` — JPEG frame capture
4. `GET /api/info` — sysinfo tool
5. `GET /api/streamer/ocr` — capability probe (often disabled on the LAN unit)

ATX power actions and MSD ISO upload/mount have **not** been live-qualified in read-only smoke. Fuller firmware inventory: [`docs/research/glkvm-api-surface.md`](../research/glkvm-api-surface.md).

**SSH write to `/userdata/media` is not a required MCP path** — MSD APIs are the supported virtual-media interface. Root shell layout above remains useful for capacity planning.

## Summary of Design-Relevant Facts

| Fact | Source | Design Impact |
|------|--------|---------------|
| RM1: 8GB eMMC, ~5.3GB free at `/userdata/media` | gl-inet/glkvm#14 | Maps fit easily on base model |
| RM10: 32GB eMMC | Product materials | Headroom for multiple installer/rescue ISOs; confirm with `df` / MSD state |
| Root SSH layout confirmed (RM1) | gl-inet/glkvm#14 | Capacity planning; optional direct file ops |
| No GPU (Cortex-A7/A53) | Datasheets | VLM interpretation must run on host, not device |
| USB-A expansion supported | gl-inet/glkvm#14 | Soft storage ceiling via external drive |
| PiKVM-fork firmware (`kvmd`) | Product + glkvm source | Shared `/api` family; `override.yaml` for config |
| Self-signed cert | Client + CVE context | TLS verify disabled in MCP httpx client |
| Background asyncio loops in KVM core | `src/kvm_core/comet/client.py` | Transport reliability pattern already present |
