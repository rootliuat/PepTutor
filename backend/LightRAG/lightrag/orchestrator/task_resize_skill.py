"""Recognize learner requests to make the active lesson task smaller."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal


TaskResizeIntent = Literal["word", "chunk", "slow"]


@dataclass(frozen=True)
class TaskResize:
    """A smaller task target derived from the current lesson block."""

    intent: TaskResizeIntent
    target: str
    source: str = "task_resize_skill"


class TaskResizeSkill:
    """Map "太长了" or "先教单词" into a word- or chunk-sized target."""

    def resize(
        self,
        *,
        learner_input: str,
        focus_vocabulary: Iterable[str],
        core_patterns: Iterable[str],
        answer_scope: Iterable[str],
        fallback_target: str,
    ) -> TaskResize | None:
        normalized = _resize_key(learner_input)
        if not normalized or _looks_like_definition_question(normalized):
            return None

        intent = _resize_intent(normalized)
        if intent is None:
            return None

        target = self._target_for_intent(
            intent=intent,
            focus_vocabulary=focus_vocabulary,
            core_patterns=core_patterns,
            answer_scope=answer_scope,
            fallback_target=fallback_target,
        )
        if not target:
            return None
        return TaskResize(intent=intent, target=target)

    def _target_for_intent(
        self,
        *,
        intent: TaskResizeIntent,
        focus_vocabulary: Iterable[str],
        core_patterns: Iterable[str],
        answer_scope: Iterable[str],
        fallback_target: str,
    ) -> str:
        vocab = _first_useful(focus_vocabulary)
        answer = _first_useful(answer_scope)
        pattern = _first_useful(core_patterns)
        fallback = fallback_target.strip()

        if intent == "word":
            return vocab or _word_target(answer or fallback or pattern)
        if intent == "slow":
            if vocab:
                return vocab
            return _chunk_target(fallback or answer or pattern)
        return _chunk_target(fallback or answer or pattern)


def _resize_intent(normalized: str) -> TaskResizeIntent | None:
    if any(token in normalized for token in ("先教单词", "教单词", "单词", "词")):
        return "word"
    if any(
        token in normalized
        for token in (
            "太长",
            "太多",
            "分段",
            "一句一句",
            "一段一段",
            "拆开",
            "拆小",
            "短一点",
            "少一点",
            "breakitdown",
            "shorter",
            "chunk",
        )
    ):
        return "chunk"
    if any(
        token in normalized
        for token in (
            "慢一点",
            "慢点",
            "太难",
            "不会",
            "跟不上",
            "听不懂",
            "不明白",
            "slower",
            "toohard",
        )
    ):
        return "slow"
    return None


def _first_useful(values: Iterable[str]) -> str:
    for value in values:
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return ""


def _word_target(text: str) -> str:
    tokens = _word_tokens(text)
    if not tokens:
        return text.strip()
    if len(tokens) == 1:
        return tokens[0]
    return tokens[-1].strip(".,!?")


def _chunk_target(text: str) -> str:
    cleaned = text.strip()
    tokens = _word_tokens(cleaned)
    if len(tokens) <= 3:
        return cleaned
    chunk_size = 3 if len(tokens) <= 6 else 4
    return " ".join(tokens[:chunk_size])


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?|[0-9]+|[\u4e00-\u9fff]+", text)


def _looks_like_definition_question(normalized: str) -> bool:
    return any(
        token in normalized
        for token in (
            "什么意思",
            "意思是",
            "怎么读",
            "怎么说",
            "为什么",
            "whatdoes",
            "mean",
            "meaning",
        )
    )


def _resize_key(text: str) -> str:
    return re.sub(r"[\s'’`\"“”.,!?！？。；;:：、，-]+", "", text.casefold())
