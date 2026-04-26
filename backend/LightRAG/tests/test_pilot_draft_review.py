from pathlib import Path

from lightrag.orchestrator.pilot_draft_review import (
    compare_pilot_and_draft,
    render_comparison_markdown,
)


def _structured_root() -> Path:
    return (Path(__file__).resolve().parents[3] / "app" / "knowledge" / "structured").resolve()


def test_compare_pilot_and_draft_flags_known_top_level_and_field_gaps():
    structured_root = _structured_root()
    report = compare_pilot_and_draft(
        structured_root / "g5s1u3-p24-p25-pilot.json",
        structured_root / "drafts/g5s1u3-p24-p25-draft.json",
    )

    assert report.missing_top_level_in_draft == []
    assert report.extra_top_level_in_draft == []
    assert report.differing_top_level_fields == []

    page_section = next(
        section for section in report.sections if section.section_name == "page_lessons"
    )
    block_section = next(
        section for section in report.sections if section.section_name == "teaching_blocks"
    )

    assert page_section.pilot_only_ids == []
    assert page_section.draft_only_ids == []
    assert [(diff.record_id, diff.differing_fields) for diff in page_section.differing_records] == [
        ("TB-G5S1U3-P24", ["entry_probe_questions", "page_intro_cn"]),
        ("TB-G5S1U3-P25", ["entry_probe_questions", "page_intro_cn"]),
    ]
    assert [(diff.record_id, diff.differing_fields) for diff in block_section.differing_records] == [
        ("TB-G5S1U3-P24-D1", ["entry_probe_questions", "teaching_goal", "teaching_summary"]),
        (
            "TB-G5S1U3-P24-D2",
            ["allowed_answer_scope", "entry_probe_questions", "teaching_goal", "teaching_summary"],
        ),
        ("TB-G5S1U3-P24-D3", ["entry_probe_questions", "teaching_goal", "teaching_summary"]),
        ("TB-G5S1U3-P24-D4", ["entry_probe_questions", "teaching_goal", "teaching_summary"]),
        (
            "TB-G5S1U3-P25-D1",
            ["branchable_topics", "entry_probe_questions", "teaching_goal", "teaching_summary"],
        ),
        ("TB-G5S1U3-P25-D2", ["entry_probe_questions", "teaching_goal", "teaching_summary"]),
        ("TB-G5S1U3-P25-D3", ["entry_probe_questions", "teaching_goal", "teaching_summary"]),
    ]


def test_render_comparison_markdown_mentions_known_missing_fields():
    structured_root = _structured_root()
    report = compare_pilot_and_draft(
        structured_root / "g5s1u3-p24-p25-pilot.json",
        structured_root / "drafts/g5s1u3-p24-p25-draft.json",
    )

    markdown = render_comparison_markdown(report)

    assert "# Pilot Draft Review" in markdown
    assert "- Differing values: none" in markdown
    assert "## page_lessons" in markdown
    assert "## teaching_blocks" in markdown
    assert "- Shared record differences:" in markdown
    assert "TB-G5S1U3-P24-D4" in markdown
    assert "`entry_probe_questions`, `page_intro_cn`" in markdown
