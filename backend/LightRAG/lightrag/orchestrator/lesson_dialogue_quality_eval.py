"""Offline quality evaluation for lesson teacher turns."""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from lightrag.orchestrator.lesson_runtime import (
    LessonTurnResult,
    PilotLessonCatalog,
)
from lightrag.orchestrator.simplemem_prompt_memory import LearnerMemorySummary
from lightrag.orchestrator.support_asset_retrieval import SupportAssetRetriever
from lightrag.pedagogy.system_contract import BANNED_TEACHER_PHRASES
from lightrag.pedagogy.responder import LessonResponder
from lightrag.pedagogy.teaching_move import LearnerSignal, TeachingMoveName
from lightrag.pedagogy.types import (
    EvaluationResult,
    RetrievalMode,
    TeachingAction,
    TurnLabel,
)


DEFAULT_FORBIDDEN_RESPONSE_PHRASES = [
    *BANNED_TEACHER_PHRASES,
    "如果老师问你",
]

_ASCII_TOKEN_RE = re.compile(r"^[a-z0-9_]+$", re.IGNORECASE)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_dialogue_quality_gold_path() -> Path:
    return _repo_root() / "app/knowledge/evals/lesson-dialogue-quality-gold.json"


def default_manifest_path() -> Path:
    return _repo_root() / "app/knowledge/structured/general/general-manifest.json"


class LessonDialogueQualityEvalSample(BaseModel):
    """One fixed classroom turn used to evaluate teacher quality contracts."""

    model_config = ConfigDict(extra="forbid")

    sample_id: str
    page_uid: str
    learner_inputs: list[str] = Field(min_length=1)
    student_id: str = "eval-student"
    force_open_state_after_start: bool = False
    memory_summary: LearnerMemorySummary | None = None
    expected_turn_label: TurnLabel
    expected_teaching_action: TeachingAction
    expected_retrieval_mode: RetrievalMode
    expected_evaluation: EvaluationResult | Literal["none"] | None = None
    expected_retrieved_block_uids: list[str] = Field(default_factory=list)
    expected_support_entry_uids: list[str] = Field(default_factory=list)
    required_response_phrases: list[str] = Field(default_factory=list)
    forbidden_response_phrases: list[str] = Field(default_factory=list)
    max_response_chars: int = 220
    expected_prompt_memory_buckets: list[str] = Field(default_factory=list)
    expected_persona_relationship_signals: list[str] = Field(default_factory=list)
    expected_airi_speech_style: str | None = None
    expected_airi_motion: str | None = None
    expected_lesson_evidence_page_type: str | None = None
    expected_lesson_evidence_exact_block_uid: str | None = None
    expected_lesson_evidence_source_refs: list[str] = Field(default_factory=list)
    expected_lesson_brief_material_uids: list[str] = Field(default_factory=list)
    required_lesson_brief_phrases: list[str] = Field(default_factory=list)
    expected_lesson_brief_answer_scope_phrases: list[str] = Field(default_factory=list)
    expected_teaching_move_signal: LearnerSignal | None = None
    expected_teaching_move: TeachingMoveName | None = None
    expected_state_current_block_uid: str | None = None
    expected_state_awaiting_answer: bool | None = None


class LessonDialogueQualityGoldSet(BaseModel):
    """Versioned quality gold-set for deterministic lesson turns."""

    model_config = ConfigDict(extra="forbid")

    version: int
    description: str | None = None
    samples: list[LessonDialogueQualityEvalSample] = Field(default_factory=list)


class LessonDialogueQualitySampleOutcome(BaseModel):
    """Observed quality result for one dialogue sample."""

    model_config = ConfigDict(extra="forbid")

    sample_id: str
    page_uid: str
    teacher_response: str
    expected_turn_label: TurnLabel
    actual_turn_label: TurnLabel
    expected_teaching_action: TeachingAction
    actual_teaching_action: TeachingAction
    expected_retrieval_mode: RetrievalMode
    actual_retrieval_mode: RetrievalMode
    expected_evaluation: EvaluationResult | Literal["none"] | None = None
    actual_evaluation: EvaluationResult | None = None
    expected_retrieved_block_uids: list[str] = Field(default_factory=list)
    actual_retrieved_block_uids: list[str] = Field(default_factory=list)
    expected_support_entry_uids: list[str] = Field(default_factory=list)
    actual_support_entry_uids: list[str] = Field(default_factory=list)
    expected_lesson_evidence_page_type: str | None = None
    actual_lesson_evidence_page_type: str | None = None
    expected_lesson_evidence_exact_block_uid: str | None = None
    actual_lesson_evidence_exact_block_uid: str | None = None
    expected_teaching_move_signal: LearnerSignal | None = None
    actual_teaching_move_signal: LearnerSignal | None = None
    expected_teaching_move: TeachingMoveName | None = None
    actual_teaching_move: TeachingMoveName | None = None
    expected_state_current_block_uid: str | None = None
    actual_state_current_block_uid: str | None = None
    expected_state_awaiting_answer: bool | None = None
    actual_state_awaiting_answer: bool | None = None
    missing_required_response_phrases: list[str] = Field(default_factory=list)
    matched_forbidden_response_phrases: list[str] = Field(default_factory=list)
    response_has_cjk: bool
    response_under_length_limit: bool
    retrieval_contract_pass: bool
    source_grounding_contract_pass: bool
    lesson_brief_contract_pass: bool
    teaching_move_contract_pass: bool
    state_progression_contract_pass: bool
    prompt_contract_pass: bool
    response_quality_pass: bool
    persona_contract_pass: bool
    memory_contract_pass: bool
    quality_score: float
    strict_pass: bool
    failure_reasons: list[str] = Field(default_factory=list)


class LessonDialogueQualityMetricSummary(BaseModel):
    """Aggregate metrics over dialogue quality outcomes."""

    model_config = ConfigDict(extra="forbid")

    sample_count: int
    strict_pass_count: int
    retrieval_contract_pass_count: int
    source_grounding_contract_pass_count: int
    lesson_brief_contract_pass_count: int
    teaching_move_contract_pass_count: int
    state_progression_contract_pass_count: int
    prompt_contract_pass_count: int
    response_quality_pass_count: int
    persona_contract_pass_count: int
    memory_contract_pass_count: int
    strict_pass_rate: float
    retrieval_contract_rate: float
    source_grounding_contract_rate: float
    lesson_brief_contract_rate: float
    teaching_move_contract_rate: float
    state_progression_contract_rate: float
    prompt_contract_rate: float
    response_quality_rate: float
    persona_contract_rate: float
    memory_contract_rate: float
    average_quality_score: float


class LessonDialogueQualityEvalReport(BaseModel):
    """Full quality eval report with per-sample outcomes and aggregates."""

    model_config = ConfigDict(extra="forbid")

    gold_path: str
    manifest_path: str
    sample_count: int
    overall: LessonDialogueQualityMetricSummary
    outcomes: list[LessonDialogueQualitySampleOutcome] = Field(default_factory=list)

    @property
    def failed_outcomes(self) -> list[LessonDialogueQualitySampleOutcome]:
        return [outcome for outcome in self.outcomes if not outcome.strict_pass]


class _StaticPromptMemoryProvider:
    semantic_recall_provider = None

    def __init__(self, summary: LearnerMemorySummary):
        self.summary = summary

    def get_summary(self, *, student_id: str, **_: Any) -> LearnerMemorySummary:
        return self.summary.model_copy(update={"student_id": student_id})


class _PromptCapture:
    """Capture the actual responder prompt while returning deterministic fallback."""

    def __init__(self) -> None:
        self.prompts: list[dict[str, Any]] = []
        self.system_prompts: list[str] = []

    def complete_text(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        history_messages: list[dict[str, Any]] | None = None,
        **_: Any,
    ) -> str:
        _ = history_messages
        payload = json.loads(prompt)
        self.prompts.append(payload)
        self.system_prompts.append(system_prompt or "")
        fallback_response = payload.get("safety_fallback_response")
        return fallback_response if isinstance(fallback_response, str) else ""

    @property
    def latest_prompt(self) -> dict[str, Any] | None:
        return self.prompts[-1] if self.prompts else None

    @property
    def latest_system_prompt(self) -> str:
        return self.system_prompts[-1] if self.system_prompts else ""


def load_dialogue_quality_gold_set(
    gold_path: Path | None = None,
) -> LessonDialogueQualityGoldSet:
    path = (gold_path or default_dialogue_quality_gold_path()).resolve()
    return LessonDialogueQualityGoldSet.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def evaluate_lesson_dialogue_quality(
    *,
    gold_path: Path | None = None,
    manifest_path: Path | None = None,
) -> LessonDialogueQualityEvalReport:
    resolved_gold_path = (gold_path or default_dialogue_quality_gold_path()).resolve()
    resolved_manifest_path = (manifest_path or default_manifest_path()).resolve()
    gold = load_dialogue_quality_gold_set(resolved_gold_path)

    catalog = PilotLessonCatalog(manifest_path=resolved_manifest_path)
    support_retriever = SupportAssetRetriever(catalog)
    outcomes = [
        _evaluate_sample(
            sample=sample,
            catalog=catalog,
            support_retriever=support_retriever,
        )
        for sample in gold.samples
    ]
    return LessonDialogueQualityEvalReport(
        gold_path=str(resolved_gold_path),
        manifest_path=str(resolved_manifest_path),
        sample_count=len(outcomes),
        overall=_build_summary(outcomes),
        outcomes=outcomes,
    )


def render_dialogue_quality_eval_report(
    report: LessonDialogueQualityEvalReport,
) -> str:
    lines = [
        "Lesson dialogue quality eval",
        f"Gold set: {report.gold_path}",
        f"Manifest: {report.manifest_path}",
        f"Samples: {report.sample_count}",
        _format_summary("Overall", report.overall),
    ]
    if report.failed_outcomes:
        lines.append("Failures:")
        for outcome in report.failed_outcomes:
            reasons = "; ".join(outcome.failure_reasons)
            lines.append(f"- {outcome.sample_id}: {reasons}")
    else:
        lines.append("PASS: dialogue quality samples matched the current baseline.")
    return "\n".join(lines)


def _evaluate_sample(
    *,
    sample: LessonDialogueQualityEvalSample,
    catalog: PilotLessonCatalog,
    support_retriever: SupportAssetRetriever,
) -> LessonDialogueQualitySampleOutcome:
    from lightrag.orchestrator.lesson_runtime import LessonRuntime

    memory_provider = (
        _StaticPromptMemoryProvider(sample.memory_summary)
        if sample.memory_summary is not None
        else None
    )
    prompt_capture = _PromptCapture()
    runtime = LessonRuntime(
        catalog,
        support_retriever=support_retriever,
        memory_provider=memory_provider,
        responder=LessonResponder(prompt_capture.complete_text),
        debug_signals_enabled=True,
    )
    state = runtime.start_page(sample.page_uid, sample.student_id).state
    if sample.force_open_state_after_start:
        state = state.model_copy(update={"awaiting_answer": False})

    result: LessonTurnResult | None = None
    for learner_input in sample.learner_inputs:
        result = runtime.handle_turn(state, learner_input)
        state = result.state
    if result is None:
        raise ValueError(f"Gold sample {sample.sample_id} did not run a turn")

    failure_reasons: list[str] = []
    retrieval_contract_pass = _check_retrieval_contract(
        sample=sample,
        result=result,
        failure_reasons=failure_reasons,
    )
    prompt_payload = prompt_capture.latest_prompt
    source_grounding_contract_pass = _check_source_grounding_contract(
        sample=sample,
        result=result,
        prompt_payload=prompt_payload,
        failure_reasons=failure_reasons,
    )
    lesson_brief_contract_pass = _check_lesson_brief_contract(
        sample=sample,
        prompt_payload=prompt_payload,
        failure_reasons=failure_reasons,
    )
    teaching_move_contract_pass = _check_teaching_move_contract(
        sample=sample,
        result=result,
        prompt_payload=prompt_payload,
        failure_reasons=failure_reasons,
    )
    state_progression_contract_pass = _check_state_progression_contract(
        sample=sample,
        result=result,
        failure_reasons=failure_reasons,
    )
    prompt_contract_pass = _check_prompt_contract(
        prompt_payload=prompt_payload,
        system_prompt=prompt_capture.latest_system_prompt,
        failure_reasons=failure_reasons,
    )
    response_quality_pass = _check_response_quality(
        sample=sample,
        result=result,
        failure_reasons=failure_reasons,
    )
    persona_contract_pass = _check_persona_contract(
        sample=sample,
        result=result,
        failure_reasons=failure_reasons,
    )
    memory_contract_pass = _check_memory_contract(
        sample=sample,
        result=result,
        failure_reasons=failure_reasons,
    )
    passed_groups = sum(
        [
            retrieval_contract_pass,
            source_grounding_contract_pass,
            lesson_brief_contract_pass,
            teaching_move_contract_pass,
            state_progression_contract_pass,
            prompt_contract_pass,
            response_quality_pass,
            persona_contract_pass,
            memory_contract_pass,
        ]
    )
    strict_pass = passed_groups == 9
    forbidden = _matched_forbidden_phrases(sample, result.teacher_response)
    actual_move_signal = _prompt_value(
        prompt_payload,
        "teaching_move",
        "detected_signal",
    )
    actual_move = _prompt_value(prompt_payload, "teaching_move", "move")

    return LessonDialogueQualitySampleOutcome(
        sample_id=sample.sample_id,
        page_uid=sample.page_uid,
        teacher_response=result.teacher_response,
        expected_turn_label=sample.expected_turn_label,
        actual_turn_label=result.turn_label,
        expected_teaching_action=sample.expected_teaching_action,
        actual_teaching_action=result.teaching_action,
        expected_retrieval_mode=sample.expected_retrieval_mode,
        actual_retrieval_mode=result.retrieval_mode,
        expected_evaluation=sample.expected_evaluation,
        actual_evaluation=result.evaluation,
        expected_retrieved_block_uids=sample.expected_retrieved_block_uids,
        actual_retrieved_block_uids=result.retrieved_block_uids,
        expected_support_entry_uids=sample.expected_support_entry_uids,
        actual_support_entry_uids=result.support_entry_uids,
        expected_lesson_evidence_page_type=sample.expected_lesson_evidence_page_type,
        actual_lesson_evidence_page_type=_prompt_value(
            prompt_payload,
            "lesson_evidence",
            "exact_page",
            "page_type",
        ),
        expected_lesson_evidence_exact_block_uid=(
            sample.expected_lesson_evidence_exact_block_uid
        ),
        actual_lesson_evidence_exact_block_uid=_prompt_value(
            prompt_payload,
            "lesson_evidence",
            "exact_block",
            "block_uid",
        ),
        expected_teaching_move_signal=sample.expected_teaching_move_signal,
        actual_teaching_move_signal=actual_move_signal,
        expected_teaching_move=sample.expected_teaching_move,
        actual_teaching_move=actual_move,
        expected_state_current_block_uid=sample.expected_state_current_block_uid,
        actual_state_current_block_uid=result.state.current_block_uid,
        expected_state_awaiting_answer=sample.expected_state_awaiting_answer,
        actual_state_awaiting_answer=result.state.awaiting_answer,
        missing_required_response_phrases=_missing_required_phrases(
            sample.required_response_phrases,
            result.teacher_response,
        ),
        matched_forbidden_response_phrases=forbidden,
        response_has_cjk=_contains_cjk(result.teacher_response),
        response_under_length_limit=len(result.teacher_response) <= sample.max_response_chars,
        retrieval_contract_pass=retrieval_contract_pass,
        source_grounding_contract_pass=source_grounding_contract_pass,
        lesson_brief_contract_pass=lesson_brief_contract_pass,
        teaching_move_contract_pass=teaching_move_contract_pass,
        state_progression_contract_pass=state_progression_contract_pass,
        prompt_contract_pass=prompt_contract_pass,
        response_quality_pass=response_quality_pass,
        persona_contract_pass=persona_contract_pass,
        memory_contract_pass=memory_contract_pass,
        quality_score=round(passed_groups / 9, 4),
        strict_pass=strict_pass,
        failure_reasons=failure_reasons,
    )


def _check_retrieval_contract(
    *,
    sample: LessonDialogueQualityEvalSample,
    result: LessonTurnResult,
    failure_reasons: list[str],
) -> bool:
    passed = True
    if result.turn_label != sample.expected_turn_label:
        failure_reasons.append(
            f"turn_label expected {sample.expected_turn_label}, got {result.turn_label}"
        )
        passed = False
    if result.teaching_action != sample.expected_teaching_action:
        failure_reasons.append(
            "teaching_action expected "
            f"{sample.expected_teaching_action}, got {result.teaching_action}"
        )
        passed = False
    if result.retrieval_mode != sample.expected_retrieval_mode:
        failure_reasons.append(
            "retrieval_mode expected "
            f"{sample.expected_retrieval_mode}, got {result.retrieval_mode}"
        )
        passed = False
    if sample.expected_evaluation is not None:
        expected_evaluation = (
            None
            if sample.expected_evaluation == "none"
            else sample.expected_evaluation
        )
        if result.evaluation != expected_evaluation:
            failure_reasons.append(
                f"evaluation expected {expected_evaluation}, got {result.evaluation}"
            )
            passed = False
    if not _is_subset(sample.expected_retrieved_block_uids, result.retrieved_block_uids):
        failure_reasons.append(
            "retrieved blocks missing "
            f"{sample.expected_retrieved_block_uids}, got {result.retrieved_block_uids}"
        )
        passed = False
    if not _is_subset(sample.expected_support_entry_uids, result.support_entry_uids):
        failure_reasons.append(
            "support entries missing "
            f"{sample.expected_support_entry_uids}, got {result.support_entry_uids}"
        )
        passed = False
    return passed


def _check_source_grounding_contract(
    *,
    sample: LessonDialogueQualityEvalSample,
    result: LessonTurnResult,
    prompt_payload: dict[str, Any] | None,
    failure_reasons: list[str],
) -> bool:
    if prompt_payload is None:
        failure_reasons.append("responder prompt payload missing")
        return False

    lesson_evidence = prompt_payload.get("lesson_evidence") or {}
    exact_page = lesson_evidence.get("exact_page") or {}
    exact_block = lesson_evidence.get("exact_block") or {}
    scope = lesson_evidence.get("scope") or {}
    passed = True

    if exact_page.get("page_uid") != result.page_uid:
        failure_reasons.append(
            "lesson_evidence exact_page.page_uid expected "
            f"{result.page_uid}, got {exact_page.get('page_uid')}"
        )
        passed = False
    if exact_block.get("block_uid") != result.block_uid:
        failure_reasons.append(
            "lesson_evidence exact_block.block_uid expected "
            f"{result.block_uid}, got {exact_block.get('block_uid')}"
        )
        passed = False
    if scope.get("grade") != result.state.current_grade:
        failure_reasons.append(
            f"lesson_evidence grade expected {result.state.current_grade}, "
            f"got {scope.get('grade')}"
        )
        passed = False
    if scope.get("semester") != result.state.current_semester:
        failure_reasons.append(
            f"lesson_evidence semester expected {result.state.current_semester}, "
            f"got {scope.get('semester')}"
        )
        passed = False
    if scope.get("unit") != result.state.current_unit:
        failure_reasons.append(
            f"lesson_evidence unit expected {result.state.current_unit}, "
            f"got {scope.get('unit')}"
        )
        passed = False

    if (
        sample.expected_lesson_evidence_page_type is not None
        and exact_page.get("page_type") != sample.expected_lesson_evidence_page_type
    ):
        failure_reasons.append(
            "lesson_evidence page_type expected "
            f"{sample.expected_lesson_evidence_page_type}, "
            f"got {exact_page.get('page_type')}"
        )
        passed = False
    if (
        sample.expected_lesson_evidence_exact_block_uid is not None
        and exact_block.get("block_uid")
        != sample.expected_lesson_evidence_exact_block_uid
    ):
        failure_reasons.append(
            "lesson_evidence exact block expected "
            f"{sample.expected_lesson_evidence_exact_block_uid}, "
            f"got {exact_block.get('block_uid')}"
        )
        passed = False

    source_refs = _flatten_source_refs(lesson_evidence)
    if not _is_subset(sample.expected_lesson_evidence_source_refs, source_refs):
        failure_reasons.append(
            "lesson_evidence source refs missing "
            f"{sample.expected_lesson_evidence_source_refs}, got {source_refs}"
        )
        passed = False
    return passed


def _check_lesson_brief_contract(
    *,
    sample: LessonDialogueQualityEvalSample,
    prompt_payload: dict[str, Any] | None,
    failure_reasons: list[str],
) -> bool:
    if prompt_payload is None:
        failure_reasons.append("lesson_brief prompt payload missing")
        return False

    lesson_brief = prompt_payload.get("lesson_brief") or {}
    lesson_evidence = prompt_payload.get("lesson_evidence") or {}
    exact_page = lesson_evidence.get("exact_page") or {}
    exact_block = lesson_evidence.get("exact_block") or {}
    page_context = lesson_brief.get("page_context") or {}
    turn_context = lesson_brief.get("turn_context") or {}
    answer_scope = lesson_brief.get("answer_scope") or {}
    materials = lesson_brief.get("materials") or []
    passed = True

    if page_context.get("page_uid") != exact_page.get("page_uid"):
        failure_reasons.append(
            "lesson_brief page_context.page_uid does not match lesson_evidence"
        )
        passed = False
    if turn_context.get("current_block_uid") != exact_block.get("block_uid"):
        failure_reasons.append(
            "lesson_brief turn_context.current_block_uid does not match exact block"
        )
        passed = False
    if not lesson_brief.get("teaching_focus"):
        failure_reasons.append("lesson_brief teaching_focus missing")
        passed = False
    if not materials:
        failure_reasons.append("lesson_brief materials missing")
        passed = False
    if not answer_scope.get("expected_answer_shape"):
        failure_reasons.append("lesson_brief answer_scope expected shape missing")
        passed = False

    material_uids = [
        material.get("uid")
        for material in materials
        if isinstance(material, dict) and isinstance(material.get("uid"), str)
    ]
    if not _is_subset(sample.expected_lesson_brief_material_uids, material_uids):
        failure_reasons.append(
            "lesson_brief materials missing "
            f"{sample.expected_lesson_brief_material_uids}, got {material_uids}"
        )
        passed = False

    serialized_brief = json.dumps(lesson_brief, ensure_ascii=False)
    missing_brief_phrases = _missing_required_phrases(
        sample.required_lesson_brief_phrases,
        serialized_brief,
    )
    if missing_brief_phrases:
        failure_reasons.append(
            f"lesson_brief missing required phrases {missing_brief_phrases}"
        )
        passed = False

    answer_scope_values = [
        str(answer_scope.get("expected_answer_shape") or ""),
        *[
            str(value)
            for value in answer_scope.get("acceptable_answers", [])
            if isinstance(value, str)
        ],
        *[
            str(value)
            for value in answer_scope.get("must_not_accept", [])
            if isinstance(value, str)
        ],
    ]
    answer_scope_text = "\n".join(answer_scope_values)
    missing_answer_scope = _missing_required_phrases(
        sample.expected_lesson_brief_answer_scope_phrases,
        answer_scope_text,
    )
    if missing_answer_scope:
        failure_reasons.append(
            f"lesson_brief answer_scope missing phrases {missing_answer_scope}"
        )
        passed = False
    return passed


def _check_teaching_move_contract(
    *,
    sample: LessonDialogueQualityEvalSample,
    result: LessonTurnResult,
    prompt_payload: dict[str, Any] | None,
    failure_reasons: list[str],
) -> bool:
    if prompt_payload is None:
        failure_reasons.append("teaching_move prompt payload missing")
        return False

    teaching_move = prompt_payload.get("teaching_move") or {}
    passed = True
    actual_signal = teaching_move.get("detected_signal")
    actual_move = teaching_move.get("move")
    if (
        sample.expected_teaching_move_signal is not None
        and actual_signal != sample.expected_teaching_move_signal
    ):
        failure_reasons.append(
            "teaching_move signal expected "
            f"{sample.expected_teaching_move_signal}, got {actual_signal}"
        )
        passed = False
    if (
        sample.expected_teaching_move is not None
        and actual_move != sample.expected_teaching_move
    ):
        failure_reasons.append(
            f"teaching_move expected {sample.expected_teaching_move}, "
            f"got {actual_move}"
        )
        passed = False
    if teaching_move.get("teaching_action") != result.teaching_action:
        failure_reasons.append(
            "teaching_move teaching_action expected "
            f"{result.teaching_action}, got {teaching_move.get('teaching_action')}"
        )
        passed = False
    if not teaching_move.get("rationale"):
        failure_reasons.append("teaching_move rationale missing")
        passed = False
    if not teaching_move.get("evidence_fields_used"):
        failure_reasons.append("teaching_move evidence_fields_used missing")
        passed = False
    if not teaching_move.get("expected_next_learner_action"):
        failure_reasons.append("teaching_move expected_next_learner_action missing")
        passed = False

    move_text = json.dumps(teaching_move, ensure_ascii=False)
    if "TB-" in move_text or sample.page_uid in move_text:
        failure_reasons.append("teaching_move leaked page-specific template details")
        passed = False
    return passed


def _check_state_progression_contract(
    *,
    sample: LessonDialogueQualityEvalSample,
    result: LessonTurnResult,
    failure_reasons: list[str],
) -> bool:
    passed = True
    if result.state.current_page_uid != sample.page_uid:
        failure_reasons.append(
            f"state current_page_uid expected {sample.page_uid}, "
            f"got {result.state.current_page_uid}"
        )
        passed = False
    if result.block_uid != result.state.current_block_uid:
        failure_reasons.append(
            f"result block_uid {result.block_uid} does not match state block "
            f"{result.state.current_block_uid}"
        )
        passed = False
    if (
        sample.expected_state_current_block_uid is not None
        and result.state.current_block_uid != sample.expected_state_current_block_uid
    ):
        failure_reasons.append(
            "state current_block_uid expected "
            f"{sample.expected_state_current_block_uid}, "
            f"got {result.state.current_block_uid}"
        )
        passed = False
    if (
        sample.expected_state_awaiting_answer is not None
        and result.state.awaiting_answer != sample.expected_state_awaiting_answer
    ):
        failure_reasons.append(
            "state awaiting_answer expected "
            f"{sample.expected_state_awaiting_answer}, "
            f"got {result.state.awaiting_answer}"
        )
        passed = False
    return passed


def _check_prompt_contract(
    *,
    prompt_payload: dict[str, Any] | None,
    system_prompt: str,
    failure_reasons: list[str],
) -> bool:
    if prompt_payload is None:
        failure_reasons.append("responder prompt contract missing")
        return False

    passed = True
    natural_contract = prompt_payload.get("natural_response_contract") or {}
    private_inputs = natural_contract.get("private_inputs") or []
    must_not_copy = natural_contract.get("must_not_copy") or []
    response_contract = prompt_payload.get("response_contract") or []
    output_rules = prompt_payload.get("output_rules") or []

    for key in ("lesson_evidence", "lesson_brief", "teaching_move"):
        if key not in prompt_payload:
            failure_reasons.append(f"prompt payload missing {key}")
            passed = False
    if "teacher_soul" in prompt_payload:
        failure_reasons.append("prompt payload includes raw teacher_soul")
        passed = False
    if not _is_subset(
        [
            "lesson_evidence",
            "lesson_brief",
            "teaching_move",
            "learner_memory",
            "persona_context",
        ],
        private_inputs,
    ):
        failure_reasons.append(
            f"natural_response_contract private_inputs incomplete: {private_inputs}"
        )
        passed = False
    if "JSON field names" not in must_not_copy:
        failure_reasons.append("natural_response_contract must_not_copy JSON keys missing")
        passed = False
    boundary = str(natural_contract.get("persona_memory_boundary") or "")
    if "must not change facts" not in boundary:
        failure_reasons.append("natural_response_contract boundary missing fact guard")
        passed = False
    if not any("teaching_move" in rule for rule in response_contract):
        failure_reasons.append("response_contract missing teaching_move rule")
        passed = False
    if not any("Never quote JSON keys" in rule for rule in output_rules):
        failure_reasons.append("output_rules missing private JSON leak guard")
        passed = False
    if "# Teacher Kernel" not in system_prompt:
        failure_reasons.append("system_prompt missing teacher kernel")
        passed = False
    if "# Lesson System Contract" in system_prompt or "# Teacher Soul" in system_prompt:
        failure_reasons.append("system_prompt includes deprecated long contract or soul")
        passed = False
    if len(system_prompt) > 2000:
        failure_reasons.append("system_prompt exceeds compact teacher kernel budget")
        passed = False
    return passed


def _check_response_quality(
    *,
    sample: LessonDialogueQualityEvalSample,
    result: LessonTurnResult,
    failure_reasons: list[str],
) -> bool:
    passed = True
    missing_required = _missing_required_phrases(
        sample.required_response_phrases,
        result.teacher_response,
    )
    if missing_required:
        failure_reasons.append(f"response missing required phrases {missing_required}")
        passed = False
    forbidden = _matched_forbidden_phrases(sample, result.teacher_response)
    if forbidden:
        failure_reasons.append(f"response leaked forbidden phrases {forbidden}")
        passed = False
    if not _contains_cjk(result.teacher_response):
        failure_reasons.append("response does not contain Simplified Chinese")
        passed = False
    if len(result.teacher_response) > sample.max_response_chars:
        failure_reasons.append(
            "response length exceeded "
            f"{sample.max_response_chars} chars: {len(result.teacher_response)}"
        )
        passed = False
    return passed


def _check_persona_contract(
    *,
    sample: LessonDialogueQualityEvalSample,
    result: LessonTurnResult,
    failure_reasons: list[str],
) -> bool:
    if result.debug_signals is None:
        failure_reasons.append("debug_signals missing")
        return False
    persona = result.debug_signals.persona
    passed = True
    if persona.profile_id != "peptutor-teacher-v1":
        failure_reasons.append(f"unexpected persona profile {persona.profile_id}")
        passed = False
    if not _is_subset(
        sample.expected_persona_relationship_signals,
        persona.relationship_signals,
    ):
        failure_reasons.append(
            "persona signals missing "
            f"{sample.expected_persona_relationship_signals}, "
            f"got {persona.relationship_signals}"
        )
        passed = False
    if (
        sample.expected_airi_speech_style
        and persona.airi_performance.speech_style != sample.expected_airi_speech_style
    ):
        failure_reasons.append(
            "AIRI speech_style expected "
            f"{sample.expected_airi_speech_style}, "
            f"got {persona.airi_performance.speech_style}"
        )
        passed = False
    if sample.expected_airi_motion and (
        persona.airi_performance.motion != sample.expected_airi_motion
    ):
        failure_reasons.append(
            f"AIRI motion expected {sample.expected_airi_motion}, "
            f"got {persona.airi_performance.motion}"
        )
        passed = False
    return passed


def _check_memory_contract(
    *,
    sample: LessonDialogueQualityEvalSample,
    result: LessonTurnResult,
    failure_reasons: list[str],
) -> bool:
    if not sample.expected_prompt_memory_buckets:
        return True
    if result.debug_signals is None:
        failure_reasons.append("memory debug_signals missing")
        return False
    actual = result.debug_signals.prompt_memory.injected_buckets
    if not _is_subset(sample.expected_prompt_memory_buckets, actual):
        failure_reasons.append(
            "prompt memory buckets missing "
            f"{sample.expected_prompt_memory_buckets}, got {actual}"
        )
        return False
    return True


def _build_summary(
    outcomes: list[LessonDialogueQualitySampleOutcome],
) -> LessonDialogueQualityMetricSummary:
    sample_count = len(outcomes)

    def rate(count: int) -> float:
        return round(count / sample_count, 4) if sample_count else 0.0

    strict_pass_count = sum(outcome.strict_pass for outcome in outcomes)
    retrieval_count = sum(outcome.retrieval_contract_pass for outcome in outcomes)
    source_grounding_count = sum(
        outcome.source_grounding_contract_pass for outcome in outcomes
    )
    lesson_brief_count = sum(outcome.lesson_brief_contract_pass for outcome in outcomes)
    teaching_move_count = sum(outcome.teaching_move_contract_pass for outcome in outcomes)
    state_progression_count = sum(
        outcome.state_progression_contract_pass for outcome in outcomes
    )
    prompt_contract_count = sum(outcome.prompt_contract_pass for outcome in outcomes)
    response_count = sum(outcome.response_quality_pass for outcome in outcomes)
    persona_count = sum(outcome.persona_contract_pass for outcome in outcomes)
    memory_count = sum(outcome.memory_contract_pass for outcome in outcomes)
    average_quality_score = (
        sum(outcome.quality_score for outcome in outcomes) / sample_count
        if sample_count
        else 0.0
    )
    return LessonDialogueQualityMetricSummary(
        sample_count=sample_count,
        strict_pass_count=strict_pass_count,
        retrieval_contract_pass_count=retrieval_count,
        source_grounding_contract_pass_count=source_grounding_count,
        lesson_brief_contract_pass_count=lesson_brief_count,
        teaching_move_contract_pass_count=teaching_move_count,
        state_progression_contract_pass_count=state_progression_count,
        prompt_contract_pass_count=prompt_contract_count,
        response_quality_pass_count=response_count,
        persona_contract_pass_count=persona_count,
        memory_contract_pass_count=memory_count,
        strict_pass_rate=rate(strict_pass_count),
        retrieval_contract_rate=rate(retrieval_count),
        source_grounding_contract_rate=rate(source_grounding_count),
        lesson_brief_contract_rate=rate(lesson_brief_count),
        teaching_move_contract_rate=rate(teaching_move_count),
        state_progression_contract_rate=rate(state_progression_count),
        prompt_contract_rate=rate(prompt_contract_count),
        response_quality_rate=rate(response_count),
        persona_contract_rate=rate(persona_count),
        memory_contract_rate=rate(memory_count),
        average_quality_score=round(average_quality_score, 4),
    )


def _format_summary(
    label: str,
    summary: LessonDialogueQualityMetricSummary,
) -> str:
    return (
        f"{label}: strict={summary.strict_pass_count}/{summary.sample_count} "
        f"({summary.strict_pass_rate:.0%}), "
        f"retrieval={summary.retrieval_contract_rate:.0%}, "
        f"source={summary.source_grounding_contract_rate:.0%}, "
        f"brief={summary.lesson_brief_contract_rate:.0%}, "
        f"move={summary.teaching_move_contract_rate:.0%}, "
        f"state={summary.state_progression_contract_rate:.0%}, "
        f"prompt={summary.prompt_contract_rate:.0%}, "
        f"response={summary.response_quality_rate:.0%}, "
        f"persona={summary.persona_contract_rate:.0%}, "
        f"memory={summary.memory_contract_rate:.0%}, "
        f"avg_quality={summary.average_quality_score:.2f}"
    )


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _missing_required_phrases(required: list[str], response: str) -> list[str]:
    response_lower = response.casefold()
    return [phrase for phrase in required if phrase.casefold() not in response_lower]


def _matched_forbidden_phrases(
    sample: LessonDialogueQualityEvalSample,
    response: str,
) -> list[str]:
    response_lower = response.casefold()
    forbidden = [
        *DEFAULT_FORBIDDEN_RESPONSE_PHRASES,
        *sample.forbidden_response_phrases,
    ]
    return [
        phrase
        for phrase in forbidden
        if _matches_forbidden_phrase(response_lower, phrase)
    ]


def _matches_forbidden_phrase(response_lower: str, phrase: str) -> bool:
    phrase_lower = phrase.casefold()
    if _ASCII_TOKEN_RE.fullmatch(phrase_lower):
        return bool(
            re.search(
                rf"(?<![a-z0-9_]){re.escape(phrase_lower)}(?![a-z0-9_])",
                response_lower,
            )
        )
    return phrase_lower in response_lower


def _is_subset(expected: list[str], actual: list[str]) -> bool:
    return set(expected).issubset(actual)


def _prompt_value(prompt_payload: dict[str, Any] | None, *path: str) -> Any:
    current: Any = prompt_payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _flatten_source_refs(payload: Any) -> list[str]:
    source_refs: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "source_refs" and isinstance(child, list):
                    source_refs.extend(item for item in child if isinstance(item, str))
                else:
                    visit(child)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return list(dict.fromkeys(source_refs))
