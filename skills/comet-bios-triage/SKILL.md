---
name: comet-bios-triage
description: Use when operating a GL.iNet Comet/GLKVM through MCP for BIOS, pre-OS, recovery, or visible console workflows, especially MSI Z690 CPU power/voltage tuning followed by Windows HWiNFO logging and analysis. Triggers include Comet KVM, GLKVM, BIOS driving, UEFI navigation, console OCR, CPU Lite Load, MSI Z690, HWiNFO thermal triage, and KVM-assisted undervolt testing.
---

# Comet BIOS Triage

Use the Comet MCP tools as hands and eyes, not as a blind macro engine.

Before changing BIOS settings, verify your context:
- Ensure the stateful KVM tools are connected
- Consult the embedded reference guides on MSI Z690 workflows and HWiNFO run loops

Rules:

- Never use blind key sequences for BIOS changes.
- Always capture a screenshot before and after each setting change.
- Change exactly one BIOS variable per run.
- Confirm the visible old value and new value before saving.
- Run `kvm_release_all` after any failed or interrupted input sequence.
- Do not continue after WHEA errors, crashes, score collapse, severe throttling, or clock-stretching.
- Use the run ledger for every experiment.

## Choose the cheapest reliable perception tool

Before depending on text reads, call `kvm_ocr_status()`. It reports whether host Tesseract is callable by the MCP and identifies the GL.iNet product UI's browser-only Tesseract.js engine so the two paths are not confused.

Use this order:

1. **Visible terminal, shell, POST text, or recovery text:** call `kvm_ocr_text()`. It captures one frame and runs host Tesseract. Default `psm=6` and `preserve_interword_spaces=1` suit terminal text. Supply pixel crop coordinates when the terminal occupies only part of the screen.
2. **Text coordinates or confidence are required:** call `kvm_ocr_screenshot(...)`. It uses host pytesseract word boxes.
3. **Click a visible label:** call `kvm_ocr_click(...)`. Treat an OCR error as a failed action; do not convert it into "text not found."
4. **Layout, icons, BIOS semantics, or ambiguous OCR:** call `kvm_screenshot()` or the semantic `bios_*` observation tools. OCR is a text extractor, not a substitute for visual state verification.

Do not call the inherited `/api/streamer/ocr` route and describe it as GL.iNet
Text Recognition. Firmware 1.9's product UI crops its browser canvas and runs
Tesseract.js/WASM in the controlling browser. This MCP cannot reuse that worker;
its OCR tools require host Tesseract.

Do not call the Comet HTTP OCR endpoint directly. The MCP tools probe capability, normalize the GL.iNet JSON response, apply native crop/language parameters, and handle the verified host fallback.

Do not assume native OCR status for any device or after a firmware change; use `kvm_ocr_status()`.

## Visible console command loop

For a command line reached through pixels rather than a real SSH transport:

1. `kvm_ocr_text()` to capture the prompt/baseline.
2. `kvm_send_text(command)`.
3. `kvm_send_keys("Enter")`.
4. `kvm_ocr_text()` to receive visible output directly as `text` and `lines` in the tool result.
5. Read again only while output is visibly changing; use a crop to reduce latency and noise.

This path cannot guarantee bytes that scrolled off the HDMI viewport or an exact exit status. Do not describe OCR as SSH stdout. If an approved exact target-shell transport exists, prefer it for ordinary network-reachable Linux command execution and reserve KVM OCR for BIOS, recovery, network-down, or otherwise pixel-only states.
