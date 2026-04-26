"""Route-contract scoring for captured lesson route transcripts.

This evaluator checks that live `/lesson/turn` responses satisfy backend
contracts: localized output, grounding, debug signals, AIRI performance metadata,
and latency. It is not a human pedagogical dialogue-quality judge.
"""

from __future__ import annotations

from collections.abc import Iterable
from statistics import mean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lightrag.orchestrator.lesson_dialogue_quality_eval import (
    DEFAULT_FORBIDDEN_RESPONSE_PHRASES,
)

_ALLOWED_AIRI_SPEECH_STYLES = {
    "normal",
    "slow_split",
    "short_prompt",
    "gentle_correction",
}
_ALLOWED_AIRI_INTERRUPT_POLICIES = {
    "barge_in_allowed",
    "finish_current_sentence",
    "no_interrupt",
}
_ALLOWED_AIRI_MOTIONS = {
    "Idle",
    "Listen",
    "Explain",
    "Nod",
    "Encourage",
    "Interrupted",
}
_ALLOWED_AIRI_CONTENT_SOURCES = {"lesson_runtime_teacher_response"}


class LessonTranscriptTurnRecord(BaseModel):
    """One observed `/lesson/turn` response plus optional smoke metadata."""

    model_config = ConfigDict(extra="forbid")

    name: str
    elapsed_ms: int = 0
    payload: dict[str, Any]

    @property
    def teacher_response(self) -> str:
        return str(self.payload.get("teacher_response") or "")

    @property
    def turn_label(self) -> str:
        return str(self.payload.get("turn_label") or "")

    @property
    def retrieval_mode(self) -> str:
        return str(self.payload.get("retrieval_mode") or "")


class LessonTranscriptTurnOutcome(BaseModel):
    """Per-turn quality verdict for a captured transcript."""

    model_config = ConfigDict(extra="forbid")

    name: str
    turn_label: str
    teaching_action: str
    retrieval_mode: str
    elapsed_ms: int
    teacher_response: str
    response_has_cjk: bool
    response_under_length_limit: bool
    matched_forbidden_response_phrases: list[str] = Field(default_factory=list)
    duplicate_previous_response: bool = False
    retrieval_grounded: bool
    branch_anchor_present: bool
    persona_signal_present: bool
    airi_performance_signal_present: bool
    airi_performance_adaptive: bool
    live_prompt_signal_present: bool
    prompt_memory_enabled: bool
    prompt_memory_bucket_count: int
    latency_pass: bool
    strict_pass: bool
    failure_reasons: list[str] = Field(default_factory=list)


class LessonTranscriptQualitySummary(BaseModel):
    """Aggregate quality metrics for a captured transcript."""

    model_config = ConfigDict(extra="forbid")

    turn_count: int
    strict_pass_count: int
    response_quality_pass_count: int
    retrieval_grounding_pass_count: int
    persona_signal_pass_count: int
    airi_performance_pass_count: int
    live_prompt_signal_pass_count: int
    latency_pass_count: int
    prompt_memory_enabled_turn_count: int
    prompt_memory_bucket_turn_count: int
    strict_pass_rate: float
    response_quality_rate: float
    retrieval_grounding_rate: float
    persona_signal_rate: float
    airi_performance_rate: float
    live_prompt_signal_rate: float
    latency_pass_rate: float
    average_latency_ms: int
    max_latency_ms: int


class LessonTranscriptQualityReport(BaseModel):
    """Transcript quality report suitable for live-model smoke output."""

    model_config = ConfigDict(extra="forbid")

    summary: LessonTranscriptQualitySummary
    outcomes: list[LessonTranscriptTurnOutcome] = Field(default_factory=list)

    @property
    def failed_outcomes(self) -> list[LessonTranscriptTurnOutcome]:
        return [outcome for outcome in self.outcomes if not outcome.strict_pass]


def score_lesson_transcript(
    turns: Iterable[LessonTranscriptTurnRecord | dict[str, Any]],
    *,
    max_response_chars: int = 320,
    max_latency_ms: int = 15_000,
) -> LessonTranscriptQualityReport:
    """Score a captured route transcript without calling an LLM judge."""

    records = [_normalize_turn_record(turn, index=index) for index, turn in enumerate(turns)]
    outcomes: list[LessonTranscriptTurnOutcome] = []
    previous_response = ""
    for record in records:
        outcome = _score_turn(
            record,
            previous_response=previous_response,
            max_response_chars=max_response_chars,
            max_latency_ms=max_latency_ms,
        )
        outcomes.append(outcome)
        previous_response = record.teacher_response

    return LessonTranscriptQualityReport(
        summary=_build_summary(outcomes),
        outcomes=outcomes,
    )


def render_transcript_quality_report(report: LessonTranscriptQualityReport) -> str:
    """Render a compact text report for CLI and smoke output."""

    summary = report.summary
    lines = [
        "Lesson transcript quality eval",
        (
            "Overall: "
            f"strict={summary.strict_pass_count}/{summary.turn_count} "
            f"({summary.strict_pass_rate:.0%}), "
            f"response={summary.response_quality_rate:.0%}, "
            f"retrieval={summary.retrieval_grounding_rate:.0%}, "
            f"persona={summary.persona_signal_rate:.0%}, "
            f"airi={summary.airi_performance_rate:.0%}, "
            f"live_prompt={summary.live_prompt_signal_rate:.0%}, "
            f"latency={summary.latency_pass_rate:.0%}, "
            f"avg_latency={summary.average_latency_ms}ms, "
            f"max_latency={summary.max_latency_ms}ms"
        ),
        (
            "Prompt memory observed: "
            f"enabled_turns={summary.prompt_memory_enabled_turn_count}, "
            f"bucket_turns={summary.prompt_memory_bucket_turn_count}"
        ),
    ]
    if report.failed_outcomes:
        lines.append("Failures:")
        for outcome in report.failed_outcomes:
            lines.append(
                f"- {outcome.name}: {'; '.join(outcome.failure_reasons)}"
            )
    else:
        lines.append(
            "PASS: route-contract transcript checks matched the current baseline; "
            "this is not a pedagogical dialogue-quality score."
        )
    return "\n".join(lines)


def _score_turn(
    record: LessonTranscriptTurnRecord,
    *,
    previous_response: str,
    max_response_chars: int,
    max_latency_ms: int,
) -> LessonTranscriptTurnOutcome:
    payload = record.payload
    response = record.teacher_response
    debug_signals = payload.get("debug_signals")
    debug = debug_signals if isinstance(debug_signals, dict) else {}
    persona = debug.get("persona") if isinstance(debug.get("persona"), dict) else {}
    airi_performance = (
        persona.get("airi_performance")
        if isinstance(persona.get("airi_performance"), dict)
        else {}
    )
    live_prompts = (
        debug.get("live_prompts")
        if isinstance(debug.get("live_prompts"), dict)
        else {}
    )
    prompt_memory = (
        debug.get("prompt_memory")
        if isinstance(debug.get("prompt_memory"), dict)
        else {}
    )

    forbidden = _matched_forbidden_phrases(response)
    response_has_cjk = _contains_cjk(response)
    response_under_length_limit = len(response) <= max_response_chars
    duplicate_previous_response = bool(response and response == previous_response)
    response_quality_pass = (
        response_has_cjk
        and response_under_length_limit
        and not forbidden
        and not duplicate_previous_response
    )
    retrieval_grounded = _retrieval_grounded(payload)
    branch_anchor_present = (
        record.retrieval_mode != "branch" or bool(payload.get("return_anchor"))
    )
    persona_signal_present = (
        persona.get("profile_id") == "peptutor-teacher-v1"
        and bool(airi_performance.get("speech_style"))
        and bool(airi_performance.get("motion"))
    )
    airi_performance_signal_present = _airi_performance_signal_present(
        airi_performance
    )
    airi_performance_adaptive = _airi_performance_adaptive(
        payload,
        airi_performance=airi_performance,
    )
    live_prompt_signal_present = live_prompts.get("enabled") is True
    prompt_memory_enabled = prompt_memory.get("enabled") is True
    injected_buckets = prompt_memory.get("injected_buckets")
    prompt_memory_bucket_count = (
        len(injected_buckets) if isinstance(injected_buckets, list) else 0
    )
    latency_pass = record.elapsed_ms <= max_latency_ms

    failure_reasons: list[str] = []
    if not response_quality_pass:
        if not response_has_cjk:
            failure_reasons.append("response has no Chinese scaffold")
        if not response_under_length_limit:
            failure_reasons.append(
                f"response longer than {max_response_chars} chars"
            )
        if forbidden:
            failure_reasons.append(f"forbidden response phrases {forbidden}")
        if duplicate_previous_response:
            failure_reasons.append("duplicated previous teacher response")
    if not retrieval_grounded:
        failure_reasons.append("ask_knowledge turn has no grounded retrieval hit")
    if not branch_anchor_present:
        failure_reasons.append("branch turn has no return_anchor")
    if not persona_signal_present:
        failure_reasons.append("persona/AIRI performance signal missing")
    if not airi_performance_signal_present:
        failure_reasons.append("AIRI performance contract incomplete")
    if airi_performance_signal_present and not airi_performance_adaptive:
        failure_reasons.append("AIRI performance plan does not match turn state")
    if not live_prompt_signal_present:
        failure_reasons.append("live prompt signal missing")
    if not latency_pass:
        failure_reasons.append(f"latency exceeded {max_latency_ms}ms")

    strict_pass = (
        response_quality_pass
        and retrieval_grounded
        and branch_anchor_present
        and persona_signal_present
        and airi_performance_signal_present
        and airi_performance_adaptive
        and live_prompt_signal_present
        and latency_pass
    )
    return LessonTranscriptTurnOutcome(
        name=record.name,
        turn_label=record.turn_label,
        teaching_action=str(payload.get("teaching_action") or ""),
        retrieval_mode=record.retrieval_mode,
        elapsed_ms=record.elapsed_ms,
        teacher_response=response,
        response_has_cjk=response_has_cjk,
        response_under_length_limit=response_under_length_limit,
        matched_forbidden_response_phrases=forbidden,
        duplicate_previous_response=duplicate_previous_response,
        retrieval_grounded=retrieval_grounded,
        branch_anchor_present=branch_anchor_present,
        persona_signal_present=persona_signal_present,
        airi_performance_signal_present=airi_performance_signal_present,
        airi_performance_adaptive=airi_performance_adaptive,
        live_prompt_signal_present=live_prompt_signal_present,
        prompt_memory_enabled=prompt_memory_enabled,
        prompt_memory_bucket_count=prompt_memory_bucket_count,
        latency_pass=latency_pass,
        strict_pass=strict_pass,
        failure_reasons=failure_reasons,
    )


def _build_summary(
    outcomes: list[LessonTranscriptTurnOutcome],
) -> LessonTranscriptQualitySummary:
    turn_count = len(outcomes)

    def rate(count: int) -> float:
        return round(count / turn_count, 4) if turn_count else 0.0

    strict_count = sum(outcome.strict_pass for outcome in outcomes)
    response_count = sum(_response_quality_pass(outcome) for outcome in outcomes)
    retrieval_count = sum(outcome.retrieval_grounded for outcome in outcomes)
    persona_count = sum(outcome.persona_signal_present for outcome in outcomes)
    airi_count = sum(
        outcome.airi_performance_signal_present
        and outcome.airi_performance_adaptive
        for outcome in outcomes
    )
    live_count = sum(outcome.live_prompt_signal_present for outcome in outcomes)
    latency_count = sum(outcome.latency_pass for outcome in outcomes)
    memory_enabled_count = sum(outcome.prompt_memory_enabled for outcome in outcomes)
    memory_bucket_count = sum(
        outcome.prompt_memory_bucket_count > 0 for outcome in outcomes
    )
    latencies = [outcome.elapsed_ms for outcome in outcomes]
    return LessonTranscriptQualitySummary(
        turn_count=turn_count,
        strict_pass_count=strict_count,
        response_quality_pass_count=response_count,
        retrieval_grounding_pass_count=retrieval_count,
        persona_signal_pass_count=persona_count,
        airi_performance_pass_count=airi_count,
        live_prompt_signal_pass_count=live_count,
        latency_pass_count=latency_count,
        prompt_memory_enabled_turn_count=memory_enabled_count,
        prompt_memory_bucket_turn_count=memory_bucket_count,
        strict_pass_rate=rate(strict_count),
        response_quality_rate=rate(response_count),
        retrieval_grounding_rate=rate(retrieval_count),
        persona_signal_rate=rate(persona_count),
        airi_performance_rate=rate(airi_count),
        live_prompt_signal_rate=rate(live_count),
        latency_pass_rate=rate(latency_count),
        average_latency_ms=round(mean(latencies)) if latencies else 0,
        max_latency_ms=max(latencies) if latencies else 0,
    )


def _normalize_turn_record(
    turn: LessonTranscriptTurnRecord | dict[str, Any],
    *,
    index: int,
) -> LessonTranscriptTurnRecord:
    if isinstance(turn, LessonTranscriptTurnRecord):
        return turn
    if "payload" in turn:
        return LessonTranscriptTurnRecord.model_validate(turn)
    return LessonTranscriptTurnRecord(
        name=str(turn.get("name") or f"turn-{index + 1}"),
        elapsed_ms=int(turn.get("elapsed_ms") or 0),
        payload=turn,
    )


def _response_quality_pass(outcome: LessonTranscriptTurnOutcome) -> bool:
    return (
        outcome.response_has_cjk
        and outcome.response_under_length_limit
        and not outcome.matched_forbidden_response_phrases
        and not outcome.duplicate_previous_response
    )


def _retrieval_grounded(payload: dict[str, Any]) -> bool:
    if payload.get("turn_label") != "ask_knowledge":
        return True
    mode = payload.get("retrieval_mode")
    if mode == "none":
        return False
    retrieved = payload.get("retrieved_block_uids")
    return isinstance(retrieved, list) and bool(retrieved)


def _airi_performance_signal_present(airi_performance: dict[str, Any]) -> bool:
    speech_style = airi_performance.get("speech_style")
    interrupt_policy = airi_performance.get("interrupt_policy")
    mouth_intensity = airi_performance.get("mouth_intensity")
    content_source = airi_performance.get("content_source")
    fallback_allowed = airi_performance.get("fallback_allowed")
    motion = airi_performance.get("motion")

    return (
        speech_style in _ALLOWED_AIRI_SPEECH_STYLES
        and interrupt_policy in _ALLOWED_AIRI_INTERRUPT_POLICIES
        and isinstance(mouth_intensity, (int, float))
        and not isinstance(mouth_intensity, bool)
        and 0.0 <= float(mouth_intensity) <= 1.0
        and content_source in _ALLOWED_AIRI_CONTENT_SOURCES
        and isinstance(fallback_allowed, bool)
        and motion in _ALLOWED_AIRI_MOTIONS
    )


def _airi_performance_adaptive(
    payload: dict[str, Any],
    *,
    airi_performance: dict[str, Any],
) -> bool:
    expected_speech_style = _expected_airi_speech_style(payload)
    if expected_speech_style is None:
        return True
    return airi_performance.get("speech_style") == expected_speech_style


def _expected_airi_speech_style(payload: dict[str, Any]) -> str | None:
    turn_label = str(payload.get("turn_label") or "")
    teaching_action = str(payload.get("teaching_action") or "")
    evaluation = _effective_evaluation(payload)

    if evaluation in {"correct", "acceptable"} and teaching_action == "confirm":
        return "normal"
    if teaching_action in {"hint", "model", "repeat_drill"}:
        if evaluation in {"incorrect", "partially_correct", "unclear"}:
            return "gentle_correction"
        return "slow_split"
    if turn_label == "ask_help":
        return "slow_split"
    if turn_label == "ask_knowledge" or teaching_action == "explain":
        return "normal"
    if teaching_action == "redirect":
        return "short_prompt"
    if teaching_action == "page_intro":
        return "normal"
    return None


def _effective_evaluation(payload: dict[str, Any]) -> str:
    evaluation = payload.get("evaluation")
    if evaluation:
        return str(evaluation)

    state = payload.get("state")
    if isinstance(state, dict) and state.get("last_eval_result"):
        return str(state["last_eval_result"])
    return ""


def _matched_forbidden_phrases(response: str) -> list[str]:
    response_lower = response.casefold()
    return [
        phrase
        for phrase in DEFAULT_FORBIDDEN_RESPONSE_PHRASES
        if phrase.casefold() in response_lower
    ]


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)
