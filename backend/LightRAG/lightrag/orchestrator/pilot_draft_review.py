"""Review helpers for deterministic draft vs approved pilot comparison."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class RecordDifference(BaseModel):
    """One shared record with field coverage and value differences."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    missing_fields_in_draft: list[str] = Field(default_factory=list)
    extra_fields_in_draft: list[str] = Field(default_factory=list)
    differing_fields: list[str] = Field(default_factory=list)


class SectionComparison(BaseModel):
    """Comparison summary for page_lessons or teaching_blocks."""

    model_config = ConfigDict(extra="forbid")

    section_name: str
    pilot_count: int
    draft_count: int
    pilot_only_ids: list[str] = Field(default_factory=list)
    draft_only_ids: list[str] = Field(default_factory=list)
    differing_records: list[RecordDifference] = Field(default_factory=list)


class PilotDraftComparison(BaseModel):
    """High-level comparison between an approved pilot and a deterministic draft."""

    model_config = ConfigDict(extra="forbid")

    pilot_path: str
    draft_path: str
    missing_top_level_in_draft: list[str] = Field(default_factory=list)
    extra_top_level_in_draft: list[str] = Field(default_factory=list)
    differing_top_level_fields: list[str] = Field(default_factory=list)
    sections: list[SectionComparison] = Field(default_factory=list)


def compare_pilot_and_draft(
    pilot_path: Path,
    draft_path: Path,
) -> PilotDraftComparison:
    """Compare one approved pilot file with one deterministic draft file."""
    approved = json.loads(pilot_path.read_text(encoding="utf-8"))
    draft = json.loads(draft_path.read_text(encoding="utf-8"))

    sections = [
        _compare_section("page_lessons", approved.get("page_lessons", []), draft.get("page_lessons", [])),
        _compare_section(
            "teaching_blocks",
            approved.get("teaching_blocks", []),
            draft.get("teaching_blocks", []),
        ),
    ]

    return PilotDraftComparison(
        pilot_path=str(pilot_path.resolve()),
        draft_path=str(draft_path.resolve()),
        missing_top_level_in_draft=sorted(set(approved) - set(draft)),
        extra_top_level_in_draft=sorted(set(draft) - set(approved)),
        differing_top_level_fields=sorted(
            key
            for key in set(approved) & set(draft)
            if key not in {"pilot_id", "page_lessons", "teaching_blocks"}
            and approved[key] != draft[key]
        ),
        sections=sections,
    )


def render_comparison_markdown(report: PilotDraftComparison) -> str:
    """Render a compact markdown review report for human inspection."""
    lines = [
        "# Pilot Draft Review",
        "",
        f"- Pilot: `{report.pilot_path}`",
        f"- Draft: `{report.draft_path}`",
        "",
        "## Top-Level",
        "",
        f"- Missing in draft: {_format_list(report.missing_top_level_in_draft)}",
        f"- Extra in draft: {_format_list(report.extra_top_level_in_draft)}",
        f"- Differing values: {_format_list(report.differing_top_level_fields)}",
    ]

    for section in report.sections:
        lines.extend(
            [
                "",
                f"## {section.section_name}",
                "",
                f"- Pilot count: {section.pilot_count}",
                f"- Draft count: {section.draft_count}",
                f"- Pilot-only ids: {_format_list(section.pilot_only_ids)}",
                f"- Draft-only ids: {_format_list(section.draft_only_ids)}",
            ]
        )
        if not section.differing_records:
            lines.append("- Shared record differences: none")
            continue

        lines.append("- Shared record differences:")
        for diff in section.differing_records:
            lines.append(f"  - `{diff.record_id}`")
            lines.append(
                "    - Missing fields in draft: "
                + _format_list(diff.missing_fields_in_draft)
            )
            lines.append(
                "    - Extra fields in draft: "
                + _format_list(diff.extra_fields_in_draft)
            )
            lines.append(
                "    - Differing fields: " + _format_list(diff.differing_fields)
            )

    return "\n".join(lines) + "\n"


def _compare_section(
    section_name: str,
    approved_records: list[dict],
    draft_records: list[dict],
) -> SectionComparison:
    approved_map = {_record_id(item): item for item in approved_records}
    draft_map = {_record_id(item): item for item in draft_records}

    differing_records: list[RecordDifference] = []
    for record_id in sorted(set(approved_map) & set(draft_map)):
        approved_item = approved_map[record_id]
        draft_item = draft_map[record_id]
        missing_fields = sorted(set(approved_item) - set(draft_item))
        extra_fields = sorted(set(draft_item) - set(approved_item))
        differing_fields = sorted(
            key
            for key in set(approved_item) & set(draft_item)
            if approved_item[key] != draft_item[key]
        )
        if missing_fields or extra_fields or differing_fields:
            differing_records.append(
                RecordDifference(
                    record_id=record_id,
                    missing_fields_in_draft=missing_fields,
                    extra_fields_in_draft=extra_fields,
                    differing_fields=differing_fields,
                )
            )

    return SectionComparison(
        section_name=section_name,
        pilot_count=len(approved_records),
        draft_count=len(draft_records),
        pilot_only_ids=sorted(set(approved_map) - set(draft_map)),
        draft_only_ids=sorted(set(draft_map) - set(approved_map)),
        differing_records=differing_records,
    )


def _record_id(item: dict) -> str:
    record_id = item.get("block_uid") or item.get("page_uid")
    if not isinstance(record_id, str) or not record_id:
        raise ValueError(f"Unable to infer record id from item: {item}")
    return record_id


def _format_list(values: list[str]) -> str:
    if not values:
        return "none"
    return ", ".join(f"`{value}`" for value in values)
