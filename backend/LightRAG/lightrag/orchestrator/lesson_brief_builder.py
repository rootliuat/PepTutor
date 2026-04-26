"""Build compact private teacher-prep briefs from exact lesson evidence."""

from __future__ import annotations

from typing import Any

from lightrag.orchestrator.lesson_evidence import LessonEvidence, LessonEvidenceBlock
from lightrag.pedagogy.evaluation import normalize_text
from lightrag.pedagogy.lesson_brief import (
    CurrentTurnLessonBrief,
    LessonBriefAnswerRubric,
    LessonBriefAnswerScope,
    LessonBriefMaterial,
    LessonBriefMisconceptionHint,
    LessonBriefPageContext,
    LessonBriefProgression,
    LessonBriefTeacherMove,
    LessonBriefTurnContext,
)
from lightrag.pedagogy.system_contract import BANNED_TEACHER_PHRASES

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


class LessonBriefBuilder:
    """Turn exact lesson evidence into one-turn teacher preparation."""

    def build(
        self,
        *,
        lesson_evidence: LessonEvidence,
        learner_input: str,
        turn_label: str,
        decision: Any,
        state: Any,
    ) -> CurrentTurnLessonBrief:
        block = lesson_evidence.exact_block
        if block is None:
            raise ValueError("LessonBriefBuilder requires exact block evidence")

        support_vocabulary = self._support_vocabulary(
            block=block,
            same_page_blocks=lesson_evidence.same_page_blocks,
        )
        acceptable_answers = self._answer_scope(
            block=block,
            same_page_blocks=lesson_evidence.same_page_blocks,
            last_teacher_question=getattr(state, "last_teacher_question", None),
        )
        must_not_accept = self._must_not_accept(block)
        expected_answer_shape = self._expected_answer_shape(
            block=block,
            acceptable_answers=acceptable_answers,
        )
        progression_condition = self._progression_condition(block)
        likely_mistakes = self._likely_mistakes(
            learner_input=learner_input,
            state=state,
            block=block,
        )

        return CurrentTurnLessonBrief(
            teaching_focus=self._teaching_focus(block),
            materials=self._materials(lesson_evidence),
            answer_scope=LessonBriefAnswerScope(
                expected_answer_shape=expected_answer_shape,
                acceptable_answers=acceptable_answers[:8],
                must_not_accept=must_not_accept,
                evidence_source_block_uid=block.block_uid,
            ),
            support_vocabulary=support_vocabulary[:12],
            likely_mistakes=likely_mistakes,
            progression=LessonBriefProgression(condition=progression_condition),
            page_context=LessonBriefPageContext(
                page_uid=lesson_evidence.exact_page.page_uid,
                page_type=lesson_evidence.exact_page.page_type,
                lesson_title=self._lesson_title(lesson_evidence),
                target_language=self._target_language(
                    block=block,
                    acceptable_answers=acceptable_answers,
                    support_vocabulary=support_vocabulary,
                ),
                block_sequence_summary=self._block_sequence_summary(
                    block=block,
                    same_page_blocks=lesson_evidence.same_page_blocks,
                ),
            ),
            turn_context=LessonBriefTurnContext(
                current_block_uid=block.block_uid,
                current_block_type=block.block_type,
                turn_label=turn_label,
                learner_input=learner_input,
                evaluation=getattr(state, "last_eval_result", None),
                awaiting_answer=getattr(state, "awaiting_answer", False),
                last_teacher_question=getattr(state, "last_teacher_question", None),
                recent_turn_labels=list(getattr(state, "recent_turn_labels", [])),
            ),
            answer_rubric=LessonBriefAnswerRubric(
                teaching_goal=block.teaching_goal,
                expected_answer_shape=expected_answer_shape,
                acceptable_variants=acceptable_answers[:8],
                must_not_accept=must_not_accept,
                progression_condition=progression_condition,
            ),
            misconception_map=likely_mistakes,
            teacher_move=LessonBriefTeacherMove(
                action=getattr(decision, "teaching_action", ""),
                response_focus=getattr(decision, "response_focus", ""),
                should_retrieve=getattr(decision, "retrieval_mode", "none") != "none",
                banned_phrases=list(BANNED_TEACHER_PHRASES),
            ),
        )

    def _teaching_focus(self, block: LessonEvidenceBlock) -> list[str]:
        return _unique_non_empty(
            [
                block.teaching_goal,
                _strip_metadata_prefix(block.teaching_summary),
            ]
        )[:2]

    def _materials(self, lesson_evidence: LessonEvidence) -> list[LessonBriefMaterial]:
        page = lesson_evidence.exact_page
        block = lesson_evidence.exact_block
        materials = [
            LessonBriefMaterial(
                source="exact_page",
                uid=page.page_uid,
                kind=page.page_type,
                summary=_strip_metadata_prefix(page.page_intro_cn),
                source_refs=page.source_refs,
            )
        ]
        if block is not None:
            materials.append(
                LessonBriefMaterial(
                    source="exact_block",
                    uid=block.block_uid,
                    kind=block.block_type,
                    summary=_strip_metadata_prefix(block.teaching_summary),
                    source_refs=block.source_refs,
                )
            )
        materials.extend(
            LessonBriefMaterial(
                source="same_page_support",
                uid=support.block_uid,
                kind=support.block_type,
                summary=_strip_metadata_prefix(support.teaching_summary),
                source_refs=support.source_refs,
            )
            for support in lesson_evidence.same_page_blocks[:3]
        )
        return materials

    def _support_vocabulary(
        self,
        *,
        block: LessonEvidenceBlock,
        same_page_blocks: list[LessonEvidenceBlock],
    ) -> list[str]:
        values: list[str] = []
        support_blocks = sorted(
            same_page_blocks,
            key=lambda candidate: (
                0 if candidate.block_type in {"picture_scene", "vocabulary"} else 1,
                candidate.block_uid,
            ),
        )
        for candidate in [block, *support_blocks]:
            values.extend(candidate.focus_vocabulary)
            values.extend(
                value
                for value in candidate.allowed_answer_scope
                if self._looks_like_classroom_answer_example(value)
            )
        return _unique_non_instruction(values)

    def _answer_scope(
        self,
        *,
        block: LessonEvidenceBlock,
        same_page_blocks: list[LessonEvidenceBlock],
        last_teacher_question: str | None,
    ) -> list[str]:
        if self._block_has_task_instruction(block) or self._question_has_task_instruction(
            last_teacher_question or ""
        ):
            examples = self._page_answer_examples(
                same_page_blocks=same_page_blocks,
                limit=8,
            )
            if examples:
                return examples

        return _unique_non_instruction(block.allowed_answer_scope)

    def _page_answer_examples(
        self,
        *,
        same_page_blocks: list[LessonEvidenceBlock],
        limit: int,
    ) -> list[str]:
        preferred_blocks = sorted(
            same_page_blocks,
            key=lambda candidate: (
                0 if candidate.block_type in {"picture_scene", "vocabulary"} else 1,
                candidate.block_uid,
            ),
        )
        examples: list[str] = []
        for candidate in preferred_blocks:
            for value in [*candidate.focus_vocabulary, *candidate.allowed_answer_scope]:
                if not self._looks_like_classroom_answer_example(value):
                    continue
                examples.append(value)
                if len(_unique_non_instruction(examples)) >= limit:
                    return _unique_non_instruction(examples)[:limit]
        return _unique_non_instruction(examples)[:limit]

    def _expected_answer_shape(
        self,
        *,
        block: LessonEvidenceBlock,
        acceptable_answers: list[str],
    ) -> str:
        if self._block_has_task_instruction(block):
            return (
                "A concrete party-list item or a short first-person list sentence, "
                "for example: cake / orange juice / I'm going to bring cake."
            )
        if block.allowed_answer_scope or acceptable_answers:
            return "One answer that fits the current block's allowed answer scope."
        return "A short lesson-aware learner response."

    def _progression_condition(self, block: LessonEvidenceBlock) -> str:
        if self._block_has_task_instruction(block):
            return (
                "Advance only after the learner gives their own concrete party-list item "
                "or a clear item-list sentence; do not advance on the task instruction itself."
            )
        return "Advance only when the active answer rubric is correct or acceptable."

    def _must_not_accept(self, block: LessonEvidenceBlock) -> list[str]:
        return _unique_non_empty(
            [
                value
                for value in [*block.core_patterns, *block.allowed_answer_scope]
                if self._looks_like_task_instruction(value)
            ]
        )

    def _likely_mistakes(
        self,
        *,
        learner_input: str,
        state: Any,
        block: LessonEvidenceBlock,
    ) -> list[LessonBriefMisconceptionHint]:
        if not self._block_has_task_instruction(block):
            return []
        normalized_input = normalize_text(learner_input)
        task_literals = {
            normalize_text(candidate)
            for candidate in [
                *self._probe_literal_candidates(
                    getattr(state, "last_teacher_question", None)
                ),
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
        evaluation = getattr(state, "last_eval_result", None)
        if evaluation == "partially_correct":
            return [
                LessonBriefMisconceptionHint(
                    likely_error="rough_item_sentence",
                    repair_move="Lightly remodel the sentence without a grammar lecture.",
                    scaffold_example="I'm going to bring an apple.",
                )
            ]
        if evaluation in {"unclear", "incorrect"}:
            return [
                LessonBriefMisconceptionHint(
                    likely_error="low_confidence_or_no_concrete_item",
                    repair_move="Lower pressure and offer one tiny item-level entry point.",
                    scaffold_example="cake",
                )
            ]
        return []

    def _target_language(
        self,
        *,
        block: LessonEvidenceBlock,
        acceptable_answers: list[str],
        support_vocabulary: list[str],
    ) -> list[str]:
        exact_values = _unique_non_instruction(
            [*block.core_patterns, *block.focus_vocabulary]
        )
        if exact_values:
            return exact_values[:8]
        return _unique_non_empty([*acceptable_answers, *support_vocabulary])[:8]

    def _block_sequence_summary(
        self,
        *,
        block: LessonEvidenceBlock,
        same_page_blocks: list[LessonEvidenceBlock],
    ) -> list[str]:
        return [
            f"{candidate.block_uid}: {candidate.block_type}"
            for candidate in [block, *same_page_blocks][:5]
        ]

    def _lesson_title(self, lesson_evidence: LessonEvidence) -> str:
        page = lesson_evidence.exact_page
        block = lesson_evidence.exact_block
        text = f"{page.page_intro_cn} {block.teaching_summary if block else ''}".casefold()
        if "farewell party" in text:
            return "Farewell party shopping list"
        if "zoom" in text and "salad" in text:
            return "Zoom and Zip salad story"
        return page.page_type

    def _block_has_task_instruction(self, block: LessonEvidenceBlock) -> bool:
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
        text = prompt.strip()
        lower = text.casefold()
        if lower.startswith("can you say:"):
            return self._looks_like_task_instruction(text.split(":", 1)[1])
        return self._looks_like_task_instruction(text)

    def _looks_like_task_instruction(self, text: str) -> bool:
        return text.strip().casefold().startswith(_TASK_INSTRUCTION_STARTERS)

    def _looks_like_classroom_answer_example(self, text: str) -> bool:
        lower = text.strip().casefold()
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


def _unique_non_instruction(values: list[str]) -> list[str]:
    return _unique_non_empty(
        [value for value in values if not _looks_like_task_instruction(value)]
    )


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _looks_like_task_instruction(text: str) -> bool:
    return text.strip().casefold().startswith(_TASK_INSTRUCTION_STARTERS)


def _strip_metadata_prefix(text: str) -> str:
    stripped = text.strip()
    for prefix in ("Theme:", "Key patterns:"):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :].strip()
    return stripped
