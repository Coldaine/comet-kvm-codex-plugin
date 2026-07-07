from __future__ import annotations
import asyncio
import logging
from src.bios_sidecar.comet.client import CometClient
from src.bios_sidecar.state.hashing import calculate_visual_phash

LOG = logging.getLogger("bios_sidecar.controller.settle")

class ScreenSettler:
    def __init__(self, check_interval_s: float = 0.1, max_wait_s: float = 2.0):
        self.check_interval_s = check_interval_s
        self.max_wait_s = max_wait_s

    async def wait_for_settle(self, client: CometClient) -> bytes:
        """
        Polls the frame stream until two consecutive frame captures yield
        the identical perceptual hash, indicating visual settle.
        """
        start = asyncio.get_event_loop().time()
        last_hash = ""
        last_data = b""

        while (asyncio.get_event_loop().time() - start) < self.max_wait_s:
            try:
                data = await client.get_screenshot(preview=True, max_width=640, quality=50)
                h = calculate_visual_phash(data)

                if last_hash and h == last_hash:
                    # Settled! Now fetch a full high-fidelity snapshot
                    LOG.info("Screen settled in %.2f seconds", asyncio.get_event_loop().time() - start)
                    return await client.get_screenshot(preview=False)

                last_hash = h
                last_data = data
            except Exception as e:
                LOG.warning("Failed capture step in settle loop: %s", e)

            await asyncio.sleep(self.check_interval_s)

        LOG.warning("Screen did not settle within budget; returning last frame.")
        # If timeout, try to get a high quality frame anyway and return
        try:
            return await client.get_screenshot(preview=False)
        except Exception:
            return last_data

    async def wait_fixed(self, duration_s: float = 0.5):
        """Simpler fixed sleep helper."""
        await asyncio.sleep(duration_s)
