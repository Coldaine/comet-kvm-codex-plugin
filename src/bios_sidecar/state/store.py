from __future__ import annotations
import sqlite3
import json
import os
import logging
import threading
from typing import Dict, List, Optional
from src.bios_sidecar.domain.enums import EventClass
from src.bios_sidecar.domain.models import BiosState, StateNode, GraphEdge, CapabilityEntry, TraceEvent, EdgeAction, EdgeEvidence

LOG = logging.getLogger("bios_sidecar.state.store")

class SQLiteStore:
    def __init__(self, db_path: str = "state/bios_sidecar.db"):
        self.db_path = db_path
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        # Full BiosState objects for in-process OCR-first rematch (DB row is a projection).
        self._state_cache: Dict[str, BiosState] = {}
        self._create_tables()

    def _create_tables(self):
        with self._lock:
         cursor = self.conn.cursor()

        # 1. Runs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                device_id TEXT,
                started_at TEXT,
                status TEXT
            )
        """)

        # 2. States table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS states (
                state_id TEXT PRIMARY KEY,
                run_id TEXT,
                device_id TEXT,
                screen_title TEXT,
                menu_path TEXT,
                screen_kind TEXT,
                selection_label TEXT,
                selection_val TEXT,
                controls TEXT,
                blocklist_flag INTEGER,
                blocklist_keywords TEXT,
                actions TEXT,
                frame_screenshot_id TEXT,
                frame_sha256 TEXT,
                frame_phash TEXT,
                frame_resolution TEXT,
                frame_captured_at TEXT,
                confidence TEXT
            )
        """)

        # 3. Nodes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                visual_hash TEXT,
                ocr_hash TEXT,
                semantic_hash TEXT,
                volatile_regions TEXT,
                representative_state_id TEXT
            )
        """)

        # 4. Edges table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                edge_id TEXT PRIMARY KEY,
                from_node TEXT,
                action_type TEXT,
                action_key TEXT,
                policy_decision TEXT,
                policy_profile TEXT,
                to_node TEXT,
                transition_type TEXT,
                before_screenshot TEXT,
                after_screenshot TEXT,
                before_state TEXT,
                after_state TEXT
            )
        """)

        # 5. Capabilities table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS capabilities (
                capability_id TEXT PRIMARY KEY,
                canonical_name TEXT,
                aliases TEXT,
                vendor TEXT,
                board_family TEXT,
                paths TEXT,
                risk TEXT,
                mutation_policy TEXT,
                validation TEXT
            )
        """)

        # 6. Trace events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trace_events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT,
                timestamp TEXT,
                event_type TEXT,
                state_before TEXT,
                requested_action TEXT,
                policy_decision TEXT,
                state_after TEXT,
                artifacts TEXT
            )
        """)

        self.conn.commit()

    def close(self):
        with self._lock:
            self.conn.close()

    # --- Run persistence ---
    def save_run(self, run_id: str, device_id: str, started_at: str, status: str = "active"):
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO runs (run_id, device_id, started_at, status) VALUES (?, ?, ?, ?)",
                (run_id, device_id, started_at, status)
            )
            self.conn.commit()

    # --- BiosState persistence ---
    def save_bios_state(self, state: BiosState):
        with self._lock:
         cursor = self.conn.cursor()
         d = state.to_dict()
         cursor.execute("""
            INSERT OR REPLACE INTO states (
                state_id, run_id, device_id, screen_title, menu_path, screen_kind,
                selection_label, selection_val, controls, blocklist_flag, blocklist_keywords,
                actions, frame_screenshot_id, frame_sha256, frame_phash, frame_resolution,
                frame_captured_at, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            d["state_id"], d["run_id"], d["device_id"], d["location"]["screen_title"],
            json.dumps(d["location"]["breadcrumb"]), d["location"]["screen_kind"],
            d["selection"]["label"], d["selection"]["value"], json.dumps(d["controls"]),
            1 if d["risk"]["blocklist_flag"] else 0, json.dumps(d["risk"]["blocklist_keywords"]),
            json.dumps(d["actions"]), d["frame"]["screenshot_id"], d["frame"]["sha256"],
            d["frame"]["perceptual_hash"], json.dumps(d["frame"]["resolution"]),
            d["frame"]["captured_at"], json.dumps(d["confidence"])
        ))
        self.conn.commit()
        self._state_cache[state.state_id] = state

    def get_bios_state(self, state_id: str) -> Optional[BiosState]:
        """Load a previously saved BiosState by id (used to reuse graph-matched representatives)."""
        cached = self._state_cache.get(state_id)
        if cached is not None:
            return cached

        from src.bios_sidecar.domain.enums import StateKind
        from src.bios_sidecar.domain.models import (
            FrameMetadata, BiosMetadata, LocationMetadata, SelectionMetadata,
            ControlEntry, ModalMetadata, RiskStatus, ActionPolicies, ConfidenceMetrics,
        )

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM states WHERE state_id = ?", (state_id,))
            row = cursor.fetchone()
        if row is None:
            return None

        breadcrumb = json.loads(row["menu_path"] or "[]")
        controls_raw = json.loads(row["controls"] or "[]")
        actions_raw = json.loads(row["actions"] or "{}")
        confidence_raw = json.loads(row["confidence"] or "{}")
        resolution = json.loads(row["frame_resolution"] or "[1920, 1080]")
        top_module = breadcrumb[0] if breadcrumb else "SETTINGS"

        state = BiosState(
            state_id=row["state_id"],
            run_id=row["run_id"],
            device_id=row["device_id"],
            frame=FrameMetadata(
                screenshot_id=row["frame_screenshot_id"] or "",
                sha256=row["frame_sha256"] or "",
                perceptual_hash=row["frame_phash"] or "",
                resolution=resolution,
                captured_at=row["frame_captured_at"] or "",
            ),
            bios=BiosMetadata(
                vendor="generic",
                board_hint="unknown",
                family="generic_uefi",
                mode="advanced",
            ),
            location=LocationMetadata(
                screen_kind=StateKind(row["screen_kind"]) if row["screen_kind"] else StateKind.UNKNOWN,
                top_module=top_module,
                breadcrumb=breadcrumb,
                screen_title=row["screen_title"],
            ),
            selection=SelectionMetadata(
                selected_index=None,
                label=row["selection_label"],
                value=row["selection_val"],
            ),
            controls=[ControlEntry.from_dict(c) for c in controls_raw],
            modal=ModalMetadata(present=False),
            risk=RiskStatus(
                blocklist_flag=bool(row["blocklist_flag"]),
                blocklist_keywords=json.loads(row["blocklist_keywords"] or "[]"),
            ),
            actions=ActionPolicies.from_dict(actions_raw) if actions_raw else ActionPolicies(),
            confidence=ConfidenceMetrics.from_dict(confidence_raw) if confidence_raw else ConfidenceMetrics(1.0, 1.0, 1.0),
        )
        self._state_cache[state_id] = state
        return state

    # --- StateNode persistence ---
    def save_node(self, node: StateNode):
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO nodes (
                    node_id, visual_hash, ocr_hash, semantic_hash, volatile_regions, representative_state_id
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                node.node_id, node.visual_hash, node.ocr_hash, node.semantic_hash,
                json.dumps(node.volatile_regions), node.representative_state_id
            ))
            self.conn.commit()

    def get_node(self, node_id: str) -> Optional[StateNode]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
            row = cursor.fetchone()
        if row:
            return StateNode(
                node_id=row["node_id"],
                visual_hash=row["visual_hash"],
                ocr_hash=row["ocr_hash"],
                semantic_hash=row["semantic_hash"],
                volatile_regions=json.loads(row["volatile_regions"]),
                representative_state_id=row["representative_state_id"]
            )
        return None

    def list_nodes(self) -> List[StateNode]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM nodes")
            rows = cursor.fetchall()
        return [
            StateNode(
                node_id=row["node_id"],
                visual_hash=row["visual_hash"],
                ocr_hash=row["ocr_hash"],
                semantic_hash=row["semantic_hash"],
                volatile_regions=json.loads(row["volatile_regions"]),
                representative_state_id=row["representative_state_id"]
            )
            for row in rows
        ]

    # --- GraphEdge persistence ---
    def save_edge(self, edge: GraphEdge):
        with self._lock:
            cursor = self.conn.cursor()
            d = edge.to_dict()
            cursor.execute("""
                INSERT OR REPLACE INTO edges (
                    edge_id, from_node, action_type, action_key, policy_decision, policy_profile,
                    to_node, transition_type, before_screenshot, after_screenshot, before_state, after_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                d["edge_id"], d["from_node"], d["action"]["type"], d["action"]["key"],
                d["action"]["policy_decision"], d["action"]["policy_profile"], d["to_node"], d["transition_type"],
                d["evidence"]["before_screenshot"], d["evidence"]["after_screenshot"],
                d["evidence"]["before_state"], d["evidence"]["after_state"]
            ))
            self.conn.commit()

    def list_edges(self) -> List[GraphEdge]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM edges")
            rows = cursor.fetchall()
        edges = []
        for r in rows:
            edges.append(GraphEdge(
                edge_id=r["edge_id"],
                from_node=r["from_node"],
                action=EdgeAction(
                    type=r["action_type"],
                    key=r["action_key"],
                    policy_decision=r["policy_decision"],
                    policy_profile=r["policy_profile"]
                ),
                to_node=r["to_node"],
                transition_type=r["transition_type"],
                evidence=EdgeEvidence(
                    before_screenshot=r["before_screenshot"],
                    after_screenshot=r["after_screenshot"],
                    before_state=r["before_state"],
                    after_state=r["after_state"]
                )
            ))
        return edges

    # --- CapabilityIndex persistence ---
    def save_capability(self, cap: CapabilityEntry):
        with self._lock:
            cursor = self.conn.cursor()
            d = cap.to_dict()
            cursor.execute("""
                INSERT OR REPLACE INTO capabilities (
                    capability_id, canonical_name, aliases, vendor, board_family, paths, risk, mutation_policy, validation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                d["capability_id"], d["canonical_name"], json.dumps(d["aliases"]), d["vendor"], d["board_family"],
                json.dumps(d["paths"]), d["risk"], d["mutation_policy"], json.dumps(d["validation"])
            ))
            self.conn.commit()

    def get_capability(self, cap_id: str) -> Optional[CapabilityEntry]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM capabilities WHERE capability_id = ?", (cap_id,))
            r = cursor.fetchone()
        if r:
            return CapabilityEntry.from_dict({
                "capability_id": r["capability_id"],
                "canonical_name": r["canonical_name"],
                "aliases": json.loads(r["aliases"]),
                "vendor": r["vendor"],
                "board_family": r["board_family"],
                "paths": json.loads(r["paths"]),
                "risk": r["risk"],
                "mutation_policy": r["mutation_policy"],
                "validation": json.loads(r["validation"])
            })
        return None

    def list_capabilities(self) -> List[CapabilityEntry]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM capabilities")
            rows = cursor.fetchall()
        return [
            CapabilityEntry.from_dict({
                "capability_id": r["capability_id"],
                "canonical_name": r["canonical_name"],
                "aliases": json.loads(r["aliases"]),
                "vendor": r["vendor"],
                "board_family": r["board_family"],
                "paths": json.loads(r["paths"]),
                "risk": r["risk"],
                "mutation_policy": r["mutation_policy"],
                "validation": json.loads(r["validation"])
            })
            for r in rows
        ]

    # --- Trace event logs ---
    def save_trace_event(self, event: TraceEvent):
        with self._lock:
            cursor = self.conn.cursor()
            d = event.to_dict()
            cursor.execute("""
                INSERT INTO trace_events (
                    event_id, run_id, timestamp, event_type, state_before, requested_action, policy_decision, state_after, artifacts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                d["event_id"], d["run_id"], d["timestamp"], d["event_type"],
                d.get("state_before"), json.dumps(d.get("requested_action")),
                json.dumps(d.get("policy_decision")), d.get("state_after"), json.dumps(d.get("artifacts", {}))
            ))
            self.conn.commit()

    def list_trace_events(self, run_id: str) -> List[TraceEvent]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM trace_events WHERE run_id = ? ORDER BY timestamp ASC", (run_id,))
            rows = cursor.fetchall()
        events = []
        for r in rows:
            events.append(TraceEvent(
                event_id=r["event_id"],
                run_id=r["run_id"],
                timestamp=r["timestamp"],
                event_type=EventClass(r["event_type"]),
                state_before=r["state_before"],
                requested_action=json.loads(r["requested_action"]) if r["requested_action"] else None,
                policy_decision=json.loads(r["policy_decision"]) if r["policy_decision"] else None,
                state_after=r["state_after"],
                artifacts=json.loads(r["artifacts"]) if r["artifacts"] else {}
            ))
        return events
