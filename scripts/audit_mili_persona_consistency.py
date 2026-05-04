#!/usr/bin/env python3
"""Audit Mili persona wiring, leakage, tone signals, and token impact."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path
import re
from typing import Any


REPORT_KIND = "mili_persona_consistency_audit"
DEFAULT_ARTIFACT_DIR = Path("temp/lesson-smoke-artifacts")

FULL_SOUL_MARKERS = (
    "# Teacher Soul",
    "Long-form Identity",
    "Sample Lines",
    "Runtime Summary",
)
INTEREST_MARKERS = (
    "海鲜螺蛳粉",
    "课堂手账",
    "周末去海边看日落",
    "英语节奏操练",
    "Live2D 与语音互动",
    "周末看推理动画",
)
SAMPLE_LINES = (
    "这一页我们学点好吃的，先热个身。",
    "差一点点，这个词我们单拎出来练。",
    "你已经听懂了，现在把嘴巴也带起来。",
    "先别急，我给你一个小提示。",
    "你卡的是哪个词？先指给我，我把它拆小。",
    "这个词没错，只是现在这轮问的是喝的，不是吃的。",
    "我先示范，你跟我半句半句来。",
    "现在你口渴了，跟老师说一句：I'd like some tea.",
    "关键词你已经抓到了，这一页先收一下，我们接下一小题。",
)

WARM_ACK_RE = re.compile(
    r"你(?:刚才|刚刚)?(?:说的是|说了|说|提到|刚说了)|我听到了|I heard",
    re.I,
)
ACTION_RE = re.compile(
    r"跟我读|请跟|你来读|先读|读一遍|说一说|试试|试试看|告诉老师|"
    r"回答老师|用[^。！？\n]{0,30}回答|先回答|选择|你先说|你先读|你可以",
    re.I,
)
SHORT_SCAFFOLD_RE = re.compile(
    r"（[^）]{0,28}[\u3400-\u9fff][^）]{0,28}）|"
    r"\([^)]{0,28}[\u3400-\u9fff][^)]{0,28}\)|"
    r"意思是|中文是|也就是"
)
GENERIC_PRAISE_RE = re.compile(r"很棒|很好|不错|真好|太棒|good job", re.I)
OVERPLAY_PERSONA_RE = re.compile(
    r"海鲜螺蛳粉|课堂手账|海边看日落|推理动画|我是米粒|米粒来啦|卖萌|嘿嘿"
)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (_repo_root() / path).resolve()


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    resolved = _resolve_path(path)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{resolved} does not contain a JSON object")
    return payload


def _latest(pattern: str, artifact_dir: Path) -> Path | None:
    reports = sorted(
        _resolve_path(artifact_dir).glob(pattern),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return reports[0] if reports else None


def latest_smoke_report(artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path:
    path = _latest("lesson_smoke_matrix_*.json", artifact_dir)
    if path is None:
        raise FileNotFoundError(f"No lesson_smoke_matrix_*.json found in {artifact_dir}")
    return path


def audit_mili_persona_consistency(
    *,
    smoke_report_path: Path,
    token_audit_path: Path | None = None,
    context_audit_path: Path | None = None,
    redirect_audit_path: Path | None = None,
    out_dir: Path | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    resolved_smoke_path = _resolve_path(smoke_report_path)
    smoke_report = _load_json(resolved_smoke_path)
    token_audit = _load_json(token_audit_path)
    context_audit = _load_json(context_audit_path)
    redirect_audit = _load_json(redirect_audit_path)
    turns = [turn for turn in smoke_report.get("turns") or [] if isinstance(turn, dict)]
    calls = _extract_llm_calls(turns)

    wiring = _persona_wiring(turns=turns, calls=calls)
    tone = _persona_tone_signal(turns)
    token_impact = _token_impact(
        calls=calls,
        token_audit=token_audit,
        context_audit=context_audit,
    )
    overreach = _persona_overreach_guard(
        smoke_report=smoke_report,
        redirect_audit=redirect_audit,
        wiring=wiring,
    )
    audit_passed = (
        wiring["full_soul_leak_count"] == 0
        and wiring["interest_leak_count"] == 0
        and wiring["sample_line_copy_count"] == 0
        and wiring["answer_turn_policy_injected_call_count"] > 0
        and wiring["llm_only_injected_call_count"] == 0
        and wiring["deterministic_injected_turn_count"] == 0
        and wiring["miswired_turn_count"] == 0
    )
    report = {
        "kind": REPORT_KIND,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "smoke_file": str(resolved_smoke_path),
        "token_audit_file": str(_resolve_path(token_audit_path)) if token_audit_path else "",
        "context_audit_file": (
            str(_resolve_path(context_audit_path)) if context_audit_path else ""
        ),
        "redirect_audit_file": (
            str(_resolve_path(redirect_audit_path)) if redirect_audit_path else ""
        ),
        "audit_passed": audit_passed,
        "interpretation": "wiring success != visible personality success",
        "summary": {
            "page_count": _int((smoke_report.get("summary") or {}).get("page_count")),
            "turn_count": _int((smoke_report.get("summary") or {}).get("turn_count")),
            "smoke_acceptance_passed": bool(
                (smoke_report.get("summary") or {}).get("acceptance_passed")
            ),
            "llm_call_count": len(calls),
        },
        "persona_wiring": wiring,
        "persona_tone_signal": tone,
        "persona_overreach_guard": overreach,
        "token_impact": token_impact,
    }
    if out_dir is not None:
        stamp = timestamp or _timestamp()
        resolved_out_dir = _resolve_path(out_dir)
        resolved_out_dir.mkdir(parents=True, exist_ok=True)
        json_path = resolved_out_dir / f"mili_persona_consistency_audit_{stamp}.json"
        md_path = resolved_out_dir / f"mili_persona_consistency_audit_{stamp}.md"
        json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_path.write_text(render_markdown(report), encoding="utf-8")
        report["json_path"] = str(json_path)
        report["markdown_path"] = str(md_path)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    wiring = report["persona_wiring"]
    tone = report["persona_tone_signal"]
    token = report["token_impact"]
    overreach = report["persona_overreach_guard"]
    lines = [
        "# Mili Persona Consistency Audit",
        "",
        f"Generated: {report['generated_at']}",
        f"Smoke file: `{report['smoke_file']}`",
        f"Audit passed: `{'PASS' if report['audit_passed'] else 'FAIL'}`",
        "",
        "> wiring success != visible personality success",
        "",
        "## Wiring",
        "",
        f"- full_soul_leak_count: `{wiring['full_soul_leak_count']}`",
        f"- interest_leak_count: `{wiring['interest_leak_count']}`",
        f"- sample_line_copy_count: `{wiring['sample_line_copy_count']}`",
        f"- answer_turn_policy_injected_call_count: `{wiring['answer_turn_policy_injected_call_count']}`",
        f"- llm_only_injected_call_count: `{wiring['llm_only_injected_call_count']}`",
        f"- deterministic_injected_turn_count: `{wiring['deterministic_injected_turn_count']}`",
        f"- miswired_turn_count: `{wiring['miswired_turn_count']}`",
        "",
        "## Tone Signal",
        "",
        f"- warm_ack_rate: `{tone['warm_ack_rate']}`",
        f"- one_action_rate: `{tone['one_action_rate']}`",
        f"- short_scaffold_rate: `{tone['short_scaffold_rate']}`",
        f"- generic_praise_count: `{tone['generic_praise_count']}`",
        f"- overplay_persona_count: `{tone['overplay_persona_count']}`",
        "",
        "## Overreach Guard",
        "",
        f"- route_guard: `{overreach['route_guard']}`",
        f"- block_guard: `{overreach['block_guard']}`",
        f"- answer_scope_guard: `{overreach['answer_scope_guard']}`",
        f"- interest_smalltalk_guard: `{overreach['interest_smalltalk_guard']}`",
        "",
        "## Token Impact",
        "",
        f"- persona_capsule_bytes_total: `{token['persona_capsule_bytes_total']}`",
        f"- persona_capsule_share: `{token['persona_capsule_share']}`",
        f"- avg_prompt_tokens: `{token['avg_prompt_tokens']}`",
        f"- p95_prompt_tokens: `{token['p95_prompt_tokens']}`",
        f"- max_prompt_tokens: `{token['max_prompt_tokens']}`",
        "",
    ]
    return "\n".join(lines)


def _extract_llm_calls(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for turn in turns:
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
    return {
        "call_id": _text(call.get("call_id")) or f"{page_uid}:{turn.get('step')}:{index}",
        "audit_tag": _text(call.get("audit_tag")),
        "page_uid": page_uid,
        "route": route,
        "turn_label": _text(call.get("turn_label")) or _text(turn.get("turn_label")),
        "prompt_token_estimate": _int(call.get("prompt_token_estimate")),
        "persona_capsule_bytes": _int(call.get("persona_capsule_bytes")),
    }


def _persona_wiring(
    *,
    turns: list[dict[str, Any]],
    calls: list[dict[str, Any]],
) -> dict[str, Any]:
    response_text = "\n".join(_text(turn.get("teacher_response")) for turn in turns)
    answer_injected_calls = [
        call
        for call in calls
        if _text(call.get("route")) == "answer_turn_policy"
        and _int(call.get("persona_capsule_bytes")) > 0
    ]
    llm_only_injected_calls = [
        call
        for call in calls
        if _text(call.get("route")) == "llm_only"
        and _int(call.get("persona_capsule_bytes")) > 0
    ]
    deterministic_injected_turns = [
        turn
        for turn in turns
        if not bool(turn.get("llm_called"))
        and (
            bool(turn.get("current_llm_call_persona_capsule_injected"))
            or _int(turn.get("persona_capsule_bytes_metered")) > 0
        )
    ]
    miswired_turns = [
        turn
        for turn in turns
        if _text(turn.get("route")) != "answer_turn_policy"
        and (
            bool(turn.get("current_llm_call_persona_capsule_injected"))
            or _int(turn.get("persona_capsule_bytes_metered")) > 0
        )
    ]
    return {
        "full_soul_leak_count": _hit_count(response_text, FULL_SOUL_MARKERS),
        "interest_leak_count": _hit_count(response_text, INTEREST_MARKERS),
        "sample_line_copy_count": _hit_count(response_text, SAMPLE_LINES),
        "answer_turn_policy_injected_call_count": len(answer_injected_calls),
        "llm_only_injected_call_count": len(llm_only_injected_calls),
        "deterministic_injected_turn_count": len(deterministic_injected_turns),
        "miswired_turn_count": len(miswired_turns),
        "enabled_turn_count": sum(
            1 for turn in turns if turn.get("answer_turn_policy_persona_capsule_enabled")
        ),
        "configured_byte_values": sorted(
            {
                _int(turn.get("persona_capsule_bytes_configured"))
                for turn in turns
                if turn.get("persona_capsule_bytes_configured") is not None
            }
        ),
        "miswired_examples": [
            _turn_excerpt(turn)
            for turn in miswired_turns[:5]
        ],
    }


def _persona_tone_signal(turns: list[dict[str, Any]]) -> dict[str, Any]:
    response_turns = [
        turn for turn in turns if _text(turn.get("teacher_response"))
    ]
    if not response_turns:
        return {
            "turn_count": 0,
            "warm_ack_rate": 0.0,
            "one_action_rate": 0.0,
            "short_scaffold_rate": 0.0,
            "generic_praise_count": 0,
            "overplay_persona_count": 0,
        }
    warm_ack_count = 0
    one_action_count = 0
    scaffold_count = 0
    generic_praise_count = 0
    overplay_count = 0
    action_counts: Counter[int] = Counter()
    for turn in response_turns:
        response = _text(turn.get("teacher_response"))
        if WARM_ACK_RE.search(response):
            warm_ack_count += 1
        action_count = len(ACTION_RE.findall(response))
        action_counts[action_count] += 1
        if action_count <= 1:
            one_action_count += 1
        if SHORT_SCAFFOLD_RE.search(response):
            scaffold_count += 1
        generic_praise_count += len(GENERIC_PRAISE_RE.findall(response))
        overplay_count += len(OVERPLAY_PERSONA_RE.findall(response))
    denominator = len(response_turns)
    return {
        "turn_count": denominator,
        "warm_ack_rate": _ratio(warm_ack_count, denominator),
        "one_action_rate": _ratio(one_action_count, denominator),
        "short_scaffold_rate": _ratio(scaffold_count, denominator),
        "generic_praise_count": generic_praise_count,
        "overplay_persona_count": overplay_count,
        "action_count_distribution": dict(sorted(action_counts.items())),
    }


def _persona_overreach_guard(
    *,
    smoke_report: dict[str, Any],
    redirect_audit: dict[str, Any],
    wiring: dict[str, Any],
) -> dict[str, Any]:
    summary = smoke_report.get("summary") if isinstance(smoke_report.get("summary"), dict) else {}
    redirect_summary = (
        redirect_audit.get("summary") if isinstance(redirect_audit.get("summary"), dict) else {}
    )
    classification_counts = redirect_summary.get("experience_classification_counts")
    if not isinstance(classification_counts, dict):
        classification_counts = redirect_summary.get("classification_counts")
    if not isinstance(classification_counts, dict):
        classification_counts = {}
    return {
        "route_guard": "pass" if _int(summary.get("issue_count")) == 0 else "review",
        "block_guard": "pass" if _int(summary.get("state_drift_count")) == 0 else "review",
        "answer_scope_guard": (
            "known_out_of_scope"
            if _int(classification_counts.get("answer_scope_issue")) > 0
            else "pass"
        ),
        "interest_smalltalk_guard": (
            "pass" if _int(wiring.get("interest_leak_count")) == 0 else "review"
        ),
        "smoke_issue_count": _int(summary.get("issue_count")),
        "state_drift_count": _int(summary.get("state_drift_count")),
        "redirect_classification_counts": classification_counts,
    }


def _token_impact(
    *,
    calls: list[dict[str, Any]],
    token_audit: dict[str, Any],
    context_audit: dict[str, Any],
) -> dict[str, Any]:
    token_summary = (
        token_audit.get("summary") if isinstance(token_audit.get("summary"), dict) else {}
    )
    context_summary = (
        context_audit.get("summary")
        if isinstance(context_audit.get("summary"), dict)
        else {}
    )
    component_totals = context_summary.get("component_totals")
    if not isinstance(component_totals, dict):
        component_totals = {}
    persona_capsule_total = _int(component_totals.get("persona_capsule_bytes"))
    if persona_capsule_total <= 0:
        persona_capsule_total = sum(_int(call.get("persona_capsule_bytes")) for call in calls)
    total_lesson_context = _int(context_summary.get("total_lesson_context_bytes"))
    if total_lesson_context <= 0:
        total_lesson_context = sum(_int(call.get("prompt_token_estimate")) for call in calls) * 4
    prompt_tokens = [_int(call.get("prompt_token_estimate")) for call in calls]
    return {
        "persona_capsule_bytes_total": persona_capsule_total,
        "persona_capsule_share": round(
            persona_capsule_total / max(1, total_lesson_context),
            4,
        ),
        "avg_prompt_tokens": _int(token_summary.get("avg_prompt_tokens"))
        or _average(prompt_tokens),
        "p95_prompt_tokens": _int(token_summary.get("p95_prompt_tokens"))
        or _percentile(prompt_tokens, 95),
        "max_prompt_tokens": _int(token_summary.get("max_prompt_tokens"))
        or max(prompt_tokens, default=0),
    }


def _turn_excerpt(turn: dict[str, Any]) -> dict[str, Any]:
    return {
        "page_uid": _text(turn.get("page_uid")),
        "step": _text(turn.get("step")),
        "route": _text(turn.get("route")),
        "llm_called": bool(turn.get("llm_called")),
        "metered": _int(turn.get("persona_capsule_bytes_metered")),
    }


def _hit_count(text: str, patterns: tuple[str, ...]) -> int:
    return sum(text.count(pattern) for pattern in patterns if pattern)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _average(values: list[int]) -> int:
    values = [value for value in values if value > 0]
    if not values:
        return 0
    return round(sum(values) / len(values))


def _percentile(values: list[int], percentile: int) -> int:
    values = sorted(value for value in values if value > 0)
    if not values:
        return 0
    index = max(0, math.ceil((percentile / 100) * len(values)) - 1)
    return values[index]


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
    parser.add_argument("--token-audit", type=Path, default=None)
    parser.add_argument("--context-audit", type=Path, default=None)
    parser.add_argument("--redirect-audit", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    smoke_path = args.smoke_report or latest_smoke_report(args.out_dir)
    token_path = args.token_audit or _latest("llm_token_usage_audit_*.json", args.out_dir)
    context_path = args.context_audit or _latest(
        "llm_context_breakdown_audit_*.json",
        args.out_dir,
    )
    redirect_path = args.redirect_audit or _latest(
        "redirect_experience_audit_*.json",
        args.out_dir,
    )
    report = audit_mili_persona_consistency(
        smoke_report_path=smoke_path,
        token_audit_path=token_path,
        context_audit_path=context_path,
        redirect_audit_path=redirect_path,
        out_dir=args.out_dir,
    )
    print(
        json.dumps(
            {
                "json_path": report["json_path"],
                "markdown_path": report["markdown_path"],
                "audit_passed": report["audit_passed"],
                "persona_wiring": report["persona_wiring"],
                "token_impact": report["token_impact"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
