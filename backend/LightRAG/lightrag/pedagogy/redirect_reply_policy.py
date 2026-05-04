"""Deterministic micro-repairs for answer-turn redirect wording."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from lightrag.pedagogy.teaching_move import TeachingMoveActionContract


_PHRASE_SCAFFOLD_BY_KEY = {
    "water": "水",
    "tea": "茶",
    "pizza": "披萨",
    "sandwich": "三明治",
    "sandwiches": "三明治",
    "please": "请",
    "clean": "清洁",
    "food": "食物",
    "drink": "饮料",
    "dinosaur": "恐龙",
    "subway": "地铁",
    "museum": "博物馆",
    "bookstore": "书店",
    "turnleft": "左转",
    "getup": "起床",
    "taller": "更高",
    "heavier": "更重",
    "howtallareyou": "你有多高？",
    "howtallisit": "它有多高？",
    "iamhungry": "我饿了。",
    "imhungry": "我饿了。",
    "im16metrestall": "我身高 1.6 米。",
    "ioftengetupat7oclock": "我经常七点起床。",
    "igetupat7oclock": "我七点起床。",
    "whendoyougetup": "你几点起床？",
    "science museum": "科学博物馆",
    "sciencemuseum": "科学博物馆",
    "museumshop": "博物馆商店",
    "thesciencemuseumisnearthedoor": "科学博物馆在门附近。",
    "itsnearthedoor": "它在门旁边。",
    "itsnearthelibrary": "它在图书馆旁边。",
    "whatsyourfavouritefood": "你最喜欢的食物是什么？",
    "whatisyourfavouritefood": "你最喜欢的食物是什么？",
    "whatsyourfavoritefood": "你最喜欢的食物是什么？",
    "whatisyourfavoritefood": "你最喜欢的食物是什么？",
    "whatwouldyouliketodrink": "你想喝什么？",
    "whatwouldyouliketoeat": "你想吃什么？",
    "whatdidyoudolastweekend": "你上个周末做了什么？",
    "lastweekend": "上周末",
    "whatwouldzoomliketoeat": "Zoom 想吃什么？",
    "whereisthemuseumshop": "博物馆商店在哪里？",
    "whereisthesciencemuseum": "科学博物馆在哪里？",
    "thatsthetallestdinosaur": "那是最高的恐龙。",
}

_KNOWN_REDIRECT_TARGETS = (
    "Where is the science museum?",
    "Where is the museum shop?",
    "The science museum is near the door.",
    "It's near the library.",
    "It's near the door.",
    "When do you get up?",
    "I often get up at 7 o'clock.",
    "I get up at 7 o'clock.",
    "What's your favourite food?",
    "What would you like to drink?",
    "What would you like to eat?",
    "science museum",
    "museum shop",
    "get up",
    "bookstore",
    "turn left",
)
_CHARACTER_NAME_KEYS = {
    "amy",
    "john",
    "mike",
    "pedro",
    "robin",
    "sarah",
    "wubinbin",
    "zhangpeng",
    "zip",
    "zoom",
}

_REDIRECT_MARKER_RE = re.compile(
    r"你刚才说的是|你刚说到(?:了)?|你说的是|你说了|你提到了目标句|我听到|"
    r"你刚说的是|试着说说|试着说|现在试着说|完整的句子|"
    r"老师(?:刚才)?问的是|老师刚问|"
    r"这一步先听清|先听，再说|我们先说这个|你来读|跟我读|"
    r"请你跟我读|把这句读出来|试着读|读一下|回到|先回到|先练|先看这个|"
    r"选入口|先选一块|我们先选一块|我们先选|你想先(?:看|学)哪一块|"
    r"你选哪一块|可以说[“\"]?第[一二三四五六七八九十]+块",
)
_NON_REDIRECT_TRANSLATION_RE = re.compile(r"用英语怎么说|完整句子是|how\s+do\s+you\s+say", re.I)
_MODULE_CHOICE_RE = re.compile(
    r"第[一二三四五六七八九十]+块|第二块|第一块|随便|你安排"
)
_PHONICS_TARGET_RE = re.compile(
    r"learn\s+the\s+consonant\s+blend\s+['’\"]?(?P<blend>[a-z]{1,3})['’\"]?"
    r"\s+as\s+in\s+['’\"]?(?P<example>[a-z]+)['’\"]?",
    re.IGNORECASE,
)


def looks_like_redirect_reply(teacher_reply: str) -> bool:
    """Return whether deterministic redirect rendering should inspect the reply."""

    return _looks_like_redirect(teacher_reply)


def maybe_render_redirect_reply(
    *,
    learner_input: str,
    target_phrase: str,
    teacher_reply: str,
    block: Any,
    active_prompt: str = "",
    return_anchor: str = "",
    action_fields: Mapping[str, object] | None = None,
) -> str | None:
    """Return a shorter redirect reply when evidence is deterministic.

    The helper does not decide route, block progression, correctness, or facts. It
    only renders a small redirect when the caller has already selected the active
    classroom target.
    """

    if not _looks_like_redirect(teacher_reply):
        return None
    learner_phrase = _learner_phrase(learner_input)
    if not learner_phrase or _looks_like_module_choice(learner_phrase):
        return None
    learner_key = _phrase_key(learner_phrase)
    has_action_fields = bool(action_fields)
    fields = _validated_action_fields(action_fields)
    invalid_action_fields = has_action_fields and not fields
    if (
        learner_key in _CHARACTER_NAME_KEYS
        and fields.get("target_role") != "story"
        and not _is_story_context(block)
    ):
        return None
    self_target_keys = (
        _action_contract_target_keys(fields)
        if fields and _looks_like_module_choice(teacher_reply)
        else set()
    )
    if not self_target_keys:
        self_target_keys = {_phrase_key(active_prompt), _phrase_key(return_anchor)}
        if not invalid_action_fields:
            self_target_keys.add(_phrase_key(target_phrase))
    if learner_key and learner_key in {
        key for key in self_target_keys if key
    }:
        return None

    action_reply = _render_action_field_redirect(
        learner_phrase=learner_phrase,
        block=block,
        action_fields=fields,
    )
    if action_reply:
        return action_reply
    if fields.get("target_role") == "phrase":
        phrase_target = _clean_phrase(
            target_phrase
            or active_prompt
            or return_anchor
            or fields.get("answer_target")
        )
        if phrase_target and not _known_phrase_scaffold(phrase_target):
            return None

    target = _select_redirect_target(
        block=block,
        active_prompt=active_prompt,
        return_anchor=return_anchor,
        target_phrase="" if invalid_action_fields else target_phrase,
        teacher_reply=teacher_reply,
        learner_phrase=learner_phrase,
    )
    if not target:
        return None
    phonics = normalize_redirect_read_target_for_phonics(block, target)
    if phonics is not None:
        return _render_phonics_redirect(
            learner_phrase=learner_phrase,
            phonics=phonics,
        )

    target_meaning = _known_phrase_scaffold(target) or _meaning_from_reply(
        teacher_reply,
        target,
    )
    if not _can_render_scaffold_target(target):
        return None
    if not target_meaning:
        anchor_meaning = _known_phrase_scaffold(return_anchor)
        if anchor_meaning and _phrase_key(return_anchor) == _phrase_key(target):
            target_meaning = anchor_meaning
    if not target_meaning:
        return None

    learner_meaning = _known_phrase_scaffold(learner_phrase)
    return _render_scaffold_redirect(
        learner_phrase=learner_phrase,
        learner_meaning=learner_meaning,
        target_phrase=target,
        target_meaning=target_meaning,
    )


def _validated_action_fields(
    action_fields: Mapping[str, object] | None,
) -> dict[str, str]:
    contract = TeachingMoveActionContract.try_from_payload_fields(dict(action_fields or {}))
    if contract is None:
        return {}
    return contract.to_payload_fields()


def _action_contract_target_keys(action_fields: Mapping[str, str]) -> set[str]:
    if not action_fields:
        return set()
    keys: set[str] = set()
    for field in ("question_target", "answer_target", "target_phrase"):
        value = _clean_phrase(action_fields.get(field, ""))
        if not value:
            continue
        key = _phrase_key(value)
        if key:
            keys.add(key)
    return keys


def normalize_redirect_read_target_for_phonics(
    block: Any,
    target_phrase: str,
) -> dict[str, str] | None:
    """Return a concrete phonics read target for a structured blend phrase."""

    if not _is_phonics_context(block):
        return None
    match = _PHONICS_TARGET_RE.search(_clean_phrase(target_phrase))
    if match:
        blend = match.group("blend").casefold()
        example = match.group("example").casefold()
        if blend and example:
            return {"blend": blend, "example": example}
    example = _phonics_example_from_target(block, target_phrase)
    if example:
        return {"blend": example[:2], "example": example}
    return None


def normalize_redirect_target_punctuation(phrase: str) -> str:
    """Fix obvious declarative targets that were accidentally marked as questions."""

    cleaned = _clean_phrase(phrase)
    if not cleaned:
        return ""
    if cleaned.endswith("?") and not _looks_like_english_question(cleaned):
        return f"{cleaned.rstrip('?').rstrip()}."
    return cleaned


def _looks_like_redirect(teacher_reply: str) -> bool:
    if _NON_REDIRECT_TRANSLATION_RE.search(teacher_reply or ""):
        return False
    return bool(_REDIRECT_MARKER_RE.search(teacher_reply or ""))


def _looks_like_module_choice(text: str) -> bool:
    return bool(_MODULE_CHOICE_RE.search(text or ""))


def _is_story_context(block: Any) -> bool:
    context = " ".join(
        str(getattr(block, attr, "") or "")
        for attr in ("block_type", "page_type", "teaching_goal", "teaching_summary")
    )
    return "story" in context.casefold()


def _select_redirect_target(
    *,
    block: Any,
    active_prompt: str,
    return_anchor: str,
    target_phrase: str,
    teacher_reply: str,
    learner_phrase: str,
) -> str:
    learner_key = _phrase_key(learner_phrase)
    for candidate in (
        active_prompt,
        return_anchor,
        target_phrase,
        _target_from_teacher_reply(teacher_reply, learner_phrase=learner_phrase),
        *_block_redirect_target_candidates(block),
    ):
        target = normalize_redirect_target_punctuation(
            _redirect_target_candidate_phrase(candidate)
        )
        if not target or not _is_reliable_redirect_target(target):
            continue
        if learner_key and _phrase_key(target) == learner_key:
            continue
        return target
    return ""


def _redirect_target_candidate_phrase(candidate: str) -> str:
    cleaned = _clean_phrase(candidate)
    if _contains_cjk(cleaned):
        extracted = _last_english_phrase(cleaned)
        if extracted:
            cleaned = extracted
    stripped = _strip_surface_target_wrapper(cleaned)
    if stripped:
        cleaned = stripped
    phonics_match = _PHONICS_TARGET_RE.search(cleaned)
    if phonics_match:
        return _clean_phrase(phonics_match.group("example"))
    match = re.match(
        r"^(?:can you answer|can you say|can you try|please answer|answer)"
        r"\s*[:：]?\s+(?P<body>.+)$",
        cleaned,
        flags=re.IGNORECASE,
    )
    if match:
        return _clean_phrase(match.group("body"))
    match = re.match(
        r"^do you know (?:the word )?(?P<body>[A-Za-z][A-Za-z'’]*(?:\s+[A-Za-z][A-Za-z'’]*){0,3})\??$",
        cleaned,
        flags=re.IGNORECASE,
    )
    if match:
        return _clean_phrase(match.group("body"))
    return cleaned


def _target_from_teacher_reply(teacher_reply: str, *, learner_phrase: str) -> str:
    patterns = (
        r"(?:这页(?:先回答这个问题|的问题是|的句子是)|这一步先听清这个问题|"
        r"先回到课本目标|回到课本目标|老师刚才问的是|老师问的是|"
        r"这一步老师问的是|我们把目标句放小|先听，再说|"
        r"把这句读出来|你来读|跟我读|跟我说一遍|我们先说这个|"
        r"这句读清楚|课文里的句子|这个问题|试着说说这个|试着说完整的句子|"
        r"试着说这个|现在试着说完整的句子|现在试着说)"
        r"[:：]?\s*[“\"']?(?P<target>[A-Za-z][A-Za-z'’]*(?:\s+[A-Za-z][A-Za-z'’]*){0,12}[?.!]?)",
    )
    for pattern in patterns:
        match = re.search(pattern, teacher_reply or "", flags=re.IGNORECASE)
        if match:
            return _clean_phrase(match.group("target"))
    learner_key = _phrase_key(learner_phrase)
    reply_key = _phrase_key(teacher_reply)
    for phrase in _KNOWN_REDIRECT_TARGETS:
        if _phrase_key(phrase) == learner_key:
            continue
        if _phrase_key(phrase) in reply_key:
            return phrase
    return ""


def _render_action_field_redirect(
    *,
    learner_phrase: str,
    block: Any,
    action_fields: Mapping[str, str],
) -> str | None:
    target_role = action_fields.get("target_role", "")
    expected_action = action_fields.get("expected_student_action", "")
    if target_role == "question" and expected_action == "answer":
        question_target = _clean_phrase(action_fields.get("question_target", ""))
        answer_frame = _clean_phrase(action_fields.get("answer_frame", ""))
        if _safe_question_answer_frame(question_target, answer_frame):
            return _render_question_answer_frame_redirect(
                learner_phrase=learner_phrase,
                question_target=question_target,
                answer_frame=answer_frame,
            )
    if target_role == "story" and expected_action == "answer":
        question_target = _clean_phrase(action_fields.get("question_target", ""))
        answer_frame = _clean_phrase(action_fields.get("answer_frame", ""))
        if question_target and answer_frame:
            return _render_story_answer_frame_redirect(
                learner_phrase=learner_phrase,
                question_target=question_target,
                answer_frame=answer_frame,
            )
    if target_role == "phonics" and expected_action == "repeat":
        answer_target = _clean_phrase(action_fields.get("answer_target", ""))
        phonics = normalize_redirect_read_target_for_phonics(block, answer_target)
        if phonics is not None:
            return _render_phonics_redirect(
                learner_phrase=learner_phrase,
                phonics=phonics,
            )
    return None


def _safe_question_answer_frame(question_target: str, answer_frame: str) -> bool:
    key = _phrase_key(question_target)
    frame_key = _phrase_key(answer_frame)
    return (key == "howtallisit" and frame_key == "itsmetrestall") or (
        key == "whatdidyoudolastweekend" and frame_key == "ilastweekend"
    )


def _render_question_answer_frame_redirect(
    *,
    learner_phrase: str,
    question_target: str,
    answer_frame: str,
) -> str:
    learner_meaning = _known_phrase_scaffold(learner_phrase)
    question = _english_sentence(question_target)
    question_meaning = _known_phrase_scaffold(question_target)
    lines = _warm_ack_lines(learner_phrase, learner_meaning)
    if question_meaning:
        lines.append(
            f"这页的问题是：{question}（{_strip_sentence_tail(question_meaning)}？）"
        )
    else:
        lines.append(f"这页的问题是：{question}")
    lines.append(f"可以用这个句型回答：{_english_sentence(answer_frame)}")
    return "\n".join(lines)


def _render_story_answer_frame_redirect(
    *,
    learner_phrase: str,
    question_target: str,
    answer_frame: str,
) -> str:
    learner = _display_phrase_for_ack(learner_phrase)
    learner_meaning = _known_phrase_scaffold(learner_phrase)
    lines = [f"你说 {learner}，我听到了。"]
    if _phrase_key(learner_phrase) in _CHARACTER_NAME_KEYS:
        lines.append(f"{learner} 是故事里的角色。")
    elif learner_meaning:
        lines.append(f"{learner} 是“{_strip_sentence_tail(learner_meaning)}”。")
    question = _english_sentence(question_target)
    question_meaning = _known_phrase_scaffold(question_target)
    if question_meaning:
        lines.append(
            f"故事里老师问：{question}（{_strip_sentence_tail(question_meaning)}？）"
        )
    else:
        lines.append(f"故事里老师问：{question}")
    lines.append(f"你可以这样回答：{_english_sentence(answer_frame)}")
    return "\n".join(lines)


def _block_redirect_target_candidates(block: Any) -> tuple[str, ...]:
    candidates: list[str] = []
    for attr in ("core_patterns", "return_anchors", "allowed_answer_scope", "focus_vocabulary"):
        values = getattr(block, attr, []) or []
        if not isinstance(values, list):
            continue
        for value in values:
            candidate = _clean_phrase(str(value))
            if candidate:
                candidates.append(candidate)
    return tuple(candidates)


def _is_reliable_redirect_target(target: str) -> bool:
    if not target or "..." in target or "___" in target:
        return False
    key = _phrase_key(target)
    if key in {"whereisthe", "whereis", "whatisthe", "whatis", "howis", "whenis"}:
        return False
    if key.endswith("withme"):
        return False
    if key in {"canyoutry", "canyousay", "repeatafterme", "readafterme"}:
        return False
    if target.endswith("?") and not _known_phrase_scaffold(target):
        return False
    return bool(
        _known_phrase_scaffold(target)
        or target.endswith("?")
        or _PHONICS_TARGET_RE.search(target)
    )


def _phonics_example_from_target(block: Any, target_phrase: str) -> str:
    target_tokens = {
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z'’]*", target_phrase or "")
    }
    if not target_tokens:
        return ""
    block_terms: set[str] = set()
    for attr in ("focus_vocabulary", "allowed_answer_scope", "core_patterns"):
        for value in getattr(block, attr, []) or []:
            block_terms.update(
                token.casefold()
                for token in re.findall(r"[A-Za-z][A-Za-z'’]*", str(value))
            )
    for token in target_tokens:
        clean = token.strip("'’").casefold()
        if len(clean) <= 2 or clean not in block_terms:
            continue
        if clean.startswith(("cl", "pl")):
            return clean
    return ""


def _can_render_scaffold_target(target_phrase: str) -> bool:
    key = _phrase_key(target_phrase)
    if _clean_phrase(target_phrase).endswith("?"):
        return True
    return bool(_known_phrase_scaffold(target_phrase)) or key in {
        "iamhungry",
        "imhungry",
        "thatsthetallestdinosaur",
    }


def _render_scaffold_redirect(
    *,
    learner_phrase: str,
    learner_meaning: str,
    target_phrase: str,
    target_meaning: str,
) -> str:
    target = _english_sentence(target_phrase)
    lines = _warm_ack_lines(learner_phrase, learner_meaning)
    if target.endswith("?"):
        lines.append(
            f"这页的问题是：{target}（{_strip_sentence_tail(target_meaning)}？）"
        )
    elif _looks_like_short_vocab_target(target_phrase):
        target_word = _display_phrase_for_meaning(target_phrase)
        noun = "地点词" if _looks_like_place_target(target_phrase) else "这个词"
        lines.append(
            f"这页我们先看{noun}：{target_word}（{_strip_sentence_tail(target_meaning)}）。"
        )
    else:
        lines.append(f"这页的句子是：{target}（{_strip_sentence_tail(target_meaning)}。）")
    lines.append(_next_action_for_target(target_phrase))
    return "\n".join(lines)


def _render_phonics_redirect(
    *,
    learner_phrase: str,
    phonics: dict[str, str],
) -> str:
    learner_meaning = _known_phrase_scaffold(learner_phrase)
    blend = phonics["blend"]
    example = _display_phrase_for_ack(phonics["example"])
    lines = _warm_ack_lines(learner_phrase, learner_meaning)
    lines.extend(
        [
            f"这一步练 {blend} 的发音，{example} 里的 {blend} 要连起来读。",
            f"跟我读：{_english_sentence(phonics['example'])}",
        ]
    )
    return "\n".join(lines)


def _warm_ack_lines(learner_phrase: str, learner_meaning: str = "") -> list[str]:
    learner = _display_phrase_for_ack(learner_phrase)
    if learner_meaning:
        if _separate_ack_meaning(learner_phrase):
            return [
                f"我听到你说 {_english_sentence(learner_phrase)}",
                f"意思是“{_strip_sentence_tail(learner_meaning)}”。",
            ]
        return [f"我听到你说 {learner}，是“{_strip_sentence_tail(learner_meaning)}”。"]
    return [f"我听到你说 {_english_sentence(learner_phrase)}"]


def _separate_ack_meaning(phrase: str) -> bool:
    return bool(
        re.search(
            r"\b(?:I'd like|What would|you can|please|turn left|go straight)\b",
            _clean_phrase(phrase),
            flags=re.IGNORECASE,
        )
    )


def _next_action_for_target(target_phrase: str) -> str:
    key = _phrase_key(target_phrase)
    if key in {
        "whatsyourfavouritefood",
        "whatisyourfavouritefood",
        "whatsyourfavoritefood",
        "whatisyourfavoritefood",
    }:
        return "你先说一个食物。"
    if key == "whatwouldyouliketodrink":
        return "你先回答想喝什么。"
    if key == "whatwouldyouliketoeat":
        return "你先回答想吃什么。"
    if key == "whendoyougetup":
        return "你先回答一个时间。"
    if key == "whereisthemuseumshop":
        return "你先读这个问题。"
    if _clean_phrase(target_phrase).endswith("?"):
        return "你先回答这个问题。"
    return "你先读一遍。"


def _learner_phrase(text: str) -> str:
    cleaned = _clean_phrase(text)
    if not cleaned:
        return ""
    if _contains_cjk(cleaned):
        match = re.search(
            r"[A-Za-z][A-Za-z'’]*(?:\s+[A-Za-z][A-Za-z'’]*){0,8}",
            cleaned,
        )
        return _clean_phrase(match.group(0)) if match else ""
    return cleaned


def _known_phrase_scaffold(phrase: str) -> str:
    compact = _clean_phrase(phrase)
    if not compact:
        return ""
    dynamic = _dynamic_phrase_scaffold(compact)
    if dynamic:
        return dynamic
    return _PHRASE_SCAFFOLD_BY_KEY.get(_phrase_key(compact), "")


def _last_english_phrase(text: str) -> str:
    matches = list(
        re.finditer(
            r"[A-Za-z][A-Za-z'’]*(?:\s+[A-Za-z][A-Za-z'’]*){0,12}[?.!]?",
            text or "",
        )
    )
    if not matches:
        return ""
    return _clean_phrase(matches[-1].group(0))


def _dynamic_phrase_scaffold(phrase: str) -> str:
    match = re.fullmatch(
        r"i(?:'|’)m\s+(?P<number>\d+(?:\.\d+)?)\s+metres?\.?",
        phrase,
        flags=re.IGNORECASE,
    )
    if match:
        return f"我身高 {match.group('number')} 米。"
    return ""


def _meaning_from_reply(teacher_reply: str, phrase: str) -> str:
    compact = _clean_phrase(phrase)
    if not compact:
        return ""
    escaped = re.escape(compact).replace(r"\ ", r"\s+")
    patterns = (
        rf"{escaped}\s*(?:是|意思是|的意思是)[“\"]([^”\"。！？\n]{{1,18}})[”\"]",
        rf"{escaped}[^。！？\n]{{0,18}}意思是[“\"]([^”\"。！？\n]{{1,18}})[”\"]",
        rf"{escaped}[，,、]\s*([^。！？\n]{{1,10}}?)(?:。|，|,)",
    )
    for pattern in patterns:
        match = re.search(pattern, teacher_reply or "", flags=re.IGNORECASE)
        if match:
            return _strip_sentence_tail(match.group(1).strip())
    return ""


def _is_phonics_context(block: Any) -> bool:
    fields = [
        getattr(block, "block_type", ""),
        getattr(block, "page_type", ""),
        getattr(block, "teaching_goal", ""),
        getattr(block, "teaching_summary", ""),
        " ".join(str(item) for item in getattr(block, "core_patterns", []) or []),
        " ".join(str(item) for item in getattr(block, "return_anchors", []) or []),
    ]
    context = " ".join(fields).casefold()
    return bool(
        re.search(
            r"\bphonics\b|consonant\s+blend|\bblend\b|字母组合|拼读|发音",
            context,
        )
    )


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text or ""))


def _clean_phrase(phrase: str) -> str:
    cleaned = " ".join(str(phrase or "").strip().split())
    cleaned = cleaned.strip("“”\"'`，,、；;:：")
    cleaned = re.sub(r"([A-Za-z0-9])['’`]+(?=[.?!。！？]?$)", r"\1", cleaned)
    cleaned = re.sub(r"([A-Za-z0-9])['’`]+\s+([.?!。！？])$", r"\1\2", cleaned)
    return cleaned.strip("“”\"'`，,、；;:：")


def _english_sentence(phrase: str) -> str:
    cleaned = _clean_phrase(phrase)
    if not cleaned:
        return ""
    if cleaned.endswith("..") and not cleaned.endswith("..."):
        cleaned = cleaned.rstrip(".") + "."
    if cleaned.endswith(("?", "!", ".")):
        return cleaned
    return f"{cleaned}."


def _display_phrase_for_ack(phrase: str) -> str:
    cleaned = _clean_phrase(phrase)
    if cleaned.endswith(("?", "!")):
        return cleaned
    return cleaned.rstrip(".")


def _display_phrase_for_meaning(phrase: str) -> str:
    return _display_phrase_for_ack(phrase).strip("：:，, ")


def _looks_like_short_vocab_target(phrase: str) -> bool:
    cleaned = _clean_phrase(phrase)
    if not cleaned or cleaned.endswith(("?", ".", "!")):
        return False
    if not re.fullmatch(r"[A-Za-z][A-Za-z'’]*(?:\s+[A-Za-z][A-Za-z'’]*){0,3}", cleaned):
        return False
    return bool(_known_phrase_scaffold(cleaned))


def _looks_like_place_target(phrase: str) -> bool:
    key = _phrase_key(phrase)
    return any(marker in key for marker in ("museum", "bookstore", "library", "shop"))


def _looks_like_english_question(phrase: str) -> bool:
    cleaned = _clean_phrase(phrase).rstrip("?").strip()
    return bool(
        re.match(
            r"^(?:what|where|when|who|why|how|which|is|are|am|do|does|did|"
            r"can|could|would|will|should|may|have|has)\b",
            cleaned,
            flags=re.IGNORECASE,
        )
    )


def _strip_sentence_tail(text: str) -> str:
    return str(text or "").strip().strip("。！？!?；;，,、 ")


def _phrase_key(phrase: str) -> str:
    compact = _clean_phrase(phrase).casefold().replace("’", "'")
    compact = compact.replace("favourite", "favourite")
    return re.sub(r"[^a-z0-9]+", "", compact)


def _strip_surface_target_wrapper(phrase: str) -> str:
    cleaned = _clean_phrase(phrase)
    match = re.match(
        r"^\s*(?:try to say|try saying|say after me|repeat after me|read after me|"
        r"please repeat|please say|can you follow me and say|can you say|"
        r"can you try|can you repeat)\s*[:：]\s*[“\"']?(?P<body>.+?)[”\"']?\s*$",
        cleaned,
        flags=re.IGNORECASE,
    )
    if match:
        return _clean_phrase(match.group("body"))
    return ""
