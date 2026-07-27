# Visible-Console Commands

Read this file only when the machine exposes a shell through pixels and an exact
transport such as SSH, serial console, or the Proxmox API is unavailable.

Establish the visible prompt and baseline with `kvm_screenshot` plus
`kvm_ocr_text`. Confirm the intended target, focus, shell, and command before
calling `kvm_send_text(text=...)`. Before submitting, re-capture the command
line and OCR it to confirm the typed text matches the intended command —
mandatory when the command is destructive or has a similar-looking dangerous
variant. If the visible text does not match, clear the line and retype instead
of submitting. Only then send `kvm_send_keys(combo="Enter")`, and re-read the
relevant screen region until output stops changing or a bounded timeout is
reached.

Use short commands and bounded output. When shell quoting is known, append a
visible completion marker and exit code. Do not invent an exit status when no
marker was observed.

Pixel OCR cannot guarantee bytes that scrolled off screen, stdout versus stderr,
complete whitespace, an undisplayed exit status, or output that changed faster
than capture. Do not describe OCR as exact SSH output.

Avoid entering secrets through the visible console when a safer credential path
exists. Switch to an exact transport when one becomes available. Report the
visible command, observed output, completion evidence, and uncertainty.
