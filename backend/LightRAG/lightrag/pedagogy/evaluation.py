"""Local answer evaluation for lesson-mode turns."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from lightrag.pedagogy.types import EvaluationResult

_QUESTION_STARTERS = {
    "what",
    "why",
    "how",
    "can",
    "could",
    "do",
    "does",
    "is",
    "are",
    "where",
    "when",
}


def normalize_text(value: str) -> str:
    """Normalize learner text for tolerant answer matching."""
    lowered = value.casefold()
    cleaned = re.sub(r"[^a-z0-9'\s]", " ", lowered)
    return " ".join(cleaned.split())


def _tokenize(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", normalize_text(value)))


def evaluate_answer(
    answer: str,
    allowed_answer_scope: list[str],
) -> EvaluationResult:
    """Classify a learner answer against a small local answer scope."""
    normalized_answer = normalize_text(answer)
    if not normalized_answer:
        return "unclear"

    normalized_scope = [
        normalize_text(item) for item in allowed_answer_scope if normalize_text(item)
    ]
    if not normalized_scope:
        return "unclear"

    answer_tokens = _tokenize(normalized_answer)
    if not answer_tokens:
        return "unclear"
    scope_tokenized = [_tokenize(item) for item in normalized_scope]
    scope_has_single_word_target = any(len(tokens) <= 1 for tokens in scope_tokenized)

    if any(normalized_answer == item for item in normalized_scope):
        return "correct"

    if (len(answer_tokens) > 1 or scope_has_single_word_target) and any(
        normalized_answer in item or item in normalized_answer for item in normalized_scope
    ):
        return "acceptable"

    best_similarity = max(
        SequenceMatcher(None, normalized_answer, item).ratio()
        for item in normalized_scope
    )
    if best_similarity >= 0.88:
        return "acceptable"

    best_overlap = max(
        len(answer_tokens & item_tokens) / max(len(answer_tokens), 1)
        for item_tokens in scope_tokenized
    )
    if best_overlap >= 0.65:
        return "partially_correct"

    first_word = normalized_answer.split(" ", 1)[0]
    if normalized_answer.endswith("?") or first_word in _QUESTION_STARTERS:
        return "off_topic"

    if len(answer_tokens) <= 1:
        return "unclear"

    return "incorrect"
