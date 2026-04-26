#!/usr/bin/env python3
"""Build a generic structured lesson draft from one raw textbook source."""

from __future__ import annotations

import argparse
import json
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


def main() -> int:
    args = _parse_args()
    source_path = args.source.resolve()
    raw_root = args.raw_root.resolve()
    normalized_pages = normalize_textbook_source(source_path)
    selected_pages = select_general_scope_pages(
        normalized_pages,
        grade=args.grade,
        semester=args.semester,
        unit=args.unit,
    )
    if not selected_pages:
        raise SystemExit(
            f"No main textbook pages found for {args.grade} {args.semester} {args.unit}"
        )

    word_list_path = args.word_list
    if word_list_path is None:
        word_list_path = detect_word_list_path(
            raw_root,
            grade=args.grade,
            semester=args.semester,
        )
    word_list_sections = (
        normalize_word_list_markdown(word_list_path) if word_list_path is not None else []
    )

    draft = build_general_draft(
        selected_pages,
        draft_id=args.draft_id,
        source_files=_build_source_files(
            source_path=source_path,
            repo_root=_repo_root(),
            word_list_path=word_list_path,
        ),
        word_list_sections=word_list_sections,
        display_name=selected_pages[0].book,
    )
    payload = draft.model_dump(mode="json", exclude_none=True)

    output_path = args.output
    if args.repo_output:
        output_path = default_general_draft_output_path(
            grade=args.grade,
            semester=args.semester,
            unit=args.unit,
        )

    if output_path is None:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


def _build_source_files(
    *,
    source_path: Path,
    repo_root: Path,
    word_list_path: Path | None,
) -> list[str]:
    source_files = [source_path.resolve().relative_to(repo_root).as_posix()]
    if word_list_path is not None:
        source_files.append(word_list_path.resolve().relative_to(repo_root).as_posix())
    return source_files


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Raw textbook source file")
    parser.add_argument("--grade", required=True, help="Grade, for example G6")
    parser.add_argument("--semester", required=True, help="Semester, for example S1")
    parser.add_argument(
        "--unit",
        required=True,
        help="Unit or recycle scope, for example U1 or Recycle1",
    )
    parser.add_argument(
        "--draft-id",
        required=True,
        help="Structured draft identifier",
    )
    parser.add_argument(
        "--word-list",
        type=Path,
        default=None,
        help="Optional word-list markdown. Auto-detected when omitted.",
    )
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=Path("app/knowledge/raw"),
        help="Raw curriculum root used for auto-detecting the word list.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output path. Defaults to stdout.",
    )
    parser.add_argument(
        "--repo-output",
        action="store_true",
        help="Write to app/knowledge/structured/general/<grade><semester><unit>-general.json.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
