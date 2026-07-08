from __future__ import annotations
import os
import logging
from typing import Dict, Any, List, Optional
from src.bios_sidecar.domain.models import BiosState, PolicyDecision
from src.bios_sidecar.domain.enums import PolicyProfile, RiskClass, StateKind, ControlRole
from src.bios_sidecar.policy.hazards import HazardDetector
from src.bios_sidecar.policy.approvals import ApprovalTracker

LOG = logging.getLogger("bios_sidecar.policy.engine")

class PolicyEngine:
    def __init__(self, approval_tracker: ApprovalTracker, matrix_path: Optional[str] = None):
        self.approval_tracker = approval_tracker
        self.hazard_detector = HazardDetector()

        if matrix_path is None:
            matrix_path = os.path.join(os.path.dirname(__file__), "matrix.yaml")
        self.matrix = self._load_default_matrix()
        if os.path.exists(matrix_path):
            try:
                loaded = self._load_matrix_file(matrix_path)
                if self._is_valid_matrix(loaded):
                    self.matrix = loaded
                else:
                    LOG.warning("Policy matrix %s is invalid; using hardcoded default.", matrix_path)
            except OSError as exc:
                LOG.warning("Could not load policy matrix %s: %s", matrix_path, exc)

    def _load_default_matrix(self) -> Dict[str, Any]:
        return {
            "observe_only": {
                "allowed_keys": [],
                "enter_allowed": False,
                "save_allowed": False,
                "all_hid_allowed": False
            },
            "read_only_crawl": {
                "allowed_keys": ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Escape", "F11", "F7"],
                "enter_allowed": True,
                "save_allowed": False,
                "all_hid_allowed": False
            },
            "supervised_mutation": {
                "allowed_keys": ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Escape", "Enter", "F10", "F11", "F7"],
                "enter_allowed": True,
                "save_allowed": True,
                "all_hid_allowed": False
            },
            "admin_debug": {
                "allowed_keys": [],
                "enter_allowed": True,
                "save_allowed": True,
                "all_hid_allowed": True
            }
        }

    def _load_matrix_file(self, matrix_path: str) -> Any:
        with open(matrix_path, "r", encoding="utf-8") as f:
            text = f.read()
        try:
            import yaml
            return yaml.safe_load(text)
        except ImportError:
            return self._load_simple_matrix_yaml(text)

    def _load_simple_matrix_yaml(self, text: str) -> Dict[str, Any]:
        matrix: Dict[str, Any] = {}
        current_profile: Optional[str] = None
        current_list_key: Optional[str] = None
        for raw_line in text.splitlines():
            line_without_comment = raw_line.split("#", 1)[0].rstrip()
            if not line_without_comment.strip():
                continue
            indent = len(line_without_comment) - len(line_without_comment.lstrip(" "))
            stripped = line_without_comment.strip()
            if indent == 0 and stripped.endswith(":"):
                current_profile = stripped[:-1]
                matrix[current_profile] = {}
                current_list_key = None
            elif current_profile and stripped.startswith("-") and current_list_key:
                matrix[current_profile][current_list_key].append(stripped[1:].strip())
            elif current_profile and ":" in stripped:
                key, value = [part.strip() for part in stripped.split(":", 1)]
                if value == "":
                    matrix[current_profile][key] = []
                    current_list_key = key
                elif value == "[]":
                    matrix[current_profile][key] = []
                    current_list_key = None
                else:
                    matrix[current_profile][key] = value.lower() == "true" if value.lower() in {"true", "false"} else value
                    current_list_key = None
        return matrix

    def _is_valid_matrix(self, matrix: Any) -> bool:
        if not isinstance(matrix, dict):
            return False
        required_profiles = {profile.value for profile in PolicyProfile}
        required_fields = {"allowed_keys", "enter_allowed", "save_allowed", "all_hid_allowed"}
        for profile in required_profiles:
            rules = matrix.get(profile)
            if not isinstance(rules, dict) or not required_fields.issubset(rules):
                return False
            if not isinstance(rules["allowed_keys"], list):
                return False
        return True

    def evaluate(
        self,
        state: BiosState,
        requested_action: str,
        policy_profile: PolicyProfile,
        approval_id: Optional[str] = None
    ) -> PolicyDecision:
        """
        Evaluate if requested_action is allowed.
        Returns PolicyDecision.
        """
        prof_name = policy_profile.value
        prof_rules = self.matrix.get(prof_name, self.matrix["observe_only"])

        # 1. Direct block on hazards or active blocklist flags
        hazards = self.hazard_detector.analyze_hazards(state)
        if hazards:
            # Hard block on everything except emergency back-out (Escape)
            if requested_action == "Escape":
                return PolicyDecision(
                    decision="allowed",
                    reason="EMERGENCY_BACKOUT_PERMITTED",
                    requested_action=requested_action,
                    policy_profile=policy_profile,
                    state_id=state.state_id
                )
            return PolicyDecision(
                decision="blocked",
                reason=f"HAZARDS_DETECTED:{','.join(hazards)}",
                requested_action=requested_action,
                policy_profile=policy_profile,
                state_id=state.state_id
            )

        # 2. Check general HID profile rules
        if prof_rules.get("all_hid_allowed", False):
            return PolicyDecision(
                decision="allowed",
                reason="ADMIN_DEBUG_UNRESTRICTED",
                requested_action=requested_action,
                policy_profile=policy_profile,
                state_id=state.state_id
            )

        if prof_name == "observe_only":
            return PolicyDecision(
                decision="blocked",
                reason="OBSERVE_ONLY_PROFILE",
                requested_action=requested_action,
                policy_profile=policy_profile,
                state_id=state.state_id
            )

        # 3. Check key-specific rules
        if requested_action not in prof_rules.get("allowed_keys", []) and requested_action != "Enter":
            # Gated because not explicitly in list
            return PolicyDecision(
                decision="blocked",
                reason=f"KEY_NOT_ALLOWED_IN_PROFILE:{requested_action}",
                requested_action=requested_action,
                policy_profile=policy_profile,
                state_id=state.state_id
            )

        # 4. Context-gated Enter check
        if requested_action == "Enter":
            # Check Enter permissions in profile
            if not prof_rules.get("enter_allowed", False):
                return PolicyDecision(
                    decision="blocked",
                    reason="ENTER_BLOCKED_IN_PROFILE",
                    requested_action=requested_action,
                    policy_profile=policy_profile,
                    state_id=state.state_id
                )

            # Content check: Is cursor pointing at submenu, setting, or modal?
            cursor_role = ControlRole.UNKNOWN
            cursor_risk = RiskClass.LOW
            cursor_label = "None"

            for ctrl in state.controls:
                if ctrl.selected:
                    cursor_role = ctrl.role
                    cursor_risk = ctrl.risk
                    cursor_label = ctrl.label
                    break

            if cursor_role == ControlRole.SUBMENU:
                if cursor_risk == RiskClass.LOW or cursor_risk == RiskClass.MEDIUM:
                    return PolicyDecision(
                        decision="allowed",
                        reason="ENTER_SUBMENU_SAFE",
                        requested_action=requested_action,
                        policy_profile=policy_profile,
                        state_id=state.state_id
                    )
                else:
                    return PolicyDecision(
                        decision="blocked",
                        reason=f"ENTER_SUBMENU_RISKY:{cursor_risk.value}",
                        requested_action=requested_action,
                        policy_profile=policy_profile,
                        state_id=state.state_id
                    )
            elif cursor_role == ControlRole.SETTING:
                if policy_profile == PolicyProfile.READ_ONLY_CRAWL:
                    # BLOCK mutation entries on read only crawl
                    return PolicyDecision(
                        decision="blocked",
                        reason="ENTER_SETTING_BLOCKED_IN_CRAWL",
                        requested_action=requested_action,
                        policy_profile=policy_profile,
                        state_id=state.state_id
                    )
                elif policy_profile == PolicyProfile.SUPERVISED_MUTATION:
                    if approval_id and self.approval_tracker.is_approved(approval_id):
                        return PolicyDecision(
                            decision="allowed",
                            reason=f"MUTATION_AUTHORIZED_BY_HUMAN_FOR:{cursor_label}",
                            requested_action=requested_action,
                            policy_profile=policy_profile,
                            state_id=state.state_id
                        )
                    # Supervised mutation is allowed with approval
                    return PolicyDecision(
                        decision="requires_approval",
                        reason=f"MUTATION_REQUIRES_APPROVAL_FOR:{cursor_label}",
                        requested_action=requested_action,
                        policy_profile=policy_profile,
                        state_id=state.state_id,
                        required_approval=True
                    )
            elif state.location.screen_kind == StateKind.CONFIRMATION_MODAL or state.location.screen_kind == StateKind.SAVE_CHANGES_MODAL:
                # Modals are heavily gated
                return PolicyDecision(
                    decision="requires_approval",
                    reason="MODAL_CONFIRMATION_GATED",
                    requested_action=requested_action,
                    policy_profile=policy_profile,
                    state_id=state.state_id,
                    required_approval=True
                )
            else:
                # Fallback safeguard on unknown roles
                return PolicyDecision(
                    decision="blocked",
                    reason=f"ENTER_ON_UNKNOWN_ROLE_BLOCKED:{cursor_label}",
                    requested_action=requested_action,
                    policy_profile=policy_profile,
                    state_id=state.state_id
                )

        # 5. Check F10 Save gating
        if requested_action == "F10":
            if not prof_rules.get("save_allowed", False):
                return PolicyDecision(
                    decision="blocked",
                    reason="SAVE_BLOCKED_IN_PROFILE",
                    requested_action=requested_action,
                    policy_profile=policy_profile,
                    state_id=state.state_id
                )

            # Verify if approval ID is valid and active
            if approval_id and self.approval_tracker.is_approved(approval_id):
                return PolicyDecision(
                    decision="allowed",
                    reason="F10_SAVE_AUTHORIZED_BY_HUMAN",
                    requested_action=requested_action,
                    policy_profile=policy_profile,
                    state_id=state.state_id
                )
            else:
                return PolicyDecision(
                    decision="requires_approval",
                    reason="F10_SAVE_REQUIRES_APPROVAL",
                    requested_action=requested_action,
                    policy_profile=policy_profile,
                    state_id=state.state_id,
                    required_approval=True
                )

        # Default allowed for standard arrow/esc navigation keys under safe conditions
        return PolicyDecision(
            decision="allowed",
            reason="NAVIGATION_PERMITTED",
            requested_action=requested_action,
            policy_profile=policy_profile,
            state_id=state.state_id
        )
