"""Per-turn LLM byte and token metering for lesson runtime diagnostics."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


TOKEN_COUNT_SOURCE_BYTE_ESTIMATE = "byte_estimate"
TOKEN_COUNT_SOURCE_PROVIDER_USAGE = "provider_usage"


@dataclass
class LessonLLMCallMeter:
    call_id: str
    llm_provider: str
    llm_model: str
    prompt_bytes: int
    prompt_token_estimate: int
    completion_bytes: int
    completion_token_estimate: int
    total_token_estimate: int
    token_count_source: str
    route: str = ""
    turn_label: str = ""
    page_uid: str = ""
    block_uid: str = ""
    rag_context_bytes: int = 0
    history_bytes: int = 0
    system_prompt_bytes: int = 0
    lesson_context_bytes: int = 0
    persona_prompt_bytes: int = 0
    persona_capsule_bytes: int = 0
    textbook_block_bytes: int = 0
    page_overview_bytes: int = 0
    runtime_state_bytes: int = 0
    runtime_state_minimal_view_bytes: int = 0
    runtime_state_legacy_frame_bytes: int = 0
    runtime_state_savings_candidate_bytes: int = 0
    minimal_runtime_state_prompt_enabled: bool = False
    teaching_move_bytes: int = 0
    policy_instruction_bytes: int = 0
    quality_revision_prompt_bytes: int = 0
    learner_input_bytes: int = 0
    prompt_frame_overhead_bytes: int = 0
    json_serialization_overhead_bytes: int = 0
    output_schema_bytes: int = 0
    planner_prompt_overhead_bytes: int = 0
    responder_prompt_overhead_bytes: int = 0
    revision_notes_bytes: int = 0
    unclassified_context_bytes: int = 0
    other_bytes: int = 0
    unknown_context_bytes: int = 0
    audit_tag: str = ""
    mode: str = "complete"
    status: str = "success"

    def to_report_payload(
        self,
        *,
        route: str = "",
        turn_label: str = "",
        page_uid: str = "",
        block_uid: str = "",
        llm_provider: str = "",
        llm_model: str = "",
    ) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "audit_tag": self.audit_tag,
            "mode": self.mode,
            "status": self.status,
            "prompt_bytes": self.prompt_bytes,
            "prompt_token_estimate": self.prompt_token_estimate,
            "completion_bytes": self.completion_bytes,
            "completion_token_estimate": self.completion_token_estimate,
            "total_token_estimate": self.total_token_estimate,
            "token_count_source": self.token_count_source,
            "route": self.route or route,
            "turn_label": self.turn_label or turn_label,
            "page_uid": self.page_uid or page_uid,
            "block_uid": self.block_uid or block_uid,
            "llm_provider": self.llm_provider or llm_provider or "unknown",
            "llm_model": self.llm_model or llm_model or "unknown",
            "rag_context_bytes": self.rag_context_bytes,
            "history_bytes": self.history_bytes,
            "system_prompt_bytes": self.system_prompt_bytes,
            "lesson_context_bytes": self.lesson_context_bytes,
            "persona_prompt_bytes": self.persona_prompt_bytes,
            "persona_capsule_bytes": self.persona_capsule_bytes,
            "textbook_block_bytes": self.textbook_block_bytes,
            "page_overview_bytes": self.page_overview_bytes,
            "runtime_state_bytes": self.runtime_state_bytes,
            "runtime_state_minimal_view_bytes": (
                self.runtime_state_minimal_view_bytes
            ),
            "runtime_state_legacy_frame_bytes": self.runtime_state_legacy_frame_bytes,
            "runtime_state_savings_candidate_bytes": (
                self.runtime_state_savings_candidate_bytes
            ),
            "minimal_runtime_state_prompt_enabled": (
                self.minimal_runtime_state_prompt_enabled
            ),
            "teaching_move_bytes": self.teaching_move_bytes,
            "policy_instruction_bytes": self.policy_instruction_bytes,
            "quality_revision_prompt_bytes": self.quality_revision_prompt_bytes,
            "learner_input_bytes": self.learner_input_bytes,
            "prompt_frame_overhead_bytes": self.prompt_frame_overhead_bytes,
            "json_serialization_overhead_bytes": self.json_serialization_overhead_bytes,
            "output_schema_bytes": self.output_schema_bytes,
            "planner_prompt_overhead_bytes": self.planner_prompt_overhead_bytes,
            "responder_prompt_overhead_bytes": self.responder_prompt_overhead_bytes,
            "revision_notes_bytes": self.revision_notes_bytes,
            "unclassified_context_bytes": self.unclassified_context_bytes,
            "other_bytes": self.other_bytes,
            "unknown_context_bytes": self.unknown_context_bytes,
        }


@dataclass
class LessonLLMMeteringContext:
    route: str = ""
    turn_label: str = ""
    page_uid: str = ""
    block_uid: str = ""
    llm_provider: str = "unknown"
    llm_model: str = "unknown"
    calls: list[LessonLLMCallMeter] = field(default_factory=list)


_ACTIVE_METERING_CONTEXT: ContextVar[LessonLLMMeteringContext | None] = ContextVar(
    "lesson_llm_metering_context",
    default=None,
)
_PROMPT_BREAKDOWN_OVERRIDES: ContextVar[dict[str, Any] | None] = ContextVar(
    "lesson_llm_prompt_breakdown_overrides",
    default=None,
)


@contextmanager
def collect_lesson_llm_metering(
    *,
    route: str = "",
    turn_label: str = "",
    page_uid: str = "",
    block_uid: str = "",
    llm_provider: str = "unknown",
    llm_model: str = "unknown",
) -> Iterator[LessonLLMMeteringContext]:
    context = LessonLLMMeteringContext(
        route=route,
        turn_label=turn_label,
        page_uid=page_uid,
        block_uid=block_uid,
        llm_provider=llm_provider or "unknown",
        llm_model=llm_model or "unknown",
    )
    token = _ACTIVE_METERING_CONTEXT.set(context)
    try:
        yield context
    finally:
        _ACTIVE_METERING_CONTEXT.reset(token)


@contextmanager
def override_lesson_llm_prompt_breakdown(
    overrides: Mapping[str, Any] | None,
) -> Iterator[None]:
    token = _PROMPT_BREAKDOWN_OVERRIDES.set(dict(overrides or {}))
    try:
        yield
    finally:
        _PROMPT_BREAKDOWN_OVERRIDES.reset(token)


def active_lesson_llm_call_count() -> int:
    context = _ACTIVE_METERING_CONTEXT.get()
    if context is None:
        return 0
    return len(context.calls)


def default_lesson_llm_model() -> str:
    return (
        os.getenv("PEPTUTOR_LESSON_LLM_MODEL")
        or os.getenv("LLM_MODEL")
        or "unknown"
    )


def record_lesson_llm_call(
    *,
    prompt: str,
    completion: str,
    system_prompt: str | None = None,
    history_messages: list[dict[str, Any]] | None = None,
    llm_provider: str = "unknown",
    llm_model: str = "unknown",
    audit_tag: str = "",
    mode: str = "complete",
    status: str = "success",
    route: str = "",
    turn_label: str = "",
    page_uid: str = "",
    block_uid: str = "",
    call_id: str = "",
    provider_usage: Mapping[str, Any] | None = None,
) -> None:
    context = _ACTIVE_METERING_CONTEXT.get()
    if context is None:
        return

    history_bytes = _json_bytes(history_messages or [])
    system_prompt_bytes = _text_bytes(system_prompt)
    user_prompt_bytes = _text_bytes(prompt)
    prompt_bytes = user_prompt_bytes + system_prompt_bytes + history_bytes
    completion_bytes = _text_bytes(completion)
    token_counts = _token_counts(
        prompt=prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        completion=completion,
        provider_usage=provider_usage,
    )
    breakdown = _apply_prompt_breakdown_overrides(_prompt_breakdown(prompt))
    context.calls.append(
        LessonLLMCallMeter(
            call_id=call_id,
            llm_provider=llm_provider or context.llm_provider or "unknown",
            llm_model=llm_model or context.llm_model or "unknown",
            prompt_bytes=prompt_bytes,
            prompt_token_estimate=token_counts["prompt_token_estimate"],
            completion_bytes=completion_bytes,
            completion_token_estimate=token_counts["completion_token_estimate"],
            total_token_estimate=token_counts["total_token_estimate"],
            token_count_source=token_counts["token_count_source"],
            route=route,
            turn_label=turn_label,
            page_uid=page_uid,
            block_uid=block_uid,
            rag_context_bytes=breakdown["rag_context_bytes"],
            history_bytes=history_bytes,
            system_prompt_bytes=system_prompt_bytes,
            lesson_context_bytes=breakdown["lesson_context_bytes"],
            persona_prompt_bytes=breakdown["persona_prompt_bytes"],
            persona_capsule_bytes=breakdown["persona_capsule_bytes"],
            textbook_block_bytes=breakdown["textbook_block_bytes"],
            page_overview_bytes=breakdown["page_overview_bytes"],
            runtime_state_bytes=breakdown["runtime_state_bytes"],
            runtime_state_minimal_view_bytes=breakdown[
                "runtime_state_minimal_view_bytes"
            ],
            runtime_state_legacy_frame_bytes=breakdown[
                "runtime_state_legacy_frame_bytes"
            ],
            runtime_state_savings_candidate_bytes=breakdown[
                "runtime_state_savings_candidate_bytes"
            ],
            minimal_runtime_state_prompt_enabled=bool(
                breakdown["minimal_runtime_state_prompt_enabled"]
            ),
            teaching_move_bytes=breakdown["teaching_move_bytes"],
            policy_instruction_bytes=breakdown["policy_instruction_bytes"],
            quality_revision_prompt_bytes=breakdown[
                "quality_revision_prompt_bytes"
            ],
            learner_input_bytes=breakdown["learner_input_bytes"],
            prompt_frame_overhead_bytes=breakdown["prompt_frame_overhead_bytes"],
            json_serialization_overhead_bytes=breakdown[
                "json_serialization_overhead_bytes"
            ],
            output_schema_bytes=breakdown["output_schema_bytes"],
            planner_prompt_overhead_bytes=breakdown["planner_prompt_overhead_bytes"],
            responder_prompt_overhead_bytes=breakdown[
                "responder_prompt_overhead_bytes"
            ],
            revision_notes_bytes=breakdown["revision_notes_bytes"],
            unclassified_context_bytes=breakdown["unclassified_context_bytes"],
            other_bytes=breakdown["other_bytes"],
            unknown_context_bytes=breakdown["unknown_context_bytes"],
            audit_tag=audit_tag,
            mode=mode,
            status=status,
        )
    )


def summarize_lesson_llm_metering(
    context: LessonLLMMeteringContext,
    *,
    route: str = "",
    turn_label: str = "",
    page_uid: str = "",
    block_uid: str = "",
    llm_provider: str = "",
    llm_model: str = "",
) -> dict[str, Any] | None:
    if not context.calls:
        return None
    effective_route = route or context.route
    effective_turn_label = turn_label or context.turn_label
    effective_page_uid = page_uid or context.page_uid
    effective_block_uid = block_uid or context.block_uid
    effective_provider = llm_provider or context.llm_provider or "unknown"
    effective_model = llm_model or context.llm_model or "unknown"
    calls = [
        call.to_report_payload(
            route=effective_route,
            turn_label=effective_turn_label,
            page_uid=effective_page_uid,
            block_uid=effective_block_uid,
            llm_provider=effective_provider,
            llm_model=effective_model,
        )
        for call in context.calls
    ]
    sources = sorted({str(call["token_count_source"]) for call in calls})
    return {
        "llm_call_count": len(calls),
        "prompt_bytes": sum(int(call["prompt_bytes"]) for call in calls),
        "prompt_token_estimate": sum(
            int(call["prompt_token_estimate"]) for call in calls
        ),
        "completion_bytes": sum(int(call["completion_bytes"]) for call in calls),
        "completion_token_estimate": sum(
            int(call["completion_token_estimate"]) for call in calls
        ),
        "total_token_estimate": sum(int(call["total_token_estimate"]) for call in calls),
        "token_count_source": sources[0] if len(sources) == 1 else "mixed",
        "route": effective_route,
        "turn_label": effective_turn_label,
        "page_uid": effective_page_uid,
        "block_uid": effective_block_uid,
        "llm_provider": effective_provider,
        "llm_model": effective_model,
        "rag_context_bytes": sum(int(call["rag_context_bytes"]) for call in calls),
        "history_bytes": sum(int(call["history_bytes"]) for call in calls),
        "system_prompt_bytes": sum(
            int(call["system_prompt_bytes"]) for call in calls
        ),
        "lesson_context_bytes": sum(
            int(call["lesson_context_bytes"]) for call in calls
        ),
        "persona_prompt_bytes": sum(
            int(call["persona_prompt_bytes"]) for call in calls
        ),
        "persona_capsule_bytes": sum(
            int(call["persona_capsule_bytes"]) for call in calls
        ),
        "textbook_block_bytes": sum(
            int(call["textbook_block_bytes"]) for call in calls
        ),
        "page_overview_bytes": sum(
            int(call["page_overview_bytes"]) for call in calls
        ),
        "runtime_state_bytes": sum(
            int(call["runtime_state_bytes"]) for call in calls
        ),
        "runtime_state_minimal_view_bytes": sum(
            int(call["runtime_state_minimal_view_bytes"]) for call in calls
        ),
        "runtime_state_legacy_frame_bytes": sum(
            int(call["runtime_state_legacy_frame_bytes"]) for call in calls
        ),
        "runtime_state_savings_candidate_bytes": sum(
            int(call["runtime_state_savings_candidate_bytes"]) for call in calls
        ),
        "minimal_runtime_state_prompt_enabled_call_count": sum(
            1 for call in calls if bool(call["minimal_runtime_state_prompt_enabled"])
        ),
        "teaching_move_bytes": sum(
            int(call["teaching_move_bytes"]) for call in calls
        ),
        "policy_instruction_bytes": sum(
            int(call["policy_instruction_bytes"]) for call in calls
        ),
        "quality_revision_prompt_bytes": sum(
            int(call["quality_revision_prompt_bytes"]) for call in calls
        ),
        "learner_input_bytes": sum(
            int(call["learner_input_bytes"]) for call in calls
        ),
        "prompt_frame_overhead_bytes": sum(
            int(call["prompt_frame_overhead_bytes"]) for call in calls
        ),
        "json_serialization_overhead_bytes": sum(
            int(call["json_serialization_overhead_bytes"]) for call in calls
        ),
        "output_schema_bytes": sum(
            int(call["output_schema_bytes"]) for call in calls
        ),
        "planner_prompt_overhead_bytes": sum(
            int(call["planner_prompt_overhead_bytes"]) for call in calls
        ),
        "responder_prompt_overhead_bytes": sum(
            int(call["responder_prompt_overhead_bytes"]) for call in calls
        ),
        "revision_notes_bytes": sum(
            int(call["revision_notes_bytes"]) for call in calls
        ),
        "unclassified_context_bytes": sum(
            int(call["unclassified_context_bytes"]) for call in calls
        ),
        "other_bytes": sum(int(call["other_bytes"]) for call in calls),
        "unknown_context_bytes": sum(
            int(call["unknown_context_bytes"]) for call in calls
        ),
        "calls": calls,
    }


def _token_counts(
    *,
    prompt: str,
    system_prompt: str | None,
    history_messages: list[dict[str, Any]] | None,
    completion: str,
    provider_usage: Mapping[str, Any] | None,
) -> dict[str, Any]:
    provider_prompt = _int_from_mapping(
        provider_usage,
        ("prompt_tokens", "input_tokens"),
    )
    provider_completion = _int_from_mapping(
        provider_usage,
        ("completion_tokens", "output_tokens"),
    )
    provider_total = _int_from_mapping(provider_usage, ("total_tokens",))
    if provider_prompt is not None or provider_completion is not None:
        prompt_tokens = provider_prompt or 0
        completion_tokens = provider_completion or 0
        total_tokens = provider_total or prompt_tokens + completion_tokens
        return {
            "prompt_token_estimate": prompt_tokens,
            "completion_token_estimate": completion_tokens,
            "total_token_estimate": total_tokens,
            "token_count_source": TOKEN_COUNT_SOURCE_PROVIDER_USAGE,
        }

    prompt_text = "".join(
        (
            system_prompt or "",
            prompt,
            json.dumps(history_messages or [], ensure_ascii=False, separators=(",", ":")),
        )
    )
    prompt_tokens = _estimate_tokens(prompt_text)
    completion_tokens = _estimate_tokens(completion)
    return {
        "prompt_token_estimate": prompt_tokens,
        "completion_token_estimate": completion_tokens,
        "total_token_estimate": prompt_tokens + completion_tokens,
        "token_count_source": TOKEN_COUNT_SOURCE_BYTE_ESTIMATE,
    }


def _prompt_breakdown(prompt: str) -> dict[str, int]:
    empty = _empty_prompt_breakdown()
    try:
        payload = json.loads(prompt)
    except json.JSONDecodeError:
        empty["lesson_context_bytes"] = _text_bytes(prompt)
        empty["unclassified_context_bytes"] = _text_bytes(prompt)
        empty["other_bytes"] = _text_bytes(prompt)
        empty["unknown_context_bytes"] = _text_bytes(prompt)
        return empty
    if not isinstance(payload, dict):
        empty["lesson_context_bytes"] = _text_bytes(prompt)
        empty["unclassified_context_bytes"] = _text_bytes(prompt)
        empty["other_bytes"] = _text_bytes(prompt)
        empty["unknown_context_bytes"] = _text_bytes(prompt)
        return empty

    prompt_bytes = _text_bytes(prompt)
    ascii_json_prompt = "\\u" in prompt
    compact_prompt_bytes = _json_bytes(payload, ensure_ascii=ascii_json_prompt)
    json_serialization_overhead_bytes = max(0, prompt_bytes - compact_prompt_bytes)
    rag_context = payload.get("ragcontext")
    rag_context_bytes = (
        _json_bytes(rag_context, ensure_ascii=ascii_json_prompt) if rag_context else 0
    )
    turn_kind = str(payload.get("turn_kind") or "")
    frame = payload.get("frame") if isinstance(payload.get("frame"), dict) else {}

    learner_input_bytes = _component_bytes(
        payload,
        ("studentsaid", "learner_input"),
        ensure_ascii=ascii_json_prompt,
    ) + _component_bytes(
        frame,
        ("studentsaid",),
        ensure_ascii=ascii_json_prompt,
    )
    persona_capsule_bytes = _component_bytes(
        payload,
        ("persona_capsule",),
        ensure_ascii=ascii_json_prompt,
    )
    persona_prompt_bytes = _component_bytes(
        payload,
        ("persona_context", "style", "persona_capsule"),
        ensure_ascii=ascii_json_prompt,
    )
    textbook_block_bytes = _component_bytes(
        payload,
        (
            "currentgoal",
            "lesson_brief",
            "lesson_evidence",
            "current_block",
        ),
        ensure_ascii=ascii_json_prompt,
    ) + _component_bytes(
        frame,
        (
            "currentblock",
            "nextblock",
            "samepageblocks",
            "currenttaskfacts",
        ),
        ensure_ascii=ascii_json_prompt,
    )
    page_overview_bytes = _component_bytes(
        payload,
        ("page",),
        ensure_ascii=ascii_json_prompt,
    ) + _component_bytes(
        frame,
        ("lessoncontext",),
        ensure_ascii=ascii_json_prompt,
    )
    runtime_state_bytes = _component_bytes(
        payload,
        (
            "diagnosis",
            "mustsay",
            "fallback",
            "fallback_plan",
            "fallback_route",
            "plan",
            "safety_fallback_response",
            "return_anchor",
            "learner_memory",
            "state",
        ),
        ensure_ascii=ascii_json_prompt,
    ) + _component_bytes(
        frame,
        (
            "teacherasked",
            "runtimestate",
            "taskboundary",
            "recentdialogue",
            "allowedstatewrites",
            "learnerinputmatches",
        ),
        ensure_ascii=ascii_json_prompt,
    )
    prompt_runtime_state = frame.get("runtimestate")
    runtime_state_legacy_frame_bytes = _answer_turn_policy_legacy_state_bytes(
        frame,
        ensure_ascii=ascii_json_prompt,
    )
    if isinstance(prompt_runtime_state, dict):
        runtime_state_minimal_view_bytes = _json_bytes(
            prompt_runtime_state,
            ensure_ascii=ascii_json_prompt,
        )
    elif runtime_state_legacy_frame_bytes:
        runtime_state_minimal_view_bytes = _json_bytes(
            _answer_turn_policy_runtime_state_minimal_view(frame),
            ensure_ascii=ascii_json_prompt,
        )
    else:
        runtime_state_minimal_view_bytes = 0
    runtime_state_savings_candidate_bytes = max(
        0,
        runtime_state_legacy_frame_bytes - runtime_state_minimal_view_bytes,
    )
    teaching_move_bytes = _component_bytes(
        payload,
        ("teachermove", "teaching_move"),
        ensure_ascii=ascii_json_prompt,
    )
    quality_revision_prompt_bytes = 0
    revision_notes_bytes = 0
    if turn_kind == "answer_turn_policy_reply_quality_revision":
        quality_revision_prompt_bytes = _component_bytes(
            payload,
            ("instructions",),
            ensure_ascii=ascii_json_prompt,
        )
        revision_notes_bytes = _component_bytes(
            frame,
            ("originalteacherreply", "qualitynotes"),
            ensure_ascii=ascii_json_prompt,
        )
    output_schema_bytes = _component_bytes(
        payload,
        ("required_output_schema",),
        ensure_ascii=ascii_json_prompt,
    )
    planner_prompt_overhead_bytes = _component_bytes(
        payload,
        (
            "allowed_actions",
            "allowed_modes",
            "allowed_turn_labels",
        ),
        ensure_ascii=ascii_json_prompt,
    )
    responder_prompt_overhead_bytes = _component_bytes(
        payload,
        ("teacher_kernel_source", "turn_label"),
        ensure_ascii=ascii_json_prompt,
    )
    prompt_frame_value_bytes = _component_bytes(
        payload,
        ("turn_kind",),
        ensure_ascii=ascii_json_prompt,
    )
    policy_instruction_keys = [
        "natural_response_contract",
        "response_contract",
        "output_rules",
    ]
    if turn_kind != "answer_turn_policy_reply_quality_revision":
        policy_instruction_keys.append("instructions")
    policy_instruction_bytes = _component_bytes(
        payload,
        tuple(policy_instruction_keys),
        ensure_ascii=ascii_json_prompt,
    )

    known_user_prompt_bytes = sum(
        (
            rag_context_bytes,
            learner_input_bytes,
            persona_prompt_bytes,
            textbook_block_bytes,
            page_overview_bytes,
            runtime_state_bytes,
            teaching_move_bytes,
            policy_instruction_bytes,
            quality_revision_prompt_bytes,
            output_schema_bytes,
            planner_prompt_overhead_bytes,
            responder_prompt_overhead_bytes,
            revision_notes_bytes,
            prompt_frame_value_bytes,
        )
    )
    prompt_frame_overhead_bytes = max(
        0,
        compact_prompt_bytes - known_user_prompt_bytes,
    ) + prompt_frame_value_bytes
    unclassified_context_bytes = 0
    other_bytes = sum(
        (
            prompt_frame_overhead_bytes,
            json_serialization_overhead_bytes,
            output_schema_bytes,
            planner_prompt_overhead_bytes,
            responder_prompt_overhead_bytes,
            revision_notes_bytes,
            unclassified_context_bytes,
        )
    )
    lesson_context_bytes = max(0, prompt_bytes - rag_context_bytes)
    return {
        "rag_context_bytes": rag_context_bytes,
        "lesson_context_bytes": lesson_context_bytes,
        "persona_prompt_bytes": persona_prompt_bytes,
        "persona_capsule_bytes": persona_capsule_bytes,
        "textbook_block_bytes": textbook_block_bytes,
        "page_overview_bytes": page_overview_bytes,
        "runtime_state_bytes": runtime_state_bytes,
        "runtime_state_minimal_view_bytes": runtime_state_minimal_view_bytes,
        "runtime_state_legacy_frame_bytes": runtime_state_legacy_frame_bytes,
        "runtime_state_savings_candidate_bytes": (
            runtime_state_savings_candidate_bytes
        ),
        "minimal_runtime_state_prompt_enabled": bool(
            payload.get("minimal_runtime_state_prompt_enabled")
        )
        or (
            isinstance(prompt_runtime_state, dict)
            and "taskboundary" not in frame
            and "allowedstatewrites" not in frame
            and "learnerinputmatches" not in frame
        ),
        "teaching_move_bytes": teaching_move_bytes,
        "policy_instruction_bytes": policy_instruction_bytes,
        "quality_revision_prompt_bytes": quality_revision_prompt_bytes,
        "learner_input_bytes": learner_input_bytes,
        "prompt_frame_overhead_bytes": prompt_frame_overhead_bytes,
        "json_serialization_overhead_bytes": json_serialization_overhead_bytes,
        "output_schema_bytes": output_schema_bytes,
        "planner_prompt_overhead_bytes": planner_prompt_overhead_bytes,
        "responder_prompt_overhead_bytes": responder_prompt_overhead_bytes,
        "revision_notes_bytes": revision_notes_bytes,
        "unclassified_context_bytes": unclassified_context_bytes,
        "other_bytes": other_bytes,
        "unknown_context_bytes": unclassified_context_bytes,
    }


def _empty_prompt_breakdown() -> dict[str, Any]:
    return {
        "rag_context_bytes": 0,
        "lesson_context_bytes": 0,
        "persona_prompt_bytes": 0,
        "persona_capsule_bytes": 0,
        "textbook_block_bytes": 0,
        "page_overview_bytes": 0,
        "runtime_state_bytes": 0,
        "runtime_state_minimal_view_bytes": 0,
        "runtime_state_legacy_frame_bytes": 0,
        "runtime_state_savings_candidate_bytes": 0,
        "minimal_runtime_state_prompt_enabled": False,
        "teaching_move_bytes": 0,
        "policy_instruction_bytes": 0,
        "quality_revision_prompt_bytes": 0,
        "learner_input_bytes": 0,
        "prompt_frame_overhead_bytes": 0,
        "json_serialization_overhead_bytes": 0,
        "output_schema_bytes": 0,
        "planner_prompt_overhead_bytes": 0,
        "responder_prompt_overhead_bytes": 0,
        "revision_notes_bytes": 0,
        "unclassified_context_bytes": 0,
        "other_bytes": 0,
        "unknown_context_bytes": 0,
    }


def _component_bytes(
    mapping: Any,
    keys: tuple[str, ...],
    *,
    ensure_ascii: bool = False,
) -> int:
    if not isinstance(mapping, dict):
        return 0
    return sum(
        _json_bytes(mapping[key], ensure_ascii=ensure_ascii)
        for key in keys
        if key in mapping
    )


def _apply_prompt_breakdown_overrides(
    breakdown: dict[str, Any],
) -> dict[str, Any]:
    overrides = _PROMPT_BREAKDOWN_OVERRIDES.get() or {}
    if not overrides:
        return breakdown
    adjusted = dict(breakdown)
    for key in (
        "runtime_state_legacy_frame_bytes",
        "runtime_state_minimal_view_bytes",
        "runtime_state_savings_candidate_bytes",
        "minimal_runtime_state_prompt_enabled",
    ):
        if key in overrides:
            adjusted[key] = overrides[key]
    return adjusted


def _answer_turn_policy_legacy_state_bytes(
    frame: dict[str, Any],
    *,
    ensure_ascii: bool,
) -> int:
    return _component_bytes(
        frame,
        (
            "teacherasked",
            "taskboundary",
            "recentdialogue",
            "allowedstatewrites",
            "learnerinputmatches",
        ),
        ensure_ascii=ensure_ascii,
    )


def _answer_turn_policy_runtime_state_minimal_view(
    frame: dict[str, Any],
) -> dict[str, Any]:
    current_block = frame.get("currentblock")
    current_block_uid = ""
    if isinstance(current_block, dict):
        current_block_uid = str(current_block.get("blockuid") or "")

    allowed_state_writes = frame.get("allowedstatewrites")
    allowed_block_uids: list[str] = []
    if isinstance(allowed_state_writes, dict):
        current_block_uids = allowed_state_writes.get("currentblockuids")
        if isinstance(current_block_uids, list):
            allowed_block_uids = [
                str(block_uid)
                for block_uid in current_block_uids
                if str(block_uid).strip()
            ]

    learner_input_matches = frame.get("learnerinputmatches")
    matched_block_uids: list[str] = []
    matched_block_fields: dict[str, list[str]] = {}
    if isinstance(learner_input_matches, list):
        for item in learner_input_matches:
            if not isinstance(item, dict):
                continue
            block_uid = str(item.get("blockuid") or "")
            if not block_uid:
                continue
            matched_block_uids.append(block_uid)
            fields: list[str] = []
            matches = item.get("matches")
            if isinstance(matches, list):
                for match in matches:
                    if not isinstance(match, dict):
                        continue
                    field_name = str(match.get("field") or "").strip()
                    text = str(match.get("text") or "").strip()
                    if field_name and text:
                        fields.append(f"{field_name}:{text}")
                    elif field_name:
                        fields.append(field_name)
            if fields:
                matched_block_fields[block_uid] = sorted(dict.fromkeys(fields))

    task_boundary = frame.get("taskboundary")
    if not isinstance(task_boundary, dict):
        task_boundary = {}
    same_page_block_roles: list[dict[str, str]] = []
    raw_same_page_roles = task_boundary.get("samepageblockroles")
    if isinstance(raw_same_page_roles, list):
        for item in raw_same_page_roles:
            if not isinstance(item, dict):
                continue
            block_uid = str(item.get("blockuid") or "")
            if not block_uid:
                continue
            same_page_block_roles.append(
                {
                    "blockuid": block_uid,
                    "relation": str(item.get("relation") or ""),
                    "topic": str(item.get("topic") or ""),
                }
            )

    return {
        "teacherasked": str(frame.get("teacherasked") or ""),
        "currentblockuid": current_block_uid,
        "allowedcurrentblockuids": allowed_block_uids,
        "currentblockcanstay": current_block_uid in allowed_block_uids,
        "canwriteotherblocks": any(
            block_uid != current_block_uid for block_uid in allowed_block_uids
        ),
        "matchedblockuids": matched_block_uids,
        "matchedblockfields": matched_block_fields,
        "activequestionkind": str(task_boundary.get("activequestionkind") or ""),
        "currentblockscope": str(task_boundary.get("currentblockscope") or ""),
        "hasmultiplecurrenttargets": bool(
            task_boundary.get("currentblockhasmultipletargets"),
        ),
        "samepageblockroles": same_page_block_roles,
    }


def _int_from_mapping(
    mapping: Mapping[str, Any] | None,
    keys: tuple[str, ...],
) -> int | None:
    if not mapping:
        return None
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, float):
            return max(0, int(value))
    return None


def _estimate_tokens(text: str) -> int:
    byte_count = _text_bytes(text)
    if byte_count == 0:
        return 0
    return max(1, math.ceil(byte_count / 4))


def _text_bytes(text: str | None) -> int:
    if not text:
        return 0
    return len(str(text).encode("utf-8"))


def _json_bytes(value: Any, *, ensure_ascii: bool = False) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=ensure_ascii,
            separators=(",", ":"),
        ).encode("utf-8")
    )
