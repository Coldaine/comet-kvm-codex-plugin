from __future__ import annotations
import logging
from typing import Optional
from src.bios_sidecar.comet.client import CometClient

LOG = logging.getLogger("bios_sidecar.comet.session")

class SessionManager:
    def __init__(self):
        self._active_client: Optional[CometClient] = None

    async def establish_session(
        self, host: str, username: str = "admin", password: str = "", verify_ssl: bool = False
    ) -> CometClient:
        if self._active_client is not None:
            await self.close_session()

        client = CometClient(host=host, username=username, password=password, verify_ssl=verify_ssl)
        await client.connect()
        self._active_client = client
        return client

    async def close_session(self):
        if self._active_client is not None:
            await self._active_client.disconnect()
            self._active_client = None

    def get_active_client(self) -> CometClient:
        if self._active_client is None:
            raise RuntimeError("No active session. Call establish_session first.")
        return self._active_client

    def has_active_session(self) -> bool:
        return self._active_client is not None and self._active_client.is_connected()
