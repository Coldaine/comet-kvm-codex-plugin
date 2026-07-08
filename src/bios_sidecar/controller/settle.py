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
        Polls the frame stream until three consecutive frame captures yield
        the identical perceptual hash, indicating visual settle.

        Enforces a mandatory 150ms pre-delay before beginning comparisons to
        avoid returning the pre-transition frame (which is always static
        immediately after a keypress, before the BIOS re-renders).
        """
        # Mandatory pre-delay: give the BIOS time to begin rendering the next
        # screen before we start comparing hashes.
        await asyncio.sleep(0.15)

        start = asyncio.get_event_loop().time()
        last_hash = ""
        consec_count = 0
        last_data = b""

        while (asyncio.get_event_loop().time() - start) < self.max_wait_s:
            try:
                data = await client.get_screenshot(preview=True, max_width=640, quality=50)
                h = calculate_visual_phash(data)

                if last_hash and h == last_hash:
                    consec_count += 1
                    if consec_count >= 2:  # 3 total polls matched (first match + 2 more)
                        elapsed = asyncio.get_event_loop().time() - start
                        LOG.info(
                            "Screen settled after %d consecutive matches in %.2f seconds",
                            consec_count + 1,
                            elapsed,
                        )
                        return await client.get_screenshot(preview=False)
                else:
                    consec_count = 0

                last_hash = h
                last_data = data
            except Exception as e:
                LOG.warning("Failed capture step in settle loop: %s", e)
                consec_count = 0

            await asyncio.sleep(self.check_interval_s)

        LOG.warning("Screen did not settle within budget; returning last frame.")
        try:
            return await client.get_screenshot(preview=False)
        except Exception:
            return last_data

    async def wait_fixed(self, duration_s: float = 0.5):
        """Simpler fixed sleep helper."""
        await asyncio.sleep(duration_s)
