from __future__ import annotations
import sqlite3
import json
import os
import logging
from typing import Dict, Any, List, Optional
from src.bios_sidecar.domain.enums import EventClass
from src.bios_sidecar.domain.models import BiosState, StateNode, GraphEdge, CapabilityEntry, TraceEvent, EdgeAction, EdgeEvidence

LOG = logging.getLogger("bios_sidecar.state.store")

class SQLiteStore:
    def __init__(self, db_path: str = "state/bios_sidecar.db"):
        self.db_path = db_path
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
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

        # 6. Approvals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                plan_id TEXT,
                approved_at TEXT,
                approved_by TEXT,
                status TEXT
            )
        """)

        # 7. Trace events table
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
        self.conn.close()

    # --- Run persistence ---
    def save_run(self, run_id: str, device_id: str, started_at: str, status: str = "active"):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO runs (run_id, device_id, started_at, status) VALUES (?, ?, ?, ?)",
            (run_id, device_id, started_at, status)
        )
        self.conn.commit()

    # --- BiosState persistence ---
    def save_bios_state(self, state: BiosState):
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

    # --- StateNode persistence ---
    def save_node(self, node: StateNode):
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
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM nodes")
        return [
            StateNode(
                node_id=row["node_id"],
                visual_hash=row["visual_hash"],
                ocr_hash=row["ocr_hash"],
                semantic_hash=row["semantic_hash"],
                volatile_regions=json.loads(row["volatile_regions"]),
                representative_state_id=row["representative_state_id"]
            )
            for row in cursor.fetchall()
        ]

    # --- GraphEdge persistence ---
    def save_edge(self, edge: GraphEdge):
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
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM edges")
        edges = []
        for r in cursor.fetchall():
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
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM capabilities")
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
            for r in cursor.fetchall()
        ]

    # --- Approvals persistence ---
    def save_approval(self, approval_id: str, plan_id: str, approved_at: str, approved_by: str, status: str):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO approvals (approval_id, plan_id, approved_at, approved_by, status)
            VALUES (?, ?, ?, ?, ?)
        """, (approval_id, plan_id, approved_at, approved_by, status))
        self.conn.commit()

    def get_approval(self, approval_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    # --- Trace event logs ---
    def save_trace_event(self, event: TraceEvent):
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
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM trace_events WHERE run_id = ? ORDER BY timestamp ASC", (run_id,))
        events = []
        for r in cursor.fetchall():
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
