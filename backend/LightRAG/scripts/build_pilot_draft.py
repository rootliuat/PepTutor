#!/usr/bin/env python3
"""Build a deterministic pilot draft from one raw textbook source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lightrag.orchestrator.pilot_draft_builder import (
    build_pilot_draft,
    default_pilot_draft_output_path,
)
from lightrag.orchestrator.raw_curriculum import normalize_textbook_source


def main() -> int:
    args = _parse_args()
    source_path = args.source.resolve()
    selected_pages = [
        page
        for page in normalize_textbook_source(source_path)
        if page.grade == args.grade
        and page.semester == args.semester
        and page.unit == args.unit
        and (not args.pages or page.page in args.pages)
    ]
    draft = build_pilot_draft(selected_pages, pilot_id=args.pilot_id)
    payload = draft.model_dump(mode="json", exclude_none=True)
    output_path = args.output
    if args.repo_output:
        output_path = default_pilot_draft_output_path(args.pilot_id)

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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Raw textbook source")
    parser.add_argument("--pilot-id", required=True, help="Draft pilot identifier")
    parser.add_argument("--grade", required=True, help="Grade, for example G5")
    parser.add_argument("--semester", required=True, help="Semester, for example S1")
    parser.add_argument("--unit", required=True, help="Unit, for example U3")
    parser.add_argument(
        "--pages",
        type=_parse_pages,
        default=None,
        help="Comma-separated page numbers, for example 24,25",
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
        help="Write to app/knowledge/structured/drafts/<pilot-id>.json.",
    )
    return parser.parse_args()


def _parse_pages(value: str) -> set[int]:
    pages = {int(part.strip()) for part in value.split(",") if part.strip()}
    if not pages:
        raise argparse.ArgumentTypeError("At least one page number is required")
    return pages


if __name__ == "__main__":
    raise SystemExit(main())
