"""Live responder prompt helpers for lesson open turns."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from lightrag.pedagogy.system_contract import (
    matches_banned_teacher_phrase,
)
from lightrag.pedagogy.planner import PlannerDecision
from lightrag.pedagogy.teacher_soul import load_teacher_kernel
from lightrag.utils import logger


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _contains_curriculum_meta(text: str) -> bool:
    return matches_banned_teacher_phrase(text)


_MARKDOWN_EMPHASIS_RE = re.compile(
    r"(?<!\*)\*\*([^*\n]+)\*\*(?!\*)|(?<!_)__([^_\n]+)__(?!_)"
)
_MARKDOWN_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


def _strip_plain_text_markdown(text: str) -> str:
    text = _MARKDOWN_INLINE_CODE_RE.sub(r"\1", text)
    return _MARKDOWN_EMPHASIS_RE.sub(
        lambda match: match.group(1) or match.group(2) or "",
        text,
    )


def _strip_stream_chunk_markdown_tokens(text: str) -> str:
    return text.replace("**", "").replace("__", "").replace("`", "")


class LessonResponder:
    """Wrap a text-completion function as a lesson teacher voice."""

    def __init__(
        self,
        complete_text: Callable[..., str],
        *,
        stream_text: Callable[..., Iterable[str]] | None = None,
        teacher_kernel: str | None = None,
        teacher_kernel_path: str | Path | None = None,
        teacher_soul: str | None = None,
        teacher_soul_path: str | Path | None = None,
    ):
        self.complete_text = complete_text
        self.stream_text = stream_text
        kernel_override = teacher_kernel if teacher_kernel is not None else teacher_soul
        kernel_path = (
            teacher_kernel_path
            if teacher_kernel_path is not None
            else teacher_soul_path
        )
        self.teacher_kernel = (
            kernel_override.strip()
            if kernel_override is not None
            else load_teacher_kernel(kernel_path)
        )

    def render_teacher_turn(
        self,
        *,
        learner_input: str,
        turn_label: str,
        decision: PlannerDecision,
        state_snapshot: dict[str, Any],
        page_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
        learner_memory: dict[str, Any] | None,
        retrieval_evidence: list[dict[str, str]],
        support_evidence: list[dict[str, str]],
        return_anchor: str | None,
        fallback_response: str,
        persona_context: dict[str, Any] | None = None,
        lesson_brief: dict[str, Any] | None = None,
        lesson_evidence: dict[str, Any] | None = None,
        teaching_move: dict[str, Any] | None = None,
    ) -> str:
        must_keep_phrases = self._must_keep_phrases(
            block_snapshot=block_snapshot,
            fallback_response=fallback_response,
        )
        hard_keep_phrases = self._hard_keep_phrases(
            decision=decision,
            must_keep_phrases=must_keep_phrases,
        )
        prompt = self._build_prompt(
            learner_input=learner_input,
            turn_label=turn_label,
            decision=decision,
            state_snapshot=state_snapshot,
            page_snapshot=page_snapshot,
            block_snapshot=block_snapshot,
            learner_memory=learner_memory,
            persona_context=persona_context,
            retrieval_evidence=retrieval_evidence,
            support_evidence=support_evidence,
            return_anchor=return_anchor,
            fallback_response=fallback_response,
            must_keep_phrases=must_keep_phrases,
            lesson_brief=lesson_brief,
            lesson_evidence=lesson_evidence,
            teaching_move=teaching_move,
        )

        try:
            raw = self.complete_text(
                prompt,
                system_prompt=self._build_system_prompt(),
                history_messages=[],
                max_tokens=220,
                _lesson_audit_tag=f"responder.render_teacher_turn.{turn_label}",
            )
        except Exception as exc:
            logger.warning(
                "Lesson responder failed, using deterministic teacher response: %s",
                exc,
            )
            return fallback_response

        return self._normalize_teacher_response(
            raw,
            fallback_response,
            turn_label=turn_label,
            must_keep_phrases=hard_keep_phrases,
        )

    def render_teacher_turn_stream(
        self,
        *,
        learner_input: str,
        turn_label: str,
        decision: PlannerDecision,
        state_snapshot: dict[str, Any],
        page_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
        learner_memory: dict[str, Any] | None,
        retrieval_evidence: list[dict[str, str]],
        support_evidence: list[dict[str, str]],
        return_anchor: str | None,
        fallback_response: str,
        on_delta: Callable[[str], None],
        persona_context: dict[str, Any] | None = None,
        lesson_brief: dict[str, Any] | None = None,
        lesson_evidence: dict[str, Any] | None = None,
        teaching_move: dict[str, Any] | None = None,
    ) -> str:
        if self.stream_text is None:
            response = self.render_teacher_turn(
                learner_input=learner_input,
                turn_label=turn_label,
                decision=decision,
                state_snapshot=state_snapshot,
                page_snapshot=page_snapshot,
                block_snapshot=block_snapshot,
                learner_memory=learner_memory,
                persona_context=persona_context,
                retrieval_evidence=retrieval_evidence,
                support_evidence=support_evidence,
                return_anchor=return_anchor,
                fallback_response=fallback_response,
                lesson_brief=lesson_brief,
                lesson_evidence=lesson_evidence,
                teaching_move=teaching_move,
            )
            on_delta(response)
            return response

        must_keep_phrases = self._must_keep_phrases(
            block_snapshot=block_snapshot,
            fallback_response=fallback_response,
        )
        hard_keep_phrases = self._hard_keep_phrases(
            decision=decision,
            must_keep_phrases=must_keep_phrases,
        )
        prompt = self._build_prompt(
            learner_input=learner_input,
            turn_label=turn_label,
            decision=decision,
            state_snapshot=state_snapshot,
            page_snapshot=page_snapshot,
            block_snapshot=block_snapshot,
            learner_memory=learner_memory,
            persona_context=persona_context,
            retrieval_evidence=retrieval_evidence,
            support_evidence=support_evidence,
            return_anchor=return_anchor,
            fallback_response=fallback_response,
            must_keep_phrases=must_keep_phrases,
            lesson_brief=lesson_brief,
            lesson_evidence=lesson_evidence,
            teaching_move=teaching_move,
        )

        chunks: list[str] = []
        try:
            for chunk in self.stream_text(
                prompt,
                system_prompt=self._build_system_prompt(),
                history_messages=[],
                max_tokens=220,
                _lesson_audit_tag=f"responder.render_teacher_turn_stream.{turn_label}",
            ):
                if not chunk:
                    continue
                clean_chunk = _strip_stream_chunk_markdown_tokens(chunk)
                if not clean_chunk:
                    continue
                chunks.append(clean_chunk)
                on_delta(clean_chunk)
        except Exception as exc:
            logger.warning(
                "Lesson responder streaming failed, handling with available output: %s",
                exc,
            )
            partial_response = "".join(chunks)
            if partial_response.strip():
                return partial_response

            response = self.render_teacher_turn(
                learner_input=learner_input,
                turn_label=turn_label,
                decision=decision,
                state_snapshot=state_snapshot,
                page_snapshot=page_snapshot,
                block_snapshot=block_snapshot,
                learner_memory=learner_memory,
                persona_context=persona_context,
                retrieval_evidence=retrieval_evidence,
                support_evidence=support_evidence,
                return_anchor=return_anchor,
                fallback_response=fallback_response,
                lesson_brief=lesson_brief,
                lesson_evidence=lesson_evidence,
                teaching_move=teaching_move,
            )
            on_delta(response)
            return response

        streamed_response = "".join(chunks)
        normalized = self._normalize_teacher_response(
            streamed_response,
            fallback_response,
            turn_label=turn_label,
            must_keep_phrases=hard_keep_phrases,
        )
        if normalized:
            if normalized == fallback_response:
                if _contains_cjk(fallback_response):
                    on_delta(fallback_response)
                return normalized
            return streamed_response

        on_delta(fallback_response)
        return fallback_response

    def render_open_turn(
        self,
        *,
        learner_input: str,
        turn_label: str,
        decision: PlannerDecision,
        state_snapshot: dict[str, Any],
        page_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
        learner_memory: dict[str, Any] | None,
        retrieval_evidence: list[dict[str, str]],
        support_evidence: list[dict[str, str]],
        return_anchor: str | None,
        fallback_response: str,
        persona_context: dict[str, Any] | None = None,
        lesson_brief: dict[str, Any] | None = None,
        lesson_evidence: dict[str, Any] | None = None,
        teaching_move: dict[str, Any] | None = None,
    ) -> str:
        return self.render_teacher_turn(
            learner_input=learner_input,
            turn_label=turn_label,
            decision=decision,
            state_snapshot=state_snapshot,
            page_snapshot=page_snapshot,
            block_snapshot=block_snapshot,
            learner_memory=learner_memory,
            persona_context=persona_context,
            retrieval_evidence=retrieval_evidence,
            support_evidence=support_evidence,
            return_anchor=return_anchor,
            fallback_response=fallback_response,
            lesson_brief=lesson_brief,
            lesson_evidence=lesson_evidence,
            teaching_move=teaching_move,
        )

    def _build_prompt(
        self,
        *,
        learner_input: str,
        turn_label: str,
        decision: PlannerDecision,
        state_snapshot: dict[str, Any],
        page_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
        learner_memory: dict[str, Any] | None,
        retrieval_evidence: list[dict[str, str]],
        support_evidence: list[dict[str, str]],
        return_anchor: str | None,
        fallback_response: str,
        must_keep_phrases: list[str] | None = None,
        persona_context: dict[str, Any] | None = None,
        lesson_brief: dict[str, Any] | None = None,
        lesson_evidence: dict[str, Any] | None = None,
        teaching_move: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "teacher_kernel_source": "system_prompt",
            "learner_input": learner_input,
            "turn_label": turn_label,
            "plan": decision.model_dump(),
            "state": state_snapshot,
            "page": page_snapshot,
            "current_block": block_snapshot,
            "learner_memory": learner_memory or {},
            "retrieval_evidence": retrieval_evidence,
            "support_evidence": support_evidence,
            "safety_fallback_response": fallback_response,
            "natural_response_contract": {
                "voice": "one fresh child-facing teacher reply in Simplified Chinese",
                "length": "1 to 3 short sentences",
                "mili_transfer_filters": [
                    "hear_child_before_teaching",
                    "one_small_step",
                    "follow_child_readiness",
                    "help_changes_method",
                    "role_logic_stays_clear",
                    "teacher_may_resize_method",
                ],
                "private_inputs": [
                    "lesson_evidence",
                    "lesson_brief",
                    "teaching_move",
                    "learner_memory",
                    "persona_context",
                ],
                "must_not_copy": [
                    "JSON field names",
                    "source refs",
                    "block/page UIDs",
                    "brief or move rationale",
                    "deterministic fallback wording",
                    "fixed catchphrases as a required sign-off",
                ],
                "persona_memory_boundary": (
                    "persona and memory may change tone, pacing, and scaffold size only; "
                    "they must not change facts, correctness, target answer, or progression"
                ),
            },
            "response_contract": [
                "Generate one classroom reply from the current page evidence, private lesson preparation, selected teaching move, learner's latest words, memory hints, persona style, and scoped support evidence.",
                "lesson_evidence is exact page/block evidence first; retrieval_evidence is only a scoped supplement.",
                "lesson_brief is private teacher preparation, not wording to copy.",
                "teaching_move is an auditable classroom move selection, not wording to copy.",
                "safety_fallback_response is only a failure fallback, not recommended wording.",
                "Do not copy safety_fallback_response unless the live model cannot produce a compliant teacher reply.",
            ],
            "output_rules": [
                "Keep it short and teacher-like.",
                "Every response must contain Simplified Chinese; do not return English-only text.",
                "Sound warm and child-facing, not like a worksheet or test prompt.",
                "If teaching_action is redirect, gently steer back to the lesson.",
                "If retrieval_mode is branch, allow a short side explanation and then bridge back.",
                "If support evidence includes a word meaning or phonetic, use it naturally.",
                "Use lesson_evidence.exact_page and lesson_evidence.exact_block as the content authority for the active page and block.",
                "Use lesson_evidence.same_page_support and lesson_evidence.same_unit_support only as scoped support; do not infer across grades or units.",
                "Use lesson_brief.teaching_focus, materials, answer_scope, support_vocabulary, likely_mistakes, and progression as private preparation; paraphrase into natural classroom wording.",
                "Use the selected teaching move to choose the next classroom move; never expose private field names or rationale.",
                "Before writing the final reply, silently apply Mili's teaching principles: hear the child before teaching, give one small step, follow the child's readiness, change method after help, keep role-play logic clear, and resize your own method when needed.",
                "When the learner has said something, first respond to the child's intent, mistake, question, emotion, or fragment; do not merely copy a keyword into the target sentence.",
                "A reply is not good enough just because it includes the learner's word and the textbook sentence; it must make classroom sense for why this is the next step now.",
                "Correct only the most important reachable point in this turn; do not stack pronunciation, grammar, vocabulary, role-play, and next-page goals in one reply.",
                "Advance at most one classroom step beyond what the learner has shown; never jump from a word to a full dialogue unless the learner has already earned that step.",
                "If the learner asks for help or shows repeated stuckness, change method first: diagnose the stuck word, split smaller, change rhythm, or give a different example instead of replaying the same sentence.",
                "Keep role-play logic clean: a service question is not a customer answer, and a customer answer should not be another service question.",
                "It is allowed to briefly self-correct the teaching method, for example saying the previous step was too big and shrinking it.",
                "Never quote JSON keys, schema names, source refs, page/block IDs, or private rationale from lesson_brief, lesson_evidence, teaching_move, learner_memory, or persona_context.",
                "Do not repeat the same scene setup on consecutive turns; after the scene is set, focus on completing the sentence.",
                "Whenever you include a full English question, instruction, listening line, or model sentence, immediately add a short Simplified Chinese meaning or task cue; do not leave standalone English without Chinese support.",
                "If the learner is stuck, first receive the difficulty briefly, then give one small next step.",
                "Use specific praise instead of generic praise.",
                "Use learner_memory.memory_layers as private hints: facts predict stable needs, episodes describe recent context, and procedures shape teaching style only.",
                "If learner_memory.memory_conflicts is present, follow the chosen resolution privately and do not mention the conflict.",
                "Use persona_context only for tone, pacing, encouragement, scaffold granularity, classroom habits, speech style, and AIRI presentation intent.",
                "Do not force a fixed catchphrase into every reply.",
                "Never let persona_context change the target answer, correctness judgment, page progression, retrieval scope, teaching block, or required teaching_action.",
                "Do not mention stored memory, persona profile, AIRI, affect labels, or internal performance labels to the learner.",
                "If turn_label is page_entry and page.page_overview is present, briefly introduce those modules and ask the learner which one to start; do not start a drill yet.",
                "If turn_label is page_entry, transform page.page_intro_cn and current_block.teaching_summary into a fresh teacher opening instead of copying them.",
                "For page_entry, do not output curriculum metadata words such as Theme:, Key patterns:, teaching_goal, 开放性的活动, 鼓励学生, 要求学生, or 引导学生.",
                "For page_entry task instructions like Create, Identify, Group, Match, or List, ask the learner for a concrete answer or observation; do not ask them to repeat the instruction sentence.",
                "For any task instruction such as Practice, Design, Write, Create, Identify, Group, Match, or List, convert it into a classroom action; do not ask the learner to repeat the instruction sentence.",
                "If persona_context.airi_performance.speech_style is slow_split, split one target phrase into a smaller retry step.",
                "If persona_context.airi_performance.speech_style is gentle_correction, correct briefly and keep the required answer phrase intact.",
                "If persona_context.airi_performance.speech_style is short_prompt, keep the reply to one short redirect or prompt.",
                "If must_keep_phrases is present, keep at least one phrase exactly as written.",
                "If must_keep_phrases has multiple items, prefer keeping two choices instead of collapsing to one.",
                "Do not copy safety_fallback_response as a script; use it only to understand the minimum safe teacher move.",
                "Return plain text only.",
            ],
        }
        if lesson_brief:
            payload["lesson_brief"] = lesson_brief
        if lesson_evidence:
            payload["lesson_evidence"] = lesson_evidence
        if teaching_move:
            payload["teaching_move"] = teaching_move
        compact_persona_context = self._compact_persona_context(persona_context)
        if compact_persona_context:
            payload["persona_context"] = compact_persona_context
        if return_anchor:
            payload["return_anchor"] = return_anchor
        if must_keep_phrases:
            payload["must_keep_phrases"] = must_keep_phrases
        return json.dumps(payload, ensure_ascii=True, indent=2)

    def _build_system_prompt(self) -> str:
        return self.teacher_kernel.strip()

    def _compact_persona_context(
        self,
        persona_context: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not persona_context:
            return None

        profile = persona_context.get("profile") or {}
        relationship = persona_context.get("relationship") or {}
        boundaries = profile.get("boundaries") or {}
        voice_style = profile.get("voice_style") or {}

        return {
            "schema_version": persona_context.get("schema_version"),
            "teacher_profile": {
                "profile_id": profile.get("profile_id"),
                "version": profile.get("version"),
                "display_name": profile.get("display_name"),
                "role": profile.get("role"),
                "stable_traits": profile.get("stable_traits") or [],
                "teaching_style": profile.get("teaching_style") or [],
                "classroom_habits": profile.get("classroom_habits") or [],
                "catchphrases": profile.get("catchphrases") or [],
                "voice_hint": voice_style.get("tts_voice_hint"),
            },
            "relationship": {
                "student_id": relationship.get("student_id"),
                "relationship_signals": relationship.get("relationship_signals") or [],
                "common_mistakes": relationship.get("common_mistakes") or [],
                "preferences": relationship.get("preferences") or [],
                "mastery_signals": relationship.get("mastery_signals") or [],
                "semantic_memories": relationship.get("semantic_memories") or [],
            },
            "affect_state": persona_context.get("affect_state") or {},
            "airi_performance": persona_context.get("airi_performance") or {},
            "boundaries": {
                "content_authority": boundaries.get("content_authority"),
                "presentation_authority": boundaries.get("presentation_authority"),
                "allowed_to_shape": boundaries.get("allowed_to_shape") or [],
                "must_not_change": boundaries.get("must_not_change") or [],
                "can_change_target_answer": bool(
                    boundaries.get("can_change_target_answer")
                ),
                "can_change_correctness_judgment": bool(
                    boundaries.get("can_change_correctness_judgment")
                ),
                "can_change_page_progression": bool(
                    boundaries.get("can_change_page_progression")
                ),
            },
            "prompt_contract": [
                "Persona shapes delivery style only.",
                "Lesson runtime remains the authority for target answer, correctness, retrieval, current block, and page progression.",
                "Use relationship signals as private teaching hints; never reveal memory mechanics.",
            ],
        }

    def _normalize_teacher_response(
        self,
        raw: str,
        fallback_response: str,
        *,
        turn_label: str | None = None,
        must_keep_phrases: list[str] | None = None,
    ) -> str:
        normalized = _strip_plain_text_markdown(" ".join(raw.strip().split()))
        if not normalized:
            return fallback_response

        if not _contains_cjk(normalized) and _contains_cjk(fallback_response):
            logger.warning(
                "Lesson responder returned English-only output; using deterministic Chinese fallback.",
            )
            return fallback_response

        if _contains_curriculum_meta(normalized):
            logger.warning(
                "Lesson responder leaked internal lesson metadata; using deterministic fallback.",
            )
            return fallback_response

        if must_keep_phrases:
            normalized_lower = normalized.casefold()
            if not any(
                phrase.casefold() in normalized_lower for phrase in must_keep_phrases
            ):
                logger.warning(
                    "Lesson responder dropped required practice phrase; using deterministic fallback.",
                )
                return fallback_response

        return normalized

    def _must_keep_phrases(
        self,
        *,
        block_snapshot: dict[str, Any],
        fallback_response: str,
    ) -> list[str]:
        fallback_lower = fallback_response.casefold()
        candidates: list[str] = []
        for key in ("allowed_answer_scope", "core_patterns", "return_anchors"):
            for value in block_snapshot.get(key, []):
                if not isinstance(value, str):
                    continue
                phrase = value.strip()
                if not phrase or "..." in phrase:
                    continue
                if phrase.casefold() in fallback_lower and phrase not in candidates:
                    candidates.append(phrase)
        return candidates

    def _hard_keep_phrases(
        self,
        *,
        decision: PlannerDecision,
        must_keep_phrases: list[str],
    ) -> list[str]:
        if decision.teaching_action != "confirm":
            return []
        return must_keep_phrases
