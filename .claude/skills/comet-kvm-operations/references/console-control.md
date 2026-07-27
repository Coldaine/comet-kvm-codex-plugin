# Console Control

Read this file when the task is primarily visual observation or keyboard and
mouse interaction.

## Choose the perception path

Use `kvm_screenshot` for layout, icons, modal state, focus, and other visual
context. Use `kvm_ocr_text` for text-heavy screens such as POST, installers,
recovery prompts, and shells.

Use `kvm_ocr_screenshot` when word coordinates or confidence are required. Use
`kvm_ocr_click` only when the intended label is visible, sufficiently unique,
and appropriate to click in the current screen context.

The MCP OCR path uses host Tesseract. A successful OCR call does not establish
what the screen means; pair text with a screenshot when layout or semantics
matter.

## Send and verify input

Use `kvm_send_keys` for named key operations and `kvm_send_text` for short,
inspectable text. Use `kvm_mouse_move`, `kvm_mouse_move_pct`,
`kvm_mouse_click`, or `kvm_mouse_scroll` only from an observed screen state.

When the destination is uncertain, send one logical action, wait for the display
to settle, and observe before continuing. For read-only requests, do not send
input.

After failed, cancelled, or interrupted input, call `kvm_release_all`, capture
the current screen, determine actual focus and state, and continue from there.
Do not replay the entire prior sequence.

Completion requires the requested visible result, not merely a successful tool
response.
