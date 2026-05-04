#!/usr/bin/env python3
"""Audit gentle_redirect classroom experience from smoke and TeachingMove reports."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any


REPORT_KIND = "lesson_redirect_experience_audit"
DEFAULT_ARTIFACT_DIR = Path("temp/lesson-smoke-artifacts")

MECHANICAL_PHRASES = (
    "你刚才说的是",
    "先回到课本目标",
    "把这句读出来",
    "我们先说这个",
    "这一步先听清这个问题",
    "先听，再说",
    "你来读",
)
WARM_ACK_RE = re.compile(
    r"你(?:刚才|刚刚)?(?:说的是|说了|提到|刚说了)|我听到了|I heard",
    re.I,
)
CHINESE_SCAFFOLD_RE = re.compile(
    r"意思是|中文是|也就是|（[^）]{0,24}[\u3400-\u9fff][^）]{0,24}）|"
    r"\([^)]{0,24}[\u3400-\u9fff][^)]{0,24}\)"
)
TARGET_SELECTION_ISSUE_RE = re.compile(
    r"\b(?:can you try|comprehension ques|a table showing tr|cl'\s+as\s+in)\b",
    re.I,
)
PUNCTUATION_ISSUE_RE = re.compile(r"，。|,\s*\.|[，,：:；;\-—]\s*$")
ACTION_RE = re.compile(
    r"跟我读|请跟|你来读|先读|读一遍|说一说|试试|试试看|告诉老师|"
    r"回答老师|用[^。！？\n]{0,30}回答|先回答|选择|你先说|你能",
    re.I,
)
ENGLISH_RE = re.compile(r"[A-Za-z]")
CHINESE_RE = re.compile(r"[\u3400-\u9fff]")
SHORT_ENGLISH_INPUT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9' .-]{0,48}[?!.]?$")

DELIBERATE_SMOKE_INPUTS = {
    "i want to play basketball",
    "i played football yesterday",
    "yesterday i played football",
    "water",
}
MODULE_CHOICE_RE = re.compile(r"第[一二三四五六七八九十]块|哪一块|先学第|第一块|第二块|模块")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (_repo_root() / path).resolve()


def _load_json(path: Path) -> dict[str, Any]:
    resolved = _resolve_path(path)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{resolved} does not contain a JSON object")
    return payload


def _as_text(value: Any) -> str:
    return str(value or "")


def _shorten(text: str, *, limit: int = 220) -> str:
    compact = " ".join(_as_text(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def latest_smoke_report(artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path:
    reports = sorted(
        _resolve_path(artifact_dir).glob("lesson_smoke_matrix_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        raise FileNotFoundError(f"No lesson_smoke_matrix_*.json found in {artifact_dir}")
    return reports[0]


def latest_teaching_move_audit(artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path:
    reports = sorted(
        _resolve_path(artifact_dir).glob("teaching_move_audit_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        raise FileNotFoundError(f"No teaching_move_audit_*.json found in {artifact_dir}")
    return reports[0]


def latest_classroom_quality_audit(artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path | None:
    reports = sorted(
        _resolve_path(artifact_dir).glob("classroom_quality_audit_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return reports[0] if reports else None


def _turn_key(record: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        _as_text(record.get("page_uid")),
        _as_text(record.get("step")),
        _as_text(record.get("learner_input")),
        _as_text(record.get("route")),
        _as_text(record.get("turn_label")),
    )


def _attach_smoke_turns(
    moves: list[dict[str, Any]],
    turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    lookup: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for turn in turns:
        lookup[_turn_key(turn)].append(turn)

    used_ids: set[int] = set()
    aligned: list[dict[str, Any]] = []
    for move in moves:
        smoke_turn: dict[str, Any] = {}
        for candidate in lookup.get(_turn_key(move), []):
            candidate_id = id(candidate)
            if candidate_id in used_ids:
                continue
            smoke_turn = candidate
            used_ids.add(candidate_id)
            break
        aligned.append({**move, "smoke_turn": smoke_turn})
    return aligned


def _payload_fields(move: dict[str, Any]) -> dict[str, Any]:
    payload = move.get("payload") if isinstance(move.get("payload"), dict) else {}
    fields = payload.get("payload_fields") if isinstance(payload.get("payload_fields"), dict) else {}
    return fields


def _block_uid(move: dict[str, Any]) -> str:
    fields = _payload_fields(move)
    smoke_turn = move.get("smoke_turn") if isinstance(move.get("smoke_turn"), dict) else {}
    return (
        _as_text(fields.get("preserve_block_uid"))
        or _as_text(smoke_turn.get("state_block_uid"))
        or _as_text(move.get("runtime_block_uid"))
    )


def _page_metadata(smoke_report: dict[str, Any], turns: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    pages = smoke_report.get("pages")
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_uid = _as_text(page.get("page_uid"))
            if not page_uid:
                continue
            metadata[page_uid] = {
                "book": _as_text(page.get("book")),
                "page_label": _as_text(page.get("label") or page.get("page_label")),
                "page_risk": _as_text(page.get("risk") or page.get("page_risk")),
                "block_count": int(page.get("block_count") or 0),
            }
    for turn in turns:
        page_uid = _as_text(turn.get("page_uid"))
        if not page_uid:
            continue
        record = metadata.setdefault(
            page_uid,
            {"book": "", "page_label": "", "page_risk": "", "block_count": 0},
        )
        record["book"] = record["book"] or _as_text(turn.get("book"))
        record["page_label"] = record["page_label"] or _as_text(turn.get("page_label"))
        record["page_risk"] = record["page_risk"] or _as_text(turn.get("page_risk"))
        if not record["block_count"]:
            record["block_count"] = int(turn.get("block_count") or 0)
    return metadata


def _answer_turn_counts(turns: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for turn in turns:
        if turn.get("turn_label") != "answer_question":
            continue
        counts[_as_text(turn.get("page_uid"))] += 1
    return counts


def _normalize_input(value: str) -> str:
    return value.strip().strip("\"'“”.,!?。！？").casefold()


def _is_deliberate_smoke_input(learner_input: str) -> bool:
    normalized = _normalize_input(learner_input)
    return normalized in DELIBERATE_SMOKE_INPUTS or "play basketball" in normalized


def _input_relevance(*, learner_input: str, interpreted_intent: str) -> str:
    if _is_deliberate_smoke_input(learner_input):
        return "deliberate_smoke_probe"
    if interpreted_intent == "off_topic":
        return "off_topic"
    if interpreted_intent in {"short_answer_pullback", "free_input_pullback"}:
        return "related_or_partial"
    return "unknown"


def _mechanical_hits(response: str) -> list[str]:
    return [phrase for phrase in MECHANICAL_PHRASES if phrase in response]


def _has_warm_ack(*, response: str, learner_input: str) -> bool:
    if WARM_ACK_RE.search(response):
        return True
    normalized_input = _normalize_input(learner_input)
    return bool(normalized_input and normalized_input in response.casefold())


def _has_short_chinese_scaffold(response: str) -> bool:
    return bool(CHINESE_SCAFFOLD_RE.search(response))


def _english_target_is_clear(*, response: str, target_phrase: str, active_prompt: str, return_anchor: str) -> bool:
    for candidate in (target_phrase, active_prompt, return_anchor):
        compact = " ".join(_as_text(candidate).split()).strip().strip(".。")
        if len(compact) < 2 or not ENGLISH_RE.search(compact):
            continue
        if compact.casefold() in response.casefold():
            return True
    return False


def _action_count(response: str) -> int:
    return len(ACTION_RE.findall(response))


def _punctuation_issues(response: str) -> list[str]:
    issues: list[str] = []
    if "，。" in response:
        issues.append("comma_then_period")
    if PUNCTUATION_ISSUE_RE.search(response):
        issues.append("dangling_punctuation")
    return issues


def _target_selection_issues(*, response: str, target_phrase: str) -> list[str]:
    issues: list[str] = []
    target = _as_text(target_phrase)
    target_has_bad_fragment = TARGET_SELECTION_ISSUE_RE.search(target) and not re.search(
        r"learn\s+the\s+consonant\s+blend\s+['’\"]?[a-z]{1,3}['’\"]?\s+as\s+in\s+['’\"]?[a-z]+['’\"]?",
        target,
        flags=re.I,
    )
    if TARGET_SELECTION_ISSUE_RE.search(response) or target_has_bad_fragment:
        issues.append("bad_target_fragment")
    return issues


def _missing_scaffold_translation(*, learner_input: str, response: str) -> bool:
    compact_input = " ".join(learner_input.split())
    if not compact_input or not SHORT_ENGLISH_INPUT_RE.match(compact_input):
        return False
    if len(compact_input.split()) > 4:
        return False
    if not ENGLISH_RE.search(compact_input):
        return False
    return CHINESE_RE.search(response) is not None and not _has_short_chinese_scaffold(response)


def _long_chinese_explanation(response: str) -> bool:
    cjk_count = len(CHINESE_RE.findall(response))
    return cjk_count >= 90


def _english_chinese_mixed(response: str) -> bool:
    for sentence in re.split(r"[。！？\n]+", response):
        if len(sentence) >= 48 and CHINESE_RE.search(sentence) and ENGLISH_RE.search(sentence):
            return True
    return False


def _sample_turn(move: dict[str, Any]) -> dict[str, Any]:
    fields = _payload_fields(move)
    smoke_turn = move.get("smoke_turn") if isinstance(move.get("smoke_turn"), dict) else {}
    response = _as_text(smoke_turn.get("teacher_response"))
    learner_input = _as_text(move.get("learner_input"))
    interpreted_intent = _as_text(fields.get("interpreted_intent"))
    target_phrase = _as_text(fields.get("target_phrase"))
    active_prompt = _as_text(fields.get("active_prompt"))
    return_anchor = _as_text(fields.get("return_anchor"))
    target_selection_issues = _target_selection_issues(
        response=response,
        target_phrase=target_phrase,
    )
    target_clear = _english_target_is_clear(
        response=response,
        target_phrase=target_phrase,
        active_prompt=active_prompt,
        return_anchor=return_anchor,
    )
    actions = _action_count(response)
    return {
        "step": _as_text(move.get("step")),
        "block_uid": _block_uid(move),
        "learner_input": learner_input,
        "student_input_relevance": _input_relevance(
            learner_input=learner_input,
            interpreted_intent=interpreted_intent,
        ),
        "interpreted_intent": interpreted_intent,
        "target_phrase": target_phrase,
        "active_prompt": active_prompt,
        "return_anchor": return_anchor,
        "teacher_response_excerpt": _shorten(response, limit=260),
        "has_warm_ack": _has_warm_ack(response=response, learner_input=learner_input),
        "has_short_chinese_scaffold": _has_short_chinese_scaffold(response),
        "missing_scaffold_translation": _missing_scaffold_translation(
            learner_input=learner_input,
            response=response,
        ),
        "long_chinese_explanation": _long_chinese_explanation(response),
        "english_target_is_clear": target_clear,
        "english_chinese_mixed_long_sentence": _english_chinese_mixed(response),
        "one_next_action": actions <= 1,
        "action_count": actions,
        "mechanical_phrase_hits": _mechanical_hits(response),
        "punctuation_issues": _punctuation_issues(response),
        "target_selection_issues": sorted(set(target_selection_issues)),
        "module_choice_mismatch": bool(MODULE_CHOICE_RE.search(response))
        and "module" not in _as_text(fields.get("next_action")).casefold(),
    }


def _student_relevance_summary(samples: list[dict[str, Any]]) -> str:
    counts = Counter(_as_text(sample.get("student_input_relevance")) for sample in samples)
    total = len(samples)
    if total and counts["deliberate_smoke_probe"] / total >= 0.5:
        return "mostly_deliberate_smoke_probe"
    if counts["related_or_partial"] >= 2:
        return "mixed_with_related_inputs"
    if total and counts["off_topic"] / total >= 0.5:
        return "mostly_off_topic"
    return "mixed"


def _experience_classification(samples: list[dict[str, Any]]) -> tuple[str, str, str]:
    target_issue_count = sum(bool(sample["target_selection_issues"]) for sample in samples)
    answer_scope_issue_count = sum(bool(sample["module_choice_mismatch"]) for sample in samples)
    overloaded_count = sum(
        not sample["one_next_action"]
        or sample["long_chinese_explanation"]
        or sample["english_chinese_mixed_long_sentence"]
        for sample in samples
    )
    missing_scaffold_count = sum(bool(sample["missing_scaffold_translation"]) for sample in samples)
    mechanical_count = sum(bool(sample["mechanical_phrase_hits"]) for sample in samples)
    relevance = _student_relevance_summary(samples)

    if target_issue_count:
        return (
            "target_selection_issue",
            "target_selection_issue",
            "target_selection",
        )
    if answer_scope_issue_count:
        return (
            "answer_scope_issue",
            "answer_scope_issue",
            "answer_scope",
        )
    if overloaded_count >= 2:
        return (
            "overloaded_redirect",
            "overloaded_redirect",
            "wording_variant",
        )
    if missing_scaffold_count >= 2:
        return (
            "missing_scaffold_translation",
            "missing_scaffold_translation",
            "scaffold_translation",
        )
    if mechanical_count >= 2:
        return (
            "wording_too_mechanical",
            "wording_too_mechanical",
            "wording_variant",
        )
    if relevance in {"mostly_deliberate_smoke_probe", "mostly_off_topic"}:
        return (
            "normal_test_artifact",
            "normal_test_artifact",
            "no_change",
        )
    return (
        "needs_runtime_review",
        "needs_runtime_review",
        "runtime_review",
    )


def _page_record(
    *,
    page_uid: str,
    moves: list[dict[str, Any]],
    page_meta: dict[str, dict[str, Any]],
    answer_turn_counts: Counter[str],
) -> dict[str, Any]:
    samples = [_sample_turn(move) for move in moves]
    redirect_count = len(samples)
    answer_turn_count = answer_turn_counts.get(page_uid, redirect_count)
    classification, primary_issue, fix_scope = _experience_classification(samples)
    issue_counts = {
        "mechanical_phrase_turn_count": sum(bool(sample["mechanical_phrase_hits"]) for sample in samples),
        "missing_scaffold_translation_count": sum(bool(sample["missing_scaffold_translation"]) for sample in samples),
        "overloaded_turn_count": sum(
            not sample["one_next_action"]
            or sample["long_chinese_explanation"]
            or sample["english_chinese_mixed_long_sentence"]
            for sample in samples
        ),
        "target_selection_issue_count": sum(bool(sample["target_selection_issues"]) for sample in samples),
        "punctuation_issue_count": sum(bool(sample["punctuation_issues"]) for sample in samples),
        "module_choice_mismatch_count": sum(bool(sample["module_choice_mismatch"]) for sample in samples),
    }
    meta = page_meta.get(page_uid, {})
    relevance = _student_relevance_summary(samples)
    return {
        "page_uid": page_uid,
        "book": _as_text(meta.get("book")),
        "page_label": _as_text(meta.get("page_label")),
        "page_risk": _as_text(meta.get("page_risk")),
        "block_count": int(meta.get("block_count") or 0),
        "redirect_count": redirect_count,
        "answer_turn_count": answer_turn_count,
        "redirect_rate": _ratio(redirect_count, answer_turn_count),
        "experience_classification": classification,
        "primary_issue": primary_issue,
        "student_input_relevance": relevance,
        "has_warm_ack": any(sample["has_warm_ack"] for sample in samples),
        "has_short_chinese_scaffold": any(sample["has_short_chinese_scaffold"] for sample in samples),
        "english_target_is_clear": all(sample["english_target_is_clear"] for sample in samples),
        "one_next_action": all(sample["one_next_action"] for sample in samples),
        "mechanical_phrase_hits": sorted(
            {
                phrase
                for sample in samples
                for phrase in sample["mechanical_phrase_hits"]
            }
        ),
        "issue_counts": issue_counts,
        "recommended_fix_scope": fix_scope,
        "sample_turns": samples[:6],
    }


def _hotspot_page_uids(
    *,
    classroom_quality_report: dict[str, Any] | None,
    moves_by_page: dict[str, list[dict[str, Any]]],
    answer_turn_counts: Counter[str],
) -> list[str]:
    if classroom_quality_report:
        top_pages = classroom_quality_report.get("top_redirect_pages")
        if isinstance(top_pages, list):
            page_uids = [
                _as_text(page.get("page_uid"))
                for page in top_pages
                if isinstance(page, dict) and _as_text(page.get("page_uid"))
            ]
            if page_uids:
                return page_uids

    ranked = sorted(
        moves_by_page,
        key=lambda page_uid: (
            -len(moves_by_page[page_uid]),
            -_ratio(len(moves_by_page[page_uid]), answer_turn_counts.get(page_uid, 0)),
            page_uid,
        ),
    )
    return ranked[:10]


def audit_redirect_experience(
    *,
    smoke_report_path: Path,
    teaching_move_audit_path: Path,
    classroom_quality_audit_path: Path | None = None,
) -> dict[str, Any]:
    resolved_smoke_path = _resolve_path(smoke_report_path)
    resolved_teaching_path = _resolve_path(teaching_move_audit_path)
    resolved_classroom_path = (
        _resolve_path(classroom_quality_audit_path)
        if classroom_quality_audit_path is not None
        else None
    )

    smoke_report = _load_json(resolved_smoke_path)
    teaching_report = _load_json(resolved_teaching_path)
    classroom_report = (
        _load_json(resolved_classroom_path)
        if resolved_classroom_path is not None and resolved_classroom_path.exists()
        else None
    )
    turns_raw = smoke_report.get("turns")
    moves_raw = teaching_report.get("moves")
    if not isinstance(turns_raw, list):
        raise ValueError(f"{resolved_smoke_path} does not contain a turn list")
    if not isinstance(moves_raw, list):
        raise ValueError(f"{resolved_teaching_path} does not contain a move list")

    turns = [turn for turn in turns_raw if isinstance(turn, dict)]
    moves = [move for move in moves_raw if isinstance(move, dict)]
    aligned_moves = _attach_smoke_turns(moves, turns)
    gentle_moves = [move for move in aligned_moves if move.get("move_type") == "gentle_redirect"]
    moves_by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for move in gentle_moves:
        page_uid = _as_text(move.get("page_uid"))
        if page_uid:
            moves_by_page[page_uid].append(move)

    answer_turn_counts = _answer_turn_counts(turns)
    page_meta = _page_metadata(smoke_report, turns)
    hotspot_uids = _hotspot_page_uids(
        classroom_quality_report=classroom_report,
        moves_by_page=moves_by_page,
        answer_turn_counts=answer_turn_counts,
    )
    hotspot_pages = [
        _page_record(
            page_uid=page_uid,
            moves=moves_by_page[page_uid],
            page_meta=page_meta,
            answer_turn_counts=answer_turn_counts,
        )
        for page_uid in hotspot_uids
        if moves_by_page.get(page_uid)
    ]
    classification_counts = Counter(
        page["experience_classification"] for page in hotspot_pages
    )
    smoke_summary = smoke_report.get("summary") if isinstance(smoke_report.get("summary"), dict) else {}
    teaching_summary = teaching_report.get("summary") if isinstance(teaching_report.get("summary"), dict) else {}
    generated_at = datetime.now().isoformat(timespec="seconds")
    summary = {
        "smoke_file": str(resolved_smoke_path),
        "teaching_move_audit_file": str(resolved_teaching_path),
        "classroom_quality_audit_file": str(resolved_classroom_path or ""),
        "page_count": int(smoke_summary.get("page_count") or len({turn.get("page_uid") for turn in turns})),
        "turn_count": int(smoke_summary.get("turn_count") or len(turns)),
        "gentle_redirect_count": len(gentle_moves),
        "hotspot_page_count": len(hotspot_pages),
        "smoke_acceptance_passed": bool(smoke_summary.get("acceptance_passed")),
        "teaching_move_audit_passed": bool(teaching_summary.get("audit_passed")),
        "audit_passed": bool(smoke_summary.get("acceptance_passed"))
        and bool(teaching_summary.get("audit_passed")),
        "generated_at": generated_at,
        "experience_classification_counts": dict(sorted(classification_counts.items())),
        "candidate_policy": (
            "This is a read-only S3 redirect experience diagnostic. It does not "
            "change smoke acceptance, runtime routing, responder prompts, RAG, S4, "
            "or classification policy."
        ),
    }
    return {
        "kind": REPORT_KIND,
        "generated_at": generated_at,
        "smoke_regression_set_id": smoke_report.get("regression_set_id"),
        "summary": summary,
        "smoke_summary": smoke_summary,
        "teaching_move_summary": teaching_summary,
        "hotspot_pages": hotspot_pages,
        "normal_test_artifact_pages": [
            page for page in hotspot_pages if page["experience_classification"] == "normal_test_artifact"
        ],
        "wording_too_mechanical_pages": [
            page for page in hotspot_pages if page["experience_classification"] == "wording_too_mechanical"
        ],
        "missing_scaffold_translation_pages": [
            page for page in hotspot_pages if page["experience_classification"] == "missing_scaffold_translation"
        ],
        "overloaded_redirect_pages": [
            page for page in hotspot_pages if page["experience_classification"] == "overloaded_redirect"
        ],
        "target_selection_issue_pages": [
            page for page in hotspot_pages if page["experience_classification"] == "target_selection_issue"
        ],
        "answer_scope_issue_pages": [
            page for page in hotspot_pages if page["experience_classification"] == "answer_scope_issue"
        ],
        "needs_runtime_review_pages": [
            page for page in hotspot_pages if page["experience_classification"] == "needs_runtime_review"
        ],
        "interpretation": [
            (
                "High gentle_redirect volume can be a normal smoke artifact when "
                "the fixed matrix deliberately sends unrelated or rapid inputs."
            ),
            (
                "The issue fields identify S3 wording, scaffold, overload, target, "
                "and answer-scope review candidates. They are not runtime regressions."
            ),
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Redirect Experience Audit",
        "",
        "## Summary",
        f"- Smoke acceptance: {'PASS' if summary['smoke_acceptance_passed'] else 'FAIL'}",
        f"- Pages: {summary['page_count']}",
        f"- Turns: {summary['turn_count']}",
        f"- gentle_redirect: {summary['gentle_redirect_count']}",
        f"- Hotspot pages: {summary['hotspot_page_count']}",
        f"- Audit passed: {str(summary['audit_passed']).lower()}",
        f"- Smoke file: `{summary['smoke_file']}`",
        f"- TeachingMove audit file: `{summary['teaching_move_audit_file']}`",
        "",
        "## Classification Counts",
    ]
    for key, count in summary["experience_classification_counts"].items():
        lines.append(f"- {key}: {count}")

    lines.extend(
        [
            "",
            "## Redirect Hotspots",
            (
                "| Page | Label | Redirects | Rate | Classification | "
                "Primary Issue | Relevance | Fix Scope |"
            ),
            "|---|---|---:|---:|---|---|---|---|",
        ]
    )
    for page in report["hotspot_pages"]:
        lines.append(
            "| "
            f"`{page['page_uid']}` | {page['page_label']} | "
            f"{page['redirect_count']} | {page['redirect_rate']:.2f} | "
            f"{page['experience_classification']} | {page['primary_issue']} | "
            f"{page['student_input_relevance']} | {page['recommended_fix_scope']} |"
        )

    lines.extend(["", "## Sample Findings"])
    for page in report["hotspot_pages"][:8]:
        lines.append(
            f"- `{page['page_uid']}` {page['experience_classification']}: "
            f"mechanical={page['issue_counts']['mechanical_phrase_turn_count']}, "
            f"missing_scaffold={page['issue_counts']['missing_scaffold_translation_count']}, "
            f"overloaded={page['issue_counts']['overloaded_turn_count']}, "
            f"target_issue={page['issue_counts']['target_selection_issue_count']}"
        )
        for sample in page["sample_turns"][:2]:
            lines.append(
                f"  - {sample['step']} `{sample['learner_input']}` -> "
                f"{sample['teacher_response_excerpt']}"
            )

    lines.extend(["", "## Interpretation"])
    for note in report["interpretation"]:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], out_dir: Path = DEFAULT_ARTIFACT_DIR) -> tuple[Path, Path]:
    resolved_out_dir = _resolve_path(out_dir)
    resolved_out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    json_path = resolved_out_dir / f"redirect_experience_audit_{stamp}.json"
    md_path = resolved_out_dir / f"redirect_experience_audit_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a read-only redirect experience audit from lesson smoke reports.",
    )
    parser.add_argument("--smoke-report", type=Path, default=None)
    parser.add_argument("--teaching-move-audit", type=Path, default=None)
    parser.add_argument("--classroom-quality-audit", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    smoke_report = args.smoke_report or latest_smoke_report()
    teaching_move_audit = args.teaching_move_audit or latest_teaching_move_audit()
    classroom_quality_audit = (
        args.classroom_quality_audit
        if args.classroom_quality_audit is not None
        else latest_classroom_quality_audit()
    )
    report = audit_redirect_experience(
        smoke_report_path=smoke_report,
        teaching_move_audit_path=teaching_move_audit,
        classroom_quality_audit_path=classroom_quality_audit,
    )
    json_path, md_path = write_report(report, args.out_dir)
    print(
        json.dumps(
            {
                "json_path": str(json_path),
                "markdown_path": str(md_path),
                "summary": report["summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
