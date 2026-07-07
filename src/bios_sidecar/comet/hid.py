from __future__ import annotations
import logging
from src.bios_sidecar.comet.client import CometClient

LOG = logging.getLogger("bios_sidecar.comet.hid")

class HIDController:
    def __init__(self, client: CometClient):
        self.client = client

    async def press_up(self):
        await self.client.send_combo("ArrowUp")

    async def press_down(self):
        await self.client.send_combo("ArrowDown")

    async def press_left(self):
        await self.client.send_combo("ArrowLeft")

    async def press_right(self):
        await self.client.send_combo("ArrowRight")

    async def press_enter(self):
        await self.client.send_combo("Enter")

    async def press_esc(self):
        await self.client.send_combo("Escape")

    async def press_f10(self):
        await self.client.send_combo("F10")

    async def press_f7(self):
        await self.client.send_combo("F7")

    async def send_text(self, text: str):
        await self.client.send_text(text)

    async def release_all(self):
        await self.client.release_all()
