#!/usr/bin/env python3
"""Export RAGFlow chunks into a local generated artifact."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from lib.ragflow_client import RAGFlowClient, RAGFlowConfig


DEFAULT_OUT_DIR = Path("temp/lesson-smoke-artifacts")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", default="")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = RAGFlowConfig.from_env()
    client = RAGFlowClient(config)
    chunks = client.export_chunks(dataset_id=args.dataset_id or None)
    payload = {
        "schema_version": "ragflow_chunks_export_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "ragflow",
        "dataset_id": args.dataset_id or config.dataset_id,
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
    out_dir = resolve_path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"ragflow_chunks_{timestamp()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
