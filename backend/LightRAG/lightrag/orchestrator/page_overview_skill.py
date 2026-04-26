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
        module_lines = " ".join(
            f"{module.label}：{module.summary}" for module in modules
        )
        teacher_response = (
            f"这一页有 {len(modules)} 块：{self._format_labels(labels)}。"
            f" {module_lines} {choice_prompt}"
        )
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

        explicit_labels = {
            draft.label for draft in drafts if draft.has_explicit_label and draft.blocks
        }
        if not {"Let's check", "Let's wrap it up"}.issubset(explicit_labels):
            return []

        return [
            PageOverviewModule(
                label=draft.label,
                block_uids=tuple(str(getattr(block, "block_uid", "")) for block in draft.blocks),
                summary=self._summarize_module(draft),
                aliases=self._aliases_for_label(draft.label),
            )
            for draft in drafts
            if draft.blocks
        ]

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
