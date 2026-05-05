import importlib.util
import json
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_script(name: str):
    script_path = _repo_root() / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_curriculum_evidence_index_merges_sources_without_ragflow_override():
    builder = _load_script("build_curriculum_evidence_index")
    graph = {
        "nodes": [
            {
                "id": "Block:TB-G6S1U1-P4-D2",
                "type": "Block",
                "page_uid": "TB-G6S1U1-P4",
                "block_uid": "TB-G6S1U1-P4-D2",
                "label": "Where is the museum shop?",
            }
        ],
        "edges": [],
    }
    audit = {
        "findings": [
            {
                "rule": "bare_noun_redirect_risk",
                "node_id": "Block:TB-G6S1U1-P4-D2",
                "page_uid": "TB-G6S1U1-P4",
                "block_uid": "TB-G6S1U1-P4-D2",
                "message": "museum shop could be over-selected",
            }
        ]
    }
    candidates = {
        "candidates": [
            {
                "candidate_id": "CDT-1",
                "class": "defer_low_priority_candidate",
                "page_uid": "TB-G6S1U1-P4",
                "block_uid": "TB-G6S1U1-P4-D2",
                "suggested_action": "Keep as risk evidence.",
            }
        ]
    }
    ragflow = {
        "chunks": [
            {
                "chunk_id": "ragflow:c1",
                "ragflow_chunk_id": "c1",
                "page_uid": "TB-G6S1U1-P4",
                "block_uid": "TB-G6S1U1-P4-D2",
                "chunk_type": "qa",
                "text": "Where is the museum shop?",
                "mapping_confidence": "exact",
            }
        ]
    }

    index = builder.build_evidence_index(graph=graph, audit=audit, candidates=candidates, ragflow=ragflow)

    assert index["schema_version"] == "curriculum_evidence_index_v1"
    assert index["canonical_source"] == "app/knowledge/structured"
    assert index["ragflow_overrides_structured"] is False
    assert index["summary"]["entry_counts_by_source"]["structured"] == 1
    assert index["summary"]["entry_counts_by_source"]["audit"] == 1
    assert index["summary"]["entry_counts_by_source"]["candidate"] == 1
    assert index["summary"]["entry_counts_by_source"]["ragflow"] == 1
    structured = [entry for entry in index["entries"] if entry["source"] == "structured"][0]
    ragflow_entry = [entry for entry in index["entries"] if entry["source"] == "ragflow"][0]
    assert structured["canonical_priority"] == "canonical"
    assert ragflow_entry["canonical_priority"] == "supporting"


def test_curriculum_evidence_index_writes_valid_json(tmp_path):
    builder = _load_script("build_curriculum_evidence_index")
    index = builder.build_evidence_index(
        graph={"nodes": [], "edges": []},
        audit={"findings": []},
        candidates={"candidates": []},
        ragflow={"chunks": []},
    )
    path = builder.write_index(index, tmp_path)

    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "curriculum_evidence_index_v1"
    assert parsed["ragflow_overrides_structured"] is False
