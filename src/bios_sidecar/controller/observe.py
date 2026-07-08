from __future__ import annotations
import asyncio
import datetime
import logging
import hashlib
from typing import Optional, Dict, Any
from src.bios_sidecar.domain.models import BiosState, StateNode
from src.bios_sidecar.comet.client import CometClient
from src.bios_sidecar.comet.capture import CaptureManager
from src.bios_sidecar.perception.ocr import OCRManager
from src.bios_sidecar.perception.vlm_client import VLMClient
from src.bios_sidecar.perception.normalize import normalize_bios_state
from src.bios_sidecar.state.hashing import calculate_sha256, calculate_visual_phash, calculate_ocr_hash, calculate_state_semantic_hash
from src.bios_sidecar.state.sync import StateSyncer
from src.bios_sidecar.state.store import SQLiteStore

LOG = logging.getLogger("bios_sidecar.controller.observe")

class StateObserver:
    def __init__(
        self,
        capture_mgr: CaptureManager,
        ocr_mgr: OCRManager,
        vlm_client: VLMClient,
        syncer: StateSyncer,
        store: SQLiteStore
    ):
        self.capture_mgr = capture_mgr
        self.ocr_mgr = ocr_mgr
        self.vlm_client = vlm_client
        self.syncer = syncer
        self.store = store

    async def observe_state(
        self,
        client: CometClient,
        run_id: str,
        device_id: str,
        previous_state: Optional[BiosState] = None,
        last_action: Optional[str] = None
    ) -> BiosState:
        """
        Captures screenshot, runs Tesseract OCR, feeds structured image + OCR annotations to VLM,
        normalizes the output into a structured BiosState record, indexes findings and persists details.
        """
        # 1. Capture screenshot and cache it
        img_bytes, screenshot_id, file_path = await self.capture_mgr.capture_frame(client, preview=False)
        sha = calculate_sha256(img_bytes)
        phash = calculate_visual_phash(img_bytes)

        # 2. Run local OCR
        ocr_res = self.ocr_mgr.run_ocr(img_bytes)
        ocr_h = calculate_ocr_hash(ocr_res.get("elements", []))
        ocr_conf = sum(e["confidence"] for e in ocr_res.get("elements", [])) / max(1, len(ocr_res.get("elements", []))) if ocr_res.get("elements") else 90.0

        # 3. Call VLM perception client (with OCR context & previous state hint)
        prev_dict = previous_state.to_dict() if previous_state else None
        vlm_res = await self.vlm_client.parse_screenshot(
            img_bytes,
            previous_state=prev_dict,
            last_action=last_action,
        )

        # 4. Normalize raw outputs to canonical BiosState
        now_str = datetime.datetime.now().isoformat()
        state = normalize_bios_state(
            run_id=run_id,
            device_id=device_id,
            vlm_data=vlm_res,
            screenshot_id=screenshot_id,
            sha256=sha,
            perceptual_hash=phash,
            resolution=[ocr_res.get("width", 1920), ocr_res.get("height", 1080)],
            captured_at=now_str,
            ocr_confidence=ocr_conf / 100.0
        )

        # 5. Persist live raw observations to SQLite
        self.store.save_bios_state(state)

        # 6. Re-align state syncer with map
        aligned, matched_node_id = self.syncer.verify_and_align(state)

        # 7. Auto register on-the-fly discovered nodes
        if not aligned:
            # First time seeing this screen Kind, register as new state graph node
            v = state.bios.vendor
            b = state.bios.board_hint
            t = state.location.screen_title or "unknown"
            p = state.location.breadcrumb
            sem_hash = calculate_state_semantic_hash(v, b, t, p)
            new_node_id = f"node_{sha[:12]}"

            new_node = StateNode(
                node_id=new_node_id,
                visual_hash=phash,
                ocr_hash=ocr_h,
                semantic_hash=sem_hash,
                volatile_regions=["time", "temp", "voltage"],
                representative_state_id=state.state_id
            )
            self.syncer.matcher.graph.add_node(new_node)
            self.syncer.verify_and_align(state)

        return state
