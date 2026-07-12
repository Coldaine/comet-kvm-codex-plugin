from __future__ import annotations
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
    ) -> Tuple[bool, Optional[BiosState], str]:
        """
        Commit staged BIOS changes to NVRAM and reboot.

        Flow:
            1. Observe current state.
            2. Send F10, capture the confirmation modal.
            3. Check for a save/confirm dialog via screen-title keywords
               (save/confirm/reset/reboot/exit) or modal.present.
            4. Confirm with Enter only if that check passes (fail-closed otherwise).
        """
        # 1. Ground current state.
        state = await self.observer.observe_state(client, run_id, device_id)

        # 3. Send F10 and wait for the confirmation modal.
        await client.send_combo("F10")
        await self.settler.wait_for_settle(client)
        modal_state = await self.observer.observe_state(client, run_id, device_id)

        # 5. Verify a save/confirmation dialog is actually present before confirming.
        title = (modal_state.location.screen_title or "").lower()
        modal_present = getattr(modal_state.modal, "present", False)
        looks_like_save = any(
            kw in title for kw in ("save", "confirm", "reset", "reboot", "exit")
        )
        if not (modal_present or looks_like_save):
            return (
                False,
                modal_state,
                "Save confirmation dialog not detected after F10; aborting without confirm.",
            )

        # 6. Confirm the save.
        await client.send_combo("Enter")
        await self.settler.wait_for_settle(client)

        LOG.info("Save confirmed for run %s; target is rebooting.", run_id)
        return True, modal_state, "Save confirmed. Target committing changes and rebooting."
