from pathlib import Path

from lightrag.orchestrator.general_draft_builder import (
    build_general_draft,
    default_display_name,
    default_general_draft_output_path,
    detect_word_list_path,
    select_general_scope_pages,
)
from lightrag.orchestrator.raw_curriculum import (
    normalize_textbook_source,
    normalize_word_list_markdown,
)


def _raw_root() -> Path:
    return (
        Path(__file__).resolve().parents[3] / "app" / "knowledge" / "raw"
    ).resolve()


def test_select_general_scope_pages_filters_to_main_unit_pages_only():
    normalized_pages = normalize_textbook_source(_raw_root() / "03.六年级上册语料.json")

    selected_pages = select_general_scope_pages(
        normalized_pages,
        grade="G6",
        semester="S1",
        unit="U1",
    )

    assert [page.page for page in selected_pages] == [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    assert all(page.unit == "U1" for page in selected_pages)


def test_build_general_draft_from_real_g6_s1_u1_pages():
    raw_root = _raw_root()
    normalized_pages = normalize_textbook_source(raw_root / "03.六年级上册语料.json")
    selected_pages = select_general_scope_pages(
        normalized_pages,
        grade="G6",
        semester="S1",
        unit="U1",
    )
    word_list_sections = normalize_word_list_markdown(raw_root / "07.六年级上册单词表.md")

    draft = build_general_draft(
        selected_pages,
        draft_id="g6s1u1-general-v1",
        source_files=[
            "app/knowledge/raw/03.六年级上册语料.json",
            "app/knowledge/raw/07.六年级上册单词表.md",
        ],
        word_list_sections=word_list_sections,
        display_name=selected_pages[0].book,
    )

    assert draft.pilot_id == "g6s1u1-general-v1"
    assert draft.scope.grade == "G6"
    assert draft.scope.semester == "S1"
    assert draft.scope.unit == "U1"
    assert draft.scope.pages == [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    assert draft.source_files == [
        "app/knowledge/raw/03.六年级上册语料.json",
        "app/knowledge/raw/07.六年级上册单词表.md",
    ]
    assert draft.draft_metadata["display_name"] == default_display_name(
        grade="G6",
        semester="S1",
    )
    assert draft.draft_metadata["raw_display_name"].startswith(
        "English (Primary School, Grade 6"
    )
    assert len(draft.page_lessons) == 10
    assert len(draft.teaching_blocks) == 19
    assert len(draft.learning_targets) == 19

    page4 = next(page for page in draft.page_lessons if page.page_uid == "TB-G6S1U1-P4")
    assert page4.priority_blocks == [
        "TB-G6S1U1-P4-D2",
        "TB-G6S1U1-P4-D3",
        "TB-G6S1U1-P4-D1",
    ]
    assert page4.entry_probe_questions == [
        "Do you know the word museum shop?",
        "Can you say: Where is the museum shop?",
    ]

    talk_block = next(
        block for block in draft.teaching_blocks if block.block_uid == "TB-G6S1U1-P4-D2"
    )
    assert talk_block.block_type == "dialogue_core"
    assert talk_block.focus_vocabulary == [
        "museum shop",
        "postcard",
        "post office",
        "near",
        "next to",
    ]
    assert talk_block.core_patterns == [
        "Where is the museum shop?",
        "It's near the door.",
        "Where is the post office?",
        "It's next to the museum.",
        "I don't know. I'll ask. Excuse me, sir.",
        "Wow! A talking robot! What a great museum!",
    ]
    assert talk_block.allowed_answer_scope == [
        "It's near the door.",
        "I don't know. I'll ask. Excuse me, sir.",
        "Wow! A talking robot! What a great museum!",
        "It's next to the museum.",
    ]
    assert talk_block.learning_target_uids == ["LT-G6S1U1-P4-D2-goal"]

    bookstore_entry = next(
        entry for entry in draft.wordlist_entries if entry.word == "bookstore"
    )
    assert bookstore_entry.chinese == "书店"
    assert bookstore_entry.linked_block_uids == ["TB-G6S1U1-P4-D1", "TB-G6S1U1-P5-D1"]

    bookstore_atom = next(
        item for item in draft.knowledge_atoms if item["text"] == "bookstore"
    )
    assert bookstore_atom["gloss"] == "书店"
    assert bookstore_atom["linked_blocks"] == ["TB-G6S1U1-P4-D1", "TB-G6S1U1-P5-D1"]


def test_select_general_scope_pages_supports_explicit_page_override_for_dirty_metadata():
    raw_root = _raw_root()
    normalized_pages = normalize_textbook_source(raw_root / "04.六年级下册语料.json")

    selected_pages = select_general_scope_pages(
        normalized_pages,
        grade="G6",
        semester="S2",
        unit="U4",
        page_numbers=tuple(range(32, 42)),
    )

    assert [page.page for page in selected_pages] == [32, 33, 34, 35, 36, 37, 38, 39, 40, 41]
    assert all(page.unit == "U4" for page in selected_pages)
    page39 = next(page for page in selected_pages if page.page == 39)
    assert page39.page_uid == "TB-G6S2U4-P39"


def test_select_general_scope_pages_dedupes_duplicate_g5_s1_pages_by_page_uid():
    raw_root = _raw_root()
    normalized_pages = normalize_textbook_source(raw_root / "01.五年级上册语料.js")

    selected_pages = select_general_scope_pages(
        normalized_pages,
        grade="G5",
        semester="S1",
        unit="U1",
        page_numbers=tuple(range(2, 12)),
    )

    assert [page.page for page in selected_pages] == [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    assert [page.page_uid for page in selected_pages].count("TB-G5S1U1-P8") == 1


def test_select_general_scope_pages_supports_recycle_pages_without_numeric_page_id():
    raw_root = _raw_root()
    normalized_pages = normalize_textbook_source(raw_root / "01.五年级上册语料.js")

    selected_pages = select_general_scope_pages(
        normalized_pages,
        grade="G5",
        semester="S1",
        unit="Recycle2",
    )

    assert [page.page for page in selected_pages] == [66, 67, None]
    assert [page.page_uid for page in selected_pages] == [
        "TB-G5S1Recycle2-P66",
        "TB-G5S1Recycle2-P67",
        "TB-G5S1Recycle2-P68-69",
    ]
    assert all(page.unit == "Recycle2" for page in selected_pages)


def test_build_general_draft_expands_scope_pages_for_spread_page_uid():
    raw_root = _raw_root()
    normalized_pages = normalize_textbook_source(raw_root / "01.五年级上册语料.js")
    selected_pages = select_general_scope_pages(
        normalized_pages,
        grade="G5",
        semester="S1",
        unit="Recycle2",
    )

    draft = build_general_draft(
        selected_pages,
        draft_id="g5s1recycle2-general-v1",
        source_files=[
            "app/knowledge/raw/01.五年级上册语料.js",
            "app/knowledge/raw/05.五年级上册单词表.md",
        ],
        word_list_sections=normalize_word_list_markdown(raw_root / "05.五年级上册单词表.md"),
        display_name=selected_pages[0].book,
    )

    assert draft.scope.pages == [66, 67, 68, 69]
    assert [page.page_uid for page in draft.page_lessons] == [
        "TB-G5S1Recycle2-P66",
        "TB-G5S1Recycle2-P67",
        "TB-G5S1Recycle2-P68-69",
    ]
    assert "TB-G5S1Recycle2-P68-69-D1" in [
        block.block_uid for block in draft.teaching_blocks
    ]


def test_detect_word_list_path_and_output_path_cover_current_layout():
    raw_root = _raw_root()

    assert detect_word_list_path(raw_root, grade="G5", semester="S1") == (
        raw_root / "05.五年级上册单词表.md"
    )
    assert detect_word_list_path(raw_root, grade="G6", semester="S1") == (
        raw_root / "07.六年级上册单词表.md"
    )
    assert default_general_draft_output_path(
        grade="G6",
        semester="S1",
        unit="U1",
        repo_root=Path(__file__).resolve().parents[3],
    ) == (
        Path(__file__).resolve().parents[3]
        / "app/knowledge/structured/general/g6s1u1-general.json"
    )
