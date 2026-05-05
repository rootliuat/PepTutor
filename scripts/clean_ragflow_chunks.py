#!/usr/bin/env python3
"""Clean exported RAGFlow chunks while preserving provenance hints."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("temp/lesson-smoke-artifacts")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _chunk_text(chunk: dict[str, Any]) -> str:
    return " ".join(str(chunk.get("content") or chunk.get("text") or "").split())


def clean_chunks(payload: dict[str, Any], *, min_chars: int = 20) -> dict[str, Any]:
    seen = set()
    cleaned = []
    dropped = {"empty": 0, "duplicate": 0, "too_short": 0}
    for chunk in payload.get("chunks", []):
        if not isinstance(chunk, dict):
            continue
        text = _chunk_text(chunk)
        if not text:
            dropped["empty"] += 1
            continue
        if len(text) < min_chars:
            dropped["too_short"] += 1
            continue
        key = text.casefold()
        if key in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(key)
        item = dict(chunk)
        item["text"] = text
        item.setdefault("source_document", chunk.get("document_name") or chunk.get("source_file") or "")
        item.setdefault("ragflow_chunk_id", chunk.get("id") or chunk.get("chunk_id") or "")
        item.setdefault("ragflow_document_id", chunk.get("document_id") or "")
        cleaned.append(item)
    return {
        "schema_version": "ragflow_chunks_clean_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_schema_version": payload.get("schema_version", ""),
        "input_chunk_count": len(payload.get("chunks", [])),
        "clean_chunk_count": len(cleaned),
        "dropped_counts": dropped,
        "chunks": cleaned,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--min-chars", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(resolve_path(args.chunks).read_text(encoding="utf-8"))
    cleaned = clean_chunks(payload, min_chars=args.min_chars)
    out_dir = resolve_path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"ragflow_chunks_clean_{timestamp()}.json"
    path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
