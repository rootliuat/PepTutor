#!/usr/bin/env python3
"""Convert cleaned RAGFlow chunks into PepTutor curriculum evidence chunks."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("temp/lesson-smoke-artifacts")
PAGE_UID_RE = re.compile(r"TB-G\dS\d(?:Recycle\d|U\d)-P\d+(?:-\d+)?", re.I)
BLOCK_UID_RE = re.compile(r"TB-G\dS\d(?:Recycle\d|U\d)-P\d+(?:-\d+)?-D\d+", re.I)
BOOK_RE = re.compile(r"\b(G\dS\d)\b", re.I)
UNIT_RE = re.compile(r"\b(U\d|Recycle\d)\b", re.I)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _text(chunk: dict[str, Any]) -> str:
    return " ".join(str(chunk.get("text") or chunk.get("content") or "").split())


def _first(pattern: re.Pattern[str], *values: str) -> str:
    for value in values:
        match = pattern.search(value or "")
        if match:
            return match.group(0)
    return ""


def _keywords(text: str) -> list[str]:
    candidates = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text)
    result = []
    for candidate in candidates:
        lowered = candidate.lower()
        if lowered not in result:
            result.append(lowered)
        if len(result) >= 12:
            break
    return result


def _chunk_type(text: str) -> str:
    lowered = text.lower()
    if "answer_scope" in lowered or "allowed_answer_scope" in lowered:
        return "answer_scope"
    if "phonics" in lowered or "blend" in lowered or "sound" in lowered:
        return "phonics"
    if "story" in lowered or "zoom" in lowered or "zip" in lowered:
        return "story"
    if "question" in lowered or "answer" in lowered:
        return "qa"
    return "evidence"


def _mapping_confidence(page_uid: str, block_uid: str, book_id: str, unit_id: str) -> str:
    if block_uid:
        return "exact"
    if page_uid:
        return "page_only"
    if book_id or unit_id:
        return "book_unit_only"
    return "unknown"


def convert_chunks(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = []
    for index, chunk in enumerate(payload.get("chunks", []), start=1):
        if not isinstance(chunk, dict):
            continue
        text = _text(chunk)
        source_file = str(chunk.get("source_document") or chunk.get("document_name") or chunk.get("source_file") or "")
        joined = f"{source_file}\n{text}"
        block_uid = _first(BLOCK_UID_RE, joined)
        page_uid = _first(PAGE_UID_RE, block_uid, joined)
        book_id = _first(BOOK_RE, page_uid, source_file, text).upper()
        unit_id = _first(UNIT_RE, page_uid, source_file, text).upper()
        ragflow_chunk_id = str(chunk.get("ragflow_chunk_id") or chunk.get("id") or chunk.get("chunk_id") or "")
        evidence.append(
            {
                "chunk_id": f"ragflow:{ragflow_chunk_id or index}",
                "source": "ragflow",
                "book_id": book_id,
                "unit_id": unit_id,
                "page_uid": page_uid,
                "block_uid": block_uid,
                "chunk_type": _chunk_type(text),
                "text": text,
                "keywords": _keywords(text),
                "source_file": source_file,
                "ragflow_document_id": str(chunk.get("ragflow_document_id") or chunk.get("document_id") or ""),
                "ragflow_chunk_id": ragflow_chunk_id,
                "mapping_confidence": _mapping_confidence(page_uid, block_uid, book_id, unit_id),
            }
        )
    return {
        "schema_version": "peptutor_ragflow_evidence_chunks_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_schema_version": payload.get("schema_version", ""),
        "chunk_count": len(evidence),
        "chunks": evidence,
    }


def mapping_summary(evidence_payload: dict[str, Any]) -> dict[str, Any]:
    counts = {"exact": 0, "page_only": 0, "book_unit_only": 0, "unknown": 0}
    anchors = {
        "TB-G5S1U3-P22": 0,
        "TB-G6S1U1-P4": 0,
        "TB-G6S2U1-P4": 0,
        "TB-G5S1U3-P31": 0,
        "TB-G5S2U1-P6": 0,
        "TB-G6S2U2-P13": 0,
    }
    for chunk in evidence_payload.get("chunks", []):
        confidence = chunk.get("mapping_confidence", "unknown")
        counts[confidence] = counts.get(confidence, 0) + 1
        page_uid = chunk.get("page_uid", "")
        if page_uid in anchors:
            anchors[page_uid] += 1
    return {
        "mapped_exact_count": counts.get("exact", 0),
        "mapped_page_only_count": counts.get("page_only", 0),
        "mapped_book_unit_only_count": counts.get("book_unit_only", 0),
        "unknown_count": counts.get("unknown", 0),
        "six_anchor_mapping_summary": anchors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(resolve_path(args.chunks).read_text(encoding="utf-8"))
    evidence = convert_chunks(payload)
    evidence["summary"] = mapping_summary(evidence)
    out_dir = resolve_path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"ragflow_peptutor_evidence_chunks_{timestamp()}.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
