"""Small deterministic policy for classification-task short answers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal


ClassificationShortAnswerKind = Literal[
    "exact_page_item",
    "alias_page_item",
    "related_category_term",
    "wrong_category",
    "off_topic",
    "unknown",
]

_CLASSIFICATION_TASK_TYPES = {
    "classify",
    "classification",
    "find_word",
    "find-word",
    "findword",
    "list",
}
_TASK_TEXT_RE = re.compile(
    r"\b(?:classify|group|sort|find\s+one|which\s+words?|list)\b|分类|归类|找一个",
    re.IGNORECASE,
)
_NAVIGATION_RE = re.compile(
    r"第[一二三四五六七八九十0-9]+(?:块|部分|模块)|"
    r"想学|选|模块|下一块|上一块|随便|你安排|"
    r"\b(?:next|previous|module|part)\b",
    re.IGNORECASE,
)
_QUESTION_RE = re.compile(r"\?|？|what\s+(?:does|is)\b|是什么意思|什么意思", re.IGNORECASE)
_UNCERTAINTY_RE = re.compile(
    r"^(?:我)?(?:不知道|不会|不懂|不清楚)|^(?:i\s+don'?t\s+know|no\s+idea)$",
    re.IGNORECASE,
)
_SHORT_SENTENCE_VERBS = {"like", "want", "bring", "buy", "need", "have", "am", "is", "are"}
_SAFE_RELATED_TERMS_BY_CATEGORY = {
    "food": {"pizza", "hamburger", "burger", "sandwich", "noodles", "rice"},
    "drinks": {"water", "juice", "cola", "soda"},
}
_SAFE_OFF_TOPIC_TERMS = {
    "basketball",
    "football",
    "news",
    "book",
    "books",
    "museum",
    "left",
    "right",
}
_CATEGORY_NAME_ALIASES = {
    "food": {"food", "foods", "食物", "吃的"},
    "drinks": {"drink", "drinks", "饮料", "喝的"},
    "drink": {"drink", "drinks", "饮料", "喝的"},
    "supplies": {"supply", "supplies", "用品", "物品"},
    "supply": {"supply", "supplies", "用品", "物品"},
}


@dataclass(frozen=True)
class ClassificationCategory:
    name: str
    items: tuple[str, ...] = ()
    aliases: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ClassificationShortAnswerDecision:
    kind: ClassificationShortAnswerKind
    learner_input: str
    term: str
    canonical_term: str
    matched_category: str | None = None
    target_category: str | None = None
    page_item_examples: tuple[str, ...] = ()
    target_category_examples: tuple[str, ...] = ()
    category_names: tuple[str, ...] = ()
    reason: str = ""


def classify_short_answer_for_task(
    *,
    learner_input: str,
    block: Any,
    last_teacher_question: str | None = None,
) -> ClassificationShortAnswerDecision | None:
    """Classify a short learner answer using only block metadata."""

    categories = _categories_for_block(block)
    if not _is_classification_task(block=block, categories=categories):
        return None
    if not is_short_answer(learner_input):
        return None

    raw_term = _clean_term(learner_input)
    target_category = _target_category_from_question(
        last_teacher_question or "",
        categories=categories,
    )
    category_names = tuple(category.name for category in categories)
    if _is_uncertainty(learner_input):
        return ClassificationShortAnswerDecision(
            kind="unknown",
            learner_input=learner_input,
            term=raw_term,
            canonical_term="",
            target_category=target_category,
            page_item_examples=_page_examples(categories),
            target_category_examples=_examples_for_category(categories, target_category),
            category_names=category_names,
            reason="learner_uncertain",
        )

    term_key = _term_key(raw_term)
    if not term_key:
        return None

    match = _match_category_term(term_key, categories)
    if match is not None:
        kind, canonical_term, matched_category = match
        if target_category and matched_category != target_category:
            return ClassificationShortAnswerDecision(
                kind="wrong_category",
                learner_input=learner_input,
                term=raw_term,
                canonical_term=canonical_term,
                matched_category=matched_category,
                target_category=target_category,
                page_item_examples=_page_examples(categories),
                target_category_examples=_examples_for_category(
                    categories,
                    target_category,
                ),
                category_names=category_names,
                reason=f"{kind}_outside_target_category",
            )
        return ClassificationShortAnswerDecision(
            kind=kind,
            learner_input=learner_input,
            term=raw_term,
            canonical_term=canonical_term,
            matched_category=matched_category,
            target_category=target_category,
            page_item_examples=_examples_for_category(categories, matched_category),
            target_category_examples=_examples_for_category(categories, target_category),
            category_names=category_names,
            reason=kind,
        )

    if term_key in _SAFE_OFF_TOPIC_TERMS:
        return ClassificationShortAnswerDecision(
            kind="off_topic",
            learner_input=learner_input,
            term=raw_term,
            canonical_term=raw_term,
            target_category=target_category,
            page_item_examples=_page_examples(categories),
            target_category_examples=_examples_for_category(categories, target_category),
            category_names=category_names,
            reason="known_off_topic_term",
        )

    return ClassificationShortAnswerDecision(
        kind="unknown",
        learner_input=learner_input,
        term=raw_term,
        canonical_term=raw_term,
        target_category=target_category,
        page_item_examples=_page_examples(categories),
        target_category_examples=_examples_for_category(categories, target_category),
        category_names=category_names,
        reason="not_in_answer_scope",
    )


def is_short_answer(text: str) -> bool:
    cleaned = _clean_term(text)
    if not cleaned:
        return False
    if _is_uncertainty(cleaned):
        return True
    if _NAVIGATION_RE.search(cleaned) or _QUESTION_RE.search(cleaned):
        return False
    if re.fullmatch(r"[A-Za-z][A-Za-z'’ -]{0,60}", cleaned):
        words = [word for word in re.split(r"[\s-]+", cleaned) if word]
        if len(words) > 3:
            return False
        if any(word.casefold().strip("'’") in _SHORT_SENTENCE_VERBS for word in words):
            return False
        return True
    if re.fullmatch(r"[\u4e00-\u9fff]{1,8}", cleaned):
        return True
    return False


def _is_classification_task(
    *,
    block: Any,
    categories: tuple[ClassificationCategory, ...],
) -> bool:
    task_type = str(_block_value(block, "task_type", "") or "").strip().casefold()
    if task_type:
        return task_type in _CLASSIFICATION_TASK_TYPES
    text = " ".join(
        str(value or "")
        for value in (
            _block_value(block, "teaching_goal", ""),
            _block_value(block, "teaching_summary", ""),
            *(_block_value(block, "core_patterns", []) or []),
            *(_block_value(block, "entry_probe_questions", []) or []),
        )
    )
    return bool(categories and _TASK_TEXT_RE.search(text))


def _categories_for_block(block: Any) -> tuple[ClassificationCategory, ...]:
    scope = _answer_scope(block)
    raw_categories = scope.get("categories")
    categories: list[ClassificationCategory] = []
    if isinstance(raw_categories, list):
        for raw_category in raw_categories:
            if not isinstance(raw_category, dict):
                continue
            name = str(raw_category.get("name") or "").strip()
            if not name:
                continue
            items = tuple(
                str(item).strip()
                for item in raw_category.get("items", [])
                if str(item).strip()
            )
            aliases = {
                str(key).strip(): str(value).strip()
                for key, value in (raw_category.get("aliases") or {}).items()
                if str(key).strip() and str(value).strip()
            }
            categories.append(ClassificationCategory(name=name, items=items, aliases=aliases))

    if categories:
        return tuple(categories)

    parsed: list[ClassificationCategory] = []
    for value in _block_value(block, "allowed_answer_scope", []) or []:
        if not isinstance(value, str) or ":" not in value:
            continue
        name, raw_items = value.split(":", 1)
        items = tuple(item.strip() for item in raw_items.split(",") if item.strip())
        if name.strip() and items:
            parsed.append(ClassificationCategory(name=name.strip(), items=items))
    return tuple(parsed)


def _answer_scope(block: Any) -> dict[str, Any]:
    value = _block_value(block, "answer_scope", {}) or {}
    return value if isinstance(value, dict) else {}


def _block_value(block: Any, key: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _match_category_term(
    term_key: str,
    categories: tuple[ClassificationCategory, ...],
) -> tuple[ClassificationShortAnswerKind, str, str] | None:
    for category in categories:
        item_by_key = {_term_key(item): item for item in category.items}
        if term_key in item_by_key:
            return "exact_page_item", item_by_key[term_key], category.name

    for category in categories:
        item_keys = {_term_key(item) for item in category.items}
        for alias, canonical in category.aliases.items():
            alias_key = _term_key(alias)
            canonical_key = _term_key(canonical)
            if term_key not in {alias_key, canonical_key}:
                continue
            if canonical_key in item_keys:
                return "alias_page_item", canonical, category.name
            return "related_category_term", canonical, category.name

    for category in categories:
        safe_terms = _SAFE_RELATED_TERMS_BY_CATEGORY.get(category.name.casefold(), set())
        if term_key in safe_terms:
            return "related_category_term", term_key, category.name
    return None


def _target_category_from_question(
    question: str,
    *,
    categories: tuple[ClassificationCategory, ...],
) -> str | None:
    key = _term_key(question)
    if not key:
        return None
    padded = f" {key} "
    for category in categories:
        aliases = _category_aliases(category.name)
        aliases.update(_term_key(alias) for alias in category.aliases)
        for alias in aliases:
            if alias and f" {alias} " in padded:
                return category.name
    return None


def _category_aliases(name: str) -> set[str]:
    key = _term_key(name)
    aliases = {key}
    aliases.update(_CATEGORY_NAME_ALIASES.get(key, set()))
    if key.endswith("s"):
        aliases.add(key[:-1])
    else:
        aliases.add(f"{key}s")
    return {_term_key(alias) for alias in aliases if alias}


def _examples_for_category(
    categories: tuple[ClassificationCategory, ...],
    category_name: str | None,
    *,
    limit: int = 2,
) -> tuple[str, ...]:
    if not category_name:
        return ()
    for category in categories:
        if category.name == category_name:
            return tuple(category.items[:limit])
    return ()


def _page_examples(
    categories: tuple[ClassificationCategory, ...],
    *,
    limit: int = 3,
) -> tuple[str, ...]:
    examples: list[str] = []
    for category in categories:
        for item in category.items:
            if item not in examples:
                examples.append(item)
            if len(examples) >= limit:
                return tuple(examples)
    return tuple(examples)


def _is_uncertainty(text: str) -> bool:
    return bool(_UNCERTAINTY_RE.search(_clean_term(text)))


def _clean_term(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    return cleaned.strip(" \"'`“”‘’.,!?！？。；;:：、，")


def _term_key(text: str) -> str:
    normalized = _clean_term(text).casefold().replace("’", "'")
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
