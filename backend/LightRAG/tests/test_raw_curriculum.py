import json
from pathlib import Path

from lightrag.orchestrator.raw_curriculum import (
    audit_raw_assets,
    infer_raw_asset_kind,
    load_textbook_source,
    normalize_textbook_source,
    normalize_useful_expressions_markdown,
    normalize_word_list_markdown,
)


def _raw_root() -> Path:
    return (
        Path(__file__).resolve().parents[3] / "app" / "knowledge" / "raw"
    ).resolve()


def _page_by_uid(pages, page_uid: str):
    return next(page for page in pages if page.page_uid == page_uid)


def _block_by_uid(page, block_uid: str):
    return next(block for block in page.blocks if block.block_uid == block_uid)


def test_infer_raw_asset_kind_matches_current_filename_conventions():
    assert infer_raw_asset_kind(Path("01.五年级上册语料.js")) == "textbook_source_js"
    assert infer_raw_asset_kind(Path("03.六年级上册语料.json")) == "textbook_source_json"
    assert infer_raw_asset_kind(Path("05.五年级上册单词表.md")) == "word_list_markdown"
    assert (
        infer_raw_asset_kind(Path("09.五年级上册Useful expressions.md"))
        == "useful_expressions_markdown"
    )
    assert (
        infer_raw_asset_kind(Path("13.六年级下册Irregular verbs.md"))
        == "irregular_verbs_markdown"
    )


def test_audit_raw_assets_counts_current_raw_inventory():
    report = audit_raw_assets(_raw_root())

    assert report.total_files == 15
    assert report.kind_counts["textbook_source_js"] == 2
    assert report.kind_counts["textbook_source_json"] == 2
    assert report.kind_counts["unknown"] == 1
    assert report.kind_counts["word_list_markdown"] == 4
    assert report.kind_counts["useful_expressions_markdown"] == 4
    assert report.kind_counts["irregular_verbs_markdown"] == 1
    assert report.kind_counts["pronunciation_patterns_json"] == 1
    assert report.zero_byte_paths == []


def test_pronunciation_patterns_asset_is_present_and_non_empty():
    path = _raw_root() / "14.六年级下册English pronunciation patterns.json"

    data = json.loads(path.read_text(encoding="utf-8"))

    assert len(data) == 1
    entry = data[0]
    assert entry["metadata"]["uid"] == "PP-G6S2Recycle2-P49"
    assert entry["metadata"]["source_page_uid"] == "TB-G6S2Recycle2-P49"
    assert [block["source_block_uid"] for block in entry["content_blocks"]] == [
        "TB-G6S2Recycle2-P49-D2",
        "TB-G6S2Recycle2-P49-D3",
    ]


def test_normalize_textbook_source_supports_pronunciation_patterns_json():
    pages = normalize_textbook_source(
        _raw_root() / "14.六年级下册English pronunciation patterns.json"
    )

    assert len(pages) == 1
    page = pages[0]
    assert page.page_uid == "PP-G6S2Recycle2-P49"
    assert page.source_kind == "pronunciation_patterns_json"
    assert page.page_type_hint == "phonics"
    assert page.block_types == ["practice_write", "phonics"]


def test_load_textbook_source_supports_real_js_and_json_assets():
    raw_root = _raw_root()

    js_pages = load_textbook_source(raw_root / "01.五年级上册语料.js")
    json_pages = load_textbook_source(raw_root / "03.六年级上册语料.json")

    assert len(js_pages) > 1
    assert js_pages[0].metadata.grade == "G5"
    assert js_pages[0].metadata.semester == "S1"
    assert js_pages[0].content_blocks[0].type == "table_of_contents"

    assert len(json_pages) > 1
    assert json_pages[0].metadata.grade == "G6"
    assert json_pages[0].metadata.semester == "S1"
    assert json_pages[1].content_blocks[0].type == "dialogue_core"


def test_normalize_textbook_source_extracts_real_g5_s1_u3_page_signals():
    pages = normalize_textbook_source(_raw_root() / "01.五年级上册语料.js")

    page24 = _page_by_uid(pages, "TB-G5S1U3-P24")
    page25 = _page_by_uid(pages, "TB-G5S1U3-P25")

    assert page24.source_kind == "textbook_source_js"
    assert page24.source_format == "js"
    assert page24.page_type_hint == "dialogue"
    assert page24.block_types == [
        "listening_exercise",
        "dialogue_core",
        "dialogue_practice",
    ]

    d1 = _block_by_uid(page24, "TB-G5S1U3-P24-D1")
    assert d1.questions[0].prompt == "She would like some ______ and ______."
    assert d1.questions[0].answer == "bread, noodles"
    assert d1.word_bank == ["bread", "noodles", "chicken"]

    d2 = _block_by_uid(page24, "TB-G5S1U3-P24-D2")
    assert {item.word for item in d2.vocabulary} >= {
        "hungry",
        "sandwich",
        "drink",
        "water",
        "thirsty",
    }
    assert {pattern.english for pattern in d2.patterns} == {
        "What would you like to eat?",
        "What would you like to drink?",
    }
    assert d2.dialogue_lines[0].english == "I'm hungry."
    assert d2.dialogue_lines[-1].english == "Thanks."

    assert page25.page_type_hint == "vocabulary"
    d3 = _block_by_uid(page25, "TB-G5S1U3-P25-D3")
    assert d3.templates == [
        "My order\nFood: ____\nDrink: ____\n\n____'s order\nFood: ____\nDrink: ____"
    ]


def test_normalize_textbook_source_supports_real_json_nested_examples():
    pages = normalize_textbook_source(_raw_root() / "03.六年级上册语料.json")

    page19 = _page_by_uid(pages, "TB-G6S1U2-P19")
    block = _block_by_uid(page19, "TB-G6S1U2-P19-D2")

    assert page19.source_kind == "textbook_source_json"
    assert page19.source_format == "json"
    assert page19.page_type_hint == "grammar"
    assert page19.theme == "Ways to go to school"
    assert {pattern.english for pattern in block.patterns} >= {
        "You must ...",
        "Don't ...",
        "On foot: You must stop at a red light.",
        "By subway: Don't run on the subway.",
    }
    assert "Traffic Rules Suggestions" in block.prompts
    assert "Choose some suggestions for the kids on page 18." in block.prompts


def test_normalize_word_list_markdown_extracts_real_unit_sections():
    sections = normalize_word_list_markdown(_raw_root() / "05.五年级上册单词表.md")

    assert [section.unit for section in sections[:3]] == ["Unit 1", "Unit 2", "Unit 3"]

    unit3 = next(section for section in sections if section.unit == "Unit 3")
    sandwich = next(entry for entry in unit3.entries if entry.word == "sandwich")
    ice_cream = next(entry for entry in unit3.entries if entry.word == "ice cream")
    dear = next(entry for entry in unit3.entries if entry.word == "Dear")

    assert sandwich.phonetic == "/'sænwɪtʃ/"
    assert sandwich.chinese == "三明治"
    assert sandwich.emphasized is True
    assert ice_cream.phonetic == "/ˌaɪs'kriːm/"
    assert dear.chinese.startswith("（用于信函抬头")


def test_normalize_useful_expressions_markdown_extracts_real_rows():
    entries = normalize_useful_expressions_markdown(_raw_root() / "09.五年级上册Useful expressions.md")

    unit3_entries = [entry for entry in entries if entry.unit == "Unit 3"]
    first_unit3 = unit3_entries[0]
    water_reply = next(
        entry for entry in unit3_entries if entry.english == "I'd like some water."
    )

    assert first_unit3.english == "What would you like to eat?"
    assert first_unit3.chinese == "你想吃什么？"
    assert first_unit3.page_ref == "p.24"
    assert first_unit3.emphasized is True
    assert water_reply.chinese == "我想喝点水。"
    assert water_reply.page_ref == "p.24"
