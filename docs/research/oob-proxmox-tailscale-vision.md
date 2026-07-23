# OOB Proxmox / Tailscale / Comet vision

> **Kind:** Research / deployment **judgment** — not project authority.  
> **Do not** treat this as `NORTH_STAR` until explicitly promoted via `docs/decisions.md`.  
> **API contracts:** Link to [`glkvm-api-surface.md`](glkvm-api-surface.md) and [`docs/reference/comet-api.md`](../reference/comet-api.md). This file does not re-list every endpoint.  
> **Repo blockers:** See [`glkvm-client-audit-2026-07-15.md`](glkvm-client-audit-2026-07-15.md) — do not mix remediation into this vision.

Banner for agents: this is how we *might* deploy Comet as an out-of-band control plane beside Proxmox and Tailscale. It encodes operational experience and recommendations, not firmware facts.

---

## 1. Control-plane framing

Treat the Comet (especially Pro / RM10-class) as an **OOB control plane**, not merely a remote monitor:

| Plane | Path | Role |
|-------|------|------|
| **Normal operations** | Proxmox API, SSH, cluster UI, automation | Day-to-day VM/host management |
| **Recovery operations** | Tailnet → Comet → BIOS/console (HID + snapshot/OCR) | Inspect and recover when the node plane is sick |
| **Physical recovery** | Comet → ATX board / Fingerbot → power / reset | Hardware power when software paths fail |
| **Provisioning** | Comet virtual media (MSD) → automated Proxmox installer | Bare-metal / rebuild factory |

Firmware is a PiKVM-derived `kvmd` stack; the native `/api` surface is enough for serious automation beyond the web UI. A narrow `/redfish/v1` power facade already exists — use it for generic power tools; use native APIs for everything else.

---

## 2. Tailscale topology and toggles

Recommended starting point for a Comet attached to a Proxmox node:

| Setting | Recommendation | Reason |
|---------|----------------|--------|
| Tailscale | **On** | Direct remote access to the Comet itself |
| Exit Node | **Off** | Routes general Internet traffic through the Comet; no benefit for reaching the KVM |
| Subnet Routes | **Off initially** | Enable only when the Comet should gateway specific non-tailnet networks (ideally a dedicated OOB VLAN) |

Exit Node advertises default Internet routes. Subnet Routes expose specific private prefixes. Neither is required merely to reach the Comet’s own Tailscale address / MagicDNS name.

GL.iNet documents Exit Node and Subnet Routes as supported features. Community experience still cautions that **RM10 should not be treated like a general two-interface GL.iNet router** (especially Wi-Fi-as-WAN / Ethernet-as-LAN patterns). Prefer wired Ethernet to the Comet; validate any subnet-route behavior and reboot persistence before relying on it for break-glass.

If Subnet Routes are enabled later: advertise an **explicit OOB CIDR** (or specific `/32` management addresses), not `auto` discovery of every attached IPv4 subnet from eth/wlan/wwan. Prefer `accept_routes` / `accept_dns` off unless deliberately required.

Three control layers:

1. **Tailnet identity** — who may reach the Comet host/ports  
2. **GLKVM authentication** — application token / login (`Token` header preferred)  
3. **BIOS sidecar / orchestrator** — stateful BIOS ops with blocklists and visual verification (not an approval-token / policy-engine gate; see `docs/decisions.md` D11)

Tailscale encrypts transport; it does **not** replace GLKVM auth.

### ACL / tagging sketch (judgment)

Rename appliances by physical target (`oob-pve01`, `oob-pve02`, …). Tag Comets as something like `tag:oob-kvm` (service identity; check key expiry after tagging). Restrict grants from `group:oob-admins` / orchestrator tags to `tag:oob-kvm` on the browser/API ports (e.g. tcp:80, tcp:443, icmp) — **not** ssh unless intentionally exposing appliance shell. Optional separate `tag:oob-router` for a dedicated subnet router into the OOB VLAN.

Exact Tailscale policy JSON is environment-specific; keep it in the tailnet admin console / IaC, not as a claimed API fact.

---

## 3. Network placement / OOB VLAN sketch

Do not place the Comet as just another workload-plane peer on the cluster VLAN if you can avoid it.

Preferred sketch:

- Dedicated **OOB management VLAN** for Comets, switch/UPS/router management, future IPMI, and (optionally) a dedicated Tailscale subnet router.
- Comet on **wired Ethernet**, powered by its **own adapter** on UPS-backed infrastructure so it stays up when the Proxmox node is off.
- Pattern: Comet = direct tailnet endpoint; dedicated OOB subnet router (if any) exposes the OOB VLAN; Proxmox uses its normal management/Tailscale path for routine work.

---

## 4. Recovery escalation ladder

1. Check Proxmox API and SSH.  
2. Try Wake-on-LAN (`/api/wol/*`).  
3. Open Comet console — screenshot / OCR / classify screen.  
4. Send normal ACPI power press or keyboard command (`/api/atx/click`, HID).  
5. Issue hardware reset (`reset_hard` / Redfish `ForceRestart`).  
6. Forced power-off (`off_hard` / Redfish `ForceOff`) **last**.

ATX board is the highest-value add-on for fixed Proxmox nodes. Fingerbot is a physical-button fallback when ATX headers are unavailable.

---

## 5. Provisioning factory (MSD + ATX + answer.toml)

RM10-class internal storage can hold multiple installer/rescue images (reviewers often cite ~25–29 GB usable; confirm on device via MSD/storage state).

Proxmox automated installer can embed `answer.toml` in an ISO or fetch answers over HTTP. Sketch:

```text
Build customized Proxmox ISO
        ↓
Upload / write_remote to Comet MSD
        ↓
set_params (cdrom) + set_connected
        ↓
ATX reset / boot-menu navigation via HID
        ↓
Automated install
        ↓
Post-install / cluster enrollment
        ↓
Unmount MSD + restore normal boot
```

Keep two variants for disaster recovery:

- **Offline installer** — host-specific `answer.toml` embedded in the ISO (works when DNS/DHCP beyond the local segment or the rest of the cluster is down).  
- **Dynamic installer** — one ISO calling an answer service keyed by MAC / hardware identity.

Contract details: [`glkvm-api-surface.md`](glkvm-api-surface.md) MSD + ATX sections.

---

## 6. External watchdog / screen classification

Host MCP OCR (`kvm_ocr_*` over `/api/streamer/snapshot`) plus HID enables an **external** watchdog (must not run on the cluster it monitors):

1. Detect Proxmox unresponsive.  
2. Capture Comet screenshot.  
3. Classify: no signal / BIOS / GRUB / panic / installer / login.  
4. Extract error text.  
5. Notify with screenshot + proposed remediation.  
6. Auto-continue safe actions; require approval at irreversible boundaries.

Deploy on a small management host, independent NAS, router-class appliance, or external service.

---

## 7. Agent permission model

Preserve the repo architecture: `bios.*` stateful primary interface; `comet.raw.*` / low-level transport for debug; sidecar owns retries, timing, verification, audit. Do not hand raw HID freely to a general-purpose agent without policy.

### Autonomous (broad recovery authority)

- Read every state endpoint; screenshots and OCR.  
- Keyboard/mouse for navigation on known screens.  
- Stream parameter tweaks.  
- Wake-on-LAN.  
- Mount/unmount/upload/delete **approved** ISO images.  
- Start/stop recordings; collect logs/metrics.  
- Graceful shutdown and power-on.  
- Hard reset / hard-off **after objective recovery predicates** (e.g. API+SSH unreachable for configured interval **and** screen shows hang/panic/stalled boot).  
- BIOS setting changes covered by an **approved policy**.

### Confirm-only (explicit human/orchestrator approval)

- Format Comet media partition.  
- Start firmware upgrade.  
- Factory reset.  
- Change Tailscale account or advertised routes.  
- Reprogram EDID.  
- Install OS onto non-disposable disks outside an active maintenance/rebuild workflow.  
- Mutating GETs and other footguns — never raw-exposed to crawlers.

Native API appears to lack route-level RBAC beyond auth-required flags. The sidecar must provide action-level authorization and normalize poor semantics (mutating GETs).

---

## 8. Firmware discipline

- Stay on GL.iNet **stable** firmware as the tested integration unit.  
- Avoid independently replacing the bundled Tailscale binary without a recovery image ready (prior RM1 Tailscale update breakage is a cautionary tale; RM10 is a different platform but the discipline still applies).  
- Prefer capability discovery over pinning client behavior to a single firmware label.  
- Ops vision may *observe* public source tags for research; clients should still discover at runtime.

---

## 9. Phases 1–4 (implement-next)

### Phase 1 — Reliable break-glass

- Rename appliance (`oob-pve01`).  
- Assign `tag:oob-kvm`; restrict to admin group.  
- Exit Node and Subnet Routes off.  
- Wired Ethernet + independent UPS-backed power.  
- Leave public GLKVM cloud unbound unless needed.

### Phase 2 — Physical control

- Install ATX board on fixed Proxmox nodes.  
- Configure WOL.  
- Test short press, reset, forced-off **while physically present**.  
- Document motherboard/BIOS responses.

### Phase 3 — Automated provisioning

- Automated Proxmox ISO + `answer.toml`.  
- Store installer, SystemRescue, memory diagnostics, firmware media on Comet.  
- Reproducible “reinstall node” runbook.

### Phase 4 — Agentic recovery

```text
Proxmox health probe
       ↓
Comet screenshot + OCR
       ↓
State classification
       ↓
bios.* recovery plan
       ↓
Automatic safe actions
       ↓
Approval at destructive boundary
       ↓
ATX / HID / virtual-media execution
       ↓
Verify Proxmox API recovery
       ↓
Audit record
```

Human break-glass remains the Comet web UI. Sidecar is the programmable path. Raw HID stays available under debug namespaces.

---

## 10. Fleet / GLKVM Cloud (optional)

GL.iNet’s self-hosted GLKVM Cloud (device groups, user groups, batch commands, web SSH, OIDC/LDAP) becomes relevant with several Comets or delegated access. Keep Tailscale as the network access layer. Host any fleet portal **behind the tailnet**, not on the cluster it is supposed to recover.

---

## 11. Multi-target open questions

- Process-global singleton vs `targets: dict[str, TargetRuntime]` registry.  
- Optional `target=` on MCP tools vs selected-default target.  
- Per-target capability profiles, BIOS graphs, and secrets remaining external to profiles.  
- Concurrent sessions without disconnecting the previous host.  
- Naming alignment with MagicDNS (`oob-pve01`) vs LAN IPs.

These are open design questions for a later `decisions.md` entry — not decided here.

---

## 12. Map to this repo

| Today | Future OOB (this vision) |
|-------|---------------------------|
| `kvm_core` transport + screenshot/OCR + HID | Same, with correct ATX/MSD/WS contracts (see audit snapshot) |
| `bios_sidecar` cartography / visually verified BIOS | Phase 4 agentic recovery consumer |
| Docs: reference API + hardware | Track A facts already separated |
| NORTH_STAR / architecture / VLM contract | Unchanged by this note — relationship only |

What would need a later **`decisions.md` promotion** before becoming authority:

- Multi-target registry shape  
- Agent permission matrix as binding policy  
- OOB VLAN / Tailscale topology as the endorsed deployment  
- Virtual-media provisioning as a first-class product goal  
- Watchdog hosting model  

Until then: BIOS sidecar architecture stays in [`docs/architecture.md`](../architecture.md) / [`docs/kvm-core.md`](../kvm-core.md) / skills — summarize relationship here; do not fork a second architecture. VLM / cartography design stays in `docs/architecture.md` and `docs/vlm-prompt-contract.md`; board adapters and MSI procedure stay in the BIOS skill.
