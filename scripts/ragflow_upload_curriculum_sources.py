#!/usr/bin/env python3
"""Plan or upload selected PepTutor curriculum evidence sources to RAGFlow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lib.ragflow_client import RAGFlowClient, RAGFlowConfig, RAGFlowError


DEFAULT_DOCS = (
    "docs/curriculum-graph-audit-summary-20260505.md",
    "docs/curriculum-graph-findings-triage-20260505.md",
    "docs/curriculum-data-tightening-candidates-20260505.md",
)
RAW_EXTENSIONS = {".md", ".txt"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def rel_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root()))
    except ValueError:
        return str(path)


def discover_candidates(*, include_raw: bool = True, raw_limit: int = 20) -> list[Path]:
    root = repo_root()
    paths = [root / item for item in DEFAULT_DOCS if (root / item).is_file()]
    if include_raw:
        raw_root = root / "app/knowledge/raw"
        raw_files = sorted(
            path for path in raw_root.rglob("*") if path.is_file() and path.suffix.lower() in RAW_EXTENSIONS
        )
        paths.extend(raw_files[:raw_limit])
    return paths


def build_upload_plan(paths: list[Path]) -> dict[str, Any]:
    skipped = []
    upload = []
    for path in paths:
        rel = rel_path(path)
        if rel.startswith("temp/lesson-smoke-artifacts/"):
            skipped.append({"path": rel, "reason": "generated smoke/audit artifact"})
            continue
        if path.suffix.lower() == ".json":
            skipped.append({"path": rel, "reason": "raw JSON artifacts are excluded"})
            continue
        upload.append({"path": rel, "bytes": path.stat().st_size})
    return {"upload_candidates": upload, "skipped": skipped}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Only print upload plan. Default.")
    mode.add_argument("--commit", action="store_true", help="Upload candidates to configured RAGFlow dataset.")
    parser.add_argument("--no-raw", action="store_true", help="Do not include selected raw markdown/text files.")
    parser.add_argument("--raw-limit", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = discover_candidates(include_raw=not args.no_raw, raw_limit=max(args.raw_limit, 0))
    plan = build_upload_plan(paths)
    if not args.commit:
        print(json.dumps({"mode": "dry_run", **plan}, ensure_ascii=False, indent=2))
        return

    client = RAGFlowClient(RAGFlowConfig.from_env())
    uploaded = []
    errors = []
    for item in plan["upload_candidates"]:
        try:
            response = client.upload_document(repo_root() / item["path"])
            uploaded.append({"path": item["path"], "response": response})
        except RAGFlowError as exc:
            errors.append({"path": item["path"], "error": str(exc)})
    print(json.dumps({"mode": "commit", **plan, "uploaded": uploaded, "errors": errors}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
