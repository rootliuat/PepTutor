"""Recognize page-module navigation without RAG or LLM routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from lightrag.orchestrator.page_overview_skill import (
    PageOverview,
    PageOverviewModule,
)


ModuleChoiceIntent = Literal["choose", "next", "previous", "switch", "auto"]


@dataclass(frozen=True)
class ModuleChoice:
    """A resolved learner request to move within the current page overview."""

    module: PageOverviewModule
    intent: ModuleChoiceIntent
    source: str = "module_choice_skill"


class ModuleChoiceSkill:
    """Map learner text like "换一个" or "Let's check" to a page module."""

    def choose(
        self,
        *,
        learner_input: str,
        overview: PageOverview,
        current_block_uid: str | None,
        allow_bare_index: bool = False,
    ) -> ModuleChoice | None:
        normalized = _choice_key(learner_input)
        if not normalized or _looks_like_definition_question(normalized):
            return None

        if allow_bare_index and _has_teacher_choice_intent(normalized):
            return ModuleChoice(module=overview.modules[0], intent="auto")

        module = self._match_explicit_module(
            learner_input=learner_input,
            overview=overview,
            allow_bare_index=allow_bare_index,
        )
        if module is not None:
            return ModuleChoice(module=module, intent="choose")

        intent = _relative_intent(normalized)
        if intent is None:
            return None

        current_index = _current_module_index(
            overview=overview,
            current_block_uid=current_block_uid,
        )
        if current_index is None:
            return None

        if intent == "previous":
            target_index = (current_index - 1) % len(overview.modules)
        else:
            target_index = (current_index + 1) % len(overview.modules)
        return ModuleChoice(module=overview.modules[target_index], intent=intent)

    def has_selection_intent(
        self,
        learner_input: str,
        *,
        allow_bare_index: bool = False,
    ) -> bool:
        normalized = _choice_key(learner_input)
        if not normalized or _looks_like_definition_question(normalized):
            return False
        if allow_bare_index and _has_teacher_choice_intent(normalized):
            return True
        has_navigation_intent = _has_navigation_intent(normalized)
        if has_navigation_intent or _relative_intent(normalized) is not None:
            return True
        return (
            _choice_index(
                normalized,
                allow_bare_index=allow_bare_index,
                has_navigation_intent=has_navigation_intent,
            )
            is not None
        )

    def has_module_navigation_request(
        self,
        learner_input: str,
        *,
        allow_bare_index: bool = False,
    ) -> bool:
        """Return true only for explicit within-page module navigation."""
        normalized = _choice_key(learner_input)
        if not normalized or _looks_like_definition_question(normalized):
            return False
        if _relative_intent(normalized) is not None:
            return True
        return (
            _choice_index(
                normalized,
                allow_bare_index=allow_bare_index,
                has_navigation_intent=_has_navigation_intent(normalized),
            )
            is not None
        )

    def _match_explicit_module(
        self,
        *,
        learner_input: str,
        overview: PageOverview,
        allow_bare_index: bool,
    ) -> PageOverviewModule | None:
        normalized = _choice_key(learner_input)
        has_navigation_intent = _has_navigation_intent(normalized)

        index = _choice_index(
            normalized,
            allow_bare_index=allow_bare_index,
            has_navigation_intent=has_navigation_intent,
        )
        if index is not None and 0 <= index < len(overview.modules):
            return overview.modules[index]

        for module in overview.modules:
            for alias in module.aliases:
                alias_key = _choice_key(alias)
                if not alias_key:
                    continue
                if normalized == alias_key:
                    return module
                if alias_key in normalized and (
                    allow_bare_index
                    or has_navigation_intent
                    or len(normalized) <= len(alias_key) + 4
                ):
                    return module
        return None


def _current_module_index(
    *,
    overview: PageOverview,
    current_block_uid: str | None,
) -> int | None:
    if not current_block_uid:
        return None
    for index, module in enumerate(overview.modules):
        if current_block_uid in module.block_uids:
            return index
    return None


def _choice_index(
    normalized: str,
    *,
    allow_bare_index: bool,
    has_navigation_intent: bool,
) -> int | None:
    bare_indexes = {
        "1": 0,
        "one": 0,
        "first": 0,
        "2": 1,
        "two": 1,
        "second": 1,
        "3": 2,
        "three": 2,
        "third": 2,
        "4": 3,
        "four": 3,
        "fourth": 3,
        "5": 4,
        "five": 4,
        "fifth": 4,
        "6": 5,
        "six": 5,
        "sixth": 5,
    }
    if allow_bare_index and normalized in bare_indexes:
        return bare_indexes[normalized]

    digit_match = re.search(
        r"(?:第([1-6])个|第?([1-6])(?:块|部分|模块|part|module))",
        normalized,
    )
    if digit_match and (has_navigation_intent or "块" in normalized or "模块" in normalized):
        return int(digit_match.group(1) or digit_match.group(2)) - 1

    chinese_indexes = {
        "一": 0,
        "二": 1,
        "两": 1,
        "三": 2,
        "四": 3,
        "五": 4,
        "六": 5,
    }
    for char, index in chinese_indexes.items():
        if re.search(rf"(?:第{char}个|第?{char}(?:块|部分|模块))", normalized) and (
            has_navigation_intent or "块" in normalized or "模块" in normalized
        ):
            return index
    return None


def _relative_intent(normalized: str) -> ModuleChoiceIntent | None:
    if any(token in normalized for token in ("上一个", "上一块", "上个模块", "前一个")):
        return "previous"
    if normalized in {"previous", "prev", "previousone", "previousmodule"}:
        return "previous"

    if any(token in normalized for token in ("换一个", "换一块", "换个模块", "另一个", "别的")):
        return "switch"
    if normalized in {"another", "other", "otherone", "switch", "switchmodule"}:
        return "switch"

    if any(token in normalized for token in ("下一个", "下一块", "下个模块", "下个部分")):
        return "next"
    if normalized in {"next", "nextone", "nextmodule", "nextpart"}:
        return "next"
    return None


def _has_navigation_intent(normalized: str) -> bool:
    return any(
        token in normalized
        for token in (
            "想学",
            "学",
            "选",
            "做",
            "讲",
            "看",
            "去",
            "回到",
            "切到",
            "换",
            "模块",
            "部分",
            "块",
            "module",
        )
    )


def _has_teacher_choice_intent(normalized: str) -> bool:
    return any(
        token in normalized
        for token in (
            "随便",
            "你安排",
            "老师安排",
            "都可以",
            "都行",
            "听你的",
            "哪个都行",
            "whatever",
            "anything",
            "anyone",
        )
    )


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


def _choice_key(text: str) -> str:
    return re.sub(r"[\s'’`\"“”.,!?！？。；;:：、，-]+", "", text.casefold())
