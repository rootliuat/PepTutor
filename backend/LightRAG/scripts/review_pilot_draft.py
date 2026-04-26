#!/usr/bin/env python3
"""Generate a markdown review report comparing an approved pilot and a draft."""

from __future__ import annotations

import argparse
from pathlib import Path

from lightrag.orchestrator.pilot_draft_review import (
    compare_pilot_and_draft,
    render_comparison_markdown,
)


def main() -> int:
    args = _parse_args()
    report = compare_pilot_and_draft(args.pilot.resolve(), args.draft.resolve())
    markdown = render_comparison_markdown(report)

    if args.output is None:
        print(markdown, end="")
        return 0

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(output_path)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True, help="Approved pilot JSON")
    parser.add_argument("--draft", type=Path, required=True, help="Deterministic draft JSON")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional markdown output path. Defaults to stdout.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
