#!/usr/bin/env python3
"""Build the compact PepTutor curriculum map from structured general drafts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lightrag.orchestrator.curriculum_map_builder import (
    build_curriculum_map,
    default_curriculum_map_output_path,
    default_general_manifest_path,
)


def main() -> int:
    args = _parse_args()
    repo_root = _repo_root()
    manifest_path = args.manifest.resolve() if args.manifest else default_general_manifest_path(repo_root)
    output_path = args.output.resolve() if args.output else default_curriculum_map_output_path(repo_root)
    raw_root = args.raw_root.resolve() if args.raw_root else repo_root / "app" / "knowledge" / "raw"

    curriculum_map = build_curriculum_map(
        manifest_path=manifest_path,
        raw_root=raw_root,
        repo_root=repo_root,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            curriculum_map.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Path to app/knowledge/structured/general/general-manifest.json.",
    )
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=None,
        help="Raw curriculum root used for Useful expressions lookup.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults to app/knowledge/structured/curriculum-map.json.",
    )
    return parser.parse_args()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


if __name__ == "__main__":
    raise SystemExit(main())
