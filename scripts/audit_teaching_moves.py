#!/usr/bin/env python3
"""Audit TeachingMove planner records from a lesson smoke run."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


REPORT_KIND = "lesson_teaching_move_audit"
DEFAULT_ARTIFACT_DIR = Path("temp/lesson-smoke-artifacts")
DEFAULT_RUNTIME_LOG_DIR = Path("backend/LightRAG/temp")

KNOWN_MOVE_TYPES = {
    "answer_briefly_then_return",
    "confirm_and_advance",
    "convert_task_echo_to_answer",
    "give_one_step_hint",
    "light_recast",
    "lower_pressure_reinvite",
    "open_with_probe",
    "prompt_missing_piece",
    "redirect_to_active_task",
    "gentle_redirect",
    "single_block_guard",
    "vocab_answer_return",
}

BASE_REQUIRED_FIELDS = (
    "schema_version",
    "detected_signal",
    "move",
    "teaching_action",
    "rationale",
    "evidence_fields_used",
    "expected_next_learner_action",
)
VOCAB_PAYLOAD_REQUIRED_FIELDS = (
    "query_term",
    "retrieval_mode",
    "return_anchor",
    "active_prompt",
    "return_to_current_task",
    "retrieval_evidence_count",
    "support_evidence_count",
)
GENTLE_REDIRECT_PAYLOAD_REQUIRED_FIELDS = (
    "learner_input",
    "interpreted_intent",
    "current_target",
    "target_phrase",
    "active_prompt",
    "return_anchor",
    "next_action",
    "correction_kind",
    "route",
    "turn_label",
    "preserve_page_uid",
    "preserve_block_uid",
)
GENTLE_REDIRECT_TEACHING_ACTION_REQUIRED_FIELDS = (
    "target_role",
    "expected_student_action",
    "action_source",
)
KNOWN_TARGET_ROLES = {"question", "answer", "phrase", "phonics", "story"}
KNOWN_EXPECTED_STUDENT_ACTIONS = {"read", "answer", "repeat", "choose", "role_play"}
KNOWN_ACTION_SOURCES = {
    "block_core_pattern",
    "active_prompt",
    "return_anchor",
    "answer_scope",
    "phonics_context",
    "story_context",
    "fallback_conservative",
}
QUESTION_PREFIXES = (
    "what ",
    "what's ",
    "what is ",
    "where ",
    "when ",
    "who ",
    "whose ",
    "which ",
    "why ",
    "how ",
    "do ",
    "does ",
    "did ",
    "can ",
    "is ",
    "are ",
)
DECLARATIVE_ANSWER_PREFIXES = (
    "it's ",
    "it is ",
    "i'd ",
    "i would ",
    "i'm ",
    "i am ",
    "i get ",
    "i often ",
    "i usually ",
    "zoom would ",
    "he ",
    "she ",
    "they ",
    "there ",
    "look ",
    "yes, ",
    "no, ",
)

TEACHING_MOVE_RE = re.compile(
    r"Lesson teaching move planned route=(?P<planned_route>\S+) payload=(?P<payload>\{.*\})"
)
TURN_AUDIT_RE = re.compile(
    r"Lesson turn audit path=(?P<route>\S+) turn_label=(?P<turn_label>\S+) "
    r"page_uid=(?P<page_uid>\S+) block_uid=(?P<block_uid>\S+).*?"
    r"retrieval_evidence=(?P<retrieval_evidence>\d+) "
    r"support_evidence=(?P<support_evidence>\d+)"
)
TEACHER_RESPONSE_AUDIT_RE = re.compile(
    r"Lesson teacher response audit turn_label=(?P<turn_label>\S+).*?"
    r"(?:\sroute=(?P<route>\S+))"
)
VOCAB_MEANING_RE = re.compile(
    r"\bwhat\s+does\s+(.+?)\s+mean\??\s*$|是什么意思|什么意思|怎么说",
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


def latest_smoke_report(artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path:
    reports = sorted(
        _resolve_path(artifact_dir).glob("lesson_smoke_matrix_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        raise FileNotFoundError(f"No lesson_smoke_matrix_*.json found in {artifact_dir}")
    return reports[0]


def latest_runtime_log(log_dir: Path = DEFAULT_RUNTIME_LOG_DIR) -> Path:
    reports = sorted(
        _resolve_path(log_dir).glob("smoke_lesson_regression20_*.log"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        raise FileNotFoundError(f"No smoke_lesson_regression20_*.log found in {log_dir}")
    return reports[0]


def _as_text(value: Any) -> str:
    return str(value or "")


def _clean_phrase(value: Any) -> str:
    return " ".join(_as_text(value).strip().split()).strip("“”\"'`，,、；;:：").strip()


def _normalized_phrase(value: Any) -> str:
    return _clean_phrase(value).strip("。！？!?.").casefold()


def _looks_like_declarative_answer(value: Any) -> bool:
    return _normalized_phrase(value).startswith(DECLARATIVE_ANSWER_PREFIXES)


def _looks_like_question(value: Any) -> bool:
    cleaned = _clean_phrase(value)
    normalized = _normalized_phrase(cleaned)
    if not cleaned:
        return False
    if _looks_like_declarative_answer(cleaned):
        return False
    return cleaned.endswith("?") or normalized.startswith(QUESTION_PREFIXES)


def _shorten(text: str, *, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = _as_text(item.get(key)) or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def _is_vocab_meaning_query(value: Any) -> bool:
    return bool(VOCAB_MEANING_RE.search(_as_text(value).strip()))


def _load_smoke_turns(smoke_report_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolved = _resolve_path(smoke_report_path)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    turns = payload.get("turns") if isinstance(payload, dict) else None
    if not isinstance(turns, list):
        raise ValueError(f"{resolved} does not contain a turn list")
    return payload, [turn for turn in turns if isinstance(turn, dict)]


def _runtime_audit_from_line(line: str) -> dict[str, Any] | None:
    turn_match = TURN_AUDIT_RE.search(line)
    if turn_match:
        payload = turn_match.groupdict()
        payload["retrieval_evidence"] = int(payload["retrieval_evidence"])
        payload["support_evidence"] = int(payload["support_evidence"])
        return payload

    response_match = TEACHER_RESPONSE_AUDIT_RE.search(line)
    if response_match:
        return {
            key: value
            for key, value in response_match.groupdict().items()
            if value is not None
        }
    return None


def parse_runtime_moves(runtime_log_path: Path) -> list[dict[str, Any]]:
    lines = _resolve_path(runtime_log_path).read_text(encoding="utf-8").splitlines()
    records: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        match = TEACHING_MOVE_RE.search(line)
        if not match:
            continue
        payload_text = match.group("payload")
        parse_error = ""
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            payload = {}
            parse_error = str(exc)

        runtime_audit = None
        for follow_line in lines[index : index + 8]:
            runtime_audit = _runtime_audit_from_line(follow_line)
            if runtime_audit is not None:
                break

        records.append(
            {
                "line_no": index,
                "planned_route": match.group("planned_route"),
                "payload": payload,
                "payload_parse_error": parse_error,
                "move_type": _as_text(payload.get("move")),
                "runtime_route": _as_text(runtime_audit.get("route") if runtime_audit else ""),
                "runtime_turn_label": _as_text(runtime_audit.get("turn_label") if runtime_audit else ""),
                "runtime_page_uid": _as_text(runtime_audit.get("page_uid") if runtime_audit else ""),
                "runtime_block_uid": _as_text(runtime_audit.get("block_uid") if runtime_audit else ""),
                "runtime_audit": runtime_audit or {},
            }
        )
    return records


def _turn_matches_move(
    turn: dict[str, Any],
    record: dict[str, Any],
) -> bool:
    move_type = record["move_type"]
    if move_type == "single_block_guard":
        return (
            turn.get("route") == "single_module_navigation_guard"
            and turn.get("turn_label") == "navigation"
        )
    if move_type == "vocab_answer_return":
        payload_fields = record.get("payload", {}).get("payload_fields")
        query_term = ""
        if isinstance(payload_fields, dict):
            query_term = _as_text(payload_fields.get("query_term")).casefold()
        learner_input = _as_text(turn.get("learner_input")).casefold()
        return (
            turn.get("route") == "rag_plus_llm"
            and turn.get("turn_label") == "ask_knowledge"
            and _is_vocab_meaning_query(turn.get("learner_input"))
            and (not query_term or query_term in learner_input)
        )
    if move_type == "gentle_redirect":
        payload_fields = record.get("payload", {}).get("payload_fields")
        if not isinstance(payload_fields, dict):
            return False
        route = _as_text(payload_fields.get("route"))
        turn_label = _as_text(payload_fields.get("turn_label"))
        preserve_page_uid = _as_text(payload_fields.get("preserve_page_uid"))
        preserve_block_uid = _as_text(payload_fields.get("preserve_block_uid"))
        learner_input = _as_text(payload_fields.get("learner_input"))
        if route and turn.get("route") != route:
            return False
        if turn_label and turn.get("turn_label") != turn_label:
            return False
        if preserve_page_uid and turn.get("page_uid") != preserve_page_uid:
            return False
        if preserve_block_uid and turn.get("state_block_uid") != preserve_block_uid:
            return False
        return _as_text(turn.get("learner_input")) == learner_input
    return False


def align_moves_to_smoke_turns(
    *,
    records: list[dict[str, Any]],
    turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    used_turn_indexes: set[int] = set()
    search_start = 0
    aligned: list[dict[str, Any]] = []
    for record in records:
        match_index: int | None = None
        for index in range(search_start, len(turns)):
            if index in used_turn_indexes:
                continue
            if _turn_matches_move(turns[index], record):
                match_index = index
                break
        if match_index is None:
            for index, turn in enumerate(turns):
                if index in used_turn_indexes:
                    continue
                if _turn_matches_move(turn, record):
                    match_index = index
                    break
        if match_index is not None:
            used_turn_indexes.add(match_index)
            search_start = match_index + 1
            record = {
                **record,
                "smoke_turn_index": match_index,
                "page_uid": _as_text(turns[match_index].get("page_uid")),
                "step": _as_text(turns[match_index].get("step")),
                "learner_input": turns[match_index].get("learner_input"),
                "route": _as_text(turns[match_index].get("route")),
                "turn_label": _as_text(turns[match_index].get("turn_label")),
                "teacherresponsesource": turns[match_index].get("teacherresponsesource"),
                "repair_reason": turns[match_index].get("repair_reason"),
            }
        else:
            record = {
                **record,
                "smoke_turn_index": None,
                "page_uid": "",
                "step": "",
                "learner_input": None,
                "route": record.get("runtime_route") or record.get("planned_route") or "",
                "turn_label": record.get("runtime_turn_label") or "",
            }
        aligned.append(record)
    return aligned


def missing_payload_fields(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for record in records:
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        missing_fields = [
            field
            for field in BASE_REQUIRED_FIELDS
            if field not in payload or payload.get(field) in ("", None, [])
        ]
        if record.get("move_type") == "vocab_answer_return":
            payload_fields = payload.get("payload_fields")
            if not isinstance(payload_fields, dict):
                missing_fields.append("payload_fields")
            else:
                for field in VOCAB_PAYLOAD_REQUIRED_FIELDS:
                    if field not in payload_fields or payload_fields.get(field) in ("", None):
                        missing_fields.append(f"payload_fields.{field}")
        if record.get("move_type") == "gentle_redirect":
            payload_fields = payload.get("payload_fields")
            if not isinstance(payload_fields, dict):
                missing_fields.append("payload_fields")
            else:
                for field in GENTLE_REDIRECT_PAYLOAD_REQUIRED_FIELDS:
                    if field not in payload_fields or payload_fields.get(field) in ("", None):
                        missing_fields.append(f"payload_fields.{field}")
        if missing_fields:
            missing.append(
                {
                    "line_no": record.get("line_no"),
                    "move_type": record.get("move_type") or "unknown",
                    "page_uid": record.get("page_uid") or "unmatched",
                    "missing_fields": missing_fields,
                }
            )
    return missing


def teaching_action_field_issues(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    missing: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    semantic_warnings: list[dict[str, Any]] = []
    for record in records:
        if record.get("move_type") != "gentle_redirect":
            continue
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        payload_fields = payload.get("payload_fields")
        if not isinstance(payload_fields, dict):
            missing.append(
                _teaching_action_issue(
                    record=record,
                    issues=["payload_fields"],
                )
            )
            continue
        missing_fields = [
            field
            for field in GENTLE_REDIRECT_TEACHING_ACTION_REQUIRED_FIELDS
            if field not in payload_fields or payload_fields.get(field) in ("", None)
        ]
        target_role = _as_text(payload_fields.get("target_role"))
        expected_action = _as_text(payload_fields.get("expected_student_action"))
        action_source = _as_text(payload_fields.get("action_source"))
        if target_role and target_role not in KNOWN_TARGET_ROLES:
            missing_fields.append("target_role:unknown")
        if expected_action and expected_action not in KNOWN_EXPECTED_STUDENT_ACTIONS:
            missing_fields.append("expected_student_action:unknown")
        if action_source and action_source not in KNOWN_ACTION_SOURCES:
            missing_fields.append("action_source:unknown")
        if missing_fields:
            missing.append(_teaching_action_issue(record=record, issues=missing_fields))

        warning_fields: list[str] = []
        if (
            target_role == "question"
            and expected_action == "answer"
            and _question_likely_needs_answer_frame(
                payload_fields.get("question_target")
            )
            and not _as_text(payload_fields.get("answer_target"))
            and not _as_text(payload_fields.get("answer_frame"))
        ):
            warning_fields.append("question_answer_without_answer_target_or_frame")
        if target_role == "story" and not _as_text(
            payload_fields.get("question_target")
        ) and not _as_text(payload_fields.get("answer_frame")):
            warning_fields.append("story_without_question_target_or_answer_frame")
        if warning_fields:
            warnings.append(_teaching_action_issue(record=record, issues=warning_fields))

        semantic_fields = _teaching_action_semantic_issues(payload_fields)
        if semantic_fields:
            semantic_warnings.append(
                _teaching_action_issue(record=record, issues=semantic_fields)
            )
    return missing, warnings, semantic_warnings


def _teaching_action_semantic_issues(payload_fields: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    target_role = _as_text(payload_fields.get("target_role"))
    expected_action = _as_text(payload_fields.get("expected_student_action"))
    action_source = _as_text(payload_fields.get("action_source"))
    question_target = _clean_phrase(payload_fields.get("question_target"))
    answer_target = _clean_phrase(payload_fields.get("answer_target"))
    answer_frame = _clean_phrase(payload_fields.get("answer_frame"))
    target_phrase = _clean_phrase(payload_fields.get("target_phrase"))
    active_prompt = _clean_phrase(payload_fields.get("active_prompt"))
    block_uid = _as_text(payload_fields.get("preserve_block_uid"))

    if target_role == "question":
        if not question_target:
            issues.append("question_role_without_question_target")
        elif not _looks_like_question(question_target):
            if _looks_like_declarative_answer(question_target):
                issues.append("question_role_uses_declarative_sentence")
            else:
                issues.append("question_role_uses_non_question_target")
        if (
            expected_action == "answer"
            and _question_likely_needs_answer_frame(question_target)
            and not answer_target
            and not answer_frame
        ):
            issues.append("question_answer_without_answer_target_or_frame")

    if target_role == "answer":
        if not answer_target:
            issues.append("answer_role_without_answer_target")
        elif _looks_like_question(answer_target):
            issues.append("answer_role_uses_question_target")
        if expected_action not in {"repeat", "answer"}:
            issues.append("answer_role_unexpected_student_action")

    if (
        block_uid == "TB-G6S2U1-P4-D2"
        and _normalized_phrase(active_prompt) == "how tall is it"
    ):
        if _normalized_phrase(question_target) == "how tall are you":
            issues.append("height_object_question_overridden_by_personal_question")
        if target_role == "question" and answer_frame != "It's ... metres tall.":
            issues.append("height_object_question_missing_answer_frame")
        if _normalized_phrase(target_phrase) == "how tall are you":
            issues.append("height_object_target_phrase_overridden_by_personal_question")

    if target_role == "phonics":
        if question_target:
            issues.append("phonics_role_has_question_target")
        bad_phonics_fragments = (target_phrase, answer_target)
        if any("cl' as in" in value.casefold() for value in bad_phonics_fragments):
            issues.append("phonics_role_uses_fragment_target")
        if not answer_target:
            issues.append("phonics_role_without_answer_target")

    if target_role == "story":
        if not question_target:
            issues.append("story_role_without_question_target")
        if not answer_frame:
            issues.append("story_role_without_answer_frame")
        if expected_action != "answer":
            issues.append("story_role_unexpected_student_action")
        if action_source != "story_context":
            issues.append("story_role_unexpected_action_source")

    return issues


def _question_likely_needs_answer_frame(value: Any) -> bool:
    normalized = _normalized_phrase(value)
    if not normalized:
        return False
    return normalized.startswith(
        (
            "what ",
            "what's ",
            "what is ",
            "what did ",
            "what would ",
            "where ",
            "when ",
            "how tall ",
        )
    )


def _teaching_action_issue(
    *,
    record: dict[str, Any],
    issues: list[str],
) -> dict[str, Any]:
    return {
        "line_no": record.get("line_no"),
        "move_type": record.get("move_type") or "unknown",
        "page_uid": record.get("page_uid") or "unmatched",
        "step": record.get("step") or "",
        "learner_input": record.get("learner_input"),
        "issues": issues,
    }


def _payload_field_counts(
    records: list[dict[str, Any]],
    field: str,
) -> dict[str, int]:
    items: list[dict[str, Any]] = []
    for record in records:
        if record.get("move_type") != "gentle_redirect":
            continue
        payload_fields = record.get("payload", {}).get("payload_fields")
        if not isinstance(payload_fields, dict):
            continue
        items.append({field: _as_text(payload_fields.get(field)) or "unknown"})
    return _count_by(items, field)


def route_turn_label_mismatches(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    for record in records:
        move_type = record.get("move_type")
        route = record.get("route")
        turn_label = record.get("turn_label")
        runtime_route = record.get("runtime_route")
        runtime_turn_label = record.get("runtime_turn_label")
        reasons: list[str] = []

        if record.get("smoke_turn_index") is None:
            reasons.append("no matching smoke turn")
        if move_type == "single_block_guard":
            if route != "single_module_navigation_guard" or turn_label != "navigation":
                reasons.append(
                    "single_block_guard must align to route=single_module_navigation_guard and turn_label=navigation"
                )
            if runtime_route and runtime_route != "single_module_navigation_guard":
                reasons.append("runtime audit route mismatch")
            if runtime_turn_label and runtime_turn_label != "navigation":
                reasons.append("runtime audit turn_label mismatch")
        elif move_type == "vocab_answer_return":
            if route != "rag_plus_llm" or turn_label != "ask_knowledge":
                reasons.append(
                    "vocab_answer_return must align to route=rag_plus_llm and turn_label=ask_knowledge"
                )
            if not _is_vocab_meaning_query(record.get("learner_input")):
                reasons.append("vocab_answer_return learner input is not a vocabulary meaning query")
            if runtime_route and runtime_route != "rag_plus_llm":
                reasons.append("runtime audit route mismatch")
            if runtime_turn_label and runtime_turn_label != "ask_knowledge":
                reasons.append("runtime audit turn_label mismatch")
        elif move_type == "gentle_redirect":
            payload_fields = record.get("payload", {}).get("payload_fields")
            if not isinstance(payload_fields, dict):
                reasons.append("gentle_redirect payload_fields missing")
            else:
                payload_route = _as_text(payload_fields.get("route"))
                payload_turn_label = _as_text(payload_fields.get("turn_label"))
                if payload_route and route != payload_route:
                    reasons.append("gentle_redirect smoke route does not match payload route")
                if payload_turn_label and turn_label != payload_turn_label:
                    reasons.append(
                        "gentle_redirect smoke turn_label does not match payload turn_label"
                    )
                if payload_turn_label not in {"answer_question", "ask_help", "social"}:
                    reasons.append("gentle_redirect turn_label is not a pullback/help scene")
                if not _as_text(payload_fields.get("return_anchor")):
                    reasons.append("gentle_redirect return_anchor missing")
                if not _as_text(payload_fields.get("target_phrase")):
                    reasons.append("gentle_redirect target_phrase missing")
        elif move_type not in KNOWN_MOVE_TYPES:
            reasons.append("unknown move_type")

        if reasons:
            mismatches.append(
                {
                    "line_no": record.get("line_no"),
                    "move_type": move_type or "unknown",
                    "page_uid": record.get("page_uid") or "unmatched",
                    "step": record.get("step") or "",
                    "learner_input": record.get("learner_input"),
                    "route": route,
                    "turn_label": turn_label,
                    "runtime_route": runtime_route,
                    "runtime_turn_label": runtime_turn_label,
                    "reasons": reasons,
                }
            )
    return mismatches


def _examples_by_move_type(
    records: list[dict[str, Any]],
    *,
    max_examples_per_move: int,
) -> dict[str, list[dict[str, Any]]]:
    examples: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        move_type = record.get("move_type") or "unknown"
        bucket = examples.setdefault(move_type, [])
        if len(bucket) >= max_examples_per_move:
            continue
        payload_fields = record.get("payload", {}).get("payload_fields")
        bucket.append(
            {
                "line_no": record.get("line_no"),
                "page_uid": record.get("page_uid") or "unmatched",
                "step": record.get("step") or "",
                "learner_input": record.get("learner_input"),
                "route": record.get("route"),
                "turn_label": record.get("turn_label"),
                "planned_route": record.get("planned_route"),
                "runtime_route": record.get("runtime_route"),
                "runtime_turn_label": record.get("runtime_turn_label"),
                "payload_fields": payload_fields if isinstance(payload_fields, dict) else {},
                "evidence_fields_used": record.get("payload", {}).get("evidence_fields_used", []),
            }
        )
    return dict(sorted(examples.items()))


def audit_teaching_moves(
    *,
    smoke_report_path: Path,
    runtime_log_path: Path,
    max_examples_per_move: int = 5,
) -> dict[str, Any]:
    smoke_report, turns = _load_smoke_turns(smoke_report_path)
    records = parse_runtime_moves(runtime_log_path)
    aligned_records = align_moves_to_smoke_turns(records=records, turns=turns)
    missing_fields = missing_payload_fields(aligned_records)
    (
        teaching_action_missing,
        teaching_action_warnings,
        teaching_action_semantic_warnings,
    ) = teaching_action_field_issues(aligned_records)
    mismatches = route_turn_label_mismatches(aligned_records)
    unknown_move_types = sorted(
        {
            _as_text(record.get("move_type")) or "unknown"
            for record in aligned_records
            if (_as_text(record.get("move_type")) or "unknown") not in KNOWN_MOVE_TYPES
        }
    )
    unmatched_count = sum(1 for record in aligned_records if record.get("smoke_turn_index") is None)

    summary = {
        "smoke_report_path": str(_resolve_path(smoke_report_path)),
        "runtime_log_path": str(_resolve_path(runtime_log_path)),
        "move_count": len(aligned_records),
        "move_type_counts": _count_by(aligned_records, "move_type"),
        "page_counts": _count_by(aligned_records, "page_uid"),
        "route_counts": _count_by(aligned_records, "route"),
        "turn_label_counts": _count_by(aligned_records, "turn_label"),
        "missing_payload_field_count": len(missing_fields),
        "teaching_action_field_missing_count": len(teaching_action_missing),
        "teaching_action_field_warning_count": len(teaching_action_warnings),
        "teaching_action_semantic_warning_count": len(
            teaching_action_semantic_warnings
        ),
        "teaching_action_type_counts": _payload_field_counts(
            aligned_records,
            "target_role",
        ),
        "expected_student_action_counts": _payload_field_counts(
            aligned_records,
            "expected_student_action",
        ),
        "unknown_move_type_count": len(unknown_move_types),
        "route_turn_label_mismatch_count": len(mismatches),
        "unmatched_move_count": unmatched_count,
        "audit_passed": (
            not missing_fields
            and not teaching_action_missing
            and not teaching_action_semantic_warnings
            and not unknown_move_types
            and not mismatches
            and unmatched_count == 0
        ),
    }
    return {
        "kind": REPORT_KIND,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "smoke_regression_set_id": smoke_report.get("regression_set_id"),
        "smoke_summary": smoke_report.get("summary", {}),
        "summary": summary,
        "missing_payload_fields": missing_fields,
        "teaching_action_field_missing": teaching_action_missing,
        "teaching_action_field_warnings": teaching_action_warnings,
        "teaching_action_semantic_warnings": teaching_action_semantic_warnings,
        "unknown_move_types": unknown_move_types,
        "route_turn_label_mismatches": mismatches,
        "examples_by_move_type": _examples_by_move_type(
            aligned_records,
            max_examples_per_move=max_examples_per_move,
        ),
        "moves": [
            {
                "line_no": record.get("line_no"),
                "move_type": record.get("move_type") or "unknown",
                "page_uid": record.get("page_uid") or "unmatched",
                "step": record.get("step") or "",
                "learner_input": record.get("learner_input"),
                "route": record.get("route"),
                "turn_label": record.get("turn_label"),
                "planned_route": record.get("planned_route"),
                "runtime_route": record.get("runtime_route"),
                "runtime_turn_label": record.get("runtime_turn_label"),
                "payload": record.get("payload"),
            }
            for record in aligned_records
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Lesson Teaching Move Audit",
        "",
        f"Generated: {report['generated_at']}",
        f"Smoke report: `{summary['smoke_report_path']}`",
        f"Runtime log: `{summary['runtime_log_path']}`",
        f"Regression set: `{report.get('smoke_regression_set_id')}`",
        "",
        "## Summary",
        "",
    ]
    for key in (
        "audit_passed",
        "move_count",
        "move_type_counts",
        "page_counts",
        "route_counts",
        "turn_label_counts",
        "missing_payload_field_count",
        "teaching_action_field_missing_count",
        "teaching_action_field_warning_count",
        "teaching_action_semantic_warning_count",
        "teaching_action_type_counts",
        "expected_student_action_counts",
        "unknown_move_type_count",
        "route_turn_label_mismatch_count",
        "unmatched_move_count",
    ):
        lines.append(f"- {key}: `{summary[key]}`")

    lines.extend(["", "## Missing Payload Fields", ""])
    if not report["missing_payload_fields"]:
        lines.append("- none")
    else:
        for item in report["missing_payload_fields"]:
            lines.append(
                "- "
                f"line={item['line_no']} move={item['move_type']} "
                f"page={item['page_uid']} missing={item['missing_fields']}"
            )

    lines.extend(["", "## Teaching Action Fields", ""])
    if not report["teaching_action_field_missing"]:
        lines.append("- missing: none")
    else:
        for item in report["teaching_action_field_missing"]:
            lines.append(
                "- "
                f"missing line={item['line_no']} page={item['page_uid']} "
                f"step={item['step']} input={item['learner_input']!r} "
                f"issues={item['issues']}"
            )
    if not report["teaching_action_field_warnings"]:
        lines.append("- warnings: none")
    else:
        for item in report["teaching_action_field_warnings"]:
            lines.append(
                "- "
                f"warning line={item['line_no']} page={item['page_uid']} "
                f"step={item['step']} input={item['learner_input']!r} "
                f"issues={item['issues']}"
            )
    if not report["teaching_action_semantic_warnings"]:
        lines.append("- semantic warnings: none")
    else:
        for item in report["teaching_action_semantic_warnings"]:
            lines.append(
                "- "
                f"semantic-warning line={item['line_no']} page={item['page_uid']} "
                f"step={item['step']} input={item['learner_input']!r} "
                f"issues={item['issues']}"
            )

    lines.extend(["", "## Route / Turn Label Mismatches", ""])
    if not report["route_turn_label_mismatches"]:
        lines.append("- none")
    else:
        for item in report["route_turn_label_mismatches"]:
            lines.append(
                "- "
                f"line={item['line_no']} move={item['move_type']} "
                f"page={item['page_uid']} step={item['step']} "
                f"input={item['learner_input']!r} reasons={item['reasons']}"
            )

    lines.extend(["", "## Examples", ""])
    examples = report["examples_by_move_type"]
    if not examples:
        lines.append("- none")
    else:
        for move_type, items in examples.items():
            lines.append(f"### `{move_type}`")
            for item in items:
                lines.append(
                    "- "
                    f"`{item['page_uid']}` {item['step']} "
                    f"input={item['learner_input']!r} "
                    f"route={item['route']} turn_label={item['turn_label']} "
                    f"planned={item['planned_route']} fields={item['payload_fields']}"
                )
            lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    resolved_out_dir = _resolve_path(out_dir)
    resolved_out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    json_path = resolved_out_dir / f"teaching_move_audit_{stamp}.json"
    md_path = resolved_out_dir / f"teaching_move_audit_{stamp}.md"
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
        "--runtime-log",
        type=Path,
        default=None,
        help="Path to smoke_lesson_regression20_*.log. Defaults to the newest runtime log.",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--max-examples-per-move", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    smoke_report_path = args.smoke_report or latest_smoke_report(args.out_dir)
    runtime_log_path = args.runtime_log or latest_runtime_log()
    report = audit_teaching_moves(
        smoke_report_path=smoke_report_path,
        runtime_log_path=runtime_log_path,
        max_examples_per_move=args.max_examples_per_move,
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
    return 0 if report["summary"]["audit_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
