from __future__ import annotations
import os
import hashlib
import time
import uuid
from typing import Tuple
from src.kvm_core.comet.client import CometClient

class CaptureManager:
    def __init__(self, cache_dir: str = "state/screenshots"):
        self.cache_dir = cache_dir
        self._capture_count = 0
        os.makedirs(cache_dir, exist_ok=True)
        # Enforce D1 30-day TTL on startup so stale screenshots never accumulate.
        self.purge_old_screenshots()

    async def capture_frame(
        self, client: CometClient, preview: bool = False, max_width: int = 1920, quality: int = 80
    ) -> Tuple[bytes, str, str]:
        """
        Captures frame, computes SHA256, and stores in the cache.
        Returns:
            (image_bytes, screenshot_id, file_path)
        """
        data = await client.get_screenshot(preview=preview, max_width=max_width, quality=quality)

        sha = hashlib.sha256(data).hexdigest()
        screenshot_id = f"shot_{sha[:16]}_{time.time_ns()}_{uuid.uuid4().hex[:8]}"

        file_path = os.path.join(self.cache_dir, f"{screenshot_id}.jpg")
        with open(file_path, "wb") as f:
            f.write(data)

        # Enforce D1 TTL every 100 captures to avoid unbounded growth mid-session.
        self._capture_count += 1
        if self._capture_count % 100 == 0:
            self.purge_old_screenshots()

        return data, screenshot_id, file_path

    def purge_old_screenshots(self, max_age_days: int = 30):
        """Purge files older than 30 days according to Decision D1."""
        now = time.time()
        max_age_s = max_age_days * 86400
        for name in os.listdir(self.cache_dir):
            path = os.path.join(self.cache_dir, name)
            if os.path.isfile(path):
                if now - os.path.getmtime(path) > max_age_s:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
