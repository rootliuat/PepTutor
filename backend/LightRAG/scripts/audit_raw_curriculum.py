#!/usr/bin/env python3
"""Print a JSON audit summary for PepTutor raw curriculum assets."""

from __future__ import annotations

import argparse
from pathlib import Path

from lightrag.orchestrator.raw_curriculum import audit_raw_assets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-root",
        default="../../../app/knowledge/raw",
        help="Path to the raw curriculum root relative to this script",
    )
    args = parser.parse_args()

    raw_root = (Path(__file__).resolve().parent / args.raw_root).resolve()
    report = audit_raw_assets(raw_root)
    print(report.model_dump_json(indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
