#!/usr/bin/env python3
"""Build all configured PepTutor general drafts and emit a manifest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from lightrag.orchestrator.general_draft_builder import (
    build_general_draft,
    default_general_draft_output_path,
    detect_word_list_path,
    select_general_scope_pages,
)
from lightrag.orchestrator.raw_curriculum import (
    normalize_textbook_source,
    normalize_word_list_markdown,
)


@dataclass(frozen=True)
class ScopeBuildSpec:
    scope: str
    page_numbers: tuple[int, ...] | None = None


@dataclass(frozen=True)
class VolumeBuildSpec:
    source_name: str
    grade: str
    semester: str
    scopes: tuple[ScopeBuildSpec, ...]


VOLUME_SPECS: tuple[VolumeBuildSpec, ...] = (
    VolumeBuildSpec(
        source_name="01.五年级上册语料.js",
        grade="G5",
        semester="S1",
        scopes=(
            ScopeBuildSpec("U1", tuple(range(2, 12))),
            ScopeBuildSpec("U2", tuple(range(12, 22))),
            ScopeBuildSpec("U3", tuple(range(22, 32))),
            ScopeBuildSpec("Recycle1", tuple(range(32, 36))),
            ScopeBuildSpec("U4", tuple(range(36, 46))),
            ScopeBuildSpec("U5", tuple(range(46, 56))),
            ScopeBuildSpec("U6", tuple(range(56, 66))),
            # Raw G5 S1 stores the closing recycle spread as a single P68-69 page with no numeric page.
            ScopeBuildSpec("Recycle2"),
        ),
    ),
    VolumeBuildSpec(
        source_name="02.五年级下册语料.js",
        grade="G5",
        semester="S2",
        scopes=(
            ScopeBuildSpec("U1", tuple(range(2, 12))),
            ScopeBuildSpec("U2", tuple(range(12, 22))),
            ScopeBuildSpec("U3", tuple(range(22, 32))),
            ScopeBuildSpec("Recycle1", tuple(range(32, 36))),
            ScopeBuildSpec("U4", tuple(range(36, 46))),
            ScopeBuildSpec("U5", tuple(range(46, 56))),
            ScopeBuildSpec("U6", tuple(range(56, 66))),
            ScopeBuildSpec("Recycle2", tuple(range(66, 70))),
        ),
    ),
    VolumeBuildSpec(
        source_name="03.六年级上册语料.json",
        grade="G6",
        semester="S1",
        scopes=(
            ScopeBuildSpec("U1", tuple(range(2, 12))),
            ScopeBuildSpec("U2", tuple(range(12, 22))),
            ScopeBuildSpec("U3", tuple(range(22, 32))),
            ScopeBuildSpec("Recycle1", tuple(range(32, 36))),
            ScopeBuildSpec("U4", tuple(range(36, 46))),
            ScopeBuildSpec("U5", tuple(range(46, 56))),
            ScopeBuildSpec("U6", tuple(range(56, 66))),
            ScopeBuildSpec("Recycle2", tuple(range(66, 70))),
        ),
    ),
    VolumeBuildSpec(
        source_name="04.六年级下册语料.json",
        grade="G6",
        semester="S2",
        scopes=(
            ScopeBuildSpec("U1", tuple(range(2, 12))),
            ScopeBuildSpec("U2", tuple(range(12, 22))),
            ScopeBuildSpec("U3", tuple(range(22, 32))),
            ScopeBuildSpec("U4", tuple(range(32, 42))),
            ScopeBuildSpec("Recycle1", tuple(range(42, 48))),
            ScopeBuildSpec("Recycle2", (48, 49, 50, 51)),
        ),
    ),
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    raw_root = repo_root / "app" / "knowledge" / "raw"
    output_root = repo_root / "app" / "knowledge" / "structured" / "general"
    manifest_path = output_root / "general-manifest.json"
    report_path = output_root / "general-build-report.json"

    output_root.mkdir(parents=True, exist_ok=True)
    manifest_files: list[str] = []
    report_volumes: list[dict] = []

    for spec in VOLUME_SPECS:
        source_path = (raw_root / spec.source_name).resolve()
        normalized_pages = normalize_textbook_source(source_path)
        word_list_path = detect_word_list_path(
            raw_root,
            grade=spec.grade,
            semester=spec.semester,
        )
        word_list_sections = (
            normalize_word_list_markdown(word_list_path)
            if word_list_path is not None
            else []
        )

        assigned_pages: set[int] = set()
        scope_reports: list[dict] = []

        for scope_spec in spec.scopes:
            selected_pages = select_general_scope_pages(
                normalized_pages,
                grade=spec.grade,
                semester=spec.semester,
                unit=scope_spec.scope,
                page_numbers=scope_spec.page_numbers,
            )
            assigned_pages.update(
                page.page for page in selected_pages if page.page is not None
            )

            draft_id = (
                f"{spec.grade.lower()}{spec.semester.lower()}{scope_spec.scope.lower()}-general-v1"
            )
            output_path = default_general_draft_output_path(
                grade=spec.grade,
                semester=spec.semester,
                unit=scope_spec.scope,
                repo_root=repo_root,
            )
            draft = build_general_draft(
                selected_pages,
                draft_id=draft_id,
                source_files=_build_source_files(
                    repo_root=repo_root,
                    source_path=source_path,
                    word_list_path=word_list_path,
                ),
                word_list_sections=word_list_sections,
                display_name=selected_pages[0].book,
            )
            output_path.write_text(
                json.dumps(draft.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
            manifest_files.append(output_path.relative_to(manifest_path.parent).as_posix())
            scope_reports.append(
                {
                    "scope": scope_spec.scope,
                    "draft_id": draft_id,
                    "pages": list(draft.scope.pages),
                    "page_uids": [page.page_uid for page in draft.page_lessons],
                    "teaching_block_count": len(draft.teaching_blocks),
                    "wordlist_entry_count": len(draft.wordlist_entries),
                }
            )

        report_volumes.append(
            {
                "source_file": source_path.relative_to(repo_root).as_posix(),
                "grade": spec.grade,
                "semester": spec.semester,
                "word_list_file": (
                    word_list_path.relative_to(repo_root).as_posix()
                    if word_list_path is not None
                    else None
                ),
                "scopes": scope_reports,
                "unassigned_main_pages": _find_unassigned_main_pages(
                    normalized_pages=normalized_pages,
                    assigned_pages=assigned_pages,
                ),
            }
        )

    manifest_payload = {
        "kind": "peptutor_general_manifest",
        "generated_at": datetime.now(UTC).isoformat(),
        "files": manifest_files,
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report_payload = {
        "kind": "peptutor_general_build_report",
        "generated_at": datetime.now(UTC).isoformat(),
        "volumes": report_volumes,
    }
    report_path.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(manifest_path)
    print(report_path)
    return 0


def _build_source_files(
    *,
    repo_root: Path,
    source_path: Path,
    word_list_path: Path | None,
) -> list[str]:
    files = [source_path.relative_to(repo_root).as_posix()]
    if word_list_path is not None:
        files.append(word_list_path.relative_to(repo_root).as_posix())
    return files


def _find_unassigned_main_pages(
    *,
    normalized_pages,
    assigned_pages: set[int],
) -> list[dict]:
    result: list[dict] = []
    for page in normalized_pages:
        if page.page is None:
            continue
        if page.page in assigned_pages:
            continue
        unit = page.unit or ""
        if unit == "U0" or unit.startswith("A") or unit.startswith("Appendix"):
            continue
        result.append(
            {
                "page": page.page,
                "page_uid": page.page_uid,
                "raw_unit": page.unit,
                "raw_theme": page.theme,
            }
        )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
