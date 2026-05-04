"""Build a data-driven page overview before drilling a textbook page."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_MODULE_LABEL_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Let's wrap it up", (r"\blet'?s\s+wrap\s+(?:it\s+)?up\b",)),
    ("Let's check", (r"\blet'?s\s+check\b",)),
    ("Read and write", (r"\bread\s+and\s+write\b",)),
    ("Story time", (r"\bstory\s+time\b",)),
    ("Let's spell", (r"\blet'?s\s+spell\b",)),
    ("Let's learn", (r"\blet'?s\s+learn\b",)),
    ("Let's talk", (r"\blet'?s\s+talk\b",)),
    ("Let's try", (r"\blet'?s\s+try\b",)),
    ("Ask and answer", (r"\bask\s+and\s+answer\b",)),
    ("Let's play", (r"\blet'?s\s+play\b",)),
    ("Start to read", (r"\bstart\s+to\s+read\b",)),
)

_CHINESE_ORDINALS = {
    "一": 0,
    "二": 1,
    "两": 1,
    "三": 2,
    "四": 3,
    "五": 4,
}

_FALLBACK_MODULE_LABELS = ("第一块", "第二块", "第三块", "第四块", "第五块", "第六块")
_BROAD_CORE_BLOCK_TYPES = {"dialogue_core"}
_ALIAS_DETAIL_FIELDS = ("branchable_topics", "focus_vocabulary", "core_patterns")
_ALIAS_WORD_STOPWORDS = {
    "and",
    "are",
    "for",
    "like",
    "some",
    "the",
    "what",
    "would",
    "you",
}


@dataclass(frozen=True)
class PageOverviewModule:
    """One visible textbook module on the current page."""

    label: str
    block_uids: tuple[str, ...]
    summary: str
    aliases: tuple[str, ...]

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "block_uids": list(self.block_uids),
            "summary": self.summary,
            "aliases": list(self.aliases),
        }


@dataclass(frozen=True)
class PageOverview:
    """Structured opening plan for a multi-module textbook page."""

    page_uid: str
    modules: tuple[PageOverviewModule, ...]
    teacher_response: str
    choice_prompt: str
    source: str = "page_overview_skill"

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "page_uid": self.page_uid,
            "choice_prompt": self.choice_prompt,
            "modules": [module.to_prompt_payload() for module in self.modules],
        }


@dataclass
class _ModuleDraft:
    label: str
    blocks: list[Any]
    has_explicit_label: bool


class PageOverviewSkill:
    """Create a short page overview from page/block records, not page IDs."""

    def build(self, *, page: Any, blocks: list[Any]) -> PageOverview | None:
        modules = self._build_modules(blocks)
        if len(modules) < 2:
            return None

        labels = [module.label for module in modules]
        choice_prompt = f"你想先学哪一块？可以说 {self._format_choices(labels)}。"
        module_lines = self._format_module_choice_overview(modules)
        topic_prefix = self._compact_page_topic_prefix(
            str(getattr(page, "page_intro_cn", "") or "")
        )
        teacher_response = f"这一页{topic_prefix}先选入口：{module_lines}。{choice_prompt}"
        return PageOverview(
            page_uid=str(getattr(page, "page_uid", "")),
            modules=tuple(modules),
            teacher_response=teacher_response,
            choice_prompt=choice_prompt,
        )

    def match_choice(
        self,
        learner_input: str,
        overview: PageOverview,
    ) -> PageOverviewModule | None:
        normalized = _choice_key(learner_input)
        if not normalized:
            return None

        index = self._choice_index(normalized)
        if index is not None and 0 <= index < len(overview.modules):
            return overview.modules[index]

        for module in overview.modules:
            for alias in module.aliases:
                alias_key = _choice_key(alias)
                if not alias_key:
                    continue
                if normalized == alias_key or alias_key in normalized:
                    return module
                if normalized in alias_key and len(normalized) >= 4:
                    return module
        return None

    def is_choice_prompt(self, prompt: str | None, overview: PageOverview) -> bool:
        return bool(prompt) and _choice_key(prompt or "") == _choice_key(
            overview.choice_prompt
        )

    def _build_modules(self, blocks: list[Any]) -> list[PageOverviewModule]:
        drafts: list[_ModuleDraft] = []
        current: _ModuleDraft | None = None

        for block in blocks:
            detected_label = self._detect_module_label(block)
            if detected_label is None and current is None:
                continue
            label = detected_label or current.label

            if current is None or current.label != label:
                current = _ModuleDraft(
                    label=label,
                    blocks=[],
                    has_explicit_label=detected_label is not None,
                )
                drafts.append(current)
            elif detected_label is not None:
                current.has_explicit_label = True
            current.blocks.append(block)

        explicit_drafts = [
            draft for draft in drafts if draft.has_explicit_label and draft.blocks
        ]
        if len(explicit_drafts) < 2:
            return self._build_block_modules(blocks)

        return [
            PageOverviewModule(
                label=draft.label,
                block_uids=tuple(
                    str(getattr(block, "block_uid", "")) for block in draft.blocks
                ),
                summary=self._summarize_module(draft),
                aliases=self._aliases_for_label(draft.label),
            )
            for draft in explicit_drafts
        ]

    def _build_block_modules(self, blocks: list[Any]) -> list[PageOverviewModule]:
        visible_blocks = [block for block in blocks if _has_visible_source(block)]
        if len(visible_blocks) < 2:
            return []

        all_detail_alias_keys = self._block_detail_alias_keys_by_uid(visible_blocks)
        modules: list[PageOverviewModule] = []
        for index, block in enumerate(visible_blocks):
            label = _fallback_label(index)
            draft = _ModuleDraft(label=label, blocks=[block], has_explicit_label=False)
            modules.append(
                PageOverviewModule(
                    label=label,
                    block_uids=(str(getattr(block, "block_uid", "")),),
                    summary=self._summarize_module(draft),
                    aliases=self._aliases_for_block_module(
                        label=label,
                        block=block,
                        all_detail_alias_keys=all_detail_alias_keys,
                    ),
                )
            )
        return modules

    def _format_module_choice_overview(
        self,
        modules: list[PageOverviewModule],
    ) -> str:
        parts = [
            f"{module.label}（{self._compact_summary_for_overview(module.summary)}）"
            for module in modules
        ]
        return "、".join(parts)

    def _compact_summary_for_overview(self, summary: str) -> str:
        text = re.sub(r"\s+", " ", summary).strip(" 。.!！")
        if not text:
            return "先看这一块"

        lower = text.casefold()
        if not re.search(r"[\u4e00-\u9fff]", text):
            if "listen" in lower and "circle" in lower:
                return "听音辨词"
            if "listen" in lower and "complete" in lower:
                return "听音补词"
            if "ow as in" in lower or ("ow" in lower and "pronunciation" in lower):
                return "ow 发音"
            if "writing" in lower or "write" in lower:
                return "写句子"
            if "social media" in lower or "post" in lower:
                return "读图文"
            if "talking about" in lower or "dialogue" in lower:
                return "看对话"
            return _clip_for_overview(text, limit=18)

        text = re.sub(r"\s*Key patterns:.*$", "", text, flags=re.IGNORECASE).strip()
        if "饥饿" in text and "口渴" in text:
            return "hungry/thirsty"
        if "食物小词库" in text:
            return "食物小词库"
        if "饮料小词库" in text:
            return "饮料小词库"
        if "角色扮演" in text:
            return "角色扮演"
        if "示范" in text and "I'd like" in text:
            return "点餐示范"
        if "听" in text and ("录音" in text or "听力" in text):
            return "听力"
        if "认识" in text:
            vocabulary_hint = _vocabulary_hint_for_overview(text)
            if vocabulary_hint:
                return vocabulary_hint
            return "认词"
        text = re.sub(r"^(?:先|继续|再次)\s*", "", text)
        text = re.split(r"[。；;]", text, maxsplit=1)[0]
        text = re.split(r"，(?:再|然后|并|提供|要求|鼓励)", text, maxsplit=1)[0]
        return _clip_for_overview(text, limit=22)

    def _compact_page_topic_prefix(self, page_intro_cn: str) -> str:
        intro = re.sub(r"\s+", " ", page_intro_cn).strip()
        if not intro:
            return ""
        if any(token in intro for token in ("点餐", "想吃", "想喝", "餐厅")):
            return "练点餐，"
        return ""

    def _block_detail_alias_keys_by_uid(
        self,
        blocks: list[Any],
    ) -> dict[str, set[str]]:
        keys_by_uid: dict[str, set[str]] = {}
        for block in blocks:
            block_uid = str(getattr(block, "block_uid", "") or "")
            keys_by_uid[block_uid] = {
                _choice_key(alias)
                for alias in self._block_detail_aliases(block)
                if _choice_key(alias)
            }
        return keys_by_uid

    def _detect_module_label(self, block: Any) -> str | None:
        values: list[str] = []
        for attr in ("branchable_topics", "source_refs", "core_patterns"):
            values.extend(str(value) for value in getattr(block, attr, []) if value)
        values.append(str(getattr(block, "teaching_summary", "") or ""))

        haystack = "\n".join(values)
        for label, patterns in _MODULE_LABEL_PATTERNS:
            if any(re.search(pattern, haystack, flags=re.IGNORECASE) for pattern in patterns):
                return label
        return None

    def _summarize_module(self, draft: _ModuleDraft) -> str:
        summaries = [
            str(getattr(block, "teaching_summary", "") or "") for block in draft.blocks
        ]
        patterns = [
            str(pattern)
            for block in draft.blocks
            for pattern in getattr(block, "core_patterns", [])
            if pattern
        ]
        block_types = [
            str(getattr(block, "block_type", "") or "") for block in draft.blocks
        ]

        topic_bits = self._topic_bits(" ".join(summaries))
        activity_bits = self._activity_bits(patterns=patterns, block_types=block_types)
        if not draft.has_explicit_label and summaries:
            cleaned = _clean_summary(summaries[0])
            if cleaned and not topic_bits:
                return _finish_sentence(_shorten(cleaned, limit=64))
        bits = _unique([*topic_bits, *activity_bits])
        if not bits:
            cleaned = _clean_summary(summaries[0] if summaries else "")
            if cleaned:
                return _finish_sentence(_shorten(cleaned, limit=32))
            return "先了解这一块要做什么。"
        return _finish_sentence("，".join(bits[:3]))

    def _topic_bits(self, text: str) -> list[str]:
        bits: list[str] = []
        if "生日" in text and "日期" in text:
            bits.append("抓生日日期")
        elif "日期" in text:
            bits.append("练日期表达")
        if "基数词" in text or "序数词" in text:
            bits.append("复习基数词和序数词")
        return bits

    def _activity_bits(
        self,
        *,
        patterns: list[str],
        block_types: list[str],
    ) -> list[str]:
        bits: list[str] = []
        pattern_text = " ".join(patterns).casefold()
        if "listen" in pattern_text and "number" in pattern_text:
            bits.append("听录音排序")
        if "tick or cross" in pattern_text or "true or false" in pattern_text:
            bits.append("听录音判断")
        if "fill in the table" in pattern_text:
            bits.append("填表巩固")
        if "finish the sentences" in pattern_text:
            bits.append("补全句子")
        if "write" in pattern_text and "sentence" in pattern_text:
            bits.append("写句子")
        if "match" in pattern_text:
            bits.append("配对")

        for block_type in block_types:
            normalized = block_type.casefold()
            if normalized == "listening_probe":
                bits.append("听录音抓关键信息")
            elif normalized == "summary_wrap_up":
                bits.append("整理本单元重点")
            elif normalized == "assessment_quiz":
                bits.append("做小检测")
            elif normalized == "practice_fill_blank":
                bits.append("填空巩固")
            elif normalized == "practice_write":
                bits.append("写句子练习")
            elif normalized == "dialogue_core":
                bits.append("看对话抓关键句")
            elif normalized == "dialogue_practice":
                bits.append("练短对话")
            elif normalized == "reading_passage":
                bits.append("读短文抓信息")
        return _unique(bits)

    def _aliases_for_label(self, label: str) -> tuple[str, ...]:
        aliases = [label]
        lower = label.casefold()
        if lower.startswith("let's "):
            aliases.append(label[6:])
        if lower == "let's wrap it up":
            aliases.extend(["wrap it up", "wrap up", "Let's wrap up"])
        return tuple(_unique(aliases))

    def _aliases_for_block_module(
        self,
        *,
        label: str,
        block: Any,
        all_detail_alias_keys: dict[str, set[str]],
    ) -> tuple[str, ...]:
        aliases = [
            label,
            str(getattr(block, "block_uid", "") or ""),
        ]
        detail_aliases = self._block_detail_aliases(block)
        if _is_broad_core_block(block):
            block_uid = str(getattr(block, "block_uid", "") or "")
            other_keys: set[str] = set()
            for uid, keys in all_detail_alias_keys.items():
                if uid != block_uid:
                    other_keys.update(keys)
            detail_aliases = [
                alias
                for alias in detail_aliases
                if _choice_key(alias) and _choice_key(alias) not in other_keys
            ]
            detail_aliases = [
                alias
                for alias in detail_aliases
                if alias not in [*getattr(block, "core_patterns", [])]
            ]
        aliases.extend(detail_aliases[:12])
        return tuple(_unique(aliases))

    def _block_detail_aliases(self, block: Any) -> list[str]:
        aliases: list[str] = []
        for attr in _ALIAS_DETAIL_FIELDS:
            for value in getattr(block, attr, []) or []:
                aliases.extend(_alias_variants(str(value)))
        return _unique(aliases)

    def _format_labels(self, labels: list[str]) -> str:
        if len(labels) == 2:
            return f"{labels[0]} 和 {labels[1]}"
        return "、".join(labels[:-1]) + f" 和 {labels[-1]}"

    def _format_choices(self, labels: list[str]) -> str:
        if len(labels) == 2:
            return f"{labels[0]} 或 {labels[1]}"
        return "、".join(labels[:-1]) + f" 或 {labels[-1]}"

    def _choice_index(self, normalized: str) -> int | None:
        if normalized in {"1", "one", "first", "第1个", "第1块"}:
            return 0
        if normalized in {"2", "two", "second", "第2个", "第2块"}:
            return 1
        if normalized in {"3", "three", "third", "第3个", "第3块"}:
            return 2
        for char, index in _CHINESE_ORDINALS.items():
            if f"第{char}" in normalized:
                return index
        return None


def _clean_summary(text: str) -> str:
    cleaned = re.sub(r"Key patterns:.*$", "", text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^Theme:\s*[^。.!?]+[。.!?]?\s*", "", cleaned).strip()
    return cleaned


def _shorten(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip("，,。.!?；;") + "..."


def _vocabulary_hint_for_overview(text: str) -> str:
    words = [
        " ".join(match.group(0).split())
        for match in re.finditer(r"[A-Za-z][A-Za-z]*(?:\s+[A-Za-z][A-Za-z]*)*", text)
    ]
    words = [
        word
        for word in _unique(words)
        if word.casefold() not in {"i", "key patterns", "let", "learn"}
    ]
    if len(words) >= 2:
        return f"{words[0]}/{words[-1]}"
    if words:
        return words[0]
    return ""


def _clip_for_overview(text: str, *, limit: int) -> str:
    cleaned = text.strip(" ，,。.!?；;")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip(" ，,。.!?；;")


def _finish_sentence(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "先了解这一块要做什么。"
    if stripped.endswith(("。", "！", "？", ".", "!", "?")):
        return stripped
    return f"{stripped}。"


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        if not stripped:
            continue
        key = stripped.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(stripped)
    return result


def _choice_key(text: str) -> str:
    return re.sub(r"[\s'’`\"“”.,!?！？。；;:：、，-]+", "", text.casefold())


def _fallback_label(index: int) -> str:
    if index < len(_FALLBACK_MODULE_LABELS):
        return _FALLBACK_MODULE_LABELS[index]
    return f"第{index + 1}块"


def _has_visible_source(block: Any) -> bool:
    return any(str(value).strip() for value in getattr(block, "source_refs", []) or [])


def _is_broad_core_block(block: Any) -> bool:
    block_type = str(getattr(block, "block_type", "") or "").casefold()
    return block_type in _BROAD_CORE_BLOCK_TYPES


def _alias_variants(text: str) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    variants = []
    if _alias_is_safe_for_content_match(cleaned):
        variants.append(cleaned)
    for token in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", cleaned):
        normalized = token.strip("'’`-").casefold()
        if len(normalized) < 4 or normalized in _ALIAS_WORD_STOPWORDS:
            continue
        variants.append(normalized)
    return variants


def _alias_is_safe_for_content_match(text: str) -> bool:
    key = _choice_key(text)
    if not key:
        return False
    if re.search(r"[\u4e00-\u9fff]", text):
        return len(key) >= 2
    return len(key) >= 4
