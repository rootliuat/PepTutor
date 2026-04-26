#!/usr/bin/env python3
"""Run the lesson dialogue quality gold-set evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lightrag.orchestrator.lesson_dialogue_quality_eval import (
    default_dialogue_quality_gold_path,
    default_manifest_path,
    evaluate_lesson_dialogue_quality,
    render_dialogue_quality_eval_report,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gold-path",
        type=Path,
        default=default_dialogue_quality_gold_path(),
        help="Path to the dialogue quality gold JSON file.",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=default_manifest_path(),
        help="Path to the lesson manifest JSON file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full report as JSON instead of a text summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = evaluate_lesson_dialogue_quality(
        gold_path=args.gold_path,
        manifest_path=args.manifest_path,
    )

    if args.json:
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        print(render_dialogue_quality_eval_report(report))

    return 0 if not report.failed_outcomes else 1


if __name__ == "__main__":
    raise SystemExit(main())
