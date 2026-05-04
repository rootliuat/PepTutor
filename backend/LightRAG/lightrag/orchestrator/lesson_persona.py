"""Versioned persona contracts for the PepTutor lesson runtime."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lightrag.orchestrator.simplemem_prompt_memory import LearnerMemorySummary


PERSONA_CONTEXT_SCHEMA_VERSION = "lesson-persona-context/v1"
DEFAULT_TEACHER_PERSONA_PROFILE_ID = "peptutor-teacher-v1"
DEFAULT_TEACHER_PERSONA_PROFILE_VERSION = "2026-04-24"
MILI_PERSONA_CAPSULE_VERSION = "v1"
MILI_PERSONA_CAPSULE_SOURCE = "mili_persona_capsule"
MILI_PERSONA_INTERESTS_RUNTIME_USAGE = "low_frequency_flavor_only"
MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1 = (
    "米粒老师风格：温柔、耐心、短句引导；先接住学生表达，再给短中文脚手架，"
    "明确英文目标，最后只给一个动作。人格只影响语气和脚手架大小，"
    "不改变教材事实、page/block/route、answer_scope 或 progression。"
)
MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_BYTES = len(
    MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1.encode("utf-8")
)
MILI_PERSONA_CAPSULE_PROMPT_STATUS = (
    "bounded capsule injected into answer_turn_policy"
)
MILI_PERSONA_INTERESTS_ANSWER_TURN_POLICY_USAGE = (
    "low_frequency_flavor_only_not_in_answer_turn_policy_v1"
)
MILI_PERSONA_SOUL_PATH = str(Path(__file__).resolve().parents[4] / "soul.md")
_MAX_RELATIONSHIP_ITEMS = 4
_MAX_SEMANTIC_MEMORIES = 3

MILI_PERSONA_CAPSULE_V1: dict[str, object] = {
    "name": "米粒",
    "nickname": "Mili",
    "role": "小学英语陪练老师",
    "identity": "温柔、耐心、带一点俏皮感的年轻英语老师，擅长把难句拆成小步骤。",
    "style": [
        "温柔",
        "耐心",
        "轻快",
        "一点点俏皮",
        "短句引导",
    ],
    "teaching_rules": [
        "先接住学生表达",
        "给短中文脚手架",
        "明确英文目标",
        "最后只给一个动作",
        "学生已经会了就往前走，不反复 drill",
    ],
    "boundaries": [
        "不离开教材",
        "不改变 page/block/route",
        "不编造教材内容",
        "不长篇闲聊",
        "不靠卖萌代替教学",
    ],
    "interests": [
        "海鲜螺蛳粉",
        "课堂手账",
        "周末去海边看日落",
        "英语节奏操练",
        "Live2D 与语音互动",
        "周末看推理动画",
    ],
    "interest_usage_policy": [
        "兴趣爱好只作为低频人格味道",
        "不要在每轮课堂回复里出现",
        "不要影响教材目标和教学路线",
        "只在破冰、鼓励、轻松承接或前端角色卡展示中使用",
    ],
}

PersonaInfluence = Literal[
    "tone",
    "pacing",
    "encouragement",
    "scaffold_granularity",
    "classroom_habits",
    "speech_style",
    "embodied_performance",
]
ProtectedLessonAuthority = Literal[
    "target_answer",
    "correctness_judgment",
    "page_progression",
    "retrieval_scope",
    "teaching_block",
    "required_teaching_action",
]

DEFAULT_ALLOWED_PERSONA_INFLUENCES: tuple[PersonaInfluence, ...] = (
    "tone",
    "pacing",
    "encouragement",
    "scaffold_granularity",
    "classroom_habits",
    "speech_style",
    "embodied_performance",
)
DEFAULT_PROTECTED_LESSON_AUTHORITIES: tuple[ProtectedLessonAuthority, ...] = (
    "target_answer",
    "correctness_judgment",
    "page_progression",
    "retrieval_scope",
    "teaching_block",
    "required_teaching_action",
)


def _non_empty(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("value cannot be empty")
    return stripped


def _non_empty_list(values: list[str]) -> list[str]:
    stripped_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = _non_empty(value)
        if stripped in seen:
            continue
        seen.add(stripped)
        stripped_values.append(stripped)
    return stripped_values


def _compact_text_list(values: Sequence[str], *, limit: int) -> list[str]:
    compact: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = " ".join(value.split())
        if not stripped:
            continue
        key = stripped.casefold()
        if key in seen:
            continue
        seen.add(key)
        compact.append(stripped)
        if len(compact) >= limit:
            break
    return compact


def _contains_hint(values: Sequence[str], hints: set[str]) -> bool:
    normalized = "\n".join(values).casefold()
    return any(hint in normalized for hint in hints)


def _clamp_stuckness(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 2)


class PersonaInfluenceBoundaries(BaseModel):
    """Fields that separate persona style from lesson correctness authority."""

    model_config = ConfigDict(extra="forbid")

    content_authority: Literal["lesson_runtime"] = "lesson_runtime"
    presentation_authority: Literal["airi_runtime"] = "airi_runtime"
    allowed_to_shape: list[PersonaInfluence] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_PERSONA_INFLUENCES)
    )
    must_not_change: list[ProtectedLessonAuthority] = Field(
        default_factory=lambda: list(DEFAULT_PROTECTED_LESSON_AUTHORITIES)
    )
    can_change_target_answer: bool = False
    can_change_correctness_judgment: bool = False
    can_change_page_progression: bool = False


class TeacherVoiceStyle(BaseModel):
    """Compact voice and classroom speech contract for a persona profile."""

    model_config = ConfigDict(extra="forbid")

    language_policy: Literal[
        "zh_cn_scaffold_with_required_english_targets"
    ] = "zh_cn_scaffold_with_required_english_targets"
    default_pace: Literal["measured"] = "measured"
    repair_pace: Literal["slow_split"] = "slow_split"
    sentence_length: Literal["short_classroom_sentences"] = (
        "short_classroom_sentences"
    )
    tts_voice_hint: str = Field(default="zh-CN-XiaoxiaoNeural", min_length=1)

    @field_validator("tts_voice_hint", mode="after")
    @classmethod
    def _strip_voice_hint(cls, value: str) -> str:
        return _non_empty(value)


class TeacherPersonaProfile(BaseModel):
    """Stable teacher identity used to shape delivery, not lesson truth."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    stable_traits: list[str] = Field(min_length=1)
    teaching_style: list[str] = Field(min_length=1)
    classroom_habits: list[str] = Field(default_factory=list)
    catchphrases: list[str] = Field(default_factory=list)
    voice_style: TeacherVoiceStyle = Field(default_factory=TeacherVoiceStyle)
    boundaries: PersonaInfluenceBoundaries = Field(
        default_factory=PersonaInfluenceBoundaries
    )

    @field_validator("profile_id", "version", "display_name", "role", mode="after")
    @classmethod
    def _strip_non_empty_fields(cls, value: str) -> str:
        return _non_empty(value)

    @field_validator(
        "stable_traits",
        "teaching_style",
        "classroom_habits",
        "catchphrases",
        mode="after",
    )
    @classmethod
    def _strip_non_empty_lists(cls, values: list[str]) -> list[str]:
        return _non_empty_list(values)


class LearnerRelationshipProfile(BaseModel):
    """SimpleMem-derived learner relationship cards for the current turn."""

    model_config = ConfigDict(extra="forbid")

    student_id: str = Field(min_length=1)
    relationship_signals: list[str] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    mastery_signals: list[str] = Field(default_factory=list)
    semantic_memories: list[str] = Field(default_factory=list)

    @field_validator("student_id", mode="after")
    @classmethod
    def _strip_student_id(cls, value: str) -> str:
        return _non_empty(value)

    @field_validator(
        "relationship_signals",
        "common_mistakes",
        "preferences",
        "mastery_signals",
        "semantic_memories",
        mode="after",
    )
    @classmethod
    def _strip_relationship_lists(cls, values: list[str]) -> list[str]:
        return _non_empty_list(values)


class ClassroomAffectState(BaseModel):
    """Deterministic classroom affect state assembled before generation."""

    model_config = ConfigDict(extra="forbid")

    student_confidence: Literal["unknown", "low", "steady", "high"] = "unknown"
    teacher_energy: Literal["calm", "encouraging", "focused"] = "calm"
    stuckness: float = Field(default=0.0, ge=0.0, le=1.0)
    interruption_state: Literal["none", "student_barge_in", "teacher_cancelled"] = (
        "none"
    )
    recent_turn_labels: list[str] = Field(default_factory=list)

    @field_validator("recent_turn_labels", mode="after")
    @classmethod
    def _strip_recent_turn_labels(cls, values: list[str]) -> list[str]:
        return _non_empty_list(values)


class AiriPerformancePlan(BaseModel):
    """Presentation intent for AIRI; it never carries replacement lesson text."""

    model_config = ConfigDict(extra="forbid")

    emotion: Literal[
        "neutral",
        "encouraging",
        "joy",
        "thinking",
        "concerned",
        "correction",
    ] = "encouraging"
    expression: Literal["neutral", "soft_smile", "thinking", "concerned", "focused"] = (
        "soft_smile"
    )
    motion: Literal["Idle", "Listen", "Explain", "Nod", "Encourage", "Interrupted"] = (
        "Idle"
    )
    speech_style: Literal["normal", "slow_split", "short_prompt", "gentle_correction"] = (
        "normal"
    )
    mouth_intensity: float = Field(default=0.8, ge=0.0, le=1.0)
    interrupt_policy: Literal[
        "barge_in_allowed",
        "finish_current_sentence",
        "no_interrupt",
    ] = "barge_in_allowed"
    content_source: Literal["lesson_runtime_teacher_response"] = (
        "lesson_runtime_teacher_response"
    )
    fallback_allowed: bool = True
    target_role: str = ""
    expected_student_action: str = ""
    speech_style_tag: str = ""


class LessonPersonaContext(BaseModel):
    """Small per-turn context object passed through lesson persona stages."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["lesson-persona-context/v1"] = (
        PERSONA_CONTEXT_SCHEMA_VERSION
    )
    profile: TeacherPersonaProfile
    relationship: LearnerRelationshipProfile
    affect_state: ClassroomAffectState = Field(default_factory=ClassroomAffectState)
    airi_performance: AiriPerformancePlan = Field(default_factory=AiriPerformancePlan)


_DEFAULT_TEACHER_PERSONA_PROFILE_DATA = {
    "profile_id": DEFAULT_TEACHER_PERSONA_PROFILE_ID,
    "version": DEFAULT_TEACHER_PERSONA_PROFILE_VERSION,
    "display_name": "米粒",
    "role": "25-year-old G5/G6 English teacher; Guangxi Normal University information-security graduate",
    "stable_traits": [
        "warm older-sister patience",
        "lightly playful but never sarcastic",
        "self-reflective when the learner is confused",
        "precise about the one smallest repair point",
    ],
    "teaching_style": [
        "protect textbook targets before adding personality",
        "receive the learner's actual words before steering to the page target",
        "use short Chinese scaffolds when the learner is stuck",
        "ask for one tiny retry instead of giving a long lecture",
        "split sentences into smaller chunks during repair",
        "separate waiter questions from customer answers during role-play",
    ],
    "classroom_habits": [
        "ask what got stuck when the learner asks for help",
        "acknowledge frustration briefly and return to the task",
        "praise specific progress rather than giving generic praise",
        "move forward once the learner has shown the target is understood",
    ],
    "catchphrases": [
        "我们慢慢来",
        "先抓住这一小句",
        "你不用一下子全说对",
    ],
}


def load_default_teacher_persona_profile() -> TeacherPersonaProfile:
    """Return a fresh deterministic default PepTutor teacher profile."""

    return TeacherPersonaProfile.model_validate(
        deepcopy(_DEFAULT_TEACHER_PERSONA_PROFILE_DATA)
    )


def build_default_lesson_persona_context(
    *,
    student_id: str,
    relationship_signals: list[str] | None = None,
) -> LessonPersonaContext:
    """Build a deterministic starter context before runtime-specific assembly."""

    return LessonPersonaContext(
        profile=load_default_teacher_persona_profile(),
        relationship=LearnerRelationshipProfile(
            student_id=student_id,
            relationship_signals=relationship_signals or [],
        ),
    )


def build_learner_relationship_profile_from_memory(
    *,
    student_id: str,
    learner_memory: LearnerMemorySummary,
) -> LearnerRelationshipProfile:
    """Convert prompt-memory buckets into the compact persona relationship card."""

    common_mistakes = _compact_text_list(
        [
            *learner_memory.common_mistakes,
            *learner_memory.stable_common_mistakes,
        ],
        limit=_MAX_RELATIONSHIP_ITEMS,
    )
    preferences = _compact_text_list(
        [
            *learner_memory.preferences,
            *learner_memory.stable_preferences,
        ],
        limit=_MAX_RELATIONSHIP_ITEMS,
    )
    mastery_signals = _compact_text_list(
        [
            *learner_memory.mastery_signals,
            *learner_memory.stable_mastery_signals,
        ],
        limit=_MAX_RELATIONSHIP_ITEMS,
    )
    semantic_memories = _compact_text_list(
        learner_memory.semantic_memories,
        limit=_MAX_SEMANTIC_MEMORIES,
    )
    relationship_signals = derive_relationship_signals(
        common_mistakes=common_mistakes,
        preferences=preferences,
        mastery_signals=mastery_signals,
        semantic_memories=semantic_memories,
    )
    return LearnerRelationshipProfile(
        student_id=student_id,
        relationship_signals=relationship_signals,
        common_mistakes=common_mistakes,
        preferences=preferences,
        mastery_signals=mastery_signals,
        semantic_memories=semantic_memories,
    )


def derive_relationship_signals(
    *,
    common_mistakes: Sequence[str],
    preferences: Sequence[str],
    mastery_signals: Sequence[str],
    semantic_memories: Sequence[str],
) -> list[str]:
    """Derive stable, explainable relationship hints from memory buckets."""

    signals: list[str] = []
    if common_mistakes:
        signals.append("stored_mistake_pattern")
    if _contains_hint(
        preferences,
        {
            "slow",
            "slower",
            "split",
            "chunk",
            "step by step",
            "phrase by phrase",
            "拆开",
            "慢",
        },
    ):
        signals.append("slow_split_practice")
    if _contains_hint(
        preferences,
        {
            "chinese",
            "translation",
            "translate",
            "中文",
            "解释",
            "母语",
        },
    ):
        signals.append("chinese_scaffold")
    if _contains_hint(
        common_mistakes,
        {
            "omit",
            "missing",
            "full sentence",
            "sentence",
            "pattern",
            "some",
            "完整",
            "漏",
            "句",
        },
    ):
        signals.append("target_sentence_completion_risk")
    if _contains_hint(
        semantic_memories,
        {
            "shy",
            "nervous",
            "anxious",
            "frustrat",
            "stuck",
            "afraid",
            "害羞",
            "紧张",
            "卡住",
            "挫败",
        },
    ):
        signals.append("low_confidence_risk")
    if mastery_signals:
        signals.append("recent_mastery_available")
    return signals


def build_classroom_affect_state_for_turn(
    *,
    turn_label: str,
    evaluation: str | None = None,
    same_goal_attempt_count: int = 0,
    repair_mode: str = "none",
    recent_turn_labels: Sequence[str] | None = None,
    relationship_signals: Sequence[str] | None = None,
    interruption_state: Literal["none", "student_barge_in", "teacher_cancelled"] = "none",
) -> ClassroomAffectState:
    """Derive deterministic affect from runtime state without calling an LLM."""

    labels = list(recent_turn_labels or [])
    signals = set(relationship_signals or [])
    stuckness = 0.0
    if turn_label == "ask_help":
        stuckness += 0.45
    if evaluation in {"incorrect", "unclear"}:
        stuckness += 0.35
    elif evaluation == "partially_correct":
        stuckness += 0.25
    elif evaluation == "off_topic":
        stuckness += 0.2
    stuckness += min(0.4, max(0, same_goal_attempt_count) * 0.15)
    if repair_mode and repair_mode != "none":
        stuckness += 0.15
    if "ask_help" in labels[-3:]:
        stuckness += 0.1
    if "low_confidence_risk" in signals:
        stuckness += 0.1
    if evaluation in {"correct", "acceptable"}:
        stuckness -= 0.35
    stuckness = _clamp_stuckness(stuckness)

    if interruption_state != "none" or stuckness >= 0.55:
        student_confidence: Literal["unknown", "low", "steady", "high"] = "low"
    elif evaluation in {"correct", "acceptable"}:
        student_confidence = "high"
    elif evaluation is not None or turn_label in {"ask_help", "ask_knowledge", "social"}:
        student_confidence = "steady"
    else:
        student_confidence = "unknown"

    if interruption_state != "none" or turn_label == "ask_knowledge":
        teacher_energy: Literal["calm", "encouraging", "focused"] = "focused"
    elif student_confidence == "low" or turn_label == "ask_help":
        teacher_energy = "encouraging"
    else:
        teacher_energy = "calm"

    return ClassroomAffectState(
        student_confidence=student_confidence,
        teacher_energy=teacher_energy,
        stuckness=stuckness,
        interruption_state=interruption_state,
        recent_turn_labels=_compact_text_list(labels[-5:], limit=5),
    )


def build_airi_performance_plan_for_turn(
    *,
    affect_state: ClassroomAffectState,
    turn_label: str,
    teaching_action: str,
    evaluation: str | None = None,
) -> AiriPerformancePlan:
    """Map affect and teaching state to an AIRI presentation-only plan."""

    if affect_state.interruption_state != "none":
        return AiriPerformancePlan(
            emotion="concerned",
            expression="concerned",
            motion="Interrupted",
            speech_style="short_prompt",
            mouth_intensity=0.35,
            interrupt_policy="barge_in_allowed",
        )

    if evaluation in {"correct", "acceptable"} and teaching_action == "confirm":
        return AiriPerformancePlan(
            emotion="joy",
            expression="soft_smile",
            motion="Nod",
            speech_style="normal",
            mouth_intensity=0.8,
        )

    if teaching_action in {"hint", "model", "repeat_drill"}:
        if evaluation in {"incorrect", "partially_correct", "unclear"}:
            return AiriPerformancePlan(
                emotion="correction",
                expression="focused",
                motion="Explain",
                speech_style="gentle_correction",
                mouth_intensity=0.7,
            )
        return AiriPerformancePlan(
            emotion="encouraging",
            expression="soft_smile",
            motion="Encourage",
            speech_style="slow_split",
            mouth_intensity=0.65,
        )

    if turn_label == "ask_help":
        return AiriPerformancePlan(
            emotion="encouraging",
            expression="concerned",
            motion="Encourage",
            speech_style="slow_split",
            mouth_intensity=0.65,
        )

    if turn_label == "ask_knowledge" or teaching_action == "explain":
        return AiriPerformancePlan(
            emotion="thinking",
            expression="thinking",
            motion="Explain",
            speech_style="normal",
            mouth_intensity=0.7,
            interrupt_policy="finish_current_sentence",
        )

    if teaching_action == "redirect":
        return AiriPerformancePlan(
            emotion="neutral",
            expression="soft_smile",
            motion="Listen",
            speech_style="short_prompt",
            mouth_intensity=0.55,
        )

    if teaching_action == "page_intro":
        return AiriPerformancePlan(
            emotion="encouraging",
            expression="soft_smile",
            motion="Encourage",
            speech_style="normal",
            mouth_intensity=0.75,
        )

    return AiriPerformancePlan()


def build_lesson_persona_context_for_turn(
    *,
    student_id: str,
    learner_memory: LearnerMemorySummary,
    turn_label: str,
    teaching_action: str,
    evaluation: str | None = None,
    same_goal_attempt_count: int = 0,
    repair_mode: str = "none",
    recent_turn_labels: Sequence[str] | None = None,
    interruption_state: Literal["none", "student_barge_in", "teacher_cancelled"] = "none",
) -> LessonPersonaContext:
    """Assemble the per-turn persona context used by debug and future prompts."""

    relationship = build_learner_relationship_profile_from_memory(
        student_id=student_id,
        learner_memory=learner_memory,
    )
    affect_state = build_classroom_affect_state_for_turn(
        turn_label=turn_label,
        evaluation=evaluation,
        same_goal_attempt_count=same_goal_attempt_count,
        repair_mode=repair_mode,
        recent_turn_labels=recent_turn_labels,
        relationship_signals=relationship.relationship_signals,
        interruption_state=interruption_state,
    )
    return LessonPersonaContext(
        profile=load_default_teacher_persona_profile(),
        relationship=relationship,
        affect_state=affect_state,
        airi_performance=build_airi_performance_plan_for_turn(
            affect_state=affect_state,
            turn_label=turn_label,
            teaching_action=teaching_action,
            evaluation=evaluation,
        ),
    )


__all__ = [
    "AiriPerformancePlan",
    "ClassroomAffectState",
    "DEFAULT_ALLOWED_PERSONA_INFLUENCES",
    "DEFAULT_PROTECTED_LESSON_AUTHORITIES",
    "DEFAULT_TEACHER_PERSONA_PROFILE_ID",
    "DEFAULT_TEACHER_PERSONA_PROFILE_VERSION",
    "LearnerRelationshipProfile",
    "LessonPersonaContext",
    "MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_BYTES",
    "MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1",
    "MILI_PERSONA_CAPSULE_PROMPT_STATUS",
    "MILI_PERSONA_CAPSULE_SOURCE",
    "MILI_PERSONA_CAPSULE_V1",
    "MILI_PERSONA_CAPSULE_VERSION",
    "MILI_PERSONA_INTERESTS_ANSWER_TURN_POLICY_USAGE",
    "MILI_PERSONA_INTERESTS_RUNTIME_USAGE",
    "MILI_PERSONA_SOUL_PATH",
    "PERSONA_CONTEXT_SCHEMA_VERSION",
    "PersonaInfluenceBoundaries",
    "TeacherPersonaProfile",
    "TeacherVoiceStyle",
    "build_airi_performance_plan_for_turn",
    "build_classroom_affect_state_for_turn",
    "build_default_lesson_persona_context",
    "build_learner_relationship_profile_from_memory",
    "build_lesson_persona_context_for_turn",
    "derive_relationship_signals",
    "load_default_teacher_persona_profile",
]
