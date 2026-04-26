"""Structured pilot loader and text-first lesson runtime helpers."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from lightrag.orchestrator.lesson_brief_builder import LessonBriefBuilder
from lightrag.orchestrator.lesson_evidence import LessonEvidenceLookup
from lightrag.orchestrator.lesson_graph import build_lesson_turn_graph
from lightrag.orchestrator.lesson_readiness_judge import (
    ReadinessJudge,
    ReadinessJudgeResult,
)
from lightrag.orchestrator.lesson_retrieval import ScopedRetriever
from lightrag.orchestrator.lesson_persona import (
    AiriPerformancePlan,
    ClassroomAffectState,
    LessonPersonaContext,
    build_lesson_persona_context_for_turn,
)
from lightrag.orchestrator.page_overview_skill import PageOverview, PageOverviewSkill
from lightrag.orchestrator.lesson_state import LessonRuntimeState
from lightrag.orchestrator.simplemem_prompt_memory import LearnerMemorySummary
from lightrag.orchestrator.simplemem_writeback import SimpleMemSQLiteLessonMemoryWriter
from lightrag.orchestrator.support_asset_retrieval import SupportAssetRetriever, SupportMatch
from lightrag.orchestrator.teaching_move_planner import TeachingMovePlanner
from lightrag.pedagogy.lesson_brief import (
    CurrentTurnLessonBrief,
    LessonBriefMisconceptionHint,
)
from lightrag.pedagogy.planner import (
    LessonPlanner,
    OpenTurnRouteDecision,
    PlannerDecision,
)
from lightrag.pedagogy.responder import LessonResponder
from lightrag.pedagogy.evaluation import evaluate_answer, normalize_text
from lightrag.pedagogy.types import (
    EvaluationResult,
    RetrievalMode,
    TeachingAction,
    TurnLabel,
)
from lightrag.utils import logger

_DRINK_ANSWER_TOKENS = {"water", "juice", "tea", "milk", "coffee"}
_FOOD_ANSWER_TOKENS = {
    "sandwich",
    "bread",
    "noodles",
    "rice",
    "vegetables",
    "chicken",
    "hamburger",
    "salad",
    "ice",
    "cream",
}
_TASK_INSTRUCTION_STARTERS = (
    "create ",
    "make ",
    "list ",
    "identify ",
    "group ",
    "match ",
    "practice ",
    "design ",
    "write ",
)
_PARTY_LIST_ITEM_TOKENS = {
    "apple",
    "apples",
    "banana",
    "bananas",
    "bread",
    "cake",
    "cakes",
    "cheese",
    "chocolate",
    "chocolates",
    "drink",
    "drinks",
    "food",
    "fruit",
    "fruits",
    "juice",
    "milk",
    "tea",
    "water",
}
_PARTY_LIST_ACTION_TOKENS = {"bring", "buy", "take", "prepare", "need", "want"}


def _is_enabled(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().casefold() in {"1", "true", "yes", "on"}


class ScopeInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    grade: str
    semester: str
    unit: str
    pages: list[int] = Field(default_factory=list)


class PageLessonRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page_uid: str
    page_type: str
    page_intro_cn: str
    entry_probe_questions: list[str] = Field(default_factory=list)
    priority_blocks: list[str] = Field(default_factory=list)
    assumed_prior_knowledge: list[dict[str, Any]] = Field(default_factory=list)


class LessonCatalogPageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_uid: str
    page: int
    page_type: str
    page_intro_cn: str


class LessonCatalogScopeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: str
    semester: str
    unit: str
    pages: list[LessonCatalogPageRecord] = Field(default_factory=list)


class LessonCatalogOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_count: int
    page_count: int
    block_count: int
    scopes: list[LessonCatalogScopeRecord] = Field(default_factory=list)


class TeachingBlockRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    block_uid: str
    page_uid: str
    page_type: str
    block_type: str
    source_refs: list[str] = Field(default_factory=list)
    teaching_goal: str
    teaching_summary: str
    focus_vocabulary: list[str] = Field(default_factory=list)
    core_patterns: list[str] = Field(default_factory=list)
    allowed_answer_scope: list[str] = Field(default_factory=list)
    entry_probe_questions: list[str] = Field(default_factory=list)
    repair_modes: list[str] = Field(default_factory=list)
    next_block_uids: list[str] = Field(default_factory=list)
    learning_target_uids: list[str] = Field(default_factory=list)
    branchable_topics: list[str] = Field(default_factory=list)
    return_anchors: list[str] = Field(default_factory=list)


class PilotLessonFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pilot_id: str
    scope: ScopeInfo
    source_files: list[str] = Field(default_factory=list)
    learning_targets: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_atoms: list[dict[str, Any]] = Field(default_factory=list)
    page_lessons: list[PageLessonRecord] = Field(default_factory=list)
    teaching_blocks: list[TeachingBlockRecord] = Field(default_factory=list)


class LessonTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_uid: str
    block_uid: str | None
    turn_label: TurnLabel
    teaching_action: TeachingAction
    retrieval_mode: RetrievalMode
    teacher_response: str
    state: LessonRuntimeState
    evaluation: EvaluationResult | None = None
    retrieved_block_uids: list[str] = Field(default_factory=list)
    support_entry_uids: list[str] = Field(default_factory=list)
    return_anchor: str | None = None
    branch_reason: str | None = None
    debug_signals: "LessonTurnDebugSignals | None" = None

    @model_serializer(mode="wrap")
    def _serialize_without_empty_debug_signals(self, handler):
        payload = handler(self)
        if payload.get("debug_signals") is None:
            payload.pop("debug_signals", None)
        return payload


class LessonLivePromptsDebugSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class LessonVectorRetrievalDebugSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    hit_modes: list[Literal["unit", "branch"]] = Field(default_factory=list)


class LessonPromptMemoryDebugSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    injected_buckets: list[str] = Field(default_factory=list)


class LessonSemanticRecallDebugSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    recalled_memories: list[str] = Field(default_factory=list)


class LessonMemoryRuntimeDebugSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: str
    project: str
    memory_session_id: str | None = None
    last_recall_status: Literal["success", "skipped", "degraded"]
    last_recall_summary: str
    last_writeback_status: Literal["success", "skipped", "degraded"]
    last_writeback_summary: str
    degradation_state: Literal[
        "healthy",
        "idle",
        "memory_disabled",
        "session_degraded",
        "recall_degraded",
        "writeback_degraded",
        "recall_and_writeback_degraded",
    ]


class LessonPersonaDebugSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    schema_version: str
    profile_id: str
    profile_version: str
    display_name: str
    voice_hint: str
    allowed_to_shape: list[str] = Field(default_factory=list)
    protected_authorities: list[str] = Field(default_factory=list)
    relationship_student_id: str
    relationship_signals: list[str] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    mastery_signals: list[str] = Field(default_factory=list)
    semantic_memories: list[str] = Field(default_factory=list)
    affect_state: ClassroomAffectState
    airi_performance: AiriPerformancePlan


class LessonTurnDebugSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    live_prompts: LessonLivePromptsDebugSignal
    vector_retrieval: LessonVectorRetrievalDebugSignal
    prompt_memory: LessonPromptMemoryDebugSignal
    semantic_recall: LessonSemanticRecallDebugSignal
    memory_runtime: LessonMemoryRuntimeDebugSignal
    persona: LessonPersonaDebugSignal


def _extract_page_number(page_uid: str) -> int:
    match = re.search(r"-P(\d+)(?:-\d+)?$", page_uid)
    if not match:
        raise ValueError(f"Cannot extract page number from page uid: {page_uid}")
    return int(match.group(1))


def _default_manifest_path() -> Path:
    env_path = os.getenv("PEPTUTOR_PILOT_MANIFEST")
    if env_path:
        return Path(env_path)

    current = Path(__file__).resolve()
    for ancestor in current.parents:
        candidate = ancestor / "app/knowledge/structured/g5s1u3-pilot-manifest.json"
        if candidate.exists():
            return candidate

    raise FileNotFoundError("Unable to locate g5s1u3-pilot-manifest.json")


class PilotLessonCatalog:
    """Loads the approved G5 S1 U3 pilot into page and block maps."""

    def __init__(self, manifest_path: Path | None = None):
        self.manifest_path = (manifest_path or _default_manifest_path()).resolve()
        self.pages: dict[str, PageLessonRecord] = {}
        self.blocks: dict[str, TeachingBlockRecord] = {}
        self.page_scopes: dict[str, ScopeInfo] = {}
        self._load()

    def get_page(self, page_uid: str) -> PageLessonRecord:
        return self.pages[page_uid]

    def get_block(self, block_uid: str) -> TeachingBlockRecord:
        return self.blocks[block_uid]

    def get_scope_for_page(self, page_uid: str) -> ScopeInfo:
        return self.page_scopes[page_uid]

    def first_block_for_page(self, page_uid: str) -> TeachingBlockRecord:
        page = self.get_page(page_uid)
        if page.priority_blocks:
            return self.get_block(page.priority_blocks[0])
        for block in self.blocks.values():
            if block.page_uid == page_uid:
                return block
        raise KeyError(f"No teaching block found for page {page_uid}")

    def blocks_for_page(
        self,
        page_uid: str,
        *,
        exclude_block_uid: str | None = None,
    ) -> list[TeachingBlockRecord]:
        page = self.get_page(page_uid)
        ordered_uids = [
            block_uid
            for block_uid in page.priority_blocks
            if block_uid != exclude_block_uid and block_uid in self.blocks
        ]
        seen = set(ordered_uids)
        for block in self.blocks.values():
            if (
                block.page_uid == page_uid
                and block.block_uid != exclude_block_uid
                and block.block_uid not in seen
            ):
                ordered_uids.append(block.block_uid)
        return [self.blocks[block_uid] for block_uid in ordered_uids]

    def blocks_for_unit(
        self,
        page_uid: str,
        *,
        exclude_page_uid: str | None = None,
    ) -> list[TeachingBlockRecord]:
        scope = self.get_scope_for_page(page_uid)
        result = []
        for candidate_page_uid, candidate_scope in self.page_scopes.items():
            if (
                candidate_scope.grade == scope.grade
                and candidate_scope.semester == scope.semester
                and candidate_scope.unit == scope.unit
                and candidate_page_uid != exclude_page_uid
            ):
                result.extend(self.blocks_for_page(candidate_page_uid))
        return result

    def page_records_for_scope(
        self,
        *,
        grade: str,
        semester: str,
        unit: str,
    ) -> list[LessonCatalogPageRecord]:
        page_records: list[LessonCatalogPageRecord] = []
        for page_uid, scope in self.page_scopes.items():
            if (
                scope.grade == grade
                and scope.semester == semester
                and scope.unit == unit
            ):
                page = self.get_page(page_uid)
                page_records.append(
                    LessonCatalogPageRecord(
                        page_uid=page_uid,
                        page=_extract_page_number(page_uid),
                        page_type=page.page_type,
                        page_intro_cn=page.page_intro_cn,
                    )
                )
        return sorted(page_records, key=lambda record: (record.page, record.page_uid))

    def catalog_outline(self) -> LessonCatalogOutline:
        scope_records: list[LessonCatalogScopeRecord] = []
        seen_scope_keys: set[tuple[str, str, str]] = set()
        for scope in self.page_scopes.values():
            scope_key = (scope.grade, scope.semester, scope.unit)
            if scope_key in seen_scope_keys:
                continue
            seen_scope_keys.add(scope_key)
            scope_records.append(
                LessonCatalogScopeRecord(
                    grade=scope.grade,
                    semester=scope.semester,
                    unit=scope.unit,
                    pages=self.page_records_for_scope(
                        grade=scope.grade,
                        semester=scope.semester,
                        unit=scope.unit,
                    ),
                )
            )
        return LessonCatalogOutline(
            scope_count=len(scope_records),
            page_count=len(self.pages),
            block_count=len(self.blocks),
            scopes=scope_records,
        )

    def _load(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        for file_ref in manifest.get("files", []):
            file_path = self._resolve_manifest_entry(file_ref)
            payload = PilotLessonFile.model_validate_json(
                file_path.read_text(encoding="utf-8")
            )
            for page in payload.page_lessons:
                self.pages[page.page_uid] = page
                self.page_scopes[page.page_uid] = payload.scope
            for block in payload.teaching_blocks:
                self.blocks[block.block_uid] = block

    def _resolve_manifest_entry(self, file_ref: str) -> Path:
        raw_path = Path(file_ref)
        if raw_path.is_absolute() and raw_path.exists():
            return raw_path

        candidates = [self.manifest_path.parent / raw_path]
        candidates.extend(ancestor / raw_path for ancestor in self.manifest_path.parents)
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        raise FileNotFoundError(f"Unable to resolve pilot data file: {file_ref}")


_HELP_HINTS = (
    "help",
    "again",
    "don't know",
    "dont know",
    "不会",
    "不懂",
    "不明白",
    "听不懂",
    "再来",
    "再说一遍",
    "慢一点",
    "慢点",
    "拆开",
    "一步一步",
    "跟不上",
)
_KNOWLEDGE_HINTS = ("mean", "meaning", "what does", "what is", "difference", "怎么说", "什么意思")
_EMOTION_HELP_HINTS = (
    "nervous",
    "worried",
    "afraid",
    "scared",
    "shy",
    "紧张",
    "害怕",
    "担心",
    "不敢",
    "怕",
)


class LessonTeacherResponseStreamSink:
    """Request-local bridge from synchronous lesson runtime code to SSE output."""

    def __init__(
        self,
        *,
        on_text_delta: Callable[[str], None],
        on_action_metadata: Callable[[dict[str, Any]], None] | None = None,
    ):
        self._on_text_delta = on_text_delta
        self._on_action_metadata = on_action_metadata
        self.text_delta_emitted = False
        self.action_metadata_emitted = False

    def emit_text_delta(self, text: str) -> None:
        if not text:
            return
        self.text_delta_emitted = True
        self._on_text_delta(text)

    def emit_action_metadata(
        self,
        *,
        teaching_action: TeachingAction,
        evaluation: EvaluationResult | None,
        branch_active: bool,
        turn_label: TurnLabel,
        airi_performance: dict[str, Any] | None = None,
    ) -> None:
        if self._on_action_metadata is None or self.action_metadata_emitted:
            return
        self.action_metadata_emitted = True
        self._on_action_metadata(
            {
                "teaching_action": teaching_action,
                "evaluation": evaluation,
                "branch_active": branch_active,
                "turn_label": turn_label,
                "airi_performance": airi_performance,
            }
        )


_ACTIVE_TEACHER_RESPONSE_STREAM: ContextVar[
    LessonTeacherResponseStreamSink | None
] = ContextVar("active_lesson_teacher_response_stream", default=None)


@contextmanager
def stream_lesson_teacher_response(sink: LessonTeacherResponseStreamSink):
    token = _ACTIVE_TEACHER_RESPONSE_STREAM.set(sink)
    try:
        yield
    finally:
        _ACTIVE_TEACHER_RESPONSE_STREAM.reset(token)


class LessonRuntime:
    """Deterministic text-first lesson loop for the pilot pages."""

    def __init__(
        self,
        catalog: PilotLessonCatalog,
        retriever=None,
        support_retriever: SupportAssetRetriever | None = None,
        memory_provider=None,
        memory_writer: SimpleMemSQLiteLessonMemoryWriter | None = None,
        evidence_lookup: LessonEvidenceLookup | None = None,
        brief_builder: LessonBriefBuilder | None = None,
        teaching_move_planner: TeachingMovePlanner | None = None,
        planner: LessonPlanner | None = None,
        readiness_judge: ReadinessJudge | None = None,
        responder: LessonResponder | None = None,
        page_overview_skill: PageOverviewSkill | None = None,
        feature_statuses: dict[str, Any] | None = None,
        debug_signals_enabled: bool | None = None,
    ):
        self.catalog = catalog
        self.retriever = retriever or ScopedRetriever(catalog)
        self.support_retriever = support_retriever
        self.memory_provider = memory_provider
        self.memory_writer = memory_writer
        self.evidence_lookup = evidence_lookup or LessonEvidenceLookup(catalog)
        self.brief_builder = brief_builder or LessonBriefBuilder()
        self.teaching_move_planner = teaching_move_planner or TeachingMovePlanner()
        self.planner = planner
        self.readiness_judge = readiness_judge
        self.responder = responder
        self.page_overview_skill = page_overview_skill or PageOverviewSkill()
        self.feature_statuses = feature_statuses or {}
        self.debug_signals_enabled = (
            _is_enabled(os.getenv("PEPTUTOR_DEBUG_SIGNALS"))
            if debug_signals_enabled is None
            else debug_signals_enabled
        )
        self.turn_graph = build_lesson_turn_graph(self)

    def start_page(self, page_uid: str, student_id: str) -> LessonTurnResult:
        return self._run_turn_graph(
            {
                "page_uid": page_uid,
                "student_id": student_id,
                "state": None,
            }
        )

    def _start_page_impl(self, page_uid: str, student_id: str) -> LessonTurnResult:
        page = self.catalog.get_page(page_uid)
        scope = self.catalog.get_scope_for_page(page_uid)
        block = self.catalog.first_block_for_page(page_uid)
        probe = self._pick_probe_question(block, page)
        overview = self._build_page_overview(page)
        last_teacher_question = overview.choice_prompt if overview is not None else probe
        state = LessonRuntimeState(
            student_id=student_id,
            current_grade=scope.grade,
            current_semester=scope.semester,
            current_unit=scope.unit,
            current_page=_extract_page_number(page_uid),
            current_page_uid=page_uid,
            current_page_type=page.page_type,
            current_block_uid=block.block_uid,
            current_activity_type="page_entry",
            awaiting_answer=bool(last_teacher_question),
            last_teacher_question=last_teacher_question,
            page_entry_probe_done=overview is None,
            simplemem_content_session_id=f"lesson-{page_uid}-{uuid4().hex}",
        )
        state.push_turn_label("page_entry")
        self._ensure_memory_session(state=state, page=page, block=block)
        response = (
            overview.teacher_response
            if overview is not None
            else self._render_page_entry_response(
                page=page,
                block=block,
                probe=probe,
            )
        )
        response_focus = (
            "Give a concise page overview and ask the learner which module to start."
            if overview is not None
            else "Welcome the learner, explain the page, and ask the probe naturally."
        )
        response = self._respond_teacher_turn(
            learner_input="",
            turn_label="page_entry",
            decision=PlannerDecision(
                teaching_action="page_intro",
                retrieval_mode="none",
                response_focus=response_focus,
            ),
            state=state,
            page=page,
            block=block,
            fallback_response=response,
        )
        return LessonTurnResult(
            page_uid=page_uid,
            block_uid=block.block_uid,
            turn_label="page_entry",
            teaching_action="page_intro",
            retrieval_mode="none",
            teacher_response=response,
            state=state,
            debug_signals=self._build_debug_signals(
                state=state,
                retrieval_mode="none",
                turn_label="page_entry",
                teaching_action="page_intro",
            ),
        )

    def handle_turn(
        self,
        state: LessonRuntimeState,
        learner_input: str,
        requested_page_uid: str | None = None,
    ) -> LessonTurnResult:
        return self._run_turn_graph(
            {
                "page_uid": requested_page_uid or state.current_page_uid,
                "student_id": state.student_id,
                "state": state,
                "learner_input": learner_input,
                "requested_page_uid": requested_page_uid,
            }
        )

    def _run_turn_graph(self, graph_state: dict[str, Any]) -> LessonTurnResult:
        result = self.turn_graph.invoke(graph_state).get("result")
        if result is None:
            raise RuntimeError("Lesson turn graph completed without a result")
        result.state.push_turn_text(
            turn_label=result.turn_label,
            teacher_text=result.teacher_response,
            learner_text=graph_state.get("learner_input") or "",
        )
        return result

    def _handle_answer_turn(
        self,
        state: LessonRuntimeState,
        learner_input: str,
    ) -> LessonTurnResult:
        block = self.catalog.get_block(state.current_block_uid or "")
        page_overview_choice = self._handle_page_overview_choice_turn(
            state=state,
            learner_input=learner_input,
            current_block=block,
        )
        if page_overview_choice is not None:
            return page_overview_choice

        follow_up_prompt = self._follow_up_prompt_after_probe_echo(
            learner_input=learner_input,
            question=state.last_teacher_question,
            block=block,
        )
        if follow_up_prompt is not None:
            return self._handle_probe_echo_success(
                block=block,
                state=state,
                follow_up_prompt=follow_up_prompt,
            )
        answer_scope = self._evaluation_answer_scope(
            block,
            state.last_teacher_question,
        )
        evaluation = self._evaluate_learner_answer(
            learner_input=learner_input,
            block=block,
            question=state.last_teacher_question,
            answer_scope=answer_scope,
        )
        if self._should_interrupt_answer_turn(
            learner_input=learner_input,
            evaluation=evaluation,
            state=state,
            block=block,
        ):
            return self._handle_open_turn(state, learner_input)

        next_state = state.model_copy(deep=True)
        next_state.push_turn_label("answer_question")
        next_state.last_eval_result = evaluation

        if next_state.last_eval_result in {"correct", "acceptable"}:
            readiness = self._judge_answer_readiness(
                learner_input=learner_input,
                state=next_state,
                block=block,
                answer_scope=answer_scope,
                evaluation=evaluation,
            )
            if readiness is not None and not readiness.can_advance:
                return self._handle_readiness_stay(
                    block,
                    next_state,
                    learner_input=learner_input,
                    readiness=readiness,
                )
            return self._handle_success(block, next_state, learner_input=learner_input)
        return self._handle_difficulty(
            block,
            next_state,
            learner_input=learner_input,
        )

    def _handle_page_overview_choice_turn(
        self,
        *,
        state: LessonRuntimeState,
        learner_input: str,
        current_block: TeachingBlockRecord,
    ) -> LessonTurnResult | None:
        if state.current_activity_type != "page_entry":
            return None

        page = self.catalog.get_page(state.current_page_uid)
        overview = self._build_page_overview(page)
        if overview is None or not self.page_overview_skill.is_choice_prompt(
            state.last_teacher_question,
            overview,
        ):
            return None

        selected_module = self.page_overview_skill.match_choice(
            learner_input,
            overview,
        )
        next_state = state.model_copy(deep=True)
        next_state.push_turn_label("navigation")
        if selected_module is None:
            next_state.last_eval_result = "unclear"
            next_state.awaiting_answer = True
            next_state.last_teacher_question = overview.choice_prompt
            response = (
                f"我先把选择说清楚：可以选 {self._format_page_overview_choices(overview)}。"
                "你想先哪一块？"
            )
            response = self._respond_teacher_turn(
                learner_input=learner_input,
                turn_label="navigation",
                decision=PlannerDecision(
                    teaching_action="redirect",
                    retrieval_mode="none",
                    response_focus=(
                        "Clarify the page module choices without starting a drill."
                    ),
                ),
                state=next_state,
                page=page,
                block=current_block,
                fallback_response=response,
            )
            return LessonTurnResult(
                page_uid=next_state.current_page_uid,
                block_uid=current_block.block_uid,
                turn_label="navigation",
                teaching_action="redirect",
                retrieval_mode="none",
                teacher_response=response,
                state=next_state,
                evaluation=next_state.last_eval_result,
                debug_signals=self._build_debug_signals(
                    state=next_state,
                    retrieval_mode="none",
                    turn_label="navigation",
                    teaching_action="redirect",
                    evaluation=next_state.last_eval_result,
                    learner_turn=True,
                ),
            )

        selected_block_uid = selected_module.block_uids[0]
        selected_block = self.catalog.get_block(selected_block_uid)
        probe = self._pick_probe_question(selected_block, page)
        next_state.current_block_uid = selected_block.block_uid
        next_state.current_activity_type = "teaching"
        next_state.awaiting_answer = bool(probe)
        next_state.last_teacher_question = probe
        next_state.page_entry_probe_done = True
        next_state.last_eval_result = "acceptable"

        formatted_probe = self._render_probe_prompt(probe, selected_block)
        response = f"好，我们先从 {selected_module.label} 开始。{selected_module.summary}"
        if formatted_probe:
            response = f"{response} {formatted_probe}"
        response = self._respond_teacher_turn(
            learner_input=learner_input,
            turn_label="navigation",
            decision=PlannerDecision(
                teaching_action="probe",
                retrieval_mode="none",
                response_focus=(
                    "Confirm the selected page module and start its first tiny task."
                ),
            ),
            state=next_state,
            page=page,
            block=selected_block,
            fallback_response=response,
        )
        return LessonTurnResult(
            page_uid=next_state.current_page_uid,
            block_uid=selected_block.block_uid,
            turn_label="navigation",
            teaching_action="probe",
            retrieval_mode="none",
            teacher_response=response,
            state=next_state,
            evaluation=next_state.last_eval_result,
            debug_signals=self._build_debug_signals(
                state=next_state,
                retrieval_mode="none",
                turn_label="navigation",
                teaching_action="probe",
                evaluation=next_state.last_eval_result,
                learner_turn=True,
            ),
        )

    def _handle_probe_echo_success(
        self,
        *,
        block: TeachingBlockRecord,
        state: LessonRuntimeState,
        follow_up_prompt: str,
    ) -> LessonTurnResult:
        next_state = state.model_copy(deep=True)
        next_state.push_turn_label("answer_question")
        next_state.last_eval_result = "correct"
        next_state.same_goal_attempt_count = 0
        next_state.hint_level = 0
        next_state.pedagogy_level = 0
        next_state.model_already_given = False
        next_state.repair_mode = "none"
        next_state.current_activity_type = "practice"
        next_state.awaiting_answer = True
        next_state.last_teacher_question = follow_up_prompt

        prompt = self._render_probe_prompt(follow_up_prompt, block)
        response = (
            f"好，这句服务员的话会了。{prompt}"
            if prompt
            else "好，这句服务员的话会了，我们接着往下说。"
        )
        response = self._respond_teacher_turn(
            learner_input="",
            turn_label="answer_question",
            decision=PlannerDecision(
                teaching_action="confirm",
                retrieval_mode="none",
                response_focus=(
                    "Confirm the learner echoed the service question, then move"
                    " into one concrete answer turn."
                ),
            ),
            state=next_state,
            page=self.catalog.get_page(next_state.current_page_uid),
            block=block,
            fallback_response=response,
        )

        return LessonTurnResult(
            page_uid=next_state.current_page_uid,
            block_uid=block.block_uid,
            turn_label="answer_question",
            teaching_action="confirm",
            retrieval_mode="none",
            teacher_response=response,
            state=next_state,
            evaluation=next_state.last_eval_result,
            debug_signals=self._build_debug_signals(
                state=next_state,
                retrieval_mode="none",
                turn_label="answer_question",
                teaching_action="confirm",
                evaluation=next_state.last_eval_result,
                learner_turn=True,
            ),
        )

    def _handle_success(
        self,
        block: TeachingBlockRecord,
        state: LessonRuntimeState,
        *,
        learner_input: str = "",
    ) -> LessonTurnResult:
        state.same_goal_attempt_count = 0
        state.hint_level = 0
        state.pedagogy_level = 0
        state.model_already_given = False
        state.repair_mode = "none"
        state.current_activity_type = "teaching"

        if block.next_block_uids:
            next_block = self.catalog.get_block(block.next_block_uids[0])
            next_page = self.catalog.get_page(next_block.page_uid)
            probe = self._pick_probe_question(next_block, next_page)
            state.current_block_uid = next_block.block_uid
            state.awaiting_answer = bool(probe)
            state.last_teacher_question = probe
            formatted_probe = self._render_probe_prompt(probe, next_block)
            if self._block_has_task_instruction(block):
                response = (
                    "对了，这就是你自己的清单表达。我们继续："
                    if not formatted_probe
                    else f"对了，这就是你自己的清单表达。我们继续：{formatted_probe}"
                )
            else:
                response = (
                    "对了。我们继续："
                    if not formatted_probe
                    else f"对了。我们继续：{formatted_probe}"
                )
            next_block_uid = next_block.block_uid
            response_page = next_page
            response_block = next_block
        else:
            state.awaiting_answer = False
            state.last_teacher_question = None
            if self._block_has_task_instruction(block):
                response = "对了，这就是你自己的清单表达。这一页先收一下，我们接下一小题。"
            else:
                response = "对了，关键词你已经抓到了。这一页先收一下，我们接下一小题。"
            next_block_uid = block.block_uid
            response_page = self.catalog.get_page(state.current_page_uid)
            response_block = block

        response = self._respond_teacher_turn(
            learner_input=learner_input,
            turn_label="answer_question",
            decision=PlannerDecision(
                teaching_action="confirm",
                retrieval_mode="none",
                response_focus="Confirm the improvement clearly and move the lesson forward.",
            ),
            state=state,
            page=response_page,
            block=response_block,
            fallback_response=response,
        )

        return LessonTurnResult(
            page_uid=state.current_page_uid,
            block_uid=next_block_uid,
            turn_label="answer_question",
            teaching_action="confirm",
            retrieval_mode="none",
            teacher_response=response,
            state=state,
            evaluation=state.last_eval_result,
            debug_signals=self._build_debug_signals(
                state=state,
                retrieval_mode="none",
                turn_label="answer_question",
                teaching_action="confirm",
                evaluation=state.last_eval_result,
                learner_turn=True,
            ),
        )

    def _handle_readiness_stay(
        self,
        block: TeachingBlockRecord,
        state: LessonRuntimeState,
        *,
        learner_input: str,
        readiness: ReadinessJudgeResult,
    ) -> LessonTurnResult:
        del readiness
        return self._handle_difficulty(
            block,
            state,
            learner_input=learner_input,
        )

    def _handle_difficulty(
        self,
        block: TeachingBlockRecord,
        state: LessonRuntimeState,
        *,
        learner_input: str = "",
    ) -> LessonTurnResult:
        state.same_goal_attempt_count += 1
        state.current_activity_type = "practice"
        state.awaiting_answer = True
        use_full_target = self._prefer_full_answer_scaffold(
            state.last_teacher_question,
            self._best_model_answer(block, state.last_teacher_question),
        )
        target_answers = self._best_model_answers(
            block,
            state.last_teacher_question,
            limit=2 if use_full_target else 1,
        )
        target_answer = target_answers[0]
        answer_choices = self._format_answer_choices(target_answers)

        if state.same_goal_attempt_count == 1:
            state.hint_level = 1
            state.pedagogy_level = 0
            state.repair_mode = self._pick_repair_mode(block, "repeat", "word_drill")
            action = "hint"
            task_instruction_response = self._render_task_instruction_difficulty_response(
                block=block,
                state=state,
                learner_input=learner_input,
            )
            if task_instruction_response is not None:
                response = task_instruction_response
            elif use_full_target:
                if len(target_answers) > 1:
                    if self._is_scene_setup_prompt(state.last_teacher_question or ""):
                        response = f"差一点，我们把这句说完整。你可以选：{answer_choices}"
                    else:
                        response = f"先别急，跟老师选一句说：{answer_choices}"
                else:
                    if self._is_scene_setup_prompt(state.last_teacher_question or ""):
                        response = f"差一点，我们把这句说完整：{target_answer}"
                    else:
                        response = f"先别急，跟老师说一句：{target_answer}"
            else:
                response = f"先别急，我们先把这句开头带起来：{self._frame_sentence(target_answer)}"
        elif state.same_goal_attempt_count == 2:
            state.hint_level = 2
            state.pedagogy_level = 1
            state.repair_mode = self._pick_repair_mode(
                block,
                "sentence_drill",
                "word_drill",
            )
            action = "hint"
            if use_full_target:
                if len(target_answers) > 1:
                    if self._is_scene_setup_prompt(state.last_teacher_question or ""):
                        response = f"再补完整一点，直接选一句整句说：{answer_choices}"
                    else:
                        response = f"再完整一点，跟老师选一句完整地说：{answer_choices}"
                else:
                    if self._is_scene_setup_prompt(state.last_teacher_question or ""):
                        response = f"再补完整一点，直接说整句：{target_answer}"
                    else:
                        response = f"再完整一点，跟老师说一句：{target_answer}"
            else:
                response = f"再完整一点，先把这句说顺：{self._frame_sentence(target_answer)}"
        elif not state.model_already_given:
            state.pedagogy_level = 2
            state.model_already_given = True
            state.repair_mode = self._pick_repair_mode(
                block,
                "sentence_drill",
                "slow_read",
            )
            action = "model"
            response = f"我先示范一句：{target_answer} 你先听老师说一遍，再跟我读一遍。"
        else:
            state.pedagogy_level = 3
            state.repair_mode = self._pick_repair_mode(
                block,
                "sentence_drill",
                "slow_read",
                "word_drill",
            )
            action = "repeat_drill"
            response = f"我们拆小一点。先跟我读：{target_answer}。读完以后，不看老师，再自己完整说一遍。"

        response = self._respond_teacher_turn(
            learner_input=learner_input,
            turn_label="answer_question",
            decision=PlannerDecision(
                teaching_action=action,
                retrieval_mode="none",
                response_focus=(
                    "Keep the learner on one small target, correct clearly, and stay warm."
                ),
            ),
            state=state,
            page=self.catalog.get_page(state.current_page_uid),
            block=block,
            fallback_response=response,
        )

        return LessonTurnResult(
            page_uid=state.current_page_uid,
            block_uid=block.block_uid,
            turn_label="answer_question",
            teaching_action=action,
            retrieval_mode="none",
            teacher_response=response,
            state=state,
            evaluation=state.last_eval_result,
            debug_signals=self._build_debug_signals(
                state=state,
                retrieval_mode="none",
                turn_label="answer_question",
                teaching_action=action,
                evaluation=state.last_eval_result,
                learner_turn=True,
            ),
        )

    def _handle_open_turn(
        self,
        state: LessonRuntimeState,
        learner_input: str,
    ) -> LessonTurnResult:
        state = state.model_copy(deep=True)
        block = self.catalog.get_block(state.current_block_uid or "")
        page = self.catalog.get_page(state.current_page_uid)
        learner_memory, recall_status, recall_summary = self._lookup_learner_memory(
            learner_input=learner_input,
            state=state,
            block=block,
        )
        route_label = self._classify_open_turn(
            learner_input=learner_input,
            state=state,
            page=page,
            block=block,
            learner_memory=learner_memory,
        )

        if route_label == "ask_help":
            state.push_turn_label("ask_help")
            decision = self._plan_open_turn(
                turn_kind="ask_help",
                learner_input=learner_input,
                state=state,
                page=page,
                block=block,
                learner_memory=learner_memory,
                allowed_actions=["hint", "redirect"],
                allowed_modes=["none"],
                fallback=PlannerDecision(
                    teaching_action="hint",
                    retrieval_mode="none",
                    response_focus="Give a calm hint and keep the learner trying.",
                ),
            )
            response = self._render_help_response(
                decision=decision,
                block=block,
                page=page,
                learner_input=learner_input,
            )
            response = self._respond_open_turn(
                learner_input=learner_input,
                turn_label="ask_help",
                decision=decision,
                state=state,
                page=page,
                block=block,
                learner_memory=learner_memory,
                fallback_response=response,
            )
            return self._build_open_result(
                state,
                block,
                "ask_help",
                decision.teaching_action,
                decision.retrieval_mode,
                response,
                learner_memory=learner_memory,
                recall_status=recall_status,
                recall_summary=recall_summary,
            )

        if route_label == "ask_knowledge":
            state.push_turn_label("ask_knowledge")
            fallback_selection = self.retriever.select(
                current_page_uid=state.current_page_uid,
                current_block_uid=block.block_uid,
                query=learner_input,
            )
            decision = self._plan_knowledge_turn(
                learner_input=learner_input,
                state=state,
                page=page,
                block=block,
                learner_memory=learner_memory,
                fallback_selection=fallback_selection,
            )
            selection = self._select_mode_for_turn(
                current_page_uid=state.current_page_uid,
                current_block_uid=block.block_uid,
                query=learner_input,
                desired_mode=decision.retrieval_mode,
                fallback_selection=fallback_selection,
            )
            selection = self._merge_branch_metadata(
                selection=selection,
                block=block,
                decision=decision,
            )
            support_hits = self._lookup_support_hits(
                state=state,
                block=block,
                learner_input=learner_input,
                selection=selection,
            )
            fallback_response = self._render_knowledge_response(
                selection=selection,
                current_block=block,
                page=page,
                support_hits=support_hits,
                learner_input=learner_input,
                active_prompt=(
                    self._render_probe_prompt(state.last_teacher_question, block)
                    if state.awaiting_answer
                    else None
                ),
            )
            response = self._respond_open_turn(
                learner_input=learner_input,
                turn_label="ask_knowledge",
                decision=decision,
                state=state,
                page=page,
                block=block,
                learner_memory=learner_memory,
                fallback_response=fallback_response,
                selection=selection,
                support_hits=support_hits,
            )
            state.current_activity_type = "teaching"
            if selection.mode == "branch":
                state.branch_active = True
                state.branch_reason = decision.branch_reason or selection.branch_reason
                state.branch_origin_block_uid = block.block_uid
                state.branch_turn_budget = 2
                state.branch_resume_awaiting_answer = state.awaiting_answer
                state.awaiting_answer = False
                state.return_anchor = decision.return_anchor or selection.return_anchor
                state.return_target = block.block_uid
                state.current_activity_type = "branch"
            return self._build_open_result(
                state,
                block,
                "ask_knowledge",
                decision.teaching_action,
                selection.mode,
                response,
                retrieved_block_uids=selection.block_uids,
                support_entry_uids=[item.entry_uid for item in support_hits],
                return_anchor=decision.return_anchor or selection.return_anchor,
                branch_reason=decision.branch_reason or selection.branch_reason,
                learner_memory=learner_memory,
                recall_status=recall_status,
                recall_summary=recall_summary,
            )

        if state.branch_active and state.return_anchor:
            state.push_turn_label("social")
            planner_anchor = state.return_anchor
            decision = self._plan_open_turn(
                turn_kind="branch_close",
                learner_input=learner_input,
                state=state,
                page=page,
                block=block,
                learner_memory=learner_memory,
                allowed_actions=["redirect"],
                allowed_modes=["none"],
                fallback=PlannerDecision(
                    teaching_action="redirect",
                    retrieval_mode="none",
                    return_anchor=planner_anchor,
                    response_focus="Close the short branch and bridge back naturally.",
                ),
            )
            state.return_anchor = decision.return_anchor or planner_anchor
            state.branch_active = False
            state.current_activity_type = "teaching"
            state.branch_turn_budget = 0
            state.awaiting_answer = state.branch_resume_awaiting_answer
            state.branch_resume_awaiting_answer = False
            response = f"这个点我们先聊到这儿，顺着绕回本页：{state.return_anchor}"
            response = self._respond_open_turn(
                learner_input=learner_input,
                turn_label="social",
                decision=decision.model_copy(
                    update={"return_anchor": state.return_anchor}
                ),
                state=state,
                page=page,
                block=block,
                learner_memory=learner_memory,
                fallback_response=response,
                return_anchor=state.return_anchor,
            )
            return self._build_open_result(
                state,
                block,
                "social",
                decision.teaching_action,
                decision.retrieval_mode,
                response,
                return_anchor=state.return_anchor,
                learner_memory=learner_memory,
                recall_status=recall_status,
                recall_summary=recall_summary,
            )

        state.push_turn_label("social")
        prompt = self._render_probe_prompt(
            state.last_teacher_question or self._pick_probe_question(block, page),
            block,
        )
        decision = self._plan_open_turn(
            turn_kind="social_redirect",
            learner_input=learner_input,
            state=state,
            page=page,
            block=block,
            learner_memory=learner_memory,
            allowed_actions=["redirect"],
            allowed_modes=["none"],
            fallback=PlannerDecision(
                teaching_action="redirect",
                retrieval_mode="none",
                response_focus="Gently redirect the learner to the active page prompt.",
            ),
        )
        if self._block_has_task_instruction(block):
            response = (
                "好，我们拉回告别派对清单。"
                if not prompt
                else f"好，我们拉回告别派对清单：{prompt}"
            )
        else:
            response = "好，我们继续这一页。" if not prompt else f"好，我们继续这一页：{prompt}"
        response = self._respond_open_turn(
            learner_input=learner_input,
            turn_label="social",
            decision=decision,
            state=state,
            page=page,
            block=block,
            learner_memory=learner_memory,
            fallback_response=response,
        )
        return self._build_open_result(
            state,
            block,
            "social",
            decision.teaching_action,
            decision.retrieval_mode,
            response,
            learner_memory=learner_memory,
            recall_status=recall_status,
            recall_summary=recall_summary,
        )

    def _classify_open_turn(
        self,
        *,
        learner_input: str,
        state: LessonRuntimeState,
        page: PageLessonRecord,
        block: TeachingBlockRecord,
        learner_memory: LearnerMemorySummary,
    ) -> str:
        if self._looks_like_emotional_help_input(learner_input):
            return "ask_help"
        fallback_label = self._deterministic_open_turn_label(learner_input)
        if self.planner is None:
            return fallback_label
        decision = self.planner.classify_open_turn(
            learner_input=learner_input,
            state_snapshot=self._state_snapshot(state),
            page_snapshot=self._page_snapshot(page),
            block_snapshot=self._block_snapshot(block),
            learner_memory=learner_memory.to_prompt_payload(),
            allowed_turn_labels=["ask_help", "ask_knowledge", "social"],
            fallback=OpenTurnRouteDecision(turn_label=fallback_label),
        )
        if (
            self._looks_like_lexicon_query(learner_input)
            and decision.turn_label != "ask_knowledge"
        ):
            return "ask_knowledge"
        return decision.turn_label

    def _deterministic_open_turn_label(self, learner_input: str) -> str:
        lower = learner_input.casefold()
        if any(token in lower for token in _HELP_HINTS):
            return "ask_help"
        if any(token in lower for token in _EMOTION_HELP_HINTS):
            return "ask_help"
        if learner_input.endswith("?") or any(token in lower for token in _KNOWLEDGE_HINTS):
            return "ask_knowledge"
        return "social"

    def _should_interrupt_answer_turn(
        self,
        *,
        learner_input: str,
        evaluation: EvaluationResult,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
    ) -> bool:
        route_label = self._deterministic_open_turn_label(learner_input)
        if route_label in {"ask_help", "ask_knowledge"}:
            return True
        if evaluation == "off_topic":
            return True
        return self._looks_like_social_redirect_input(
            learner_input=learner_input,
            state=state,
            block=block,
        )

    def _looks_like_social_redirect_input(
        self,
        *,
        learner_input: str,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
    ) -> bool:
        learner_tokens = self._teacher_tokens(learner_input)
        if len(learner_tokens) < 2:
            return False

        lesson_tokens = self._teacher_tokens(state.last_teacher_question or "")
        for value in block.focus_vocabulary:
            lesson_tokens.update(self._teacher_tokens(value))
        for value in block.core_patterns:
            lesson_tokens.update(self._teacher_tokens(value))
        for value in self._evaluation_answer_scope(block, state.last_teacher_question):
            lesson_tokens.update(self._teacher_tokens(value))

        social_markers = {
            "yesterday",
            "today",
            "tomorrow",
            "weekend",
            "soccer",
            "football",
            "basketball",
            "school",
            "home",
            "friend",
            "played",
            "play",
            "went",
        }
        if learner_tokens & lesson_tokens:
            return False
        return bool(learner_tokens & social_markers)

    def _build_open_result(
        self,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
        turn_label: TurnLabel,
        teaching_action: TeachingAction,
        retrieval_mode: RetrievalMode,
        teacher_response: str,
        *,
        retrieved_block_uids: list[str] | None = None,
        support_entry_uids: list[str] | None = None,
        return_anchor: str | None = None,
        branch_reason: str | None = None,
        learner_memory: LearnerMemorySummary | None = None,
        recall_status: Literal["success", "skipped", "degraded"] | None = None,
        recall_summary: str | None = None,
    ) -> LessonTurnResult:
        return LessonTurnResult(
            page_uid=state.current_page_uid,
            block_uid=block.block_uid,
            turn_label=turn_label,
            teaching_action=teaching_action,
            retrieval_mode=retrieval_mode,
            teacher_response=teacher_response,
            state=state,
            retrieved_block_uids=retrieved_block_uids or [],
            support_entry_uids=support_entry_uids or [],
            return_anchor=return_anchor,
            branch_reason=branch_reason,
            debug_signals=self._build_debug_signals(
                state=state,
                retrieval_mode=retrieval_mode,
                turn_label=turn_label,
                teaching_action=teaching_action,
                evaluation=state.last_eval_result,
                learner_memory=learner_memory,
                recall_executed=True,
                learner_turn=True,
                recall_status_override=recall_status,
                recall_summary_override=recall_summary,
            ),
        )

    def _build_debug_signals(
        self,
        *,
        state: LessonRuntimeState,
        retrieval_mode: RetrievalMode,
        turn_label: str | None = None,
        teaching_action: str | None = None,
        evaluation: str | None = None,
        learner_memory: LearnerMemorySummary | None = None,
        recall_executed: bool = False,
        learner_turn: bool = False,
        recall_status_override: Literal["success", "skipped", "degraded"] | None = None,
        recall_summary_override: str | None = None,
    ) -> LessonTurnDebugSignals | None:
        if not self.debug_signals_enabled:
            return None

        learner_memory = learner_memory or LearnerMemorySummary(student_id="")
        vector_enabled = self._feature_enabled(
            "vector_retrieval",
            default=isinstance(self.retriever, ScopedRetriever) is False,
        )
        prompt_memory_enabled = self._feature_enabled(
            "prompt_injection",
            default=self.memory_provider is not None,
        )
        semantic_recall_enabled = self._feature_enabled(
            "semantic_recall",
            default=getattr(self.memory_provider, "semantic_recall_provider", None) is not None,
        )
        live_prompts_enabled = self._feature_enabled(
            "live_prompts",
            default=self.planner is not None or self.responder is not None,
        )
        return LessonTurnDebugSignals(
            live_prompts=LessonLivePromptsDebugSignal(
                enabled=live_prompts_enabled,
            ),
            vector_retrieval=LessonVectorRetrievalDebugSignal(
                enabled=vector_enabled,
                hit_modes=(
                    [retrieval_mode]
                    if vector_enabled and retrieval_mode in {"unit", "branch"}
                    else []
                ),
            ),
            prompt_memory=LessonPromptMemoryDebugSignal(
                enabled=prompt_memory_enabled,
                injected_buckets=self._prompt_memory_bucket_names(learner_memory)
                if prompt_memory_enabled
                else [],
            ),
            semantic_recall=LessonSemanticRecallDebugSignal(
                enabled=semantic_recall_enabled,
                recalled_memories=(
                    list(learner_memory.semantic_memories)
                    if semantic_recall_enabled
                    else []
                ),
            ),
            memory_runtime=self._build_memory_runtime_debug_signal(
                state=state,
                learner_memory=learner_memory,
                recall_executed=recall_executed,
                learner_turn=learner_turn,
                recall_status_override=recall_status_override,
                recall_summary_override=recall_summary_override,
            ),
            persona=self._build_persona_debug_signal(
                state=state,
                learner_memory=learner_memory,
                turn_label=turn_label,
                teaching_action=teaching_action,
                evaluation=evaluation,
            ),
        )

    def _build_persona_debug_signal(
        self,
        *,
        state: LessonRuntimeState,
        learner_memory: LearnerMemorySummary,
        turn_label: str | None,
        teaching_action: str | None,
        evaluation: str | None,
    ) -> LessonPersonaDebugSignal:
        persona_context = self._build_lesson_persona_context(
            state=state,
            learner_memory=learner_memory,
            turn_label=turn_label or self._last_debug_turn_label(state),
            teaching_action=teaching_action or "redirect",
            evaluation=evaluation,
        )
        profile = persona_context.profile
        relationship = persona_context.relationship
        return LessonPersonaDebugSignal(
            enabled=True,
            schema_version=persona_context.schema_version,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            display_name=profile.display_name,
            voice_hint=profile.voice_style.tts_voice_hint,
            allowed_to_shape=list(profile.boundaries.allowed_to_shape),
            protected_authorities=list(profile.boundaries.must_not_change),
            relationship_student_id=relationship.student_id,
            relationship_signals=list(relationship.relationship_signals),
            common_mistakes=list(relationship.common_mistakes),
            preferences=list(relationship.preferences),
            mastery_signals=list(relationship.mastery_signals),
            semantic_memories=list(relationship.semantic_memories),
            affect_state=persona_context.affect_state,
            airi_performance=persona_context.airi_performance,
        )

    def _build_lesson_persona_context(
        self,
        *,
        state: LessonRuntimeState,
        learner_memory: LearnerMemorySummary,
        turn_label: str,
        teaching_action: str,
        evaluation: str | None = None,
    ) -> LessonPersonaContext:
        return build_lesson_persona_context_for_turn(
            student_id=state.student_id,
            learner_memory=learner_memory,
            turn_label=turn_label,
            teaching_action=teaching_action,
            evaluation=evaluation if evaluation is not None else state.last_eval_result,
            same_goal_attempt_count=state.same_goal_attempt_count,
            repair_mode=state.repair_mode,
            recent_turn_labels=state.recent_turn_labels,
        )

    def _last_debug_turn_label(self, state: LessonRuntimeState) -> str:
        for label in reversed(state.recent_turn_labels):
            if label in {
                "page_entry",
                "answer_question",
                "ask_knowledge",
                "ask_help",
                "navigation",
                "social",
            }:
                return label
        return "social"

    def _build_memory_runtime_debug_signal(
        self,
        *,
        state: LessonRuntimeState,
        learner_memory: LearnerMemorySummary,
        recall_executed: bool,
        learner_turn: bool,
        recall_status_override: Literal["success", "skipped", "degraded"] | None = None,
        recall_summary_override: str | None = None,
    ) -> LessonMemoryRuntimeDebugSignal:
        prompt_memory_enabled = self._feature_enabled(
            "prompt_injection",
            default=self.memory_provider is not None,
        )
        writeback_enabled = self._feature_enabled(
            "writeback",
            default=self.memory_writer is not None,
        )

        if recall_status_override is not None:
            recall_status = recall_status_override
        elif not prompt_memory_enabled:
            recall_status = "skipped"
        elif recall_executed:
            recall_status = "success"
        else:
            recall_status = "skipped"

        if recall_summary_override is not None:
            recall_summary = recall_summary_override
        elif not prompt_memory_enabled:
            recall_summary = self._feature_reason(
                "prompt_injection",
                default="Backend prompt-memory recall is disabled or unavailable.",
            )
        elif recall_executed:
            recall_summary = self._render_memory_recall_summary(learner_memory)
        else:
            recall_summary = "This turn did not run learner-memory recall."

        if not writeback_enabled:
            writeback_status: Literal["success", "skipped", "degraded"] = "skipped"
            writeback_summary = self._feature_reason(
                "writeback",
                default="Backend learner-memory writeback is disabled or unavailable.",
            )
        elif state.simplemem_memory_session_id is None:
            writeback_status = "degraded"
            writeback_summary = "Backend memory session is unavailable; writeback cannot run."
        elif learner_turn:
            writeback_status = "skipped"
            writeback_summary = "Waiting for after-turn backend writeback."
        else:
            writeback_status = "skipped"
            writeback_summary = "No learner turn yet; backend writeback has not run."

        return LessonMemoryRuntimeDebugSignal(
            student_id=state.student_id,
            project=self._memory_project(),
            memory_session_id=state.simplemem_memory_session_id,
            last_recall_status=recall_status,
            last_recall_summary=recall_summary,
            last_writeback_status=writeback_status,
            last_writeback_summary=writeback_summary,
            degradation_state=self._resolve_memory_degradation_state(
                recall_status=recall_status,
                writeback_status=writeback_status,
                prompt_memory_enabled=prompt_memory_enabled,
                writeback_enabled=writeback_enabled,
                memory_session_id=state.simplemem_memory_session_id,
            ),
        )

    def _render_memory_recall_summary(
        self,
        learner_memory: LearnerMemorySummary,
    ) -> str:
        parts: list[str] = []
        injected_buckets = self._prompt_memory_bucket_names(learner_memory)
        if injected_buckets:
            parts.append(f"Injected buckets: {' / '.join(injected_buckets)}.")
        if learner_memory.semantic_memories:
            parts.append(f"Semantic hits: {len(learner_memory.semantic_memories)}.")
        if learner_memory.summary_text.strip():
            parts.append("Prompt summary available.")
        if not parts:
            return "Recall ran but did not inject stored learner memory."
        return " ".join(parts)

    def _resolve_memory_degradation_state(
        self,
        *,
        recall_status: Literal["success", "skipped", "degraded"],
        writeback_status: Literal["success", "skipped", "degraded"],
        prompt_memory_enabled: bool,
        writeback_enabled: bool,
        memory_session_id: str | None,
    ) -> Literal[
        "healthy",
        "idle",
        "memory_disabled",
        "session_degraded",
        "recall_degraded",
        "writeback_degraded",
        "recall_and_writeback_degraded",
    ]:
        if recall_status == "degraded" and writeback_status == "degraded":
            return "recall_and_writeback_degraded"
        if recall_status == "degraded":
            return "recall_degraded"
        if writeback_status == "degraded":
            return "session_degraded" if memory_session_id is None else "writeback_degraded"
        if not prompt_memory_enabled or not writeback_enabled:
            return "memory_disabled"
        if recall_status == "skipped" and writeback_status == "skipped":
            return "idle"
        return "healthy"

    def _memory_project(self) -> str:
        for source in (self.memory_writer, self.memory_provider):
            project = getattr(source, "project", None)
            if isinstance(project, str) and project.strip():
                return project.strip()

        env_project = os.getenv("PEPTUTOR_SIMPLEMEM_PROJECT", "").strip()
        return env_project or "peptutor-lesson"

    def _feature_reason(self, feature_key: str, *, default: str) -> str:
        status = self.feature_statuses.get(feature_key)
        reason = getattr(status, "reason", None)
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
        return default

    def _update_result_memory_writeback_debug(
        self,
        result: LessonTurnResult,
        *,
        status: Literal["success", "skipped", "degraded"],
        summary: str,
    ) -> None:
        if not self.debug_signals_enabled or result.debug_signals is None:
            return

        memory_runtime = result.debug_signals.memory_runtime
        memory_runtime.memory_session_id = result.state.simplemem_memory_session_id
        memory_runtime.last_writeback_status = status
        memory_runtime.last_writeback_summary = summary
        memory_runtime.degradation_state = self._resolve_memory_degradation_state(
            recall_status=memory_runtime.last_recall_status,
            writeback_status=status,
            prompt_memory_enabled=self._feature_enabled(
                "prompt_injection",
                default=self.memory_provider is not None,
            ),
            writeback_enabled=self._feature_enabled(
                "writeback",
                default=self.memory_writer is not None,
            ),
            memory_session_id=result.state.simplemem_memory_session_id,
        )

    def _prompt_memory_bucket_names(
        self,
        learner_memory: LearnerMemorySummary,
    ) -> list[str]:
        bucket_map = [
            ("common_mistakes", learner_memory.common_mistakes),
            ("preferences", learner_memory.preferences),
            ("mastery_signals", learner_memory.mastery_signals),
            ("stable_common_mistakes", learner_memory.stable_common_mistakes),
            ("stable_preferences", learner_memory.stable_preferences),
            ("stable_mastery_signals", learner_memory.stable_mastery_signals),
        ]
        return [
            bucket_name
            for bucket_name, values in bucket_map
            if values
        ]

    def _feature_enabled(self, feature_key: str, *, default: bool) -> bool:
        status = self.feature_statuses.get(feature_key)
        if status is None:
            return default
        enabled = getattr(status, "enabled", status)
        return bool(enabled)

    def _render_retrieval_response(
        self,
        selection,
        current_block: TeachingBlockRecord,
        *,
        query: str | None = None,
        support_hits: list[SupportMatch] | None = None,
    ) -> str:
        query_text = query or ""
        support_prefix = self._render_support_prefix(support_hits or [])
        if not selection.block_uids:
            base = (
                "先贴着当前这一块理解。"
                f"先抓这句：{self._best_model_answer(current_block, query_text)}"
            )
            return f"{support_prefix}。{base}" if support_prefix else base

        top_block = self.catalog.get_block(selection.block_uids[0])
        if selection.mode == "block":
            base = (
                "先贴着当前这一块理解。"
                f"先抓这句：{self._best_model_answer(top_block, query_text)}"
            )
            return f"{support_prefix}。{base}" if support_prefix else base
        if selection.mode == "page":
            base = f"这页里相关的是这句：{self._best_model_answer(top_block, query_text)}"
            return f"{support_prefix}。{base}" if support_prefix else base
        if selection.mode == "unit":
            base = f"这个点在本单元里还能连到这句：{self._best_model_answer(top_block, query_text)}"
            return f"{support_prefix}。{base}" if support_prefix else base
        if selection.mode == "branch":
            anchor = selection.return_anchor or self._best_model_answer(current_block, query_text)
            base = (
                "这个问题可以短聊一下。"
                f"比如这句：{self._best_model_answer(top_block, query_text)} "
                f"等会儿我们再绕回：{anchor}"
            )
            return f"{support_prefix}。{base}" if support_prefix else base
        base = f"先贴着当前这一块理解。先抓这句：{self._best_model_answer(top_block, query_text)}"
        return f"{support_prefix}。{base}" if support_prefix else base

    def _render_knowledge_response(
        self,
        *,
        selection,
        current_block: TeachingBlockRecord,
        page: PageLessonRecord,
        support_hits: list[SupportMatch],
        learner_input: str,
        active_prompt: str | None = None,
    ) -> str:
        if selection.mode == "none":
            prompt = active_prompt or self._render_probe_prompt(
                self._pick_probe_question(current_block, page),
                current_block,
            )
            if prompt:
                return f"这个问题我们先轻轻放一下，先回到这一页：{prompt}"
            return "这个问题我们先轻轻放一下，先回到这一页的重点。"
        response = self._render_retrieval_response(
            selection,
            current_block,
            query=learner_input,
            support_hits=support_hits,
        )
        if active_prompt and selection.mode != "branch":
            return f"{response} 现在先回到刚才这句：{active_prompt}"
        return response

    def _lookup_support_hits(
        self,
        *,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
        learner_input: str,
        selection,
    ) -> list[SupportMatch]:
        if self.support_retriever is None:
            return []
        if selection.mode not in {"block", "page", "unit", "branch"}:
            return []
        return self.support_retriever.search(
            current_page_uid=state.current_page_uid,
            current_block_uid=block.block_uid,
            selection=selection,
            query=learner_input,
        )

    def _render_support_prefix(self, support_hits: list[SupportMatch]) -> str | None:
        if not support_hits:
            return None
        top = support_hits[0]
        if top.entry_kind == "lexicon":
            if top.phonetic:
                return f"{top.english} 是“{top.chinese}”，读音 {top.phonetic}"
            return f"{top.english} 是“{top.chinese}”"
        return f"{top.english} 可以理解为“{top.chinese}”"

    def _plan_knowledge_turn(
        self,
        *,
        learner_input: str,
        state: LessonRuntimeState,
        page: PageLessonRecord,
        block: TeachingBlockRecord,
        learner_memory: LearnerMemorySummary,
        fallback_selection,
    ) -> PlannerDecision:
        fallback = PlannerDecision(
            teaching_action="explain",
            retrieval_mode=fallback_selection.mode,
            branch_reason=fallback_selection.branch_reason,
            return_anchor=fallback_selection.return_anchor,
            response_focus="Answer briefly, stay lively, and keep the lesson on track.",
        )
        if self.planner is None:
            return fallback
        return self.planner.plan_knowledge_turn(
            learner_input=learner_input,
            state_snapshot=self._state_snapshot(state),
            page_snapshot=self._page_snapshot(page),
            block_snapshot=self._block_snapshot(block),
            learner_memory=learner_memory.to_prompt_payload(),
            allowed_actions=["explain", "redirect"],
            allowed_modes=["none", "block", "page", "unit", "branch"],
            fallback=fallback,
        )

    def _plan_open_turn(
        self,
        *,
        turn_kind: str,
        learner_input: str,
        state: LessonRuntimeState,
        page: PageLessonRecord,
        block: TeachingBlockRecord,
        learner_memory: LearnerMemorySummary,
        allowed_actions: list[TeachingAction],
        allowed_modes: list[RetrievalMode],
        fallback: PlannerDecision,
    ) -> PlannerDecision:
        if self.planner is None:
            return fallback
        return self.planner.plan_turn(
            turn_kind=turn_kind,
            learner_input=learner_input,
            state_snapshot=self._state_snapshot(state),
            page_snapshot=self._page_snapshot(page),
            block_snapshot=self._block_snapshot(block),
            learner_memory=learner_memory.to_prompt_payload(),
            allowed_actions=allowed_actions,
            allowed_modes=allowed_modes,
            fallback=fallback,
        )

    def _select_mode_for_turn(
        self,
        *,
        current_page_uid: str,
        current_block_uid: str,
        query: str,
        desired_mode: RetrievalMode,
        fallback_selection,
    ):
        if desired_mode == fallback_selection.mode:
            return fallback_selection
        if fallback_selection.mode == "branch" and desired_mode != "branch":
            return fallback_selection
        if (
            self._looks_like_lexicon_query(query)
            and fallback_selection.mode in {"page", "unit"}
            and desired_mode != fallback_selection.mode
        ):
            return fallback_selection
        select_mode = getattr(self.retriever, "select_mode", None)
        if select_mode is None:
            return fallback_selection
        try:
            return select_mode(
                current_page_uid=current_page_uid,
                current_block_uid=current_block_uid,
                query=query,
                mode=desired_mode,
            )
        except Exception:
            return fallback_selection

    def _merge_branch_metadata(
        self,
        *,
        selection,
        block: TeachingBlockRecord,
        decision: PlannerDecision,
    ):
        if selection.mode != "branch":
            return selection
        anchor = decision.return_anchor or selection.return_anchor
        if not anchor and block.return_anchors:
            anchor = block.return_anchors[0]
        branch_reason = decision.branch_reason or selection.branch_reason
        return selection.model_copy(
            update={
                "return_anchor": anchor,
                "branch_reason": branch_reason,
            }
        )

    def _respond_open_turn(
        self,
        *,
        learner_input: str,
        turn_label: TurnLabel,
        decision: PlannerDecision,
        state: LessonRuntimeState,
        page: PageLessonRecord,
        block: TeachingBlockRecord,
        learner_memory: LearnerMemorySummary,
        fallback_response: str,
        selection=None,
        support_hits: list[SupportMatch] | None = None,
        return_anchor: str | None = None,
    ) -> str:
        return self._respond_teacher_turn(
            learner_input=learner_input,
            turn_label=turn_label,
            decision=decision,
            state=state,
            page=page,
            block=block,
            learner_memory=learner_memory,
            fallback_response=fallback_response,
            selection=selection,
            support_hits=support_hits,
            return_anchor=return_anchor,
        )

    def _respond_teacher_turn(
        self,
        *,
        learner_input: str,
        turn_label: TurnLabel,
        decision: PlannerDecision,
        state: LessonRuntimeState,
        page: PageLessonRecord,
        block: TeachingBlockRecord,
        learner_memory: LearnerMemorySummary | None = None,
        fallback_response: str,
        selection=None,
        support_hits: list[SupportMatch] | None = None,
        return_anchor: str | None = None,
    ) -> str:
        stream_sink = _ACTIVE_TEACHER_RESPONSE_STREAM.get()
        effective_anchor = return_anchor or decision.return_anchor
        if effective_anchor is None and selection is not None:
            effective_anchor = selection.return_anchor
        effective_memory = learner_memory or LearnerMemorySummary(
            student_id=state.student_id
        )
        memory_payload = effective_memory.to_prompt_payload()
        persona_context_model = self._build_lesson_persona_context(
            state=state,
            learner_memory=effective_memory,
            turn_label=turn_label,
            teaching_action=decision.teaching_action,
        )
        persona_context = persona_context_model.model_dump()
        lesson_evidence_model = self.evidence_lookup.lookup(
            page_uid=page.page_uid,
            block_uid=block.block_uid,
        )
        lesson_brief_model = self.brief_builder.build(
            lesson_evidence=lesson_evidence_model,
            learner_input=learner_input,
            turn_label=turn_label,
            decision=decision,
            state=state,
        )
        teaching_move_model = self.teaching_move_planner.plan(
            lesson_brief=lesson_brief_model,
            learner_input=learner_input,
            turn_label=turn_label,
            decision=decision,
            state=state,
        )
        lesson_brief = lesson_brief_model.to_prompt_payload()
        lesson_evidence = lesson_evidence_model.to_prompt_payload()
        teaching_move = teaching_move_model.to_prompt_payload()
        retrieval_evidence = self._retrieval_evidence(selection)
        support_evidence = self._support_evidence(support_hits or [])
        has_rag_context = bool(retrieval_evidence or support_evidence)
        prompt_path = (
            "rag_plus_llm"
            if self.responder is not None and has_rag_context
            else "llm_only"
            if self.responder is not None
            else "rag_only"
            if has_rag_context
            else "deterministic_only"
        )
        logger.info(
            "Lesson turn audit path=%s turn_label=%s page_uid=%s block_uid=%s teaching_action=%s retrieval_mode=%s retrieval_evidence=%d support_evidence=%d responder_llm=%s stream=%s fallback_chars=%d",
            prompt_path,
            turn_label,
            page.page_uid,
            block.block_uid,
            decision.teaching_action,
            decision.retrieval_mode,
            len(retrieval_evidence),
            len(support_evidence),
            self.responder is not None,
            stream_sink is not None,
            len(fallback_response),
        )
        if stream_sink is not None:
            stream_sink.emit_action_metadata(
                teaching_action=decision.teaching_action,
                evaluation=state.last_eval_result,
                branch_active=state.branch_active or decision.retrieval_mode == "branch",
                turn_label=turn_label,
                airi_performance=persona_context["airi_performance"],
            )
        if self.responder is None:
            if stream_sink is not None:
                stream_sink.emit_text_delta(fallback_response)
            return fallback_response
        page_snapshot = self._page_snapshot_for_turn(page=page, turn_label=turn_label)
        state_snapshot = self._state_snapshot(state)
        block_snapshot = self._block_snapshot(block)
        if stream_sink is not None:
            return self.responder.render_teacher_turn_stream(
                learner_input=learner_input,
                turn_label=turn_label,
                decision=decision,
                state_snapshot=state_snapshot,
                page_snapshot=page_snapshot,
                block_snapshot=block_snapshot,
                learner_memory=memory_payload,
                retrieval_evidence=retrieval_evidence,
                support_evidence=support_evidence,
                return_anchor=effective_anchor,
                fallback_response=fallback_response,
                on_delta=stream_sink.emit_text_delta,
                persona_context=persona_context,
                lesson_brief=lesson_brief,
                lesson_evidence=lesson_evidence,
                teaching_move=teaching_move,
            )
        return self.responder.render_teacher_turn(
            learner_input=learner_input,
            turn_label=turn_label,
            decision=decision,
            state_snapshot=state_snapshot,
            page_snapshot=page_snapshot,
            block_snapshot=block_snapshot,
            learner_memory=memory_payload,
            retrieval_evidence=retrieval_evidence,
            support_evidence=support_evidence,
            return_anchor=effective_anchor,
            fallback_response=fallback_response,
            persona_context=persona_context,
            lesson_brief=lesson_brief,
            lesson_evidence=lesson_evidence,
            teaching_move=teaching_move,
        )

    def _lookup_learner_memory(
        self,
        *,
        learner_input: str,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
    ) -> tuple[LearnerMemorySummary, Literal["success", "skipped", "degraded"], str]:
        if self.memory_provider is None:
            return (
                LearnerMemorySummary(student_id=state.student_id),
                "skipped",
                self._feature_reason(
                    "prompt_injection",
                    default="Backend prompt-memory recall is disabled or unavailable.",
                ),
            )
        try:
            summary = self.memory_provider.get_summary(
                student_id=state.student_id,
                learner_input=learner_input,
                state_snapshot=self._state_snapshot(state),
                block_snapshot=self._block_snapshot(block),
                exclude_memory_session_id=state.simplemem_memory_session_id,
            )
            return (
                summary,
                "success",
                self._render_memory_recall_summary(summary),
            )
        except Exception as exc:
            logger.warning("Learner memory lookup failed, continuing without injection: %s", exc)
            return (
                LearnerMemorySummary(student_id=state.student_id),
                "degraded",
                "Learner-memory recall failed; continuing without backend injection.",
            )

    def _ensure_memory_session(
        self,
        *,
        state: LessonRuntimeState,
        page: PageLessonRecord,
        block: TeachingBlockRecord,
    ) -> None:
        if self.memory_writer is None:
            return
        if state.simplemem_content_session_id is None:
            state.simplemem_content_session_id = f"lesson-{page.page_uid}-{uuid4().hex}"
        if state.simplemem_memory_session_id is not None:
            return
        try:
            state.simplemem_memory_session_id = self.memory_writer.ensure_session(
                student_id=state.student_id,
                content_session_id=state.simplemem_content_session_id,
                page=page,
                block=block,
            )
        except Exception as exc:
            logger.warning("SimpleMem writeback session setup failed: %s", exc)
            state.simplemem_memory_session_id = None

    def _write_memory_trace(
        self,
        *,
        prior_state: LessonRuntimeState,
        learner_input: str,
        result: LessonTurnResult,
    ) -> None:
        if self.memory_writer is None:
            return
        page = self.catalog.get_page(prior_state.current_page_uid)
        block = self.catalog.get_block(prior_state.current_block_uid or "")
        self._ensure_memory_session(state=result.state, page=page, block=block)
        if (
            result.state.simplemem_content_session_id is None
            or result.state.simplemem_memory_session_id is None
        ):
            self._update_result_memory_writeback_debug(
                result,
                status="degraded",
                summary="Backend memory session is unavailable; writeback could not persist this turn.",
            )
            return
        try:
            self.memory_writer.record_turn(
                student_id=result.state.student_id,
                content_session_id=result.state.simplemem_content_session_id,
                memory_session_id=result.state.simplemem_memory_session_id,
                learner_input=learner_input,
                prior_state=prior_state,
                result=result,
                page=page,
                block=block,
            )
            self._update_result_memory_writeback_debug(
                result,
                status="success",
                summary="Recorded learner turn in backend memory.",
            )
        except Exception as exc:
            logger.warning("SimpleMem lesson trace writeback failed: %s", exc)
            self._update_result_memory_writeback_debug(
                result,
                status="degraded",
                summary="Backend learner-memory writeback failed for this turn.",
            )

    def _should_summarize_page_session(
        self,
        *,
        prior_state: LessonRuntimeState,
        result: LessonTurnResult,
    ) -> bool:
        if result.turn_label != "answer_question":
            return False
        if result.teaching_action != "confirm":
            return False
        if result.evaluation not in {"correct", "acceptable"}:
            return False
        if result.state.awaiting_answer:
            return False
        previous_block = self.catalog.get_block(prior_state.current_block_uid or "")
        return not previous_block.next_block_uids

    def _persist_page_summary(self, state: LessonRuntimeState) -> None:
        if self.memory_writer is None or state.simplemem_memory_session_id is None:
            return
        page = self.catalog.get_page(state.current_page_uid)
        try:
            self.memory_writer.summarize_session(
                memory_session_id=state.simplemem_memory_session_id,
                page=page,
                state=state,
            )
        except Exception as exc:
            logger.warning("SimpleMem lesson summary writeback failed: %s", exc)

    def _persist_page_summary_and_finalize(self, state: LessonRuntimeState) -> None:
        if self.memory_writer is None or state.simplemem_memory_session_id is None:
            return
        self._persist_page_summary(state)
        try:
            self.memory_writer.finalize_session(
                memory_session_id=state.simplemem_memory_session_id,
            )
        except Exception as exc:
            logger.warning("SimpleMem lesson session finalization failed: %s", exc)

    def _state_snapshot(self, state: LessonRuntimeState) -> dict[str, Any]:
        return {
            "current_page_uid": state.current_page_uid,
            "current_block_uid": state.current_block_uid,
            "current_activity_type": state.current_activity_type,
            "awaiting_answer": state.awaiting_answer,
            "hint_level": state.hint_level,
            "pedagogy_level": state.pedagogy_level,
            "branch_active": state.branch_active,
            "branch_reason": state.branch_reason,
            "return_anchor": state.return_anchor,
            "recent_turn_labels": state.recent_turn_labels,
        }

    def _build_current_turn_lesson_brief(
        self,
        *,
        learner_input: str,
        turn_label: TurnLabel,
        decision: PlannerDecision,
        state: LessonRuntimeState,
        page: PageLessonRecord,
        block: TeachingBlockRecord,
    ) -> CurrentTurnLessonBrief:
        lesson_evidence = self.evidence_lookup.lookup(
            page_uid=page.page_uid,
            block_uid=block.block_uid,
        )
        return self.brief_builder.build(
            lesson_evidence=lesson_evidence,
            learner_input=learner_input,
            turn_label=turn_label,
            decision=decision,
            state=state,
        )

    def _safe_lesson_title(
        self,
        page: PageLessonRecord,
        block: TeachingBlockRecord,
    ) -> str:
        if "farewell party" in (page.page_intro_cn + block.teaching_summary).casefold():
            return "Farewell party shopping list"
        return page.page_type

    def _target_language_for_brief(self, block: TeachingBlockRecord) -> list[str]:
        values = [
            value
            for value in [*block.core_patterns, *block.focus_vocabulary]
            if value and not self._looks_like_task_instruction(value)
        ]
        if values:
            return values[:8]
        examples = self._page_answer_examples(block.page_uid, limit=8)
        return examples[:8]

    def _expected_answer_shape_for_brief(self, block: TeachingBlockRecord) -> str:
        if self._block_has_task_instruction(block):
            return (
                "A concrete party-list item or a short first-person list sentence, "
                "for example: cake / orange juice / I'm going to bring cake."
            )
        if block.allowed_answer_scope:
            return "One answer that fits the current block's allowed answer scope."
        return "A short lesson-aware learner response."

    def _progression_condition_for_brief(self, block: TeachingBlockRecord) -> str:
        if self._block_has_task_instruction(block):
            return (
                "Advance only after the learner gives their own concrete party-list item "
                "or a clear item-list sentence; do not advance on the task instruction itself."
            )
        return "Advance only when the active answer rubric is correct or acceptable."

    def _misconception_map_for_brief(
        self,
        *,
        learner_input: str,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
    ) -> list[LessonBriefMisconceptionHint]:
        if not self._block_has_task_instruction(block):
            return []
        normalized_input = normalize_text(learner_input)
        task_literals = {
            normalize_text(candidate)
            for candidate in [
                *self._probe_literal_candidates(state.last_teacher_question),
                *block.core_patterns,
                *block.allowed_answer_scope,
            ]
            if self._looks_like_task_instruction(candidate)
        }
        if normalized_input in task_literals:
            return [
                LessonBriefMisconceptionHint(
                    likely_error="task_instruction_echo",
                    repair_move="Tell the learner that the sentence is the task, then ask for one item.",
                    scaffold_example="cake",
                )
            ]
        if state.last_eval_result == "partially_correct":
            return [
                LessonBriefMisconceptionHint(
                    likely_error="rough_item_sentence",
                    repair_move="Lightly remodel the sentence without a grammar lecture.",
                    scaffold_example="I'm going to bring an apple.",
                )
            ]
        if state.last_eval_result in {"unclear", "incorrect"}:
            return [
                LessonBriefMisconceptionHint(
                    likely_error="low_confidence_or_no_concrete_item",
                    repair_move="Lower pressure and offer one tiny item-level entry point.",
                    scaffold_example="cake",
                )
            ]
        return []

    def _page_snapshot(self, page: PageLessonRecord) -> dict[str, Any]:
        return {
            "page_uid": page.page_uid,
            "page_type": page.page_type,
            "page_intro_cn": page.page_intro_cn,
            "entry_probe_questions": page.entry_probe_questions,
            "priority_blocks": page.priority_blocks,
        }

    def _page_snapshot_for_turn(
        self,
        *,
        page: PageLessonRecord,
        turn_label: TurnLabel,
    ) -> dict[str, Any]:
        snapshot = self._page_snapshot(page)
        if turn_label == "page_entry":
            overview = self._build_page_overview(page)
            if overview is not None:
                snapshot["page_overview"] = overview.to_prompt_payload()
        return snapshot

    def _build_page_overview(self, page: PageLessonRecord) -> PageOverview | None:
        return self.page_overview_skill.build(
            page=page,
            blocks=self.catalog.blocks_for_page(page.page_uid),
        )

    def _format_page_overview_choices(self, overview: PageOverview) -> str:
        labels = [module.label for module in overview.modules]
        if len(labels) == 2:
            return f"{labels[0]} 或 {labels[1]}"
        return "、".join(labels[:-1]) + f" 或 {labels[-1]}"

    def _block_snapshot(self, block: TeachingBlockRecord) -> dict[str, Any]:
        return {
            "block_uid": block.block_uid,
            "page_uid": block.page_uid,
            "block_type": block.block_type,
            "teaching_goal": block.teaching_goal,
            "teaching_summary": block.teaching_summary,
            "focus_vocabulary": block.focus_vocabulary,
            "core_patterns": block.core_patterns,
            "allowed_answer_scope": block.allowed_answer_scope,
            "repair_modes": block.repair_modes,
            "branchable_topics": block.branchable_topics,
            "return_anchors": block.return_anchors,
        }

    def _retrieval_evidence(self, selection) -> list[dict[str, str]]:
        if selection is None or not getattr(selection, "block_uids", None):
            return []
        result: list[dict[str, str]] = []
        for block_uid in selection.block_uids:
            block = self.catalog.get_block(block_uid)
            result.append(
                {
                    "block_uid": block.block_uid,
                    "block_type": block.block_type,
                    "teaching_summary": block.teaching_summary,
                    "model_answer": self._best_model_answer(block),
                }
            )
        return result

    def _support_evidence(self, support_hits: list[SupportMatch]) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for hit in support_hits:
            item = {
                "entry_uid": hit.entry_uid,
                "entry_kind": hit.entry_kind,
                "english": hit.english,
                "chinese": hit.chinese,
            }
            if hit.phonetic:
                item["phonetic"] = hit.phonetic
            result.append(item)
        return result

    def _render_help_response(
        self,
        *,
        decision: PlannerDecision,
        block: TeachingBlockRecord,
        page: PageLessonRecord,
        learner_input: str,
    ) -> str:
        raw_prompt = self._pick_probe_question(block, page)
        prompt = self._render_probe_prompt(raw_prompt, block)
        if decision.teaching_action == "redirect":
            if prompt:
                return f"我们先回到这一页：{prompt}"
            return "我们先回到这一页的重点。"
        target = self._best_model_answer(block, raw_prompt)
        target_answers = self._best_model_answers(
            block,
            raw_prompt,
            limit=2 if self._prefer_full_answer_scaffold(prompt, target) else 1,
        )
        prefix = "先别急，我们慢慢来。"
        if not self._looks_like_emotional_help_input(learner_input):
            prefix = "没关系，"
        if prompt:
            return self._render_help_scaffold(
                prompt,
                target,
                target_answers,
                prefix=prefix,
            )
        return f"{prefix}我们先拆小一点。{self._frame_sentence(target)}"

    def _render_help_scaffold(
        self,
        prompt: str,
        target: str,
        target_answers: list[str] | None = None,
        *,
        prefix: str = "没关系，",
    ) -> str:
        if any(token in prompt for token in ("完整的话", "完整句", "热个身")):
            if "hungry" in target.casefold():
                return f"{prefix}假设你饿了，跟老师说一句：{target}"
            return f"{prefix}我们先用完整句说出来：{target}"
        if "假设你饿了" in prompt and "hungry" in target.casefold():
            return f"{prefix}假设你饿了，跟老师说一句：{target}"
        if self._is_service_question_text(target):
            return (
                f"{prefix}这句是服务员在问你。我们慢慢来："
                f"{self._chunk_sentence(target)}。再完整说一遍：{target}"
            )
        if self._is_scene_setup_prompt(prompt):
            if self._prefer_full_answer_scaffold(prompt, target):
                answer_choices = self._format_answer_choices(target_answers or [target])
                if len(target_answers or []) > 1:
                    return f"{prefix}我们只把这句说完整。你可以选：{answer_choices}"
                return f"{prefix}我们只把这句说完整：{target}"
            return f"{prefix}我们先把这句补完整：{self._frame_sentence(target)}"
        if any(token in prompt for token in ("认不认识", "这个词", "读一读")):
            return f"{prefix}我们先跟老师读一读这个词：{target}"
        if any(token in prompt for token in ("跟老师读一遍", "试着说一遍", "跟着我说一遍")):
            return f"{prefix}我们先跟老师读一遍：{target}"
        if any(token in prompt for token in ("怎么答", "怎么回答", "顾客", "点餐", "口渴", "想点吃的", "说一句", "选一句说")):
            if self._prefer_full_answer_scaffold(prompt, target):
                answer_choices = self._format_answer_choices(target_answers or [target])
                if len(target_answers or []) > 1:
                    return f"{prefix}先跟老师选一句说：{answer_choices}"
                return f"{prefix}先跟老师说一句：{target}"
            return f"{prefix}先套这个句型说：{self._frame_sentence(target)}"
        return f"{prefix}我们先拆小一点。{self._frame_sentence(target)}"

    def _render_task_instruction_difficulty_response(
        self,
        *,
        block: TeachingBlockRecord,
        state: LessonRuntimeState,
        learner_input: str,
    ) -> str | None:
        if not self._block_has_task_instruction(block):
            return None
        examples = self._page_answer_examples(block.page_uid, limit=4)
        first = examples[0] if examples else "cake"
        second = examples[1] if len(examples) > 1 else "orange juice"
        normalized_input = normalize_text(learner_input)
        task_literals = {
            normalize_text(candidate)
            for candidate in [
                *self._probe_literal_candidates(state.last_teacher_question),
                *block.core_patterns,
                *block.allowed_answer_scope,
            ]
            if self._looks_like_task_instruction(candidate)
        }
        if normalized_input in task_literals:
            return (
                "这句是任务说明，还不是你的清单。你换成一个东西就行，"
                f"比如 {first}。"
            )
        if state.last_eval_result == "partially_correct":
            if "apple" in learner_input.casefold():
                return "意思对了，我们把句子说顺：I'm going to bring an apple. 你再试一次。"
            return f"意思对了，我们把句子说顺：I'm going to bring {first}. 你再试一次。"
        if state.last_eval_result == "off_topic":
            return f"我们先拉回告别派对清单。你可以只说一个东西，比如 {first} 或 {second}。"
        return f"没关系，我们先说最小的一步。你可以只说一个词，比如 {first}。"

    def _render_page_entry_response(
        self,
        *,
        page: PageLessonRecord,
        block: TeachingBlockRecord,
        probe: str | None,
    ) -> str:
        intro = page.page_intro_cn.strip()
        if not self._contains_cjk(intro) or self._looks_like_curriculum_intro(intro):
            intro = self._fallback_page_intro(page, block)
        prompt = self._render_probe_prompt(probe, block)
        if prompt:
            return f"{intro} {prompt}"
        return intro

    def _fallback_page_intro(
        self,
        page: PageLessonRecord,
        block: TeachingBlockRecord,
    ) -> str:
        key_patterns = [pattern for pattern in block.core_patterns[:2] if pattern]
        key_words = [word for word in block.focus_vocabulary[:3] if word]
        page_type = page.page_type.casefold()

        if block.block_type == "extension_task":
            return "这一页我们把前面学过的词用起来，先做一个小表达任务。"

        if page_type == "dialogue":
            if len(key_patterns) >= 2:
                return (
                    f"这一页我们练习点餐和饮料表达，先抓两个关键句型："
                    f"{key_patterns[0]} 和 {key_patterns[1]}。"
                )
            if key_patterns:
                return f"这一页我们先练这个句型：{key_patterns[0]}。"
            return "这一页我们先练点餐对话。"

        if page_type == "vocabulary":
            if key_words:
                return f"这一页我们先认食物和饮料单词，重点有：{'、'.join(key_words)}。"
            return "这一页我们先认食物和饮料单词。"

        if page_type == "phonics":
            return "这一页我们先练发音和拼读。"
        if page_type == "reading":
            return "这一页我们先读短文，再抓重点信息。"
        if page_type == "story":
            return "这一页我们先读故事，再抓关键句子。"
        if page_type == "review":
            return "这一页我们先做一个小复习。"
        return "这一页我们先抓住当前课本的重点。"

    def _looks_like_curriculum_intro(self, text: str) -> bool:
        normalized = text.strip()
        lower = normalized.casefold()
        return (
            lower.startswith("theme:")
            or " key patterns:" in lower
            or "teaching goal:" in lower
            or "鼓励学生" in normalized
            or "要求学生" in normalized
            or "引导学生" in normalized
        )

    def _render_probe_prompt(
        self,
        probe: str | None,
        block: TeachingBlockRecord,
    ) -> str | None:
        if not probe:
            return None
        text = probe.strip()
        if not text:
            return None
        lower = text.casefold()
        if self._contains_cjk(text):
            rewritten = self._rewrite_cjk_probe_prompt(text, block)
            return rewritten

        if lower.startswith("what does ") and lower.endswith(" mean?"):
            term = text[10:-6].strip(" \"'")
            model_answer = self._best_model_answer(block, text)
            if term and term.casefold() in model_answer.casefold():
                return f"先热个身，用 {term} 说一句完整的话。"
            return f"先热个身，告诉我 {term} 是什么意思？"

        if lower.startswith("can you say:"):
            sentence = text.split(":", 1)[1].strip()
            if self._is_service_question_text(sentence):
                return self._render_service_question_repeat_prompt(sentence)
            if self._looks_like_task_instruction(sentence):
                return self._render_task_instruction_probe_prompt(sentence, block)
            return f"先试着说一遍：{sentence}"

        if lower.startswith("can you repeat:"):
            sentence = text.split(":", 1)[1].strip()
            if self._is_service_question_text(sentence):
                return self._render_service_question_repeat_prompt(sentence)
            return f"先跟老师读一遍：{sentence}"

        if lower.startswith("if i ask ") and lower.endswith("how do you answer?"):
            body = text[len("If I ask ") : -len("how do you answer?")].rstrip(" ,")
            target = self._best_model_answer(block, text)
            target_answers = self._best_model_answers(
                block,
                text,
                limit=2 if self._prefer_full_answer_scaffold(text, target) else 1,
            )
            answer_choices = self._format_answer_choices(target_answers)
            if "drink" in body.casefold():
                if len(target_answers) > 1:
                    return f"现在你口渴了，跟老师选一句说：{answer_choices}"
                return f"现在你口渴了，跟老师说一句：{target}"
            if "eat" in body.casefold():
                if len(target_answers) > 1:
                    return f"现在你想点吃的，跟老师选一句说：{answer_choices}"
                return f"现在你想点吃的，跟老师说一句：{target}"
            if len(target_answers) > 1:
                return f"老师来问你：{body} 你就选一句说：{answer_choices}"
            return f"老师来问你：{body} 你就说：{target}"

        if lower.startswith("do you know the word "):
            word = text[len("Do you know the word ") :].strip(" ?")
            return f"先看看这个词你认不认识：{word}"

        if lower.startswith("do you know "):
            word = text[len("Do you know ") :].strip(" ?")
            return f"先看看这个词你认不认识：{word}"

        if lower.startswith("can you read "):
            word = text[len("Can you read ") :].strip(" ?")
            return f"先跟老师读一读：{word}"

        if lower.startswith("can you hear ") and lower.endswith(" clearly?"):
            phrase = text[len("Can you hear ") : -len(" clearly?")].strip()
            return f"先听一听，{phrase} 这几个词你能分清吗？"

        return f"先试试：{text}"

    def _looks_like_task_instruction(self, text: str) -> bool:
        return text.strip().casefold().startswith(_TASK_INSTRUCTION_STARTERS)

    def _render_task_instruction_probe_prompt(
        self,
        sentence: str,
        block: TeachingBlockRecord,
    ) -> str:
        _ = sentence
        block_type = block.block_type.casefold()
        if block_type == "roleplay_task":
            return "现在进入小对话。你先当顾客，说一句你想点什么。"
        if block_type == "writing_prompt":
            return "先说一个你准备写进去的关键信息。"
        if block_type == "picture_scene":
            return "先观察图片，说一个你看到的东西。"
        return "先说一个你自己的答案，不用重复任务句。"

    def _page_answer_examples(self, page_uid: str, *, limit: int) -> list[str]:
        preferred_blocks = sorted(
            self.catalog.blocks_for_page(page_uid),
            key=lambda candidate: (
                0
                if candidate.block_type in {"picture_scene", "vocabulary"}
                else 1,
                candidate.block_uid,
            ),
        )
        examples: list[str] = []
        seen: set[str] = set()
        for candidate in preferred_blocks:
            for value in [*candidate.focus_vocabulary, *candidate.allowed_answer_scope]:
                normalized = value.strip()
                if not normalized or self._looks_like_task_instruction(normalized):
                    continue
                if not self._looks_like_classroom_answer_example(normalized):
                    continue
                key = normalized.casefold()
                if key in seen:
                    continue
                seen.add(key)
                examples.append(normalized)
                if len(examples) >= limit:
                    return examples
        return examples

    def _looks_like_classroom_answer_example(self, text: str) -> bool:
        lower = text.casefold()
        if len(lower) <= 3 or "-" in lower:
            return False
        return not any(
            lower.startswith(prefix)
            for prefix in (
                "identify ",
                "group ",
                "create ",
                "match ",
                "notice ",
                "work on ",
            )
        )

    def _rewrite_cjk_probe_prompt(
        self,
        prompt: str,
        block: TeachingBlockRecord,
    ) -> str:
        text = prompt.strip()
        target = self._best_model_answer(block, text)
        target_answers = self._best_model_answers(
            block,
            text,
            limit=2 if self._prefer_full_answer_scaffold(text, target) else 1,
        )
        answer_choices = self._format_answer_choices(target_answers)

        if "如果老师问你" in text and "What would you like to drink?" in text:
            if len(target_answers) > 1:
                return f"现在你口渴了，跟老师选一句说：{answer_choices}"
            return f"现在你口渴了，跟老师说一句：{target}"

        if "如果老师问你" in text and "What would you like to eat?" in text:
            if len(target_answers) > 1:
                return f"现在你想点吃的，跟老师选一句说：{answer_choices}"
            return f"现在你想点吃的，跟老师说一句：{target}"

        if "如果老师问你" in text and "怎么答" in text:
            body = text.split("如果老师问你", 1)[1]
            body = body.split("，你可以怎么答", 1)[0].strip()
            if len(target_answers) > 1:
                return f"老师来问你：{body} 你就选一句说：{answer_choices}"
            return f"老师来问你：{body} 你就说：{target}"

        return text

    def _render_service_question_repeat_prompt(self, sentence: str) -> str:
        meaning = self._service_question_meaning(sentence)
        return (
            f"服务员会问你：{sentence}，意思是“{meaning}”。"
            f" 这句有点长，我们慢慢来：{self._chunk_sentence(sentence)}。"
            f" 来，跟着我说一遍：{sentence}"
        )

    def _service_question_meaning(self, sentence: str) -> str:
        lower = sentence.casefold()
        if "like to eat" in lower:
            return "你想吃什么"
        if "like to drink" in lower:
            return "你想喝什么"
        return "你想要什么"

    def _chunk_sentence(self, sentence: str) -> str:
        return " - ".join(sentence.split())

    def _contains_cjk(self, text: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", text))

    def _looks_like_lexicon_query(self, text: str) -> bool:
        lower = text.casefold()
        return any(
            token in lower
            for token in ("what does", " meaning", " mean", "怎么说", "什么意思")
        )

    def _pick_probe_question(
        self,
        block: TeachingBlockRecord,
        page: PageLessonRecord,
    ) -> str | None:
        if block.entry_probe_questions:
            return block.entry_probe_questions[0]
        if page.entry_probe_questions:
            return page.entry_probe_questions[0]
        return None

    def _best_model_answers(
        self,
        block: TeachingBlockRecord,
        question: str | None = None,
        *,
        limit: int = 1,
    ) -> list[str]:
        allowed_answers = self._evaluation_answer_scope(block, question)
        probe_literals = self._probe_literal_candidates(question)
        candidates = []
        candidates.extend(probe_literals)
        candidates.extend(allowed_answers)
        candidates.extend(
            pattern for pattern in block.core_patterns if pattern and pattern not in candidates
        )
        if not candidates:
            return [block.teaching_goal]

        question_tokens = self._teacher_tokens(question or "")
        lower_question = (question or "").casefold()
        answer_style_prompt = any(
            phrase in lower_question
            for phrase in (
                "answer",
                "how do you answer",
                "怎么答",
                "怎么回答",
                "跟老师说",
                "说一句",
                "选一句说",
            )
        )

        def _score(candidate: str) -> tuple[int, int, int]:
            tokens = self._teacher_tokens(candidate)
            overlap = len(tokens & question_tokens)
            candidate_is_question = candidate.strip().endswith("?")
            candidate_has_placeholder = "..." in candidate
            candidate_is_allowed_answer = candidate in allowed_answers
            candidate_is_probe_literal = candidate in probe_literals

            if "hungry" in question_tokens and "hungry" in tokens:
                overlap += 2
            if "drink" in question_tokens and tokens & _DRINK_ANSWER_TOKENS:
                overlap += 2
            if "eat" in question_tokens and tokens & _FOOD_ANSWER_TOKENS:
                overlap += 2
            if candidate_is_probe_literal:
                overlap += 4
            if any(word in lower_question for word in ("say", "repeat", "answer")) and len(
                candidate.split()
            ) >= 2:
                overlap += 1
            if answer_style_prompt:
                if candidate_is_allowed_answer:
                    overlap += 3
                if candidate_is_question:
                    overlap -= 4
                if candidate_has_placeholder:
                    overlap -= 2
            return (
                overlap,
                1 if candidate_is_probe_literal else 0,
                1 if candidate_is_allowed_answer else 0,
                0 if candidate_is_question else 1,
                1 if len(candidate.split()) >= 2 else 0,
                len(candidate.split()),
            )

        ranked = sorted(candidates, key=_score, reverse=True)
        return ranked[: max(limit, 1)]

    def _best_model_answer(
        self,
        block: TeachingBlockRecord,
        question: str | None = None,
    ) -> str:
        return self._best_model_answers(block, question, limit=1)[0]

    def _format_answer_choices(self, answers: list[str]) -> str:
        unique_answers: list[str] = []
        for answer in answers:
            if answer and answer not in unique_answers:
                unique_answers.append(answer)
        if not unique_answers:
            return ""
        if len(unique_answers) == 1:
            return unique_answers[0]
        return " 或 ".join(unique_answers[:2])

    def _probe_literal_candidates(self, question: str | None) -> list[str]:
        if not question:
            return []
        text = question.strip()
        if not text:
            return []
        lower = text.casefold()

        def _single(value: str) -> list[str]:
            candidate = value.strip().strip(" ?")
            return [candidate] if candidate else []

        if lower.startswith("can you say:"):
            return _single(text.split(":", 1)[1])
        if lower.startswith("can you repeat:"):
            return _single(text.split(":", 1)[1])
        if lower.startswith("can you read "):
            return _single(text[len("Can you read ") :])
        if lower.startswith("do you know the word "):
            return _single(text[len("Do you know the word ") :])
        if lower.startswith("do you know "):
            return _single(text[len("Do you know ") :])
        return []

    def _follow_up_prompt_after_probe_echo(
        self,
        *,
        learner_input: str,
        question: str | None,
        block: TeachingBlockRecord,
    ) -> str | None:
        if not question:
            return None
        candidates = self._probe_literal_candidates(question)
        if not candidates:
            return None

        normalized_input = normalize_text(learner_input)
        if normalized_input not in {normalize_text(candidate) for candidate in candidates}:
            return None

        sentence = candidates[0]
        lower = sentence.casefold()
        if "what would you like to eat" in lower:
            answers = self._format_answer_choices(
                self._best_model_answers(
                    block,
                    "现在你想点吃的，跟老师选一句说。",
                    limit=2,
                )
            )
            return f"现在你想点吃的，跟老师选一句说：{answers}"
        if "what would you like to drink" in lower:
            answers = self._format_answer_choices(
                self._best_model_answers(
                    block,
                    "现在你口渴了，跟老师选一句说。",
                    limit=2,
                )
            )
            return f"现在你口渴了，跟老师选一句说：{answers}"
        return None

    def _evaluate_learner_answer(
        self,
        *,
        learner_input: str,
        block: TeachingBlockRecord,
        question: str | None,
        answer_scope: list[str],
    ) -> EvaluationResult:
        if (
            self._block_has_task_instruction(block)
            or self._question_has_task_instruction((question or "").casefold())
        ):
            task_eval = self._evaluate_task_instruction_answer(
                learner_input=learner_input,
                block=block,
                question=question,
            )
            if task_eval is not None:
                return task_eval
        return evaluate_answer(learner_input, answer_scope)

    def _judge_answer_readiness(
        self,
        *,
        learner_input: str,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
        answer_scope: list[str],
        evaluation: EvaluationResult,
    ) -> ReadinessJudgeResult | None:
        if self.readiness_judge is None:
            return None
        return self.readiness_judge.judge(
            self._build_readiness_judge_context(
                learner_input=learner_input,
                state=state,
                block=block,
                answer_scope=answer_scope,
                evaluation=evaluation,
            )
        )

    def _build_readiness_judge_context(
        self,
        *,
        learner_input: str,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
        answer_scope: list[str],
        evaluation: EvaluationResult,
    ) -> dict[str, Any]:
        return {
            "learner_input": learner_input,
            "last_teacher_question": state.last_teacher_question,
            "last_teacher_response": self._last_teacher_text(state),
            "current_goal": block.teaching_goal,
            "allowed_answer_scope": answer_scope,
            "answer_evaluation": evaluation,
            "current_block": {
                "block_uid": block.block_uid,
                "teaching_goal": block.teaching_goal,
                "core_patterns": block.core_patterns,
                "focus_vocabulary": block.focus_vocabulary,
                "allowed_answer_scope": block.allowed_answer_scope,
            },
            "recent_turns": list(state.recent_turns[-3:]),
        }

    def _last_teacher_text(self, state: LessonRuntimeState) -> str | None:
        for turn in reversed(state.recent_turns):
            teacher_text = turn.get("teacher_text")
            if teacher_text:
                return teacher_text
        return None

    def _evaluate_task_instruction_answer(
        self,
        *,
        learner_input: str,
        block: TeachingBlockRecord,
        question: str | None,
    ) -> EvaluationResult | None:
        normalized_input = normalize_text(learner_input)
        if not normalized_input:
            return "unclear"

        task_literals = {
            normalize_text(candidate)
            for candidate in [
                *self._probe_literal_candidates(question),
                *block.core_patterns,
                *block.allowed_answer_scope,
            ]
            if self._looks_like_task_instruction(candidate)
        }
        if normalized_input in task_literals:
            return "incorrect"

        item_tokens = self._task_answer_item_tokens(block)
        input_tokens = self._teacher_tokens(learner_input)
        matched_items = input_tokens & item_tokens
        if not matched_items:
            return None

        if "bring" in input_tokens and not self._has_future_or_list_answer_shape(
            learner_input,
        ):
            return "partially_correct"
        if len(input_tokens) <= 3:
            return "correct"
        if input_tokens & _PARTY_LIST_ACTION_TOKENS or any(
            token in input_tokens for token in ("and", "some", "a", "an")
        ):
            return "correct"
        return "acceptable"

    def _task_answer_item_tokens(self, block: TeachingBlockRecord) -> set[str]:
        tokens = set(_PARTY_LIST_ITEM_TOKENS)
        for example in self._page_answer_examples(block.page_uid, limit=12):
            tokens.update(self._teacher_tokens(example))
        return tokens

    def _has_future_or_list_answer_shape(self, learner_input: str) -> bool:
        lower = learner_input.casefold()
        normalized = normalize_text(learner_input)
        return any(
            phrase in lower or phrase in normalized
            for phrase in (
                "going to bring",
                "will bring",
                "i'll bring",
                "i m going to bring",
                "i am going to bring",
                "want to bring",
                "need to bring",
            )
        )

    def _evaluation_answer_scope(
        self,
        block: TeachingBlockRecord,
        question: str | None,
    ) -> list[str]:
        allowed_answers = [answer for answer in block.allowed_answer_scope if answer]
        question_lower = (question or "").casefold()
        if (
            self._block_has_task_instruction(block)
            or self._question_has_task_instruction(question_lower)
        ):
            examples = self._page_answer_examples(block.page_uid, limit=8)
            if examples:
                return examples

        if not allowed_answers:
            return []

        if self._looks_like_drink_answer_prompt(question_lower):
            filtered = [
                answer
                for answer in allowed_answers
                if self._matches_answer_domain(answer, _DRINK_ANSWER_TOKENS)
            ]
            if filtered:
                return filtered

        if self._looks_like_food_answer_prompt(question_lower):
            filtered = [
                answer
                for answer in allowed_answers
                if self._matches_answer_domain(answer, _FOOD_ANSWER_TOKENS)
            ]
            if filtered:
                return filtered

        return allowed_answers

    def _block_has_task_instruction(self, block: TeachingBlockRecord) -> bool:
        return any(
            self._looks_like_task_instruction(value)
            for value in [
                *block.core_patterns,
                *block.allowed_answer_scope,
                *block.entry_probe_questions,
            ]
        )

    def _question_has_task_instruction(self, prompt: str) -> bool:
        if not prompt:
            return False
        if prompt.startswith("can you say:"):
            return self._looks_like_task_instruction(prompt.split(":", 1)[1])
        return self._looks_like_task_instruction(prompt)

    def _looks_like_drink_answer_prompt(self, prompt: str) -> bool:
        return any(token in prompt for token in ("drink", "喝", "口渴"))

    def _looks_like_food_answer_prompt(self, prompt: str) -> bool:
        return any(token in prompt for token in ("eat", "吃", "想吃", "点吃的"))

    def _looks_like_emotional_help_input(self, learner_input: str) -> bool:
        lower = learner_input.casefold()
        return any(token in lower for token in _EMOTION_HELP_HINTS)

    def _is_service_question_text(self, text: str) -> bool:
        lower = text.casefold()
        return (
            "what would you like to eat" in lower
            or "what would you like to drink" in lower
        )

    def _matches_answer_domain(self, answer: str, domain_tokens: set[str]) -> bool:
        return bool(self._teacher_tokens(answer) & domain_tokens)

    def _prefer_full_answer_scaffold(
        self,
        prompt: str | None,
        target: str,
    ) -> bool:
        if not prompt or not target or "..." in target:
            return False
        lower_prompt = prompt.casefold()
        return any(
            phrase in lower_prompt
            for phrase in (
                "answer",
                "how do you answer",
                "怎么答",
                "怎么回答",
                "顾客",
                "点餐",
                "口渴",
                "想点吃的",
                "说一句",
                "选一句说",
            )
        )

    def _is_scene_setup_prompt(self, prompt: str) -> bool:
        lower_prompt = prompt.casefold()
        return any(
            phrase in lower_prompt
            for phrase in (
                "口渴",
                "想点吃的",
                "假设你饿了",
                "现在你饿了",
                "老师来问你",
            )
        )

    def _teacher_tokens(self, text: str) -> set[str]:
        lowered = text.casefold()
        parts = re.split(r"[^a-z0-9\u4e00-\u9fff']+", lowered)
        return {part for part in parts if part}

    def _frame_sentence(self, sentence: str) -> str:
        words = sentence.split()
        if len(words) <= 3:
            return sentence
        return " ".join(words[:-1]) + " ..."

    def _pick_repair_mode(self, block: TeachingBlockRecord, *preferred: str) -> str:
        for mode in preferred:
            if mode in block.repair_modes:
                return mode
        if block.repair_modes:
            return block.repair_modes[0]
        return "none"
