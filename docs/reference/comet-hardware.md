# Deployed Comet Pro Hardware & Platform Reference

> **Repo:** `Coldaine/comet-kvm-codex-plugin` (fork of `kennypeh85/glkvm-mcp`)
> **Scope:** The homelab's portable GL.iNet Comet Pro **GL-RM10**. This is not
> a comparison of the Comet product family and must not use base-Comet facts as
> facts about the deployed unit.
> **Sources:** GL.iNet's GL-RM10 product and setup documentation, plus the
> dated authenticated read in the operations briefing. No credentials, console
> images, or tailnet identity are retained here.
> **Revised:** 2026-07-27

## Identified appliance

| Fact | Value | Basis |
|---|---|---|
| Product | GL.iNet Comet Pro (GL-RM10) | Confirmed physical unit and GL.iNet product documentation |
| Processor | Quad-core ARM Cortex | GL.iNet product page; it does not name a more specific CPU model |
| Memory / internal storage | 1 GB DDR3L / 32 GB eMMC | GL.iNet product page |
| Capture class | 4K at 30 fps | GL.iNet product page; not a guarantee for every target's HDMI mode |
| Network | Gigabit Ethernet and dual-band Wi-Fi 6 | GL.iNet product and setup documentation |
| Local controls | 2.22-inch touchscreen and reset pinhole | GL.iNet product and overview documentation |
| Observed firmware | `V1.9.1 release1` | Authenticated read, 2026-07-27 |

The MCP implementation targets the shared GLKVM/PiKVM-style API surface. That
does not make another Comet SKU's storage, connector, power, or recovery facts
applicable to this RM10.

## Connections for a move

For a controlled machine, GL.iNet's RM10 setup specifies these connections:

1. Power the Comet Pro.
2. Connect the target's HDMI output to the Comet Pro **HD IN** port.
3. Connect the Comet Pro's USB Type-C data port to the target's USB port for
   keyboard, mouse, and virtual media.
4. Give the Comet Pro network access over Ethernet or 2.4/5 GHz Wi-Fi.

**HD OUT** is optional for a local monitor. Exact cables and accessories present
in the portable kit are not inferred here; record them only after a physical
inventory.

## Present deployed state

The 2026-07-27 authenticated read observed a writable `GLKVM` virtual-media
partition with 28,797,599,744 bytes total and 28,797,403,136 bytes free.
Tailscale reported running. The ATX API reported disabled. The ATX add-on
board is owned but not yet installed or wired to a compatible target.

This is appliance state from one dated read, not a standing health claim. In
the same observation window, Prometheus metrics returned HTTP 500 and a later
snapshot request returned HTTP 503; see the [operations briefing](../workflows/comet-pro-homelab-briefing.md#live-read-record--2026-07-27).

## Hardware facts still unverified for this unit

- The exact Linux partition layout, root-shell access, and free space outside
  the media API.
- Any external-storage expansion path.
- The physical contents and condition of the portable cable/power kit.
- Actual target behavior for capture, USB HID, virtual-media boot, Wake-on-LAN,
  and ATX. Those are target-dependent qualification tasks, not appliance specs.

## Operating limits that matter

- The advertised 4K@30 capture class does not establish that a particular
  target's firmware screen, resolution, HDCP state, or cable path will capture
  correctly.
- Tailscale being enabled does not prove remote recovery from an independent
  client or through a particular outage.
- The separate ATX board is required for remote power/reset; the deployed
  appliance currently reports that board disabled.
- The appliance uses a self-signed HTTPS certificate. The MCP client currently
  disables certificate verification, so access belongs on the trusted LAN or
  through the private tailnet—not on a directly exposed public interface.

## Sources

- [Comet Pro (GL-RM10) product page](https://www.gl-inet.com/products/gl-rm10/)
- [Comet Pro overview](https://docs.gl-inet.com/kvm/en/user_guide/gl-rm10/product_overview/)
- [Comet Pro quick setup](https://docs.gl-inet.com/kvm/en/user_guide/gl-rm10/quick_setup_guide/)
- [Dated live read](../workflows/comet-pro-homelab-briefing.md#live-read-record--2026-07-27)
