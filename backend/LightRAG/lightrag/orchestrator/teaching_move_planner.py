"""Select reusable teaching moves from learner signal and lesson brief."""

from __future__ import annotations

from typing import Any

from lightrag.pedagogy.evaluation import normalize_text
from lightrag.pedagogy.lesson_brief import CurrentTurnLessonBrief
from lightrag.pedagogy.teaching_move import TeachingMovePlan

_REFUSAL_HINTS = (
    "no",
    "nope",
    "i don't want",
    "i dont want",
    "don't want to",
    "dont want to",
    "not say",
    "skip",
    "pass",
    "不想",
    "不说",
    "不要",
    "算了",
    "跳过",
)


class TeachingMovePlanner:
    """Classify the learner signal and name the next reusable classroom move."""

    def plan(
        self,
        *,
        lesson_brief: CurrentTurnLessonBrief,
        learner_input: str,
        turn_label: str,
        decision: Any,
        state: Any,
    ) -> TeachingMovePlan:
        evidence_fields = [
            "turn_label",
            "planner.teaching_action",
            "runtime_state.last_eval_result",
        ]
        signal = self._detected_signal(
            lesson_brief=lesson_brief,
            learner_input=learner_input,
            turn_label=turn_label,
            decision=decision,
            state=state,
            evidence_fields=evidence_fields,
        )
        return self._move_for_signal(
            signal=signal,
            lesson_brief=lesson_brief,
            decision=decision,
            evidence_fields=evidence_fields,
        )

    def _detected_signal(
        self,
        *,
        lesson_brief: CurrentTurnLessonBrief,
        learner_input: str,
        turn_label: str,
        decision: Any,
        state: Any,
        evidence_fields: list[str],
    ) -> str:
        evaluation = getattr(state, "last_eval_result", None)
        teaching_action = getattr(decision, "teaching_action", "")

        if turn_label == "page_entry":
            return "page_entry"
        if turn_label == "ask_help":
            return "help_request"
        if turn_label == "ask_knowledge":
            return "knowledge_question"
        if turn_label == "social" or teaching_action == "redirect":
            return "off_topic"

        if evaluation in {"correct", "acceptable"} or teaching_action == "confirm":
            return "good_answer"

        if self._looks_like_refusal(learner_input):
            evidence_fields.append("learner_input")
            return "refusal"

        if self._looks_like_task_echo(
            learner_input=learner_input,
            lesson_brief=lesson_brief,
        ):
            evidence_fields.extend(
                [
                    "lesson_brief.answer_scope.must_not_accept",
                    "lesson_brief.likely_mistakes",
                ]
            )
            return "task_echo"

        if evaluation == "partially_correct":
            evidence_fields.append("lesson_brief.likely_mistakes")
            if self._likely_mistake(lesson_brief, "rough_item_sentence"):
                return "small_error"
            if self._looks_like_short_fragment(
                learner_input=learner_input,
                lesson_brief=lesson_brief,
            ):
                evidence_fields.append("lesson_brief.answer_scope.acceptable_answers")
                return "incomplete_answer"
            return "small_error"

        if evaluation == "off_topic":
            return "off_topic"

        if self._looks_like_short_fragment(
            learner_input=learner_input,
            lesson_brief=lesson_brief,
        ):
            evidence_fields.append("lesson_brief.answer_scope.acceptable_answers")
            return "incomplete_answer"

        return "incomplete_answer"

    def _move_for_signal(
        self,
        *,
        signal: str,
        lesson_brief: CurrentTurnLessonBrief,
        decision: Any,
        evidence_fields: list[str],
    ) -> TeachingMovePlan:
        teaching_action = getattr(decision, "teaching_action", "hint")
        if signal == "page_entry":
            return TeachingMovePlan(
                detected_signal="page_entry",
                move="open_with_probe",
                teaching_action=teaching_action,
                rationale="The learner has not answered yet; open the page from the active brief and ask one concrete probe.",
                evidence_fields_used=_unique(evidence_fields + ["lesson_brief.teaching_focus"]),
                expected_next_learner_action="Answer the first page probe with one short lesson-aware response.",
            )
        if signal == "refusal":
            return TeachingMovePlan(
                detected_signal="refusal",
                move="lower_pressure_reinvite",
                teaching_action="hint",
                rationale="The learner is resisting the turn; reduce pressure and ask for a very small attempt.",
                evidence_fields_used=_unique(evidence_fields),
                expected_next_learner_action="Try one word, one choice, or one short phrase from the active answer scope.",
            )
        if signal == "task_echo":
            return TeachingMovePlan(
                detected_signal="task_echo",
                move="convert_task_echo_to_answer",
                teaching_action="hint",
                rationale="The learner repeated a task instruction, so the next move must ask for a concrete answer instead of accepting the instruction.",
                evidence_fields_used=_unique(evidence_fields),
                expected_next_learner_action="Give one concrete answer item or a short personal sentence.",
            )
        if signal == "incomplete_answer":
            return TeachingMovePlan(
                detected_signal="incomplete_answer",
                move="prompt_missing_piece",
                teaching_action="hint",
                rationale="The answer has some lesson signal but is not complete enough for progression.",
                evidence_fields_used=_unique(evidence_fields + ["lesson_brief.answer_scope"]),
                expected_next_learner_action="Complete the target phrase or choose one acceptable answer from the brief.",
            )
        if signal == "small_error":
            return TeachingMovePlan(
                detected_signal="small_error",
                move="light_recast",
                teaching_action="hint",
                rationale="The learner's meaning is close; recast lightly without turning the turn into a grammar lecture.",
                evidence_fields_used=_unique(evidence_fields + ["lesson_brief.likely_mistakes"]),
                expected_next_learner_action="Repeat the corrected short sentence once, then try it independently.",
            )
        if signal == "help_request":
            return TeachingMovePlan(
                detected_signal="help_request",
                move="give_one_step_hint",
                teaching_action=teaching_action,
                rationale="The learner asked for help, so the next move should give one small scaffold and keep them in the task.",
                evidence_fields_used=_unique(evidence_fields + ["lesson_brief.support_vocabulary"]),
                expected_next_learner_action="Use the scaffold to attempt one answer, not wait for a full teacher answer.",
            )
        if signal == "knowledge_question":
            return TeachingMovePlan(
                detected_signal="knowledge_question",
                move="answer_briefly_then_return",
                teaching_action=teaching_action,
                rationale="The learner asked a knowledge question; answer narrowly and bridge back to the active lesson.",
                evidence_fields_used=_unique(evidence_fields + ["lesson_brief.materials"]),
                expected_next_learner_action="Acknowledge the explanation and return to the active page prompt.",
            )
        if signal == "off_topic":
            return TeachingMovePlan(
                detected_signal="off_topic",
                move="redirect_to_active_task",
                teaching_action="redirect",
                rationale="The learner turn does not serve the active answer scope; redirect to the current task.",
                evidence_fields_used=_unique(evidence_fields + ["lesson_brief.progression"]),
                expected_next_learner_action="Answer the current lesson prompt instead of continuing the side topic.",
            )
        return TeachingMovePlan(
            detected_signal="good_answer",
            move="confirm_and_advance",
            teaching_action=teaching_action,
            rationale="The learner answer is correct or acceptable under runtime evaluation, so the teacher can confirm and move forward.",
            evidence_fields_used=_unique(evidence_fields + ["lesson_brief.progression"]),
            expected_next_learner_action="Listen for the next prompt or answer the next block.",
        )

    def _looks_like_refusal(self, learner_input: str) -> bool:
        normalized = normalize_text(learner_input)
        lower = learner_input.casefold()
        if normalized in {"no", "nope", "skip", "pass"}:
            return True
        return any(token in lower for token in _REFUSAL_HINTS)

    def _looks_like_task_echo(
        self,
        *,
        learner_input: str,
        lesson_brief: CurrentTurnLessonBrief,
    ) -> bool:
        normalized_input = normalize_text(learner_input)
        if not normalized_input:
            return False
        must_not_accept = {
            normalize_text(value)
            for value in lesson_brief.answer_scope.must_not_accept
            if value
        }
        if normalized_input in must_not_accept:
            return True
        return self._likely_mistake(lesson_brief, "task_instruction_echo")

    def _likely_mistake(
        self,
        lesson_brief: CurrentTurnLessonBrief,
        likely_error: str,
    ) -> bool:
        return any(
            mistake.likely_error == likely_error
            for mistake in lesson_brief.likely_mistakes
        )

    def _looks_like_short_fragment(
        self,
        *,
        learner_input: str,
        lesson_brief: CurrentTurnLessonBrief,
    ) -> bool:
        tokens = set(normalize_text(learner_input).split())
        if not tokens:
            return True
        if len(tokens) > 3:
            return False
        answer_tokens = set()
        for answer in lesson_brief.answer_scope.acceptable_answers:
            answer_tokens.update(normalize_text(answer).split())
        for word in lesson_brief.support_vocabulary:
            answer_tokens.update(normalize_text(word).split())
        return bool(tokens & answer_tokens)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
