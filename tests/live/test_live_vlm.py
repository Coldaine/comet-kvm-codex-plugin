from __future__ import annotations

import asyncio
import io
import os

import pytest
from PIL import Image, ImageDraw

from src.bios_sidecar.perception.models import BiosScreenParse

# Live VLM access is opt-in. Collection skips before credential or network
# access unless RUN_LIVE_VLM_SMOKE=1 is set by an operator or the manual workflow.
_FORCE = os.environ.get("RUN_LIVE_VLM_SMOKE")

if _FORCE != "1":
    pytest.skip(
        "live VLM checks require explicit RUN_LIVE_VLM_SMOKE=1",
        allow_module_level=True,
    )


def resolve_live_vlm_api_key() -> str | None:
    """Prefer VLM_API_KEY env, then Doppler's OPENROUTER_API_KEY secret."""
    env_key = (os.environ.get("VLM_API_KEY") or "").strip()
    if env_key:
        return env_key
    try:
        from src.kvm_core.doppler_credentials import resolve_vlm_api_key

        return resolve_vlm_api_key(require=False)
    except Exception:
        # Doppler CLI missing/unauthenticated is not a fatal condition here —
        # it just means no key is available from that fallback.
        return None


def _render_synthetic_bios_screen() -> bytes:
    """Render a synthetic BIOS-style Advanced settings screen as JPEG bytes."""
    width, height = 1280, 800
    background = (12, 20, 48)  # dark navy
    highlight = (70, 90, 140)  # lighter inverse row
    foreground = (230, 235, 245)

    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)

    # Header title
    draw.text((40, 30), "Advanced", fill=foreground)
    draw.line([(40, 70), (width - 40, 70)], fill=foreground, width=2)

    entries = [
        "PCI Subsystem Settings",
        "ACPI Settings",
        "Re-Size BAR Support   [Auto]",
        "Above 4G Decoding   [Enabled]",
        "USB Configuration",
        "Trusted Computing",
    ]
    selected_index = 2
    row_height = 60
    top = 120
    for i, entry in enumerate(entries):
        y0 = top + i * row_height
        y1 = y0 + row_height - 10
        if i == selected_index:
            draw.rectangle([(40, y0), (width - 40, y1)], fill=highlight)
        draw.text((60, y0 + 18), entry, fill=foreground)

    # Footer hotkey legend
    footer_y = top + len(entries) * row_height + 40
    draw.line([(40, footer_y), (width - 40, footer_y)], fill=foreground, width=2)
    draw.text(
        (40, footer_y + 20),
        "F10: Save & Exit    ESC: Exit    Enter: Select",
        fill=foreground,
    )

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_openrouter_free_parses_synthetic_bios_screen():
    """Drive the real OpenRouter Free Models Router against a synthetic screen.

    Tolerant of free-model variance: only checks that the response validates
    against the v2 contract, entries are non-empty, and at least some text
    (title or a label) came back. Exact labels/values are not asserted.
    """
    key = resolve_live_vlm_api_key()
    if not key:
        pytest.skip("no VLM_API_KEY and no OPENROUTER_API_KEY in Doppler")

    from src.bios_sidecar.perception.vlm_client import VLMClient

    image_bytes = _render_synthetic_bios_screen()

    async def run() -> dict:
        client = VLMClient(provider="openrouter", api_key=key)
        try:
            return await client.parse_screenshot(image_bytes)
        finally:
            await client.close()

    result = asyncio.run(asyncio.wait_for(run(), timeout=60.0))

    parsed = BiosScreenParse.model_validate(result)
    assert parsed.entries, "expected at least one parsed entry"
    any_label = any((entry.label or "").strip() for entry in parsed.entries)
    assert (parsed.screen_title or "").strip() or any_label, (
        "expected a non-empty screen title or at least one non-empty entry label"
    )

    print(
        f"LIVE-VLM entries={len(parsed.entries)} "
        f"title={parsed.screen_title!r} confidence={parsed.confidence}"
    )
