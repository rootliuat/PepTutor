#!/usr/bin/env python3
"""Audit PepTutor lesson LLM prompt context byte attribution."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


REPORT_KIND = "lesson_llm_context_breakdown_audit"
DEFAULT_ARTIFACT_DIR = Path("temp/lesson-smoke-artifacts")
CONTEXT_BYTE_FIELDS = (
    "system_prompt_bytes",
    "persona_prompt_bytes",
    "persona_capsule_bytes",
    "lesson_context_bytes",
    "textbook_block_bytes",
    "page_overview_bytes",
    "runtime_state_bytes",
    "teaching_move_bytes",
    "policy_instruction_bytes",
    "quality_revision_prompt_bytes",
    "rag_context_bytes",
    "history_bytes",
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
PROMPT_DIET_COMPONENTS = (
    "textbook_block_bytes",
    "page_overview_bytes",
    "runtime_state_bytes",
    "policy_instruction_bytes",
    "quality_revision_prompt_bytes",
    "persona_prompt_bytes",
    "teaching_move_bytes",
    "output_schema_bytes",
    "planner_prompt_overhead_bytes",
    "responder_prompt_overhead_bytes",
    "revision_notes_bytes",
    "prompt_frame_overhead_bytes",
    "json_serialization_overhead_bytes",
    "unclassified_context_bytes",
    "rag_context_bytes",
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


def audit_llm_context_breakdown(
    *,
    smoke_report_path: Path,
    out_dir: Path | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    resolved_smoke_path = _resolve_path(smoke_report_path)
    smoke_report = json.loads(resolved_smoke_path.read_text(encoding="utf-8"))
    calls = _extract_llm_calls(smoke_report)
    report = {
        "kind": REPORT_KIND,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "smoke_file": str(resolved_smoke_path),
        "smoke_acceptance_passed": bool(
            (smoke_report.get("summary") or {}).get("acceptance_passed")
        ),
        "summary": _summary(calls),
        "top_calls_by_lesson_context_bytes": _top_calls(calls),
        "top_pages_by_lesson_context_bytes": _top_grouped(calls, "page_uid"),
        "top_routes_by_lesson_context_bytes": _top_grouped(calls, "route"),
        "top_audit_tags_by_lesson_context_bytes": _top_grouped(calls, "audit_tag"),
        "answer_turn_policy_breakdown": _route_breakdown(
            calls,
            lambda call: _text(call.get("route")) == "answer_turn_policy"
            and "reply_quality_revision" not in _text(call.get("audit_tag")),
        ),
        "reply_quality_revision_breakdown": _route_breakdown(
            calls,
            lambda call: "reply_quality_revision" in _text(call.get("audit_tag")),
        ),
        "rag_vs_non_rag_breakdown": _rag_vs_non_rag(calls),
        "estimated_savings_candidates": _estimated_savings_candidates(calls),
        "recommended_prompt_diet_plan": _recommended_prompt_diet_plan(calls),
        "calls": calls,
    }
    if out_dir is not None:
        stamp = timestamp or _timestamp()
        resolved_out_dir = _resolve_path(out_dir)
        resolved_out_dir.mkdir(parents=True, exist_ok=True)
        json_path = resolved_out_dir / f"llm_context_breakdown_audit_{stamp}.json"
        md_path = resolved_out_dir / f"llm_context_breakdown_audit_{stamp}.md"
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
        "# LLM Context Breakdown Audit",
        "",
        f"Generated: {report['generated_at']}",
        f"Smoke file: `{report['smoke_file']}`",
        f"Smoke acceptance: `{'PASS' if report['smoke_acceptance_passed'] else 'FAIL'}`",
        "",
        "## Summary",
        "",
        f"- total_llm_calls: `{summary['total_llm_calls']}`",
        f"- total_lesson_context_bytes: `{summary['total_lesson_context_bytes']}`",
        f"- avg_lesson_context_bytes: `{summary['avg_lesson_context_bytes']}`",
        f"- max_lesson_context_bytes: `{summary['max_lesson_context_bytes']}`",
        f"- unknown_context_bytes: `{summary['component_totals']['unknown_context_bytes']}`",
        f"- unclassified_context_bytes: `{summary['component_totals']['unclassified_context_bytes']}`",
        f"- minimal_runtime_state_prompt_enabled_call_count: `{summary['minimal_runtime_state_prompt_enabled_call_count']}`",
        "",
        "## Component Totals",
        "",
    ]
    lines.append("| Component | Bytes | Share |")
    lines.append("|---|---:|---:|")
    for key, value in summary["component_totals"].items():
        if key == "lesson_context_bytes":
            continue
        lines.append(f"| `{key}` | {value} | {summary['component_shares'].get(key, 0)} |")

    lines.extend(["", "## Top Calls By Lesson Context Bytes", ""])
    lines.append("| Page | Route | Audit Tag | Lesson Context | Top Component | Unknown |")
    lines.append("|---|---|---|---:|---|---:|")
    for call in report["top_calls_by_lesson_context_bytes"][:10]:
        lines.append(
            "| `{page_uid}` | `{route}` | `{audit_tag}` | {lesson_context_bytes} | `{top_component}` | {unknown_context_bytes} |".format(
                **call
            )
        )

    lines.extend(["", "## Top Pages", ""])
    lines.append("| Page | Calls | Lesson Context | Avg | Top Component |")
    lines.append("|---|---:|---:|---:|---|")
    for row in report["top_pages_by_lesson_context_bytes"][:10]:
        lines.append(
            "| `{page_uid}` | {call_count} | {lesson_context_bytes} | {avg_lesson_context_bytes} | `{top_component}` |".format(
                **row
            )
        )

    lines.extend(["", "## Top Routes", ""])
    lines.append("| Route | Calls | Lesson Context | Avg | Top Component |")
    lines.append("|---|---:|---:|---:|---|")
    for row in report["top_routes_by_lesson_context_bytes"]:
        lines.append(
            "| `{route}` | {call_count} | {lesson_context_bytes} | {avg_lesson_context_bytes} | `{top_component}` |".format(
                **row
            )
        )

    lines.extend(["", "## Top Audit Tags", ""])
    lines.append("| Audit Tag | Calls | Lesson Context | Avg | Top Component |")
    lines.append("|---|---:|---:|---:|---|")
    for row in report["top_audit_tags_by_lesson_context_bytes"][:10]:
        lines.append(
            "| `{audit_tag}` | {call_count} | {lesson_context_bytes} | {avg_lesson_context_bytes} | `{top_component}` |".format(
                **row
            )
        )

    lines.extend(["", "## Answer Turn Policy Breakdown", ""])
    lines.extend(_breakdown_lines(report["answer_turn_policy_breakdown"]))
    lines.extend(["", "## Answer Turn Policy Runtime State", ""])
    runtime_state = summary["answer_turn_policy_runtime_state"]
    lines.extend(
        [
            f"- call_count: `{runtime_state['call_count']}`",
            f"- runtime_state_bytes: `{runtime_state['runtime_state_bytes']}`",
            f"- avg_runtime_state_bytes: `{runtime_state['avg_runtime_state_bytes']}`",
            f"- p95_runtime_state_bytes: `{runtime_state['p95_runtime_state_bytes']}`",
            f"- max_runtime_state_bytes: `{runtime_state['max_runtime_state_bytes']}`",
            f"- avg_prompt_tokens: `{runtime_state['avg_prompt_tokens']}`",
            f"- p95_prompt_tokens: `{runtime_state['p95_prompt_tokens']}`",
            f"- max_prompt_tokens: `{runtime_state['max_prompt_tokens']}`",
        ]
    )
    lines.extend(["", "## Reply Quality Revision Breakdown", ""])
    lines.extend(_breakdown_lines(report["reply_quality_revision_breakdown"]))

    lines.extend(["", "## RAG vs Non-RAG", ""])
    lines.append("| Bucket | Calls | Lesson Context | Avg Prompt Tokens | Top Component |")
    lines.append("|---|---:|---:|---:|---|")
    for row in report["rag_vs_non_rag_breakdown"]:
        lines.append(
            "| {bucket} | {call_count} | {lesson_context_bytes} | {avg_prompt_tokens} | `{top_component}` |".format(
                **row
            )
        )

    lines.extend(["", "## Estimated Savings Candidates", ""])
    for item in report["estimated_savings_candidates"]:
        lines.append(
            f"- `{item['component']}`: {item['bytes']} bytes, "
            f"{item['share']} share. {item['reason']}"
        )

    lines.extend(["", "## Recommended Prompt Diet Plan", ""])
    for item in report["recommended_prompt_diet_plan"]:
        lines.append(f"- `{item['slice']}`: {item['recommendation']}")
    lines.append("")
    return "\n".join(lines)


def _breakdown_lines(breakdown: dict[str, Any]) -> list[str]:
    lines = [
        f"- call_count: `{breakdown['call_count']}`",
        f"- lesson_context_bytes: `{breakdown['lesson_context_bytes']}`",
        f"- avg_lesson_context_bytes: `{breakdown['avg_lesson_context_bytes']}`",
        f"- top_component: `{breakdown['top_component']}`",
        "",
        "| Component | Bytes | Share |",
        "|---|---:|---:|",
    ]
    for key, value in breakdown["component_totals"].items():
        if key == "lesson_context_bytes":
            continue
        lines.append(f"| `{key}` | {value} | {breakdown['component_shares'].get(key, 0)} |")
    return lines


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
                if isinstance(call, dict):
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
    audit_tag = _text(call.get("audit_tag")) or "unknown"
    call_id = _text(call.get("call_id")) or f"{page_uid}:{turn.get('step')}:{index}"
    normalized = {
        "call_id": call_id,
        "audit_tag": audit_tag,
        "mode": _text(call.get("mode")) or "complete",
        "status": _text(call.get("status")) or "success",
        "page_uid": page_uid,
        "page_label": _text(turn.get("page_label")),
        "step": _text(turn.get("step")),
        "learner_input": turn.get("learner_input"),
        "route": route,
        "turn_label": _text(call.get("turn_label")) or _text(turn.get("turn_label")),
        "block_uid": _text(call.get("block_uid")) or _text(turn.get("state_block_uid")),
        "llm_provider": _text(call.get("llm_provider")) or "unknown",
        "llm_model": _text(call.get("llm_model")) or "unknown",
        "prompt_bytes": _int(call.get("prompt_bytes")),
        "prompt_token_estimate": _int(call.get("prompt_token_estimate")),
        "completion_bytes": _int(call.get("completion_bytes")),
        "completion_token_estimate": _int(call.get("completion_token_estimate")),
        "total_token_estimate": _int(call.get("total_token_estimate")),
    }
    for field in CONTEXT_BYTE_FIELDS:
        normalized[field] = _int(call.get(field))
    normalized["minimal_runtime_state_prompt_enabled"] = bool(
        call.get("minimal_runtime_state_prompt_enabled")
    )
    normalized["top_component"] = _top_component(normalized)
    return normalized


def _summary(calls: list[dict[str, Any]]) -> dict[str, Any]:
    lesson_context_values = [int(call["lesson_context_bytes"]) for call in calls]
    totals = _component_totals(calls)
    total_context = totals["lesson_context_bytes"]
    return {
        "total_llm_calls": len(calls),
        "total_lesson_context_bytes": total_context,
        "avg_lesson_context_bytes": _average(lesson_context_values),
        "max_lesson_context_bytes": max(lesson_context_values, default=0),
        "component_totals": totals,
        "component_shares": _component_shares(totals, total_context),
        "audit_tag_counts": dict(Counter(_text(call.get("audit_tag")) for call in calls)),
        "minimal_runtime_state_prompt_enabled_call_count": sum(
            1 for call in calls if bool(call.get("minimal_runtime_state_prompt_enabled"))
        ),
        "answer_turn_policy_runtime_state": _answer_turn_policy_runtime_state_stats(
            calls
        ),
    }


def _answer_turn_policy_runtime_state_stats(
    calls: list[dict[str, Any]],
) -> dict[str, Any]:
    selected = [
        call
        for call in calls
        if _text(call.get("route")) == "answer_turn_policy"
        and "reply_quality_revision" not in _text(call.get("audit_tag"))
    ]
    runtime_state_values = [int(call["runtime_state_bytes"]) for call in selected]
    prompt_values = [int(call["prompt_token_estimate"]) for call in selected]
    return {
        "call_count": len(selected),
        "runtime_state_bytes": sum(runtime_state_values),
        "avg_runtime_state_bytes": _average(runtime_state_values),
        "p95_runtime_state_bytes": _percentile(runtime_state_values, 95),
        "max_runtime_state_bytes": max(runtime_state_values, default=0),
        "avg_prompt_tokens": _average(prompt_values),
        "p95_prompt_tokens": _percentile(prompt_values, 95),
        "max_prompt_tokens": max(prompt_values, default=0),
    }


def _top_calls(calls: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    return sorted(
        calls,
        key=lambda call: (-int(call["lesson_context_bytes"]), str(call["call_id"])),
    )[:limit]


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
        totals = _component_totals(group)
        lesson_context_bytes = totals["lesson_context_bytes"]
        rows.append(
            {
                key: value,
                "call_count": len(group),
                "lesson_context_bytes": lesson_context_bytes,
                "avg_lesson_context_bytes": _average(
                    [int(call["lesson_context_bytes"]) for call in group]
                ),
                "component_totals": totals,
                "component_shares": _component_shares(totals, lesson_context_bytes),
                "top_component": _top_component(totals),
            }
        )
    return sorted(
        rows,
        key=lambda item: (-int(item["lesson_context_bytes"]), str(item.get(key, ""))),
    )[:limit]


def _route_breakdown(
    calls: list[dict[str, Any]],
    predicate,
) -> dict[str, Any]:
    selected = [call for call in calls if predicate(call)]
    totals = _component_totals(selected)
    lesson_context_bytes = totals["lesson_context_bytes"]
    return {
        "call_count": len(selected),
        "lesson_context_bytes": lesson_context_bytes,
        "avg_lesson_context_bytes": _average(
            [int(call["lesson_context_bytes"]) for call in selected]
        ),
        "component_totals": totals,
        "component_shares": _component_shares(totals, lesson_context_bytes),
        "top_component": _top_component(totals),
        "top_calls": _top_calls(selected, limit=5),
    }


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
        totals = _component_totals(group)
        rows.append(
            {
                "bucket": bucket,
                "call_count": len(group),
                "lesson_context_bytes": totals["lesson_context_bytes"],
                "avg_prompt_tokens": _average(
                    [int(call["prompt_token_estimate"]) for call in group]
                ),
                "component_totals": totals,
                "top_component": _top_component(totals),
            }
        )
    return rows


def _estimated_savings_candidates(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals = _component_totals(calls)
    total_context = max(1, totals["lesson_context_bytes"])
    reasons = {
        "textbook_block_bytes": "教材块、同页 block 和 lesson brief 是事实输入，后续只能做结构化裁剪，不能删除。",
        "page_overview_bytes": "多 block 页 page overview 可考虑只在 page_entry 或 module_choice 保留完整版本。",
        "runtime_state_bytes": "runtime state / task boundary 可考虑用枚举和短码替代长中文规则说明。",
        "policy_instruction_bytes": "policy rubric 是 answer_turn_policy 的固定成本，可考虑缓存或压缩固定说明。",
        "quality_revision_prompt_bytes": "revision prompt 只在质量修复调用出现，可考虑减少原回复/notes 重复。",
        "persona_prompt_bytes": "persona 只应影响语气和脚手架大小，可保持短摘要。",
        "teaching_move_bytes": "TeachingMove 是结构化契约，后续可保持字段化而不是自然语言解释。",
        "output_schema_bytes": "输出 schema 是固定格式约束，后续可考虑短码或共享 schema 版本号。",
        "planner_prompt_overhead_bytes": "planner 允许值、fallback plan 等 wrapper 可后续短码化，但不能改变 route 选择边界。",
        "responder_prompt_overhead_bytes": "responder 包装元信息可审计后压缩，不能改 teacher kernel 语义。",
        "revision_notes_bytes": "revision notes 是动态修复证据，可考虑结构化短码替代长中文 notes。",
        "prompt_frame_overhead_bytes": "prompt JSON key/frame 包装成本，可后续通过紧凑序列化或 schema caching 降低。",
        "json_serialization_overhead_bytes": "pretty JSON 空白缩进成本，可后续改紧凑序列化，但要先验证 provider 可读性。",
        "unclassified_context_bytes": "仍未归因的上下文字节，需要先定位来源再裁剪。",
        "rag_context_bytes": "当前 RAG 平均不高，只有真实 ask_knowledge/RAG route 再考虑召回裁剪。",
    }
    candidates = []
    for component in PROMPT_DIET_COMPONENTS:
        value = totals.get(component, 0)
        if value <= 0:
            continue
        candidates.append(
            {
                "component": component,
                "bytes": value,
                "share": round(value / total_context, 4),
                "reason": reasons[component],
            }
        )
    return sorted(candidates, key=lambda item: -int(item["bytes"]))[:8]


def _recommended_prompt_diet_plan(calls: list[dict[str, Any]]) -> list[dict[str, str]]:
    ranked = [
        item["component"]
        for item in _estimated_savings_candidates(calls)
        if item["component"] != "rag_context_bytes"
    ]
    primary = ranked[0] if ranked else "policy_instruction_bytes"
    return [
        {
            "slice": "P5.7-readonly-design",
            "recommendation": (
                f"先围绕 `{primary}` 写 prompt diet 设计，不直接压缩；验证哪些字段是事实必需。"
            ),
        },
        {
            "slice": "P5.8-fixed-rubric-cache",
            "recommendation": "把固定 policy/output 说明和每轮动态教材事实分开计量，再决定是否压缩固定 rubric。",
        },
        {
            "slice": "P5.9-dynamic-context-trim",
            "recommendation": "只对 answer_turn_policy 的动态 frame 做候选裁剪，先保持 20 页 smoke 全绿。",
        },
    ]


def _component_totals(calls: list[dict[str, Any]]) -> dict[str, int]:
    return {
        field: sum(int(call.get(field) or 0) for call in calls)
        for field in CONTEXT_BYTE_FIELDS
    }


def _component_shares(totals: dict[str, int], denominator: int) -> dict[str, float]:
    base = max(1, denominator)
    return {
        field: round(value / base, 4)
        for field, value in totals.items()
        if field != "lesson_context_bytes"
    }


def _top_component(values: dict[str, Any]) -> str:
    component_values = {
        field: int(values.get(field) or 0)
        for field in PROMPT_DIET_COMPONENTS
        if field != "rag_context_bytes" or int(values.get(field) or 0) > 0
    }
    if not component_values:
        return "unknown_context_bytes"
    return max(component_values.items(), key=lambda item: (item[1], item[0]))[0]


def _average(values: list[int]) -> int:
    if not values:
        return 0
    return round(sum(values) / len(values))


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(
        len(ordered) - 1,
        max(0, round((percentile / 100) * (len(ordered) - 1))),
    )
    return ordered[index]


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
    report = audit_llm_context_breakdown(
        smoke_report_path=smoke_path,
        out_dir=args.out_dir,
    )
    print(
        json.dumps(
            {
                "json_path": report["json_path"],
                "markdown_path": report["markdown_path"],
                "summary": report["summary"],
                "top_pages_by_lesson_context_bytes": report[
                    "top_pages_by_lesson_context_bytes"
                ][:5],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
