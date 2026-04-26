from pathlib import Path

from lightrag.orchestrator.lesson_runtime import PilotLessonCatalog
from lightrag.orchestrator.teaching_block_index import (
    build_embedding_text,
    build_index_record,
    build_unit_index_records,
)


def test_build_embedding_text_uses_teaching_fields():
    catalog = PilotLessonCatalog()
    block = catalog.get_block("TB-G5S1U3-P24-D2")

    text = build_embedding_text(block)

    assert block.teaching_goal in text
    assert block.teaching_summary in text
    assert "What would you like to eat?" in text
    assert "hungry" in text


def test_build_index_record_contains_expected_payload_fields():
    catalog = PilotLessonCatalog()
    block = catalog.get_block("TB-G5S1U3-P24-D2")

    record = build_index_record(catalog, block)

    assert record.point_id == "TB-G5S1U3-P24-D2"
    assert record.payload["grade"] == "G5"
    assert record.payload["semester"] == "S1"
    assert record.payload["unit"] == "U3"
    assert record.payload["page"] == 24
    assert record.payload["page_type"] == "dialogue"
    assert "branchable_topics" in record.payload
    assert "return_anchors" in record.payload


def test_build_unit_index_records_covers_all_loaded_blocks():
    catalog = PilotLessonCatalog()

    records = build_unit_index_records(catalog)

    assert len(records) == len(catalog.blocks)
    assert records[0].point_id == "TB-G5S1U3-P24-D1"
    assert records[-1].point_id == "TB-G5S1U3-P31-D1"


def test_build_index_record_uses_first_page_number_for_spread_page_uids():
    manifest_path = (
        Path(__file__).resolve().parents[3]
        / "app/knowledge/structured/general/general-manifest.json"
    )
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    block = catalog.get_block("TB-G5S1Recycle2-P68-69-D1")

    record = build_index_record(catalog, block)

    assert record.payload["page_uid"] == "TB-G5S1Recycle2-P68-69"
    assert record.payload["page"] == 68
