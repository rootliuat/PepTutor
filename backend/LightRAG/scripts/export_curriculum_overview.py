#!/usr/bin/env python3
"""Export the PepTutor curriculum map as a human-readable Chinese overview."""

from __future__ import annotations

import argparse
from pathlib import Path

from lightrag.orchestrator.curriculum_map_builder import (
    CurriculumMapFile,
    default_curriculum_map_output_path,
)
from lightrag.orchestrator.curriculum_overview_builder import (
    build_curriculum_overview,
    default_curriculum_overview_output_path,
)


def main() -> int:
    args = _parse_args()
    repo_root = _repo_root()
    input_path = args.input.resolve() if args.input else default_curriculum_map_output_path(repo_root)
    output_path = args.output.resolve() if args.output else default_curriculum_overview_output_path(repo_root)

    curriculum_map = CurriculumMapFile.model_validate_json(
        input_path.read_text(encoding="utf-8")
    )
    overview = build_curriculum_overview(
        curriculum_map,
        max_vocabulary=args.max_vocabulary,
        max_patterns=args.max_patterns,
        max_targets=args.max_targets,
        max_sources=args.max_sources,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(overview, encoding="utf-8")
    print(output_path)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to app/knowledge/structured/curriculum-map.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults to app/knowledge/structured/curriculum-overview.zh.md.",
    )
    parser.add_argument(
        "--max-vocabulary",
        type=int,
        default=12,
        help="Maximum vocabulary items shown for each unit.",
    )
    parser.add_argument(
        "--max-patterns",
        type=int,
        default=8,
        help="Maximum sentence patterns shown for each unit.",
    )
    parser.add_argument(
        "--max-targets",
        type=int,
        default=4,
        help="Maximum structured learning targets shown for each unit.",
    )
    parser.add_argument(
        "--max-sources",
        type=int,
        default=4,
        help="Maximum source refs shown for each book or unit.",
    )
    return parser.parse_args()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


if __name__ == "__main__":
    raise SystemExit(main())
