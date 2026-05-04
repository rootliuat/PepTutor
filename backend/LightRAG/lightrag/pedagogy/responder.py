"""Live responder prompt helpers for lesson open turns."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lightrag.pedagogy.classification_task_policy import (
    ClassificationShortAnswerDecision,
)
from lightrag.pedagogy.system_contract import (
    matches_banned_teacher_phrase,
)
from lightrag.pedagogy.planner import PlannerDecision
from lightrag.pedagogy.teacher_soul import load_teacher_kernel
from lightrag.orchestrator.lesson_llm_metering import (
    active_lesson_llm_call_count,
    default_lesson_llm_model,
    record_lesson_llm_call,
)
from lightrag.utils import logger


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _contains_curriculum_meta(text: str) -> bool:
    return matches_banned_teacher_phrase(text)


_MARKDOWN_EMPHASIS_RE = re.compile(
    r"(?<!\*)\*\*([^*\n]+)\*\*(?!\*)|(?<!_)__([^_\n]+)__(?!_)"
)
_MARKDOWN_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_EMOJI_RE = re.compile(
    "["
    "\U0001f1e6-\U0001f1ff"
    "\U0001f300-\U0001f5ff"
    "\U0001f600-\U0001f64f"
    "\U0001f680-\U0001f6ff"
    "\U0001f700-\U0001f77f"
    "\U0001f780-\U0001f7ff"
    "\U0001f800-\U0001f8ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001faff"
    "\u2600-\u26ff"
    "\u2700-\u27bf"
    "\ufe0f"
    "\u200d"
    "]+"
)
_PAGE_ENTRY_CHOICE_CUES = (
    "哪一块",
    "哪块",
    "哪一部分",
    "想先",
    "可以说",
    "选择",
    "选",
    "choose",
    "which",
)
_MODULE_CHOICE_ORDINAL_RE = re.compile(r"第[一二三四五六七八九十]+块")


def _loose_contract_text_key(text: str) -> str:
    normalized = _contract_text_key(text)
    normalized = normalized.replace("或者", "或").replace("还是", "或")
    return re.sub(r"[\s'’`\"“”.,!?！？。；;:：、，—–-]+", "", normalized)


def _module_choice_ordinals(text: str) -> list[str]:
    seen: list[str] = []
    for label in _MODULE_CHOICE_ORDINAL_RE.findall(text):
        if label not in seen:
            seen.append(label)
    return seen


def _looks_like_module_choice_prompt(text: str) -> bool:
    key = _loose_contract_text_key(text)
    if not key:
        return False
    if any(
        cue in key
        for cue in (
            "你想先学哪一块",
            "想先学哪一块",
            "想继续学哪一块",
            "想学哪一块",
            "你想先学哪块",
            "想先学哪块",
            "想继续学哪块",
            "想学哪块",
        )
    ):
        return True
    labels = _module_choice_ordinals(text)
    if len(labels) < 2:
        return False
    has_choice_question = ("?" in text or "？" in text) and any(
        connector in text.casefold()
        for connector in ("还是", "或者", " 或 ", " or ")
    )
    if has_choice_question:
        return True
    return any(
        cue in key
        for cue in (
            "先选一下",
            "你先选",
            "先选",
            "选一下",
            "选择",
            "可以说",
            "choose",
            "which",
        )
    )


def _module_choice_required_phrase_is_satisfied(
    *,
    response: str,
    required_phrase: str,
) -> bool:
    required_labels = _module_choice_ordinals(required_phrase)
    if len(required_labels) < 2:
        return False
    response_key = _loose_contract_text_key(response)
    if not _looks_like_module_choice_prompt(response):
        return False
    return all(label in response_key for label in required_labels)


def _required_phrase_is_satisfied(response: str, required_phrase: str) -> bool:
    response_lower = response.casefold()
    phrase_lower = required_phrase.casefold()
    if phrase_lower in response_lower:
        return True
    response_key = _loose_contract_text_key(response)
    phrase_key = _loose_contract_text_key(required_phrase)
    if phrase_key and phrase_key in response_key:
        return True
    if _looks_like_module_choice_prompt(required_phrase):
        return _module_choice_required_phrase_is_satisfied(
            response=response,
            required_phrase=required_phrase,
        )
    return False


def _strip_plain_text_markdown(text: str) -> str:
    text = _MARKDOWN_INLINE_CODE_RE.sub(r"\1", text)
    return _MARKDOWN_EMPHASIS_RE.sub(
        lambda match: match.group(1) or match.group(2) or "",
        text,
    )


def _strip_stream_chunk_markdown_tokens(text: str) -> str:
    return text.replace("**", "").replace("__", "").replace("`", "")


def _strip_teacher_voice_emojis(text: str) -> str:
    return _EMOJI_RE.sub("", text)


def _contract_text_key(text: str) -> str:
    normalized = text.casefold().replace("’", "'").replace("`", "'")
    normalized = normalized.replace("'", "")
    return " ".join(normalized.split())


def _phrases_matching_anchor(
    *,
    return_anchor: str | None,
    must_keep_phrases: list[str],
) -> list[str]:
    if not return_anchor:
        return []
    anchor_key = _contract_text_key(return_anchor)
    if not anchor_key:
        return []
    matches = [
        phrase
        for phrase in must_keep_phrases
        if (phrase_key := _contract_text_key(phrase))
        and (phrase_key in anchor_key or anchor_key in phrase_key)
    ]
    if matches:
        return matches
    return [return_anchor.strip()]


def render_classification_short_answer_reply(
    decision: ClassificationShortAnswerDecision,
) -> str:
    """Render a short teacher utterance from a deterministic classifying decision."""

    term = decision.canonical_term or decision.term or decision.learner_input
    category_text = _classification_category_choice_text(decision.category_names)
    target = decision.target_category
    target_examples = _classification_format_examples(decision.target_category_examples)
    page_examples = _classification_format_examples(decision.page_item_examples)

    if decision.kind == "exact_page_item":
        return _classification_with_next_step(
            f"你说的是 {term}，可以归到 {decision.matched_category}。",
            decision=decision,
        )
    if decision.kind == "alias_page_item":
        return _classification_with_next_step(
            f"你说的是 {decision.term}，这里按 {term} 来看，可以归到 {decision.matched_category}。",
            decision=decision,
        )
    if decision.kind == "related_category_term":
        examples = page_examples or target_examples
        if examples and decision.matched_category:
            return (
                f"{term} 可以算 {decision.matched_category}，不过这页图上我们先找本页词，"
                f"比如 {examples}。"
            )
        if decision.matched_category:
            return f"{term} 可以算 {decision.matched_category}。现在回到图上找一个 party word。"
    if decision.kind == "wrong_category":
        examples = target_examples or page_examples
        if target and examples:
            return f"{term} 属于 {decision.matched_category}；这一步先找 {target}，比如 {examples}。"
        if target:
            return f"{term} 属于 {decision.matched_category}；这一步先找 {target}。"
    if decision.kind == "off_topic":
        return (
            f"{term} 不在这个 party word 任务里。"
            f"我们先找一个 {category_text}。"
        )
    examples = target_examples or page_examples
    if decision.reason == "learner_uncertain" and examples:
        return (
            f"没关系，先看一个本页词：{examples.split(' 或 ')[0]}。"
            f"你再找一个 {category_text}。"
        )
    if examples:
        return f"这个词我先不乱判。我们回到图上找一个 party word，比如 {examples}。"
    return f"这个词我先不乱判。我们回到图上找一个 {category_text}。"


def classification_short_answer_next_prompt(
    decision: ClassificationShortAnswerDecision,
) -> str:
    if decision.target_category:
        return f"Find one {decision.target_category} word in the party picture."
    return "Find one party word in the picture."


def classification_short_answer_evaluation(
    decision: ClassificationShortAnswerDecision,
) -> str:
    if decision.kind in {"exact_page_item", "alias_page_item"}:
        return "acceptable"
    if decision.kind in {"related_category_term", "wrong_category"}:
        return "partially_correct"
    return "unclear"


def _classification_with_next_step(
    prefix: str,
    *,
    decision: ClassificationShortAnswerDecision,
) -> str:
    if decision.target_category:
        other_categories = [
            category
            for category in decision.category_names
            if category != decision.target_category
        ]
        if other_categories:
            next_category = _classification_category_choice_text(tuple(other_categories))
            return f"{prefix} 再找一个 {next_category}。"
        return f"{prefix} 再找一个本页词。"
    other_categories = [
        category for category in decision.category_names if category != decision.matched_category
    ]
    if other_categories:
        next_category = _classification_category_choice_text(tuple(other_categories))
        return f"{prefix} 现在再找一个 {next_category}。"
    return f"{prefix} 现在再找一个 party word。"


def _classification_category_choice_text(categories: tuple[str, ...]) -> str:
    if not categories:
        return "party word"
    if len(categories) == 1:
        return categories[0]
    return "、".join(categories[:-1]) + f" 或 {categories[-1]}"


def _classification_format_examples(examples: tuple[str, ...]) -> str:
    if not examples:
        return ""
    if len(examples) == 1:
        return examples[0]
    return " 或 ".join(examples)


@dataclass(frozen=True)
class LessonResponderTurnResult:
    text: str
    source: str
    llm_called: bool
    llm_provider: str
    latency_ms: int
    fallback_used: bool
    fallback_reason: str
    generated_reply: str = ""
    reject_rule: str | None = None
    reject_reason: str | None = None
    repair_reason: str = "none"
    llm_token_usage: dict[str, Any] | None = None


@dataclass(frozen=True)
class _NormalizedTeacherResponse:
    text: str
    rejected: bool = False
    reject_rule: str | None = None
    reject_reason: str | None = None
    repaired: bool = False
    repair_reason: str = "none"


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
        llm_provider: str = "unknown",
        llm_model: str = "unknown",
    ):
        self.complete_text = complete_text
        self.stream_text = stream_text
        self.llm_provider = llm_provider
        self.llm_model = llm_model or default_lesson_llm_model()
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
        return self.render_teacher_turn_result(
            learner_input=learner_input,
            turn_label=turn_label,
            decision=decision,
            state_snapshot=state_snapshot,
            page_snapshot=page_snapshot,
            block_snapshot=block_snapshot,
            learner_memory=learner_memory,
            retrieval_evidence=retrieval_evidence,
            support_evidence=support_evidence,
            return_anchor=return_anchor,
            fallback_response=fallback_response,
            persona_context=persona_context,
            lesson_brief=lesson_brief,
            lesson_evidence=lesson_evidence,
            teaching_move=teaching_move,
        ).text

    def render_teacher_turn_result(
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
    ) -> LessonResponderTurnResult:
        must_keep_phrases = self._must_keep_phrases(
            block_snapshot=block_snapshot,
            fallback_response=fallback_response,
        )
        hard_keep_phrases = self._hard_keep_phrases(
            turn_label=turn_label,
            decision=decision,
            state_snapshot=state_snapshot,
            return_anchor=return_anchor,
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

        started_at = time.perf_counter()
        call_count_before = active_lesson_llm_call_count()
        system_prompt = self._build_system_prompt()
        try:
            raw = self.complete_text(
                prompt,
                system_prompt=system_prompt,
                history_messages=[],
                max_tokens=220,
                _lesson_audit_tag=f"responder.render_teacher_turn.{turn_label}",
            )
            if active_lesson_llm_call_count() == call_count_before:
                record_lesson_llm_call(
                    prompt=prompt,
                    completion=raw,
                    system_prompt=system_prompt,
                    history_messages=[],
                    llm_provider=self.llm_provider,
                    llm_model=self.llm_model,
                    audit_tag=f"responder.render_teacher_turn.{turn_label}",
                    mode="complete",
                    status="success",
                    turn_label=turn_label,
                )
        except Exception as exc:
            result = self._build_teacher_response_result(
                text=fallback_response,
                turn_label=turn_label,
                started_at=started_at,
                llm_called=True,
                fallback_used=True,
                fallback_reason=f"llm_exception:{type(exc).__name__}",
                teacher_response_source="fallback",
                response_chars=len(fallback_response),
            )
            logger.warning(
                "Lesson responder failed, using deterministic teacher response: %s",
                exc,
            )
            return result

        normalized = self._normalize_teacher_response(
            raw,
            fallback_response,
            learner_input=learner_input,
            turn_label=turn_label,
            must_keep_phrases=hard_keep_phrases,
            page_snapshot=page_snapshot,
            block_snapshot=block_snapshot,
            retrieval_evidence=retrieval_evidence,
            support_evidence=support_evidence,
        )
        fallback_used = normalized.rejected and raw != fallback_response
        return self._build_teacher_response_result(
            text=normalized.text,
            turn_label=turn_label,
            started_at=started_at,
            llm_called=True,
            fallback_used=fallback_used,
            fallback_reason="response_rejected" if fallback_used else "none",
            teacher_response_source=(
                "fallback"
                if fallback_used
                else "llm_repaired"
                if normalized.repaired
                else "llm"
            ),
            response_chars=len(normalized.text),
            generated_reply=raw,
            reject_rule=normalized.reject_rule,
            reject_reason=normalized.reject_reason,
            repair_reason=normalized.repair_reason,
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
        return self.render_teacher_turn_stream_result(
            learner_input=learner_input,
            turn_label=turn_label,
            decision=decision,
            state_snapshot=state_snapshot,
            page_snapshot=page_snapshot,
            block_snapshot=block_snapshot,
            learner_memory=learner_memory,
            retrieval_evidence=retrieval_evidence,
            support_evidence=support_evidence,
            return_anchor=return_anchor,
            fallback_response=fallback_response,
            on_delta=on_delta,
            persona_context=persona_context,
            lesson_brief=lesson_brief,
            lesson_evidence=lesson_evidence,
            teaching_move=teaching_move,
        ).text

    def render_teacher_turn_stream_result(
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
    ) -> LessonResponderTurnResult:
        if self.stream_text is None:
            result = self.render_teacher_turn_result(
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
            on_delta(result.text)
            return result

        must_keep_phrases = self._must_keep_phrases(
            block_snapshot=block_snapshot,
            fallback_response=fallback_response,
        )
        hard_keep_phrases = self._hard_keep_phrases(
            turn_label=turn_label,
            decision=decision,
            state_snapshot=state_snapshot,
            return_anchor=return_anchor,
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
        started_at = time.perf_counter()
        call_count_before = active_lesson_llm_call_count()
        system_prompt = self._build_system_prompt()
        try:
            for chunk in self.stream_text(
                prompt,
                system_prompt=system_prompt,
                history_messages=[],
                max_tokens=220,
                _lesson_audit_tag=f"responder.render_teacher_turn_stream.{turn_label}",
            ):
                if not chunk:
                    continue
                clean_chunk = _strip_teacher_voice_emojis(
                    _strip_stream_chunk_markdown_tokens(chunk)
                )
                if not clean_chunk:
                    continue
                chunks.append(clean_chunk)
                on_delta(clean_chunk)
            if active_lesson_llm_call_count() == call_count_before:
                record_lesson_llm_call(
                    prompt=prompt,
                    completion="".join(chunks),
                    system_prompt=system_prompt,
                    history_messages=[],
                    llm_provider=self.llm_provider,
                    llm_model=self.llm_model,
                    audit_tag=f"responder.render_teacher_turn_stream.{turn_label}",
                    mode="stream",
                    status="success",
                    turn_label=turn_label,
                )
        except Exception as exc:
            logger.warning(
                "Lesson responder streaming failed, handling with available output: %s",
                exc,
            )
            partial_response = "".join(chunks)
            if partial_response.strip():
                return self._build_teacher_response_result(
                    text=partial_response,
                    turn_label=turn_label,
                    started_at=started_at,
                    llm_called=True,
                    fallback_used=False,
                    fallback_reason="stream_exception_partial_output",
                    teacher_response_source="llm",
                    response_chars=len(partial_response),
                )

            result = self.render_teacher_turn_result(
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
            on_delta(result.text)
            return result

        streamed_response = "".join(chunks)
        normalized = self._normalize_teacher_response(
            streamed_response,
            fallback_response,
            learner_input=learner_input,
            turn_label=turn_label,
            must_keep_phrases=hard_keep_phrases,
            page_snapshot=page_snapshot,
            block_snapshot=block_snapshot,
            retrieval_evidence=retrieval_evidence,
            support_evidence=support_evidence,
        )
        if normalized.text:
            if normalized.rejected:
                if _contains_cjk(fallback_response):
                    on_delta(fallback_response)
                return self._build_teacher_response_result(
                    text=normalized.text,
                    turn_label=turn_label,
                    started_at=started_at,
                    llm_called=True,
                    fallback_used=streamed_response != fallback_response,
                    fallback_reason=(
                        "response_rejected"
                        if streamed_response != fallback_response
                        else "none"
                    ),
                    teacher_response_source=(
                        "fallback"
                        if streamed_response != fallback_response
                        else "llm"
                    ),
                    response_chars=len(normalized.text),
                    generated_reply=streamed_response,
                    reject_rule=normalized.reject_rule,
                    reject_reason=normalized.reject_reason,
                )
            response_text = normalized.text if normalized.repaired else streamed_response
            return self._build_teacher_response_result(
                text=response_text,
                turn_label=turn_label,
                started_at=started_at,
                llm_called=True,
                fallback_used=False,
                fallback_reason="none",
                teacher_response_source=(
                    "llm_repaired" if normalized.repaired else "llm"
                ),
                response_chars=len(response_text),
                generated_reply=streamed_response,
                repair_reason=normalized.repair_reason,
            )

        on_delta(fallback_response)
        return self._build_teacher_response_result(
            text=fallback_response,
            turn_label=turn_label,
            started_at=started_at,
            llm_called=True,
            fallback_used=True,
            fallback_reason="empty_or_rejected_response",
            teacher_response_source="fallback",
            response_chars=len(fallback_response),
            generated_reply=streamed_response,
            reject_rule=normalized.reject_rule,
            reject_reason=normalized.reject_reason,
        )

    def _build_teacher_response_result(
        self,
        *,
        text: str,
        turn_label: str,
        started_at: float,
        llm_called: bool,
        fallback_used: bool,
        fallback_reason: str,
        teacher_response_source: str,
        response_chars: int,
        generated_reply: str = "",
        reject_rule: str | None = None,
        reject_reason: str | None = None,
        repair_reason: str = "none",
    ) -> LessonResponderTurnResult:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "Lesson teacher response audit turn_label=%s llmcalled=%s llmprovider=%s latencyms=%d fallbackused=%s fallbackreason=%s teacherresponse_source=%s response_chars=%d",
            turn_label,
            str(llm_called).lower(),
            self.llm_provider,
            latency_ms,
            str(fallback_used).lower(),
            fallback_reason,
            teacher_response_source,
            response_chars,
        )
        return LessonResponderTurnResult(
            text=text,
            source=teacher_response_source,
            llm_called=llm_called,
            llm_provider=self.llm_provider,
            latency_ms=latency_ms,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            generated_reply=generated_reply,
            reject_rule=reject_rule,
            reject_reason=reject_reason,
            repair_reason=repair_reason,
        )

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
        payload = self._build_turn_frame_prompt(
            learner_input=learner_input,
            turn_label=turn_label,
            decision=decision,
            state_snapshot=state_snapshot,
            page_snapshot=page_snapshot,
            block_snapshot=block_snapshot,
            learner_memory=learner_memory,
            retrieval_evidence=retrieval_evidence,
            support_evidence=support_evidence,
            return_anchor=return_anchor,
            fallback_response=fallback_response,
            must_keep_phrases=must_keep_phrases,
            persona_context=persona_context,
            lesson_brief=lesson_brief,
            lesson_evidence=lesson_evidence,
            teaching_move=teaching_move,
        )
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _build_turn_frame_prompt(
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
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "studentsaid": learner_input,
            "currentgoal": self._current_goal_for_frame(
                turn_label=turn_label,
                page_snapshot=page_snapshot,
                block_snapshot=block_snapshot,
                lesson_brief=lesson_brief,
            ),
            "diagnosis": self._diagnosis_for_frame(
                learner_input=learner_input,
                state_snapshot=state_snapshot,
                learner_memory=learner_memory,
                lesson_brief=lesson_brief,
                teaching_move=teaching_move,
                return_anchor=return_anchor,
            ),
            "teachermove": self._teacher_move_for_frame(
                decision=decision,
                state_snapshot=state_snapshot,
                teaching_move=teaching_move,
            ),
            "mustsay": self._must_say_for_frame(
                must_keep_phrases=must_keep_phrases,
                block_snapshot=block_snapshot,
                state_snapshot=state_snapshot,
            ),
            "style": self._style_for_frame(persona_context),
            "fallback": fallback_response,
        }

        rag_context = self._rag_context_for_frame(
            retrieval_evidence=retrieval_evidence,
            support_evidence=support_evidence,
        )
        if rag_context:
            payload["ragcontext"] = rag_context

        payload.update(
            {
                "teacher_kernel_source": "system_prompt",
                "turn_label": turn_label,
                "plan": decision.model_dump(),
                "safety_fallback_response": fallback_response,
                "page": self._compact_page_for_prompt(page_snapshot),
                "learner_memory": learner_memory or {},
                "natural_response_contract": self._natural_response_contract_for_frame(),
                "response_contract": [
                    "Use teachermove, diagnosis, and mustsay as the primary current-turn frame.",
                    "teaching_move is audit context only; do not expose it.",
                    "safety_fallback_response is only a failure fallback, not recommended wording.",
                ],
                "output_rules": [
                    "Never quote JSON keys, schema names, source refs, page/block IDs, or private rationale.",
                    "If must_keep_phrases is present, keep at least one phrase exactly as written.",
                    "Use learner_memory.memory_layers as private hints only.",
                    "Use persona_context only for tone, pacing, encouragement, and scaffold size.",
                    "If turn_label is page_entry and page.page_overview is present, name the modules briefly, avoid per-block explanations, and ask which one to start.",
                    "If turn_label is page_entry, transform page.page_intro_cn into a fresh teacher opening instead of copying metadata.",
                    "When the learner has said something, first respond to the child's intent; do not merely copy a keyword.",
                    "Do not put emojis in the teacher text; the frontend drives face and motion separately.",
                    "Avoid generic celebration. Use concrete acknowledgement plus the next reachable step.",
                    "Correct only the most important reachable point in this turn.",
                    "Keep only one next classroom action; do not combine module choice, explanation, options, and repeat drill in one reply.",
                    "Return plain text only.",
                ],
            }
        )
        if must_keep_phrases:
            payload["must_keep_phrases"] = must_keep_phrases
        compact_lesson_brief = self._compact_lesson_brief_for_prompt(lesson_brief)
        if compact_lesson_brief:
            payload["lesson_brief"] = compact_lesson_brief
        if teaching_move:
            payload["teaching_move"] = teaching_move
        compact_persona_context = self._compact_persona_context(persona_context)
        if compact_persona_context:
            payload["persona_context"] = compact_persona_context
        return_anchor_value = return_anchor
        if return_anchor_value:
            payload["return_anchor"] = return_anchor_value
        compact_lesson_evidence = self._compact_lesson_evidence_for_prompt(lesson_evidence)
        if compact_lesson_evidence:
            payload["lesson_evidence"] = compact_lesson_evidence
        return payload

    def _compact_page_for_prompt(
        self,
        page_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        compact: dict[str, Any] = {}
        page_intro = page_snapshot.get("page_intro_cn")
        if isinstance(page_intro, str) and page_intro.strip():
            compact["page_intro_cn"] = page_intro
        page_overview = page_snapshot.get("page_overview")
        if page_overview:
            compact["page_overview"] = page_overview
        return compact

    def _natural_response_contract_for_frame(self) -> dict[str, Any]:
        return {
            "voice": "one fresh child-facing teacher reply in Simplified Chinese",
            "mili_transfer_filters": [
                "hear_child_before_teaching",
                "one_small_step",
                "follow_child_readiness",
                "help_changes_method",
                "role_logic_stays_clear",
                "teacher_may_resize_method",
                "concrete_acknowledgement_not_generic_praise",
            ],
            "delivery_hygiene": [
                "Do not use emojis; AIRI handles expression and motion outside text.",
                (
                    "When the learner only chooses a module or gives partial input, "
                    "acknowledge the choice or attempt, then start the next small step "
                    "without celebration."
                ),
                (
                    "Praise only when it is tied to the learner's specific words or "
                    "strategy, not as a generic status label."
                ),
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
                "Persona and memory may change tone, pacing, and scaffold size only; "
                "they must not change facts, correctness, target answer, or progression"
            ),
        }

    def _compact_lesson_evidence_for_prompt(
        self,
        lesson_evidence: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not lesson_evidence:
            return None

        exact_page = lesson_evidence.get("exact_page") or {}
        exact_block = lesson_evidence.get("exact_block") or {}
        scope = lesson_evidence.get("scope") or {}
        compact: dict[str, Any] = {
            "schema_version": lesson_evidence.get("schema_version"),
            "scope": {
                key: scope.get(key)
                for key in ("grade", "semester", "unit")
                if scope.get(key) is not None
            },
            "exact_page": {
                key: exact_page.get(key)
                for key in ("page_uid", "page_type", "source_refs")
                if exact_page.get(key) is not None
            },
            "exact_block": {
                key: exact_block.get(key)
                for key in (
                    "block_uid",
                    "page_uid",
                    "block_type",
                    "teaching_summary",
                    "source_refs",
                )
                if exact_block.get(key) is not None
            },
        }
        same_page = lesson_evidence.get("same_page_support") or []
        if same_page:
            compact["same_page_support"] = [
                {
                    key: item.get(key)
                    for key in (
                        "block_uid",
                        "page_uid",
                        "block_type",
                        "source_refs",
                    )
                    if item.get(key) is not None
                }
                for item in same_page[:3]
            ]
        same_unit = lesson_evidence.get("same_unit_support") or []
        if same_unit:
            compact["same_unit_support"] = [
                {
                    key: item.get(key)
                    for key in (
                        "block_uid",
                        "page_uid",
                        "block_type",
                        "source_refs",
                    )
                    if item.get(key) is not None
                }
                for item in same_unit[:1]
            ]
        return compact

    def _compact_lesson_brief_for_prompt(
        self,
        lesson_brief: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not lesson_brief:
            return None

        page_context = lesson_brief.get("page_context") or {}
        turn_context = lesson_brief.get("turn_context") or {}
        answer_rubric = lesson_brief.get("answer_rubric") or {}

        compact: dict[str, Any] = {
            "schema_version": lesson_brief.get("schema_version"),
            "teaching_focus": lesson_brief.get("teaching_focus") or [],
            "materials": self._compact_lesson_brief_materials(
                lesson_brief.get("materials") or []
            ),
            "answer_scope": lesson_brief.get("answer_scope") or {},
            "support_vocabulary": (lesson_brief.get("support_vocabulary") or [])[:8],
            "likely_mistakes": lesson_brief.get("likely_mistakes") or [],
            "progression": lesson_brief.get("progression") or {},
            "page_context": {
                key: page_context.get(key)
                for key in ("page_uid", "page_type")
                if page_context.get(key) is not None
            },
            "turn_context": {
                key: turn_context.get(key)
                for key in ("current_block_uid", "current_block_type", "turn_label")
                if turn_context.get(key) is not None
            },
            "answer_rubric": {
                key: answer_rubric.get(key)
                for key in (
                    "teaching_goal",
                    "expected_answer_shape",
                    "acceptable_variants",
                    "must_not_accept",
                    "progression_condition",
                )
                if answer_rubric.get(key) is not None
            },
        }
        return compact

    def _compact_lesson_brief_materials(
        self,
        materials: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        compact_materials: list[dict[str, Any]] = []
        for item in materials:
            if not isinstance(item, dict):
                continue
            if item.get("source") not in {"exact_page", "exact_block"}:
                continue
            compact_materials.append(
                {
                    key: item.get(key)
                    for key in ("source", "uid", "kind", "summary", "source_refs")
                    if item.get(key) is not None
                }
            )
        return compact_materials

    def _current_goal_for_frame(
        self,
        *,
        turn_label: str,
        page_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
        lesson_brief: dict[str, Any] | None,
    ) -> str:
        page_overview = page_snapshot.get("page_overview") or {}
        modules = page_overview.get("modules") or []
        if turn_label == "page_entry" and modules:
            module_text = "；".join(
                f"{module.get('label')}: {module.get('summary')}"
                for module in modules[:3]
                if module.get("label") or module.get("summary")
            )
            choice_prompt = page_overview.get("choice_prompt")
            if module_text and choice_prompt:
                return f"简介本页模块：{module_text}。然后问学生：{choice_prompt}"
            if module_text:
                return f"简介本页模块：{module_text}。让学生选择先学哪一块。"

        if lesson_brief:
            focus = lesson_brief.get("teaching_focus")
            if isinstance(focus, str) and focus.strip():
                return focus.strip()
        for key in ("teaching_goal", "teaching_summary"):
            value = block_snapshot.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        intro = page_snapshot.get("page_intro_cn")
        if isinstance(intro, str) and intro.strip():
            return intro.strip()
        return "完成当前这一小步课堂任务。"

    def _diagnosis_for_frame(
        self,
        *,
        learner_input: str,
        state_snapshot: dict[str, Any],
        learner_memory: dict[str, Any] | None,
        lesson_brief: dict[str, Any] | None,
        teaching_move: dict[str, Any] | None,
        return_anchor: str | None,
    ) -> str:
        parts: list[str] = []
        if teaching_move:
            signal = teaching_move.get("detected_signal")
            rationale = teaching_move.get("rationale")
            expected = teaching_move.get("expected_next_learner_action")
            if signal:
                parts.append(f"signal={signal}")
            if rationale:
                parts.append(str(rationale))
            if expected:
                parts.append(f"next={expected}")

        if lesson_brief:
            mistakes = lesson_brief.get("likely_mistakes") or []
            if mistakes:
                mistake = mistakes[0]
                if isinstance(mistake, dict):
                    error = mistake.get("likely_error")
                    repair = mistake.get("repair_move")
                    if error or repair:
                        parts.append(f"stuck={error or repair}")
            progression = lesson_brief.get("progression") or {}
            condition = progression.get("condition")
            if condition:
                parts.append(f"advance_when={condition}")

        if return_anchor:
            parts.append(f"return_to={return_anchor}")
        repair_mode = state_snapshot.get("repair_mode")
        if isinstance(repair_mode, str) and repair_mode != "none":
            parts.append(f"repair={repair_mode}")
        if learner_input and not parts:
            parts.append("先回应学生本轮话，再给一个可完成的小步骤。")

        memory = learner_memory or {}
        memory_bits = [
            *(memory.get("common_mistakes") or [])[:1],
            *(memory.get("preferences") or [])[:1],
            *(memory.get("mastery_signals") or [])[:1],
        ]
        if memory_bits:
            parts.append("memory_hint=" + "；".join(str(bit) for bit in memory_bits))
        return "；".join(parts[:5]) or "按当前程序判断执行本轮教学动作。"

    def _teacher_move_for_frame(
        self,
        *,
        decision: PlannerDecision,
        state_snapshot: dict[str, Any],
        teaching_move: dict[str, Any] | None,
    ) -> str:
        repair_mode = state_snapshot.get("repair_mode")
        if isinstance(repair_mode, str) and repair_mode.startswith("task_resize_"):
            return "resize"
        move = teaching_move.get("move") if teaching_move else None
        if move == "open_with_module_choice":
            return "switchmodule"
        action = decision.teaching_action
        if action == "repeat_drill":
            return "repeatdrill"
        if move:
            return f"{action}:{move}"
        return action

    def _must_say_for_frame(
        self,
        *,
        must_keep_phrases: list[str] | None,
        block_snapshot: dict[str, Any],
        state_snapshot: dict[str, Any],
    ) -> str:
        repair_mode = state_snapshot.get("repair_mode")
        return_target = state_snapshot.get("return_target")
        if (
            isinstance(repair_mode, str)
            and repair_mode.startswith("task_resize_")
            and isinstance(return_target, str)
            and return_target.strip()
        ):
            return return_target.strip()
        if must_keep_phrases:
            return " 或 ".join(must_keep_phrases[:2])
        for key in ("allowed_answer_scope", "core_patterns", "return_anchors"):
            for value in block_snapshot.get(key, []):
                if not isinstance(value, str):
                    continue
                phrase = value.strip()
                if phrase and "..." not in phrase:
                    return phrase
        return ""

    def _style_for_frame(self, persona_context: dict[str, Any] | None) -> str:
        style = "米粒老师，短句，像真人老师；先听学生，再给一步。"
        if not persona_context:
            return style
        profile = persona_context.get("profile") or {}
        performance = persona_context.get("airi_performance") or {}
        display_name = profile.get("display_name") or "米粒老师"
        speech_style = performance.get("speech_style")
        expression = performance.get("expression")
        bits = [str(display_name), "短句", "像真人老师"]
        if speech_style:
            bits.append(f"speech={speech_style}")
        if expression:
            bits.append(f"expression={expression}")
        return "，".join(bits) + "；先听学生，再给一步。"

    def _rag_context_for_frame(
        self,
        *,
        retrieval_evidence: list[dict[str, str]],
        support_evidence: list[dict[str, str]],
    ) -> str:
        bits: list[str] = []
        for item in retrieval_evidence[:2]:
            summary = item.get("teaching_summary") or item.get("model_answer")
            if summary:
                bits.append(str(summary))
        for item in support_evidence[:2]:
            english = item.get("english")
            chinese = item.get("chinese")
            if english and chinese:
                bits.append(f"{english}: {chinese}")
            elif english:
                bits.append(str(english))
        return "；".join(bits)

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
                "display_name": profile.get("display_name"),
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
            "affect_state": {
                key: (persona_context.get("affect_state") or {}).get(key)
                for key in ("student_confidence", "stuckness", "interruption_state")
                if (persona_context.get("affect_state") or {}).get(key) is not None
            },
            "airi_performance": {
                key: (persona_context.get("airi_performance") or {}).get(key)
                for key in ("speech_style", "expression", "motion", "interrupt_policy")
                if (persona_context.get("airi_performance") or {}).get(key) is not None
            },
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
        learner_input: str = "",
        turn_label: str | None = None,
        must_keep_phrases: list[str] | None = None,
        page_snapshot: dict[str, Any] | None = None,
        block_snapshot: dict[str, Any] | None = None,
        retrieval_evidence: list[dict[str, str]] | None = None,
        support_evidence: list[dict[str, str]] | None = None,
    ) -> _NormalizedTeacherResponse:
        normalized = _strip_plain_text_markdown(" ".join(raw.strip().split()))
        normalized = " ".join(_strip_teacher_voice_emojis(normalized).split())
        if not normalized:
            return _NormalizedTeacherResponse(
                fallback_response,
                rejected=True,
                reject_rule="empty_response",
                reject_reason="LLM returned no usable teacher text.",
            )

        if not _contains_cjk(normalized) and _contains_cjk(fallback_response):
            if self._grounded_lexicon_response_can_skip_required_phrase(
                learner_input=learner_input,
                response=fallback_response,
                block_snapshot=block_snapshot,
                page_snapshot=page_snapshot,
                retrieval_evidence=retrieval_evidence,
                support_evidence=support_evidence,
            ):
                logger.info(
                    "Lesson responder repaired English-only grounded lexicon reply; keeping llm route.",
                )
                return _NormalizedTeacherResponse(
                    fallback_response,
                    repaired=True,
                    repair_reason="grounded_lexicon_english_only_repaired",
                )
            logger.warning(
                "Lesson responder returned English-only output; using deterministic Chinese fallback.",
            )
            return _NormalizedTeacherResponse(
                fallback_response,
                rejected=True,
                reject_rule="english_only",
                reject_reason="Teacher reply must contain Simplified Chinese scaffolding.",
            )

        if _contains_curriculum_meta(normalized):
            logger.warning(
                "Lesson responder leaked internal lesson metadata; using deterministic fallback.",
            )
            return _NormalizedTeacherResponse(
                fallback_response,
                rejected=True,
                reject_rule="curriculum_metadata_leak",
                reject_reason="Teacher reply exposed internal curriculum metadata.",
            )

        if self._drops_page_entry_module_choice(
            normalized,
            turn_label=turn_label,
            page_snapshot=page_snapshot,
        ):
            repaired = self._repair_page_entry_module_choice(
                page_snapshot=page_snapshot,
            )
            if repaired:
                logger.info(
                    "Lesson responder repaired page overview module choice; keeping llm route.",
                )
                return _NormalizedTeacherResponse(
                    repaired,
                    repaired=True,
                    repair_reason="page_entry_module_choice_repaired",
                )
            logger.warning(
                "Lesson responder dropped page overview module choice; using deterministic fallback.",
            )
            return _NormalizedTeacherResponse(
                fallback_response,
                rejected=True,
                reject_rule="page_entry_module_choice_missing",
                reject_reason="Multi-module page entry did not name the module choices and ask the learner to choose.",
            )

        if must_keep_phrases:
            if not any(
                _required_phrase_is_satisfied(normalized, phrase)
                for phrase in must_keep_phrases
            ):
                repaired = self._repair_grounded_lexicon_response_with_required_phrase(
                    learner_input=learner_input,
                    response=normalized,
                    fallback_response=fallback_response,
                    must_keep_phrases=must_keep_phrases,
                    block_snapshot=block_snapshot,
                    page_snapshot=page_snapshot,
                    retrieval_evidence=retrieval_evidence,
                    support_evidence=support_evidence,
                )
                if repaired:
                    logger.info(
                        "Lesson responder repaired grounded lexicon reply with required phrase; keeping llm route.",
                    )
                    return _NormalizedTeacherResponse(
                        repaired,
                        repaired=True,
                        repair_reason="grounded_lexicon_required_phrase_repaired",
                    )
                logger.warning(
                    "Lesson responder dropped required lesson phrase; using deterministic fallback.",
                )
                return _NormalizedTeacherResponse(
                    fallback_response,
                    rejected=True,
                    reject_rule="required_phrase_missing",
                    reject_reason=(
                        "Teacher reply omitted all required return-anchor or current-task phrases: "
                        + ", ".join(must_keep_phrases)
                    ),
                )

        return _NormalizedTeacherResponse(normalized)

    def _repair_page_entry_module_choice(
        self,
        *,
        page_snapshot: dict[str, Any] | None,
    ) -> str | None:
        if not page_snapshot:
            return None
        page_overview = page_snapshot.get("page_overview")
        if not isinstance(page_overview, dict):
            return None
        modules = page_overview.get("modules") or []
        if not isinstance(modules, list) or len(modules) < 2:
            return None
        labels = [
            str(module.get("label", "")).strip()
            for module in modules
            if isinstance(module, dict) and str(module.get("label", "")).strip()
        ]
        if len(labels) < 2:
            return None
        choice_prompt = str(page_overview.get("choice_prompt") or "").strip()
        if not choice_prompt:
            if len(labels) == 2:
                choice_prompt = f"你想先学哪一块？可以说 {labels[0]} 或 {labels[1]}。"
            else:
                choice_prompt = "你想先学哪一块？可以说 " + "、".join(labels[:-1]) + f" 或 {labels[-1]}。"
        intro = str(page_snapshot.get("page_intro_cn") or "").strip()
        label_text = "、".join(labels[:-1]) + f" 和 {labels[-1]}" if len(labels) > 1 else labels[0]
        if intro:
            return f"{intro} 这一页可以先选：{label_text}。{choice_prompt}"
        return f"这一页可以先选：{label_text}。{choice_prompt}"

    def _grounded_lexicon_response_can_skip_required_phrase(
        self,
        *,
        learner_input: str,
        response: str,
        block_snapshot: dict[str, Any] | None,
        page_snapshot: dict[str, Any] | None,
        retrieval_evidence: list[dict[str, str]] | None,
        support_evidence: list[dict[str, str]] | None,
    ) -> bool:
        term = self._extract_lexicon_query_term(learner_input)
        if not term:
            return False
        if not _contains_cjk(response):
            return False
        if not any(marker in response for marker in ("意思", "表示", "是", "理解为", "mean")):
            return False
        if any(
            marker in response.casefold()
            for marker in (
                "哪一块",
                "哪块",
                "第几块",
                "哪个板块",
                "第一块",
                "第二块",
                "第三块",
                "第四块",
                "which module",
                "first module",
                "second module",
            )
        ):
            return False
        term_key = _contract_text_key(term)
        if not term_key:
            return False

        context_text = json.dumps(
            {
                "page": page_snapshot or {},
                "block": block_snapshot or {},
                "retrieval": retrieval_evidence or [],
                "support": support_evidence or [],
            },
            ensure_ascii=False,
        )
        return term_key in _contract_text_key(context_text)

    def _repair_grounded_lexicon_response_with_required_phrase(
        self,
        *,
        learner_input: str,
        response: str,
        fallback_response: str,
        must_keep_phrases: list[str],
        block_snapshot: dict[str, Any] | None,
        page_snapshot: dict[str, Any] | None,
        retrieval_evidence: list[dict[str, str]] | None,
        support_evidence: list[dict[str, str]] | None,
    ) -> str | None:
        if not must_keep_phrases:
            return None
        if not self._grounded_lexicon_response_is_grounded(
            learner_input=learner_input,
            response=response,
            block_snapshot=block_snapshot,
            page_snapshot=page_snapshot,
            retrieval_evidence=retrieval_evidence,
            support_evidence=support_evidence,
        ):
            return None
        required_phrase = must_keep_phrases[0].strip()
        if not required_phrase:
            return None
        if self._lexicon_response_forces_module_choice(response):
            base_response = fallback_response
        elif _looks_like_module_choice_prompt(required_phrase):
            base_response = response
        else:
            base_response = fallback_response or response
        if _required_phrase_is_satisfied(base_response, required_phrase):
            return base_response
        if _looks_like_module_choice_prompt(required_phrase):
            return f"{base_response} {required_phrase}"
        return f"{base_response} 现在回到刚才的问题：{required_phrase}"

    def _grounded_lexicon_response_is_grounded(
        self,
        *,
        learner_input: str,
        response: str,
        block_snapshot: dict[str, Any] | None,
        page_snapshot: dict[str, Any] | None,
        retrieval_evidence: list[dict[str, str]] | None,
        support_evidence: list[dict[str, str]] | None,
    ) -> bool:
        term = self._extract_lexicon_query_term(learner_input)
        if not term:
            return False
        if not _contains_cjk(response):
            return False
        if not any(marker in response for marker in ("意思", "表示", "是", "理解为", "mean")):
            return False
        term_key = _contract_text_key(term)
        if not term_key:
            return False
        context_text = json.dumps(
            {
                "page": page_snapshot or {},
                "block": block_snapshot or {},
                "retrieval": retrieval_evidence or [],
                "support": support_evidence or [],
            },
            ensure_ascii=False,
        )
        return term_key in _contract_text_key(context_text)

    def _lexicon_response_forces_module_choice(self, response: str) -> bool:
        return bool(
            re.search(
                r"(?:我|老师)?帮你选了?[“\"]?第[一二三四五六七八九十]+块",
                response,
            )
            or re.search(r"先从第[一二三四五六七八九十]+块", response)
        )

    def _extract_lexicon_query_term(self, text: str) -> str | None:
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
        if (
            len(query.split()) <= 4
            and re.fullmatch(r"[A-Za-z][A-Za-z'’ -]{0,40}", query)
        ):
            return query.strip(" \"'`?？")
        return None

    def _drops_page_entry_module_choice(
        self,
        response: str,
        *,
        turn_label: str | None,
        page_snapshot: dict[str, Any] | None,
    ) -> bool:
        if turn_label != "page_entry" or not page_snapshot:
            return False
        page_overview = page_snapshot.get("page_overview")
        if not isinstance(page_overview, dict):
            return False
        modules = page_overview.get("modules") or []
        if not isinstance(modules, list) or len(modules) < 2:
            return False

        labels = [
            str(module.get("label", "")).strip()
            for module in modules
            if isinstance(module, dict) and str(module.get("label", "")).strip()
        ]
        response_key = _contract_text_key(response)
        if any(_contract_text_key(label) not in response_key for label in labels):
            return True
        if any(cue in response_key for cue in _PAGE_ENTRY_CHOICE_CUES):
            return False
        return not (
            ("还是" in response_key and "开始" in response_key)
            or (" or " in response_key and "start" in response_key)
            or (" or " in response_key and "begin" in response_key)
        )

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
        turn_label: str | None,
        decision: PlannerDecision,
        state_snapshot: dict[str, Any],
        return_anchor: str | None,
        must_keep_phrases: list[str],
    ) -> list[str]:
        if decision.teaching_action == "confirm":
            return must_keep_phrases
        if (
            turn_label == "ask_knowledge"
            and decision.retrieval_mode != "none"
            and (return_anchor or state_snapshot.get("awaiting_answer") is True)
        ):
            anchor_phrases = _phrases_matching_anchor(
                return_anchor=return_anchor,
                must_keep_phrases=must_keep_phrases,
            )
            return anchor_phrases or must_keep_phrases
        return []
