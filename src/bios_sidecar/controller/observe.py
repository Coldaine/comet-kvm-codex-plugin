from __future__ import annotations
import asyncio
import datetime
import logging
import uuid
from dataclasses import replace
from typing import Optional
from src.bios_sidecar.domain.models import BiosState, StateNode, FrameMetadata, ConfidenceMetrics
from src.kvm_core.comet.client import CometClient
from src.kvm_core.comet.capture import CaptureManager
from src.kvm_core.ocr import OCRManager
from src.bios_sidecar.perception.vlm_client import VLMClient
from src.bios_sidecar.perception.normalize import normalize_bios_state
from src.bios_sidecar.state.hashing import calculate_sha256, calculate_visual_phash, calculate_ocr_hash, calculate_state_semantic_hash
from src.bios_sidecar.state.sync import StateSyncer
from src.bios_sidecar.state.store import SQLiteStore

LOG = logging.getLogger("bios_sidecar.controller.observe")

# Align with StateSyncer.verify_and_align confidence gate.
_MATCH_CONFIDENCE_MIN = 0.75


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

    def _reuse_matched_state(
        self,
        matched_node: StateNode,
        match_confidence: float,
        *,
        run_id: str,
        device_id: str,
        screenshot_id: str,
        sha: str,
        phash: str,
        resolution: list,
        captured_at: str,
        ocr_confidence: float,
    ) -> Optional[BiosState]:
        """Clone representative BiosState with the live frame; skip VLM when possible."""
        rep_id = matched_node.representative_state_id
        if not rep_id:
            return None
        representative = self.store.get_bios_state(rep_id)
        if representative is None:
            LOG.info(
                "Matched node %s but representative state %s missing; falling back to VLM",
                matched_node.node_id,
                rep_id,
            )
            return None

        return replace(
            representative,
            state_id="state_" + uuid.uuid4().hex[:12],
            run_id=run_id,
            device_id=device_id,
            frame=FrameMetadata(
                screenshot_id=screenshot_id,
                sha256=sha,
                perceptual_hash=phash,
                resolution=resolution,
                captured_at=captured_at,
            ),
            confidence=ConfidenceMetrics(
                ocr=ocr_confidence,
                vlm=0.0,  # skipped — graph match reused prior grounding
                state=match_confidence,
            ),
        )

    async def observe_state(
        self,
        client: CometClient,
        run_id: str,
        device_id: str,
        previous_state: Optional[BiosState] = None,
        last_action: Optional[str] = None
    ) -> BiosState:
        """
        Capture screenshot + OCR, match the graph first (D7), and call VLM only
        when grounding a previously unseen screen.
        """
        # 1. Capture screenshot and cache it
        img_bytes, screenshot_id, file_path = await self.capture_mgr.capture_frame(client, preview=False)
        sha = calculate_sha256(img_bytes)
        phash = calculate_visual_phash(img_bytes)

        # 2. Run local OCR (primary text source; VLM is grounding-only)
        ocr_res = await asyncio.to_thread(self.ocr_mgr.run_ocr, img_bytes)
        ocr_h = calculate_ocr_hash(ocr_res.get("elements", []))
        ocr_conf = sum(e["confidence"] for e in ocr_res.get("elements", [])) / max(1, len(ocr_res.get("elements", []))) if ocr_res.get("elements") else 90.0
        ocr_confidence = ocr_conf / 100.0
        resolution = [ocr_res.get("width", 1920), ocr_res.get("height", 1080)]
        now_str = datetime.datetime.now().isoformat()

        # 3. Graph match BEFORE VLM (phash + OCR fingerprint; semantic left empty
        #    until we have structured fields from a prior grounded state).
        matched_node, match_confidence = self.syncer.matcher.match_state(
            phash, ocr_h, semantic_hash=""
        )
        state: Optional[BiosState] = None
        if matched_node and match_confidence >= _MATCH_CONFIDENCE_MIN:
            state = self._reuse_matched_state(
                matched_node,
                match_confidence,
                run_id=run_id,
                device_id=device_id,
                screenshot_id=screenshot_id,
                sha=sha,
                phash=phash,
                resolution=resolution,
                captured_at=now_str,
                ocr_confidence=ocr_confidence,
            )
            if state is not None:
                LOG.info(
                    "OCR-first match hit node %s (confidence=%.2f); skipping VLM",
                    matched_node.node_id,
                    match_confidence,
                )

        # 4. Unmatched (or missing representative): VLM ground, then normalize
        if state is None:
            prev_dict = previous_state.to_dict() if previous_state else None
            vlm_res = await self.vlm_client.parse_screenshot(
                img_bytes,
                previous_state=prev_dict,
                last_action=last_action,
            )
            state = normalize_bios_state(
                run_id=run_id,
                device_id=device_id,
                vlm_data=vlm_res,
                screenshot_id=screenshot_id,
                sha256=sha,
                perceptual_hash=phash,
                resolution=resolution,
                captured_at=now_str,
                ocr_confidence=ocr_confidence,
            )

        # 5. Persist live observation
        self.store.save_bios_state(state)

        # 6. Re-align state syncer with map
        aligned, matched_node_id = self.syncer.verify_and_align(state)

        # 7. Auto-register newly grounded screens
        if not aligned:
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
