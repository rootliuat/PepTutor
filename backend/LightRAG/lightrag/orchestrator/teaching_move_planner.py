"""Select reusable teaching moves from learner signal and lesson brief."""

from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Iterable
from typing import Any

from lightrag.pedagogy.evaluation import normalize_text
from lightrag.pedagogy.lesson_brief import CurrentTurnLessonBrief
from lightrag.pedagogy.teaching_move import (
    TeachingMoveActionContract,
    TeachingMovePlan,
)

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

_KNOWN_TARGET_INSTRUCTION_PHRASES = {
    "repeat after me",
    "read after me",
    "listen and repeat",
    "follow me",
    "you read this sentence",
    "read this sentence",
    "read this out",
    "can you say",
    "can you repeat",
    "can you read",
    "can you try",
    "do you know",
    "do you know the word",
}
_GENERIC_TARGET_PHRASES = {
    "let's talk",
    "lets talk",
    "let's try",
    "lets try",
    "let's learn",
    "lets learn",
    "robin",
}
_UNHELPFUL_SHORT_TARGET_FRAGMENTS = {
    "i'm",
    "im",
    "suggestion",
}
_TRUNCATED_TARGET_PREFIXES = (
    "comprehension ques",
    "a table showing tr",
)
_INSTRUCTION_PAYLOAD_RE = re.compile(
    r"^(?:can you try|can you repeat(?: after me)?|can you say|say this|"
    r"repeat after me|read after me|listen and repeat|read this|please repeat|"
    r"try to say|try saying|say after me|can you follow me and say|please say|"
    r"跟我读|你读这一句|把这句读出来|请跟老师说)\s*[:：]\s*(?P<body>.+)$",
    re.IGNORECASE,
)
_WORD_PROMPT_RE = re.compile(
    r"^(?:can you read|do you know(?: the word)?)\s+(?P<body>.+)$",
    re.IGNORECASE,
)
_PHONICS_AS_IN_RE = re.compile(
    r"\b(?:consonant\s+)?blend\s+['’`-]*(?P<blend>[a-z]{1,4})['’`-]*\s+as\s+in\s+['’`](?P<word>[a-z][a-z-]*)['’`]",
    re.IGNORECASE,
)
_PHONICS_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’/-]*")
_PHONICS_INSTRUCTION_WORDS = {
    "and",
    "after",
    "as",
    "can",
    "choose",
    "circle",
    "find",
    "follow",
    "group",
    "listen",
    "look",
    "me",
    "number",
    "read",
    "repeat",
    "say",
    "the",
    "to",
    "try",
    "write",
    "you",
}
_QUESTION_PREFIXES = (
    "what ",
    "what's ",
    "what is ",
    "where ",
    "when ",
    "who ",
    "whose ",
    "which ",
    "why ",
    "how ",
    "do ",
    "does ",
    "did ",
    "can ",
    "is ",
    "are ",
)
_QUESTION_TARGET_PREFIXES = (
    "what ",
    "what's ",
    "what is ",
    "where ",
    "when ",
    "who ",
    "which ",
    "why ",
    "how ",
)
_ACTION_TARGET_ROLES = {"question", "answer", "phrase", "phonics", "story"}
_EXPECTED_STUDENT_ACTIONS = {"read", "answer", "repeat", "choose", "role_play"}
_ACTION_SOURCES = {
    "block_core_pattern",
    "active_prompt",
    "return_anchor",
    "answer_scope",
    "phonics_context",
    "story_context",
    "fallback_conservative",
}


@dataclass(frozen=True)
class ClassroomTargetPhraseCandidate:
    """One possible classroom return target plus its source field."""

    source: str
    text: str


@dataclass(frozen=True)
class ClassroomTargetPhraseSelection:
    """Selected classroom return target without teacher-response wording."""

    phrase: str
    source: str
    rejected: tuple[dict[str, str], ...] = ()


def classroom_target_phrase_reasons(
    phrase: str,
    *,
    allow_short_word_target: bool = False,
) -> tuple[str, ...]:
    """Return diagnostic reasons when a phrase is a weak classroom target."""

    compact = _clean_target_phrase(phrase)
    normalized = _normalized_target_phrase(compact)
    if not normalized:
        return ()

    reasons: list[str] = []
    if any(normalized.startswith(prefix) for prefix in _TRUNCATED_TARGET_PREFIXES):
        reasons.append("target_phrase_looks_truncated")
    if normalized in _GENERIC_TARGET_PHRASES:
        reasons.append("target_phrase_too_generic")
    if (
        normalized in _KNOWN_TARGET_INSTRUCTION_PHRASES
        or normalized.startswith(
            (
                "can you say",
                "can you try",
                "can you repeat",
                "can you read",
                "do you know",
            )
        )
        or normalized.endswith(" with me")
    ):
        reasons.append("target_phrase_is_teacher_instruction")
    if normalized in _UNHELPFUL_SHORT_TARGET_FRAGMENTS:
        reasons.append("target_phrase_unhelpful_short_fragment")
    elif _is_short_ascii_fragment(compact) and not allow_short_word_target:
        reasons.append("target_phrase_too_short")
    return tuple(reasons)


def select_classroom_target_phrase(
    candidates: Iterable[ClassroomTargetPhraseCandidate | tuple[str, str | None]],
    *,
    allow_short_word_target: bool = False,
) -> ClassroomTargetPhraseSelection:
    """Pick the first usable classroom return target from structured evidence."""

    rejected: list[dict[str, str]] = []
    fallback: ClassroomTargetPhraseSelection | None = None
    seen: set[tuple[str, str]] = set()
    for raw_candidate in candidates:
        candidate = _coerce_target_candidate(raw_candidate)
        for phrase in _target_phrase_variants(candidate.text):
            key = (candidate.source, phrase.casefold())
            if key in seen:
                continue
            seen.add(key)
            reasons = classroom_target_phrase_reasons(
                phrase,
                allow_short_word_target=allow_short_word_target,
            )
            if not reasons:
                return ClassroomTargetPhraseSelection(
                    phrase=phrase,
                    source=candidate.source,
                    rejected=tuple(rejected),
                )
            rejected.append(
                {
                    "source": candidate.source,
                    "phrase": phrase,
                    "reason": ";".join(reasons),
                }
            )
            if (
                allow_short_word_target
                and reasons == ("target_phrase_too_short",)
                and fallback is None
            ):
                fallback = ClassroomTargetPhraseSelection(
                    phrase=phrase,
                    source=candidate.source,
                    rejected=tuple(rejected),
                )
    if fallback is not None:
        return fallback
    return ClassroomTargetPhraseSelection(phrase="", source="", rejected=tuple(rejected))


def _coerce_target_candidate(
    raw_candidate: ClassroomTargetPhraseCandidate | tuple[str, str | None],
) -> ClassroomTargetPhraseCandidate:
    if isinstance(raw_candidate, ClassroomTargetPhraseCandidate):
        return raw_candidate
    source, text = raw_candidate
    return ClassroomTargetPhraseCandidate(source=str(source), text=str(text or ""))


def _target_phrase_variants(text: str) -> tuple[str, ...]:
    compact = _clean_target_phrase(text)
    if not compact:
        return ()
    variants: list[str] = []
    phonics_match = _PHONICS_AS_IN_RE.search(compact)
    if phonics_match:
        variants.append(_clean_target_phrase(phonics_match.group("word")))
    repaired = _instruction_payload_target(compact)
    if repaired:
        variants.append(repaired)
    variants.append(compact)
    result: list[str] = []
    seen: set[str] = set()
    for phrase in variants:
        key = phrase.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(phrase)
    return tuple(result)


def _instruction_payload_target(phrase: str) -> str:
    match = _INSTRUCTION_PAYLOAD_RE.match(phrase)
    if match:
        return _clean_target_phrase(match.group("body"))
    match = _WORD_PROMPT_RE.match(phrase)
    if match:
        return _clean_target_phrase(match.group("body"))
    match = _PHONICS_AS_IN_RE.search(phrase)
    if match:
        return _clean_target_phrase(match.group("word"))
    return ""


def _clean_target_phrase(phrase: str) -> str:
    cleaned = " ".join(str(phrase or "").strip().split())
    cleaned = cleaned.strip("“”\"'`，,、；;:：").strip()
    cleaned = re.sub(r"([A-Za-z0-9])['’`]+(?=[.?!。！？]?$)", r"\1", cleaned)
    cleaned = re.sub(r"([A-Za-z0-9])['’`]+\s+([.?!。！？])$", r"\1\2", cleaned)
    return cleaned.strip("“”\"'`，,、；;:：").strip()


def _normalized_target_phrase(phrase: str) -> str:
    return _clean_target_phrase(phrase).strip("。！？!?.").casefold()


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def _is_short_ascii_fragment(phrase: str) -> bool:
    normalized = _normalized_target_phrase(phrase)
    return (
        bool(normalized)
        and not _contains_cjk(normalized)
        and len(normalized.split()) == 1
        and len(normalized) <= 12
    )


def _gentle_redirect_teaching_action_payload(
    *,
    block: Any | None,
    current_target: str,
    target_phrase: str,
    active_prompt: str,
    return_anchor: str,
) -> dict[str, str]:
    block_type = _block_text(block, "block_type")
    page_type = _block_text(block, "page_type")
    task_type = _block_text(block, "task_type")
    block_context = " ".join(
        [
            block_type,
            page_type,
            task_type,
            _block_text(block, "teaching_goal"),
            _block_text(block, "teaching_summary"),
            " ".join(_block_values(block, "core_patterns")),
            " ".join(_block_values(block, "return_anchors")),
        ]
    )
    if _is_phonics_context(block_context):
        answer_target = _phonics_answer_target(
            block=block,
            target_phrase=target_phrase,
            active_prompt=active_prompt,
            return_anchor=return_anchor,
        )
        return {
            "target_role": "phonics",
            "expected_student_action": "repeat",
            "question_target": "",
            "answer_target": answer_target,
            "answer_frame": "",
            "action_source": "phonics_context",
        }

    if "story" in f"{block_type} {page_type}".casefold():
        question_target = _story_question_target(
            block=block,
            target_phrase=target_phrase,
            active_prompt=active_prompt,
            return_anchor=return_anchor,
            current_target=current_target,
        )
        answer_target = _story_answer_target(block)
        return {
            "target_role": "story",
            "expected_student_action": "answer",
            "question_target": question_target,
            "answer_target": answer_target,
            "answer_frame": _answer_frame_for(question_target, answer_target),
            "action_source": "story_context",
        }

    question_target = _question_target(
        block=block,
        target_phrase=target_phrase,
        active_prompt=active_prompt,
        return_anchor=return_anchor,
        current_target=current_target,
    )
    answer_target = _answer_target(
        block=block,
        question_target=question_target,
        target_phrase=target_phrase,
    )
    cleaned_target = _teaching_action_target_phrase(target_phrase)
    reliable_question = _reliable_block_question_target(block)
    if reliable_question and _is_question(cleaned_target):
        cleaned_target = reliable_question
    if _is_question(cleaned_target):
        return {
            "target_role": "question",
            "expected_student_action": "answer",
            "question_target": cleaned_target,
            "answer_target": answer_target,
            "answer_frame": _answer_frame_for(cleaned_target, answer_target),
            "action_source": _action_source_for_target(
                block=block,
                target=cleaned_target,
                active_prompt=active_prompt,
                return_anchor=return_anchor,
            ),
        }
    if _same_phrase(cleaned_target, answer_target) or (
        cleaned_target and _looks_like_answer_sentence(cleaned_target)
    ):
        return {
            "target_role": "answer",
            "expected_student_action": "repeat",
            "question_target": question_target,
            "answer_target": cleaned_target or answer_target,
            "answer_frame": _answer_frame_for(question_target, cleaned_target or answer_target),
            "action_source": _action_source_for_target(
                block=block,
                target=cleaned_target or answer_target,
                active_prompt=active_prompt,
                return_anchor=return_anchor,
            ),
        }
    return {
        "target_role": "phrase",
        "expected_student_action": "read",
        "question_target": question_target,
        "answer_target": answer_target,
        "answer_frame": _answer_frame_for(question_target, answer_target),
        "action_source": _action_source_for_target(
            block=block,
            target=cleaned_target,
            active_prompt=active_prompt,
            return_anchor=return_anchor,
        ),
    }


def _block_text(block: Any | None, field: str) -> str:
    return str(getattr(block, field, "") or "")


def _block_values(block: Any | None, field: str) -> list[str]:
    values = getattr(block, field, None) if block is not None else None
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value or "").strip()]


def _block_phrase_candidates(block: Any | None) -> list[str]:
    candidates: list[str] = []
    for field in (
        "return_anchors",
        "core_patterns",
        "entry_probe_questions",
        "allowed_answer_scope",
        "focus_vocabulary",
    ):
        candidates.extend(_block_values(block, field))
    return candidates


def _is_phonics_context(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "phonics",
            "consonant blend",
            "vowel",
            "sound",
            "发音",
            "拼读",
            "字母组合",
            "/aʊ/",
            "/oʊ/",
        )
    )


def _phonics_answer_target(
    *,
    block: Any | None,
    target_phrase: str,
    active_prompt: str,
    return_anchor: str,
) -> str:
    primary_values = [
        target_phrase,
        active_prompt,
        return_anchor,
    ]
    block_values = [
        *_block_values(block, "core_patterns"),
        *_block_values(block, "return_anchors"),
        *_block_values(block, "allowed_answer_scope"),
        *_block_values(block, "focus_vocabulary"),
    ]
    for value in [*primary_values, *block_values]:
        match = _PHONICS_AS_IN_RE.search(value)
        if match:
            return _clean_target_phrase(match.group("word"))
    for value in primary_values:
        instruction_target = _instruction_payload_target(_clean_target_phrase(value))
        word = _single_safe_phonics_word(instruction_target)
        if word:
            return word
    for value in primary_values:
        cleaned = _clean_target_phrase(value)
        if _is_single_word(cleaned):
            return cleaned
    for value in [*primary_values, *block_values]:
        word = _first_phonics_word_candidate(value)
        if word:
            return word
    return ""


def _first_phonics_word_candidate(value: str) -> str:
    cleaned = _clean_target_phrase(value)
    if not cleaned:
        return ""
    instruction_target = _instruction_payload_target(cleaned)
    word = _single_safe_phonics_word(instruction_target)
    if word:
        return word
    parts = [
        part.strip()
        for part in re.split(r"[,，、;/；]|(?:\s+and\s+)", cleaned)
        if part.strip()
    ]
    for part in parts:
        word = _single_safe_phonics_word(part)
        if word:
            return word
    return _single_safe_phonics_word(cleaned)


def _single_safe_phonics_word(value: str) -> str:
    tokens = [
        token.strip("'’/-").casefold()
        for token in _PHONICS_WORD_RE.findall(value or "")
    ]
    if len(tokens) != 1:
        return ""
    token = tokens[0]
    if token in _PHONICS_INSTRUCTION_WORDS:
        return ""
    if not re.fullmatch(r"[a-z][a-z-]{1,24}", token):
        return ""
    return token


def _question_target(
    *,
    block: Any | None,
    target_phrase: str,
    active_prompt: str,
    return_anchor: str,
    current_target: str,
) -> str:
    reliable_question = _reliable_block_question_target(block)
    if reliable_question:
        return reliable_question
    for value in [
        active_prompt,
        return_anchor,
        current_target,
        target_phrase,
        *_block_values(block, "return_anchors"),
        *_block_values(block, "core_patterns"),
        *_block_values(block, "entry_probe_questions"),
    ]:
        question = _first_question(value)
        if question:
            return question
    return ""


def _story_question_target(
    *,
    block: Any | None,
    target_phrase: str,
    active_prompt: str,
    return_anchor: str,
    current_target: str,
) -> str:
    for value in [
        *_block_values(block, "entry_probe_questions"),
        active_prompt,
        return_anchor,
        current_target,
        target_phrase,
        *_block_values(block, "core_patterns"),
        *_block_values(block, "return_anchors"),
    ]:
        question = _first_question(value)
        if question:
            return question
    return ""


def _answer_target(
    *,
    block: Any | None,
    question_target: str,
    target_phrase: str,
) -> str:
    cleaned_target = _teaching_action_target_phrase(target_phrase)
    if cleaned_target and not _is_question(cleaned_target) and _looks_like_answer_sentence(cleaned_target):
        return cleaned_target

    candidates = [
        *_block_values(block, "return_anchors"),
        *_block_values(block, "core_patterns"),
        *_block_values(block, "allowed_answer_scope"),
    ]
    question_key = _normalized_target_phrase(question_target)
    if question_key.startswith("where "):
        for candidate in candidates:
            cleaned = _clean_target_phrase(candidate)
            if _normalized_target_phrase(cleaned).startswith(("it's near", "it is near")):
                return cleaned
    if question_key.startswith("how tall is it"):
        return ""
    if question_key.startswith("how tall "):
        for candidate in candidates:
            cleaned = _normalize_declarative_target_punctuation(candidate)
            lowered = _normalized_target_phrase(cleaned)
            if lowered.startswith(("it's ", "it is ")) and "tall" in lowered:
                return cleaned
    if question_key.startswith("when do you get up"):
        for candidate in candidates:
            cleaned = _clean_target_phrase(candidate)
            if _normalized_target_phrase(cleaned).startswith(("i get up", "i often get up")):
                return cleaned
    if "favourite food" in question_key or "favorite food" in question_key:
        for candidate in candidates:
            cleaned = _clean_target_phrase(candidate)
            lowered = _normalized_target_phrase(cleaned)
            if "favourite food" in lowered or "favorite food" in lowered:
                return cleaned
    for candidate in candidates:
        cleaned = _clean_target_phrase(candidate)
        if cleaned and not _is_question(cleaned) and _looks_like_answer_sentence(cleaned):
            return cleaned
    return ""


def _story_answer_target(block: Any | None) -> str:
    for value in _block_values(block, "allowed_answer_scope"):
        cleaned = _clean_target_phrase(value)
        if re.search(r"\bwould\s+like\b", cleaned, flags=re.IGNORECASE):
            return cleaned
    for value in _block_values(block, "allowed_answer_scope"):
        cleaned = _clean_target_phrase(value)
        if cleaned:
            return cleaned
    return ""


def _answer_frame_for(question_target: str, answer_target: str) -> str:
    question_key = _normalized_target_phrase(question_target)
    answer = _clean_target_phrase(answer_target)
    if question_key.startswith("how tall is it"):
        return "It's ... metres tall."
    if question_key.startswith("how tall are you"):
        return "I'm ... metres tall."
    if question_key.startswith("who is taller than you"):
        return "... is taller than me."
    if question_key.startswith("who is heavier than you"):
        return "... is heavier than me."
    if question_key.startswith("where "):
        return "It's near ..."
    if question_key.startswith("what did you do") and "last weekend" in question_key:
        return "I ... last weekend."
    if question_key.startswith("when do you get up"):
        return "I get up at ..."
    if "favourite food" in question_key or "favorite food" in question_key:
        return "My favourite food is ..."
    if "suggestion" in question_key:
        return "You should ..."
    match = re.match(r"^([A-Z][A-Za-z]+)\s+would\s+like\b", answer)
    if match:
        return f"{match.group(1)} would like ..."
    if re.match(r"^I(?:'d| would)\s+like\b", answer, flags=re.IGNORECASE):
        return "I'd like ..."
    return ""


def _action_source_for_target(
    *,
    block: Any | None,
    target: str,
    active_prompt: str,
    return_anchor: str,
) -> str:
    if _contains_phrase(_block_values(block, "core_patterns"), target):
        return "block_core_pattern"
    if _contains_phrase(_block_values(block, "return_anchors"), target):
        return "return_anchor"
    if _contains_phrase(_block_values(block, "allowed_answer_scope"), target):
        return "answer_scope"
    if _same_phrase(target, active_prompt):
        return "active_prompt"
    if _same_phrase(target, return_anchor):
        return "return_anchor"
    return "fallback_conservative"


def _contains_phrase(values: list[str], target: str) -> bool:
    return any(_same_phrase(value, target) for value in values)


def _same_phrase(left: str, right: str) -> bool:
    return bool(left and right) and _normalized_target_phrase(left) == _normalized_target_phrase(right)


def _is_question(value: str) -> bool:
    cleaned = _clean_target_phrase(value)
    normalized = _normalized_target_phrase(cleaned)
    if _looks_like_answer_sentence(cleaned):
        return False
    return cleaned.endswith("?") or normalized.startswith(_QUESTION_PREFIXES)


def _first_question(value: str) -> str:
    cleaned = _clean_target_phrase(value)
    if not cleaned:
        return ""
    instruction_target = _instruction_payload_target(cleaned)
    if instruction_target and instruction_target != cleaned:
        if _normalized_target_phrase(instruction_target).startswith(
            _QUESTION_TARGET_PREFIXES
        ):
            return _first_question(instruction_target)
        return ""
    if "?" in cleaned:
        first = _clean_target_phrase(cleaned.split("?", 1)[0])
        if _normalized_target_phrase(first).startswith(_QUESTION_TARGET_PREFIXES):
            return _ensure_question_mark(first)
    if _is_question(cleaned) and _normalized_target_phrase(cleaned).startswith(
        _QUESTION_PREFIXES
    ):
        return _ensure_question_mark(cleaned)
    for match in re.finditer(
        r"\b(?:What(?:'s| is)?|Where|When|Who|Which|Why|How|Do|Does|Did|Can|Is|Are)\b[^.。!?！？]{1,100}\?",
        cleaned,
        flags=re.IGNORECASE,
    ):
        question = _clean_target_phrase(match.group(0))
        if _normalized_target_phrase(question).startswith(_QUESTION_TARGET_PREFIXES):
            return _ensure_question_mark(question)
    return ""


def _ensure_question_mark(value: str) -> str:
    cleaned = _clean_target_phrase(value).rstrip(".。!！")
    return cleaned if cleaned.endswith("?") else f"{cleaned}?"


def _reliable_block_question_target(block: Any | None) -> str:
    for field in ("core_patterns", "return_anchors", "entry_probe_questions"):
        for value in _block_values(block, field):
            question = _first_question(value)
            if question and not classroom_target_phrase_reasons(question):
                return question
    return ""


def _teaching_action_target_phrase(value: str) -> str:
    cleaned = _clean_target_phrase(value)
    instruction_target = _instruction_payload_target(cleaned)
    if instruction_target:
        cleaned = instruction_target
    return _normalize_declarative_target_punctuation(cleaned)


def _normalize_declarative_target_punctuation(value: str) -> str:
    cleaned = _clean_target_phrase(value)
    if _looks_like_answer_sentence(cleaned):
        normalized = cleaned.rstrip("?？").rstrip()
        if normalized and not normalized.endswith((".", "。", "!", "！")):
            normalized = f"{normalized}."
        return normalized
    return cleaned


def _durable_payload_target_phrase(
    *,
    fallback: str,
    action_payload: dict[str, str],
) -> str:
    target_role = action_payload.get("target_role", "")
    if target_role == "question" and action_payload.get("question_target"):
        return action_payload["question_target"]
    if target_role in {"answer", "phonics"} and action_payload.get("answer_target"):
        return action_payload["answer_target"]
    return fallback


def _validated_action_payload_fields(payload_fields: dict[str, Any]) -> dict[str, str]:
    contract = TeachingMoveActionContract.from_payload_fields(payload_fields)
    return contract.to_payload_fields()


def _fallback_action_payload_fields(
    *,
    target_phrase: str,
    active_prompt: str,
    return_anchor: str,
    preserve_page_uid: str = "",
    preserve_block_uid: str = "",
) -> dict[str, str]:
    target = _teaching_action_target_phrase(
        active_prompt or return_anchor or target_phrase
    )
    fallback_fields = {
        "target_role": "phrase",
        "expected_student_action": "read",
        "question_target": "",
        "answer_target": "",
        "answer_frame": "",
        "action_source": "fallback_conservative",
        "preserve_page_uid": preserve_page_uid,
        "preserve_block_uid": preserve_block_uid,
        "active_prompt": active_prompt,
        "return_anchor": return_anchor,
        "target_phrase": target,
    }
    return _validated_action_payload_fields(fallback_fields)


def _vocab_answer_return_action_payload(
    *,
    active_prompt: str,
    return_anchor: str,
) -> dict[str, str]:
    target_source = "active_prompt" if active_prompt else "return_anchor"
    target_phrase = active_prompt or return_anchor
    question_target = _first_question(target_phrase)
    if question_target:
        action_fields = {
            "target_role": "question",
            "expected_student_action": "answer",
            "question_target": question_target,
            "answer_target": "",
            "answer_frame": _answer_frame_for(question_target, ""),
            "action_source": target_source,
            "preserve_page_uid": "",
            "preserve_block_uid": "",
            "active_prompt": active_prompt,
            "return_anchor": return_anchor,
            "target_phrase": question_target,
        }
    else:
        action_fields = {
            "target_role": "phrase",
            "expected_student_action": "read",
            "question_target": "",
            "answer_target": "",
            "answer_frame": "",
            "action_source": target_source if target_phrase else "fallback_conservative",
            "preserve_page_uid": "",
            "preserve_block_uid": "",
            "active_prompt": active_prompt,
            "return_anchor": return_anchor,
            "target_phrase": _teaching_action_target_phrase(target_phrase),
        }
    return _validated_action_payload_fields(action_fields)


def _looks_like_answer_sentence(value: str) -> bool:
    normalized = _normalized_target_phrase(value)
    return normalized.startswith(
        (
            "it's ",
            "it is ",
            "i'd ",
            "i would ",
            "i'm ",
            "i am ",
            "i get ",
            "i often ",
            "i usually ",
            "zoom would ",
            "he ",
            "she ",
            "they ",
            "there ",
            "look ",
            "yes, ",
            "no, ",
        )
    )


def _is_single_word(value: str) -> bool:
    normalized = _normalized_target_phrase(value)
    return bool(re.fullmatch(r"[a-z][a-z-]{1,24}", normalized))


class TeachingMovePlanner:
    """Classify the learner signal and name the next reusable classroom move."""

    def plan_gentle_redirect(
        self,
        *,
        learner_input: str,
        interpreted_intent: str,
        current_target: str,
        target_phrase: str,
        active_prompt: str,
        return_anchor: str,
        next_action: str,
        correction_kind: str,
        route: str,
        turn_label: str,
        preserve_page_uid: str,
        preserve_block_uid: str,
        block: Any | None = None,
    ) -> TeachingMovePlan:
        """Return a structural move for task-preserving learner detours.

        This only names the classroom move for audit. Runtime and responder
        wording stay on their existing paths.
        """

        detected_signal = (
            "help_request"
            if interpreted_intent
            in {"language_support_request", "needs_support", "ask_help"}
            else "off_topic"
        )
        teaching_action = "hint" if detected_signal == "help_request" else "redirect"
        action_payload = _gentle_redirect_teaching_action_payload(
            block=block,
            current_target=current_target,
            target_phrase=target_phrase,
            active_prompt=active_prompt,
            return_anchor=return_anchor,
        )
        target_phrase = _durable_payload_target_phrase(
            fallback=target_phrase,
            action_payload=action_payload,
        )
        payload_fields = {
            "learner_input": learner_input,
            "interpreted_intent": interpreted_intent,
            "current_target": current_target,
            "target_phrase": target_phrase,
            "active_prompt": active_prompt,
            "return_anchor": return_anchor,
            "next_action": next_action,
            "correction_kind": correction_kind,
            "route": route,
            "turn_label": turn_label,
            "preserve_page_uid": preserve_page_uid,
            "preserve_block_uid": preserve_block_uid,
        }
        payload_fields.update(action_payload)
        try:
            payload_fields.update(_validated_action_payload_fields(payload_fields))
        except ValueError:
            payload_fields.update(
                _fallback_action_payload_fields(
                    target_phrase=target_phrase,
                    active_prompt=active_prompt,
                    return_anchor=return_anchor,
                    preserve_page_uid=preserve_page_uid,
                    preserve_block_uid=preserve_block_uid,
                )
            )
        return TeachingMovePlan(
            detected_signal=detected_signal,
            move="gentle_redirect",
            teaching_action=teaching_action,
            rationale=(
                "The learner turn needs a small scaffold or pullback while preserving "
                "the current page, block, and classroom target."
            ),
            evidence_fields_used=[
                "learner_input",
                "runtime_state.current_page_uid",
                "runtime_state.current_block_uid",
                "runtime_state.last_teacher_question",
                "teaching_block.teaching_goal",
                "teaching_block.core_patterns",
                "teaching_block.allowed_answer_scope",
                "teaching_block.return_anchors",
                "planner.route",
                "planner.turn_label",
            ],
            expected_next_learner_action=(
                "Return to the active prompt with one short answer or use the offered scaffold."
            ),
            payload_fields=payload_fields,
            constraints=[
                "Do not change the current page or block.",
                "Do not change the runtime route.",
                "Do not reopen module choice unless the existing route already does.",
                "Keep the pullback grounded in the current target phrase or active prompt.",
            ],
        )

    def plan_vocab_answer_return(
        self,
        *,
        learner_input: str,
        retrieval_mode: str,
        return_anchor: str | None,
        active_prompt: str | None,
        retrieval_count: int,
        support_count: int,
    ) -> TeachingMovePlan:
        """Return a structural move for grounded vocabulary interruption.

        This names the teaching action "answer the word, then return" without
        changing retrieval, responder wording, or runtime state writes.
        """

        query_term = _lexicon_query_term(learner_input) or ""
        evidence_fields = [
            "learner_input",
            "planner.retrieval_mode",
            "retrieval_selection.block_uids",
            "support_hits",
        ]
        if active_prompt:
            evidence_fields.append("runtime_state.last_teacher_question")
        if return_anchor:
            evidence_fields.append("return_anchor")
        effective_active_prompt = active_prompt or return_anchor or ""
        payload_fields = {
            "query_term": query_term,
            "retrieval_mode": retrieval_mode,
            "return_anchor": return_anchor or "",
            "active_prompt": effective_active_prompt,
            "return_to_current_task": bool(return_anchor or effective_active_prompt),
            "retrieval_evidence_count": retrieval_count,
            "support_evidence_count": support_count,
        }
        payload_fields.update(
            _vocab_answer_return_action_payload(
                active_prompt=effective_active_prompt,
                return_anchor=return_anchor or "",
            )
        )
        return TeachingMovePlan(
            detected_signal="vocabulary_question",
            move="vocab_answer_return",
            teaching_action="explain",
            rationale=(
                "The learner asked for a word meaning during the lesson; answer the "
                "word narrowly and return to the active classroom task."
            ),
            evidence_fields_used=evidence_fields,
            expected_next_learner_action=(
                "Use the short meaning, then continue with the current task prompt."
            ),
            payload_fields=payload_fields,
            constraints=[
                "Do not change the current page or block.",
                "Do not reopen module choice unless the active prompt is module choice.",
                "Ground the word meaning in retrieval or support evidence.",
            ],
        )

    def plan_single_block_guard(
        self,
        *,
        learner_input: str,
    ) -> TeachingMovePlan:
        """Return a structural move for unavailable module navigation.

        LessonRuntime remains responsible for the actual state write and the
        deterministic teacher reply; this payload only names the reusable
        classroom move for audit and future responder wiring.
        """

        evidence_fields = [
            "module_choice_skill.navigation_request",
            "page_overview.modules",
            "runtime_state.current_block_uid",
            "runtime_state.last_teacher_question",
        ]
        if learner_input.strip():
            evidence_fields.append("learner_input")
        return TeachingMovePlan(
            detected_signal="module_navigation_unavailable",
            move="single_block_guard",
            teaching_action="redirect",
            rationale=(
                "The learner requested another page module, but the active page has "
                "no available module choice; keep the learner in the current block."
            ),
            evidence_fields_used=evidence_fields,
            expected_next_learner_action=(
                "Continue with the current single-block prompt instead of choosing "
                "another module."
            ),
        )

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


def _lexicon_query_term(text: str) -> str | None:
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
