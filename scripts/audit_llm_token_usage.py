#!/usr/bin/env python3
"""Audit LLM token and byte usage from a PepTutor lesson smoke report."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any


REPORT_KIND = "lesson_llm_token_usage_audit"
DEFAULT_ARTIFACT_DIR = Path("temp/lesson-smoke-artifacts")
CONTEXT_BYTE_FIELDS = (
    "rag_context_bytes",
    "history_bytes",
    "system_prompt_bytes",
    "lesson_context_bytes",
    "persona_prompt_bytes",
    "persona_capsule_bytes",
    "textbook_block_bytes",
    "page_overview_bytes",
    "runtime_state_bytes",
    "teaching_move_bytes",
    "policy_instruction_bytes",
    "quality_revision_prompt_bytes",
    "learner_input_bytes",
    "prompt_frame_overhead_bytes",
    "json_serialization_overhead_bytes",
    "output_schema_bytes",
    "planner_prompt_overhead_bytes",
    "responder_prompt_overhead_bytes",
    "revision_notes_bytes",
    "unclassified_context_bytes",
    "other_bytes",
    "unknown_context_bytes",
)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (_repo_root() / path).resolve()


def latest_smoke_report(artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path:
    reports = sorted(
        _resolve_path(artifact_dir).glob("lesson_smoke_matrix_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        raise FileNotFoundError(f"No lesson_smoke_matrix_*.json found in {artifact_dir}")
    return reports[0]


def audit_llm_token_usage(
    *,
    smoke_report_path: Path,
    out_dir: Path | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    resolved_smoke_path = _resolve_path(smoke_report_path)
    smoke_report = json.loads(resolved_smoke_path.read_text(encoding="utf-8"))
    calls = _extract_llm_calls(smoke_report)
    summary = _summarize_calls(calls)
    report = {
        "kind": REPORT_KIND,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "smoke_file": str(resolved_smoke_path),
        "smoke_acceptance_passed": bool(
            (smoke_report.get("summary") or {}).get("acceptance_passed")
        ),
        "summary": summary,
        "top_pages_by_prompt_tokens": _top_grouped(calls, "page_uid"),
        "top_routes_by_prompt_tokens": _top_grouped(calls, "route"),
        "rag_vs_non_rag_avg_tokens": _rag_vs_non_rag(calls),
        "largest_context_breakdown": _largest_context_breakdown(calls),
        "calls": calls,
    }
    if out_dir is not None:
        stamp = timestamp or _timestamp()
        resolved_out_dir = _resolve_path(out_dir)
        resolved_out_dir.mkdir(parents=True, exist_ok=True)
        json_path = resolved_out_dir / f"llm_token_usage_audit_{stamp}.json"
        md_path = resolved_out_dir / f"llm_token_usage_audit_{stamp}.md"
        json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_path.write_text(render_markdown(report), encoding="utf-8")
        report["json_path"] = str(json_path)
        report["markdown_path"] = str(md_path)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# LLM Token Usage Audit",
        "",
        f"Generated: {report['generated_at']}",
        f"Smoke file: `{report['smoke_file']}`",
        f"Smoke acceptance: `{'PASS' if report['smoke_acceptance_passed'] else 'FAIL'}`",
        "",
        "## Summary",
        "",
    ]
    for key in (
        "total_llm_calls",
        "total_prompt_token_estimate",
        "total_completion_token_estimate",
        "avg_prompt_tokens",
        "p95_prompt_tokens",
        "max_prompt_tokens",
    ):
        lines.append(f"- {key}: `{summary[key]}`")

    lines.extend(["", "## Top Pages By Prompt Tokens", ""])
    lines.append("| Page | Calls | Prompt Tokens | Avg Prompt | Max Prompt |")
    lines.append("|---|---:|---:|---:|---:|")
    for item in report["top_pages_by_prompt_tokens"][:10]:
        lines.append(
            "| `{page_uid}` | {call_count} | {prompt_tokens} | {avg_prompt_tokens} | {max_prompt_tokens} |".format(
                **item
            )
        )

    lines.extend(["", "## Top Routes By Prompt Tokens", ""])
    lines.append("| Route | Calls | Prompt Tokens | Avg Prompt | Max Prompt |")
    lines.append("|---|---:|---:|---:|---:|")
    for item in report["top_routes_by_prompt_tokens"][:10]:
        lines.append(
            "| `{route}` | {call_count} | {prompt_tokens} | {avg_prompt_tokens} | {max_prompt_tokens} |".format(
                **item
            )
        )

    lines.extend(["", "## RAG vs Non-RAG", ""])
    lines.append("| Bucket | Calls | Avg Prompt Tokens | Avg Prompt Bytes |")
    lines.append("|---|---:|---:|---:|")
    for item in report["rag_vs_non_rag_avg_tokens"]:
        lines.append(
            "| {bucket} | {call_count} | {avg_prompt_tokens} | {avg_prompt_bytes} |".format(
                **item
            )
        )

    largest = report["largest_context_breakdown"]
    lines.extend(["", "## Largest Context Breakdown", ""])
    if largest:
        lines.extend(
            [
                f"- page_uid: `{largest['page_uid']}`",
                f"- route: `{largest['route']}`",
                f"- audit_tag: `{largest['audit_tag']}`",
                f"- prompt_token_estimate: `{largest['prompt_token_estimate']}`",
                f"- prompt_bytes: `{largest['prompt_bytes']}`",
                f"- rag_context_bytes: `{largest['rag_context_bytes']}`",
                f"- lesson_context_bytes: `{largest['lesson_context_bytes']}`",
                f"- system_prompt_bytes: `{largest['system_prompt_bytes']}`",
                f"- history_bytes: `{largest['history_bytes']}`",
                f"- unknown_context_bytes: `{largest['unknown_context_bytes']}`",
                f"- unclassified_context_bytes: `{largest['unclassified_context_bytes']}`",
                f"- prompt_frame_overhead_bytes: `{largest['prompt_frame_overhead_bytes']}`",
                f"- json_serialization_overhead_bytes: `{largest['json_serialization_overhead_bytes']}`",
                f"- output_schema_bytes: `{largest['output_schema_bytes']}`",
            ]
        )
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def _extract_llm_calls(smoke_report: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for turn in smoke_report.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        usage = turn.get("llm_token_usage")
        if not isinstance(usage, dict):
            continue
        usage_calls = usage.get("calls")
        if isinstance(usage_calls, list) and usage_calls:
            for index, call in enumerate(usage_calls):
                if not isinstance(call, dict):
                    continue
                calls.append(_normalize_call(call, turn=turn, index=index))
        else:
            calls.append(_normalize_call(usage, turn=turn, index=0))
    return calls


def _normalize_call(
    call: dict[str, Any],
    *,
    turn: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    page_uid = _text(call.get("page_uid")) or _text(turn.get("page_uid"))
    route = _text(call.get("route")) or _text(turn.get("route"))
    turn_label = _text(call.get("turn_label")) or _text(turn.get("turn_label"))
    call_id = _text(call.get("call_id")) or f"{page_uid}:{turn.get('step')}:{index}"
    normalized = {
        "call_id": call_id,
        "audit_tag": _text(call.get("audit_tag")),
        "mode": _text(call.get("mode")) or "complete",
        "status": _text(call.get("status")) or "success",
        "page_uid": page_uid,
        "page_label": _text(turn.get("page_label")),
        "step": _text(turn.get("step")),
        "learner_input": turn.get("learner_input"),
        "route": route,
        "turn_label": turn_label,
        "block_uid": _text(call.get("block_uid")) or _text(turn.get("state_block_uid")),
        "llm_provider": _text(call.get("llm_provider")) or "unknown",
        "llm_model": _text(call.get("llm_model")) or "unknown",
        "token_count_source": _text(call.get("token_count_source")) or "unknown",
        "prompt_bytes": _int(call.get("prompt_bytes")),
        "prompt_token_estimate": _int(call.get("prompt_token_estimate")),
        "completion_bytes": _int(call.get("completion_bytes")),
        "completion_token_estimate": _int(call.get("completion_token_estimate")),
        "total_token_estimate": _int(call.get("total_token_estimate")),
    }
    for field in CONTEXT_BYTE_FIELDS:
        normalized[field] = _int(call.get(field))
    return normalized


def _summarize_calls(calls: list[dict[str, Any]]) -> dict[str, Any]:
    prompt_tokens = [int(call["prompt_token_estimate"]) for call in calls]
    completion_tokens = [int(call["completion_token_estimate"]) for call in calls]
    return {
        "total_llm_calls": len(calls),
        "total_prompt_token_estimate": sum(prompt_tokens),
        "total_completion_token_estimate": sum(completion_tokens),
        "total_token_estimate": sum(int(call["total_token_estimate"]) for call in calls),
        "avg_prompt_tokens": _average(prompt_tokens),
        "p95_prompt_tokens": _percentile(prompt_tokens, 95),
        "max_prompt_tokens": max(prompt_tokens, default=0),
        "token_count_sources": sorted(
            {str(call["token_count_source"]) for call in calls if call.get("token_count_source")}
        ),
    }


def _top_grouped(
    calls: list[dict[str, Any]],
    key: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        grouped.setdefault(_text(call.get(key)) or "unknown", []).append(call)
    rows = []
    for value, group in grouped.items():
        prompt_values = [int(call["prompt_token_estimate"]) for call in group]
        row_key = key if key != "page_uid" else "page_uid"
        rows.append(
            {
                row_key: value,
                "call_count": len(group),
                "prompt_tokens": sum(prompt_values),
                "avg_prompt_tokens": _average(prompt_values),
                "max_prompt_tokens": max(prompt_values, default=0),
            }
        )
    return sorted(
        rows,
        key=lambda item: (-int(item["prompt_tokens"]), str(item.get(key, ""))),
    )[:limit]


def _rag_vs_non_rag(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = {
        "rag": [
            call
            for call in calls
            if int(call.get("rag_context_bytes") or 0) > 0
            or "rag" in _text(call.get("route")).casefold()
        ],
        "non_rag": [
            call
            for call in calls
            if not (
                int(call.get("rag_context_bytes") or 0) > 0
                or "rag" in _text(call.get("route")).casefold()
            )
        ],
    }
    rows = []
    for bucket, group in buckets.items():
        rows.append(
            {
                "bucket": bucket,
                "call_count": len(group),
                "avg_prompt_tokens": _average(
                    [int(call["prompt_token_estimate"]) for call in group]
                ),
                "avg_prompt_bytes": _average([int(call["prompt_bytes"]) for call in group]),
            }
        )
    return rows


def _largest_context_breakdown(calls: list[dict[str, Any]]) -> dict[str, Any]:
    if not calls:
        return {}
    return max(calls, key=lambda call: int(call["prompt_token_estimate"]))


def _average(values: list[int]) -> int:
    if not values:
        return 0
    return round(sum(values) / len(values))


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    sorted_values = sorted(values)
    index = max(0, math.ceil((percentile / 100) * len(sorted_values)) - 1)
    return sorted_values[index]


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _text(value: Any) -> str:
    return str(value or "").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-report", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    smoke_path = args.smoke_report or latest_smoke_report(args.out_dir)
    report = audit_llm_token_usage(
        smoke_report_path=smoke_path,
        out_dir=args.out_dir,
    )
    print(
        json.dumps(
            {
                "json_path": report["json_path"],
                "markdown_path": report["markdown_path"],
                "summary": report["summary"],
                "top_pages_by_prompt_tokens": report[
                    "top_pages_by_prompt_tokens"
                ][:5],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
