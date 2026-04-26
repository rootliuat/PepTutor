import json
from pathlib import Path

import pytest

from lightrag.orchestrator.lesson_evidence import LessonEvidenceLookup
from lightrag.orchestrator.lesson_runtime import LessonRuntime, PilotLessonCatalog
from lightrag.pedagogy.responder import LessonResponder


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _general_manifest_path() -> Path:
    return _repo_root() / "app/knowledge/structured/general/general-manifest.json"


def _curriculum_map_path() -> Path:
    return _repo_root() / "app/knowledge/structured/curriculum-map.json"


def _lookup() -> LessonEvidenceLookup:
    return LessonEvidenceLookup(
        PilotLessonCatalog(manifest_path=_general_manifest_path()),
        curriculum_map_path=_curriculum_map_path(),
    )


def test_lesson_evidence_uses_exact_page_and_block_before_support_scopes():
    evidence = _lookup().lookup(
        page_uid="TB-G6S2Recycle2-P49",
        block_uid="TB-G6S2Recycle2-P49-D4",
        same_page_limit=10,
        same_unit_limit=20,
    )
    payload = evidence.to_prompt_payload()

    assert payload["lookup_strategy"][:2] == ["exact_page_uid", "exact_block_uid"]
    assert payload["exact_page"]["page_uid"] == "TB-G6S2Recycle2-P49"
    assert payload["exact_block"]["block_uid"] == "TB-G6S2Recycle2-P49-D4"
    assert "物品清单" in payload["exact_block"]["teaching_summary"]
    assert all(
        item["block_uid"] != "TB-G6S2Recycle2-P49-D4"
        for item in payload["same_page_support"]
    )
    assert {item["page_uid"] for item in payload["same_page_support"]} == {
        "TB-G6S2Recycle2-P49"
    }


def test_lesson_evidence_p31_uses_pilot_story_overlay_from_actual_content():
    evidence = _lookup().lookup(
        page_uid="TB-G5S1U3-P31",
        block_uid="TB-G5S1U3-P31-D1",
        same_unit_limit=0,
    )

    assert evidence.exact_page.page_type == "story"
    assert evidence.exact_page.confidence == "high"
    assert "app/knowledge/structured/g5s1u3-p31-pilot.json" in (
        evidence.exact_page.source_refs
    )
    assert evidence.exact_block is not None
    assert evidence.exact_block.block_type == "story_block"
    assert "Zoom is hungry" in evidence.exact_block.teaching_summary
    assert "tomatoes" in evidence.exact_block.focus_vocabulary
    assert "I'd like a salad." in evidence.exact_block.core_patterns


def test_lesson_evidence_same_unit_support_does_not_cross_scope():
    evidence = _lookup().lookup(
        page_uid="TB-G6S2Recycle2-P49",
        block_uid="TB-G6S2Recycle2-P49-D4",
        same_unit_limit=50,
    )

    assert evidence.scope.grade == "G6"
    assert evidence.scope.semester == "S2"
    assert evidence.scope.unit == "Recycle2"
    assert evidence.same_unit_blocks
    assert all(block.page_uid != "TB-G6S2Recycle2-P49" for block in evidence.same_unit_blocks)
    assert all(block.block_uid.startswith("TB-G6S2Recycle2-") for block in evidence.same_unit_blocks)


def test_lesson_evidence_rejects_block_from_different_page():
    with pytest.raises(ValueError, match="not requested page"):
        _lookup().lookup(
            page_uid="TB-G6S2Recycle2-P49",
            block_uid="TB-G5S1U3-P31-D1",
        )


def test_lesson_runtime_prompt_receives_compact_lesson_evidence_not_whole_map():
    captured: list[dict[str, object]] = []

    def _teacher_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        captured.append(json.loads(prompt))
        return "我们读 Zoom 和 Zip 做沙拉的小故事，先看看 Zoom 想吃什么。"

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_manifest_path()),
        responder=LessonResponder(_teacher_llm),
    )

    runtime.start_page("TB-G5S1U3-P31", "student-1")

    lesson_evidence = captured[0]["lesson_evidence"]
    assert lesson_evidence["exact_page"]["page_type"] == "story"
    assert lesson_evidence["exact_block"]["block_type"] == "story_block"
    assert "Zoom is hungry" in lesson_evidence["exact_block"]["teaching_summary"]
    assert "books" not in lesson_evidence
    assert "units" not in lesson_evidence
