"""Hard lesson-safety contract for PepTutor teacher turns."""

from __future__ import annotations

import re


LESSON_AUTHORITY_ORDER = (
    "system_contract",
    "lesson_brief",
    "teaching_move",
    "runtime_state",
    "answer_rubric",
    "retrieval_evidence",
    "learner_memory",
    "teacher_soul",
    "persona_context",
)

PERSONA_MUST_NOT_CHANGE = (
    "target_answer",
    "correctness_judgment",
    "page_progression",
    "retrieval_scope",
    "current_block",
    "required_teaching_action",
)

BANNED_TEACHER_PHRASES = (
    "根据检索结果",
    "根据教材",
    "当前教学目标",
    "本页要求学生",
    "教材要求",
    "教学目标",
    "如果老师问你",
    "你可以怎么答",
    "Theme:",
    "Key patterns:",
    "teaching_goal",
    "teaching_summary",
    "lesson_brief",
    "teaching_move",
    "learner_memory",
    "persona_context",
    "teacher_soul",
    "natural_response_contract",
    "safety_fallback_response",
    "detected_signal",
    "evidence_fields_used",
    "expected_next_learner_action",
    "lesson_evidence",
    "page_context",
    "turn_context",
    "teaching_focus",
    "materials",
    "progression",
    "answer_scope",
    "answer_rubric",
    "misconception_map",
    "teacher_move",
    "support_vocabulary",
    "likely_mistakes",
    "current_block",
    "schema_version",
    "source_refs",
    "same_page_support",
    "same_unit_support",
    "exact_page",
    "exact_block",
    "retrieval",
    "planner",
    "persona",
    "AIRI",
    "debug",
    "memory",
    "block_uid",
    "page_uid",
    "TB-",
    "LEX-",
    "EXP-",
    "开放性的活动",
    "鼓励学生",
    "要求学生",
    "引导学生",
)

RAG_POLICY_RULES = (
    "Use retrieval evidence only as private support, not as the teacher voice.",
    "Do not retrieve when the active answer rubric is sufficient.",
    "If retrieval confidence is weak, ask one short clarifying question or return to the active task.",
)

_ASCII_TOKEN_RE = re.compile(r"^[a-z0-9_]+$", re.IGNORECASE)


def render_lesson_system_contract() -> str:
    """System-prompt rendering is intentionally empty.

    Runtime call order owns authority. Retrieval policy stays in retrieval code, and
    banned phrase checks run as response post-processing.
    """
    return ""


def postprocess_response(text: str) -> str:
    """Remove hard-banned internal phrases from learner-facing text."""
    processed = text
    for phrase in BANNED_TEACHER_PHRASES:
        processed = processed.replace(phrase, "")
    return processed


def matches_banned_teacher_phrase(text: str) -> bool:
    """Return true when text leaks hard-banned internal classroom phrasing."""
    lower = text.casefold()
    for phrase in BANNED_TEACHER_PHRASES:
        lowered_phrase = phrase.casefold()
        if _ASCII_TOKEN_RE.fullmatch(lowered_phrase):
            if re.search(
                rf"(?<![a-z0-9_]){re.escape(lowered_phrase)}(?![a-z0-9_])",
                lower,
            ):
                return True
            continue
        if lowered_phrase in lower:
            return True
    return False
