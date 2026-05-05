#!/usr/bin/env python3
"""Compare local evidence hits and offline agentic outputs for curriculum review queries."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("temp/lesson-smoke-artifacts")
DEFAULT_REPORT_PATH = Path("docs/curriculum-retrieval-comparison-report-20260505.md")


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


def _status_for_result(result: dict[str, Any]) -> str:
    provider_log = result.get("provider_log", {})
    if provider_log.get("provider") == "none":
        return "prompt_only_needs_human_review"
    if provider_log.get("exit_code") == 0:
        return "agent_output_needs_human_review"
    return "agent_failed_needs_retry_or_prompt_only_review"


def build_comparison(harness: dict[str, Any]) -> dict[str, Any]:
    comparisons = []
    source_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for result in harness.get("results", []):
        sources = Counter(hit.get("source", "") for hit in result.get("evidence_hits", []))
        source_counts.update(sources)
        status = _status_for_result(result)
        status_counts[status] += 1
        provider_log = result.get("provider_log", {})
        comparisons.append(
            {
                "query_id": result.get("query_id", ""),
                "query_text": result.get("query_text", ""),
                "page_uid": result.get("page_uid", ""),
                "review_focus": result.get("review_focus", ""),
                "status": status,
                "evidence_hit_count": len(result.get("evidence_hits", [])),
                "source_counts": dict(sorted(sources.items())),
                "provider": provider_log.get("provider", ""),
                "provider_called": provider_log.get("called", False),
                "provider_exit_code": provider_log.get("exit_code"),
                "agent_stdout_excerpt": str(provider_log.get("stdout", ""))[:800],
                "top_evidence_refs": [
                    {
                        "source": hit.get("source", ""),
                        "source_ref": hit.get("source_ref", ""),
                        "page_uid": hit.get("page_uid", ""),
                        "block_uid": hit.get("block_uid", ""),
                        "score": hit.get("score", 0),
                    }
                    for hit in result.get("evidence_hits", [])[:5]
                ],
            }
        )
    return {
        "schema_version": "curriculum_retrieval_comparison_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "harness_schema_version": harness.get("schema_version", ""),
        "canonical_source": "app/knowledge/structured",
        "agentic_outputs_are_review_only": True,
        "summary": {
            "query_count": len(comparisons),
            "provider": harness.get("provider", ""),
            "status_counts": dict(sorted(status_counts.items())),
            "evidence_source_counts": dict(sorted(source_counts.items())),
        },
        "comparisons": comparisons,
    }


def write_comparison_json(comparison: dict[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> Path:
    resolved = resolve_path(out_dir)
    resolved.mkdir(parents=True, exist_ok=True)
    path = resolved / f"curriculum_retrieval_comparison_{timestamp()}.json"
    path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_markdown(comparison: dict[str, Any], path: Path = DEFAULT_REPORT_PATH) -> Path:
    resolved = resolve_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Curriculum Retrieval Comparison Report",
        "",
        "This report compares local curriculum evidence hits with offline agentic harness outputs.",
        "",
        "RAGFlow/agentic evidence is supporting evidence only. `app/knowledge/structured` remains canonical.",
        "",
        "## Summary",
        "",
        f"- query_count: {comparison['summary']['query_count']}",
        f"- provider: {comparison['summary']['provider']}",
        f"- status_counts: `{json.dumps(comparison['summary']['status_counts'], ensure_ascii=False)}`",
        f"- evidence_source_counts: `{json.dumps(comparison['summary']['evidence_source_counts'], ensure_ascii=False)}`",
        "",
        "## Query Comparison",
        "",
    ]
    for item in comparison.get("comparisons", []):
        lines.extend(
            [
                f"### {item['query_id']}",
                "",
                f"- query: {item['query_text']}",
                f"- page_uid: {item['page_uid']}",
                f"- status: {item['status']}",
                f"- evidence_hit_count: {item['evidence_hit_count']}",
                f"- source_counts: `{json.dumps(item['source_counts'], ensure_ascii=False)}`",
                f"- provider_called: {item['provider_called']}",
                f"- provider_exit_code: {item['provider_exit_code']}",
                "",
            ]
        )
    resolved.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness-report", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_path = args.harness_report or latest_artifact("agentic_curriculum_harness_*.json")
    if not report_path:
        raise SystemExit("No agentic curriculum harness report found.")
    comparison = build_comparison(load_json(report_path))
    json_path = write_comparison_json(comparison, args.out_dir)
    md_path = write_markdown(comparison, args.report_md)
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
