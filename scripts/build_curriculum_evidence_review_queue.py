#!/usr/bin/env python3
"""Build a human review queue from offline curriculum retrieval comparison results."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("temp/lesson-smoke-artifacts")
DEFAULT_DOC_PATH = Path("docs/curriculum-evidence-review-queue-20260505.md")
HIGH_PRIORITY_QUERY_IDS = {
    "p13_answer_scope",
    "phonics_cl_clean",
    "height_question",
    "museum_shop_question",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def latest_artifact(pattern: str) -> Path | None:
    artifact_dir = repo_root() / "temp/lesson-smoke-artifacts"
    matches = sorted(artifact_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def priority_for(item: dict[str, Any]) -> str:
    if item.get("query_id") in HIGH_PRIORITY_QUERY_IDS:
        return "P1"
    if item.get("evidence_hit_count", 0) == 0:
        return "P2"
    return "P3"


def review_reason(item: dict[str, Any]) -> str:
    if item.get("status") == "agent_failed_needs_retry_or_prompt_only_review":
        return "Provider failed; keep prompt-only evidence for human review."
    if item.get("evidence_hit_count", 0) == 0:
        return "No local evidence hits were found; review whether the query needs richer evidence indexing."
    if item.get("query_id") == "p13_answer_scope":
        return "P13 answer-scope evidence remains human-reviewed and must not be inferred as return-anchor risk."
    if item.get("query_id") == "phonics_cl_clean":
        return "Phonics pattern/exemplar evidence should be reviewed for page-level inheritance, not data mutation."
    return "Review local evidence and any agent notes before deciding whether data tightening is needed."


def suggested_action(item: dict[str, Any]) -> str:
    if item.get("query_id") == "p13_answer_scope":
        return "Human-review answer-scope boundaries only; do not invent module-choice or return-anchor findings."
    if item.get("query_id") == "phonics_cl_clean":
        return "Review phonics inheritance/modeling before editing curriculum data."
    if item.get("query_id") == "story_scaffold_p31":
        return "Review story scaffold evidence and keep visible teaching-action changes separate."
    return "Compare structured evidence, audit evidence, and agent notes; decide whether to defer or open a data-review PR."


def build_review_queue(comparison: dict[str, Any]) -> dict[str, Any]:
    queue = []
    for index, item in enumerate(comparison.get("comparisons", []), start=1):
        queue.append(
            {
                "queue_id": f"CEQ-{index:03d}",
                "query_id": item.get("query_id", ""),
                "query_text": item.get("query_text", ""),
                "page_uid": item.get("page_uid", ""),
                "priority": priority_for(item),
                "status": item.get("status", ""),
                "evidence_hit_count": item.get("evidence_hit_count", 0),
                "source_counts": item.get("source_counts", {}),
                "top_evidence_refs": item.get("top_evidence_refs", []),
                "review_reason": review_reason(item),
                "suggested_action": suggested_action(item),
                "should_mutate_data_now": False,
                "owner_layer": "human_curriculum_evidence_review",
            }
        )
    queue.sort(key=lambda item: (item["priority"], item["queue_id"]))
    return {
        "schema_version": "curriculum_evidence_review_queue_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "canonical_source": "app/knowledge/structured",
        "agentic_outputs_are_review_only": True,
        "summary": {
            "queue_count": len(queue),
            "p1_count": sum(1 for item in queue if item["priority"] == "P1"),
            "should_mutate_data_now_count": sum(1 for item in queue if item["should_mutate_data_now"]),
        },
        "queue": queue,
    }


def write_queue_json(queue: dict[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> Path:
    resolved = resolve_path(out_dir)
    resolved.mkdir(parents=True, exist_ok=True)
    path = resolved / f"curriculum_evidence_review_queue_{timestamp()}.json"
    path.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_markdown(queue: dict[str, Any], path: Path = DEFAULT_DOC_PATH) -> Path:
    resolved = resolve_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Curriculum Evidence Review Queue",
        "",
        "This is a human-review queue for offline curriculum evidence. It does not approve data mutation.",
        "",
        "## Summary",
        "",
        f"- queue_count: {queue['summary']['queue_count']}",
        f"- p1_count: {queue['summary']['p1_count']}",
        f"- should_mutate_data_now_count: {queue['summary']['should_mutate_data_now_count']}",
        "",
        "## Queue",
        "",
    ]
    for item in queue.get("queue", []):
        lines.extend(
            [
                f"### {item['queue_id']} {item['query_id']}",
                "",
                f"- query: {item['query_text']}",
                f"- page_uid: {item['page_uid']}",
                f"- priority: {item['priority']}",
                f"- evidence_hit_count: {item['evidence_hit_count']}",
                f"- review_reason: {item['review_reason']}",
                f"- suggested_action: {item['suggested_action']}",
                f"- should_mutate_data_now: {item['should_mutate_data_now']}",
                "",
            ]
        )
    resolved.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison-report", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--queue-md", type=Path, default=DEFAULT_DOC_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    comparison_path = args.comparison_report or latest_artifact("curriculum_retrieval_comparison_*.json")
    if not comparison_path:
        raise SystemExit("No curriculum retrieval comparison report found.")
    queue = build_review_queue(load_json(comparison_path))
    json_path = write_queue_json(queue, args.out_dir)
    md_path = write_markdown(queue, args.queue_md)
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
