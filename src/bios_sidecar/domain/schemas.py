import os
import json
from typing import Any, Dict

SCHEMAS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "schemas"))

def load_schema(name: str) -> Dict[str, Any]:
    path = os.path.join(SCHEMAS_DIR, f"{name}.schema.json")
    if not os.path.exists(path):
        # Fallback if run elsewhere
        parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        path = os.path.join(parent_dir, "schemas", f"{name}.schema.json")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_dict(data: Dict[str, Any], schema_name: str) -> bool:
    """
    Validate dictionary against schema_name. We support using jsonschema if available.
    Otherwise we fall back to robust key-existence validation to preserve high-portability.
    """
    try:
        import jsonschema
        schema = load_schema(schema_name)
        jsonschema.validate(instance=data, schema=schema)
        return True
    except ImportError:
        # Fallback manual validation for critical fields
        if schema_name == "bios-state":
            required = ["state_id", "run_id", "device_id", "frame", "bios", "location", "selection"]
            return all(k in data for k in required)
        elif schema_name == "transition":
            required = ["edge_id", "from_node", "action", "to_node", "transition_type", "evidence"]
            return all(k in data for k in required)
        elif schema_name == "capability":
            required = ["capability_id", "canonical_name", "aliases", "vendor", "board_family", "paths", "risk", "mutation_policy"]
            return all(k in data for k in required)
        elif schema_name == "trace-event":
            required = ["event_id", "run_id", "timestamp", "event_type"]
            return all(k in data for k in required)
        return True
    except Exception:
        return False
