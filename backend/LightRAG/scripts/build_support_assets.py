#!/usr/bin/env python3
"""Build deterministic support assets from raw markdown plus the approved pilot scope."""

from __future__ import annotations

import argparse
import json
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


def main() -> int:
    args = _parse_args()
    catalog = PilotLessonCatalog(manifest_path=args.manifest.resolve())
    assets = build_support_assets(
        asset_id=args.asset_id,
        catalog=catalog,
        word_sections=normalize_word_list_markdown(args.word_list.resolve()),
        useful_expressions=normalize_useful_expressions_markdown(
            args.useful_expressions.resolve()
        ),
    )
    payload = assets.model_dump(mode="json", exclude_none=True)

    output_path = args.output
    if args.repo_output:
        output_path = default_support_asset_output_path(args.asset_id)

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
    parser.add_argument("--manifest", type=Path, required=True, help="Approved pilot manifest")
    parser.add_argument("--word-list", type=Path, required=True, help="Raw markdown word list")
    parser.add_argument(
        "--useful-expressions",
        type=Path,
        required=True,
        help="Raw markdown useful expressions table",
    )
    parser.add_argument("--asset-id", required=True, help="Support asset identifier")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output path. Defaults to stdout.",
    )
    parser.add_argument(
        "--repo-output",
        action="store_true",
        help="Write to app/knowledge/structured/support/<asset-id>.json.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
