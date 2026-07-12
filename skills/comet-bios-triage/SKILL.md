---
name: comet-bios-triage
description: Use when operating a GL.iNet Comet/GLKVM through MCP for BIOS, pre-OS, recovery, or visible console workflows, especially MSI Z690 CPU power/voltage tuning followed by Windows HWiNFO logging and analysis. Triggers include Comet KVM, GLKVM, BIOS driving, UEFI navigation, console OCR, CPU Lite Load, MSI Z690, HWiNFO thermal triage, and KVM-assisted undervolt testing.
---

# Comet BIOS Triage

Use the Comet MCP tools as hands and eyes, not as a blind macro engine.

Before changing BIOS settings, read:

- `../../docs/architecture.md` — current BIOS cartography and state-engine design
- `../../docs/vlm-prompt-contract.md` — current VLM perception contract
- `../../docs/plans/01-vlm-mcp-integration-plan.md` — VLM-MCP boundary integration plan
- `references/stateful-control-model.md`
- `references/msi-z690-bios-workflow.md`
- `references/hwinfo-run-loop.md`

Rules:

- Never use blind key sequences for BIOS changes.
- Always capture a screenshot before and after each setting change.
- Change exactly one BIOS variable per run.
- Confirm the visible old value and new value before saving.
- Run `kvm_release_all` after any failed or interrupted input sequence.
- Do not continue after WHEA errors, crashes, score collapse, severe throttling, or clock-stretching.
- Use the run ledger for every experiment.

## Choose the cheapest reliable perception tool

After `kvm_connect(host)`, call `kvm_ocr_status()` once per connection or after a firmware/configuration change. It reports both the Comet's native OCR state and host Tesseract availability, refreshes the device capability cache, and lets later text reads reuse that result.

Use this order:

1. **Visible terminal, shell, POST text, or recovery text:** call `kvm_ocr_text()`. It automatically prefers the Comet/PiKVM native OCR endpoint when the device reports it enabled, and otherwise captures one frame and falls back to host Tesseract. On the host fallback, default `psm=6` and `preserve_interword_spaces=1` suit terminal text; the native endpoint controls its own segmentation and does not expose PSM. Supply pixel crop coordinates when the terminal occupies only part of the screen.
2. **Text coordinates or confidence are required:** call `kvm_ocr_screenshot(...)`. This deliberately uses host pytesseract word boxes; native Comet OCR returns text but not click coordinates.
3. **Click a visible label:** call `kvm_ocr_click(...)`. Treat an OCR error as a failed action; do not convert it into "text not found."
4. **Layout, icons, BIOS semantics, or ambiguous OCR:** call `kvm_screenshot()` or the semantic `bios_*` observation tools. OCR is a text extractor, not a substitute for visual state verification.

Do not call the Comet HTTP OCR endpoint directly. The MCP tools probe capability, normalize the GL.iNet JSON response, apply native crop/language parameters, and handle the verified host fallback.

The live Comet at `192.168.0.126` reported native OCR disabled on 2026-07-10, so `kvm_ocr_text()` currently selects host Tesseract there. Do not assume that status for another device or after a firmware change; use `kvm_ocr_status()`.

## Visible console command loop

For a command line reached through pixels rather than a real SSH transport:

1. `kvm_ocr_text()` to capture the prompt/baseline.
2. `kvm_send_text(command)`.
3. `kvm_send_keys("Enter")`.
4. `kvm_ocr_text()` to receive visible output directly as `text` and `lines` in the tool result.
5. Read again only while output is visibly changing; use a crop to reduce latency and noise.

This path cannot guarantee bytes that scrolled off the HDMI viewport or an exact exit status. Do not describe OCR as SSH stdout. If an approved exact target-shell transport exists, prefer it for ordinary network-reachable Linux command execution and reserve KVM OCR for BIOS, recovery, network-down, or otherwise pixel-only states.
