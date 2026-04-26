from pathlib import Path

from lightrag.orchestrator.lesson_runtime import PilotLessonCatalog
from lightrag.orchestrator.raw_curriculum import (
    normalize_useful_expressions_markdown,
    normalize_word_list_markdown,
)
from lightrag.orchestrator.support_asset_builder import (
    build_support_assets,
    default_support_asset_output_path,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _raw_root() -> Path:
    return _repo_root() / "app" / "knowledge" / "raw"


def _manifest_path() -> Path:
    return _repo_root() / "app" / "knowledge" / "structured" / "g5s1u3-pilot-manifest.json"


def test_build_support_assets_from_real_g5_s1_u3_sources():
    catalog = PilotLessonCatalog(manifest_path=_manifest_path())
    assets = build_support_assets(
        asset_id="g5s1u3-support-assets",
        catalog=catalog,
        word_sections=normalize_word_list_markdown(_raw_root() / "05.五年级上册单词表.md"),
        useful_expressions=normalize_useful_expressions_markdown(
            _raw_root() / "09.五年级上册Useful expressions.md"
        ),
    )

    assert assets.asset_id == "g5s1u3-support-assets"
    assert assets.scope.grade == "G5"
    assert assets.scope.semester == "S1"
    assert assets.scope.unit == "U3"
    assert assets.scope.pages == [24, 25, 26, 27, 28, 29, 30, 31]
    assert assets.source_files == [
        "raw_wordlist_g5s1",
        "raw_useful_expressions_g5s1",
        "structured_pilot_manifest_g5s1u3",
    ]
    assert len(assets.lexicon_entries) == 16
    assert len(assets.expression_entries) == 6

    sandwich = next(entry for entry in assets.lexicon_entries if entry.english == "sandwich")
    salad = next(entry for entry in assets.lexicon_entries if entry.english == "salad")
    order_question = next(
        entry
        for entry in assets.expression_entries
        if entry.english == "What would you like to eat?"
    )
    favourite_question = next(
        entry
        for entry in assets.expression_entries
        if entry.english == "What's your favourite food?"
    )

    assert sandwich.entry_uid == "LEX-G5S1U3-sandwich"
    assert sandwich.entry_type == "word"
    assert sandwich.source_refs == ["raw_wordlist_g5s1"]
    assert set(sandwich.page_refs) >= {"p.24", "p.25"}
    assert "TB-G5S1U3-P24-D2" in sandwich.linked_block_uids
    assert "TB-G5S1U3-P25-D1" in sandwich.linked_block_uids

    assert "p.25" in salad.page_refs
    assert "TB-G5S1U3-P25" in salad.linked_page_uids
    assert "TB-G5S1U3-P25-D1" in salad.linked_block_uids

    assert order_question.entry_uid == "EXP-G5S1U3-what-would-you-like-to-eat"
    assert order_question.page_refs == ["p.24"]
    assert order_question.source_refs == ["raw_useful_expressions_g5s1"]
    assert order_question.linked_page_uids == ["TB-G5S1U3-P24"]
    assert "TB-G5S1U3-P24-D2" in order_question.linked_block_uids

    assert favourite_question.page_refs == ["p.27"]
    assert favourite_question.linked_page_uids == ["TB-G5S1U3-P27"]
    assert "TB-G5S1U3-P27-D2" in favourite_question.linked_block_uids


def test_default_support_asset_output_path_uses_repo_support_directory():
    output_path = default_support_asset_output_path(
        "g5s1u3-support-assets",
        repo_root=_repo_root(),
    )

    assert output_path == (
        _repo_root()
        / "app"
        / "knowledge"
        / "structured"
        / "support"
        / "g5s1u3-support-assets.json"
    ).resolve()
