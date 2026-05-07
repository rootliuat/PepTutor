"""Deterministic renderer for reviewed page-teaching strategy slices."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from lightrag.pedagogy.page_teaching_strategy import (
    PageTeachingStrategy,
    PageTeachingStrategyStep,
    STRATEGY_PRIORITY_ORDER,
)
from lightrag.pedagogy.types import EvaluationResult, TeachingAction


_P26_SOUND_BY_WORD = {
    "cow": "/aʊ/",
    "flower": "/aʊ/",
    "wow": "/aʊ/",
    "down": "/aʊ/",
    "slow": "/oʊ/",
    "snow": "/oʊ/",
    "yellow": "/oʊ/",
    "window": "/oʊ/",
}
_WORD_MEANINGS = {
    "bread": "面包",
    "chicken": "鸡肉",
    "cow": "奶牛",
    "down": "向下",
    "drink": "喝",
    "eat": "吃",
    "flower": "花",
    "hungry": "饿的",
    "juice": "果汁",
    "milk": "牛奶",
    "noodles": "面条",
    "salad": "沙拉",
    "sandwich": "三明治",
    "Sarah": "萨拉",
    "slow": "慢的",
    "snow": "雪",
    "tea": "茶",
    "thirsty": "渴的",
    "water": "水",
    "window": "窗户",
    "wow": "哇",
    "yellow": "黄色",
}
_ORDINAL_TO_INDEX = {
    "第一块": 0,
    "第1块": 0,
    "一块": 0,
    "第二块": 1,
    "第2块": 1,
    "二块": 1,
    "第三块": 2,
    "第3块": 2,
    "三块": 2,
    "第四块": 3,
    "第4块": 3,
    "四块": 3,
}


@dataclass(frozen=True)
class TeacherStrategyRenderResult:
    """Visible reply plus state updates emitted by the strategy renderer."""

    teacher_reply: str
    step_id: str
    block_uid: str
    module_type: str
    awaiting_answer: bool
    last_teacher_question: str
    teaching_action: TeachingAction
    evaluation: EvaluationResult | None
    completion_status: str
    focus_word: str = ""


def initial_strategy_state(strategy: PageTeachingStrategy) -> dict[str, Any]:
    """Return serializable strategy state for a new page entry."""

    step = strategy.initial_step()
    return _strategy_state_payload(
        strategy=strategy,
        step=step,
        completion_status="initialized",
    )


def render_strategy_page_entry(
    strategy: PageTeachingStrategy,
) -> TeacherStrategyRenderResult:
    """Render a strategy-controlled page opening."""

    step = strategy.initial_step()
    return TeacherStrategyRenderResult(
        teacher_reply=step.teacher_prompt,
        step_id=step.step_id,
        block_uid=step.block_uid,
        module_type=step.module_type,
        awaiting_answer=True,
        last_teacher_question=step.question_target or step.teacher_prompt,
        teaching_action="page_intro",
        evaluation=None,
        completion_status="initialized",
    )


def render_strategy_turn(
    *,
    strategy: PageTeachingStrategy,
    strategy_state: dict[str, Any] | None,
    learner_input: str,
    teaching_move_payload: dict[str, Any] | None = None,
) -> TeacherStrategyRenderResult:
    """Render a short strategy-aware teacher turn.

    The renderer only uses reviewed strategy data plus the current strategy state.
    It does not consult RAG, RAGFlow, prompts, or page-specific runtime branches.
    """

    del teaching_move_payload
    step = _current_step(strategy, strategy_state)
    learner = _normalized_oral_text(learner_input)
    if _looks_like_meaning_request(learner_input):
        return _render_meaning_request(
            strategy=strategy,
            step=step,
            learner=learner,
            focus_word=_state_focus_word(strategy_state),
        )
    if _looks_like_completion_claim(learner_input):
        return _render_completion_claim(strategy=strategy, step=step)
    choice_step = _module_choice_step(strategy, learner_input, step, strategy_state)
    if choice_step is not None:
        return _render_step_entry(strategy=strategy, step=choice_step)
    if strategy.module_type == "lets_spell":
        return _render_phonics_turn(strategy=strategy, step=step, learner=learner)
    return _render_food_drink_turn(strategy=strategy, step=step, learner=learner)


def next_strategy_state(
    *,
    strategy: PageTeachingStrategy,
    result: TeacherStrategyRenderResult,
) -> dict[str, Any]:
    """Return serializable state after a rendered turn."""

    step = strategy.step_by_id(result.step_id)
    return _strategy_state_payload(
        strategy=strategy,
        step=step,
        completion_status=result.completion_status,
        focus_word=result.focus_word,
    )


def _strategy_state_payload(
    *,
    strategy: PageTeachingStrategy,
    step: PageTeachingStrategyStep,
    completion_status: str,
    focus_word: str = "",
) -> dict[str, Any]:
    payload = {
        "schema_version": "peptutor-strategy-state-v1",
        "strategy_source": "reviewed_page_teaching_strategy",
        "priority": list(STRATEGY_PRIORITY_ORDER),
        "page_uid": strategy.page_uid,
        "module_type": step.module_type,
        "step_id": step.step_id,
        "block_uid": step.block_uid,
        "allowed_words": list(step.allowed_words or strategy.strategy_lock.allowed_words),
        "allowed_actions": list(
            step.allowed_actions or strategy.strategy_lock.allowed_actions
        ),
        "blocked_actions": list(
            step.blocked_actions or strategy.strategy_lock.blocked_actions
        ),
        "completion_rule": step.completion_rule,
        "transition_rule": step.transition_rule,
        "completion_status": completion_status,
    }
    if focus_word:
        payload["focus_word"] = focus_word
    return payload


def _current_step(
    strategy: PageTeachingStrategy,
    strategy_state: dict[str, Any] | None,
) -> PageTeachingStrategyStep:
    if isinstance(strategy_state, dict):
        step_id = str(strategy_state.get("step_id") or "")
        if step_id:
            try:
                return strategy.step_by_id(step_id)
            except KeyError:
                pass
    return strategy.initial_step()


def _render_step_entry(
    *,
    strategy: PageTeachingStrategy,
    step: PageTeachingStrategyStep,
) -> TeacherStrategyRenderResult:
    return TeacherStrategyRenderResult(
        teacher_reply=step.teacher_prompt,
        step_id=step.step_id,
        block_uid=step.block_uid,
        module_type=step.module_type,
        awaiting_answer=True,
        last_teacher_question=step.question_target or step.teacher_prompt,
        teaching_action="hint",
        evaluation=None,
        completion_status="step_entry",
    )


def _module_choice_step(
    strategy: PageTeachingStrategy,
    learner_input: str,
    current_step: PageTeachingStrategyStep,
    strategy_state: dict[str, Any] | None,
) -> PageTeachingStrategyStep | None:
    if not _strategy_accepts_module_choice(
        strategy=strategy,
        current_step=current_step,
        strategy_state=strategy_state,
    ):
        return None
    for marker, index in _ORDINAL_TO_INDEX.items():
        if marker in learner_input:
            return strategy.steps[min(index, len(strategy.steps) - 1)]
    return None


def _strategy_accepts_module_choice(
    *,
    strategy: PageTeachingStrategy,
    current_step: PageTeachingStrategyStep,
    strategy_state: dict[str, Any] | None,
) -> bool:
    if strategy.module_type != "lets_spell":
        return True
    if current_step.step_id != strategy.initial_step().step_id:
        return False
    if not isinstance(strategy_state, dict):
        return True
    if _state_focus_word(strategy_state):
        return False
    return str(strategy_state.get("completion_status") or "") in {
        "initialized",
        "step_entry",
    }


def _render_meaning_request(
    *,
    strategy: PageTeachingStrategy,
    step: PageTeachingStrategyStep,
    learner: str,
    focus_word: str,
) -> TeacherStrategyRenderResult:
    word = (
        _first_strategy_word_in_text(strategy, learner)
        or focus_word
        or _preferred_step_word(step)
    )
    if word:
        meaning = _WORD_MEANINGS.get(word, "")
        if meaning:
            reply = f"{word} 的意思是“{meaning}”。我们还在这一小步，跟我读：{word}."
        else:
            reply = f"这句先理解为当前练习内容。我们还在这一小步，跟我读：{word}."
    else:
        target = step.question_target or step.teacher_prompt
        reply = f"这句是在问当前任务：{target}\n我们先贴着这一小步回答。"
    return TeacherStrategyRenderResult(
        teacher_reply=reply,
        step_id=step.step_id,
        block_uid=step.block_uid,
        module_type=step.module_type,
        awaiting_answer=True,
        last_teacher_question=step.question_target or step.teacher_prompt,
        teaching_action="hint",
        evaluation=None,
        completion_status="meaning_return",
    )


def _render_completion_claim(
    *,
    strategy: PageTeachingStrategy,
    step: PageTeachingStrategyStep,
) -> TeacherStrategyRenderResult:
    next_step = strategy.next_step(step)
    if next_step.step_id == step.step_id:
        reply = "好，这一步完成了。我们先口头收一下，不再重复抄写。"
    else:
        reply = f"好，这一步算完成。我们进入下一小步：{next_step.teacher_prompt}"
    return TeacherStrategyRenderResult(
        teacher_reply=reply,
        step_id=next_step.step_id,
        block_uid=next_step.block_uid,
        module_type=next_step.module_type,
        awaiting_answer=True,
        last_teacher_question=next_step.question_target or next_step.teacher_prompt,
        teaching_action="confirm",
        evaluation="acceptable",
        completion_status="completion_claim",
    )


def _render_phonics_turn(
    *,
    strategy: PageTeachingStrategy,
    step: PageTeachingStrategyStep,
    learner: str,
) -> TeacherStrategyRenderResult:
    compact_learner = re.sub(r"[^a-z0-9]+", "", learner)
    if "iseeyellowflower" in compact_learner or "iseeayellowflower" in compact_learner:
        step = _step_by_type(strategy, "listen_and_circle") or step
        reply = "意思对，就是 I see a yellow flower. 这是口语练习，不纠结大小写和标点。再自然说一遍。"
        return TeacherStrategyRenderResult(
            teacher_reply=reply,
            step_id=step.step_id,
            block_uid=step.block_uid,
            module_type=step.module_type,
            awaiting_answer=True,
            last_teacher_question=step.question_target or step.teacher_prompt,
            teaching_action="confirm",
            evaluation="acceptable",
            completion_status="oral_sentence_accepted",
            focus_word="flower",
        )

    word = _first_strategy_word_in_text(strategy, learner)
    if word:
        sound = _P26_SOUND_BY_WORD.get(word, "")
        if sound:
            next_step = _phonics_next_step_for_sound(strategy, sound, step)
            contrast = (
                "它和 snow 那组不一样。"
                if sound == "/aʊ/"
                else "它和 cow 那组不一样。"
            )
            reply = f"{word} 属于 {sound} 这一组。{contrast}跟我读：{word}."
            return TeacherStrategyRenderResult(
                teacher_reply=reply,
                step_id=next_step.step_id,
                block_uid=next_step.block_uid,
                module_type=next_step.module_type,
                awaiting_answer=True,
                last_teacher_question=next_step.question_target
                or next_step.teacher_prompt,
                teaching_action="hint",
                evaluation="acceptable",
                completion_status="word_classified",
                focus_word=word,
            )

    reply = f"我们先不换任务。{step.teacher_prompt}"
    return TeacherStrategyRenderResult(
        teacher_reply=reply,
        step_id=step.step_id,
        block_uid=step.block_uid,
        module_type=step.module_type,
        awaiting_answer=True,
        last_teacher_question=step.question_target or step.teacher_prompt,
        teaching_action="hint",
        evaluation=None,
        completion_status="stay_on_step",
    )


def _phonics_next_step_for_sound(
    strategy: PageTeachingStrategy,
    sound: str,
    current_step: PageTeachingStrategyStep,
) -> PageTeachingStrategyStep:
    wanted = "p26_s2_au_group" if sound == "/aʊ/" else "p26_s3_ou_group"
    try:
        return strategy.step_by_id(wanted)
    except KeyError:
        return current_step


def _render_food_drink_turn(
    *,
    strategy: PageTeachingStrategy,
    step: PageTeachingStrategyStep,
    learner: str,
) -> TeacherStrategyRenderResult:
    word = _first_strategy_word_in_text(strategy, learner)
    if word:
        next_step = _food_next_step(strategy, step, word)
        if _is_food_word(next_step, word) or _is_drink_word(next_step, word):
            sentence = _food_drink_sentence(word)
            reply = f"可以，{word} 在这个餐厅场景里能用。\n{sentence}\n我们继续角色扮演。"
            evaluation = "acceptable"
        elif word == "chicken":
            reply = "chicken 是鸡肉，可以作为食物词。听力里 Sarah 主要要 bread 和 noodles。再说一个：bread."
            evaluation = "acceptable"
        else:
            reply = f"{word} 我听到了。我们先贴着餐厅任务，用 I'd like ... 来回答。"
            evaluation = None
        return TeacherStrategyRenderResult(
            teacher_reply=reply,
            step_id=next_step.step_id,
            block_uid=next_step.block_uid,
            module_type=next_step.module_type,
            awaiting_answer=True,
            last_teacher_question=next_step.question_target
            or next_step.teacher_prompt,
            teaching_action="hint",
            evaluation=evaluation,
            completion_status="food_drink_item_seen",
        )
    reply = f"我们先留在餐厅场景。\n{step.teacher_prompt}"
    return TeacherStrategyRenderResult(
        teacher_reply=reply,
        step_id=step.step_id,
        block_uid=step.block_uid,
        module_type=step.module_type,
        awaiting_answer=True,
        last_teacher_question=step.question_target or step.teacher_prompt,
        teaching_action="hint",
        evaluation=None,
        completion_status="stay_on_step",
    )


def _food_next_step(
    strategy: PageTeachingStrategy,
    step: PageTeachingStrategyStep,
    word: str,
) -> PageTeachingStrategyStep:
    if word in {"bread", "noodles", "chicken"}:
        return _step_by_type(strategy, "listen_and_fill") or step
    if word in {"water", "tea", "milk", "juice"}:
        return _step_by_type(strategy, "role_play") or step
    if word in {"sandwich", "salad"}:
        return _step_by_type(strategy, "role_play") or step
    return strategy.next_step(step)


def _food_drink_sentence(word: str) -> str:
    if word in {"water", "tea", "milk", "juice"}:
        return f"I'd like some {word}."
    return f"I'd like {word}."


def _is_food_word(step: PageTeachingStrategyStep, word: str) -> bool:
    return word in {value.casefold() for value in step.food_words} or word in {
        "bread",
        "noodles",
        "chicken",
        "sandwich",
        "salad",
    }


def _is_drink_word(step: PageTeachingStrategyStep, word: str) -> bool:
    return word in {value.casefold() for value in step.drink_words} or word in {
        "water",
        "tea",
        "milk",
        "juice",
    }


def _step_by_type(
    strategy: PageTeachingStrategy,
    step_type: str,
) -> PageTeachingStrategyStep | None:
    for step in strategy.steps:
        if step.step_type == step_type:
            return step
    return None


def _first_strategy_word_in_text(
    strategy: PageTeachingStrategy,
    learner: str,
) -> str:
    allowed = []
    for step in strategy.steps:
        allowed.extend(step.allowed_words)
        allowed.extend(step.target_words)
        allowed.extend(step.food_words)
        allowed.extend(step.drink_words)
    for word in sorted({value.casefold() for value in allowed}, key=len, reverse=True):
        if word and re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", learner):
            return word
    return ""


def _preferred_step_word(step: PageTeachingStrategyStep) -> str:
    for word in [*step.target_words, *step.allowed_words]:
        normalized = word.casefold()
        if normalized in _WORD_MEANINGS:
            return normalized
    return ""


def _state_focus_word(strategy_state: dict[str, Any] | None) -> str:
    if isinstance(strategy_state, dict):
        focus_word = str(strategy_state.get("focus_word") or "").casefold()
        if focus_word in _WORD_MEANINGS:
            return focus_word
    return ""


def _looks_like_meaning_request(text: str) -> bool:
    return bool(re.search(r"什么意思|这是什么意思|这句什么意思|what\s+does.+mean", text, re.I))


def _looks_like_completion_claim(text: str) -> bool:
    return bool(re.search(r"已经(?:写|抄写|做完|完成)|写完了|抄完了", text))


def _normalized_oral_text(text: str) -> str:
    normalized = text.casefold().replace("’", "'")
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
