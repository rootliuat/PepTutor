import json
from pathlib import Path

from lightrag.orchestrator.curriculum_map_builder import (
    build_curriculum_map,
    default_curriculum_map_output_path,
    detect_useful_expressions_path,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _manifest_path() -> Path:
    return _repo_root() / "app/knowledge/structured/general/general-manifest.json"


def _raw_root() -> Path:
    return _repo_root() / "app/knowledge/raw"


def _book(curriculum_map, grade: str, semester: str):
    return next(
        book
        for book in curriculum_map.books
        if book.grade == grade and book.semester == semester
    )


def _unit(book, unit: str):
    return next(entry for entry in book.units if entry.unit == unit)


def test_build_curriculum_map_covers_current_general_manifest_scopes():
    curriculum_map = build_curriculum_map(
        manifest_path=_manifest_path(),
        raw_root=_raw_root(),
        repo_root=_repo_root(),
        generated_at="2026-04-25T00:00:00+00:00",
    )

    assert curriculum_map.kind == "peptutor_curriculum_map"
    assert curriculum_map.map_id == "peptutor-curriculum-map-v1"
    assert curriculum_map.book_count == 4
    assert curriculum_map.scope_count == 30
    assert curriculum_map.page_count == 253
    assert curriculum_map.block_count == 579
    assert [book.book_id for book in curriculum_map.books] == [
        "G5S1",
        "G5S2",
        "G6S1",
        "G6S2",
    ]


def test_curriculum_map_uses_real_g5_s1_u1_content_not_handwritten_example():
    curriculum_map = build_curriculum_map(
        manifest_path=_manifest_path(),
        raw_root=_raw_root(),
        repo_root=_repo_root(),
        generated_at="2026-04-25T00:00:00+00:00",
    )

    unit = _unit(_book(curriculum_map, "G5", "S1"), "U1")
    words = {entry.word for entry in unit.core_vocabulary}

    assert {"old", "young", "funny", "kind", "strict"} <= words
    assert {"pen", "book", "desk", "chair"}.isdisjoint(words)
    assert "Is he young?" in unit.core_patterns
    assert "What's she like?" in unit.core_patterns
    assert any(ref.endswith("09.五年级上册Useful expressions.md") for ref in unit.source_refs)
    assert unit.confidence == "high"


def test_curriculum_map_keeps_p31_and_p49_grounded_in_actual_content():
    curriculum_map = build_curriculum_map(
        manifest_path=_manifest_path(),
        raw_root=_raw_root(),
        repo_root=_repo_root(),
        generated_at="2026-04-25T00:00:00+00:00",
    )

    g5u3 = _unit(_book(curriculum_map, "G5", "S1"), "U3")
    p31 = next(page for page in g5u3.page_types if page.page_uid == "TB-G5S1U3-P31")
    assert p31.page_type == "story"
    assert any(ref.endswith("g5s1u3-p31-pilot.json") for ref in p31.source_refs)
    assert "What would you like to eat?" in g5u3.core_patterns
    assert "I'd like a salad." in g5u3.core_patterns
    assert "I'd like some water." in g5u3.core_patterns
    assert any(block_uid == "TB-G5S1U3-P31-D1" for block_uid in g5u3.block_uids)

    recycle2 = _unit(_book(curriculum_map, "G6", "S2"), "Recycle2")
    p49 = next(page for page in recycle2.page_types if page.page_uid == "TB-G6S2Recycle2-P49")
    assert p49.page_type == "phonics"
    assert "TB-G6S2Recycle2-P49-D4" in recycle2.block_uids
    assert any(
        target.block_uid == "TB-G6S2Recycle2-P49-D4"
        for target in recycle2.learning_targets
    )


def test_curriculum_map_default_output_path_and_json_shape():
    curriculum_map = build_curriculum_map(
        manifest_path=_manifest_path(),
        raw_root=_raw_root(),
        repo_root=_repo_root(),
        generated_at="2026-04-25T00:00:00+00:00",
    )
    payload = curriculum_map.model_dump(mode="json", exclude_none=True)

    assert default_curriculum_map_output_path(_repo_root()) == (
        _repo_root() / "app/knowledge/structured/curriculum-map.json"
    )
    assert json.loads(json.dumps(payload, ensure_ascii=False))["scope_count"] == 30
    assert "books" in payload


def test_detect_useful_expressions_path_matches_current_raw_layout():
    assert detect_useful_expressions_path(_raw_root(), grade="G5", semester="S1") == (
        _raw_root() / "09.五年级上册Useful expressions.md"
    )
    assert detect_useful_expressions_path(_raw_root(), grade="G6", semester="S2") == (
        _raw_root() / "12.六年级下册Useful expressions.md"
    )
