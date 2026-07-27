# Comet Pro Homelab Operations Briefing

> **Scope:** The deployed, portable GL.iNet Comet Pro (GL-RM10): what it is
> doing for the homelab today and the most useful ways to grow into its features.
> It moves between machines; it is not an N5 component or a permanently assigned
> host accessory.
>
> **Live snapshot:** 2026-07-27. No credentials, LAN address, tailnet name, or
> captured console content is recorded here.

## What is deployed now

The Comet Pro is a portable KVM appliance: HDMI-in provides a target's console,
and its USB connection presents keyboard, mouse, and virtual media to whichever
machine it is attached to. It is not an N5 component and it has no durable host
placement. A move is a physical operation: power the Comet, connect the target's
HDMI output, connect the USB data/HID lead, and choose Ethernet or Wi-Fi.

The device reports itself as RM10 on firmware `V1.9.1 release1`. It is already
online in the tailnet. Its current device-reported state is deliberately modest:

| Surface | Current observed state | What that means |
|---|---|---|
| Remote path | Tailscale running and peer online | The Comet can be reached privately without publishing a KVM service. It does not prove that the network behind the Comet survives a given outage. |
| Virtual media | Enabled, no mounted image, writable 28.8 GB internal `GLKVM` store | There is ample local space for a small, controlled recovery-media library. No mounted ISO has yet proved a particular host can boot from it. |
| Wake-on-LAN | API available; saved device list empty | The appliance can send a magic packet after a target NIC and its firmware power settings are commissioned. It does not press a physical power button. |
| ATX | API reports disabled | The owned ATX board is not yet installed or wired to a compatible target. No remote power/reset action is currently available through it. |
| Video streamer | H.264/H.265 and latency/quality controls reported; no active stream client during the read | The absent streamer is not evidence that HDMI is unplugged: the firmware tears it down when no client is streaming. |

This repository already exposes the useful MCP surface: `kvm_connect`,
`comet_sysinfo`, `comet_capabilities`, `comet_streamer_state`,
`comet_media_*`, `comet_wol_*`, `comet_tailscale_status`, screenshots, OCR, and
bounded keyboard/mouse input. They are the interface to use when operating the
portable appliance.

## Live read record — 2026-07-27

**Scope:** Read-only authenticated sessions against the deployed RM10. The
credential came from Doppler. No HID, power, WOL, media, recorder, firmware, or
Tailscale mutation was sent; no console image or tailnet identity was retained.

**Observed working:** the repository's explicit live smoke passed all three
checks: authenticated connect/sysinfo/JPEG snapshot, capability plus ATX/MSD
state reads, and a WebSocket pong. A separate read-only probe also returned
Tailscale running, ATX disabled and not busy, virtual media enabled with no
mounted image, an empty saved-WOL list, recorder idle, and a streamer-state
response containing feature, limit, parameter, snapshot, and streamer data.

**Observed failing in the later probe:** metrics were not part of the live
smoke. The first and repeat `comet_metrics` calls received HTTP 500 from
`/api/export/prometheus/metrics`. After the earlier successful JPEG reads, a
later `kvm_screenshot` request received HTTP 503. This is evidence of a
presently unavailable or intermittent snapshot surface, not proof that HDMI is
disconnected. Do not represent screenshots, OCR, or metrics as currently
qualified from this observation alone.

**Official MCP path confirmed:** the exact locked stdio launcher from
`.mcp.json` registered `kvm_connect` and `comet_metrics`; `kvm_connect` and
`kvm_disconnect` succeeded without a password passed through the tool call,
while `comet_metrics` surfaced the same HTTP 500. This confirms the observed
metrics failure reaches the packaged MCP path, not only a direct client call.

**Not tested:** physical HID effect, virtual-media mount/boot, WOL wake, ATX,
BIOS, and an independent-client tailnet recovery path. Those remain separate
disposable-target qualification work.

## What we are taking advantage of

### Portable console and pre-OS access

The immediate value is seeing and controlling POST, firmware setup, bootloaders,
and recovery environments when normal network administration is unavailable.
The MCP server supplies the transport: a short-lived authenticated session,
screenshots/OCR, and HID input with watchdog and key-release safeguards. Bring
the portable device to the machine that needs it; a past connection does not
become a permanent placement.

### Private remote console

Tailscale is already running on the Comet, so a trusted tailnet client can reach
the console without exposing the appliance or MCP stdio to the public Internet.
This is the preferred remote path over the vendor cloud service for this
homelab. It is especially useful for an operating-system or management-plane
failure. Naturally, it cannot help with a failure of the Comet's own power,
uplink, or tailnet path.

### Recovery media without a local USB swap

Virtual media lets the Comet present an ISO as a USB CD/DVD or disk to the
currently attached machine, including at the UEFI/BIOS boot menu. The purpose is
to boot a known-good installer, rescue environment, or diagnostic image without
walking a USB stick to every machine. The current free store makes that practical;
the missing proof is host-by-host boot behavior.

### A useful operator interface

For a consequential change, the MCP read tools make it easy to identify the
appliance and target, inspect media/ATX/Tailscale state, and—when the snapshot
surface is available—capture a fresh screen before sending input. After
interrupted input, `kvm_release_all` is the useful reset. Console recording
fits a short diagnostic capture rather than standing collection, because
consoles can display secrets.

## Suggested next moves

These are practical enhancements, roughly in useful order. The final column is
the small real-world check worth doing before expecting the feature to help in
an outage—not a process requirement.

| Priority | Enhancement | What it adds | A useful test |
|---|---|---|---|
| 1 | Try virtual media on one convenient host | Boot a checksum-verified rescue ISO through the Comet, then return the host to normal boot. | Upload, mount read-only as CD/DVD, see it in the host's UEFI boot picker, boot it, then unmount and remove it. |
| 2 | Set up WOL where it is handy | Turn on a sleeping or powered-off host without ATX wiring. | Add the correct NIC MAC, enable firmware/NIC WOL and standby power, then wake it after a normal shutdown. |
| 3 | Exercise the tailnet route once | Check that a remote operator can reach Comet and a physically attached host when the ordinary management route is unavailable. | From another tailnet client, reach the Comet, capture the console, and send a harmless HID action while the usual management path is unavailable. |
| 4 | Find a dependable video/input profile | Keep firmware and early boot video visible after target changes. | Try the Comet UI's EDID setting and relative/absolute mouse modes against a real BIOS/boot screen and the target OS; keep the one that feels dependable. |
| 5 | Keep a small portable connection kit | Make a move easy rather than relying on remembered cables. | Keep labeled independent 5 V power, HDMI-in, target USB HID/media, and Ethernet leads with the appliance; try the kit at a second host. |
| 6 | Add the existing ATX board to a compatible machine | Gain remote momentary power/reset where a motherboard header is physically available. | Install and wire the board, see the API change from disabled, and try soft power/reset on a suitable host. It is not a fit for the Beelink-class mini PCs. |

## Things to revisit later

- Two-factor login and a different TLS trust model could be worthwhile, but the
  current MCP login is password-based. Add support for the appliance's two-step
  flow and chosen certificate model first.
- Wi-Fi is useful for relocation; test its route in the failure scenario where
  you expect it to help.
- The vendor cloud service is available, but the existing tailnet path already
  covers the private-remote-access role.
- The existing ATX board becomes useful once it is installed on a compatible
  physical target; today the appliance reports it as disabled.

## References

- [Comet Pro product page](https://www.gl-inet.com/products/gl-rm10)
- [Comet Pro quick setup](https://docs.gl-inet.com/kvm/en/user_guide/gl-rm10/quick_setup_guide/)
- [Comet Pro control panel and virtual media](https://docs.gl-inet.com/kvm/en/user_guide/gl-rm10/control_panel_guide/)
- [KVM MCP hardware and platform reference](../reference/comet-hardware.md)
- [Disposable-node live qualification runbook](live-hardware-qualification.md)
