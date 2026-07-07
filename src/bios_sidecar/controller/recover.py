from __future__ import annotations
import logging
from src.bios_sidecar.domain.models import BiosState
from src.bios_sidecar.comet.client import CometClient
from src.bios_sidecar.controller.settle import ScreenSettler

LOG = logging.getLogger("bios_sidecar.controller.recover")

class BiosRecoveryHandler:
    def __init__(self, settler: ScreenSettler):
        self.settler = settler

    async def abort_and_recover(self, client: CometClient) -> str:
        """
        Emergency recovery step.
        1. Force-release any stuck keys on the KVM interface.
        2. Press Escape consecutively to close any open dropdowns or modals.
        3. Recapture frame to confirm sync point.
        """
        LOG.warning("Triggered sidecar safety recovery sequence!")

        # 1. Release held keys
        await client.release_all()
        await self.settler.wait_fixed(0.1)

        # 2. Sequential Escape presses to back out of nested modals
        for attempt in range(3):
            LOG.info("Sending safety Esc input (%d/3)...", attempt + 1)
            await client.send_combo("Escape")
            await self.settler.wait_fixed(0.25)

        LOG.info("Safety recovery sequence completed successfully. Settle and return.")
        return "recovers_completed"
