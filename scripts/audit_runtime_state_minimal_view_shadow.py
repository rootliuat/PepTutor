#!/usr/bin/env python3
"""Audit runtime state minimal-view shadow savings from lesson smoke reports."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


REPORT_KIND = "lesson_runtime_state_minimal_view_shadow_audit"
DEFAULT_ARTIFACT_DIR = Path("temp/lesson-smoke-artifacts")
WATCHLIST_PAGES = {
    "TB-G5S1U3-P24": "food/drink boundary",
    "TB-G6S2U2-P13": "vocab return/module-choice boundary",
    "TB-G5S2U1-P6": "phonics same-page match",
    "TB-G6S1U1-P4": "question/answer target source",
    "TB-G6S2U1-P4": "height question target/action frame",
}


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


def audit_runtime_state_minimal_view_shadow(
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
        "shadow_only": True,
        "live_prompt_switched": False,
        "summary": _summary(calls),
        "top_calls_by_savings_candidate_bytes": _top_calls(calls),
        "top_pages_by_savings_candidate_bytes": _top_grouped(calls, "page_uid"),
        "top_routes_by_savings_candidate_bytes": _top_grouped(calls, "route"),
        "top_audit_tags_by_savings_candidate_bytes": _top_grouped(
            calls,
            "audit_tag",
        ),
        "boundary_watchlist": _boundary_watchlist(calls),
        "acceptance_gate_recommendation": _acceptance_gate_recommendation(calls),
        "calls": calls,
    }
    if out_dir is not None:
        stamp = timestamp or _timestamp()
        resolved_out_dir = _resolve_path(out_dir)
        resolved_out_dir.mkdir(parents=True, exist_ok=True)
        json_path = (
            resolved_out_dir
            / f"runtime_state_minimal_view_shadow_audit_{stamp}.json"
        )
        md_path = (
            resolved_out_dir / f"runtime_state_minimal_view_shadow_audit_{stamp}.md"
        )
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
        "# Runtime State Minimal View Shadow Audit",
        "",
        f"Generated: {report['generated_at']}",
        f"Smoke file: `{report['smoke_file']}`",
        f"Smoke acceptance: `{'PASS' if report['smoke_acceptance_passed'] else 'FAIL'}`",
        f"Shadow only: `{report['shadow_only']}`",
        f"Live prompt switched: `{report['live_prompt_switched']}`",
        "",
        "## Summary",
        "",
        f"- total_llm_calls: `{summary['total_llm_calls']}`",
        f"- metered_runtime_state_call_count: `{summary['metered_runtime_state_call_count']}`",
        f"- total_runtime_state_legacy_frame_bytes: `{summary['total_runtime_state_legacy_frame_bytes']}`",
        f"- total_runtime_state_minimal_view_bytes: `{summary['total_runtime_state_minimal_view_bytes']}`",
        f"- total_runtime_state_savings_candidate_bytes: `{summary['total_runtime_state_savings_candidate_bytes']}`",
        f"- avg_savings_candidate_bytes: `{summary['avg_savings_candidate_bytes']}`",
        f"- p95_savings_candidate_bytes: `{summary['p95_savings_candidate_bytes']}`",
        f"- max_savings_candidate_bytes: `{summary['max_savings_candidate_bytes']}`",
        f"- savings_share_of_legacy: `{summary['savings_share_of_legacy']}`",
        f"- minimal_view_missing_count: `{summary['minimal_view_missing_count']}`",
        "",
        "## Top Pages By Savings Candidate",
        "",
        "| Page | Calls | Legacy | Minimal | Savings | Share |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["top_pages_by_savings_candidate_bytes"][:10]:
        lines.append(
            "| `{page_uid}` | {call_count} | {runtime_state_legacy_frame_bytes} | "
            "{runtime_state_minimal_view_bytes} | {runtime_state_savings_candidate_bytes} | "
            "{savings_share_of_legacy} |".format(**row)
        )

    lines.extend(["", "## Top Routes By Savings Candidate", ""])
    lines.append("| Route | Calls | Legacy | Minimal | Savings | Share |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in report["top_routes_by_savings_candidate_bytes"]:
        lines.append(
            "| `{route}` | {call_count} | {runtime_state_legacy_frame_bytes} | "
            "{runtime_state_minimal_view_bytes} | {runtime_state_savings_candidate_bytes} | "
            "{savings_share_of_legacy} |".format(**row)
        )

    lines.extend(["", "## Top Audit Tags By Savings Candidate", ""])
    lines.append("| Audit Tag | Calls | Legacy | Minimal | Savings | Share |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in report["top_audit_tags_by_savings_candidate_bytes"][:10]:
        lines.append(
            "| `{audit_tag}` | {call_count} | {runtime_state_legacy_frame_bytes} | "
            "{runtime_state_minimal_view_bytes} | {runtime_state_savings_candidate_bytes} | "
            "{savings_share_of_legacy} |".format(**row)
        )

    lines.extend(["", "## Boundary Watchlist", ""])
    lines.append("| Page | Risk | Calls | Legacy | Minimal | Savings | Seen |")
    lines.append("|---|---|---:|---:|---:|---:|---|")
    for row in report["boundary_watchlist"]:
        lines.append(
            "| `{page_uid}` | {risk} | {call_count} | {runtime_state_legacy_frame_bytes} | "
            "{runtime_state_minimal_view_bytes} | {runtime_state_savings_candidate_bytes} | "
            "`{seen_in_sample}` |".format(**row)
        )

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            report["acceptance_gate_recommendation"],
            "",
            "This report is a shadow audit. It does not indicate that the live "
            "answer_turn_policy prompt has switched to the minimal runtime state view.",
            "",
        ]
    )
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
    call_id = _text(call.get("call_id")) or f"{page_uid}:{turn.get('step')}:{index}"
    legacy = _int(call.get("runtime_state_legacy_frame_bytes"))
    minimal = _int(call.get("runtime_state_minimal_view_bytes"))
    savings = _int(call.get("runtime_state_savings_candidate_bytes"))
    if legacy and not savings:
        savings = max(0, legacy - minimal)
    return {
        "call_id": call_id,
        "audit_tag": _text(call.get("audit_tag")) or "unknown",
        "page_uid": page_uid,
        "page_label": _text(turn.get("page_label")),
        "step": _text(turn.get("step")),
        "learner_input": turn.get("learner_input"),
        "route": route,
        "turn_label": _text(call.get("turn_label")) or _text(turn.get("turn_label")),
        "block_uid": _text(call.get("block_uid")) or _text(turn.get("state_block_uid")),
        "prompt_token_estimate": _int(call.get("prompt_token_estimate")),
        "runtime_state_bytes": _int(call.get("runtime_state_bytes")),
        "runtime_state_legacy_frame_bytes": legacy,
        "runtime_state_minimal_view_bytes": minimal,
        "runtime_state_savings_candidate_bytes": savings,
        "minimal_view_missing": legacy > 0 and minimal <= 0,
        "savings_share_of_legacy": _share(savings, legacy),
    }


def _summary(calls: list[dict[str, Any]]) -> dict[str, Any]:
    metered = [call for call in calls if int(call["runtime_state_legacy_frame_bytes"]) > 0]
    savings_values = [
        int(call["runtime_state_savings_candidate_bytes"]) for call in metered
    ]
    legacy_total = sum(int(call["runtime_state_legacy_frame_bytes"]) for call in calls)
    minimal_total = sum(int(call["runtime_state_minimal_view_bytes"]) for call in calls)
    savings_total = sum(
        int(call["runtime_state_savings_candidate_bytes"]) for call in calls
    )
    return {
        "total_llm_calls": len(calls),
        "metered_runtime_state_call_count": len(metered),
        "total_runtime_state_bytes": sum(int(call["runtime_state_bytes"]) for call in calls),
        "total_runtime_state_legacy_frame_bytes": legacy_total,
        "total_runtime_state_minimal_view_bytes": minimal_total,
        "total_runtime_state_savings_candidate_bytes": savings_total,
        "avg_savings_candidate_bytes": _average(savings_values),
        "p95_savings_candidate_bytes": _percentile(savings_values, 95),
        "max_savings_candidate_bytes": max(savings_values, default=0),
        "savings_share_of_legacy": _share(savings_total, legacy_total),
        "minimal_view_missing_count": sum(
            1 for call in calls if bool(call["minimal_view_missing"])
        ),
        "routes_with_metered_runtime_state": dict(
            Counter(_text(call.get("route")) for call in metered)
        ),
    }


def _top_calls(calls: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    return sorted(
        calls,
        key=lambda call: (
            -int(call["runtime_state_savings_candidate_bytes"]),
            str(call["call_id"]),
        ),
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
        legacy = sum(int(call["runtime_state_legacy_frame_bytes"]) for call in group)
        minimal = sum(int(call["runtime_state_minimal_view_bytes"]) for call in group)
        savings = sum(
            int(call["runtime_state_savings_candidate_bytes"]) for call in group
        )
        rows.append(
            {
                key: value,
                "call_count": len(group),
                "runtime_state_legacy_frame_bytes": legacy,
                "runtime_state_minimal_view_bytes": minimal,
                "runtime_state_savings_candidate_bytes": savings,
                "avg_savings_candidate_bytes": _average(
                    [int(call["runtime_state_savings_candidate_bytes"]) for call in group]
                ),
                "max_savings_candidate_bytes": max(
                    (
                        int(call["runtime_state_savings_candidate_bytes"])
                        for call in group
                    ),
                    default=0,
                ),
                "savings_share_of_legacy": _share(savings, legacy),
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            -int(item["runtime_state_savings_candidate_bytes"]),
            str(item.get(key, "")),
        ),
    )[:limit]


def _boundary_watchlist(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for page_uid, risk in WATCHLIST_PAGES.items():
        selected = [call for call in calls if _text(call.get("page_uid")) == page_uid]
        legacy = sum(int(call["runtime_state_legacy_frame_bytes"]) for call in selected)
        minimal = sum(int(call["runtime_state_minimal_view_bytes"]) for call in selected)
        savings = sum(
            int(call["runtime_state_savings_candidate_bytes"]) for call in selected
        )
        rows.append(
            {
                "page_uid": page_uid,
                "risk": risk,
                "call_count": len(selected),
                "runtime_state_legacy_frame_bytes": legacy,
                "runtime_state_minimal_view_bytes": minimal,
                "runtime_state_savings_candidate_bytes": savings,
                "savings_share_of_legacy": _share(savings, legacy),
                "seen_in_sample": bool(selected),
            }
        )
    return rows


def _acceptance_gate_recommendation(calls: list[dict[str, Any]]) -> str:
    summary = _summary(calls)
    if summary["minimal_view_missing_count"]:
        return (
            "Do not switch live prompt yet. Some calls have legacy runtime state "
            "metering without minimal-view shadow bytes."
        )
    if summary["metered_runtime_state_call_count"] == 0:
        return (
            "Do not switch live prompt yet. This smoke sample has no metered "
            "answer_turn_policy runtime-state calls."
        )
    return (
        "Keep this as shadow-only evidence. The next implementation slice should "
        "only switch the live prompt behind an explicit guard after reviewing the "
        "watchlist pages and acceptance audits."
    )


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


def _share(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


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
    report = audit_runtime_state_minimal_view_shadow(
        smoke_report_path=smoke_path,
        out_dir=args.out_dir,
    )
    print(
        json.dumps(
            {
                "json_path": report["json_path"],
                "markdown_path": report["markdown_path"],
                "summary": report["summary"],
                "top_pages_by_savings_candidate_bytes": report[
                    "top_pages_by_savings_candidate_bytes"
                ][:5],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
