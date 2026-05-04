#!/usr/bin/env python3
"""Audit attribution of previously unknown PepTutor lesson LLM context bytes."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_llm_context_breakdown import (  # noqa: E402
    DEFAULT_ARTIFACT_DIR,
    _average,
    _extract_llm_calls,
    _int,
    _resolve_path,
    _text,
    latest_smoke_report,
)


REPORT_KIND = "lesson_unknown_context_attribution_audit"
ATTRIBUTION_FIELDS = (
    "prompt_frame_overhead_bytes",
    "json_serialization_overhead_bytes",
    "output_schema_bytes",
    "planner_prompt_overhead_bytes",
    "responder_prompt_overhead_bytes",
    "revision_notes_bytes",
    "unclassified_context_bytes",
)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def audit_unknown_context_attribution(
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
        "top_calls_by_previously_unknown_bytes": _top_calls(calls),
        "top_pages_by_previously_unknown_bytes": _top_grouped(calls, "page_uid"),
        "top_routes_by_previously_unknown_bytes": _top_grouped(calls, "route"),
        "top_audit_tags_by_previously_unknown_bytes": _top_grouped(
            calls,
            "audit_tag",
        ),
        "attribution_notes": _attribution_notes(calls),
        "calls": [_call_attribution(call) for call in calls],
    }
    if out_dir is not None:
        stamp = timestamp or _timestamp()
        resolved_out_dir = _resolve_path(out_dir)
        resolved_out_dir.mkdir(parents=True, exist_ok=True)
        json_path = resolved_out_dir / f"unknown_context_attribution_audit_{stamp}.json"
        md_path = resolved_out_dir / f"unknown_context_attribution_audit_{stamp}.md"
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
        "# Unknown Context Attribution Audit",
        "",
        f"Generated: {report['generated_at']}",
        f"Smoke file: `{report['smoke_file']}`",
        f"Smoke acceptance: `{'PASS' if report['smoke_acceptance_passed'] else 'FAIL'}`",
        "",
        "## Summary",
        "",
        f"- total_llm_calls: `{summary['total_llm_calls']}`",
        f"- lesson_context_bytes: `{summary['lesson_context_bytes']}`",
        f"- previously_unknown_context_bytes: `{summary['previously_unknown_context_bytes']}`",
        f"- attributed_unknown_context_bytes: `{summary['attributed_unknown_context_bytes']}`",
        f"- unclassified_context_bytes: `{summary['unclassified_context_bytes']}`",
        f"- unclassified_context_share: `{summary['unclassified_context_share']}`",
        "",
        "## Attribution Totals",
        "",
        "| Field | Bytes | Share Of Lesson Context | Share Of Previously Unknown |",
        "|---|---:|---:|---:|",
    ]
    for field, value in summary["attribution_totals"].items():
        lines.append(
            "| `{field}` | {value} | {context_share} | {unknown_share} |".format(
                field=field,
                value=value,
                context_share=summary["attribution_context_shares"].get(field, 0),
                unknown_share=summary["attribution_unknown_shares"].get(field, 0),
            )
        )

    lines.extend(["", "## Top Calls", ""])
    lines.append(
        "| Page | Route | Audit Tag | Previously Unknown | Unclassified | Top Attribution |"
    )
    lines.append("|---|---|---|---:|---:|---|")
    for call in report["top_calls_by_previously_unknown_bytes"][:10]:
        lines.append(
            "| `{page_uid}` | `{route}` | `{audit_tag}` | {previously_unknown_context_bytes} | {unclassified_context_bytes} | `{top_attribution_field}` |".format(
                **call
            )
        )

    lines.extend(["", "## Top Pages", ""])
    lines.append(
        "| Page | Calls | Previously Unknown | Unclassified | Top Attribution |"
    )
    lines.append("|---|---:|---:|---:|---|")
    for row in report["top_pages_by_previously_unknown_bytes"][:10]:
        lines.append(
            "| `{page_uid}` | {call_count} | {previously_unknown_context_bytes} | {unclassified_context_bytes} | `{top_attribution_field}` |".format(
                **row
            )
        )

    lines.extend(["", "## Top Routes", ""])
    lines.append(
        "| Route | Calls | Previously Unknown | Unclassified | Top Attribution |"
    )
    lines.append("|---|---:|---:|---:|---|")
    for row in report["top_routes_by_previously_unknown_bytes"]:
        lines.append(
            "| `{route}` | {call_count} | {previously_unknown_context_bytes} | {unclassified_context_bytes} | `{top_attribution_field}` |".format(
                **row
            )
        )

    lines.extend(["", "## Notes", ""])
    for note in report["attribution_notes"]:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def _summary(calls: list[dict[str, Any]]) -> dict[str, Any]:
    lesson_context_bytes = sum(_int(call.get("lesson_context_bytes")) for call in calls)
    attribution_totals = {
        field: sum(_int(call.get(field)) for call in calls)
        for field in ATTRIBUTION_FIELDS
    }
    previously_unknown = sum(attribution_totals.values())
    unclassified = attribution_totals["unclassified_context_bytes"]
    return {
        "total_llm_calls": len(calls),
        "lesson_context_bytes": lesson_context_bytes,
        "previously_unknown_context_bytes": previously_unknown,
        "attributed_unknown_context_bytes": previously_unknown - unclassified,
        "unclassified_context_bytes": unclassified,
        "previously_unknown_context_share": _share(
            previously_unknown,
            lesson_context_bytes,
        ),
        "unclassified_context_share": _share(unclassified, lesson_context_bytes),
        "attribution_totals": attribution_totals,
        "attribution_context_shares": {
            field: _share(value, lesson_context_bytes)
            for field, value in attribution_totals.items()
        },
        "attribution_unknown_shares": {
            field: _share(value, previously_unknown)
            for field, value in attribution_totals.items()
        },
    }


def _top_calls(calls: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    rows = [_call_attribution(call) for call in calls]
    return sorted(
        rows,
        key=lambda row: (
            -int(row["previously_unknown_context_bytes"]),
            str(row["call_id"]),
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
        totals = {
            field: sum(_int(call.get(field)) for call in group)
            for field in ATTRIBUTION_FIELDS
        }
        previously_unknown = sum(totals.values())
        top_field = _top_attribution_field(totals)
        rows.append(
            {
                key: value,
                "call_count": len(group),
                "previously_unknown_context_bytes": previously_unknown,
                "avg_previously_unknown_context_bytes": _average(
                    [
                        sum(_int(call.get(field)) for field in ATTRIBUTION_FIELDS)
                        for call in group
                    ]
                ),
                "unclassified_context_bytes": totals["unclassified_context_bytes"],
                "top_attribution_field": top_field,
                "attribution_totals": totals,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -int(row["previously_unknown_context_bytes"]),
            str(row.get(key, "")),
        ),
    )[:limit]


def _call_attribution(call: dict[str, Any]) -> dict[str, Any]:
    totals = {field: _int(call.get(field)) for field in ATTRIBUTION_FIELDS}
    previously_unknown = sum(totals.values())
    return {
        "call_id": _text(call.get("call_id")),
        "page_uid": _text(call.get("page_uid")),
        "page_label": _text(call.get("page_label")),
        "step": _text(call.get("step")),
        "route": _text(call.get("route")),
        "audit_tag": _text(call.get("audit_tag")),
        "lesson_context_bytes": _int(call.get("lesson_context_bytes")),
        "previously_unknown_context_bytes": previously_unknown,
        "unclassified_context_bytes": totals["unclassified_context_bytes"],
        "top_attribution_field": _top_attribution_field(totals),
        "attribution_fields": totals,
    }


def _top_attribution_field(values: dict[str, int]) -> str:
    if not values:
        return "none"
    field, value = max(values.items(), key=lambda item: (item[1], item[0]))
    return field if value > 0 else "none"


def _attribution_notes(calls: list[dict[str, Any]]) -> list[str]:
    summary = _summary(calls)
    totals = summary["attribution_totals"]
    notes = [
        "This audit explains metering overhead only; it does not trim prompts or change lesson behavior.",
        "`unknown_context_bytes` now means remaining unclassified bytes, while `other_bytes` is the sum of attributed overhead buckets.",
    ]
    if totals.get("json_serialization_overhead_bytes", 0) > 0:
        notes.append(
            "`json_serialization_overhead_bytes` is pretty JSON whitespace/indentation overhead."
        )
    if totals.get("prompt_frame_overhead_bytes", 0) > 0:
        notes.append(
            "`prompt_frame_overhead_bytes` is JSON key/frame wrapper cost after known values are attributed."
        )
    if summary["unclassified_context_bytes"] == 0:
        notes.append("No residual unclassified context bytes remain in the current smoke report.")
    return notes


def _share(value: int, denominator: int) -> float:
    return round(value / max(1, denominator), 4)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-report", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    smoke_path = args.smoke_report or latest_smoke_report(args.out_dir)
    report = audit_unknown_context_attribution(
        smoke_report_path=smoke_path,
        out_dir=args.out_dir,
    )
    print(
        json.dumps(
            {
                "json_path": report["json_path"],
                "markdown_path": report["markdown_path"],
                "summary": report["summary"],
                "top_pages_by_previously_unknown_bytes": report[
                    "top_pages_by_previously_unknown_bytes"
                ][:5],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
