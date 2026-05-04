"""Structured pilot loader and text-first lesson runtime helpers."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from json_repair import repair_json
from pydantic import BaseModel, ConfigDict, Field, model_serializer

from lightrag.orchestrator.lesson_brief_builder import LessonBriefBuilder
from lightrag.orchestrator.lesson_evidence import LessonEvidenceLookup
from lightrag.orchestrator.lesson_graph import build_lesson_turn_graph
from lightrag.orchestrator.lesson_llm_metering import (
    active_lesson_llm_call_count,
    collect_lesson_llm_metering,
    default_lesson_llm_model,
    override_lesson_llm_prompt_breakdown,
    record_lesson_llm_call,
    summarize_lesson_llm_metering,
)
from lightrag.orchestrator.lesson_policy_prompts import (
    ANSWER_TURN_POLICY_RUBRIC_V1,
    REPLY_QUALITY_REVISION_RUBRIC_V1,
)
from lightrag.orchestrator.lesson_readiness_judge import (
    ReadinessJudge,
    ReadinessJudgeResult,
)
from lightrag.orchestrator.lesson_retrieval import RetrievalSelection, ScopedRetriever
from lightrag.orchestrator.lesson_persona import (
    AiriPerformancePlan,
    ClassroomAffectState,
    LessonPersonaContext,
    MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_BYTES,
    MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1,
    MILI_PERSONA_CAPSULE_PROMPT_STATUS,
    MILI_PERSONA_CAPSULE_SOURCE,
    MILI_PERSONA_CAPSULE_V1,
    MILI_PERSONA_CAPSULE_VERSION,
    MILI_PERSONA_INTERESTS_ANSWER_TURN_POLICY_USAGE,
    MILI_PERSONA_INTERESTS_RUNTIME_USAGE,
    MILI_PERSONA_SOUL_PATH,
    build_lesson_persona_context_for_turn,
)
from lightrag.orchestrator.module_choice_skill import ModuleChoice, ModuleChoiceSkill
from lightrag.orchestrator.page_overview_skill import (
    PageOverview,
    PageOverviewModule,
    PageOverviewSkill,
)
from lightrag.orchestrator.lesson_state import LessonRuntimeState
from lightrag.orchestrator.simplemem_prompt_memory import LearnerMemorySummary
from lightrag.orchestrator.simplemem_writeback import SimpleMemSQLiteLessonMemoryWriter
from lightrag.orchestrator.support_asset_retrieval import SupportAssetRetriever, SupportMatch
from lightrag.orchestrator.task_resize_skill import TaskResize, TaskResizeSkill
from lightrag.orchestrator.teaching_move_planner import (
    ClassroomTargetPhraseCandidate,
    TeachingMovePlanner,
    classroom_target_phrase_reasons,
    select_classroom_target_phrase,
)
from lightrag.pedagogy.lesson_brief import (
    CurrentTurnLessonBrief,
    LessonBriefMisconceptionHint,
)
from lightrag.pedagogy.classification_task_policy import (
    classify_short_answer_for_task,
)
from lightrag.pedagogy.planner import (
    LessonPlanner,
    OpenTurnRouteDecision,
    PlannerDecision,
)
from lightrag.pedagogy.responder import (
    LessonResponder,
    LessonResponderTurnResult,
    classification_short_answer_evaluation,
    classification_short_answer_next_prompt,
    render_classification_short_answer_reply,
)
from lightrag.pedagogy.redirect_reply_policy import (
    looks_like_redirect_reply,
    maybe_render_redirect_reply,
)
from lightrag.pedagogy.teaching_move import TeachingMoveActionContract
from lightrag.pedagogy.evaluation import evaluate_answer, normalize_text
from lightrag.pedagogy.types import (
    EvaluationResult,
    RetrievalMode,
    TeachingAction,
    TurnLabel,
)
from lightrag.utils import logger

_TASK_INSTRUCTION_STARTERS = (
    "create ",
    "finish ",
    "fill ",
    "make ",
    "list ",
    "identify ",
    "group ",
    "listen ",
    "match ",
    "practice ",
    "design ",
    "write ",
)
_ANSWER_TURN_GENERIC_PRAISE_COMPACT_PHRASES = (
    "很棒",
    "真棒",
    "太棒",
    "非常棒",
    "特别棒",
    "很不错",
    "真不错",
    "非常好",
    "特别好",
    "真好",
    "做得很好",
    "完全正确",
    "非常正确",
    "很正确",
    "非常准确",
    "很准确",
    "完全对",
    "说得对",
    "答得对",
    "回答得对",
    "你说对了",
    "你答对了",
    "你回答对了",
    "说对了",
    "答对了",
    "回答对了",
    "说得很好",
    "答得很好",
    "回答得很好",
    "说得很棒",
    "答得很棒",
    "回答得很棒",
    "说得很准",
    "读得很准",
    "说得很清楚",
    "讲得很清楚",
    "很清楚",
    "非常清楚",
    "表达很清楚",
    "表达得很清楚",
    "回答很清楚",
    "回答得很清楚",
    "句子很好",
    "这个句子很好",
    "句子很标准",
    "这个句子很标准",
    "回答很标准",
    "很标准",
    "这句话是对的",
    "这句是对的",
    "这个回答是对的",
    "你的回答是对的",
    "回答是对的",
    "问得好",
)
_ANSWER_TURN_MINIMAL_RUNTIME_STATE_ENV = (
    "PEPTUTOR_ANSWER_TURN_MINIMAL_RUNTIME_STATE"
)
_ANSWER_TURN_LEGACY_RUNTIME_STATE_FRAME_KEYS = (
    "taskboundary",
    "recentdialogue",
    "allowedstatewrites",
    "learnerinputmatches",
)
_ANSWER_TURN_GENERIC_PRAISE_PATTERNS = (
    r"(?:^|[，,。.!！\s])很好(?:[，,。.!！\s]|$)",
    r"句子结构(?:是)?(?:很|非常|完全)?正确",
    r"(?:这个|你的|你刚才的)?回答(?:是|也)?(?:很|非常|完全)?(?:正确|准确|清楚)",
    r"(?:这句话|这句|这个回答|你的回答|你刚才的回答|回答)(?:是|也)?(?:很|非常|完全)?(?:对|正确|没错)的?(?![（(]?\s*tick\s*[）)]?\s*还是错)",
)
_PHONICS_WORD_SOUND_BY_EXEMPLAR = {
    "cow": "/aʊ/",
    "flower": "/aʊ/",
    "down": "/aʊ/",
    "wow": "/aʊ/",
    "snow": "/oʊ/",
    "slow": "/oʊ/",
    "yellow": "/oʊ/",
    "window": "/oʊ/",
    "tomorrow": "/oʊ/",
}
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
    task_type: str | None = None
    focus_vocabulary: list[str] = Field(default_factory=list)
    core_patterns: list[str] = Field(default_factory=list)
    allowed_answer_scope: list[str] = Field(default_factory=list)
    answer_scope: dict[str, Any] = Field(default_factory=dict)
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
    persona_source: str
    persona_version: str
    capsule_name: str
    full_soul_injected: bool
    answer_turn_policy_persona_capsule_enabled: bool
    current_llm_call_persona_capsule_injected: bool
    persona_capsule_bytes_configured: int
    persona_capsule_bytes_metered: int
    soul_path: str
    teacher_kernel_used: bool
    interests_available: bool
    interests_runtime_usage: str
    interests_answer_turn_policy_usage: str
    capsule_prompt_status: str
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


class LessonTeacherResponseAuditSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal[
        "policy",
        "policy_repaired",
        "llm",
        "llm_repaired",
        "fallback",
        "deterministic",
        "unknown",
    ]
    llm_called: bool
    llm_provider: str
    latency_ms: int = 0
    fallback_used: bool
    fallback_reason: str = "none"
    repair_reason: str = "none"
    route: str
    llm_token_usage: dict[str, Any] | None = None

    @model_serializer(mode="wrap")
    def _serialize_without_empty_llm_token_usage(self, handler):
        payload = handler(self)
        if payload.get("llm_token_usage") is None:
            payload.pop("llm_token_usage", None)
        return payload


class LessonTeacherResponseRenderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    audit: LessonTeacherResponseAuditSignal


class LessonTurnDebugSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    live_prompts: LessonLivePromptsDebugSignal
    vector_retrieval: LessonVectorRetrievalDebugSignal
    prompt_memory: LessonPromptMemoryDebugSignal
    semantic_recall: LessonSemanticRecallDebugSignal
    memory_runtime: LessonMemoryRuntimeDebugSignal
    persona: LessonPersonaDebugSignal
    response_audit: LessonTeacherResponseAuditSignal | None = None

    @model_serializer(mode="wrap")
    def _serialize_without_empty_response_audit(self, handler):
        payload = handler(self)
        if payload.get("response_audit") is None:
            payload.pop("response_audit", None)
        return payload


def _extract_page_number(page_uid: str) -> int:
    match = re.search(r"-P(\d+)(?:-\d+)?$", page_uid)
    if not match:
        raise ValueError(f"Cannot extract page number from page uid: {page_uid}")
    return int(match.group(1))


def _catalog_term_key(text: str) -> str:
    normalized = text.casefold().replace("’", "'")
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _extract_lexicon_query_term(text: str) -> str | None:
    query = " ".join(text.strip().split())
    if not query:
        return None
    patterns = (
        r"^what\s+(?:does|is)\s+(.+?)\s+(?:mean|meaning)\??$",
        r"^(.+?)\s*(?:是什么意思|什么意思|怎么说)\??$",
    )
    for pattern in patterns:
        match = re.match(pattern, query, flags=re.IGNORECASE)
        if match:
            term = match.group(1).strip(" \"'`?？")
            return term or None
    return None


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
        self.knowledge_atoms_by_scope: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
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

    def support_match_for_catalog_gloss(
        self,
        *,
        page_uid: str,
        query: str,
    ) -> SupportMatch | None:
        term = _extract_lexicon_query_term(query)
        term_key = _catalog_term_key(term or "")
        if not term_key:
            return None

        linked_block_uids = self._page_blocks_containing_term(
            page_uid=page_uid,
            term_key=term_key,
        )
        if not linked_block_uids:
            linked_block_uids = self._unit_blocks_containing_term(
                page_uid=page_uid,
                term_key=term_key,
            )
        if not linked_block_uids:
            return None
        linked_page_uids = sorted(
            {
                self.get_block(block_uid).page_uid
                for block_uid in linked_block_uids
                if block_uid in self.blocks
            }
        )

        scope = self.get_scope_for_page(page_uid)
        atoms = self.knowledge_atoms_by_scope.get(
            (scope.grade, scope.semester, scope.unit),
            [],
        )
        for atom in reversed(atoms):
            atom_text = str(atom.get("text") or "").strip()
            if _catalog_term_key(atom_text) != term_key:
                continue
            gloss = str(atom.get("gloss") or atom.get("chinese") or "").strip()
            if not gloss:
                continue
            return SupportMatch(
                entry_uid=str(atom.get("atom_uid") or f"KA-{term_key}"),
                entry_kind="lexicon",
                english=atom_text,
                chinese=gloss,
                linked_page_uids=linked_page_uids or [page_uid],
                linked_block_uids=linked_block_uids,
                score=50,
            )
        return None

    def _page_blocks_containing_term(
        self,
        *,
        page_uid: str,
        term_key: str,
    ) -> list[str]:
        result: list[str] = []
        for block in self.blocks_for_page(page_uid):
            values = [
                *block.focus_vocabulary,
                *block.allowed_answer_scope,
                *block.core_patterns,
                *block.entry_probe_questions,
                *block.return_anchors,
                *block.branchable_topics,
            ]
            if any(_catalog_term_key(value) == term_key for value in values):
                result.append(block.block_uid)
        return result

    def _unit_blocks_containing_term(
        self,
        *,
        page_uid: str,
        term_key: str,
    ) -> list[str]:
        result: list[str] = []
        candidates = [
            *self.blocks_for_page(page_uid),
            *self.blocks_for_unit(page_uid, exclude_page_uid=page_uid),
        ]
        seen: set[str] = set()
        for block in candidates:
            if block.block_uid in seen:
                continue
            seen.add(block.block_uid)
            values = [
                *block.focus_vocabulary,
                *block.allowed_answer_scope,
                *block.core_patterns,
                *block.entry_probe_questions,
                *block.return_anchors,
                *block.branchable_topics,
            ]
            if any(_catalog_term_key(value) == term_key for value in values):
                result.append(block.block_uid)
        return result

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
            scope_key = (payload.scope.grade, payload.scope.semester, payload.scope.unit)
            self.knowledge_atoms_by_scope.setdefault(scope_key, []).extend(
                payload.knowledge_atoms
            )

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
    "不想",
    "怕",
)
_ANSWER_TURN_AWKWARD_MIXED_ENGLISH_RE = re.compile(
    r"\b(?:[A-Za-z][A-Za-z'’]*(?:\s+[A-Za-z][A-Za-z'’]*){1,5}|please|clean)\b"
    r"[\"”']?[^.!?。！？\n]{0,32}[\u4e00-\u9fff]",
    re.IGNORECASE,
)
_COMMON_TRADITIONAL_TO_SIMPLIFIED = str.maketrans(
    {
        "愛": "爱",
        "會": "会",
        "還": "还",
        "學": "学",
        "問": "问",
        "對": "对",
        "現": "现",
        "裡": "里",
        "個": "个",
        "這": "这",
        "們": "们",
        "飲": "饮",
        "點": "点",
        "説": "说",
        "說": "说",
        "歡": "欢",
        "經": "经",
        "來": "来",
        "後": "后",
        "聽": "听",
        "關": "关",
        "於": "于",
        "龍": "龙",
        "練": "练",
        "習": "习",
        "類": "类",
        "讀": "读",
        "著": "着",
        "認": "认",
        "識": "识",
        "詞": "词",
        "嗎": "吗",
        "麼": "么",
        "裏": "里",
        "為": "为",
        "進": "进",
        "過": "过",
        "氣": "气",
        "樣": "样",
        "讓": "让",
        "語": "语",
        "課": "课",
        "圖": "图",
        "開": "开",
        "聲": "声",
        "線": "线",
        "題": "题",
        "單": "单",
        "選": "选",
        "簡": "简",
        "節": "节",
        "請": "请",
        "應": "应",
        "該": "该",
        "擇": "择",
        "給": "给",
    }
)
_LESSON_MODULE_TITLE_RE = re.compile(
    r"\b(?:"
    r"Let's\s+(?:try|talk|learn|check|spell|wrap\s+it\s+up)|"
    r"Ask\s+and\s+answer|Read\s+and\s+write|Listen\s+and\s+\w+|"
    r"Look\s+and\s+\w+|Let's\s+play|Role[- ]?play"
    r")\b",
    re.IGNORECASE,
)

class AnswerTurnPolicyStatePatch(BaseModel):
    """Minimal state write requested by the teacher-turn LLM."""

    model_config = ConfigDict(extra="forbid")

    currentblockuid: str
    awaitinganswer: bool
    lastteacherquestion: str | None = None


class AnswerTurnPolicyOutput(BaseModel):
    """Structured LLM output for one answer turn."""

    model_config = ConfigDict(extra="forbid")

    teacherreply: str = Field(min_length=1, max_length=500)
    statepatch: AnswerTurnPolicyStatePatch


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
        module_choice_skill: ModuleChoiceSkill | None = None,
        task_resize_skill: TaskResizeSkill | None = None,
        feature_statuses: dict[str, Any] | None = None,
        debug_signals_enabled: bool | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        policy_reply_review_enabled: bool | None = None,
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
        self.module_choice_skill = module_choice_skill or ModuleChoiceSkill()
        self.task_resize_skill = task_resize_skill or TaskResizeSkill()
        self.feature_statuses = feature_statuses or {}
        self.llm_provider = llm_provider or "unknown"
        self.llm_model = llm_model or default_lesson_llm_model()
        self.policy_reply_review_enabled = (
            _is_enabled(os.getenv("PEPTUTOR_LESSON_POLICY_REPLY_REVIEW"))
            if policy_reply_review_enabled is None
            else policy_reply_review_enabled
        )
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
            teacher_response=response.text,
            state=state,
            debug_signals=self._build_debug_signals(
                state=state,
                retrieval_mode="none",
                turn_label="page_entry",
                teaching_action="page_intro",
                response_audit=response.audit,
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
        initial_state = graph_state.get("state")
        initial_block_uid = (
            initial_state.current_block_uid
            if isinstance(initial_state, LessonRuntimeState)
            else ""
        )
        with collect_lesson_llm_metering(
            page_uid=str(graph_state.get("page_uid") or ""),
            block_uid=initial_block_uid or "",
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
        ) as llm_metering:
            result = self.turn_graph.invoke(graph_state).get("result")
        if result is None:
            raise RuntimeError("Lesson turn graph completed without a result")
        self._attach_llm_token_usage(result, llm_metering)
        result.state.push_turn_text(
            turn_label=result.turn_label,
            teacher_text=result.teacher_response,
            learner_text=graph_state.get("learner_input") or "",
        )
        return result

    def _attach_llm_token_usage(
        self,
        result: LessonTurnResult,
        llm_metering: Any,
    ) -> None:
        if result.debug_signals is None or result.debug_signals.response_audit is None:
            return
        audit = result.debug_signals.response_audit
        summary = summarize_lesson_llm_metering(
            llm_metering,
            route=audit.route,
            turn_label=str(result.turn_label),
            page_uid=result.page_uid,
            block_uid=result.block_uid or "",
            llm_provider=audit.llm_provider or self.llm_provider,
            llm_model=self.llm_model,
        )
        if summary is not None:
            audit.llm_token_usage = summary
        self._attach_persona_llm_call_debug(result)

    def _attach_persona_llm_call_debug(self, result: LessonTurnResult) -> None:
        debug_signals = result.debug_signals
        if debug_signals is None or debug_signals.response_audit is None:
            return
        usage = debug_signals.response_audit.llm_token_usage
        metered_bytes = 0
        if isinstance(usage, dict):
            calls = usage.get("calls")
            if isinstance(calls, list):
                metered_bytes = sum(
                    int(call.get("persona_capsule_bytes") or 0)
                    for call in calls
                    if isinstance(call, dict)
                )
            else:
                metered_bytes = int(usage.get("persona_capsule_bytes") or 0)
        debug_signals.persona.persona_capsule_bytes_metered = metered_bytes
        debug_signals.persona.current_llm_call_persona_capsule_injected = (
            metered_bytes > 0
        )

    def _handle_answer_turn(
        self,
        state: LessonRuntimeState,
        learner_input: str,
    ) -> LessonTurnResult:
        block = self.catalog.get_block(state.current_block_uid or "")
        module_choice = self._handle_module_choice_turn(
            state=state,
            learner_input=learner_input,
            current_block=block,
        )
        if module_choice is not None:
            return module_choice

        classification_short_answer = self._handle_classification_short_answer_turn(
            state=state,
            learner_input=learner_input,
            current_block=block,
        )
        if classification_short_answer is not None:
            return classification_short_answer

        resize_follow_up = self._handle_task_resize_follow_up(
            state=state,
            learner_input=learner_input,
            current_block=block,
        )
        if resize_follow_up is not None:
            return resize_follow_up

        task_resize = self._handle_task_resize_turn(
            state=state,
            learner_input=learner_input,
            current_block=block,
        )
        if task_resize is not None:
            return task_resize

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
        if self._should_preempt_answer_turn_with_knowledge(learner_input):
            logger.info(
                "Lesson answer turn preempted to knowledge route page_uid=%s block_uid=%s reason=explicit_lexicon_query",
                state.current_page_uid,
                block.block_uid,
            )
            return self._handle_open_turn(state, learner_input)
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
        policy_available = self._answer_turn_policy_complete_text() is not None

        next_state = state.model_copy(deep=True)
        next_state.push_turn_label("answer_question")
        next_state.last_eval_result = evaluation

        if policy_available:
            policy_result = self._handle_answer_turn_policy(
                block=block,
                state=next_state,
                learner_input=learner_input,
                evaluation=evaluation,
            )
            if policy_result is not None:
                return policy_result

        if self._should_interrupt_answer_turn(
            learner_input=learner_input,
            evaluation=evaluation,
            state=state,
            block=block,
        ):
            return self._handle_open_turn(state, learner_input)

        rule_can_advance = next_state.last_eval_result in {"correct", "acceptable"}
        readiness = self._judge_answer_readiness(
            learner_input=learner_input,
            state=next_state,
            block=block,
            answer_scope=answer_scope,
            evaluation=evaluation,
        )
        llm_can_advance = (
            readiness.can_advance if readiness is not None else rule_can_advance
        )
        logger.info(
            "Lesson answer boundary judge page_uid=%s block_uid=%s rule_eval=%s rule_can_advance=%s llm_used=%s llm_readiness=%s llm_can_advance=%s disagreement=%s reason=%s",
            next_state.current_page_uid,
            block.block_uid,
            next_state.last_eval_result,
            rule_can_advance,
            readiness is not None,
            readiness.readiness if readiness is not None else None,
            llm_can_advance,
            readiness is not None and rule_can_advance != llm_can_advance,
            readiness.reason if readiness is not None else "",
        )

        if llm_can_advance:
            return self._handle_success(block, next_state, learner_input=learner_input)
        if rule_can_advance and readiness is not None:
            return self._handle_readiness_stay(
                block,
                next_state,
                learner_input=learner_input,
                readiness=readiness,
            )
        return self._handle_difficulty(
            block,
            next_state,
            learner_input=learner_input,
        )

    def _handle_answer_turn_policy(
        self,
        *,
        block: TeachingBlockRecord,
        state: LessonRuntimeState,
        learner_input: str,
        evaluation: EvaluationResult,
    ) -> LessonTurnResult | None:
        complete_text = self._answer_turn_policy_complete_text()
        if complete_text is None:
            return None

        frame = self._build_answer_turn_policy_frame(
            block=block,
            state=state,
            learner_input=learner_input,
        )
        prompt = self._build_answer_turn_policy_prompt(frame=frame)
        metering_overrides = self._answer_turn_policy_prompt_metering_overrides(
            frame=frame
        )
        raw = ""
        started_at = time.perf_counter()
        call_count_before = active_lesson_llm_call_count()
        with override_lesson_llm_prompt_breakdown(metering_overrides):
            try:
                raw = complete_text(
                    prompt,
                    system_prompt=None,
                    history_messages=[],
                    max_tokens=420,
                    _lesson_audit_tag="teacher_turn_policy.answer_question",
                )
                if active_lesson_llm_call_count() == call_count_before:
                    record_lesson_llm_call(
                        prompt=prompt,
                        completion=raw,
                        system_prompt=None,
                        history_messages=[],
                        llm_provider=self.llm_provider,
                        llm_model=self.llm_model,
                        audit_tag="teacher_turn_policy.answer_question",
                        mode="complete",
                        status="success",
                        route="answer_turn_policy",
                        turn_label="answer_question",
                        page_uid=state.current_page_uid,
                        block_uid=block.block_uid,
                    )
                policy = self._parse_answer_turn_policy(raw)
            except Exception as exc:
                if active_lesson_llm_call_count() == call_count_before:
                    record_lesson_llm_call(
                        prompt=prompt,
                        completion=raw,
                        system_prompt=None,
                        history_messages=[],
                        llm_provider=self.llm_provider,
                        llm_model=self.llm_model,
                        audit_tag="teacher_turn_policy.answer_question",
                        mode="complete",
                        status="error",
                        route="answer_turn_policy",
                        turn_label="answer_question",
                        page_uid=state.current_page_uid,
                        block_uid=block.block_uid,
                    )
                logger.info(
                    "Lesson teacher response audit turn_label=answer_question llmcalled=true llmprovider=%s latencyms=%d fallbackused=true fallbackreason=policy_exception teacherresponse_source=fallback response_chars=0",
                    self.llm_provider,
                    int((time.perf_counter() - started_at) * 1000),
                )
                logger.warning(
                    "Lesson answer policy route policy_used=false legacy_branch_used=true page_uid=%s block_uid=%s rule_eval=%s fallback_reason=policy_exception prompt_chars=%d error=%s raw=%s",
                    state.current_page_uid,
                    block.block_uid,
                    evaluation,
                    len(prompt),
                    exc,
                    raw[:500],
                )
                return None

        policy = self._apply_answer_turn_policy_state_boundary(
            block=block,
            state=state,
            learner_input=learner_input,
            policy=policy,
        )
        policy, target_source_lock_status = (
            self._maybe_lock_answer_turn_policy_target_source(
                policy=policy,
                state=state,
                block=block,
                frame=frame,
                learner_input=learner_input,
                evaluation=evaluation,
            )
        )
        rejection = self._answer_turn_policy_rejection_reason(
            frame=frame,
            policy=policy,
        )

        if rejection is not None:
            logger.info(
                "Lesson teacher response audit turn_label=answer_question llmcalled=true llmprovider=%s latencyms=%d fallbackused=true fallbackreason=policy_rejected teacherresponse_source=fallback response_chars=0",
                self.llm_provider,
                int((time.perf_counter() - started_at) * 1000),
            )
            logger.warning(
                "Lesson answer policy route policy_used=false legacy_branch_used=true page_uid=%s block_uid=%s rule_eval=%s fallback_reason=policy_rejected requested_block_uid=%s awaiting_answer=%s reason=%s raw=%s",
                state.current_page_uid,
                block.block_uid,
                evaluation,
                policy.statepatch.currentblockuid,
                policy.statepatch.awaitinganswer,
                rejection,
                raw[:500],
            )
            return None

        (
            policy,
            quality_revision_status,
            quality_issues_before,
            quality_issues_after,
            revision_raw,
        ) = self._maybe_revise_answer_turn_policy_reply(
            complete_text=complete_text,
            policy=policy,
            frame=frame,
            learner_input=learner_input,
        )
        if target_source_lock_status != "not_needed":
            quality_revision_status = (
                f"{quality_revision_status}+target_source_lock_{target_source_lock_status}"
            )
        policy, phrasing_repair_status = (
            self._maybe_repair_answer_turn_policy_reply_classroom_phrasing(
                policy=policy,
                frame=frame,
            )
        )
        if phrasing_repair_status != "not_needed":
            quality_revision_status = (
                f"{quality_revision_status}+classroom_phrasing_{phrasing_repair_status}"
            )
            quality_issues_after = self._answer_turn_policy_reply_quality_issues(
                policy.teacherreply
            )
        policy, target_phrase_repair_status = (
            self._maybe_repair_answer_turn_policy_target_phrase_quality(
                policy=policy,
                frame=frame,
            )
        )
        if target_phrase_repair_status != "not_needed":
            quality_revision_status = (
                f"{quality_revision_status}+target_phrase_quality_{target_phrase_repair_status}"
            )
            quality_issues_after = self._answer_turn_policy_reply_quality_issues(
                policy.teacherreply
            )
        policy, generic_praise_repair_status = (
            self._maybe_strip_answer_turn_policy_generic_praise(
                policy=policy,
                frame=frame,
                learner_input=learner_input,
            )
        )
        if generic_praise_repair_status != "not_needed":
            quality_revision_status = (
                f"{quality_revision_status}+generic_praise_{generic_praise_repair_status}"
            )
            quality_issues_after = self._answer_turn_policy_reply_quality_issues(
                policy.teacherreply
            )
        policy, matched_input_repair_status = (
            self._maybe_repair_answer_turn_policy_matched_input_pullback(
                policy=policy,
                frame=frame,
                learner_input=learner_input,
                evaluation=evaluation,
            )
        )
        if matched_input_repair_status != "not_needed":
            quality_revision_status = (
                f"{quality_revision_status}+matched_input_pullback_{matched_input_repair_status}"
            )
            quality_issues_after = self._answer_turn_policy_reply_quality_issues(
                policy.teacherreply
            )
        policy, phonics_repair_status = (
            self._maybe_repair_answer_turn_policy_phonics_tautology(
                policy=policy,
                frame=frame,
                learner_input=learner_input,
            )
        )
        if phonics_repair_status != "not_needed":
            quality_revision_status = (
                f"{quality_revision_status}+phonics_tautology_{phonics_repair_status}"
            )
            quality_issues_after = self._answer_turn_policy_reply_quality_issues(
                policy.teacherreply
            )
        policy, traditional_repair_status = (
            self._maybe_normalize_answer_turn_policy_traditional_chinese(policy)
        )
        if traditional_repair_status != "not_needed":
            quality_revision_status = (
                f"{quality_revision_status}+traditional_{traditional_repair_status}"
            )
            quality_issues_after = self._answer_turn_policy_reply_quality_issues(
                policy.teacherreply
            )
        if target_phrase_repair_status == "applied":
            pacing_repair_status = "not_needed"
        else:
            policy, pacing_repair_status = (
                self._maybe_repair_answer_turn_policy_reply_pacing(
                    policy=policy,
                    frame=frame,
                    learner_input=learner_input,
                )
            )
        if pacing_repair_status != "not_needed":
            quality_revision_status = (
                f"{quality_revision_status}+classroom_pacing_{pacing_repair_status}"
            )
            quality_issues_after = self._answer_turn_policy_reply_quality_issues(
                policy.teacherreply
            )
        policy, post_pacing_matched_input_repair_status = (
            self._maybe_repair_answer_turn_policy_matched_input_pullback(
                policy=policy,
                frame=frame,
                learner_input=learner_input,
                evaluation=evaluation,
            )
        )
        if post_pacing_matched_input_repair_status != "not_needed":
            quality_revision_status = (
                f"{quality_revision_status}+matched_input_pullback_{post_pacing_matched_input_repair_status}"
            )
            quality_issues_after = self._answer_turn_policy_reply_quality_issues(
                policy.teacherreply
            )
        policy, module_choice_boundary_status = (
            self._maybe_repair_answer_turn_policy_module_choice_boundary(
                policy=policy,
                frame=frame,
                learner_input=learner_input,
            )
        )
        if module_choice_boundary_status != "not_needed":
            quality_revision_status = (
                f"{quality_revision_status}+module_choice_boundary_{module_choice_boundary_status}"
            )
            quality_issues_after = self._answer_turn_policy_reply_quality_issues(
                policy.teacherreply
            )
        policy, redirect_reply_policy_status = (
            self._maybe_repair_answer_turn_policy_redirect_reply_policy(
                policy=policy,
                frame=frame,
                learner_input=learner_input,
            )
        )
        if redirect_reply_policy_status != "not_needed":
            quality_revision_status = (
                f"{quality_revision_status}+redirect_reply_policy_{redirect_reply_policy_status}"
            )
            quality_issues_after = self._answer_turn_policy_reply_quality_issues(
                policy.teacherreply
            )
        policy, sentence_tail_repair_status = (
            self._maybe_repair_answer_turn_policy_incomplete_sentence_tail(policy)
        )
        if sentence_tail_repair_status != "not_needed":
            quality_revision_status = (
                f"{quality_revision_status}+{sentence_tail_repair_status}"
            )
            quality_issues_after = self._answer_turn_policy_reply_quality_issues(
                policy.teacherreply
            )
        fact_warnings = self._answer_turn_policy_fact_warnings(
            policy=policy,
            frame=frame,
            learner_input=learner_input,
        )
        reply_warnings = self._answer_turn_policy_reply_warnings(policy.teacherreply)
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        if policy.statepatch.currentblockuid == block.block_uid:
            self._log_gentle_redirect_teaching_move(
                learner_input=learner_input,
                state=state,
                block=block,
                route="answer_turn_policy",
                turn_label="answer_question",
                evaluation=evaluation,
                target_phrase=self._answer_turn_policy_target_phrase(
                    policy=policy,
                    frame=frame,
                    teacher_reply=policy.teacherreply,
                ),
                active_prompt=str(frame.get("teacherasked") or ""),
                return_anchor=policy.statepatch.lastteacherquestion,
            )
        logger.info(
            "Lesson teacher response audit turn_label=answer_question llmcalled=true llmprovider=%s latencyms=%d fallbackused=false fallbackreason=none teacherresponse_source=policy response_chars=%d",
            self.llm_provider,
            latency_ms,
            len(policy.teacherreply),
        )
        logger.info(
            "Lesson answer policy route policy_used=true legacy_branch_used=false page_uid=%s block_uid=%s rule_eval=%s requested_block_uid=%s awaiting_answer=%s prompt_chars=%d reply_chars=%d fact_warnings=%s reply_warnings=%s quality_revision=%s quality_issues_before=%s quality_issues_after=%s teacher_response=%s raw=%s revision_raw=%s",
            state.current_page_uid,
            block.block_uid,
            evaluation,
            policy.statepatch.currentblockuid,
            policy.statepatch.awaitinganswer,
            len(prompt),
            len(policy.teacherreply),
            fact_warnings,
            reply_warnings,
            quality_revision_status,
            quality_issues_before,
            quality_issues_after,
            policy.teacherreply[:500],
            raw[:500],
            revision_raw[:500],
        )
        repair_reason = self._answer_turn_policy_audit_repair_reason(
            quality_revision_status
        )
        return self._build_answer_turn_policy_result(
            block=block,
            state=state,
            policy=policy,
            response_audit=LessonTeacherResponseAuditSignal(
                source=(
                    "policy_repaired" if repair_reason != "none" else "policy"
                ),
                llm_called=True,
                llm_provider=self.llm_provider,
                latency_ms=latency_ms,
                fallback_used=False,
                fallback_reason="none",
                repair_reason=repair_reason,
                route="answer_turn_policy",
            ),
        )

    def _log_gentle_redirect_teaching_move(
        self,
        *,
        learner_input: str,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
        route: str,
        turn_label: str,
        evaluation: EvaluationResult | None,
        target_phrase: str | None = None,
        active_prompt: str | None = None,
        return_anchor: str | None = None,
    ) -> None:
        interpreted_intent = self._gentle_redirect_interpreted_intent(
            learner_input=learner_input,
            state=state,
            block=block,
            evaluation=evaluation,
            turn_label=turn_label,
        )
        if interpreted_intent is None:
            return
        active_prompt = active_prompt or self._active_prompt_for_teaching_move(
            state=state,
            block=block,
        )
        target_phrase = target_phrase or self._target_phrase_for_teaching_move(
            state=state,
            block=block,
            active_prompt=active_prompt,
        )
        active_prompt = self._normalize_teaching_move_anchor(
            active_prompt,
            block=block,
        )
        return_anchor = self._normalize_teaching_move_anchor(
            return_anchor,
            block=block,
        )
        current_target = (
            block.teaching_goal
            or block.teaching_summary
            or target_phrase
            or active_prompt
        )
        target_phrase = target_phrase or active_prompt or current_target
        return_anchor = return_anchor or target_phrase or active_prompt or current_target
        teaching_move = self.teaching_move_planner.plan_gentle_redirect(
            learner_input=learner_input,
            interpreted_intent=interpreted_intent,
            current_target=current_target,
            target_phrase=target_phrase or "",
            active_prompt=active_prompt or "",
            return_anchor=return_anchor or "",
            next_action=self._gentle_redirect_next_action(interpreted_intent),
            correction_kind=evaluation or interpreted_intent,
            route=route,
            turn_label=turn_label,
            preserve_page_uid=state.current_page_uid,
            preserve_block_uid=block.block_uid,
            block=block,
        )
        logger.info(
            "Lesson teaching move planned route=gentle_redirect payload=%s",
            json.dumps(
                teaching_move.to_prompt_payload(),
                ensure_ascii=True,
                sort_keys=True,
            ),
        )

    def _gentle_redirect_interpreted_intent(
        self,
        *,
        learner_input: str,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
        evaluation: EvaluationResult | None,
        turn_label: str,
    ) -> str | None:
        normalized_input = normalize_text(learner_input)
        lower = learner_input.casefold()
        if not normalized_input:
            return None
        if self._looks_like_lexicon_query(learner_input):
            return None
        if "中文" in learner_input or "chinese" in lower:
            return "language_support_request"
        if any(
            token in lower
            for token in (
                "i don't know",
                "i dont know",
                "don't know",
                "dont know",
                "not sure",
                "help me",
                "不知道",
                "不懂",
                "不会",
                "随便",
            )
        ):
            return "needs_support"
        if turn_label == "ask_help":
            return "ask_help"
        if any(
            token in lower
            for token in (
                "basketball",
                "football",
                "soccer",
                "play ",
                "played ",
                "weekend",
                "friend",
            )
        ):
            return "off_topic"
        if turn_label == "social" or evaluation == "off_topic":
            return "off_topic"
        if self._looks_like_social_redirect_input(
            learner_input=learner_input,
            state=state,
            block=block,
        ):
            return "off_topic"
        if evaluation in {"incorrect", "unclear", "partially_correct"}:
            token_count = len(normalized_input.split())
            return "short_answer_pullback" if token_count <= 3 else "free_input_pullback"
        return None

    def _gentle_redirect_next_action(self, interpreted_intent: str) -> str:
        if interpreted_intent in {"language_support_request", "needs_support", "ask_help"}:
            return "offer_small_scaffold_then_retry"
        if interpreted_intent == "short_answer_pullback":
            return "connect_or_redirect_to_current_target"
        return "return_to_active_task"

    def _active_prompt_for_teaching_move(
        self,
        *,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
    ) -> str:
        if state.last_teacher_question:
            return self._render_probe_prompt(state.last_teacher_question, block) or ""
        probe = block.entry_probe_questions[0] if block.entry_probe_questions else None
        return self._render_probe_prompt(probe, block) or ""

    def _normalize_teaching_move_anchor(
        self,
        value: str | None,
        *,
        block: TeachingBlockRecord,
    ) -> str:
        if not value:
            return ""
        selected = self._select_classroom_target_phrase_for_block(
            block=block,
            prompt_values=[value],
            include_block_targets=True,
            allow_prompt_cjk=False,
            allow_short_word_target=False,
        )
        return selected or value

    def _target_phrase_for_teaching_move(
        self,
        *,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
        active_prompt: str,
    ) -> str:
        return self._select_classroom_target_phrase_for_block(
            block=block,
            prompt_values=[state.last_teacher_question, active_prompt],
            include_block_targets=True,
            allow_prompt_cjk=False,
            allow_short_word_target=False,
        )

    def _build_answer_turn_policy_prompt(
        self,
        *,
        frame: dict[str, Any],
    ) -> str:
        minimal_runtime_state_enabled = (
            self._answer_turn_policy_minimal_runtime_state_prompt_enabled()
        )
        payload = {
            "turn_kind": "answer_turn_policy",
            "persona_capsule": MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1,
            "instructions": ANSWER_TURN_POLICY_RUBRIC_V1,
            "frame": self._answer_turn_policy_prompt_frame(frame=frame),
            "required_output_schema": {
                "teacherreply": "<final teacher speech>",
                "statepatch": {
                    "currentblockuid": "<one of frame.allowedstatewrites.currentblockuids>",
                    "awaitinganswer": "<boolean>",
                    "lastteacherquestion": "<teacher's current question for the next student reply, or null>",
                },
            },
        }
        if minimal_runtime_state_enabled:
            payload["minimal_runtime_state_prompt_enabled"] = True
        return json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
        )

    def _answer_turn_policy_minimal_runtime_state_prompt_enabled(self) -> bool:
        value = os.getenv(_ANSWER_TURN_MINIMAL_RUNTIME_STATE_ENV)
        if value is None:
            return True
        return value.lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _answer_turn_policy_prompt_frame(
        self,
        *,
        frame: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._answer_turn_policy_minimal_runtime_state_prompt_enabled():
            return frame
        prompt_frame = {
            key: value
            for key, value in frame.items()
            if key not in _ANSWER_TURN_LEGACY_RUNTIME_STATE_FRAME_KEYS
        }
        prompt_frame["runtimestate"] = self._answer_turn_policy_runtime_state_view(
            frame=frame
        )
        return prompt_frame

    def _answer_turn_policy_prompt_metering_overrides(
        self,
        *,
        frame: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._answer_turn_policy_minimal_runtime_state_prompt_enabled():
            return {"minimal_runtime_state_prompt_enabled": False}
        legacy_bytes = self._answer_turn_policy_legacy_runtime_state_bytes(frame)
        minimal_bytes = self._compact_prompt_json_bytes(
            self._answer_turn_policy_runtime_state_view(frame=frame)
        )
        return {
            "minimal_runtime_state_prompt_enabled": True,
            "runtime_state_legacy_frame_bytes": legacy_bytes,
            "runtime_state_minimal_view_bytes": minimal_bytes,
            "runtime_state_savings_candidate_bytes": max(
                0,
                legacy_bytes - minimal_bytes,
            ),
        }

    def _answer_turn_policy_legacy_runtime_state_bytes(
        self,
        frame: dict[str, Any],
    ) -> int:
        return sum(
            self._compact_prompt_json_bytes(frame[key])
            for key in (
                "teacherasked",
                *_ANSWER_TURN_LEGACY_RUNTIME_STATE_FRAME_KEYS,
            )
            if key in frame
        )

    def _compact_prompt_json_bytes(self, value: Any) -> int:
        return len(
            json.dumps(
                value,
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )

    def _answer_turn_policy_audit_repair_reason(self, status: str) -> str:
        reasons: list[str] = []
        if status and status not in {"not_needed", "reviewed_unchanged"}:
            if status.startswith(("applied", "reviewed_applied")):
                reasons.append("reply_quality_revision")
            if "classroom_phrasing_applied" in status:
                reasons.append("classroom_phrasing")
            if "target_phrase_quality_applied" in status:
                reasons.append("target_phrase_quality")
            if "target_source_lock_applied" in status:
                reasons.append("target_source_lock")
            if "generic_praise_stripped" in status:
                reasons.append("generic_praise_stripped")
            if "matched_input_pullback_applied" in status:
                reasons.append("matched_input_pullback")
            if "module_choice_boundary_applied" in status:
                reasons.append("module_choice_boundary")
            if "phonics_tautology_applied" in status:
                reasons.append("phonics_tautology_repaired")
            if "traditional_normalized" in status:
                reasons.append("traditional_normalized")
            if "classroom_pacing_applied" in status:
                reasons.append("classroom_pacing")
            if "redirect_reply_policy_applied" in status:
                reasons.append("redirect_reply_policy")
            if "sentence_tail_repaired" in status:
                reasons.append("sentence_tail_repaired")
        if not reasons:
            return "none"
        return ";".join(self._unique_preserving_order(reasons))

    def _answer_turn_policy_complete_text(self) -> Callable[..., str] | None:
        complete_text = getattr(self.readiness_judge, "complete_text", None)
        if callable(complete_text):
            return complete_text
        return None

    def _build_answer_turn_policy_frame(
        self,
        *,
        block: TeachingBlockRecord,
        state: LessonRuntimeState,
        learner_input: str,
    ) -> dict[str, Any]:
        next_block_uid = block.next_block_uids[0] if block.next_block_uids else None
        next_block = None
        if next_block_uid is not None:
            next_block = self.catalog.get_block(next_block_uid)

        next_block_context = (
            self._answer_turn_policy_block_context(next_block)
            if next_block_uid is not None
            else None
        )
        same_page_blocks = self._answer_turn_policy_allowed_blocks(block)
        learner_input_matches = [
            {
                "blockuid": allowed_block.block_uid,
                "matches": self._answer_turn_policy_block_input_matches(
                    allowed_block,
                    learner_input,
                ),
            }
            for allowed_block in same_page_blocks
        ]
        learner_input_matches = [
            match for match in learner_input_matches if match["matches"]
        ]
        matched_block_uids = {
            str(match["blockuid"]) for match in learner_input_matches
        }
        state_write_blocks = self._answer_turn_policy_state_write_blocks(
            block=block,
            learner_input=learner_input,
            same_page_blocks=same_page_blocks,
        )
        state_write_block_uids = {
            allowed_block.block_uid for allowed_block in state_write_blocks
        }
        last_teacher_question_by_block = {
            allowed_block.block_uid: (
                state.last_teacher_question
                if allowed_block.block_uid == block.block_uid
                else self._render_probe_prompt(
                    self._pick_probe_question(
                        allowed_block,
                        self.catalog.get_page(allowed_block.page_uid),
                    ),
                    allowed_block,
                )
            )
            for allowed_block in state_write_blocks
        }

        return {
            "studentsaid": learner_input,
            "currentblock": self._answer_turn_policy_block_context(block),
            "nextblock": next_block_context,
            "samepageblocks": [
                self._answer_turn_policy_same_page_block_source(
                    allowed_block,
                    current_block_uid=block.block_uid,
                    next_block_uid=(
                        next_block.block_uid if next_block is not None else None
                    ),
                    include_textbook_source=(
                        allowed_block.block_uid in matched_block_uids
                        and allowed_block.block_uid
                        not in {block.block_uid, next_block_uid}
                    ),
                )
                for allowed_block in same_page_blocks
            ],
            "learnerinputmatches": learner_input_matches,
            "teacherasked": state.last_teacher_question,
            "currenttaskfacts": {
                "classroomexchange": {
                    "teacherasked": state.last_teacher_question,
                    "studentsaid": learner_input,
                },
                "textbooksource": {
                    "current": self._answer_turn_policy_textbook_source(block),
                    "next": (
                        self._answer_turn_policy_textbook_source(next_block)
                        if next_block is not None
                        and next_block.block_uid in state_write_block_uids
                        else None
                    ),
                },
            },
            "lessoncontext": self._answer_turn_policy_lesson_context(
                page_uid=block.page_uid,
            ),
            "taskboundary": self._answer_turn_policy_task_boundary(
                block=block,
                state=state,
                same_page_blocks=same_page_blocks,
                next_block=next_block,
            ),
            "recentdialogue": list(state.recent_turns[-2:]),
            "allowedstatewrites": {
                "currentblockuids": [
                    allowed_block.block_uid for allowed_block in state_write_blocks
                ],
                "lastteacherquestionbyblock": last_teacher_question_by_block,
            },
        }

    def _answer_turn_policy_runtime_state_view(
        self,
        *,
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
                role = {
                    "blockuid": block_uid,
                    "relation": str(item.get("relation") or ""),
                    "topic": str(item.get("topic") or ""),
                }
                same_page_block_roles.append(role)

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

    def _answer_turn_policy_allowed_blocks(
        self,
        block: TeachingBlockRecord,
    ) -> list[TeachingBlockRecord]:
        page = self.catalog.get_page(block.page_uid)
        ordered_uids: list[str] = []

        def add_block_uid(block_uid: str | None) -> None:
            if not block_uid or block_uid in ordered_uids:
                return
            try:
                candidate = self.catalog.get_block(block_uid)
            except KeyError:
                return
            if candidate.page_uid != block.page_uid:
                return
            ordered_uids.append(block_uid)

        add_block_uid(block.block_uid)
        for block_uid in block.next_block_uids:
            add_block_uid(block_uid)

        if block.block_uid in page.priority_blocks:
            current_index = page.priority_blocks.index(block.block_uid)
            for index in (current_index - 1, current_index + 1):
                if 0 <= index < len(page.priority_blocks):
                    add_block_uid(page.priority_blocks[index])

        for candidate in self.catalog.blocks_for_page(block.page_uid):
            add_block_uid(candidate.block_uid)

        return [self.catalog.get_block(block_uid) for block_uid in ordered_uids]

    def _answer_turn_policy_state_write_blocks(
        self,
        *,
        block: TeachingBlockRecord,
        learner_input: str,
        same_page_blocks: list[TeachingBlockRecord],
    ) -> list[TeachingBlockRecord]:
        if self._looks_like_lexicon_query(learner_input):
            return [block]
        if self.module_choice_skill.has_module_navigation_request(learner_input):
            return same_page_blocks

        writable_block_uids = {block.block_uid}
        if block.next_block_uids:
            writable_block_uids.add(block.next_block_uids[0])
        for candidate in same_page_blocks:
            if self._answer_turn_policy_block_input_matches(
                candidate,
                learner_input,
            ):
                writable_block_uids.add(candidate.block_uid)
        return [
            candidate
            for candidate in same_page_blocks
            if candidate.block_uid in writable_block_uids
        ]

    def _answer_turn_policy_block_input_matches(
        self,
        block: TeachingBlockRecord,
        learner_input: str,
    ) -> list[dict[str, str]]:
        input_key = _catalog_term_key(learner_input)
        if not input_key:
            return []

        matches: list[dict[str, str]] = []
        for field_name, values in (
            ("vocabulary", block.focus_vocabulary),
            ("examples", block.allowed_answer_scope),
            ("patterns", block.core_patterns),
            ("anchors", block.return_anchors),
        ):
            for value in values:
                if self._answer_turn_policy_value_matches_input(
                    value=value,
                    input_key=input_key,
                ):
                    matches.append({"field": field_name, "text": value})
                    break
        return matches

    def _answer_turn_policy_value_matches_input(
        self,
        *,
        value: str,
        input_key: str,
    ) -> bool:
        if "..." in value or "…" in value:
            return False
        value_key = _catalog_term_key(value)
        if not value_key:
            return False

        value_tokens = value_key.split()
        input_tokens = input_key.split()
        if len(value_tokens) == 1:
            return len(input_tokens) == 1 and value_key == input_key

        value_compact = "".join(value_tokens)
        input_compact = "".join(input_tokens)
        if len(value_compact) < 4 or len(input_compact) < 4:
            return False
        return (
            value_key == input_key
            or value_key in input_key
            or input_key in value_key
            or value_compact == input_compact
            or value_compact in input_compact
            or input_compact in value_compact
        )

    def _answer_turn_policy_task_boundary(
        self,
        *,
        block: TeachingBlockRecord,
        state: LessonRuntimeState,
        same_page_blocks: list[TeachingBlockRecord],
        next_block: TeachingBlockRecord | None,
    ) -> dict[str, Any]:
        next_block_uid = next_block.block_uid if next_block is not None else None
        return {
            "completionunit": "teacherasked_not_full_block",
            "activequestionkind": self._answer_turn_policy_active_question_kind(
                state.last_teacher_question,
            ),
            "currentblockscope": self._answer_turn_policy_block_topic(block),
            "currentblockhasmultipletargets": self._answer_turn_policy_has_multiple_targets(
                block,
            ),
            "progressionrules": [
                "teacherasked_scope_only",
                "complete_teacherasked_then_nextblock",
                "explicit_same_page_request_can_switch_samepageblocks",
                "same_page_switch_say_next_step_not_next_page",
            ],
            "samepageblockroles": [
                self._answer_turn_policy_block_role(
                    candidate,
                    current_block_uid=block.block_uid,
                    next_block_uid=next_block_uid,
                    next_block_uids=block.next_block_uids,
                )
                for candidate in same_page_blocks
            ],
        }

    def _answer_turn_policy_block_role(
        self,
        block: TeachingBlockRecord,
        *,
        current_block_uid: str,
        next_block_uid: str | None,
        next_block_uids: list[str],
    ) -> dict[str, Any]:
        if block.block_uid == current_block_uid:
            relation = "current"
        elif block.block_uid == next_block_uid:
            relation = "next"
        elif block.block_uid in next_block_uids:
            relation = "later_next"
        else:
            relation = "same_page"
        return {
            "blockuid": block.block_uid,
            "relation": relation,
            "topic": self._answer_turn_policy_block_topic(block),
            "primaryquestion": self._answer_turn_policy_primary_question(block),
        }

    def _answer_turn_policy_active_question_kind(self, question: str | None) -> str:
        lower = (question or "").casefold()
        if not lower.strip():
            return "none"
        asks_repeat = any(token in lower for token in ("repeat", "say:", "跟老师读", "说一遍"))
        if "what would you like to drink" in lower:
            return "drink_question_repeat" if asks_repeat else "drink_answer"
        if "what would you like to eat" in lower:
            return "food_question_repeat" if asks_repeat else "food_answer"
        if "hungry" in lower or "饿" in lower:
            return "need_state"
        if "thirsty" in lower or "口渴" in lower:
            return "need_state"
        if self._looks_like_task_instruction(question or ""):
            return "task_instruction"
        return "open_answer"

    def _answer_turn_policy_has_multiple_targets(
        self,
        block: TeachingBlockRecord,
    ) -> bool:
        topic_text = " ".join(
            [
                block.teaching_goal,
                block.teaching_summary,
                *block.focus_vocabulary,
                *block.core_patterns,
                *block.allowed_answer_scope,
                *block.branchable_topics,
            ]
        ).casefold()
        has_food = "food" in topic_text or "eat" in topic_text or "想吃" in topic_text
        has_drink = "drink" in topic_text or "water" in topic_text or "tea" in topic_text or "想喝" in topic_text
        return len(block.core_patterns) > 1 or (has_food and has_drink)

    def _answer_turn_policy_block_topic(self, block: TeachingBlockRecord) -> str:
        text = " ".join(
            [
                block.block_type,
                block.teaching_goal,
                block.teaching_summary,
                *block.focus_vocabulary,
                *block.core_patterns,
                *block.branchable_topics,
            ]
        ).casefold()
        has_food = any(token in text for token in ("food", "eat", "bread", "rice", "chicken", "想吃"))
        has_drink = any(token in text for token in ("drink", "water", "tea", "thirsty", "想喝", "口渴"))
        if "listening" in block.block_type.casefold():
            return "listening"
        if has_food and has_drink:
            return "mixed_food_drink_scene"
        if has_drink:
            return "drink"
        if has_food:
            return "food"
        return block.block_type

    def _answer_turn_policy_primary_question(
        self,
        block: TeachingBlockRecord,
    ) -> str | None:
        for value in [*block.entry_probe_questions, *block.core_patterns]:
            if "?" in value or "？" in value:
                return value
        return block.entry_probe_questions[0] if block.entry_probe_questions else None

    def _answer_turn_policy_lesson_context(
        self,
        *,
        page_uid: str,
    ) -> dict[str, Any]:
        page = self.catalog.get_page(page_uid)
        return {
            "pageuid": page.page_uid,
            "pageintro": page.page_intro_cn,
        }

    def _answer_turn_policy_block_context(
        self,
        block: TeachingBlockRecord,
    ) -> dict[str, Any]:
        return {"blockuid": block.block_uid}

    def _answer_turn_policy_same_page_block_source(
        self,
        block: TeachingBlockRecord,
        *,
        current_block_uid: str | None = None,
        next_block_uid: str | None = None,
        include_textbook_source: bool = False,
    ) -> dict[str, Any]:
        source: dict[str, Any] = {
            "blockuid": block.block_uid,
            "goal": block.teaching_goal,
        }
        if block.block_uid == current_block_uid:
            source["textbooksource_ref"] = "currenttaskfacts.textbooksource.current"
        elif block.block_uid == next_block_uid:
            source["textbooksource_ref"] = "currenttaskfacts.textbooksource.next"
        elif include_textbook_source:
            source["textbooksource"] = self._answer_turn_policy_textbook_source(block)
        else:
            source["textbooksource_ref"] = "omitted_until_matched_or_active"
        return source

    def _answer_turn_policy_textbook_source(
        self,
        block: TeachingBlockRecord,
    ) -> dict[str, Any]:
        if block.block_type == "extension_task":
            return {
                "vocabulary": block.focus_vocabulary[:8],
                "patterns": block.core_patterns[:4],
                "examples": [],
            }
        if self._answer_turn_policy_is_open_slot_dialogue(block):
            return {
                "vocabulary": [],
                "patterns": block.core_patterns[:4],
                "examples": [],
            }
        return {
            "vocabulary": block.focus_vocabulary[:8],
            "patterns": block.core_patterns[:4],
            "examples": block.allowed_answer_scope[:4],
        }

    def _answer_turn_policy_is_open_slot_dialogue(
        self,
        block: TeachingBlockRecord,
    ) -> bool:
        if block.block_type not in {
            "dialogue_core",
            "dialogue_practice",
            "roleplay_task",
        }:
            return False
        source_text = "\n".join(
            [
                *block.core_patterns,
                *block.allowed_answer_scope,
                *block.entry_probe_questions,
            ]
        )
        return "..." in source_text

    def _parse_answer_turn_policy(self, raw: str) -> AnswerTurnPolicyOutput:
        parsed = repair_json(raw, return_objects=True)
        if isinstance(parsed, dict):
            return self._coerce_answer_turn_policy_output(parsed)

        for candidate in self._answer_turn_policy_json_candidates(raw):
            parsed_candidate = repair_json(candidate, return_objects=True)
            if isinstance(parsed_candidate, dict):
                return self._coerce_answer_turn_policy_output(parsed_candidate)

        markdown_policy = self._answer_turn_policy_from_markdown_fields(raw)
        if markdown_policy is not None:
            return markdown_policy

        teacher_reply = self._clean_answer_turn_policy_teacher_reply(raw)
        if teacher_reply:
            return AnswerTurnPolicyOutput(
                teacherreply=teacher_reply,
                statepatch=AnswerTurnPolicyStatePatch(
                    currentblockuid="",
                    awaitinganswer=True,
                    lastteacherquestion=None,
                ),
            )

        return AnswerTurnPolicyOutput.model_validate(parsed)

    def _coerce_answer_turn_policy_output(
        self,
        parsed: dict[str, Any],
    ) -> AnswerTurnPolicyOutput:
        if "statepatch" in parsed:
            return AnswerTurnPolicyOutput.model_validate(parsed)

        teacher_reply = parsed.get("teacherreply") or parsed.get("teacher_reply")
        current_block_uid = parsed.get("currentblockuid") or parsed.get("current_block_uid")
        awaiting_answer = parsed.get("awaitinganswer")
        if awaiting_answer is None:
            awaiting_answer = parsed.get("awaiting_answer")
        if teacher_reply and current_block_uid:
            return AnswerTurnPolicyOutput(
                teacherreply=str(teacher_reply),
                statepatch=AnswerTurnPolicyStatePatch(
                    currentblockuid=str(current_block_uid),
                    awaitinganswer=bool(awaiting_answer),
                    lastteacherquestion=parsed.get("lastteacherquestion")
                    or parsed.get("last_teacher_question"),
                ),
            )

        return AnswerTurnPolicyOutput.model_validate(parsed)

    def _answer_turn_policy_json_candidates(self, raw: str) -> list[str]:
        candidates: list[str] = []
        for match in re.finditer(r"```(?:json)?\s*(.*?)```", raw, flags=re.DOTALL):
            candidate = match.group(1).strip()
            if candidate:
                candidates.append(candidate)
        for start_index, char in enumerate(raw):
            if char != "{":
                continue
            depth = 0
            in_string = False
            escape = False
            for end_index in range(start_index, len(raw)):
                current = raw[end_index]
                if escape:
                    escape = False
                    continue
                if current == "\\":
                    escape = True
                    continue
                if current == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if current == "{":
                    depth += 1
                elif current == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(raw[start_index : end_index + 1])
                        break
        return candidates

    def _answer_turn_policy_from_markdown_fields(
        self,
        raw: str,
    ) -> AnswerTurnPolicyOutput | None:
        field_pattern = re.compile(
            r"(?is)(?:\*\*)?\s*"
            r"(teacherreply|teacher_reply|老师(?:回复|说)|currentblockuid|awaitinganswer|lastteacherquestion)"
            r"\s*(?:\*\*)?\s*[:：]\s*(?:\*\*)?"
        )
        matches = list(field_pattern.finditer(raw))
        if not matches:
            return None

        fields: dict[str, str] = {}
        for index, match in enumerate(matches):
            next_start = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
            key = match.group(1).casefold()
            value = raw[match.end() : next_start].strip()
            if key in {"teacherreply", "teacher_reply"} or key.startswith("老师"):
                fields["teacherreply"] = value
            else:
                fields[key] = value

        teacher_reply = self._clean_answer_turn_policy_teacher_reply(
            fields.get("teacherreply", "")
        )
        if not teacher_reply:
            return None

        return AnswerTurnPolicyOutput(
            teacherreply=teacher_reply,
            statepatch=AnswerTurnPolicyStatePatch(
                currentblockuid=fields.get("currentblockuid", ""),
                awaitinganswer=fields.get("awaitinganswer", "true")
                .strip()
                .casefold()
                .startswith("true"),
                lastteacherquestion=fields.get("lastteacherquestion") or None,
            ),
        )

    def _clean_answer_turn_policy_teacher_reply(self, raw: str) -> str:
        reply = raw.strip()
        reply = re.sub(r"(?is)^```(?:json)?\s*|\s*```$", "", reply).strip()
        reply = re.sub(r"(?im)^\s*(?:teacherreply|teacher_reply|老师(?:回复|说))\s*[:：]\s*", "", reply).strip()
        reply = re.sub(r"(?im)^\s*\*\*(?:teacherreply|teacher_reply|老师(?:回复|说))\s*[:：]?\*\*\s*", "", reply).strip()
        reply = re.sub(r"(?im)^\s*(?:currentblockuid|awaitinganswer|lastteacherquestion)\s*[:：].*$", "", reply).strip()
        reply = reply.strip(" \t\r\n`")
        if (
            len(reply) >= 2
            and reply[0] == reply[-1]
            and reply[0] in {'"', "'", "“", "”"}
        ):
            reply = reply[1:-1].strip()
        return reply[:500].strip()

    def _answer_turn_policy_rejection_reason(
        self,
        *,
        frame: dict[str, Any],
        policy: AnswerTurnPolicyOutput,
    ) -> str | None:
        reply = policy.teacherreply.strip()
        if not reply:
            return "empty_teacher_reply"
        requested_block_uid = policy.statepatch.currentblockuid.strip()
        allowed_block_uids = set(
            frame.get("allowedstatewrites", {}).get("currentblockuids", [])
        )
        if requested_block_uid and requested_block_uid not in allowed_block_uids:
            return "state_patch_block_not_allowed"
        return None

    def _apply_answer_turn_policy_state_boundary(
        self,
        *,
        block: TeachingBlockRecord,
        state: LessonRuntimeState,
        learner_input: str,
        policy: AnswerTurnPolicyOutput,
    ) -> AnswerTurnPolicyOutput:
        if not self._looks_like_lexicon_query(learner_input):
            return policy
        patch = policy.statepatch
        return policy.model_copy(
            update={
                "statepatch": patch.model_copy(
                    update={
                        "currentblockuid": block.block_uid,
                        "awaitinganswer": True,
                        "lastteacherquestion": (
                            patch.lastteacherquestion or state.last_teacher_question
                        ),
                    }
                )
            }
        )

    def _answer_turn_policy_fact_warnings(
        self,
        *,
        policy: AnswerTurnPolicyOutput,
        frame: dict[str, Any],
        learner_input: str,
    ) -> list[str]:
        reply = policy.teacherreply.casefold()
        if not reply:
            return []

        context_text = json.dumps(
            {
                "currenttaskfacts": frame.get("currenttaskfacts", {}),
                "lessoncontext": frame.get("lessoncontext", {}),
                "currentblock": frame.get("currentblock", {}),
                "nextblock": frame.get("nextblock", {}),
            },
            ensure_ascii=False,
        ).casefold()
        learner_tokens = [
            token
            for token in re.split(r"[^a-z0-9\u4e00-\u9fff']+", learner_input.casefold())
            if token and len(token) > 1
        ]
        warnings: list[str] = []
        course_fact_markers = (
            "课本",
            "教材",
            "书上",
            "图片",
            "图上",
            "菜单",
            "上一单元",
            "上节课",
            "之前学",
            "刚才学",
            "现在学",
        )
        if any(marker in reply for marker in course_fact_markers):
            unsupported_tokens = [
                token for token in learner_tokens if token not in context_text
            ]
            if unsupported_tokens:
                warnings.append("unsupported_course_fact_about_student_term")
        return warnings

    def _maybe_revise_answer_turn_policy_reply(
        self,
        *,
        complete_text: Callable[..., str],
        policy: AnswerTurnPolicyOutput,
        frame: dict[str, Any],
        learner_input: str,
    ) -> tuple[AnswerTurnPolicyOutput, str, list[str], list[str], str]:
        issues_before = self._answer_turn_policy_reply_quality_issues(
            policy.teacherreply
        )
        if not issues_before and not self.policy_reply_review_enabled:
            return policy, "not_needed", [], [], ""

        prompt = self._build_answer_turn_policy_reply_revision_prompt(
            frame=frame,
            teacher_reply=policy.teacherreply,
            quality_notes=self._answer_turn_policy_reply_quality_notes(
                policy.teacherreply
            ),
        )
        raw = ""
        call_count_before = active_lesson_llm_call_count()
        try:
            raw = complete_text(
                prompt,
                system_prompt=None,
                history_messages=[],
                max_tokens=260,
                _lesson_audit_tag="teacher_turn_policy.reply_quality_revision",
            )
            if active_lesson_llm_call_count() == call_count_before:
                record_lesson_llm_call(
                    prompt=prompt,
                    completion=raw,
                    system_prompt=None,
                    history_messages=[],
                    llm_provider=self.llm_provider,
                    llm_model=self.llm_model,
                    audit_tag="teacher_turn_policy.reply_quality_revision",
                    mode="complete",
                    status="success",
                    route="answer_turn_policy",
                    turn_label="answer_question",
                )
        except Exception as exc:
            if active_lesson_llm_call_count() == call_count_before:
                record_lesson_llm_call(
                    prompt=prompt,
                    completion=raw,
                    system_prompt=None,
                    history_messages=[],
                    llm_provider=self.llm_provider,
                    llm_model=self.llm_model,
                    audit_tag="teacher_turn_policy.reply_quality_revision",
                    mode="complete",
                    status="error",
                    route="answer_turn_policy",
                    turn_label="answer_question",
                )
            logger.warning(
                "Lesson answer policy quality revision failed status=exception issues=%s error=%s",
                issues_before,
                exc,
            )
            return policy, "failed", issues_before, issues_before, raw

        revised_reply = self._clean_answer_turn_policy_teacher_reply(raw)
        if not revised_reply:
            return policy, "rejected_empty", issues_before, issues_before, raw

        revised_policy = AnswerTurnPolicyOutput(
            teacherreply=revised_reply,
            statepatch=policy.statepatch,
        )
        issues_after = self._answer_turn_policy_reply_quality_issues(
            revised_policy.teacherreply
        )
        fact_warnings_before = self._answer_turn_policy_fact_warnings(
            policy=policy,
            frame=frame,
            learner_input=learner_input,
        )
        fact_warnings_after = self._answer_turn_policy_fact_warnings(
            policy=revised_policy,
            frame=frame,
            learner_input=learner_input,
        )
        repairable_after = set(issues_after) <= {"awkward_mixed_english_cjk"}
        if len(fact_warnings_after) > len(fact_warnings_before):
            return policy, "unresolved", issues_before, issues_after, raw
        if issues_after and not repairable_after:
            return policy, "unresolved", issues_before, issues_after, raw
        if issues_after and repairable_after:
            return (
                revised_policy,
                "applied_needs_classroom_phrasing",
                issues_before,
                issues_after,
                raw,
            )

        if revised_policy.teacherreply.strip() == policy.teacherreply.strip():
            status = "reviewed_unchanged" if not issues_before else "unchanged"
        else:
            status = "reviewed_applied" if not issues_before else "applied"
        return revised_policy, status, issues_before, issues_after, raw

    def _maybe_repair_answer_turn_policy_reply_classroom_phrasing(
        self,
        *,
        policy: AnswerTurnPolicyOutput,
        frame: dict[str, Any],
    ) -> tuple[AnswerTurnPolicyOutput, str]:
        if not self._answer_turn_policy_reply_has_awkward_mixed_english(
            policy.teacherreply
        ):
            return policy, "not_needed"

        repaired_reply = self._repair_answer_turn_policy_reply_classroom_phrasing(
            teacher_reply=policy.teacherreply,
            policy=policy,
            frame=frame,
        )
        if not repaired_reply or repaired_reply.strip() == policy.teacherreply.strip():
            return policy, "unresolved"
        if self._answer_turn_policy_reply_has_awkward_mixed_english(repaired_reply):
            return policy, "unresolved"
        return (
            policy.model_copy(
                update={"teacherreply": repaired_reply.strip()[:500]}
            ),
            "applied",
        )

    def _maybe_repair_answer_turn_policy_target_phrase_quality(
        self,
        *,
        policy: AnswerTurnPolicyOutput,
        frame: dict[str, Any],
    ) -> tuple[AnswerTurnPolicyOutput, str]:
        block = self._answer_turn_policy_current_block_from_frame(
            frame=frame,
            requested_block_uid=policy.statepatch.currentblockuid,
        )
        if block is None:
            return policy, "not_needed"

        allow_short_word_target = self._allow_short_classroom_target_phrase(block)
        bad_anchors = [
            phrase
            for phrase in self._teacher_reply_target_phrase_occurrences(
                policy.teacherreply
            )
            if classroom_target_phrase_reasons(
                phrase,
                allow_short_word_target=allow_short_word_target,
            )
        ]
        if not bad_anchors:
            return policy, "not_needed"

        target_phrase = self._answer_turn_policy_target_phrase(
            policy=policy,
            frame=frame,
            teacher_reply=policy.teacherreply,
        )
        if not target_phrase:
            return policy, "unresolved"
        if classroom_target_phrase_reasons(
            target_phrase,
            allow_short_word_target=allow_short_word_target,
        ):
            return policy, "unresolved"

        learner_phrase = self._answer_turn_policy_spoken_english_phrase(
            str(frame.get("studentsaid") or "")
        )
        repaired_reply = self._answer_turn_policy_structured_repair_reply(
            teacher_reply=policy.teacherreply,
            learner_phrase=learner_phrase,
            target_phrase=target_phrase,
            frame=frame,
        )
        if not repaired_reply or repaired_reply.strip() == policy.teacherreply.strip():
            return policy, "unresolved"
        if any(
            classroom_target_phrase_reasons(
                phrase,
                allow_short_word_target=allow_short_word_target,
            )
            for phrase in self._teacher_reply_target_phrase_occurrences(
                repaired_reply,
                include_loose=False,
            )
        ):
            return policy, "unresolved"
        return (
            policy.model_copy(
                update={"teacherreply": repaired_reply.strip()[:500]}
            ),
            "applied",
        )

    def _teacher_reply_target_phrase_occurrences(
        self,
        teacher_reply: str,
        *,
        include_loose: bool = True,
    ) -> list[str]:
        anchors: list[str] = []
        for match in re.finditer(
            r"(?:我们先说这个|你来读|把这句读出来|跟我读|先读|"
            r"这一步先抓住|先抓住|先回到|回到|老师想让你|"
            r"老师问的是|带起来|Repeat after me|Read after me)"
            r"[:：]?\s*([^。！？\n]+)",
            teacher_reply,
            flags=re.IGNORECASE,
        ):
            anchors.append(self._clean_english_phrase(match.group(1)))
        anchors.extend(
            self._clean_english_phrase(match.group(0))
            for match in _LESSON_MODULE_TITLE_RE.finditer(teacher_reply)
        )
        _ = include_loose
        result: list[str] = []
        seen: set[str] = set()
        for anchor in anchors:
            if not anchor:
                continue
            key = anchor.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(anchor)
        return result

    def _maybe_strip_answer_turn_policy_generic_praise(
        self,
        *,
        policy: AnswerTurnPolicyOutput,
        frame: dict[str, Any],
        learner_input: str,
    ) -> tuple[AnswerTurnPolicyOutput, str]:
        if not self._answer_turn_policy_reply_has_generic_praise(policy.teacherreply):
            return policy, "not_needed"
        stripped_reply = self._strip_generic_praise_from_teacher_reply(
            policy.teacherreply
        )
        if not stripped_reply or stripped_reply.strip() == policy.teacherreply.strip():
            return policy, "unresolved"
        if self._answer_turn_policy_reply_has_generic_praise(stripped_reply):
            return policy, "unresolved"
        compact = re.sub(r"[\s'’`\"“”.,!?！？。；;:：、，-]+", "", stripped_reply)
        if len(compact) < 12:
            return policy, "unresolved"
        stripped_policy = policy.model_copy(update={"teacherreply": stripped_reply})
        fact_warnings_before = self._answer_turn_policy_fact_warnings(
            policy=policy,
            frame=frame,
            learner_input=learner_input,
        )
        fact_warnings_after = self._answer_turn_policy_fact_warnings(
            policy=stripped_policy,
            frame=frame,
            learner_input=learner_input,
        )
        if len(fact_warnings_after) > len(fact_warnings_before):
            return policy, "unresolved"
        return stripped_policy, "stripped"

    def _maybe_repair_answer_turn_policy_incomplete_sentence_tail(
        self,
        policy: AnswerTurnPolicyOutput,
    ) -> tuple[AnswerTurnPolicyOutput, str]:
        repaired_reply = self._repair_incomplete_teacher_response_tail(
            policy.teacherreply
        )
        if repaired_reply == policy.teacherreply.strip():
            return policy, "not_needed"
        return (
            policy.model_copy(update={"teacherreply": repaired_reply}),
            "sentence_tail_repaired",
        )

    def _maybe_lock_answer_turn_policy_target_source(
        self,
        *,
        policy: AnswerTurnPolicyOutput,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
        frame: dict[str, Any],
        learner_input: str,
        evaluation: EvaluationResult,
    ) -> tuple[AnswerTurnPolicyOutput, str]:
        """Keep durable answer-turn targets grounded in the current block."""

        if policy.statepatch.currentblockuid != block.block_uid:
            return policy, "not_needed"
        if not self._answer_turn_policy_uses_durable_target_lock(block):
            return policy, "not_needed"

        requested_question = (policy.statepatch.lastteacherquestion or "").strip()
        if not requested_question:
            return policy, "not_needed"

        durable_target = self._answer_turn_policy_durable_current_target(
            state=state,
            block=block,
            frame=frame,
            learner_input=learner_input,
        )
        if not durable_target:
            return policy, "not_needed"

        requested_phrase = self._answer_turn_policy_target_source_phrase(
            requested_question
        )
        if not requested_phrase:
            return policy, "not_needed"

        requested_key = self._answer_turn_policy_phrase_key(requested_phrase)
        durable_key = self._answer_turn_policy_phrase_key(durable_target)
        if not requested_key or not durable_key:
            return policy, "not_needed"

        should_lock = False
        if requested_key == durable_key:
            should_lock = self._answer_turn_policy_is_surface_instruction_wrapper(
                requested_question
            )
        elif self._answer_turn_policy_is_surface_instruction_wrapper(
            requested_question
        ):
            should_lock = True
        elif self._answer_turn_policy_phrase_matches_learner_input(
            requested_phrase,
            learner_input,
        ) and evaluation not in {"correct", "acceptable"}:
            should_lock = True
        elif self._answer_turn_policy_phrase_is_narrow_block_word_target(
            requested_phrase,
            block=block,
            durable_target=durable_target,
        ):
            should_lock = True

        if not should_lock:
            return policy, "not_needed"

        patch = policy.statepatch.model_copy(
            update={"lastteacherquestion": durable_target}
        )
        return policy.model_copy(update={"statepatch": patch}), "applied"

    def _answer_turn_policy_uses_durable_target_lock(
        self,
        block: TeachingBlockRecord,
    ) -> bool:
        return block.block_type.casefold() in {"dialogue_core"}

    def _answer_turn_policy_durable_current_target(
        self,
        *,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
        frame: dict[str, Any],
        learner_input: str,
    ) -> str:
        reliable_targets = self._answer_turn_policy_reliable_block_targets(block)
        if not reliable_targets:
            return ""
        reliable_keys = {
            self._answer_turn_policy_phrase_key(target) for target in reliable_targets
        }
        learner_key = self._answer_turn_policy_phrase_key(learner_input)
        for value in (frame.get("teacherasked"), state.last_teacher_question):
            if not isinstance(value, str) or not value.strip():
                continue
            if self._answer_turn_policy_is_surface_instruction_wrapper(value):
                continue
            phrase = self._answer_turn_policy_target_source_phrase(value)
            phrase_key = self._answer_turn_policy_phrase_key(phrase)
            if not phrase_key or phrase_key == learner_key:
                continue
            if phrase_key in reliable_keys:
                return phrase
        return ""

    def _answer_turn_policy_reliable_block_targets(
        self,
        block: TeachingBlockRecord,
    ) -> list[str]:
        targets: list[str] = []
        for values in (
            block.return_anchors,
            block.core_patterns,
            block.entry_probe_questions,
        ):
            for value in values:
                for phrase in self._answer_turn_policy_target_source_phrases(value):
                    if not self._answer_turn_policy_is_durable_textbook_target(
                        phrase,
                        block=block,
                    ):
                        continue
                    if phrase not in targets:
                        targets.append(phrase)
        return targets

    def _answer_turn_policy_target_source_phrase(self, value: str | None) -> str:
        phrases = self._answer_turn_policy_target_source_phrases(value)
        return phrases[0] if phrases else ""

    def _answer_turn_policy_target_source_phrases(
        self,
        value: str | None,
    ) -> list[str]:
        if not isinstance(value, str) or not value.strip():
            return []
        phrases: list[str] = []
        raw_phrase = self._answer_turn_policy_clean_target_source_phrase(value)
        if (
            raw_phrase
            and not self._contains_cjk(raw_phrase)
            and not self._answer_turn_policy_is_surface_instruction_wrapper(value)
            and not self._probe_literal_candidates(value)
        ):
            phrases.append(raw_phrase)
        for candidate in self._probe_literal_candidates(value):
            phrase = self._answer_turn_policy_clean_target_source_phrase(candidate)
            if phrase:
                phrases.append(phrase)
        stripped = self._answer_turn_policy_strip_surface_instruction_wrapper(value)
        if stripped:
            phrases.append(stripped)
        for anchor in self._curriculum_anchor_phrases(value):
            phrase = self._answer_turn_policy_clean_target_source_phrase(anchor)
            if phrase:
                phrases.append(phrase)
        if raw_phrase and not self._contains_cjk(raw_phrase):
            phrases.append(raw_phrase)

        unique: list[str] = []
        seen: set[str] = set()
        for phrase in phrases:
            key = self._answer_turn_policy_phrase_key(phrase)
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(phrase)
        return unique

    def _answer_turn_policy_clean_target_source_phrase(self, value: str) -> str:
        cleaned = " ".join(str(value or "").strip().split())
        cleaned = cleaned.strip("“”\"'`，,、；;:：").strip()
        cleaned = re.sub(r"([A-Za-z0-9])['’`]+(?=[.?!。！？]?$)", r"\1", cleaned)
        cleaned = re.sub(r"([A-Za-z0-9])['’`]+\s+([.?!。！？])$", r"\1\2", cleaned)
        return cleaned.strip("“”\"'`，,、；;:：").strip()

    def _answer_turn_policy_is_surface_instruction_wrapper(self, value: str) -> bool:
        if not value.strip():
            return False
        if re.search(r"\bwith\s+me[.?!。！？]?\s*$", value, flags=re.IGNORECASE):
            return True
        return bool(
            re.search(
                r"^\s*(?:can you follow me and say|please repeat|can you repeat|"
                r"can you say that in english|can you say|can you try|"
                r"try to say|try saying|say after me|repeat after me|read after me|"
                r"跟我读|跟老师读|请跟老师说|请跟我说|先听，再说|"
                r"你来读|把这句读出来|读一下这个词|试着读|来，跟老师读)"
                r"\s*[:：]",
                value,
                flags=re.IGNORECASE,
            )
        )

    def _answer_turn_policy_strip_surface_instruction_wrapper(
        self,
        value: str,
    ) -> str:
        match = re.match(
            r"^\s*(?:can you follow me and say|please repeat|can you repeat|"
            r"can you say that in english|can you say|can you try|"
            r"try to say|try saying|say after me|repeat after me|read after me|"
            r"跟我读|跟老师读|请跟老师说|请跟我说|先听，再说|"
            r"你来读|把这句读出来|读一下这个词|试着读|来，跟老师读)"
            r"\s*[:：]\s*[“\"']?(?P<body>.+?)[”\"']?\s*$",
            value,
            flags=re.IGNORECASE,
        )
        if not match:
            return ""
        return self._answer_turn_policy_clean_target_source_phrase(match.group("body"))

    def _answer_turn_policy_is_durable_textbook_target(
        self,
        phrase: str,
        *,
        block: TeachingBlockRecord,
    ) -> bool:
        cleaned = self._answer_turn_policy_clean_target_source_phrase(phrase)
        if not cleaned or "..." in cleaned or "___" in cleaned:
            return False
        if self._is_instruction_anchor_phrase(cleaned):
            return False
        focus_keys = {
            self._answer_turn_policy_phrase_key(value)
            for value in block.focus_vocabulary
        }
        if self._answer_turn_policy_phrase_key(cleaned) in focus_keys:
            return False
        if cleaned.endswith("?"):
            return True
        if cleaned.endswith((".", "!")) and len(cleaned.split()) >= 3:
            return True
        return False

    def _answer_turn_policy_phrase_matches_learner_input(
        self,
        phrase: str,
        learner_input: str,
    ) -> bool:
        phrase_key = self._answer_turn_policy_phrase_key(phrase)
        learner_key = self._answer_turn_policy_phrase_key(learner_input)
        return bool(phrase_key and learner_key and phrase_key == learner_key)

    def _answer_turn_policy_phrase_is_narrow_block_word_target(
        self,
        phrase: str,
        *,
        block: TeachingBlockRecord,
        durable_target: str,
    ) -> bool:
        phrase_key = self._answer_turn_policy_phrase_key(phrase)
        durable_key = self._answer_turn_policy_phrase_key(durable_target)
        if not phrase_key or phrase_key == durable_key:
            return False
        focus_keys = {
            self._answer_turn_policy_phrase_key(value)
            for value in block.focus_vocabulary
        }
        if phrase_key in focus_keys:
            return True
        cleaned = self._clean_english_phrase(phrase)
        return (
            bool(cleaned)
            and not cleaned.endswith(("?", ".", "!"))
            and len(cleaned.split()) <= 3
        )

    def _maybe_repair_answer_turn_policy_matched_input_pullback(
        self,
        *,
        policy: AnswerTurnPolicyOutput,
        frame: dict[str, Any],
        learner_input: str,
        evaluation: EvaluationResult,
    ) -> tuple[AnswerTurnPolicyOutput, str]:
        if evaluation not in {"correct", "acceptable"}:
            return policy, "not_needed"
        if not self._answer_turn_policy_reply_pulls_matched_input_back(
            policy.teacherreply,
            frame=frame,
        ):
            return policy, "not_needed"

        matched_block = self._answer_turn_policy_best_matched_input_block(frame)
        if matched_block is None:
            return policy, "unresolved"

        repaired_reply = self._answer_turn_policy_matched_input_bridge_reply(
            matched_block=matched_block,
            learner_input=learner_input,
        )
        if not repaired_reply:
            return policy, "unresolved"

        patch = policy.statepatch
        last_teacher_question = matched_block.get("primaryquestion")
        return (
            policy.model_copy(
                update={
                    "teacherreply": repaired_reply[:500],
                    "statepatch": patch.model_copy(
                        update={
                            "currentblockuid": matched_block["blockuid"],
                            "awaitinganswer": True,
                            "lastteacherquestion": (
                                last_teacher_question or patch.lastteacherquestion
                            ),
                        }
                    ),
                }
            ),
            "applied",
        )

    def _answer_turn_policy_reply_pulls_matched_input_back(
        self,
        teacher_reply: str,
        *,
        frame: dict[str, Any],
    ) -> bool:
        if not frame.get("learnerinputmatches"):
            return False
        matched_block = self._answer_turn_policy_best_matched_input_block(frame)
        if matched_block is None or matched_block.get("relation") == "current":
            return False
        return bool(
            re.search(
                r"(?:但|不过)?(?:老师|我)?刚才(?:是)?(?:问|让|练)|"
                r"刚才我们练的是|我们先(?:把|学|练好)|先把\s*[A-Za-z]|"
                r"把目标句放小|先听，再说|这一步先抓住|你读这一句|"
                r"我们先说这个|你来读",
                teacher_reply,
            )
        )

    def _answer_turn_policy_best_matched_input_block(
        self,
        frame: dict[str, Any],
    ) -> dict[str, Any] | None:
        allowed = set(
            frame.get("allowedstatewrites", {}).get("currentblockuids", [])
        )
        roles = {
            role.get("blockuid"): role
            for role in frame.get("taskboundary", {}).get("samepageblockroles", [])
            if isinstance(role, dict)
        }
        matches = [
            item
            for item in frame.get("learnerinputmatches", [])
            if isinstance(item, dict)
            and item.get("blockuid") in allowed
            and item.get("blockuid") in roles
        ]
        if not matches:
            return None

        current_block_uid = frame.get("currentblock", {}).get("blockuid")
        for relation in ("later_next", "next", "same_page"):
            for item in matches:
                role = roles[item["blockuid"]]
                if role.get("relation") == relation:
                    return role
        for item in matches:
            if item.get("blockuid") != current_block_uid:
                return roles[item["blockuid"]]
        return roles[matches[0]["blockuid"]]

    def _answer_turn_policy_matched_input_bridge_reply(
        self,
        *,
        matched_block: dict[str, Any],
        learner_input: str,
    ) -> str:
        learner_phrase = (
            self._answer_turn_policy_spoken_english_phrase(learner_input)
            or learner_input.strip()
        )
        if not learner_phrase:
            return ""
        learner_sentence = self._english_sentence(learner_phrase)
        topic = str(matched_block.get("topic") or "")
        if topic == "drink":
            relation = "想喝什么"
        elif topic == "food":
            relation = "想吃什么"
        elif topic == "mixed_food_drink_scene":
            relation = "点餐"
        else:
            relation = "这一块"

        primary_question = str(matched_block.get("primaryquestion") or "").strip()
        if primary_question:
            probe_literals = self._probe_literal_candidates(primary_question)
            question_phrase = probe_literals[0] if probe_literals else primary_question
            question = self._english_question_or_sentence(question_phrase)
            return (
                f"你刚才这句 {learner_sentence} 已经接到{relation}。"
                f"我来问：{question} 你可以用刚才这句回答。"
            )
        return f"你刚才说的是 {learner_sentence}。这个和{relation}有关，我们顺着它练。"

    def _english_question_or_sentence(self, phrase: str) -> str:
        cleaned = self._clean_english_phrase(phrase)
        if not cleaned:
            return ""
        if (
            "?" in phrase
            or re.match(
                r"^(?:what|where|when|who|why|how|is|are|do|does|can)\b",
                cleaned,
                re.IGNORECASE,
            )
        ) and not cleaned.endswith("?"):
            return f"{cleaned}?"
        if cleaned.endswith(("?", "!", ".")):
            return cleaned
        return f"{cleaned}."

    def _maybe_normalize_answer_turn_policy_traditional_chinese(
        self,
        policy: AnswerTurnPolicyOutput,
    ) -> tuple[AnswerTurnPolicyOutput, str]:
        normalized_reply = policy.teacherreply.translate(
            _COMMON_TRADITIONAL_TO_SIMPLIFIED
        )
        if normalized_reply == policy.teacherreply:
            return policy, "not_needed"
        return policy.model_copy(update={"teacherreply": normalized_reply}), "normalized"

    def _maybe_repair_answer_turn_policy_phonics_tautology(
        self,
        *,
        policy: AnswerTurnPolicyOutput,
        frame: dict[str, Any],
        learner_input: str,
    ) -> tuple[AnswerTurnPolicyOutput, str]:
        if not self._teacher_reply_has_phonics_tautology(policy.teacherreply):
            return policy, "not_needed"

        repaired_reply = self._repair_phonics_tautology_reply(policy.teacherreply)
        if not repaired_reply or repaired_reply.strip() == policy.teacherreply.strip():
            return policy, "unresolved"
        if self._teacher_reply_has_phonics_tautology(repaired_reply):
            return policy, "unresolved"

        repaired_policy = policy.model_copy(
            update={"teacherreply": repaired_reply.strip()[:500]}
        )
        fact_warnings_before = self._answer_turn_policy_fact_warnings(
            policy=policy,
            frame=frame,
            learner_input=learner_input,
        )
        fact_warnings_after = self._answer_turn_policy_fact_warnings(
            policy=repaired_policy,
            frame=frame,
            learner_input=learner_input,
        )
        if len(fact_warnings_after) > len(fact_warnings_before):
            return policy, "unresolved"
        return repaired_policy, "applied"

    def _maybe_repair_answer_turn_policy_reply_pacing(
        self,
        *,
        policy: AnswerTurnPolicyOutput,
        frame: dict[str, Any],
        learner_input: str,
    ) -> tuple[AnswerTurnPolicyOutput, str]:
        if not self._teacher_reply_looks_overloaded(
            policy.teacherreply,
            turn_label="answer_question",
        ):
            return policy, "not_needed"

        repaired_reply = self._repair_answer_turn_policy_reply_pacing(
            teacher_reply=policy.teacherreply,
            learner_input=learner_input,
        )
        if not repaired_reply or repaired_reply.strip() == policy.teacherreply.strip():
            return policy, "unresolved"
        if self._teacher_reply_looks_overloaded(
            repaired_reply,
            turn_label="answer_question",
        ):
            return policy, "unresolved"

        repaired_policy = policy.model_copy(
            update={"teacherreply": repaired_reply.strip()[:500]}
        )
        fact_warnings_before = self._answer_turn_policy_fact_warnings(
            policy=policy,
            frame=frame,
            learner_input=learner_input,
        )
        fact_warnings_after = self._answer_turn_policy_fact_warnings(
            policy=repaired_policy,
            frame=frame,
            learner_input=learner_input,
        )
        if len(fact_warnings_after) > len(fact_warnings_before):
            return policy, "unresolved"
        return repaired_policy, "applied"

    def _maybe_repair_answer_turn_policy_module_choice_boundary(
        self,
        *,
        policy: AnswerTurnPolicyOutput,
        frame: dict[str, Any],
        learner_input: str,
    ) -> tuple[AnswerTurnPolicyOutput, str]:
        current_block_uid = str(frame.get("currentblock", {}).get("blockuid") or "")
        if policy.statepatch.currentblockuid != current_block_uid:
            return policy, "not_needed"
        if not self._teacher_reply_has_module_choice_prompt(policy.teacherreply):
            return policy, "not_needed"
        if self.module_choice_skill.has_module_navigation_request(learner_input):
            return policy, "not_needed"

        block = self._answer_turn_policy_current_block_from_frame(
            frame=frame,
            requested_block_uid=policy.statepatch.currentblockuid,
        )
        if block is None:
            return policy, "not_needed"
        active_prompt = str(frame.get("teacherasked") or "").strip()
        if not active_prompt:
            return policy, "not_needed"
        page = self.catalog.get_page(block.page_uid)
        if self._active_prompt_is_page_module_choice(
            page=page,
            active_prompt=active_prompt,
        ):
            policy_prompt = str(policy.statepatch.lastteacherquestion or "").strip()
            if not policy_prompt or self._active_prompt_is_page_module_choice(
                page=page,
                active_prompt=policy_prompt,
            ):
                return policy, "not_needed"
            active_prompt = policy_prompt

        target_phrase = self._answer_turn_policy_target_phrase(
            policy=policy,
            frame=frame,
            teacher_reply=policy.teacherreply,
        )
        if not target_phrase:
            return policy, "not_needed"
        action_fields = self._answer_turn_policy_redirect_action_fields(
            learner_input=learner_input,
            target_phrase=target_phrase,
            active_prompt=active_prompt,
            return_anchor=policy.statepatch.lastteacherquestion,
            block=block,
        )
        repaired_reply = maybe_render_redirect_reply(
            learner_input=learner_input,
            target_phrase=target_phrase,
            teacher_reply=policy.teacherreply,
            block=block,
            active_prompt=active_prompt,
            return_anchor=policy.statepatch.lastteacherquestion,
            action_fields=action_fields,
        )
        if not repaired_reply:
            active_target = (
                self._answer_turn_policy_target_phrase_from_prompt(active_prompt)
                or active_prompt
            )
            active_action_fields = self._answer_turn_policy_redirect_action_fields(
                learner_input=learner_input,
                target_phrase=active_target,
                active_prompt=active_prompt,
                return_anchor=active_target,
                block=block,
            )
            repaired_reply = maybe_render_redirect_reply(
                learner_input=learner_input,
                target_phrase=active_target,
                teacher_reply=(
                    f"你刚才说的是 {learner_input}. 这页的问题是：{active_target}."
                ),
                block=block,
                active_prompt=active_prompt,
                return_anchor=active_target,
                action_fields=active_action_fields,
            )
        if not repaired_reply or repaired_reply.strip() == policy.teacherreply.strip():
            return policy, "unresolved"

        repaired_policy = policy.model_copy(
            update={"teacherreply": repaired_reply.strip()[:500]}
        )
        fact_warnings_before = self._answer_turn_policy_fact_warnings(
            policy=policy,
            frame=frame,
            learner_input=learner_input,
        )
        fact_warnings_after = self._answer_turn_policy_fact_warnings(
            policy=repaired_policy,
            frame=frame,
            learner_input=learner_input,
        )
        if len(fact_warnings_after) > len(fact_warnings_before):
            return policy, "unresolved"
        return repaired_policy, "applied"

    def _maybe_repair_answer_turn_policy_redirect_reply_policy(
        self,
        *,
        policy: AnswerTurnPolicyOutput,
        frame: dict[str, Any],
        learner_input: str,
    ) -> tuple[AnswerTurnPolicyOutput, str]:
        current_block_uid = str(frame.get("currentblock", {}).get("blockuid") or "")
        if policy.statepatch.currentblockuid != current_block_uid:
            return policy, "not_needed"

        block = self._answer_turn_policy_current_block_from_frame(
            frame=frame,
            requested_block_uid=policy.statepatch.currentblockuid,
        )
        if block is None:
            return policy, "not_needed"
        target_phrase = self._answer_turn_policy_target_phrase(
            policy=policy,
            frame=frame,
            teacher_reply=policy.teacherreply,
        )
        if not target_phrase:
            return policy, "not_needed"
        if not looks_like_redirect_reply(policy.teacherreply):
            return policy, "not_needed"

        active_prompt = str(frame.get("teacherasked") or "")
        return_anchor = policy.statepatch.lastteacherquestion
        action_fields = self._answer_turn_policy_redirect_action_fields(
            learner_input=learner_input,
            target_phrase=target_phrase,
            active_prompt=active_prompt,
            return_anchor=return_anchor,
            block=block,
        )
        repaired_reply = maybe_render_redirect_reply(
            learner_input=learner_input,
            target_phrase=target_phrase,
            teacher_reply=policy.teacherreply,
            block=block,
            active_prompt=active_prompt,
            return_anchor=return_anchor,
            action_fields=action_fields,
        )
        if not repaired_reply or repaired_reply.strip() == policy.teacherreply.strip():
            return policy, "not_needed"

        repaired_policy = policy.model_copy(
            update={"teacherreply": repaired_reply.strip()[:500]}
        )
        fact_warnings_before = self._answer_turn_policy_fact_warnings(
            policy=policy,
            frame=frame,
            learner_input=learner_input,
        )
        fact_warnings_after = self._answer_turn_policy_fact_warnings(
            policy=repaired_policy,
            frame=frame,
            learner_input=learner_input,
        )
        if len(fact_warnings_after) > len(fact_warnings_before):
            return policy, "unresolved"
        return repaired_policy, "applied"

    def _answer_turn_policy_redirect_action_fields(
        self,
        *,
        learner_input: str,
        target_phrase: str,
        active_prompt: str,
        return_anchor: str,
        block: TeachingBlockRecord,
    ) -> dict[str, str]:
        current_target = (
            block.teaching_goal
            or block.teaching_summary
            or target_phrase
            or active_prompt
            or return_anchor
        )
        teaching_move = self.teaching_move_planner.plan_gentle_redirect(
            learner_input=learner_input,
            interpreted_intent="redirect_reply_policy",
            current_target=current_target,
            target_phrase=target_phrase,
            active_prompt=active_prompt,
            return_anchor=return_anchor,
            next_action="return_to_active_task",
            correction_kind="redirect_reply_policy",
            route="answer_turn_policy",
            turn_label="answer_question",
            preserve_page_uid=block.page_uid,
            preserve_block_uid=block.block_uid,
            block=block,
        )
        payload = teaching_move.to_prompt_payload()
        fields = payload.get("payload_fields", {})
        if not isinstance(fields, dict):
            return {}
        contract = TeachingMoveActionContract.try_from_payload_fields(fields)
        if contract is None:
            return {}
        return contract.to_payload_fields()

    def _repair_answer_turn_policy_reply_pacing(
        self,
        *,
        teacher_reply: str,
        learner_input: str,
    ) -> str:
        compact = self._compact_overloaded_reply_text(teacher_reply)
        if compact and not self._teacher_reply_looks_overloaded(
            compact,
            turn_label="answer_question",
        ):
            return compact

        if self._teacher_reply_has_module_choice_prompt(teacher_reply):
            return self._compact_module_choice_reply(
                teacher_reply,
                learner_input=learner_input,
            )

        redirect_question = self._compact_redirect_question_reply(
            original=teacher_reply,
            stripped=teacher_reply,
        )
        if redirect_question:
            return redirect_question

        target_text = re.split(r"(?:比如|例如)", teacher_reply, maxsplit=1)[0]
        anchors = self._curriculum_anchor_phrases(target_text)
        learner_phrase = self._answer_turn_policy_spoken_english_phrase(learner_input)
        read_target = self._target_after_read_cue(teacher_reply)
        if read_target:
            parts = []
            if learner_phrase and (
                self._answer_turn_policy_phrase_key(learner_phrase)
                != self._answer_turn_policy_phrase_key(read_target)
            ):
                parts.append(f"你刚才说的是 {self._english_sentence(learner_phrase)}")
            meaning = self._short_meaning_contrast(
                teacher_reply,
                learner_phrase=learner_phrase,
                read_target=read_target,
            )
            if meaning:
                parts.append(meaning)
            if self._answer_turn_policy_target_is_task_instruction(read_target):
                parts.append(
                    f"老师这一步要你做的是：{self._english_sentence(read_target)}"
                )
            else:
                _, read_prompt = self._answer_turn_policy_practice_prompt_pair(
                    read_target,
                    learner_phrase=learner_phrase,
                    seed=teacher_reply,
                )
                parts.append(read_prompt)
            return "\n".join(parts)

        question = next((anchor for anchor in anchors if anchor.endswith("?")), "")
        if question:
            return (
                f"你找到了 {self._english_sentence(question)} "
                f"现在老师问你：{self._english_sentence(question)} 你说自己的答案。"
            )
        return compact

    def _target_after_read_cue(self, teacher_reply: str) -> str | None:
        match = re.search(
            r"(?:跟我读|跟老师读|读一遍|再读一遍|你来读|把这句读出来|"
            r"试着说(?:说)?(?:完整的句子)?|现在试着说(?:完整的句子)?)[：:]\s*"
            r"([A-Za-z][A-Za-z0-9'’]*(?:\s+[A-Za-z0-9][A-Za-z0-9'’]*){0,12}[?.!]?)",
            teacher_reply,
            flags=re.IGNORECASE,
        )
        if match:
            phrase = self._clean_english_phrase(match.group(1))
            if self._is_instruction_anchor_phrase(phrase):
                return None
            return phrase
        target_text = re.split(r"(?:比如|例如)", teacher_reply, maxsplit=1)[0]
        anchors = self._curriculum_anchor_phrases(target_text)
        target_anchors = [
            anchor
            for anchor in anchors
            if not _LESSON_MODULE_TITLE_RE.fullmatch(anchor.strip())
        ]
        for anchor in reversed(target_anchors):
            if len(anchor.split()) >= 2:
                return anchor
        return target_anchors[-1] if target_anchors else None

    def _short_meaning_contrast(
        self,
        teacher_reply: str,
        *,
        learner_phrase: str | None,
        read_target: str,
    ) -> str:
        if not learner_phrase:
            return ""
        learner_meaning = self._meaning_after_phrase(teacher_reply, learner_phrase)
        target_meaning = self._meaning_after_phrase(teacher_reply, read_target)
        if learner_meaning and target_meaning:
            return (
                f"{self._clean_english_phrase(learner_phrase)} 是{learner_meaning}，"
                f"{self._clean_english_phrase(read_target)} 是{target_meaning}。"
            )
        if "不同" in teacher_reply or "不是" in teacher_reply:
            return (
                f"{self._clean_english_phrase(learner_phrase)} 和 "
                f"{self._clean_english_phrase(read_target)} 不一样。"
            )
        return ""

    def _meaning_after_phrase(self, teacher_reply: str, phrase: str) -> str:
        escaped = re.escape(self._clean_english_phrase(phrase))
        match = re.search(
            escaped + r"\s*(?:是|意思是|指的是)[“\"']?([^，。；;”\"']{1,18})",
            teacher_reply,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    def _repair_answer_turn_policy_reply_classroom_phrasing(
        self,
        *,
        teacher_reply: str,
        policy: AnswerTurnPolicyOutput,
        frame: dict[str, Any],
    ) -> str:
        learner_phrase = self._answer_turn_policy_spoken_english_phrase(
            str(frame.get("studentsaid") or "")
        )
        target_phrase = self._answer_turn_policy_target_phrase(
            policy=policy,
            frame=frame,
            teacher_reply=teacher_reply,
        )
        if target_phrase:
            return self._answer_turn_policy_structured_repair_reply(
                teacher_reply=teacher_reply,
                learner_phrase=learner_phrase,
                target_phrase=target_phrase,
                frame=frame,
            )
        return self._insert_sentence_breaks_after_policy_english_phrases(teacher_reply)

    def _answer_turn_policy_structured_repair_reply(
        self,
        *,
        teacher_reply: str,
        learner_phrase: str | None,
        target_phrase: str,
        frame: dict[str, Any],
    ) -> str:
        parts: list[str] = []
        learner_key = self._answer_turn_policy_phrase_key(learner_phrase or "")
        target_key = self._answer_turn_policy_phrase_key(target_phrase)
        if learner_phrase and learner_key and learner_key != target_key:
            parts.append(f"你刚才说的是 {self._english_sentence(learner_phrase)}")
            learner_meaning = self._answer_turn_policy_phrase_meaning_from_reply(
                teacher_reply,
                learner_phrase,
            )
            if learner_meaning:
                parts.append(f"它的意思是“{learner_meaning}”。")

        teacherasked = str(frame.get("teacherasked") or "")
        target_meaning = self._answer_turn_policy_phrase_meaning_from_reply(
            teacher_reply,
            target_phrase,
        )
        practice_read = ""
        if target_phrase.endswith("?"):
            parts.append(f"这一步先听清这个问题：{target_phrase}")
        elif self._answer_turn_policy_target_is_task_instruction(target_phrase):
            parts.append(
                f"老师这一步要你做的是：{self._english_sentence(target_phrase)}"
            )
        elif self._looks_like_meaning_question(teacherasked):
            _, practice_read = self._answer_turn_policy_practice_prompt_pair(
                target_phrase,
                learner_phrase=learner_phrase,
                seed=teacher_reply,
            )
            parts.append(f"这一步老师问的是 {self._english_sentence(target_phrase)}")
        else:
            practice_intro, practice_read = (
                self._answer_turn_policy_practice_prompt_pair(
                    target_phrase,
                    learner_phrase=learner_phrase,
                    seed=teacher_reply,
                )
            )
            parts.append(practice_intro)
        if target_meaning:
            parts.append(f"它的意思是“{target_meaning}”。")
        if practice_read:
            parts.append(practice_read)
        return "\n".join(parts)

    def _answer_turn_policy_target_is_task_instruction(self, target_phrase: str) -> bool:
        cleaned = self._clean_english_phrase(target_phrase).casefold().rstrip(".?!")
        return cleaned.startswith(
            (
                "find ",
                "choose ",
                "say one ",
                "name one ",
                "write ",
                "circle ",
                "match ",
                "look at ",
                "answer ",
            )
        )

    def _answer_turn_policy_practice_prompt_pair(
        self,
        target_phrase: str,
        *,
        learner_phrase: str | None = None,
        seed: str = "",
    ) -> tuple[str, str]:
        target_sentence = self._english_sentence(target_phrase)
        variants = (
            (
                f"我们先说这个：{target_sentence}",
                f"你来读：{target_sentence}",
            ),
            (
                f"我们先说这个：{target_sentence}",
                f"你来读：{target_sentence}",
            ),
            (
                f"先回到课本目标：{target_sentence}",
                f"把这句读出来：{target_sentence}",
            ),
            (
                f"我们把目标句放小：{target_sentence}",
                f"先听，再说：{target_sentence}",
            ),
        )
        return variants[
            self._stable_variant_index(
                learner_phrase or "",
                target_phrase,
                seed,
                len(variants),
            )
        ]

    def _answer_turn_policy_target_phrase(
        self,
        *,
        policy: AnswerTurnPolicyOutput,
        frame: dict[str, Any],
        teacher_reply: str,
    ) -> str | None:
        prompt_values: list[Any] = [
            policy.statepatch.lastteacherquestion,
            frame.get("teacherasked"),
        ]

        question_by_block = (
            frame.get("allowedstatewrites", {}).get("lastteacherquestionbyblock", {})
        )
        requested_question = question_by_block.get(policy.statepatch.currentblockuid)
        prompt_values.append(requested_question)

        current_block_uid = str(frame.get("currentblock", {}).get("blockuid") or "")
        same_page_roles = frame.get("taskboundary", {}).get("samepageblockroles", [])
        if not isinstance(same_page_roles, list):
            same_page_roles = []
        for role in same_page_roles:
            if not isinstance(role, dict) or role.get("blockuid") != current_block_uid:
                continue
            prompt_values.append(role.get("primaryquestion"))

        match = re.search(
            r"老师问的是\s*[“\"']?([A-Za-z][A-Za-z'’]*(?:\s+[A-Za-z][A-Za-z'’]*){0,10})[”\"']?",
            teacher_reply,
            flags=re.IGNORECASE,
        )
        if match:
            prompt_values.append(self._clean_english_phrase(match.group(1)))
        block = self._answer_turn_policy_current_block_from_frame(
            frame=frame,
            requested_block_uid=policy.statepatch.currentblockuid,
        )
        if block is not None:
            phrase = self._select_classroom_target_phrase_for_block(
                block=block,
                prompt_values=prompt_values,
                include_block_targets=True,
                allow_prompt_cjk=False,
                prefer_word_prompt=self._answer_turn_policy_should_prefer_word_prompt(
                    prompt_values=prompt_values,
                    teacher_reply=teacher_reply,
                ),
            )
            return phrase or None
        for value in prompt_values:
            phrase = self._answer_turn_policy_target_phrase_from_prompt(value)
            if phrase:
                return phrase
        return None

    def _answer_turn_policy_target_phrase_from_prompt(
        self,
        value: Any,
    ) -> str | None:
        candidates = self._classroom_target_prompt_candidates(
            value,
            source="prompt",
            allow_cjk=False,
        )
        selection = select_classroom_target_phrase(
            candidates,
            allow_short_word_target=True,
        )
        return selection.phrase or None

    def _answer_turn_policy_current_block_from_frame(
        self,
        *,
        frame: dict[str, Any],
        requested_block_uid: str | None,
    ) -> TeachingBlockRecord | None:
        block_uid = (requested_block_uid or "").strip() or str(
            frame.get("currentblock", {}).get("blockuid") or ""
        )
        if not block_uid:
            return None
        try:
            return self.catalog.get_block(block_uid)
        except KeyError:
            return None

    def _allow_short_classroom_target_phrase(
        self,
        block: TeachingBlockRecord,
    ) -> bool:
        return block.block_type.casefold() in {
            "phonics",
            "phonics_core",
            "vocabulary",
            "vocabulary_core",
        }

    def _select_classroom_target_phrase_for_block(
        self,
        *,
        block: TeachingBlockRecord,
        prompt_values: list[Any],
        include_block_targets: bool,
        allow_prompt_cjk: bool,
        prefer_word_prompt: bool = False,
        allow_short_word_target: bool | None = None,
    ) -> str:
        primary_prompt_candidates: list[ClassroomTargetPhraseCandidate] = []
        deferred_prompt_candidates: list[ClassroomTargetPhraseCandidate] = []
        for value in prompt_values:
            for candidate in self._classroom_target_prompt_candidates(
                value,
                source="prompt",
                allow_cjk=allow_prompt_cjk,
            ):
                if candidate.source.endswith(".word_prompt") and prefer_word_prompt:
                    primary_prompt_candidates.append(candidate)
                elif candidate.source.endswith((".word_prompt", ".cjk_anchor")):
                    deferred_prompt_candidates.append(candidate)
                else:
                    primary_prompt_candidates.append(candidate)
        candidates: list[ClassroomTargetPhraseCandidate] = [
            *primary_prompt_candidates,
        ]
        if include_block_targets:
            candidates.extend(self._classroom_target_block_candidates(block))
        candidates.extend(deferred_prompt_candidates)
        allow_short = (
            self._allow_short_classroom_target_phrase(block)
            if allow_short_word_target is None
            else allow_short_word_target
        )
        selection = select_classroom_target_phrase(
            candidates,
            allow_short_word_target=allow_short,
        )
        return selection.phrase

    def _is_word_probe_prompt(self, value: str) -> bool:
        return value.strip().casefold().startswith(
            ("do you know the word ", "do you know ")
        )

    def _defer_cjk_prompt_anchors(self, value: str) -> bool:
        if not self._contains_cjk(value):
            return False
        anchors = self._curriculum_anchor_phrases(value)
        if len(anchors) > 1:
            return True
        if not anchors:
            return False
        return bool(classroom_target_phrase_reasons(anchors[0]))

    def _answer_turn_policy_should_prefer_word_prompt(
        self,
        *,
        prompt_values: list[Any],
        teacher_reply: str,
    ) -> bool:
        for value in prompt_values:
            if not isinstance(value, str) or not self._is_word_probe_prompt(value):
                continue
            for literal in self._probe_literal_candidates(value):
                if self._answer_turn_policy_phrase_meaning_from_reply(
                    teacher_reply,
                    literal,
                ):
                    return True
        return False

    def _classroom_target_prompt_candidates(
        self,
        value: Any,
        *,
        source: str,
        allow_cjk: bool,
    ) -> list[ClassroomTargetPhraseCandidate]:
        if not isinstance(value, str) or not value.strip():
            return []
        candidates: list[ClassroomTargetPhraseCandidate] = []
        source_prefix = source
        is_word_prompt = self._is_word_probe_prompt(value)
        is_cjk_anchor_prompt = self._defer_cjk_prompt_anchors(value)
        if is_word_prompt:
            source_prefix = f"{source}.word_prompt"
        elif is_cjk_anchor_prompt:
            source_prefix = f"{source}.cjk_anchor"
        if not is_word_prompt and (allow_cjk or not self._contains_cjk(value)):
            candidates.append(
                ClassroomTargetPhraseCandidate(source=source_prefix, text=value)
            )
        for candidate in self._probe_literal_candidates(value):
            phrase = self._clean_english_phrase(candidate)
            if phrase and (allow_cjk or not self._contains_cjk(phrase)):
                candidates.append(
                    ClassroomTargetPhraseCandidate(source=source_prefix, text=phrase)
                )
        for anchor in self._curriculum_anchor_phrases(value):
            phrase = self._clean_english_phrase(anchor)
            if phrase and (allow_cjk or not self._contains_cjk(phrase)):
                candidates.append(
                    ClassroomTargetPhraseCandidate(source=source_prefix, text=phrase)
                )
        return candidates

    def _classroom_target_block_candidates(
        self,
        block: TeachingBlockRecord,
    ) -> list[ClassroomTargetPhraseCandidate]:
        candidates: list[ClassroomTargetPhraseCandidate] = []
        for source, values in (
            ("block.return_anchors", block.return_anchors),
            ("block.core_patterns", block.core_patterns),
            ("block.entry_probe_questions", block.entry_probe_questions),
            ("block.allowed_answer_scope", block.allowed_answer_scope),
            ("block.focus_vocabulary", block.focus_vocabulary),
        ):
            for value in values:
                candidates.extend(
                    self._classroom_target_prompt_candidates(
                        value,
                        source=source,
                        allow_cjk=True,
                    )
                )
        return candidates

    def _answer_turn_policy_spoken_english_phrase(self, text: str) -> str | None:
        if not text.strip():
            return None
        if not self._contains_cjk(text):
            return self._clean_english_phrase(text)
        anchors = self._curriculum_anchor_phrases(text)
        return self._clean_english_phrase(anchors[0]) if anchors else None

    def _answer_turn_policy_phrase_meaning_from_reply(
        self,
        teacher_reply: str,
        phrase: str,
    ) -> str | None:
        phrase = self._clean_english_phrase(phrase)
        if not phrase:
            return None
        phrase_pattern = re.escape(phrase).replace(r"\ ", r"\s+")
        direct_patterns = (
            rf"{phrase_pattern}\s*(?:是|意思是|的意思是)[“\"]([^”\"]{{1,20}})[”\"]",
            rf"{phrase_pattern}\s*是[“\"]([^”\"]{{1,20}})[”\"]的意思",
            rf"{phrase_pattern}[^。！？.!?]{{0,24}}意思是[“\"]([^”\"]{{1,20}})[”\"]",
        )
        for pattern in direct_patterns:
            match = re.search(pattern, teacher_reply, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip().rstrip("。.!！")

        lower_reply = teacher_reply.casefold()
        lower_phrase = phrase.casefold()
        phrase_index = lower_reply.find(lower_phrase)
        if phrase_index >= 0:
            after_phrase = teacher_reply[phrase_index:]
            match = re.search(r"它的意思是[“\"]([^”\"]{1,20})[”\"]", after_phrase)
            if match:
                return match.group(1).strip().rstrip("。.!！")
        return None

    def _insert_sentence_breaks_after_policy_english_phrases(
        self,
        teacher_reply: str,
    ) -> str:
        def _replace_meaning(match: re.Match[str]) -> str:
            phrase = self._english_sentence(match.group("phrase"))
            meaning = match.group("meaning").strip().rstrip("。.!！")
            return f"{phrase}\n意思是“{meaning}”。"

        def _replace(match: re.Match[str]) -> str:
            phrase = match.group("phrase")
            quote = match.group("quote") or ""
            return f"{phrase}{quote}。"

        repaired = re.sub(
            r"(?P<phrase>\b(?:[A-Za-z][A-Za-z'’]*(?:\s+[A-Za-z][A-Za-z'’]*){1,5}|please|clean)\b)[\"”']?[（(](?P<meaning>[\u4e00-\u9fff][^）)\n]{0,40})[）)]",
            _replace_meaning,
            teacher_reply,
            flags=re.IGNORECASE,
        )
        repaired = re.sub(
            r"(?P<phrase>\b(?:[A-Za-z][A-Za-z'’]*(?:\s+[A-Za-z][A-Za-z'’]*){1,5}|please|clean)\b)(?P<quote>[\"”']?)[，,、]\s*(?=[\u4e00-\u9fff])",
            _replace,
            repaired,
            flags=re.IGNORECASE,
        )
        repaired = re.sub(
            r"\b(?P<phrase>turn left|go straight)\s+是",
            lambda match: f"{match.group('phrase')}。这个意思是",
            repaired,
            flags=re.IGNORECASE,
        )
        return repaired.strip()

    def _english_sentence(self, phrase: str) -> str:
        cleaned = self._clean_english_phrase(phrase)
        if not cleaned:
            return ""
        if cleaned.endswith(("?", "!", ".")):
            return cleaned
        return f"{cleaned}."

    def _clean_english_phrase(self, phrase: str) -> str:
        cleaned = " ".join(str(phrase).strip().split())
        cleaned = cleaned.strip("“”\"'`，,、；;:：。！？!?")
        cleaned = re.sub(r"([A-Za-z0-9])['’`]+(?=[.?!。！？]?$)", r"\1", cleaned)
        cleaned = re.sub(r"([A-Za-z0-9])['’`]+\s+([.?!。！？])$", r"\1\2", cleaned)
        return cleaned.strip()

    def _is_instruction_anchor_phrase(self, phrase: str) -> bool:
        compact = re.sub(r"[^a-z0-9]+", "", self._clean_english_phrase(phrase).casefold())
        if not compact:
            return False
        return compact in {
            "repeatafterme",
            "readafterme",
            "listenandrepeat",
            "followme",
            "youreadthissentence",
            "readthissentence",
            "readthisout",
            "canyousay",
            "canyourepeat",
            "canyourepeatafterme",
            "canyouread",
            "canyoutry",
            "doyouknow",
            "doyouknowtheword",
        }

    def _repair_incomplete_teacher_response_tail(self, teacher_reply: str) -> str:
        stripped = teacher_reply.strip()
        if not stripped:
            return ""
        repaired = re.sub(r"(?:[，,：:；;]|[—–-]{1,2})\s*$", "", stripped).rstrip()
        if repaired == stripped:
            return stripped
        if not repaired:
            return stripped
        if repaired.endswith(("。", ".", "!", "！", "?", "？")):
            return repaired
        if re.search(r"[A-Za-z0-9][\"'”’）)]?$", repaired):
            return f"{repaired}."
        return f"{repaired}。"

    def _answer_turn_policy_phrase_key(self, phrase: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", phrase.casefold())

    def _looks_like_meaning_question(self, text: str) -> bool:
        lower = text.casefold()
        return any(token in lower for token in ("mean", "meaning", "什么意思"))

    def _build_answer_turn_policy_reply_revision_prompt(
        self,
        *,
        frame: dict[str, Any],
        teacher_reply: str,
        quality_notes: list[str],
    ) -> str:
        payload = {
            "turn_kind": "answer_turn_policy_reply_quality_revision",
            "instructions": REPLY_QUALITY_REVISION_RUBRIC_V1,
            "frame": self._answer_turn_policy_reply_revision_frame(
                frame=frame,
                teacher_reply=teacher_reply,
                quality_notes=quality_notes,
            ),
        }
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))

    def _answer_turn_policy_reply_revision_frame(
        self,
        *,
        frame: dict[str, Any],
        teacher_reply: str,
        quality_notes: list[str],
    ) -> dict[str, Any]:
        current_task_facts = frame.get("currenttaskfacts")
        if isinstance(current_task_facts, dict):
            textbook_source = current_task_facts.get("textbooksource")
            current_task_facts = {
                "classroomexchange": current_task_facts.get("classroomexchange"),
                "textbooksource": {
                    "current": (
                        textbook_source.get("current")
                        if isinstance(textbook_source, dict)
                        else None
                    ),
                },
            }
        task_boundary = frame.get("taskboundary")
        if isinstance(task_boundary, dict):
            task_boundary = {
                "activequestionkind": task_boundary.get("activequestionkind"),
                "currentblockscope": task_boundary.get("currentblockscope"),
                "currentblockhasmultipletargets": task_boundary.get(
                    "currentblockhasmultipletargets",
                ),
            }
        same_page_blocks = frame.get("samepageblocks")
        if isinstance(same_page_blocks, list):
            same_page_blocks = [
                {
                    "blockuid": block.get("blockuid"),
                    "goal": block.get("goal"),
                    "textbooksource_ref": block.get("textbooksource_ref"),
                }
                for block in same_page_blocks
                if isinstance(block, dict)
            ]
        return {
            "studentsaid": frame.get("studentsaid"),
            "teacherasked": frame.get("teacherasked"),
            "currentblock": frame.get("currentblock"),
            "nextblock": frame.get("nextblock"),
            "samepageblocks": same_page_blocks,
            "currenttaskfacts": current_task_facts,
            "lessoncontext": frame.get("lessoncontext"),
            "taskboundary": task_boundary,
            "originalteacherreply": teacher_reply,
            "qualitynotes": quality_notes,
        }

    def _answer_turn_policy_reply_quality_notes(
        self,
        teacher_reply: str,
    ) -> list[str]:
        notes: list[str] = []
        if self._answer_turn_policy_reply_has_broken_english(teacher_reply):
            notes.append("这句有英文目标句被标点切断，请恢复成完整英文短句。")
        if self._answer_turn_policy_reply_has_awkward_mixed_english(teacher_reply):
            notes.append("这句把英文短语和中文解释挤在同一个分句里，请拆成中文说明、英文目标句和跟读指令。")
        if self._answer_turn_policy_reply_has_traditional_chinese(teacher_reply):
            notes.append("这句混入了繁体中文，请改成简体中文。")
        if self._answer_turn_policy_reply_has_same_page_mislabel(teacher_reply):
            notes.append("这轮只是在同一页内进入另一个小任务，请把“下一页”改成“下一步”或“下一个小任务”。")
        if self._answer_turn_policy_reply_has_revision_meta(teacher_reply):
            notes.append("这句包含给系统看的改写说明，请只保留老师能直接对学生说出口的话。")
        if self._answer_turn_policy_reply_has_generic_praise(teacher_reply):
            notes.append("这句含有空泛表扬，请改成具体回应学生刚说了什么，再给下一小步。")
        if self._teacher_reply_has_phonics_tautology(teacher_reply):
            notes.append("这句把发音规律说成了伪句型，请改成真实音标或口型说明。")
        return notes

    def _answer_turn_policy_reply_quality_issues(
        self,
        teacher_reply: str,
    ) -> list[str]:
        issues: list[str] = []
        if self._answer_turn_policy_reply_has_broken_english(teacher_reply):
            issues.append("broken_english_phrase")
        if self._answer_turn_policy_reply_has_awkward_mixed_english(teacher_reply):
            issues.append("awkward_mixed_english_cjk")
        if self._answer_turn_policy_reply_has_traditional_chinese(teacher_reply):
            issues.append("traditional_chinese")
        if self._answer_turn_policy_reply_has_same_page_mislabel(teacher_reply):
            issues.append("same_page_mislabel")
        if self._answer_turn_policy_reply_has_revision_meta(teacher_reply):
            issues.append("non_oral_revision_meta")
        if self._answer_turn_policy_reply_has_generic_praise(teacher_reply):
            issues.append("generic_praise")
        if self._teacher_reply_has_phonics_tautology(teacher_reply):
            issues.append("phonics_tautology")
        return issues

    def _answer_turn_policy_reply_has_broken_english(
        self,
        teacher_reply: str,
    ) -> bool:
        return bool(
            re.search(
                r"\b(?:I(?:'|’)d|I would)\s+like\s+some\.\s+[A-Za-z]",
                teacher_reply,
            )
            or re.search(
                r"\b(?:I(?:'|’)d|I would)\s+like\.\s+[A-Za-z]",
                teacher_reply,
            )
            or re.search(
                r"\b(?:I(?:'|’)d|I would)\s+like\.\s*(?:开头|回答|说)",
                teacher_reply,
            )
        )

    def _answer_turn_policy_reply_has_awkward_mixed_english(
        self,
        teacher_reply: str,
    ) -> bool:
        text = _LESSON_MODULE_TITLE_RE.sub("", teacher_reply)
        return bool(_ANSWER_TURN_AWKWARD_MIXED_ENGLISH_RE.search(text))

    def _answer_turn_policy_reply_has_traditional_chinese(
        self,
        teacher_reply: str,
    ) -> bool:
        return any(
            chr(codepoint) in teacher_reply
            for codepoint in _COMMON_TRADITIONAL_TO_SIMPLIFIED
        )

    def _answer_turn_policy_reply_has_same_page_mislabel(
        self,
        teacher_reply: str,
    ) -> bool:
        return "下一页" in teacher_reply

    def _answer_turn_policy_reply_has_revision_meta(
        self,
        teacher_reply: str,
    ) -> bool:
        first_line = teacher_reply.strip().splitlines()[0] if teacher_reply.strip() else ""
        if not first_line:
            return False
        meta_markers = ("改写", "修改", "版本", "原始", "要求", "教师回复")
        classroom_markers = ("老师", "你", "我们", "来", "跟")
        return any(marker in first_line for marker in meta_markers) and not any(
            first_line.startswith(marker) for marker in classroom_markers
        )

    def _answer_turn_policy_reply_has_generic_praise(
        self,
        teacher_reply: str,
    ) -> bool:
        normalized = teacher_reply.strip().casefold()
        if not normalized:
            return False
        if re.search(
            r"这句话是对的\s*[（(]?\s*tick\s*[）)]?\s*还是错",
            normalized,
            flags=re.IGNORECASE,
        ):
            return False
        compact = re.sub(r"[\s'’`\"“”.,!?！？。；;:：、，-]+", "", normalized)
        if any(
            phrase in compact
            for phrase in _ANSWER_TURN_GENERIC_PRAISE_COMPACT_PHRASES
        ):
            return True
        if any(
            re.search(pattern, normalized)
            for pattern in _ANSWER_TURN_GENERIC_PRAISE_PATTERNS
        ):
            return True
        return bool(
            re.search(
                r"(?:^|[，,。.!！\s])(?:很棒|真棒|太棒|非常好|完全正确|做得很好|不错)(?:[，,。.!！\s]|$)",
                normalized,
            )
            or re.search(
                r"(?:^|[，,。.!！\s])(?:good job|great job|excellent)(?:[，,。.!！\s]|$)",
                normalized,
            )
        )

    def _teacher_reply_has_phonics_tautology(self, teacher_reply: str) -> bool:
        text = teacher_reply.strip()
        if not text:
            return False
        return bool(
            re.search(
                r"\b(?P<word>[A-Za-z]{2,20})\s+uses\s+the\s+(?P=word)\s+sound\b",
                text,
                flags=re.IGNORECASE,
            )
            or re.search(
                r"\b(?P<word>[A-Za-z]{2,20})\s*(?:用的是|用的就是)\s+(?P=word)\s+sound\b",
                text,
                flags=re.IGNORECASE,
            )
            or re.search(
                r"\b(?P<word>[A-Za-z]{2,20})\s*(?:里|里面)的\s*ow\s*(?:发的是|读的是|是|发的就是)?\s*(?P=word)\s+sound\b",
                text,
                flags=re.IGNORECASE,
            )
            or re.search(
                r"\b(?:cow|flower|down|wow|snow|slow|yellow|window|tomorrow)\s+sound\b",
                text,
                flags=re.IGNORECASE,
            )
        )

    def _repair_phonics_tautology_reply(self, teacher_reply: str) -> str:
        def _sound_for(word: str) -> str:
            return _PHONICS_WORD_SOUND_BY_EXEMPLAR.get(word.casefold(), "")

        def _exemplar_sound_phrase(word: str) -> str:
            sound = _sound_for(word)
            cleaned = self._clean_english_phrase(word)
            if sound:
                return f"{cleaned} 里的 ow 读 {sound}"
            return f"{cleaned} 里的发音"

        def _replace_full_sentence(match: re.Match[str]) -> str:
            return _exemplar_sound_phrase(match.group("word"))

        def _replace_label(match: re.Match[str]) -> str:
            sound = _sound_for(match.group("word"))
            return f"{sound} 音" if sound else match.group(0)

        text = teacher_reply.strip()
        text = re.sub(
            r"\b(?P<word>[A-Za-z]{2,20})\s+uses\s+the\s+(?P=word)\s+sound\b",
            _replace_full_sentence,
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b(?P<word>[A-Za-z]{2,20})\s*(?:用的是|用的就是)\s+(?P=word)\s+sound\b",
            _replace_full_sentence,
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b(?P<word>[A-Za-z]{2,20})\s*(?:里|里面)的\s*ow\s*(?:发的是|读的是|是|发的就是)?\s*(?P=word)\s+sound\b",
            _replace_full_sentence,
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b(?P<word>cow|flower|down|wow|snow|slow|yellow|window|tomorrow)\s+sound\b",
            _replace_label,
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\s+([，,。.!！?？；;])", r"\1", text)
        text = re.sub(r"([。.!！?？]){2,}", r"\1", text)
        return text.strip()

    def _strip_generic_praise_from_teacher_reply(self, teacher_reply: str) -> str:
        stripped = teacher_reply.strip()
        if not stripped:
            return ""

        phrase_alternatives = "|".join(
            re.escape(phrase)
            for phrase in (
                *_ANSWER_TURN_GENERIC_PRAISE_COMPACT_PHRASES,
                "很好",
                "好问题",
                "问得好",
                "good job",
                "great job",
                "excellent",
            )
        )
        praise_patterns = (
            rf"(?:(?<=^)|(?<=[—–~～，,、。.!！?？；;:：\s]))(?:{phrase_alternatives})(?=$|[—–~～，,、。.!！?？；;:：\s])",
            r"(?:(?<=^)|(?<=[—–~～，,、。.!！?？；;:：\s]))(?:这句|你|你刚才|刚才)?(?:说|答|回答|读)(?:对了|好了|准了)(?=$|[—–~～，,、。.!！?？；;:：\s])",
            r"(?:(?<=^)|(?<=[—–~～，,、。.!！?？；;:：\s]))(?:你|你刚才)?(?:直接)?(?:说|答|回答|读)对了(?:目标句|这句|这个句子|这句话|老师的问题)?(?=$|[—–~～，,、。.!！?？；;:：\s])",
            r"(?:(?<=^)|(?<=[—–~～，,、。.!！?？；;:：\s]))(?:这句|这个|这部分|这一步|你|你刚才|刚才)?(?:说|答|回答|读|表达)得(?:很|非常|完全)?(?:对|好|棒|准|清楚|正确|准确|标准|不错)(?=$|[—–~～，,、。.!！?？；;:：\s])",
            r"(?:(?<=^)|(?<=[—–~～，,、。.!！?？；;:：\s]))(?:你|你刚才)?(?:直接)?说出(?:了)?[^。.!！?？；;\n]{0,32}?(?:很棒|真棒|太棒|非常棒|特别棒|很好|非常好|特别好|不错)(?:呀|哦)?(?=$|[—–~～，,、。.!！?？；;:：\s])",
            r"(?:(?<=^)|(?<=[—–~～，,、。.!！?？；;:：\s]))(?:老师|我)?听得(?:很|非常)?清楚(?=$|[—–~～，,、。.!！?？；;:：\s])",
            r"(?:(?<=^)|(?<=[—–~～，,、。.!！?？；;:：\s]))(?:哎呀|噢|哦|好)?(?:你|这个|这个词|这个单词|这个问题|这个点|你这个问题|你问的这个问题)?问得好(?=$|[—–~～，,、。.!！?？；;:：\s])",
            r"(?:你|这个词|这个单词|这个问题|这个点|你这个问题|你问的这个问题|你刚才)?问得(?:很|非常|特别)?(?:好|棒|不错)",
            r"(?:(?<=^)|(?<=[—–~～，,、。.!！?？；;:：\s]))(?:很棒|真棒|太棒|非常棒|特别棒|很好|很不错|真不错|不错|非常好|特别好)的(?:运动|爱好|活动|想法|尝试|回答|句子|表达|选择|问题)(?=$|[—–~～，,、。.!！?？；;:：\s])",
            r"(?:(?<=^)|(?<=[—–~～，,、。.!！?？；;:：\s]))(?:这是|这是个|这个是个)?好(?:运动|想法|尝试|回答|句子|表达|选择|问题)(?=$|[—–~～，,、。.!！?？；;:：\s])",
            r"(?:(?<=^)|(?<=[—–~～，,、。.!！?？；;:：\s]))(?:这个|那个|你的|这个小)?(?:想法|主意|运动|活动|选择)(?:很|真|非常|特别)?(?:棒|好|不错)(?:呀|哦)?(?=$|[—–~～，,、。.!！?？；;:：\s])",
            r"(?:(?<=^)|(?<=[—–~～，,、。.!！?？；;:：\s]))(?:那|这|这样|这也)?(?:很|真|非常|特别)?(?:棒|好|不错)(?:呀|哦)?(?=$|[—–~～，,、。.!！?？；;:：\s])",
            r"(?:(?<=^)|(?<=[—–~～，,、。.!！?？；;:：\s]))(?:句子结构|这句话|这句话说得|这个回答|你的回答|你刚才的回答|回答|答案|这句|这个句子|你的句子|你刚才的句子|表达|说法|这个说法|你的说法|这个表达)(?:是|也)?(?:很|非常|完全)?(?:正确|准确|清楚|标准|好|棒|不错|对)(?:的)?(?=$|[—–~～，,、。.!！?？；;:：\s])",
            r"(?:这个回答|你的回答|你刚才的回答|这次回答|这个句子|你的句子|这句话|这句)(?:是|也)?(?:很|非常|特别)?(?:棒|好|不错|正确|准确|清楚|标准|对)(?:的)?(?![（(]?\s*tick\s*[）)]?\s*还是错)",
            r"(?:(?<=^)|(?<=[—–~～，,、。.!！?？；;:：\s]))(?:你|你刚才|刚才)?[^。.!！?？；;\n]{0,18}?(?:很棒|真棒|太棒|非常棒|特别棒|很好|非常好|特别好|真好|不错)(?:呀|哦)?(?=$|[—–~～，,、。.!！?？；;:：\s])",
        )
        for pattern in praise_patterns:
            stripped = re.sub(pattern, "", stripped, flags=re.IGNORECASE)

        stripped = re.sub(r"[ \t]+", " ", stripped)
        stripped = re.sub(r"[，,、；;]\s*[，,、；;]+", "，", stripped)
        stripped = re.sub(r"[—–~～，,、；;]+\s*([。.!！?？])", r"\1", stripped)
        stripped = re.sub(r"^(?:好|好的|嗯|嗯好)[—–~～，,、。.!！?？；;\s]+", "", stripped)
        stripped = re.sub(r"^[—–~～，,、。.!！?？；;:：\s]+", "", stripped)
        stripped = re.sub(r"\s+([，,、。.!！?？；;])", r"\1", stripped)
        stripped = re.sub(r"([。.!?？])\s*[!！]", r"\1", stripped)
        stripped = re.sub(r"([。.!！?？]){2,}", r"\1", stripped)
        stripped = re.sub(r"([A-Za-z0-9])。", r"\1.", stripped)
        stripped = re.sub(r"([A-Za-z0-9]\.)\s*([\u4e00-\u9fff])", r"\1 \2", stripped)
        return stripped.strip()

    def _generic_praise_stripped_reply_is_usable(
        self,
        teacher_reply: str,
        *,
        fallback_response: str,
        learner_input: str = "",
    ) -> bool:
        if not teacher_reply:
            return False
        if self._answer_turn_policy_reply_has_generic_praise(teacher_reply):
            return False
        compact = re.sub(r"[\s'’`\"“”.,!?！？。；;:：、，-]+", "", teacher_reply)
        if len(compact) < 12:
            return False
        anchors = self._fallback_curriculum_anchor_phrases(fallback_response)
        normalized_reply = teacher_reply.casefold()
        if anchors and any(anchor.casefold() in normalized_reply for anchor in anchors):
            return True
        if self._teacher_reply_has_module_choice_prompt(teacher_reply):
            return True
        lexicon_term = self._lexicon_meaning_question_term(learner_input)
        if (
            lexicon_term
            and lexicon_term.casefold() in normalized_reply
            and self._contains_cjk(teacher_reply)
            and self._teacher_reply_has_next_step_cue(teacher_reply)
        ):
            return True
        learner_anchors = self._curriculum_anchor_phrases(learner_input)
        if learner_anchors and self._teacher_reply_has_next_step_cue(teacher_reply):
            return any(anchor.casefold() in normalized_reply for anchor in learner_anchors)
        reply_anchors = self._curriculum_anchor_phrases(teacher_reply)
        if self._teacher_reply_has_next_step_cue(teacher_reply) and len(reply_anchors) >= 2:
            return True
        if anchors:
            return False
        return len(compact) >= 18

    def _teacher_reply_has_module_choice_prompt(self, teacher_reply: str) -> bool:
        labels = re.findall(r"第[一二三四五六七八九十]+块", teacher_reply)
        has_choice_language = bool(
            re.search(
                r"(?:哪一块|哪块|哪个板块|哪一部分|选一块|先选|选入口)",
                teacher_reply,
            )
        ) or len(set(labels)) >= 2
        if not has_choice_language:
            return False
        if len(set(labels)) >= 2:
            return True
        english_labels = self._curriculum_anchor_phrases(teacher_reply)
        return len({label.casefold() for label in english_labels}) >= 2

    def _curriculum_anchor_phrases(self, text: str) -> list[str]:
        anchors: list[str] = []
        for match in re.finditer(
            r"[A-Za-z][A-Za-z0-9'’.]*(?:\s+[A-Za-z0-9][A-Za-z0-9'’.]*){0,10}",
            text,
        ):
            phrase = " ".join(match.group(0).split())
            compact = re.sub(r"[^a-z0-9]", "", phrase.casefold())
            if len(compact) < 4:
                continue
            if compact in {"good", "great", "excellent", "now", "okay"}:
                continue
            if self._is_instruction_anchor_phrase(phrase):
                continue
            if phrase not in anchors:
                anchors.append(phrase)
        return anchors[:8]

    def _fallback_curriculum_anchor_phrases(self, fallback_response: str) -> list[str]:
        return self._curriculum_anchor_phrases(fallback_response)

    def _teacher_reply_has_next_step_cue(self, teacher_reply: str) -> bool:
        return bool(
            re.search(
                (
                    r"(?:试着|跟我|再说|再来|选一句|回答|读一下|读一读|"
                    r"说一句|用英语|用英文|听一下|听一听|告诉我|"
                    r"先练|先听|先看|先读|先说|现在练|现在听|"
                    r"你可以说|老师来问|问你|听听看|跟着|"
                    r"say|read|try|answer|choose|listen)"
                ),
                teacher_reply,
                flags=re.IGNORECASE,
            )
        )

    def _teacher_response_log_preview(self, teacher_reply: str) -> str:
        return " ".join(teacher_reply.split())[:160]

    def _answer_turn_policy_reply_warnings(self, teacher_reply: str) -> list[str]:
        warnings: list[str] = []
        if self._answer_turn_policy_reply_has_broken_english(teacher_reply):
            warnings.append("broken_english_phrase")
        if self._answer_turn_policy_reply_has_awkward_mixed_english(teacher_reply):
            warnings.append("awkward_mixed_english_cjk")
        if self._answer_turn_policy_reply_has_traditional_chinese(teacher_reply):
            warnings.append("traditional_chinese")
        if self._answer_turn_policy_reply_has_same_page_mislabel(teacher_reply):
            warnings.append("same_page_mislabel")
        if self._answer_turn_policy_reply_has_revision_meta(teacher_reply):
            warnings.append("non_oral_revision_meta")
        if self._answer_turn_policy_reply_has_generic_praise(teacher_reply):
            warnings.append("generic_praise")
        if self._teacher_reply_has_phonics_tautology(teacher_reply):
            warnings.append("phonics_tautology")
        return warnings

    def _answer_turn_policy_last_teacher_question(
        self,
        *,
        requested_question: str | None,
        teacher_response: str,
        fallback_question: str | None,
    ) -> str | None:
        if not requested_question:
            return fallback_question
        stripped = requested_question.strip()
        if not stripped:
            return fallback_question
        if "\\u" in stripped or "\ufffd" in stripped:
            return fallback_question or teacher_response
        if len(stripped) > 220:
            return fallback_question or teacher_response
        return stripped

    def _build_answer_turn_policy_result(
        self,
        *,
        block: TeachingBlockRecord,
        state: LessonRuntimeState,
        policy: AnswerTurnPolicyOutput,
        response_audit: LessonTeacherResponseAuditSignal,
    ) -> LessonTurnResult:
        next_state = state.model_copy(deep=True)
        teacher_response = policy.teacherreply.strip()
        requested_block_uid = policy.statepatch.currentblockuid.strip() or block.block_uid

        if requested_block_uid == block.block_uid:
            next_state.current_block_uid = block.block_uid
            next_state.current_activity_type = "practice"
            next_state.awaiting_answer = policy.statepatch.awaitinganswer
            if policy.statepatch.lastteacherquestion is not None:
                next_state.last_teacher_question = (
                    self._answer_turn_policy_last_teacher_question(
                        requested_question=policy.statepatch.lastteacherquestion,
                        teacher_response=teacher_response,
                        fallback_question=state.last_teacher_question,
                    )
                )
            next_state.same_goal_attempt_count += 1
            next_state.hint_level = max(next_state.hint_level, 1)
            next_state.repair_mode = self._pick_repair_mode(
                block,
                "repeat",
                "word_drill",
                "sentence_drill",
            )
            response_block = block
            teaching_action: TeachingAction = "hint"
        else:
            next_state.same_goal_attempt_count = 0
            next_state.hint_level = 0
            next_state.pedagogy_level = 0
            next_state.model_already_given = False
            next_state.repair_mode = "none"
            next_state.current_activity_type = "teaching"
            try:
                response_block = self.catalog.get_block(requested_block_uid)
            except KeyError:
                response_block = block
            if response_block.page_uid == block.page_uid:
                response_page = self.catalog.get_page(response_block.page_uid)
                next_state.current_block_uid = response_block.block_uid
                next_state.awaiting_answer = policy.statepatch.awaitinganswer
                next_state.last_teacher_question = (
                    self._answer_turn_policy_last_teacher_question(
                        requested_question=policy.statepatch.lastteacherquestion,
                        teacher_response=teacher_response,
                        fallback_question=self._pick_probe_question(
                            response_block,
                            response_page,
                        ),
                    )
                )
            else:
                next_state.current_block_uid = block.block_uid
                next_state.awaiting_answer = policy.statepatch.awaitinganswer
                next_state.last_teacher_question = policy.statepatch.lastteacherquestion
            teaching_action = "confirm"

        self._emit_answer_turn_policy_response(
            state=next_state,
            teaching_action=teaching_action,
            teacher_response=teacher_response,
        )
        return LessonTurnResult(
            page_uid=next_state.current_page_uid,
            block_uid=response_block.block_uid,
            turn_label="answer_question",
            teaching_action=teaching_action,
            retrieval_mode="none",
            teacher_response=teacher_response,
            state=next_state,
            evaluation=next_state.last_eval_result,
            debug_signals=self._build_debug_signals(
                state=next_state,
                retrieval_mode="none",
                turn_label="answer_question",
                teaching_action=teaching_action,
                evaluation=next_state.last_eval_result,
                learner_turn=True,
                response_audit=response_audit,
            ),
        )

    def _emit_teacher_response(
        self,
        *,
        state: LessonRuntimeState,
        turn_label: TurnLabel,
        teaching_action: TeachingAction,
        teacher_response: str,
    ) -> None:
        stream_sink = _ACTIVE_TEACHER_RESPONSE_STREAM.get()
        if stream_sink is None:
            return
        persona_context = self._build_lesson_persona_context(
            state=state,
            learner_memory=LearnerMemorySummary(student_id=state.student_id),
            turn_label=turn_label,
            teaching_action=teaching_action,
        ).model_dump()
        stream_sink.emit_action_metadata(
            teaching_action=teaching_action,
            evaluation=state.last_eval_result,
            branch_active=state.branch_active,
            turn_label=turn_label,
            airi_performance=persona_context["airi_performance"],
        )
        stream_sink.emit_text_delta(teacher_response)

    def _emit_answer_turn_policy_response(
        self,
        *,
        state: LessonRuntimeState,
        teaching_action: TeachingAction,
        teacher_response: str,
    ) -> None:
        self._emit_teacher_response(
            state=state,
            turn_label="answer_question",
            teaching_action=teaching_action,
            teacher_response=teacher_response,
        )

    def _handle_module_choice_turn(
        self,
        *,
        state: LessonRuntimeState,
        learner_input: str,
        current_block: TeachingBlockRecord,
    ) -> LessonTurnResult | None:
        page = self.catalog.get_page(state.current_page_uid)
        overview = self._build_page_overview(page)
        if overview is None:
            if self.module_choice_skill.has_module_navigation_request(
                learner_input,
                allow_bare_index=False,
            ):
                return self._handle_unavailable_page_module_choice(
                    state=state,
                    learner_input=learner_input,
                    page=page,
                    current_block=current_block,
                )
            return None

        is_page_entry_choice = (
            state.current_activity_type == "page_entry"
            and state.awaiting_answer
            and self.page_overview_skill.is_choice_prompt(
                state.last_teacher_question,
                overview,
            )
        )
        choice = self.module_choice_skill.choose(
            learner_input=learner_input,
            overview=overview,
            current_block_uid=state.current_block_uid,
            allow_bare_index=is_page_entry_choice,
        )
        selection_intent = self.module_choice_skill.has_selection_intent(
            learner_input,
            allow_bare_index=is_page_entry_choice,
        )
        if (
            is_page_entry_choice
            and choice is not None
            and not selection_intent
            and state.current_block_uid in choice.module.block_uids
        ):
            return None
        if (
            not is_page_entry_choice
            and choice is not None
            and choice.intent == "choose"
            and not selection_intent
            and not self._page_module_label_selected(learner_input, choice.module)
        ):
            return None
        if choice is None and not is_page_entry_choice:
            return None
        if choice is None and not selection_intent:
            if self._deterministic_open_turn_label(learner_input) != "social":
                return None
            classification_short_answer = self._handle_classification_short_answer_turn(
                state=state,
                learner_input=learner_input,
                current_block=current_block,
            )
            if classification_short_answer is not None:
                return classification_short_answer
            return self._clarify_page_module_choice(
                state=state,
                learner_input=learner_input,
                page=page,
                current_block=current_block,
                overview=overview,
            )
        if choice is None:
            return self._clarify_page_module_choice(
                state=state,
                learner_input=learner_input,
                page=page,
                current_block=current_block,
                overview=overview,
            )
        return self._start_page_module(
            state=state,
            learner_input=learner_input,
            page=page,
            overview=overview,
            choice=choice,
        )

    def _handle_unavailable_page_module_choice(
        self,
        *,
        state: LessonRuntimeState,
        learner_input: str,
        page: PageLessonRecord,
        current_block: TeachingBlockRecord,
    ) -> LessonTurnResult:
        next_state = state.model_copy(deep=True)
        next_state.push_turn_label("navigation")
        next_state.last_eval_result = "unclear"
        next_state.current_block_uid = current_block.block_uid
        next_state.current_activity_type = "practice"
        probe = state.last_teacher_question or self._pick_probe_question(
            current_block,
            page,
        )
        next_state.awaiting_answer = bool(probe)
        next_state.last_teacher_question = probe

        response = "这一页只有这一块，我们继续这一块。"
        formatted_probe = self._render_probe_prompt(probe, current_block)
        if formatted_probe:
            response = f"{response}{formatted_probe}"

        teaching_move = self.teaching_move_planner.plan_single_block_guard(
            learner_input=learner_input,
        )
        logger.info(
            "Lesson teaching move planned route=single_module_navigation_guard payload=%s",
            json.dumps(
                teaching_move.to_prompt_payload(),
                ensure_ascii=True,
                sort_keys=True,
            ),
        )

        audit = LessonTeacherResponseAuditSignal(
            source="deterministic",
            llm_called=False,
            llm_provider=self.llm_provider,
            latency_ms=0,
            fallback_used=False,
            fallback_reason="none",
            route="single_module_navigation_guard",
        )
        logger.info(
            "Lesson teacher response audit turn_label=navigation llmcalled=false llmprovider=%s latencyms=0 fallbackused=false fallbackreason=none teacherresponse_source=deterministic response_chars=%d route=single_module_navigation_guard",
            self.llm_provider,
            len(response),
        )
        self._emit_teacher_response(
            state=next_state,
            turn_label="navigation",
            teaching_action="redirect",
            teacher_response=response,
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
                response_audit=audit,
            ),
        )

    def _clarify_page_module_choice(
        self,
        *,
        state: LessonRuntimeState,
        learner_input: str,
        page: PageLessonRecord,
        current_block: TeachingBlockRecord,
        overview: PageOverview,
    ) -> LessonTurnResult:
        next_state = state.model_copy(deep=True)
        next_state.push_turn_label("navigation")
        next_state.last_eval_result = "unclear"
        next_state.awaiting_answer = True
        next_state.last_teacher_question = overview.choice_prompt
        response = self._render_module_choice_clarification(
            overview=overview,
            learner_input=learner_input,
            page_uid=page.page_uid,
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
            teacher_response=response.text,
            state=next_state,
            evaluation=next_state.last_eval_result,
            debug_signals=self._build_debug_signals(
                state=next_state,
                retrieval_mode="none",
                turn_label="navigation",
                teaching_action="redirect",
                evaluation=next_state.last_eval_result,
                learner_turn=True,
                response_audit=response.audit,
            ),
        )

    def _start_page_module(
        self,
        *,
        state: LessonRuntimeState,
        learner_input: str,
        page: PageLessonRecord,
        overview: PageOverview,
        choice: ModuleChoice,
    ) -> LessonTurnResult:
        selected_module = choice.module
        if selected_module not in overview.modules:
            raise ValueError("selected module does not belong to the current page")
        next_state = state.model_copy(deep=True)
        next_state.push_turn_label("navigation")
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
        if choice.intent == "auto":
            response = f"好，我来安排，我们先从 {selected_module.label} 开始。"
        elif choice.intent in {"next", "previous", "switch"}:
            response = f"好，我们换到 {selected_module.label}。"
        else:
            response = f"好，我们先从 {selected_module.label} 开始。"
        if formatted_probe:
            response = f"{response}{formatted_probe}"
        response = self._respond_teacher_turn(
            learner_input=learner_input,
            turn_label="navigation",
            decision=PlannerDecision(
                teaching_action="probe",
                retrieval_mode="none",
                response_focus=(
                    "Confirm the selected page module as a choice, not as an answer score, "
                    "and start its first tiny task without generic praise."
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
            teacher_response=response.text,
            state=next_state,
            evaluation=next_state.last_eval_result,
            debug_signals=self._build_debug_signals(
                state=next_state,
                retrieval_mode="none",
                turn_label="navigation",
                teaching_action="probe",
                evaluation=next_state.last_eval_result,
                learner_turn=True,
                response_audit=response.audit,
            ),
        )

    def _handle_classification_short_answer_turn(
        self,
        *,
        state: LessonRuntimeState,
        learner_input: str,
        current_block: TeachingBlockRecord,
    ) -> LessonTurnResult | None:
        decision = classify_short_answer_for_task(
            learner_input=learner_input,
            block=current_block,
            last_teacher_question=state.last_teacher_question,
        )
        if decision is None:
            return None

        next_state = state.model_copy(deep=True)
        next_state.push_turn_label("answer_question")
        next_state.current_activity_type = "practice"
        next_state.awaiting_answer = True
        next_state.last_teacher_question = classification_short_answer_next_prompt(
            decision,
        )
        next_state.last_eval_result = classification_short_answer_evaluation(decision)
        next_state.same_goal_attempt_count += 1
        next_state.hint_level = max(next_state.hint_level, 1)
        next_state.repair_mode = self._pick_repair_mode(
            current_block,
            "choice_probe",
            "word_drill",
            "repeat",
        )

        response = render_classification_short_answer_reply(decision)
        audit = LessonTeacherResponseAuditSignal(
            source="policy_repaired",
            llm_called=False,
            llm_provider=self.llm_provider,
            latency_ms=0,
            fallback_used=False,
            fallback_reason="none",
            repair_reason="classification_short_answer_policy",
            route="classification_short_answer_policy",
        )
        logger.info(
            "Lesson classification short-answer policy page_uid=%s block_uid=%s input=%s kind=%s matched_category=%s target_category=%s repair_reason=%s response_chars=%d",
            next_state.current_page_uid,
            current_block.block_uid,
            learner_input,
            decision.kind,
            decision.matched_category,
            decision.target_category,
            audit.repair_reason,
            len(response),
        )
        logger.info(
            "Lesson teacher response audit turn_label=answer_question llmcalled=false llmprovider=%s latencyms=0 fallbackused=false fallbackreason=none teacherresponse_source=policy_repaired response_chars=%d route=classification_short_answer_policy repair_reason=%s",
            self.llm_provider,
            len(response),
            audit.repair_reason,
        )
        self._emit_teacher_response(
            state=next_state,
            turn_label="answer_question",
            teaching_action="hint",
            teacher_response=response,
        )
        return LessonTurnResult(
            page_uid=next_state.current_page_uid,
            block_uid=current_block.block_uid,
            turn_label="answer_question",
            teaching_action="hint",
            retrieval_mode="none",
            teacher_response=response,
            state=next_state,
            evaluation=next_state.last_eval_result,
            debug_signals=self._build_debug_signals(
                state=next_state,
                retrieval_mode="none",
                turn_label="answer_question",
                teaching_action="hint",
                evaluation=next_state.last_eval_result,
                learner_turn=True,
                response_audit=audit,
            ),
        )

    def _handle_task_resize_turn(
        self,
        *,
        state: LessonRuntimeState,
        learner_input: str,
        current_block: TeachingBlockRecord,
    ) -> LessonTurnResult | None:
        if state.branch_active:
            return None

        answer_scope = self._evaluation_answer_scope(
            current_block,
            state.last_teacher_question,
        )
        resize = self.task_resize_skill.resize(
            learner_input=learner_input,
            focus_vocabulary=current_block.focus_vocabulary,
            core_patterns=current_block.core_patterns,
            answer_scope=answer_scope,
            fallback_target=self._best_model_answer(
                current_block,
                state.last_teacher_question,
            ),
        )
        if resize is None:
            return None

        next_state = state.model_copy(deep=True)
        next_state.push_turn_label("ask_help")
        next_state.current_activity_type = "practice"
        next_state.awaiting_answer = True
        next_state.last_eval_result = None
        next_state.hint_level = max(next_state.hint_level, 1)
        next_state.repair_mode = f"task_resize_{resize.intent}"
        prior_resize_anchor = (
            state.return_anchor
            if state.repair_mode.startswith("task_resize_")
            else None
        )
        next_state.return_anchor = prior_resize_anchor or state.last_teacher_question
        next_state.return_target = resize.target
        next_state.last_teacher_question = f"Can you repeat: {resize.target}"

        response = self._render_task_resize_response(resize)
        response = self._respond_teacher_turn(
            learner_input=learner_input,
            turn_label="ask_help",
            decision=PlannerDecision(
                teaching_action="hint",
                retrieval_mode="none",
                response_focus=(
                    "Acknowledge that the task felt too large, shrink it to the "
                    "current target, and ask for one short repeat without sounding templated."
                ),
            ),
            state=next_state,
            page=self.catalog.get_page(next_state.current_page_uid),
            block=current_block,
            fallback_response=response,
        )
        return LessonTurnResult(
            page_uid=next_state.current_page_uid,
            block_uid=current_block.block_uid,
            turn_label="ask_help",
            teaching_action="hint",
            retrieval_mode="none",
            teacher_response=response.text,
            state=next_state,
            evaluation=next_state.last_eval_result,
            debug_signals=self._build_debug_signals(
                state=next_state,
                retrieval_mode="none",
                turn_label="ask_help",
                teaching_action="hint",
                evaluation=next_state.last_eval_result,
                learner_turn=True,
                response_audit=response.audit,
            ),
        )

    def _handle_task_resize_follow_up(
        self,
        *,
        state: LessonRuntimeState,
        learner_input: str,
        current_block: TeachingBlockRecord,
    ) -> LessonTurnResult | None:
        if state.branch_active or not state.repair_mode.startswith("task_resize_"):
            return None
        if not state.return_anchor or not state.return_target:
            return None
        if not self._matches_task_resize_target(learner_input, state.return_target):
            return None

        next_state = state.model_copy(deep=True)
        next_state.push_turn_label("answer_question")
        next_state.last_eval_result = "acceptable"
        next_state.same_goal_attempt_count = 0
        next_state.hint_level = 0
        next_state.pedagogy_level = 0
        next_state.model_already_given = False
        next_state.repair_mode = "none"
        next_state.current_activity_type = "practice"
        next_state.awaiting_answer = True
        original_question = state.return_anchor
        next_state.last_teacher_question = original_question
        next_state.return_anchor = None
        next_state.return_target = None

        prompt = self._render_probe_prompt(original_question, current_block)
        response = (
            f"好，这一小步会了。现在回到完整任务：{prompt}"
            if prompt
            else f"好，这一小步会了。现在回到完整任务：{original_question}"
        )
        response = self._respond_teacher_turn(
            learner_input=learner_input,
            turn_label="answer_question",
            decision=PlannerDecision(
                teaching_action="confirm",
                retrieval_mode="none",
                response_focus=(
                    "Confirm the resized step, then return to the exact current task "
                    "without advancing to another block."
                ),
            ),
            state=next_state,
            page=self.catalog.get_page(next_state.current_page_uid),
            block=current_block,
            fallback_response=response,
        )
        return LessonTurnResult(
            page_uid=next_state.current_page_uid,
            block_uid=current_block.block_uid,
            turn_label="answer_question",
            teaching_action="confirm",
            retrieval_mode="none",
            teacher_response=response.text,
            state=next_state,
            evaluation=next_state.last_eval_result,
            debug_signals=self._build_debug_signals(
                state=next_state,
                retrieval_mode="none",
                turn_label="answer_question",
                teaching_action="confirm",
                evaluation=next_state.last_eval_result,
                learner_turn=True,
                response_audit=response.audit,
            ),
        )

    def _matches_task_resize_target(self, learner_input: str, target: str) -> bool:
        normalized_input = normalize_text(learner_input)
        normalized_target = normalize_text(target)
        if not normalized_input or not normalized_target:
            return False
        if normalized_input == normalized_target:
            return True
        target_tokens = self._teacher_tokens(target)
        input_tokens = self._teacher_tokens(learner_input)
        return len(target_tokens) == 1 and bool(target_tokens & input_tokens)

    def _render_task_resize_response(self, resize: TaskResize) -> str:
        if resize.intent == "word":
            return f"可以。我们先缩到一个词：{resize.target}。你跟老师读：{resize.target}"
        if resize.intent == "slow":
            return f"可以，慢一点。先跟老师读这一小段：{resize.target}"
        return f"可以，我们拆小一点。先读这一段：{resize.target}"

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
            teacher_response=response.text,
            state=next_state,
            evaluation=next_state.last_eval_result,
            debug_signals=self._build_debug_signals(
                state=next_state,
                retrieval_mode="none",
                turn_label="answer_question",
                teaching_action="confirm",
                evaluation=next_state.last_eval_result,
                learner_turn=True,
                response_audit=response.audit,
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
            if self._uses_concrete_item_task_scaffold(block):
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
            if self._uses_concrete_item_task_scaffold(block):
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
            teacher_response=response.text,
            state=state,
            evaluation=state.last_eval_result,
            debug_signals=self._build_debug_signals(
                state=state,
                retrieval_mode="none",
                turn_label="answer_question",
                teaching_action="confirm",
                evaluation=state.last_eval_result,
                learner_turn=True,
                response_audit=response.audit,
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
            teacher_response=response.text,
            state=state,
            evaluation=state.last_eval_result,
            debug_signals=self._build_debug_signals(
                state=state,
                retrieval_mode="none",
                turn_label="answer_question",
                teaching_action=action,
                evaluation=state.last_eval_result,
                learner_turn=True,
                response_audit=response.audit,
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
        module_choice = self._handle_module_choice_turn(
            state=state,
            learner_input=learner_input,
            current_block=block,
        )
        if module_choice is not None:
            return module_choice

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
                response.text,
                learner_memory=learner_memory,
                recall_status=recall_status,
                recall_summary=recall_summary,
                response_audit=response.audit,
            )

        if route_label == "ask_knowledge":
            state.push_turn_label("ask_knowledge")
            fallback_selection = self.retriever.select(
                current_page_uid=state.current_page_uid,
                current_block_uid=block.block_uid,
                query=learner_input,
            )
            fallback_selection = self._with_current_task_branch_anchor(
                fallback_selection,
                state=state,
                block=block,
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
            selection = self._with_current_task_branch_anchor(
                selection,
                state=state,
                block=block,
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
            lexicon_query = self._looks_like_lexicon_query(learner_input)
            active_prompt = (
                self._render_probe_prompt(state.last_teacher_question, block)
                if state.awaiting_answer
                else None
            )
            if lexicon_query:
                active_prompt = self._lexicon_current_task_return_anchor(
                    state=state,
                    block=block,
                    page=page,
                    active_prompt=active_prompt,
                )
            fallback_response = self._render_knowledge_response(
                selection=selection,
                current_block=block,
                page=page,
                support_hits=support_hits,
                learner_input=learner_input,
                active_prompt=active_prompt,
            )
            responder_return_anchor = (
                active_prompt
                if lexicon_query and active_prompt
                else decision.return_anchor or selection.return_anchor or active_prompt
            )
            if lexicon_query:
                teaching_move = self.teaching_move_planner.plan_vocab_answer_return(
                    learner_input=learner_input,
                    retrieval_mode=selection.mode,
                    return_anchor=responder_return_anchor,
                    active_prompt=active_prompt,
                    retrieval_count=len(selection.block_uids),
                    support_count=len(support_hits),
                )
                logger.info(
                    "Lesson teaching move planned route=vocab_answer_return payload=%s",
                    json.dumps(
                        teaching_move.to_prompt_payload(),
                        ensure_ascii=True,
                        sort_keys=True,
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
                return_anchor=responder_return_anchor,
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
                response.text,
                retrieved_block_uids=selection.block_uids,
                support_entry_uids=[item.entry_uid for item in support_hits],
                return_anchor=responder_return_anchor,
                branch_reason=decision.branch_reason or selection.branch_reason,
                learner_memory=learner_memory,
                recall_status=recall_status,
                recall_summary=recall_summary,
                response_audit=response.audit,
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
                response.text,
                return_anchor=state.return_anchor,
                learner_memory=learner_memory,
                recall_status=recall_status,
                recall_summary=recall_summary,
                response_audit=response.audit,
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
            response.text,
            learner_memory=learner_memory,
            recall_status=recall_status,
            recall_summary=recall_summary,
            response_audit=response.audit,
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
        if route_label == "ask_knowledge":
            return True
        if route_label == "ask_help":
            return not self._looks_like_current_task_related_input(
                learner_input=learner_input,
                state=state,
                block=block,
            )
        if evaluation == "off_topic":
            return True
        return self._looks_like_social_redirect_input(
            learner_input=learner_input,
            state=state,
            block=block,
        )

    def _should_preempt_answer_turn_with_knowledge(self, learner_input: str) -> bool:
        """Route explicit vocabulary questions before answer-turn policy evaluates them."""

        return _extract_lexicon_query_term(learner_input) is not None

    def _looks_like_current_task_related_input(
        self,
        *,
        learner_input: str,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
    ) -> bool:
        """Keep related wrong answers in the active task instead of routing away."""

        normalized_input = normalize_text(learner_input)
        if not normalized_input:
            return False

        task_literals = {
            normalize_text(candidate)
            for candidate in [
                *self._probe_literal_candidates(state.last_teacher_question),
                *block.core_patterns,
                *block.return_anchors,
            ]
            if candidate
        }
        if normalized_input in task_literals:
            return True

        learner_tokens = self._teacher_tokens(learner_input)
        if not learner_tokens:
            return False

        lesson_tokens = self._teacher_tokens(state.last_teacher_question or "")
        for value in [
            *block.focus_vocabulary,
            *block.core_patterns,
            *block.allowed_answer_scope,
            *block.return_anchors,
        ]:
            lesson_tokens.update(self._teacher_tokens(value))
        return bool(learner_tokens & lesson_tokens)

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
        response_audit: LessonTeacherResponseAuditSignal | None = None,
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
                response_audit=response_audit,
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
        response_audit: LessonTeacherResponseAuditSignal | None = None,
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
            response_audit=response_audit,
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
            persona_source=MILI_PERSONA_CAPSULE_SOURCE,
            persona_version=MILI_PERSONA_CAPSULE_VERSION,
            capsule_name=str(MILI_PERSONA_CAPSULE_V1["name"]),
            full_soul_injected=False,
            answer_turn_policy_persona_capsule_enabled=True,
            current_llm_call_persona_capsule_injected=False,
            persona_capsule_bytes_configured=(
                MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_BYTES
            ),
            persona_capsule_bytes_metered=0,
            soul_path=MILI_PERSONA_SOUL_PATH,
            teacher_kernel_used=True,
            interests_available=bool(MILI_PERSONA_CAPSULE_V1.get("interests")),
            interests_runtime_usage=MILI_PERSONA_INTERESTS_RUNTIME_USAGE,
            interests_answer_turn_policy_usage=(
                MILI_PERSONA_INTERESTS_ANSWER_TURN_POLICY_USAGE
            ),
            capsule_prompt_status=MILI_PERSONA_CAPSULE_PROMPT_STATUS,
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
        if active_prompt and selection.mode != "branch":
            support_prefix = self._render_support_prefix(support_hits)
            if self._active_prompt_is_page_module_choice(
                page=page,
                active_prompt=active_prompt,
            ):
                if support_prefix:
                    return self._render_module_choice_lexicon_return(
                        support_prefix=support_prefix,
                        active_prompt=active_prompt,
                        learner_input=learner_input,
                        page_uid=page.page_uid,
                    )
            if support_prefix and self._looks_like_lexicon_query(learner_input):
                return f"{support_prefix}。{self._render_active_prompt_return(active_prompt)}"
        response = self._render_retrieval_response(
            selection,
            current_block,
            query=learner_input,
            support_hits=support_hits,
        )
        if active_prompt and selection.mode != "branch":
            return f"{response} {self._render_active_prompt_return(active_prompt)}"
        return response

    def _render_module_choice_lexicon_return(
        self,
        *,
        support_prefix: str,
        active_prompt: str,
        learner_input: str,
        page_uid: str,
    ) -> str:
        choices = self._choice_text_from_module_choice_prompt(active_prompt)
        if choices:
            variants = (
                f"{support_prefix}。接下来选入口：{choices}，你选哪一块？",
                f"{support_prefix}。这个意思先够用。接下来从 {choices} 里选一块。",
                f"{support_prefix}。我们接着回到课本，先选：{choices}。",
            )
        else:
            variants = (
                f"{support_prefix}。{self._render_active_prompt_return(active_prompt)}",
                f"{support_prefix}。这个意思先够用。{self._render_active_prompt_return(active_prompt)}",
                f"{support_prefix}。我们接着回到课本。{self._render_active_prompt_return(active_prompt)}",
            )
        return variants[self._stable_variant_index(page_uid, learner_input, len(variants))]

    def _choice_text_from_module_choice_prompt(self, active_prompt: str) -> str:
        match = re.search(
            r"可以说\s*(.+?)[。.!！?？]?$",
            active_prompt.strip(),
            flags=re.IGNORECASE,
        )
        if not match:
            return ""
        return match.group(1).strip(" 。.!！?？")

    def _render_active_prompt_return(self, active_prompt: str) -> str:
        prompt = re.sub(r"\s+", " ", active_prompt).strip()
        if not prompt:
            return "回到刚才的小任务。"
        for prefix in (
            "先跟老师读一遍：",
            "先跟老师读：",
            "跟我读：",
            "先试着说一遍：",
            "先试试：",
            "先听示范：",
        ):
            if prompt.startswith(prefix):
                return f"回到刚才的小任务，{prompt}"
        if prompt.startswith("现在"):
            return f"回到刚才的小任务：{prompt}"
        return f"回到刚才的小任务：{prompt}"

    def _active_prompt_is_page_module_choice(
        self,
        *,
        page: PageLessonRecord,
        active_prompt: str,
    ) -> bool:
        overview = self._build_page_overview(page)
        return bool(
            overview is not None
            and self.page_overview_skill.is_choice_prompt(active_prompt, overview)
        )

    def _lookup_support_hits(
        self,
        *,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
        learner_input: str,
        selection,
    ) -> list[SupportMatch]:
        catalog_gloss_hit = self.catalog.support_match_for_catalog_gloss(
            page_uid=state.current_page_uid,
            query=learner_input,
        )
        catalog_hits = [catalog_gloss_hit] if catalog_gloss_hit is not None else []
        if self.support_retriever is None:
            return catalog_hits
        if selection.mode not in {"block", "page", "unit", "branch"}:
            return catalog_hits
        hits = self.support_retriever.search(
            current_page_uid=state.current_page_uid,
            current_block_uid=block.block_uid,
            selection=selection,
            query=learner_input,
        )
        if not catalog_gloss_hit:
            return hits
        catalog_term_key = _catalog_term_key(catalog_gloss_hit.english)
        same_term_support_hit = next(
            (
                hit
                for hit in hits
                if _catalog_term_key(hit.english) == catalog_term_key
                and self._contains_cjk(hit.chinese)
            ),
            None,
        )
        if same_term_support_hit:
            return [
                same_term_support_hit,
                *[
                    hit
                    for hit in hits
                    if _catalog_term_key(hit.english) != catalog_term_key
                ],
            ][:2]
        return [
            catalog_gloss_hit,
            *[
                hit
                for hit in hits
                if _catalog_term_key(hit.english) != catalog_term_key
            ],
        ][:2]

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
            and fallback_selection.mode in {"block", "page", "unit"}
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

    def _with_current_task_branch_anchor(
        self,
        selection: RetrievalSelection,
        *,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
    ) -> RetrievalSelection:
        if selection.mode != "branch":
            return selection
        anchor = self._current_task_return_anchor(state=state, block=block)
        if not anchor:
            return selection
        return selection.model_copy(update={"return_anchor": anchor})

    def _current_task_return_anchor(
        self,
        *,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
    ) -> str | None:
        if state.awaiting_answer and state.last_teacher_question:
            return state.last_teacher_question
        for candidate in [
            *block.return_anchors,
            *block.entry_probe_questions,
            *block.core_patterns,
        ]:
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        return None

    def _lexicon_current_task_return_anchor(
        self,
        *,
        state: LessonRuntimeState,
        block: TeachingBlockRecord,
        page: PageLessonRecord,
        active_prompt: str | None,
    ) -> str | None:
        if active_prompt and not self._active_prompt_is_page_module_choice(
            page=page,
            active_prompt=active_prompt,
        ):
            return active_prompt
        concrete_anchor = self._current_block_concrete_return_anchor(block)
        if (
            active_prompt
            and concrete_anchor
            and self._prefer_concrete_vocab_anchor_over_module_choice(
                page=page,
                block=block,
                concrete_anchor=concrete_anchor,
            )
        ):
            return concrete_anchor
        return active_prompt or self._current_task_return_anchor(state=state, block=block)

    def _prefer_concrete_vocab_anchor_over_module_choice(
        self,
        *,
        page: PageLessonRecord,
        block: TeachingBlockRecord,
        concrete_anchor: str,
    ) -> bool:
        if page.page_type != "dialogue":
            return False
        if len(page.priority_blocks) != 2:
            return False
        if block.block_type not in {"dialogue_core", "dialogue_practice"}:
            return False
        return concrete_anchor.strip().endswith(("?", "？"))

    def _current_block_concrete_return_anchor(
        self,
        block: TeachingBlockRecord,
    ) -> str | None:
        for candidate in [
            *block.return_anchors,
            *block.entry_probe_questions,
            *block.core_patterns,
        ]:
            if not isinstance(candidate, str):
                continue
            cleaned = self._answer_turn_policy_strip_surface_instruction_wrapper(candidate)
            if not cleaned:
                cleaned = self._answer_turn_policy_clean_target_source_phrase(candidate)
            if cleaned:
                return cleaned
        return None

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
    ) -> LessonTeacherResponseRenderResult:
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
    ) -> LessonTeacherResponseRenderResult:
        stream_sink = _ACTIVE_TEACHER_RESPONSE_STREAM.get()
        effective_decision = decision
        if selection is not None and getattr(selection, "mode", None):
            effective_decision = decision.model_copy(
                update={"retrieval_mode": selection.mode}
            )
        effective_anchor = return_anchor or effective_decision.return_anchor
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
            teaching_action=effective_decision.teaching_action,
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
            decision=effective_decision,
            state=state,
        )
        teaching_move_model = self.teaching_move_planner.plan(
            lesson_brief=lesson_brief_model,
            learner_input=learner_input,
            turn_label=turn_label,
            decision=effective_decision,
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
            effective_decision.teaching_action,
            effective_decision.retrieval_mode,
            len(retrieval_evidence),
            len(support_evidence),
            self.responder is not None,
            stream_sink is not None,
            len(fallback_response),
        )
        if stream_sink is not None:
            stream_sink.emit_action_metadata(
                teaching_action=effective_decision.teaching_action,
                evaluation=state.last_eval_result,
                branch_active=state.branch_active
                or effective_decision.retrieval_mode == "branch",
                turn_label=turn_label,
                airi_performance=persona_context["airi_performance"],
            )
        if self.responder is None:
            logger.info(
                "Lesson teacher response audit turn_label=%s llmcalled=false llmprovider=%s latencyms=0 fallbackused=false fallbackreason=none teacherresponse_source=deterministic response_chars=%d",
                turn_label,
                self.llm_provider,
                len(fallback_response),
            )
            if stream_sink is not None:
                stream_sink.emit_text_delta(fallback_response)
            return LessonTeacherResponseRenderResult(
                text=fallback_response,
                audit=LessonTeacherResponseAuditSignal(
                    source="deterministic",
                    llm_called=False,
                    llm_provider=self.llm_provider,
                    latency_ms=0,
                    fallback_used=False,
                    fallback_reason="none",
                    route=prompt_path,
                ),
            )
        page_snapshot = self._page_snapshot_for_turn(page=page, turn_label=turn_label)
        state_snapshot = self._state_snapshot(state)
        block_snapshot = self._block_snapshot(block)
        if stream_sink is not None:
            buffered_text_deltas: list[str] = []
            response = self.responder.render_teacher_turn_stream_result(
                learner_input=learner_input,
                turn_label=turn_label,
                decision=effective_decision,
                state_snapshot=state_snapshot,
                page_snapshot=page_snapshot,
                block_snapshot=block_snapshot,
                learner_memory=memory_payload,
                retrieval_evidence=retrieval_evidence,
                support_evidence=support_evidence,
                return_anchor=effective_anchor,
                fallback_response=fallback_response,
                on_delta=buffered_text_deltas.append,
                persona_context=persona_context,
                lesson_brief=lesson_brief,
                lesson_evidence=lesson_evidence,
                teaching_move=teaching_move,
            )
            rendered_response = self._teacher_response_result_from_responder(
                response,
                route=prompt_path,
                turn_label=turn_label,
                fallback_response=fallback_response,
                learner_input=learner_input,
                page_uid=page.page_uid,
                selected_block_uid=block.block_uid,
                retrieval_count=len(retrieval_evidence) + len(support_evidence),
            )
            stream_sink.emit_text_delta(rendered_response.text)
            return rendered_response
        response = self.responder.render_teacher_turn_result(
            learner_input=learner_input,
            turn_label=turn_label,
            decision=effective_decision,
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
        return self._teacher_response_result_from_responder(
            response,
            route=prompt_path,
            turn_label=turn_label,
            fallback_response=fallback_response,
            learner_input=learner_input,
            page_uid=page.page_uid,
            selected_block_uid=block.block_uid,
            retrieval_count=len(retrieval_evidence) + len(support_evidence),
        )

    def _teacher_response_result_from_responder(
        self,
        result: LessonResponderTurnResult,
        *,
        route: str,
        turn_label: str | None = None,
        fallback_response: str,
        learner_input: str = "",
        page_uid: str | None = None,
        selected_block_uid: str | None = None,
        retrieval_count: int = 0,
    ) -> LessonTeacherResponseRenderResult:
        forced_fallback_reason = result.fallback_reason
        repair_reasons: list[str] = []
        if result.repair_reason and result.repair_reason != "none":
            repair_reasons.append(result.repair_reason)
        if (
            result.source != "fallback"
            and not result.fallback_used
            and self._answer_turn_policy_reply_has_generic_praise(result.text)
        ):
            stripped_text = self._strip_generic_praise_from_teacher_reply(result.text)
            if self._generic_praise_stripped_reply_is_usable(
                stripped_text,
                fallback_response=fallback_response,
                learner_input=learner_input,
            ):
                logger.info(
                    "Lesson responder response repaired reason=generic_praise_stripped route=%s response_chars=%d repaired_chars=%d",
                    route,
                    len(result.text),
                    len(stripped_text),
                )
                result_text = stripped_text
                forced_fallback_reason = "none"
                source: Literal["llm", "llm_repaired", "fallback"] = "llm"
                fallback_used = False
                repair_reasons.append("generic_praise_stripped")
            else:
                if fallback_response.strip():
                    logger.info(
                        "Lesson responder response repaired reason=generic_praise_deterministic_repair route=%s response_chars=%d repaired_chars=%d rejected_preview=%s stripped_preview=%s",
                        route,
                        len(result.text),
                        len(fallback_response),
                        self._teacher_response_log_preview(result.text),
                        self._teacher_response_log_preview(stripped_text),
                    )
                    result_text = fallback_response
                    forced_fallback_reason = "none"
                    source = "llm"
                    fallback_used = False
                    repair_reasons.append("generic_praise_deterministic_repair")
                else:
                    logger.info(
                        "Lesson responder response rejected reason=generic_praise route=%s response_chars=%d rejected_preview=%s stripped_preview=%s",
                        route,
                        len(result.text),
                        self._teacher_response_log_preview(result.text),
                        self._teacher_response_log_preview(stripped_text),
                    )
                    result_text = fallback_response
                    forced_fallback_reason = "generic_praise_rejected"
                    source = "fallback"
                    fallback_used = True
        else:
            result_text = result.text
            fallback_used = result.fallback_used
            if result.source == "fallback" or result.fallback_used:
                source = "fallback"
            elif result.source == "llm_repaired":
                source = "llm_repaired"
            else:
                source = "llm"
        if source != "fallback" and not fallback_used:
            normalized_text = result_text.translate(_COMMON_TRADITIONAL_TO_SIMPLIFIED)
            if normalized_text != result_text:
                logger.info(
                    "Lesson responder response repaired reason=traditional_normalized route=%s response_chars=%d repaired_chars=%d",
                    route,
                    len(result_text),
                    len(normalized_text),
                )
                result_text = normalized_text
                repair_reasons.append("traditional_normalized")
        needs_classroom_phrasing_repair = (
            self._answer_turn_policy_reply_has_broken_english(result_text)
            or self._answer_turn_policy_reply_has_awkward_mixed_english(result_text)
        )
        needs_page_entry_module_choice_repair = (
            turn_label == "page_entry"
            and self._teacher_reply_has_module_choice_prompt(fallback_response)
            and not self._teacher_reply_has_module_choice_prompt(result_text)
        )
        if (
            source != "fallback"
            and not fallback_used
            and route == "llm_only"
            and (
                needs_classroom_phrasing_repair
                or needs_page_entry_module_choice_repair
            )
        ):
            repaired_text = self._repair_responder_reply_classroom_phrasing(
                result_text,
                turn_label=turn_label,
                fallback_response=fallback_response,
                learner_input=learner_input,
            )
            if (
                repaired_text
                and repaired_text != result_text
                and not (
                    self._answer_turn_policy_reply_has_broken_english(repaired_text)
                    or self._answer_turn_policy_reply_has_awkward_mixed_english(
                        repaired_text
                    )
                )
            ):
                logger.info(
                    "Lesson responder response repaired reason=classroom_phrasing route=%s response_chars=%d repaired_chars=%d",
                    route,
                    len(result_text),
                    len(repaired_text),
                )
                result_text = repaired_text
                repair_reasons.append(
                    "page_entry_module_choice_repaired"
                    if needs_page_entry_module_choice_repair
                    and not needs_classroom_phrasing_repair
                    else "classroom_phrasing"
                )
        if (
            source != "fallback"
            and not fallback_used
            and self._teacher_reply_has_phonics_tautology(result_text)
        ):
            repaired_text = self._repair_phonics_tautology_reply(result_text)
            if (
                repaired_text
                and repaired_text != result_text
                and not self._teacher_reply_has_phonics_tautology(repaired_text)
            ):
                logger.info(
                    "Lesson responder response repaired reason=phonics_tautology route=%s turn_label=%s response_chars=%d repaired_chars=%d",
                    route,
                    turn_label,
                    len(result_text),
                    len(repaired_text),
                )
                result_text = repaired_text
                repair_reasons.append("phonics_tautology_repaired")
        if (
            source != "fallback"
            and not fallback_used
            and "page_entry_module_choice_repaired" not in repair_reasons
            and self._teacher_reply_looks_overloaded(
                result_text,
                turn_label=turn_label,
            )
        ):
            repaired_text = self._repair_overloaded_teacher_reply(
                result_text,
                fallback_response=fallback_response,
                learner_input=learner_input,
            )
            if (
                repaired_text
                and repaired_text != result_text
                and not self._teacher_reply_looks_overloaded(
                    repaired_text,
                    turn_label=turn_label,
                )
            ):
                logger.info(
                    "Lesson responder response repaired reason=classroom_pacing route=%s turn_label=%s response_chars=%d repaired_chars=%d",
                    route,
                    turn_label,
                    len(result_text),
                    len(repaired_text),
                )
                result_text = repaired_text
                repair_reasons.append("classroom_pacing")
        if source != "fallback" and not fallback_used:
            repaired_text = self._repair_incomplete_teacher_response_tail(result_text)
            if repaired_text != result_text.strip():
                logger.info(
                    "Lesson responder response repaired reason=sentence_tail_repaired route=%s turn_label=%s response_chars=%d repaired_chars=%d",
                    route,
                    turn_label,
                    len(result_text),
                    len(repaired_text),
                )
                result_text = repaired_text
                repair_reasons.append("sentence_tail_repaired")
        if result.reject_rule and fallback_used:
            logger.warning(
                "Lesson responder response rejection %s",
                json.dumps(
                    {
                        "pageUid": page_uid,
                        "route": route,
                        "input": learner_input,
                        "generated_reply": result.generated_reply,
                        "reject_rule": result.reject_rule,
                        "reject_reason": result.reject_reason,
                        "retrieval_count": retrieval_count,
                        "selected_block": selected_block_uid,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        repair_reason = (
            ";".join(self._unique_preserving_order(repair_reasons))
            if repair_reasons
            else "none"
        )
        if source == "llm" and repair_reason != "none":
            source = "llm_repaired"
        return LessonTeacherResponseRenderResult(
            text=result_text,
            audit=LessonTeacherResponseAuditSignal(
                source=source,
                llm_called=result.llm_called,
                llm_provider=result.llm_provider,
                latency_ms=result.latency_ms,
                fallback_used=fallback_used,
                fallback_reason=forced_fallback_reason,
                repair_reason=repair_reason,
                route=route,
            ),
        )

    def _repair_responder_reply_classroom_phrasing(
        self,
        teacher_reply: str,
        *,
        turn_label: str | None = None,
        fallback_response: str,
        learner_input: str = "",
    ) -> str:
        if (
            turn_label == "page_entry"
            and fallback_response.strip()
            and self._teacher_reply_has_module_choice_prompt(fallback_response)
        ):
            return fallback_response.strip()

        if (
            self._teacher_reply_has_module_choice_prompt(teacher_reply)
            and self._teacher_reply_has_module_choice_prompt(fallback_response)
        ):
            compact_choice = self._compact_module_choice_reply(
                fallback_response,
                learner_input=learner_input,
            )
            if compact_choice:
                return compact_choice

        redirect_question = self._compact_redirect_question_reply(
            original=teacher_reply,
            stripped=teacher_reply,
        )
        if redirect_question:
            return redirect_question

        repaired = self._insert_sentence_breaks_after_policy_english_phrases(
            teacher_reply
        )
        if not (
            self._answer_turn_policy_reply_has_broken_english(repaired)
            or self._answer_turn_policy_reply_has_awkward_mixed_english(repaired)
        ):
            return repaired

        exemplar = self._responder_reply_best_exemplar(teacher_reply)
        if exemplar:
            label = self._responder_reply_module_label(teacher_reply)
            meaning = self._responder_reply_exemplar_meaning(teacher_reply)
            lines = [f"好，我们进入{label}。" if label else "好，我们进入这一块。"]
            lines.append(f"先听示范：{self._english_sentence(exemplar)}")
            if meaning:
                lines.append(f"意思是“{meaning}”。")
            lines.append(f"跟我读：{self._english_sentence(exemplar)}")
            return "\n".join(lines)

        fallback_anchors = self._fallback_curriculum_anchor_phrases(fallback_response)
        learner_phrase = self._answer_turn_policy_spoken_english_phrase(learner_input)
        target = fallback_anchors[0] if fallback_anchors else None
        if target:
            parts = []
            if learner_phrase and (
                self._answer_turn_policy_phrase_key(learner_phrase)
                != self._answer_turn_policy_phrase_key(target)
            ):
                parts.append(f"你刚才说的是 {self._english_sentence(learner_phrase)}")
            if self._answer_turn_policy_target_is_task_instruction(target):
                parts.append(f"老师这一步要你做的是：{self._english_sentence(target)}")
            else:
                practice_intro, practice_read = (
                    self._answer_turn_policy_practice_prompt_pair(
                        target,
                        learner_phrase=learner_phrase,
                        seed=teacher_reply,
                    )
                )
                parts.append(practice_intro)
                parts.append(practice_read)
            return "\n".join(parts)
        return repaired

    def _teacher_reply_looks_overloaded(
        self,
        teacher_reply: str,
        *,
        turn_label: str | None,
    ) -> bool:
        if not teacher_reply or turn_label is None:
            return False
        anchors = self._teacher_reply_contentful_anchor_occurrences(teacher_reply)
        if turn_label == "page_entry":
            if not self._teacher_reply_has_module_choice_prompt(teacher_reply):
                return False
            return (
                len(teacher_reply) > 220
                or len(anchors) >= 5
                or teacher_reply.count("：") >= 5
            )
        module_detail_count = len(
            re.findall(r"第[一二三四五六七八九十]+块\s*[：:]", teacher_reply)
        )
        if module_detail_count >= 3:
            return True
        if len(anchors) >= 4:
            return True
        action_cues = sum(
            1
            for cue in ("先", "然后", "再", "跟我读", "回答", "试着", "现在")
            if cue in teacher_reply
        )
        return action_cues >= 4 and len(teacher_reply) > 180

    def _teacher_reply_contentful_anchor_occurrences(
        self,
        teacher_reply: str,
    ) -> list[str]:
        anchors: list[str] = []
        for match in re.finditer(
            r"[A-Za-z][A-Za-z'’]*(?:\s+[A-Za-z][A-Za-z'’]*){0,5}",
            teacher_reply,
        ):
            phrase = " ".join(match.group(0).split())
            if phrase.isupper():
                continue
            compact = re.sub(r"[^a-z]", "", phrase.casefold())
            if len(compact) < 5:
                continue
            if compact in {"peptutor", "lesson", "teacher", "excellent"}:
                continue
            anchors.append(phrase)
        return anchors

    def _repair_overloaded_teacher_reply(
        self,
        teacher_reply: str,
        *,
        fallback_response: str,
        learner_input: str = "",
    ) -> str:
        fallback = fallback_response.strip()
        if fallback and not self._teacher_reply_looks_overloaded(
            fallback,
            turn_label="navigation",
        ):
            fallback_anchor_count = len(
                self._teacher_reply_contentful_anchor_occurrences(fallback)
            )
            reply_anchor_count = len(
                self._teacher_reply_contentful_anchor_occurrences(teacher_reply)
            )
            if self._teacher_reply_has_module_choice_prompt(
                teacher_reply
            ) or len(fallback) + 40 < len(teacher_reply) or (
                reply_anchor_count >= 4 and fallback_anchor_count < reply_anchor_count
            ):
                return fallback

        if self._teacher_reply_has_module_choice_prompt(teacher_reply):
            compact_choice = self._compact_module_choice_reply(
                teacher_reply,
                learner_input=learner_input,
            )
            if compact_choice:
                return compact_choice

        lexicon_return = self._compact_lexicon_meaning_return_reply(
            teacher_reply,
            learner_input=learner_input,
        )
        if lexicon_return:
            return lexicon_return

        redirect_question = self._compact_redirect_question_reply(
            original=teacher_reply,
            stripped=teacher_reply,
        )
        if redirect_question:
            return redirect_question

        compact = self._compact_overloaded_reply_text(teacher_reply)
        if compact and compact != teacher_reply:
            return compact
        return ""

    def _compact_module_choice_reply(
        self,
        teacher_reply: str,
        *,
        learner_input: str = "",
    ) -> str:
        labels = self._module_choice_labels_from_reply(teacher_reply)
        if len(labels) < 2:
            return ""
        choices = self._format_page_choice_labels(labels)
        variants = (
            f"这页先选一个小任务：{choices}。你想先学哪一块？",
            f"我们先选一块开始：{choices}。你想从哪块开始？",
            f"我们先选一块开始：{choices}。你选哪一块？",
        )
        prefix = "我听到了。" if learner_input.strip() else ""
        return (
            prefix
            + variants[
                self._stable_variant_index(teacher_reply, learner_input, len(variants))
            ]
        )

    def _module_choice_labels_from_reply(self, teacher_reply: str) -> list[str]:
        english_labels = [
            self._clean_english_phrase(match.group(0))
            for match in _LESSON_MODULE_TITLE_RE.finditer(teacher_reply)
        ]
        english_labels = [
            label for label in self._unique_preserving_order(english_labels) if label
        ]
        if len(english_labels) >= 2:
            return english_labels[:4]

        ordinal_labels = self._unique_preserving_order(
            re.findall(r"第[一二三四五六七八九十]+块", teacher_reply)
        )
        return ordinal_labels[:4]

    def _format_page_choice_labels(self, labels: list[str]) -> str:
        if len(labels) == 2:
            return f"{labels[0]} 或 {labels[1]}"
        return "、".join(labels[:-1]) + f" 或 {labels[-1]}"

    def _compact_overloaded_reply_text(self, teacher_reply: str) -> str:
        text = teacher_reply.strip()
        text = re.sub(
            r"\s*(?:你可以)?(?:选一句|选一个)[^。！？.!?]*(?:说|回答)[：:]?.*$",
            "",
            text,
        ).strip()
        text = re.sub(r"\s*(?:比如|例如)[：:]?.*$", "", text).strip()
        redirected_question = self._compact_redirect_question_reply(
            original=teacher_reply,
            stripped=text,
        )
        if redirected_question:
            return redirected_question
        text = re.sub(
            r"这正是\s*" + _LESSON_MODULE_TITLE_RE.pattern + r"\s*里的",
            "这是这一块里的",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"那我们就先来学\s*" + _LESSON_MODULE_TITLE_RE.pattern + r"\s*吧[。.]?",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        return re.sub(r"\s+", " ", text).strip()

    def _compact_redirect_question_reply(
        self,
        *,
        original: str,
        stripped: str,
    ) -> str:
        question_match = re.search(
            r"老师(?:问的是|问你|问的)[\"'“”：:]?([^。！？（(]*[?？])",
            stripped,
            flags=re.IGNORECASE,
        )
        frame_match = re.search(
            r"(?:你可以用|可以用|用)[\"'“”]?"
            r"([^“”，,。！？]{2,60}?)(?:的句式|的句型|来回答|回答|开头|说)",
            stripped,
            flags=re.IGNORECASE,
        )
        if not question_match or not frame_match:
            return ""
        question = " ".join(
            question_match.group(1).strip("“”\"'`，,、；;:：。").split()
        )
        answer_frame = self._normalize_answer_frame_text(frame_match.group(1))
        if not question or not answer_frame:
            return ""
        anchors = self._curriculum_anchor_phrases(original)
        learner_phrase = anchors[0] if anchors else ""
        prefix = (
            f"你刚才说的是 {self._english_sentence(learner_phrase)}\n"
            if learner_phrase
            else ""
        )
        question_text = (
            question
            if question.endswith(("?", "？"))
            else self._english_sentence(question)
        )
        return (
            f"{prefix}现在先回答：{question_text} "
            f"可以用 {answer_frame} 开头。"
        )

    def _compact_lexicon_meaning_return_reply(
        self,
        teacher_reply: str,
        *,
        learner_input: str = "",
    ) -> str:
        term = self._lexicon_meaning_question_term(learner_input)
        meaning_match = re.search(
            r"\b(?P<term>[A-Za-z][A-Za-z'’]*(?:\s+[A-Za-z][A-Za-z'’]*){0,3})\b"
            r"\s*(?:就是|是|意思是|表示|指的是)[“\"']?"
            r"(?P<meaning>[\u4e00-\u9fff][^。！？；;，,\n]{0,24})",
            teacher_reply,
            flags=re.IGNORECASE,
        )
        if meaning_match:
            matched_term = self._clean_english_phrase(meaning_match.group("term"))
            if not term:
                term = matched_term
            elif self._answer_turn_policy_phrase_key(term) != self._answer_turn_policy_phrase_key(
                matched_term
            ):
                term = matched_term
            meaning = meaning_match.group("meaning").strip("“”\"' ")
        else:
            meaning = ""
        if not term or not meaning:
            return ""

        anchors = [
            anchor
            for anchor in self._curriculum_anchor_phrases(teacher_reply)
            if len(anchor.split()) >= 3
            and self._answer_turn_policy_phrase_key(anchor)
            != self._answer_turn_policy_phrase_key(term)
        ]
        target = self._clean_english_phrase(anchors[-1]) if anchors else ""
        if not target:
            return f"{self._english_sentence(term)} 是“{meaning}”。"
        return (
            f"{self._english_sentence(term)} 是“{meaning}”。"
            f"回到刚才的小任务：{self._english_sentence(target)}"
        )

    def _lexicon_meaning_question_term(self, learner_input: str) -> str:
        match = re.search(
            r"\bwhat\s+does\s+(.+?)\s+mean\b",
            learner_input,
            flags=re.IGNORECASE,
        )
        if not match:
            return ""
        return self._clean_english_phrase(match.group(1))

    def _normalize_answer_frame_text(self, answer_frame: str) -> str:
        cleaned = self._clean_english_phrase(answer_frame)
        if not cleaned:
            return ""
        if self._answer_turn_policy_phrase_key(cleaned) in {"idlike", "iwouldlike"}:
            return "I'd like ..."
        anchors = self._curriculum_anchor_phrases(cleaned)
        if anchors:
            cleaned = self._clean_english_phrase(anchors[0])
        cleaned = re.sub(r"\s*\.\.\.$", " ...", cleaned)
        if "..." in answer_frame and not cleaned.endswith("..."):
            cleaned = cleaned.rstrip(".") + " ..."
        return cleaned

    def _unique_preserving_order(self, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            stripped = str(value).strip()
            key = stripped.casefold()
            if not stripped or key in seen:
                continue
            seen.add(key)
            result.append(stripped)
        return result

    def _responder_reply_best_exemplar(self, teacher_reply: str) -> str | None:
        match = re.search(
            r"(?:示范|跟我读|跟着说|跟老师读)[：:]\s*([A-Za-z][^。！？\n]*?[.!?])",
            teacher_reply,
            flags=re.IGNORECASE,
        )
        if match:
            phrase = self._clean_english_phrase(match.group(1))
            if self._is_instruction_anchor_phrase(phrase):
                return None
            return phrase
        anchors = self._curriculum_anchor_phrases(teacher_reply)
        sentence_like = [
            anchor
            for anchor in anchors
            if len(anchor.split()) >= 3 and anchor.casefold() not in {"let's try"}
        ]
        if sentence_like:
            return self._clean_english_phrase(sentence_like[-1])
        return None

    def _responder_reply_module_label(self, teacher_reply: str) -> str | None:
        match = re.search(r"第[一二三四五六七八九十]+块", teacher_reply)
        if match:
            return match.group(0)
        match = re.search(r"Let's\s+[A-Za-z ]{2,24}", teacher_reply, flags=re.IGNORECASE)
        if match:
            return self._clean_english_phrase(match.group(0))
        return None

    def _responder_reply_exemplar_meaning(self, teacher_reply: str) -> str | None:
        match = re.search(r"意思是[“\"]([^”\"]{1,40})[”\"]", teacher_reply)
        return match.group(1).strip().rstrip("。.!！") if match else None

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
            "return_target": state.return_target,
            "repair_mode": state.repair_mode,
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
        if self._uses_concrete_item_task_scaffold(block):
            return (
                "A concrete party-list item or a short first-person list sentence, "
                "for example: cake / orange juice / I'm going to bring cake."
            )
        if self._block_has_task_instruction(block):
            return (
                "One short answer for the current textbook task; do not treat the "
                "task instruction itself as the learner's answer."
            )
        if block.allowed_answer_scope:
            return "One answer that fits the current block's allowed answer scope."
        return "A short lesson-aware learner response."

    def _progression_condition_for_brief(self, block: TeachingBlockRecord) -> str:
        if self._uses_concrete_item_task_scaffold(block):
            return (
                "Advance only after the learner gives their own concrete party-list item "
                "or a clear item-list sentence; do not advance on the task instruction itself."
            )
        if self._block_has_task_instruction(block):
            return (
                "Advance only after the learner gives an acceptable answer for the "
                "current task; do not advance on the task instruction itself."
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
            if not self._uses_concrete_item_task_scaffold(block):
                scaffold = self._format_answer_choices(
                    self._evaluation_answer_scope(block, state.last_teacher_question)[
                        :2
                    ]
                )
                return [
                    LessonBriefMisconceptionHint(
                        likely_error="task_instruction_echo",
                        repair_move=(
                            "Tell the learner that the sentence is the task instruction, "
                            "then ask for one answer in the current task."
                        ),
                        scaffold_example=scaffold or "one answer",
                    )
                ]
            return [
                LessonBriefMisconceptionHint(
                    likely_error="task_instruction_echo",
                    repair_move="Tell the learner that the sentence is the task, then ask for one item.",
                    scaffold_example="cake",
                )
            ]
        if (
            self._uses_concrete_item_task_scaffold(block)
            and state.last_eval_result == "partially_correct"
        ):
            return [
                LessonBriefMisconceptionHint(
                    likely_error="rough_item_sentence",
                    repair_move="Lightly remodel the sentence without a grammar lecture.",
                    scaffold_example="I'm going to bring an apple.",
                )
            ]
        if state.last_eval_result in {"unclear", "incorrect"}:
            if not self._uses_concrete_item_task_scaffold(block):
                scaffold = self._format_answer_choices(
                    self._evaluation_answer_scope(block, state.last_teacher_question)[
                        :2
                    ]
                )
                return [
                    LessonBriefMisconceptionHint(
                        likely_error="current_task_answer_missing",
                        repair_move=(
                            "Keep the learner on the current task and offer one small answer target."
                        ),
                        scaffold_example=scaffold or "one answer",
                    )
                ]
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
        _ = turn_label
        snapshot = self._page_snapshot(page)
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

    def _render_module_choice_clarification(
        self,
        *,
        overview: PageOverview,
        learner_input: str,
        page_uid: str,
    ) -> str:
        choices = self._format_page_overview_choices(overview)
        variants = (
            f"这页先选一个小任务：{choices}。你想从哪一块开始？",
            f"先选一块开始：{choices}。你想从哪一块开始？",
            f"我们先选一块开始：{choices}。你想学哪一块？",
        )
        return variants[self._stable_variant_index(page_uid, learner_input, len(variants))]

    def _stable_variant_index(self, *parts: object) -> int:
        if not parts:
            return 0
        size = int(parts[-1])
        text = "|".join(str(part) for part in parts[:-1])
        if size <= 1:
            return 0
        return sum(ord(char) for char in text) % size

    def _page_module_label_selected(
        self,
        learner_input: str,
        module: PageOverviewModule,
    ) -> bool:
        normalized = _module_choice_key(learner_input)
        if not normalized:
            return False
        labels = [module.label]
        lower_label = module.label.casefold()
        if lower_label.startswith("let's "):
            labels.append(module.label[6:])
        if lower_label == "let's wrap it up":
            labels.extend(["wrap it up", "wrap up", "Let's wrap up"])
        return normalized in {_module_choice_key(label) for label in labels}

    def _block_snapshot(self, block: TeachingBlockRecord) -> dict[str, Any]:
        return {
            "block_uid": block.block_uid,
            "page_uid": block.page_uid,
            "block_type": block.block_type,
            "teaching_goal": block.teaching_goal,
            "teaching_summary": block.teaching_summary,
            "task_type": block.task_type,
            "focus_vocabulary": block.focus_vocabulary,
            "core_patterns": block.core_patterns,
            "allowed_answer_scope": block.allowed_answer_scope,
            "answer_scope": block.answer_scope,
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
            if block.block_type == "listening_probe":
                choices = self._format_answer_choices(
                    self._evaluation_answer_scope(block, state.last_teacher_question)[
                        :2
                    ]
                )
                return (
                    "这句是题目要求，不是答案。我们还在当前听力小题里，"
                    f"你先抓一个答案，比如 {choices}。"
                )
            if block.block_type in {"practice_fill_blank", "practice_write"}:
                choices = self._format_answer_choices(
                    self._evaluation_answer_scope(block, state.last_teacher_question)[
                        :2
                    ]
                )
                return (
                    "这句是题目要求，不用重新读题。我们就在这一小题里补答案，"
                    f"你可以先试一个：{choices}。"
                )
            if not self._uses_concrete_item_task_scaffold(block):
                choices = self._format_answer_choices(
                    self._evaluation_answer_scope(block, state.last_teacher_question)[
                        :2
                    ]
                )
                return f"这句是题目要求，还不是答案。你先试一个答案：{choices}。"
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

        if lower.startswith("can you try:"):
            sentence = text.split(":", 1)[1].strip()
            if self._is_service_question_text(sentence):
                return self._render_service_question_repeat_prompt(sentence)
            if self._looks_like_task_instruction(sentence):
                return self._render_task_instruction_probe_prompt(sentence, block)
            return f"先试着说一遍：{sentence}"

        for prefix in (
            "try to say:",
            "try saying:",
            "say after me:",
            "repeat after me:",
            "read after me:",
            "please repeat:",
            "please say:",
            "can you follow me and say:",
        ):
            if lower.startswith(prefix):
                sentence = text.split(":", 1)[1].strip()
                if self._is_service_question_text(sentence):
                    return self._render_service_question_repeat_prompt(sentence)
                if self._looks_like_task_instruction(sentence):
                    return self._render_task_instruction_probe_prompt(sentence, block)
                return f"先跟老师读一遍：{self._english_sentence(sentence)}"

        if lower.startswith("can you repeat:"):
            sentence = text.split(":", 1)[1].strip()
            if self._is_service_question_text(sentence):
                return self._render_service_question_repeat_prompt(sentence)
            return f"先跟老师读一遍：{sentence}"

        if lower.startswith("can you repeat after me:"):
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
                limit=1,
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
        cleaned = sentence.strip()
        block_type = block.block_type.casefold()
        if block_type == "listening_probe":
            return (
                f"这一小题先看清要求：{cleaned} "
                "等听到内容后，你只要给一个最小答案。"
            )
        if block_type in {"practice_fill_blank", "practice_write"}:
            return f"这一小题不是读题，是补答案。先看要求：{cleaned}"
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
            limit=1,
        )
        answer_choices = self._format_answer_choices(target_answers)

        if "口渴" in text and ("选一句" in text or "或" in text):
            return f"现在你口渴了，跟老师说一句：{target}"

        if "想点吃的" in text and ("选一句" in text or "或" in text):
            return f"现在你想点吃的，跟老师说一句：{target}"

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
            if self._is_instruction_anchor_phrase(candidate):
                return []
            return [candidate] if candidate else []

        if lower.startswith("can you say:"):
            return _single(text.split(":", 1)[1])
        if lower.startswith("can you try:"):
            return _single(text.split(":", 1)[1])
        if lower.startswith("can you repeat:"):
            return _single(text.split(":", 1)[1])
        if lower.startswith("can you repeat after me:"):
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
                    limit=1,
                )
            )
            return f"现在你想点吃的，跟老师说一句：{answers}"
        if "what would you like to drink" in lower:
            answers = self._format_answer_choices(
                self._best_model_answers(
                    block,
                    "现在你口渴了，跟老师选一句说。",
                    limit=1,
                )
            )
            return f"现在你口渴了，跟老师说一句：{answers}"
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
        if block.block_type in {
            "listening_probe",
            "practice_fill_blank",
            "practice_write",
        }:
            return None

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
            if block.block_type not in {
                "listening_probe",
                "practice_fill_blank",
                "practice_write",
            }:
                examples = self._page_answer_examples(block.page_uid, limit=8)
                if examples:
                    return examples

        if not allowed_answers:
            return []

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

    def _uses_concrete_item_task_scaffold(self, block: TeachingBlockRecord) -> bool:
        text = " ".join(
            [
                block.teaching_goal,
                block.teaching_summary,
                *block.core_patterns,
                *block.return_anchors,
            ]
        ).casefold()
        return self._block_has_task_instruction(block) and any(
            token in text for token in ("shopping list", "party", "清单")
        )

    def _question_has_task_instruction(self, prompt: str) -> bool:
        if not prompt:
            return False
        if prompt.startswith("can you say:"):
            return self._looks_like_task_instruction(prompt.split(":", 1)[1])
        return self._looks_like_task_instruction(prompt)

    def _looks_like_emotional_help_input(self, learner_input: str) -> bool:
        lower = learner_input.casefold()
        return any(token in lower for token in _EMOTION_HELP_HINTS)

    def _is_service_question_text(self, text: str) -> bool:
        lower = text.casefold()
        return (
            "what would you like to eat" in lower
            or "what would you like to drink" in lower
        )

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


def _module_choice_key(text: str) -> str:
    return re.sub(r"[\s'’`\"“”.,!?！？。；;:：、，-]+", "", text.casefold())
