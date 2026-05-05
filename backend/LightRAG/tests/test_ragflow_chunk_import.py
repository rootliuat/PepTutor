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


def test_clean_ragflow_chunks_drops_empty_short_and_duplicate_chunks():
    cleaner = _load_script("clean_ragflow_chunks")
    payload = {
        "schema_version": "ragflow_chunks_export_v1",
        "chunks": [
            {"id": "empty", "content": ""},
            {"id": "short", "content": "tiny"},
            {"id": "one", "content": "TB-G5S2U1-P6-D1 clean is a phonics exemplar.", "document_name": "p6.md"},
            {"id": "dup", "content": "TB-G5S2U1-P6-D1 clean is a phonics exemplar.", "document_name": "p6.md"},
        ],
    }

    cleaned = cleaner.clean_chunks(payload, min_chars=10)

    assert cleaned["clean_chunk_count"] == 1
    assert cleaned["dropped_counts"] == {"empty": 1, "duplicate": 1, "too_short": 1}
    assert cleaned["chunks"][0]["ragflow_chunk_id"] == "one"
    assert cleaned["chunks"][0]["source_document"] == "p6.md"


def test_import_ragflow_chunks_maps_exact_page_and_unknown_confidence():
    importer = _load_script("import_ragflow_chunks")
    payload = {
        "schema_version": "ragflow_chunks_clean_v1",
        "chunks": [
            {
                "ragflow_chunk_id": "c1",
                "ragflow_document_id": "d1",
                "source_document": "g5s2u1.md",
                "text": "TB-G5S2U1-P6-D1 Learn the consonant blend cl as in clean.",
            },
            {
                "ragflow_chunk_id": "c2",
                "ragflow_document_id": "d2",
                "source_document": "unknown.md",
                "text": "A loose note without page identity.",
            },
        ],
    }

    evidence = importer.convert_chunks(payload)
    summary = importer.mapping_summary(evidence)

    exact = evidence["chunks"][0]
    unknown = evidence["chunks"][1]
    assert exact["source"] == "ragflow"
    assert exact["page_uid"] == "TB-G5S2U1-P6"
    assert exact["block_uid"] == "TB-G5S2U1-P6-D1"
    assert exact["mapping_confidence"] == "exact"
    assert exact["chunk_type"] == "phonics"
    assert unknown["mapping_confidence"] == "unknown"
    assert summary["mapped_exact_count"] == 1
    assert summary["unknown_count"] == 1
    assert summary["six_anchor_mapping_summary"]["TB-G5S2U1-P6"] == 1


def test_import_script_writes_valid_json(tmp_path):
    importer = _load_script("import_ragflow_chunks")
    input_path = tmp_path / "clean.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "ragflow_chunks_clean_v1",
                "chunks": [
                    {
                        "ragflow_chunk_id": "c1",
                        "text": "TB-G6S2U2-P13 Last weekend answer scope evidence.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    evidence = importer.convert_chunks(payload)
    evidence["summary"] = importer.mapping_summary(evidence)
    out = tmp_path / "evidence.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")

    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "peptutor_ragflow_evidence_chunks_v1"
    assert parsed["chunks"][0]["page_uid"] == "TB-G6S2U2-P13"
