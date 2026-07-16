from __future__ import annotations
import asyncio
import logging
from typing import Optional, Any, Dict, Tuple
from src.bios_sidecar.domain.models import BiosState
from src.bios_sidecar.domain.enums import ControlRole
from src.bios_sidecar.controller.observe import StateObserver
from src.bios_sidecar.controller.settle import ScreenSettler
from src.kvm_core.comet.client import CometClient

LOG = logging.getLogger("bios_sidecar.controller.mutate")

class BiosMutator:
    def __init__(
        self,
        observer: StateObserver,
        settler: ScreenSettler
    ):
        self.observer = observer
        self.settler = settler

    def _selection_steps(self, options: list[str], current_value: Optional[str], desired_value: str) -> Optional[int]:
        normalized = [str(option).strip().lower() for option in options]
        desired = desired_value.strip().lower()
        current = (current_value or "").strip().lower()
        if desired not in normalized or current not in normalized:
            return None
        return normalized.index(desired) - normalized.index(current)

    async def propose_setting_change(
        self,
        capability_id: str,
        desired_value: str
    ) -> Dict[str, Any]:
        """Plans a mutation without executing it, checking risks."""
        graph = self.observer.syncer.matcher.graph
        from src.bios_sidecar.state.capability_index import CapabilityIndex
        index = CapabilityIndex(graph.store)

        cap = index.resolve_capability_by_handle(capability_id)
        if not cap:
            return {
                "decision": "rejected",
                "reason": f"Capability {capability_id} not indexed.",
                "plan": None
            }

        return {
            "decision": "planned",
            "canonical_name": cap.canonical_name,
            "desired_value": desired_value,
            "risk": cap.risk.value,
            "paths": [p.to_dict() for p in cap.paths]
        }

    async def apply_setting_change(
        self,
        client: CometClient,
        run_id: str,
        device_id: str,
        capability_id: str,
        desired_value: str
    ) -> Tuple[bool, Optional[BiosState], str]:
        """
        Executes a setting change.
        Flow:
            1. Verify cursor is sitting on targeted setting entry.
            2. Open values dialog (Enter).
            3. Send input keys to select desired_value.
            4. Visually capture and verify change in value.
        """
        # Obtain latest state
        state = await self.observer.observe_state(client, run_id, device_id)

        # 2. Check if cursor is on targeting capability setting row
        cursor_ctrl = None
        for ctrl in state.controls:
            if ctrl.selected and ctrl.role == ControlRole.SETTING:
                cursor_ctrl = ctrl
                break

        # Check title similarity
        from src.bios_sidecar.state.capability_index import CapabilityIndex
        idx = CapabilityIndex(self.observer.store)
        cap = idx.resolve_capability_by_handle(capability_id)
        if not cap:
            return False, state, f"Capability {capability_id} is not indexed."

        if not cursor_ctrl or not any(a.lower() == cursor_ctrl.label.lower() for a in cap.aliases):
            label_got = cursor_ctrl.label if cursor_ctrl else "None"
            return False, state, f"Alignment mismatch: Cursor is sitting on row '{label_got}' instead of indexed core setting."

        old_val = cursor_ctrl.value
        LOG.info("Starting mutator execution: shifting %s option %s -> %s", cap.canonical_name, old_val, desired_value)

        if str(old_val).strip().lower() == desired_value.strip().lower():
            return True, state, "Setting already has the desired value."

        options = cursor_ctrl.options or []
        steps = self._selection_steps(options, old_val, desired_value)
        if steps is None:
            return False, state, "Desired value cannot be selected deterministically from observed options."

        # 3. Open dropdown / field (Enter)
        # Press Enter, wait for dropdown modal
        await client.send_combo("Enter")
        await self.settler.wait_for_settle(client)

        LOG.info("Shifting selection by %d option(s)...", steps)
        key = "ArrowDown" if steps > 0 else "ArrowUp"
        for _ in range(abs(steps)):
            await client.send_combo(key)
            await self.settler.wait_for_settle(client)

        await client.send_combo("Enter")
        await self.settler.wait_for_settle(client)

        # 5. Observe post-mutation state to verify alignment change
        post_state = await self.observer.observe_state(client, run_id, device_id)

        post_ctrl = None
        for ctrl in post_state.controls:
            if ctrl.label.lower() == cursor_ctrl.label.lower():
                post_ctrl = ctrl
                break

        final_val = post_ctrl.value if post_ctrl else "Unknown"
        LOG.info("Post setting validation: old value=%s, post value_got=%s", old_val, final_val)

        if str(final_val).strip().lower() != desired_value.strip().lower():
            return False, post_state, f"Post-change verification failed: expected {desired_value!r}, observed {final_val!r}."
        return True, post_state, "Successfully modified setting. Value is confirmed changed visually."

    async def save_and_reboot(
        self,
        client: CometClient,
        run_id: str,
        device_id: str,
        *,
        reboot_observe_seconds: float = 12.0,
    ) -> Tuple[bool, Optional[BiosState], str]:
        """
        Commit staged BIOS changes to NVRAM and reboot.

        Flow:
            1. Observe current page.
            2. Send F10 and require a screen transition into a save/confirm modal.
            3. Confirm with Enter only when modal evidence is present.
            4. Observe reboot evidence (no_signal / POST / boot target).
        """
        from src.bios_sidecar.domain.enums import StateKind

        pre_state = await self.observer.observe_state(client, run_id, device_id)
        pre_title = (pre_state.location.screen_title or "").strip().lower()
        pre_kind = pre_state.location.screen_kind

        await client.send_combo("F10")
        await self.settler.wait_for_settle(client)
        modal_state = await self.observer.observe_state(client, run_id, device_id)

        title = (modal_state.location.screen_title or "").lower()
        modal = modal_state.modal
        modal_present = bool(getattr(modal, "present", False))
        modal_type = (getattr(modal, "type", None) or "").lower()
        modal_message = (getattr(modal, "message", None) or "").lower()
        kind = modal_state.location.screen_kind
        looks_like_save = any(
            kw in f"{title} {modal_type} {modal_message}"
            for kw in ("save", "confirm", "reset", "reboot", "exit")
        ) or kind in {StateKind.SAVE_CHANGES_MODAL, StateKind.CONFIRMATION_MODAL}

        transitioned = (
            (modal_state.location.screen_title or "").strip().lower() != pre_title
            or kind != pre_kind
            or modal_present
        )
        if not transitioned:
            return (
                False,
                modal_state,
                "No screen transition after F10; aborting without confirm.",
            )
        # Fail closed: modal_present alone is not enough (unrelated dialogs).
        if not looks_like_save:
            return (
                False,
                modal_state,
                "Save confirmation dialog not detected after F10; aborting without confirm.",
            )

        selected_action = None
        if getattr(modal, "options", None):
            for option in modal.options:
                low = str(option).lower()
                if any(kw in low for kw in ("save", "yes", "ok", "confirm", "reset")):
                    selected_action = str(option)
                    break
        if selected_action is None:
            selected_action = getattr(modal, "type", None) or "confirm"

        await client.send_combo("Enter")
        await self.settler.wait_for_settle(client)

        reboot_observed = False
        post_detected = False
        final_phase = "unknown"
        final_state = modal_state
        deadline = asyncio.get_event_loop().time() + reboot_observe_seconds
        while asyncio.get_event_loop().time() < deadline:
            final_state = await self.observer.observe_state(client, run_id, device_id)
            kind = final_state.location.screen_kind
            if kind == StateKind.NO_SIGNAL:
                reboot_observed = True
                final_phase = "no_signal"
                break
            elif kind == StateKind.POST_SCREEN:
                reboot_observed = True
                post_detected = True
                final_phase = "post"
                break
            elif kind in {StateKind.BOOT_MENU, StateKind.OS_BOOTED}:
                reboot_observed = True
                final_phase = kind.value
                break
            await asyncio.sleep(0.75)

        evidence = {
            "confirmed": True,
            "modal_text": getattr(modal, "message", None) or title,
            "selected_action": selected_action,
            "reboot_observed": reboot_observed,
            "post_detected": post_detected,
            "final_phase": final_phase,
        }
        LOG.info("Save/reboot evidence for run %s: %s", run_id, evidence)
        if not reboot_observed:
            return (
                False,
                final_state,
                f"Save confirmed but reboot not observed within {reboot_observe_seconds}s: {evidence}",
            )
        return True, final_state, f"Save confirmed and reboot observed: {evidence}"
