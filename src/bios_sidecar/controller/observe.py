from __future__ import annotations
import asyncio
import datetime
import logging
from dataclasses import replace
from typing import Optional
from src.bios_sidecar.domain.models import BiosState, StateNode, ConfidenceMetrics
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

    def _reuse_page_identity(
        self,
        matched_node: StateNode,
        live_state: BiosState,
        match_confidence: float,
    ) -> BiosState:
        """Reuse only stable page identity from the graph; keep live interaction fields."""
        rep_id = matched_node.representative_state_id
        if not rep_id:
            return replace(
                live_state,
                confidence=ConfidenceMetrics(
                    ocr=live_state.confidence.ocr,
                    vlm=live_state.confidence.vlm,
                    state=match_confidence,
                ),
            )
        representative = self.store.get_bios_state(rep_id)
        if representative is None:
            return live_state

        # Page identity from representative path/title hints; bios + live interaction stay live.
        return replace(
            live_state,
            location=replace(
                live_state.location,
                top_module=representative.location.top_module or live_state.location.top_module,
                breadcrumb=list(representative.location.breadcrumb or live_state.location.breadcrumb),
                screen_title=live_state.location.screen_title or representative.location.screen_title,
                screen_kind=live_state.location.screen_kind,
            ),
            confidence=ConfidenceMetrics(
                ocr=live_state.confidence.ocr,
                vlm=live_state.confidence.vlm,
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
        Capture screenshot + OCR, match page identity from the graph, and always
        re-extract live interaction state (selection/controls/modal) via VLM.
        """
        # 1. Capture screenshot and cache it
        img_bytes, screenshot_id, file_path = await self.capture_mgr.capture_frame(client, preview=False)
        sha = calculate_sha256(img_bytes)
        phash = calculate_visual_phash(img_bytes)

        # 2. Run local OCR (primary text source; VLM grounds live interaction)
        ocr_res = await asyncio.to_thread(self.ocr_mgr.run_ocr, img_bytes)
        ocr_h = calculate_ocr_hash(ocr_res.get("elements", []))
        ocr_conf = sum(e["confidence"] for e in ocr_res.get("elements", [])) / max(1, len(ocr_res.get("elements", []))) if ocr_res.get("elements") else 90.0
        ocr_confidence = ocr_conf / 100.0
        resolution = [ocr_res.get("width", 1920), ocr_res.get("height", 1080)]
        now_str = datetime.datetime.now().isoformat()

        # 3. Graph match for page identity only (never reuse live selection/values/modal)
        matched_node, match_confidence = self.syncer.matcher.match_state(
            phash, ocr_h, semantic_hash=""
        )

        # 4. Always extract live interaction state from the current frame
        prev_dict = previous_state.to_dict() if previous_state else None
        vlm_res = await self.vlm_client.parse_screenshot(
            img_bytes,
            previous_state=prev_dict,
            last_action=last_action,
        )
        
        from src.bios_sidecar.adapters.msi_click_bios import MsiClickBiosAdapter
        
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
            adapter=MsiClickBiosAdapter()
        )

        if matched_node and match_confidence >= _MATCH_CONFIDENCE_MIN:
            LOG.info(
                "Page identity match node %s (confidence=%.2f); live fields re-extracted",
                matched_node.node_id,
                match_confidence,
            )
            state = self._reuse_page_identity(matched_node, state, match_confidence)

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
