#!/usr/bin/env python3
"""Build a local curriculum evidence index from structured, audit, candidate, and RAGFlow evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("temp/lesson-smoke-artifacts")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def rel_path(path: Path) -> str:
    resolved = resolve_path(path)
    try:
        return str(resolved.relative_to(repo_root()))
    except ValueError:
        return str(resolved)


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _load_json(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    resolved = resolve_path(path)
    if not resolved.is_file():
        return {}
    return json.loads(resolved.read_text(encoding="utf-8"))


def _latest(pattern: str) -> Path | None:
    matches = sorted((repo_root() / "temp/lesson-smoke-artifacts").glob(pattern), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def _latest_graph() -> Path | None:
    matches = [
        path
        for path in (repo_root() / "temp/lesson-smoke-artifacts").glob("curriculum_graph_*.json")
        if not path.name.startswith("curriculum_graph_audit_")
    ]
    matches = sorted(matches, key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def _evidence_id(source: str, index: int, key: str = "") -> str:
    suffix = key.replace(":", "-").replace("/", "-")[:80] or str(index)
    return f"{source}:{suffix}"


def build_evidence_index(
    *,
    graph: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
    candidates: dict[str, Any] | None = None,
    ragflow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    graph = graph or {}
    audit = audit or {}
    candidates = candidates or {}
    ragflow = ragflow or {}

    for index, node in enumerate(graph.get("nodes", []), start=1):
        if node.get("type") not in {"Block", "QuestionTarget", "AnswerFrame", "AnswerScope", "ReturnAnchor"}:
            continue
        entries.append(
            {
                "evidence_id": _evidence_id("structured", index, node.get("id", "")),
                "source": "structured",
                "source_ref": node.get("id", ""),
                "page_uid": node.get("page_uid", ""),
                "block_uid": node.get("block_uid", ""),
                "evidence_type": node.get("type", ""),
                "text": node.get("label") or node.get("properties", {}).get("teaching_goal") or "",
                "canonical_priority": "canonical",
            }
        )

    for index, finding in enumerate(audit.get("findings", []), start=1):
        entries.append(
            {
                "evidence_id": _evidence_id("audit", index, finding.get("node_id", "")),
                "source": "audit",
                "source_ref": finding.get("current_issue_rule") or finding.get("rule", ""),
                "page_uid": finding.get("page_uid", ""),
                "block_uid": finding.get("block_uid", ""),
                "evidence_type": finding.get("rule", ""),
                "text": finding.get("message", ""),
                "canonical_priority": "supporting",
            }
        )

    for candidate in candidates.get("candidates", []):
        entries.append(
            {
                "evidence_id": f"candidate:{candidate.get('candidate_id', '')}",
                "source": "candidate",
                "source_ref": candidate.get("candidate_id", ""),
                "page_uid": candidate.get("page_uid", ""),
                "block_uid": candidate.get("block_uid", ""),
                "evidence_type": candidate.get("class", ""),
                "text": candidate.get("suggested_action", ""),
                "canonical_priority": "review_only",
            }
        )

    for chunk in ragflow.get("chunks", []):
        entries.append(
            {
                "evidence_id": chunk.get("chunk_id", ""),
                "source": "ragflow",
                "source_ref": chunk.get("ragflow_chunk_id", ""),
                "page_uid": chunk.get("page_uid", ""),
                "block_uid": chunk.get("block_uid", ""),
                "evidence_type": chunk.get("chunk_type", "evidence"),
                "text": chunk.get("text", ""),
                "canonical_priority": "supporting",
                "mapping_confidence": chunk.get("mapping_confidence", "unknown"),
            }
        )

    for path in [
        "docs/curriculum-graph-audit-summary-20260505.md",
        "docs/curriculum-data-tightening-candidates-20260505.md",
    ]:
        resolved = repo_root() / path
        if resolved.is_file():
            entries.append(
                {
                    "evidence_id": f"raw:{path}",
                    "source": "raw",
                    "source_ref": path,
                    "page_uid": "",
                    "block_uid": "",
                    "evidence_type": "summary_doc",
                    "text": resolved.read_text(encoding="utf-8")[:2000],
                    "canonical_priority": "supporting",
                }
            )

    counts = Counter(entry["source"] for entry in entries)
    return {
        "schema_version": "curriculum_evidence_index_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "canonical_source": "app/knowledge/structured",
        "ragflow_overrides_structured": False,
        "summary": {"entry_count": len(entries), "entry_counts_by_source": dict(sorted(counts.items()))},
        "entries": entries,
    }


def write_index(index: dict[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> Path:
    out = resolve_path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"curriculum_evidence_index_{timestamp()}.json"
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--ragflow-evidence", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    index = build_evidence_index(
        graph=_load_json(args.graph or _latest_graph()),
        audit=_load_json(args.audit or _latest("curriculum_graph_audit_*.json")),
        candidates=_load_json(args.candidates or _latest("curriculum_data_tightening_candidates_*.json")),
        ragflow=_load_json(args.ragflow_evidence or _latest("ragflow_peptutor_evidence_chunks_*.json")),
    )
    print(write_index(index, args.out_dir))


if __name__ == "__main__":
    main()
