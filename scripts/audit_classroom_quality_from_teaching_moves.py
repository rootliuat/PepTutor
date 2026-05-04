#!/usr/bin/env python3
"""Build an S3 classroom quality diagnostic report from TeachingMove audit output."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


REPORT_KIND = "lesson_classroom_quality_audit"
DEFAULT_ARTIFACT_DIR = Path("temp/lesson-smoke-artifacts")

KNOWN_TARGET_INSTRUCTION_PHRASES = {
    "repeat after me",
    "read after me",
    "listen and repeat",
    "跟我读",
    "你读这一句",
    "把这句读出来",
}
GENERIC_TARGET_PHRASES = {
    "let's talk",
    "lets talk",
    "let's try",
    "lets try",
    "let's learn",
    "lets learn",
    "robin",
    "zoom",
}
CHARACTER_NAME_FRAGMENTS = {
    "amy",
    "john",
    "mike",
    "pedro",
    "robin",
    "sarah",
    "wu binbin",
    "zhang peng",
    "zip",
    "zoom",
}
SHORT_TARGET_FRAGMENTS = {
    "i'm",
    "im",
    "suggestion",
    "can you try",
}
TRUNCATED_TARGET_PREFIXES = (
    "comprehension ques",
    "a table showing tr",
)
TEACHER_ANCHOR_RE = re.compile(
    r"(?:我们先说这个|你读这一句|把这句读出来|跟我读|先读|Repeat after me|Read after me)"
    r"[:：]\s*([^。！？\n]+)",
    re.I,
)
PHONICS_CONTEXT_RE = re.compile(
    r"\b(?:phonics|sound|blend|consonant|vowel)\b|"
    r"发音|拼读|字母组合|/[^/\s]+/|"
    r"(?<![A-Za-z])(?:cl|pl|ow)(?![A-Za-z])",
    re.I,
)
VOCAB_CONTEXT_RE = re.compile(
    r"\b(?:vocab|vocabulary|word|words|lexicon)\b|"
    r"单词|词汇|词义|核心[^。！？\n]{0,12}词|本页词|图片词|食物|饮料",
    re.I,
)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (_repo_root() / path).resolve()


def _as_text(value: Any) -> str:
    return str(value or "")


def _shorten(text: str, *, limit: int = 180) -> str:
    compact = " ".join(_as_text(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _counter_top(values: list[str], *, limit: int = 5) -> list[dict[str, Any]]:
    counter = Counter(value for value in values if value)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _load_json(path: Path) -> dict[str, Any]:
    resolved = _resolve_path(path)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{resolved} does not contain a JSON object")
    return payload


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
                "page_uid": page_uid,
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
            {
                "page_uid": page_uid,
                "book": "",
                "page_label": "",
                "page_risk": "",
                "block_count": 0,
            },
        )
        record["book"] = record["book"] or _as_text(turn.get("book"))
        record["page_label"] = record["page_label"] or _as_text(turn.get("page_label"))
        record["page_risk"] = record["page_risk"] or _as_text(turn.get("page_risk"))
        if not record["block_count"]:
            record["block_count"] = int(turn.get("block_count") or 0)
    return metadata


def _turn_key(record: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        _as_text(record.get("page_uid")),
        _as_text(record.get("step")),
        _as_text(record.get("learner_input")),
        _as_text(record.get("route")),
        _as_text(record.get("turn_label")),
    )


def _turn_lookup(turns: list[dict[str, Any]]) -> dict[tuple[str, str, str, str, str], list[dict[str, Any]]]:
    lookup: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    for turn in turns:
        lookup.setdefault(_turn_key(turn), []).append(turn)
    return lookup


def _attach_smoke_turns(
    moves: list[dict[str, Any]],
    turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    lookup = _turn_lookup(turns)
    used_indexes: set[int] = set()
    aligned: list[dict[str, Any]] = []
    for move in moves:
        candidates = lookup.get(_turn_key(move), [])
        smoke_turn: dict[str, Any] = {}
        for candidate in candidates:
            candidate_id = id(candidate)
            if candidate_id in used_indexes:
                continue
            smoke_turn = candidate
            used_indexes.add(candidate_id)
            break
        aligned.append({**move, "smoke_turn": smoke_turn})
    return aligned


def _payload_fields(move: dict[str, Any]) -> dict[str, Any]:
    payload = move.get("payload")
    if not isinstance(payload, dict):
        return {}
    fields = payload.get("payload_fields")
    return fields if isinstance(fields, dict) else {}


def _block_uid_for_move(move: dict[str, Any]) -> str:
    fields = _payload_fields(move)
    smoke_turn = move.get("smoke_turn") if isinstance(move.get("smoke_turn"), dict) else {}
    return (
        _as_text(fields.get("preserve_block_uid"))
        or _as_text(smoke_turn.get("state_block_uid"))
        or "unknown"
    )


def _answer_turn_counts(
    turns: list[dict[str, Any]],
) -> tuple[dict[str, int], dict[tuple[str, str], int]]:
    by_page: dict[str, int] = {}
    by_block: dict[tuple[str, str], int] = {}
    for turn in turns:
        if turn.get("route") != "answer_turn_policy":
            continue
        page_uid = _as_text(turn.get("page_uid"))
        block_uid = _as_text(turn.get("state_block_uid")) or "unknown"
        if not page_uid:
            continue
        by_page[page_uid] = by_page.get(page_uid, 0) + 1
        by_block[(page_uid, block_uid)] = by_block.get((page_uid, block_uid), 0) + 1
    return by_page, by_block


def _why_flagged(*, redirect_count: int, redirect_rate: float) -> str:
    if redirect_count >= 4 and redirect_rate >= 0.8:
        return "redirect_hotspot: repeated pullbacks on most answer turns"
    if redirect_count >= 4:
        return "redirect_hotspot: repeated pullbacks on this page"
    if redirect_count >= 2 and redirect_rate >= 0.75:
        return "redirect_hotspot: high pullback rate on a small page sample"
    return "info: normal pullback volume"


def _aggregate_by_page(
    *,
    gentle_moves: list[dict[str, Any]],
    page_meta: dict[str, dict[str, Any]],
    answer_turn_by_page: dict[str, int],
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for move in gentle_moves:
        page_uid = _as_text(move.get("page_uid")) or _as_text(_payload_fields(move).get("preserve_page_uid"))
        buckets.setdefault(page_uid or "unknown", []).append(move)

    pages: list[dict[str, Any]] = []
    for page_uid, moves in buckets.items():
        fields = [_payload_fields(move) for move in moves]
        meta = page_meta.get(page_uid, {})
        answer_turn_count = answer_turn_by_page.get(page_uid, 0)
        redirect_count = len(moves)
        redirect_rate = _ratio(redirect_count, answer_turn_count)
        pages.append(
            {
                "page_uid": page_uid,
                "book": _as_text(meta.get("book")),
                "page_label": _as_text(meta.get("page_label")),
                "page_risk": _as_text(meta.get("page_risk")),
                "block_count": int(meta.get("block_count") or 0),
                "gentle_redirect_count": redirect_count,
                "answer_turn_count": answer_turn_count,
                "redirect_rate": redirect_rate,
                "top_learner_input_samples": _counter_top(
                    [_as_text(move.get("learner_input")) for move in moves],
                ),
                "top_target_phrases": _counter_top(
                    [_as_text(field.get("target_phrase")) for field in fields],
                ),
                "top_active_prompts": _counter_top(
                    [_as_text(field.get("active_prompt")) for field in fields],
                ),
                "top_return_anchors": _counter_top(
                    [_as_text(field.get("return_anchor")) for field in fields],
                ),
                "classification": "redirect_hotspot"
                if redirect_count >= 4 or redirect_rate >= 0.75
                else "classroom_quality_candidate",
                "severity": "minor" if redirect_count >= 4 or redirect_rate >= 0.75 else "info",
            }
        )
    return sorted(
        pages,
        key=lambda item: (-int(item["gentle_redirect_count"]), -float(item["redirect_rate"]), item["page_uid"]),
    )


def _aggregate_by_block(
    *,
    gentle_moves: list[dict[str, Any]],
    answer_turn_by_block: dict[tuple[str, str], int],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for move in gentle_moves:
        page_uid = _as_text(move.get("page_uid")) or _as_text(_payload_fields(move).get("preserve_page_uid"))
        block_uid = _block_uid_for_move(move)
        buckets.setdefault((page_uid or "unknown", block_uid), []).append(move)

    blocks: list[dict[str, Any]] = []
    for (page_uid, block_uid), moves in buckets.items():
        answer_turn_count = answer_turn_by_block.get((page_uid, block_uid), 0)
        redirect_count = len(moves)
        sample = moves[0]
        smoke_turn = sample.get("smoke_turn") if isinstance(sample.get("smoke_turn"), dict) else {}
        fields = _payload_fields(sample)
        blocks.append(
            {
                "page_uid": page_uid,
                "block_uid": block_uid,
                "gentle_redirect_count": redirect_count,
                "answer_turn_count": answer_turn_count,
                "redirect_rate": _ratio(redirect_count, answer_turn_count),
                "sample_learner_input": sample.get("learner_input"),
                "sample_teacher_response_excerpt": _shorten(
                    _as_text(smoke_turn.get("teacher_response")),
                    limit=180,
                ),
                "sample_target_phrase": _as_text(fields.get("target_phrase")),
            }
        )
    return sorted(
        blocks,
        key=lambda item: (-int(item["gentle_redirect_count"]), -float(item["redirect_rate"]), item["page_uid"], item["block_uid"]),
    )


def _normalized_phrase(phrase: str) -> str:
    return phrase.strip().strip("。！？!?.,，：:；;“”\"'`").casefold()


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def _target_phrase_reasons(phrase: str) -> list[str]:
    compact = " ".join(_as_text(phrase).split()).strip()
    normalized = _normalized_phrase(compact)
    if not normalized:
        return []

    reasons: list[str] = []
    is_short_ascii_fragment = not _contains_cjk(normalized) and (
        len(normalized.split()) == 1 and len(normalized) <= 12
    )
    if normalized in SHORT_TARGET_FRAGMENTS or is_short_ascii_fragment:
        reasons.append("target_phrase_too_short")
    if normalized in CHARACTER_NAME_FRAGMENTS:
        reasons.append("target_phrase_is_character_name")
    if normalized in GENERIC_TARGET_PHRASES:
        reasons.append("target_phrase_too_generic")
    if normalized in KNOWN_TARGET_INSTRUCTION_PHRASES or normalized.startswith("can you try"):
        reasons.append("target_phrase_is_teacher_instruction")
    if any(normalized.startswith(prefix) for prefix in TRUNCATED_TARGET_PREFIXES):
        reasons.append("target_phrase_looks_truncated")
    return reasons


def _target_phrase_context(move: dict[str, Any], source_field: str, phrase: str) -> str:
    fields = _payload_fields(move)
    smoke_turn = move.get("smoke_turn") if isinstance(move.get("smoke_turn"), dict) else {}
    values = [
        source_field,
        phrase,
        _as_text(move.get("learner_input")),
        _as_text(fields.get("target_phrase")),
        _as_text(fields.get("active_prompt")),
        _as_text(fields.get("return_anchor")),
        _as_text(fields.get("target_role")),
        _as_text(fields.get("expected_student_action")),
        _as_text(fields.get("question_target")),
        _as_text(fields.get("answer_target")),
        _as_text(fields.get("answer_frame")),
        _as_text(fields.get("action_source")),
        _as_text(fields.get("current_target")),
        _as_text(smoke_turn.get("teacher_response")),
        _as_text(smoke_turn.get("page_label")),
        _as_text(smoke_turn.get("page_risk")),
    ]
    return " ".join(value for value in values if value)


def _target_phrase_classification(
    *,
    phrase: str,
    reasons: list[str],
    context: str,
) -> str:
    normalized = _normalized_phrase(phrase)
    bad_anchor_reasons = {
        "target_phrase_is_character_name",
        "target_phrase_too_generic",
        "target_phrase_is_teacher_instruction",
        "target_phrase_looks_truncated",
    }
    if normalized in SHORT_TARGET_FRAGMENTS:
        return "bad_anchor_candidate"
    if any(reason in bad_anchor_reasons for reason in reasons):
        return "bad_anchor_candidate"
    if "target_phrase_too_short" in reasons:
        if PHONICS_CONTEXT_RE.search(context):
            return "legitimate_phonics_target"
        if VOCAB_CONTEXT_RE.search(context):
            return "legitimate_short_vocab_target"
        return "review_target_phrase"
    return "review_target_phrase"


def _candidate_severity(reasons: list[str]) -> str:
    major_reasons = {"target_phrase_looks_truncated", "target_phrase_is_teacher_instruction"}
    if any(reason in major_reasons for reason in reasons):
        return "major_candidate"
    return "minor"


def _teacher_response_anchors(response: str) -> list[str]:
    return [match.group(1).strip() for match in TEACHER_ANCHOR_RE.finditer(response)]


def _target_phrase_audit_items(gentle_moves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for move in gentle_moves:
        page_uid = _as_text(move.get("page_uid")) or _as_text(_payload_fields(move).get("preserve_page_uid"))
        block_uid = _block_uid_for_move(move)
        fields = _payload_fields(move)
        smoke_turn = move.get("smoke_turn") if isinstance(move.get("smoke_turn"), dict) else {}
        phrase_sources = [
            ("target_phrase", _as_text(fields.get("target_phrase"))),
            ("active_prompt", _as_text(fields.get("active_prompt"))),
            ("return_anchor", _as_text(fields.get("return_anchor"))),
        ]
        phrase_sources.extend(
            ("teacher_response_anchor", phrase)
            for phrase in _teacher_response_anchors(_as_text(smoke_turn.get("teacher_response")))
        )
        for source_field, phrase in phrase_sources:
            compact = " ".join(phrase.split()).strip()
            reasons = _target_phrase_reasons(compact)
            if not reasons:
                continue
            key = (page_uid, block_uid, source_field, compact.casefold())
            if key in seen:
                continue
            seen.add(key)
            classification = _target_phrase_classification(
                phrase=compact,
                reasons=reasons,
                context=_target_phrase_context(move, source_field, compact),
            )
            items.append(
                {
                    "page_uid": page_uid,
                    "block_uid": block_uid,
                    "phrase": compact,
                    "source_field": source_field,
                    "reason": ";".join(reasons),
                    "classification": classification,
                    "severity": _candidate_severity(reasons),
                    "step": _as_text(move.get("step")),
                    "learner_input": move.get("learner_input"),
                }
            )
    return sorted(
        items,
        key=lambda item: (
            _classification_sort_rank(_as_text(item["classification"])),
            0 if item["severity"] == "major_candidate" else 1,
            item["page_uid"],
            item["block_uid"],
            item["phrase"],
        ),
    )


def _classification_sort_rank(classification: str) -> int:
    order = {
        "bad_anchor_candidate": 0,
        "review_target_phrase": 1,
        "legitimate_phonics_target": 2,
        "legitimate_short_vocab_target": 3,
    }
    return order.get(classification, 4)


def _target_phrase_revision_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if item.get("classification") in {"bad_anchor_candidate", "review_target_phrase"}
    ]


def _items_by_classification(
    items: list[dict[str, Any]],
    classification: str,
) -> list[dict[str, Any]]:
    return [item for item in items if item.get("classification") == classification]


def audit_classroom_quality(
    *,
    smoke_report_path: Path,
    teaching_move_audit_path: Path,
) -> dict[str, Any]:
    resolved_smoke_path = _resolve_path(smoke_report_path)
    resolved_teaching_path = _resolve_path(teaching_move_audit_path)
    smoke_report = _load_json(resolved_smoke_path)
    teaching_report = _load_json(resolved_teaching_path)
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
    teaching_summary = teaching_report.get("summary") if isinstance(teaching_report.get("summary"), dict) else {}
    smoke_summary = smoke_report.get("summary") if isinstance(smoke_report.get("summary"), dict) else {}
    move_type_counts = teaching_summary.get("move_type_counts")
    if not isinstance(move_type_counts, dict):
        move_type_counts = Counter(_as_text(move.get("move_type")) for move in moves)

    page_meta = _page_metadata(smoke_report, turns)
    answer_turn_by_page, answer_turn_by_block = _answer_turn_counts(turns)
    page_aggregation = _aggregate_by_page(
        gentle_moves=gentle_moves,
        page_meta=page_meta,
        answer_turn_by_page=answer_turn_by_page,
    )
    block_aggregation = _aggregate_by_block(
        gentle_moves=gentle_moves,
        answer_turn_by_block=answer_turn_by_block,
    )
    top_redirect_pages = [
        {
            "rank": index,
            "page_uid": page["page_uid"],
            "page_label": page["page_label"],
            "gentle_redirect_count": page["gentle_redirect_count"],
            "redirect_rate": page["redirect_rate"],
            "why_flagged": _why_flagged(
                redirect_count=int(page["gentle_redirect_count"]),
                redirect_rate=float(page["redirect_rate"]),
            ),
        }
        for index, page in enumerate(page_aggregation[:10], start=1)
    ]
    target_phrase_items = _target_phrase_audit_items(gentle_moves)
    target_phrase_candidates = _target_phrase_revision_candidates(target_phrase_items)
    bad_anchor_candidates = _items_by_classification(
        target_phrase_items,
        "bad_anchor_candidate",
    )
    legitimate_short_vocab_targets = _items_by_classification(
        target_phrase_items,
        "legitimate_short_vocab_target",
    )
    legitimate_phonics_targets = _items_by_classification(
        target_phrase_items,
        "legitimate_phonics_target",
    )
    review_target_phrases = _items_by_classification(
        target_phrase_items,
        "review_target_phrase",
    )
    classification_counts = Counter(
        _as_text(item.get("classification")) for item in target_phrase_items
    )
    smoke_acceptance_passed = bool(smoke_summary.get("acceptance_passed"))
    teaching_move_audit_passed = bool(teaching_summary.get("audit_passed"))
    generated_at = datetime.now().isoformat(timespec="seconds")
    summary = {
        "smoke_file": str(resolved_smoke_path),
        "teaching_move_audit_file": str(resolved_teaching_path),
        "page_count": int(smoke_summary.get("page_count") or len({turn.get("page_uid") for turn in turns})),
        "turn_count": int(smoke_summary.get("turn_count") or len(turns)),
        "total_move_count": int(teaching_summary.get("move_count") or len(moves)),
        "gentle_redirect_count": int(move_type_counts.get("gentle_redirect", 0)),
        "vocab_answer_return_count": int(move_type_counts.get("vocab_answer_return", 0)),
        "single_block_guard_count": int(move_type_counts.get("single_block_guard", 0)),
        "smoke_acceptance_passed": smoke_acceptance_passed,
        "teaching_move_audit_passed": teaching_move_audit_passed,
        "audit_passed": smoke_acceptance_passed and teaching_move_audit_passed,
        "generated_at": generated_at,
        "target_phrase_audit_item_count": len(target_phrase_items),
        "target_phrase_revision_candidate_count": len(target_phrase_candidates),
        "bad_anchor_candidate_count": len(bad_anchor_candidates),
        "legitimate_short_vocab_target_count": len(legitimate_short_vocab_targets),
        "legitimate_phonics_target_count": len(legitimate_phonics_targets),
        "review_target_phrase_count": len(review_target_phrases),
        "target_phrase_classification_counts": dict(
            sorted(classification_counts.items())
        ),
        "classification": "classroom_quality_candidate",
        "candidate_policy": (
            "Bad/review target candidates are diagnostic only; legitimate short "
            "vocab and phonics targets are reported separately and do not change "
            "smoke acceptance."
        ),
    }
    return {
        "kind": REPORT_KIND,
        "generated_at": generated_at,
        "smoke_regression_set_id": smoke_report.get("regression_set_id"),
        "summary": summary,
        "smoke_summary": smoke_summary,
        "teaching_move_summary": teaching_summary,
        "gentle_redirect_by_page": page_aggregation,
        "gentle_redirect_by_block": block_aggregation,
        "top_redirect_pages": top_redirect_pages,
        "target_phrase_audit_items": target_phrase_items,
        "bad_anchor_candidates": bad_anchor_candidates,
        "legitimate_short_vocab_targets": legitimate_short_vocab_targets,
        "legitimate_phonics_targets": legitimate_phonics_targets,
        "review_target_phrases": review_target_phrases,
        "target_phrase_revision_candidates": target_phrase_candidates,
        "interpretation": [
            (
                "This report separates bad/review target anchors from legitimate "
                "short vocabulary and phonics targets. It does not indicate "
                "fallback, HTTP errors, state drift, or runtime regression."
            ),
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    smoke_status = "PASS" if summary["smoke_acceptance_passed"] else "FAIL"
    audit_status = "true" if summary["audit_passed"] else "false"
    lines = [
        "# Classroom Quality Audit",
        "",
        "## Summary",
        f"- Smoke acceptance: {smoke_status}",
        f"- Pages: {summary['page_count']}",
        f"- Turns: {summary['turn_count']}",
        f"- gentle_redirect: {summary['gentle_redirect_count']}",
        f"- vocab_answer_return: {summary['vocab_answer_return_count']}",
        f"- single_block_guard: {summary['single_block_guard_count']}",
        f"- bad_anchor_candidate: {summary['bad_anchor_candidate_count']}",
        f"- legitimate_short_vocab_target: {summary['legitimate_short_vocab_target_count']}",
        f"- legitimate_phonics_target: {summary['legitimate_phonics_target_count']}",
        f"- review_target_phrase: {summary['review_target_phrase_count']}",
        f"- Audit passed: {audit_status}",
        f"- Smoke file: `{summary['smoke_file']}`",
        f"- TeachingMove audit file: `{summary['teaching_move_audit_file']}`",
        "",
        "## Top Redirect Pages",
        "| Rank | Page | Label | Redirects | Rate | Note |",
        "|---|---|---|---:|---:|---|",
    ]
    for page in report["top_redirect_pages"][:5]:
        lines.append(
            "| "
            f"{page['rank']} | `{page['page_uid']}` | {page['page_label']} | "
            f"{page['gentle_redirect_count']} | {page['redirect_rate']:.2f} | "
            f"{page['why_flagged']} |"
        )
    if not report["top_redirect_pages"]:
        lines.append("| - | - | - | 0 | 0.00 | none |")

    lines.extend(
        [
            "",
            "## Bad / Review Target Phrase Candidates",
            "| Page | Block | Phrase | Classification | Reason | Severity |",
            "|---|---|---|---|---|---|",
        ]
    )
    candidates = report["target_phrase_revision_candidates"]
    if candidates:
        for item in candidates[:20]:
            lines.append(
                "| "
                f"`{item['page_uid']}` | `{item['block_uid']}` | "
                f"{item['phrase']} | {item['classification']} | "
                f"{item['reason']} | {item['severity']} |"
            )
    else:
        lines.append("| - | - | none | - | - | info |")

    legitimate_items = [
        *report["legitimate_phonics_targets"],
        *report["legitimate_short_vocab_targets"],
    ]
    lines.extend(
        [
            "",
            "## Legitimate Short Targets",
            "| Page | Block | Phrase | Classification | Reason |",
            "|---|---|---|---|---|",
        ]
    )
    if legitimate_items:
        for item in legitimate_items[:20]:
            lines.append(
                "| "
                f"`{item['page_uid']}` | `{item['block_uid']}` | "
                f"{item['phrase']} | {item['classification']} | {item['reason']} |"
            )
    else:
        lines.append("| - | - | none | - | - |")

    lines.extend(["", "## Interpretation"])
    for note in report["interpretation"]:
        lines.append(f"- {note}")
    lines.append(
        "- Bad/review candidates are S3 classroom experience inputs, not smoke failures."
    )
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    resolved_out_dir = _resolve_path(out_dir)
    resolved_out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    json_path = resolved_out_dir / f"classroom_quality_audit_{stamp}.json"
    md_path = resolved_out_dir / f"classroom_quality_audit_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke-report",
        type=Path,
        default=None,
        help="Path to lesson_smoke_matrix_*.json. Defaults to the newest report.",
    )
    parser.add_argument(
        "--teaching-move-audit",
        type=Path,
        default=None,
        help="Path to teaching_move_audit_*.json. Defaults to the newest report.",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    smoke_report_path = args.smoke_report or latest_smoke_report(args.out_dir)
    teaching_move_audit_path = args.teaching_move_audit or latest_teaching_move_audit(
        args.out_dir
    )
    report = audit_classroom_quality(
        smoke_report_path=smoke_report_path,
        teaching_move_audit_path=teaching_move_audit_path,
    )
    json_path, md_path = write_report(report, args.out_dir)
    print(
        json.dumps(
            {
                "json_path": str(json_path),
                "markdown_path": str(md_path),
                "summary": report["summary"],
                "top_redirect_pages": report["top_redirect_pages"][:5],
                "target_phrase_revision_candidate_count": len(
                    report["target_phrase_revision_candidates"]
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
