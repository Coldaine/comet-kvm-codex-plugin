from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "docs" / "reference" / "glkvm-api"
GLKVM_COMMIT = "9bd8ad11ba03d220401b0b6a4208bbfd84ed6107"
DOCS_KVM_COMMIT = "9b6d508661f0808e8e69373e0da3ebf923c6e94d"


def _csv_rows(name: str) -> list[dict[str, str]]:
    with (CORPUS / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_source_records_are_exact_pins_and_link_only() -> None:
    record = json.loads((CORPUS / "sources.json").read_text(encoding="utf-8"))
    glkvm = record["sources"]["glkvm"]
    docs_kvm = record["sources"]["docs-kvm"]

    assert glkvm["commit"] == GLKVM_COMMIT
    assert f"/tree/{GLKVM_COMMIT}" in glkvm["tree_url"]
    assert glkvm["license"]["spdx"] == "GPL-3.0-or-later"
    assert f"/blob/{GLKVM_COMMIT}/LICENSE" in glkvm["license"]["url"]
    assert glkvm["vendored"] is False

    assert docs_kvm["commit"] == DOCS_KVM_COMMIT
    assert f"/tree/{DOCS_KVM_COMMIT}" in docs_kvm["tree_url"]
    assert docs_kvm["license"] is None
    assert "No license file" in docs_kvm["license_note"]
    assert docs_kvm["vendored"] is False


def test_generated_http_inventory_is_complete_unique_and_deterministic() -> None:
    rows = _csv_rows("http-endpoints.csv")
    keys = [(row["method"], row["path"]) for row in rows]

    assert len(rows) == 200
    assert len(keys) == len(set(keys))
    assert rows == sorted(
        rows,
        key=lambda row: (
            row["path"],
            row["method"],
            row["handler"],
            row["source_file"],
            int(row["source_line"]),
        ),
    )
    assert {row["auth_required"] for row in rows} <= {"true", "false"}
    assert {row["allow_usc"] for row in rows} <= {"true", "false"}
    assert all(json.loads(row["allowed_exe_paths"]) is not None for row in rows)
    assert all(f"/blob/{GLKVM_COMMIT}/" in row["source_url"] for row in rows)
    assert all(row["source_url"].endswith(f"#L{row['source_line']}") for row in rows)


def test_generated_websocket_inventory_is_complete_unique_and_deterministic() -> None:
    rows = _csv_rows("websocket-events.csv")
    keys = [(row["event_type"], row["binary"]) for row in rows]

    assert len(rows) == 12
    assert len(keys) == len(set(keys))
    assert rows == sorted(
        rows,
        key=lambda row: (
            row["event_type"],
            row["binary"] == "true",
            row["handler"],
            row["source_file"],
            int(row["source_line"]),
        ),
    )
    assert all(f"/blob/{GLKVM_COMMIT}/" in row["source_url"] for row in rows)
    assert all(row["source_url"].endswith(f"#L{row['source_line']}") for row in rows)


def test_project_coverage_maps_client_routes_to_inventory_and_existing_evidence() -> None:
    inventory = {
        (row["method"], row["path"])
        for row in _csv_rows("http-endpoints.csv")
    }
    coverage = _csv_rows("project-endpoint-coverage.csv")
    coverage_keys = {(row["method"], row["path"]) for row in coverage}

    assert len(coverage_keys) == len(coverage)
    assert coverage_keys <= inventory
    assert all(row["handler_present"] == "true" for row in coverage)
    assert {row["registration"] for row in coverage} <= {
        "unconditional",
        "conditional",
    }
    assert all(row["discovered"] for row in coverage)
    assert all(row["exercised"] for row in coverage)
    assert all(row["hardware_required"] for row in coverage)
    assert all(row["contract_test_status"] for row in coverage)
    assert all(row["live_qualification_status"] for row in coverage)

    client_source = ROOT / "src" / "kvm_core" / "comet" / "client.py"
    client_text = client_source.read_text(encoding="utf-8")
    literal_paths = {
        path.split("?", 1)[0]
        for path in re.findall(r"(/(?:api|redfish)/[^\"'\s]+)", client_text)
    }
    assert literal_paths <= {row["path"] for row in coverage}

    for row in coverage:
        assert (ROOT / row["client_source"]).is_file()
        if row["contract_test_source"]:
            assert (ROOT / row["contract_test_source"]).is_file()


def test_pinned_catalog_has_no_mutable_main_source_links() -> None:
    catalog_paths = [
        CORPUS / "README.md",
        ROOT / "docs" / "research" / "glkvm-api-surface.md",
        ROOT / "docs" / "reference" / "comet-api.md",
    ]
    mutable = re.compile(
        r"github\.com/gl-inet/(?:glkvm|docs-kvm)/(?:blob|tree)/main(?:/|\b)",
        re.IGNORECASE,
    )
    for path in catalog_paths:
        assert not mutable.search(path.read_text(encoding="utf-8")), path


def test_ocr_docs_preserve_three_surfaces_without_native_product_claims() -> None:
    paths = [
        CORPUS / "README.md",
        ROOT / "docs" / "research" / "glkvm-api-surface.md",
        ROOT / "docs" / "reference" / "comet-api.md",
        ROOT / "docs" / "workflows" / "live-hardware-qualification.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for required in (
        "/api/streamer/ocr",
        "Tesseract.js",
        "host Tesseract",
    ):
        assert required in text

    unsupported = (
        "device-native OCR",
        "native Text Recognition API",
        "MCP uses /api/streamer/ocr",
        "firmware OCR plus",
        "intrinsic product OCR API",
    )
    lowered = text.lower()
    assert all(claim.lower() not in lowered for claim in unsupported)
