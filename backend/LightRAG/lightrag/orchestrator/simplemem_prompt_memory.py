"""Read-only learner-memory summaries for lesson prompt injection."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from lightrag.orchestrator.simplemem_semantic_memory import (
    SimpleMemSemanticRecallProvider,
)
from lightrag.utils import logger


_MISTAKE_HINTS = {
    "mistake",
    "error",
    "wrong",
    "confuse",
    "confuses",
    "omit",
    "omits",
    "forgot",
    "forgets",
    "struggle",
    "struggles",
    "漏",
    "错",
    "不会",
    "混淆",
}
_PREFERENCE_HINTS = {
    "prefer",
    "prefers",
    "likes",
    "responds",
    "better",
    "needs",
    "enjoys",
    "prefers",
    "喜欢",
    "中文",
    "带读",
    "拆开",
    "重复",
}
_MASTERY_HINTS = {
    "mastered",
    "shaky",
    "improved",
    "stable",
    "not_mastered",
    "mastery",
    "can now",
    "掌握",
    "熟练",
    "不稳",
    "薄弱",
}
_PREFERENCE_TEXT_BY_KEY = {
    "chinese_explanation": "Learner prefers Chinese explanation before retry.",
    "slow_split_practice": "Learner prefers slower split practice when stuck.",
}
_PREFERENCE_HINTS_BY_KEY = {
    "chinese_explanation": {
        "中文",
        "chinese",
        "l1",
        "l1 scaffold",
        "native language",
        "home language",
        "translation",
        "translation cue",
        "translate",
        "mother tongue",
    },
    "slow_split_practice": {
        "slow",
        "slower",
        "chunk",
        "chunked scaffold",
        "split",
        "part by part",
        "phrase by phrase",
        "smaller parts",
        "smaller phrases",
        "clause by clause",
        "step by step",
        "one by one",
        "again slowly",
        "拆开",
        "慢",
    },
}
_TARGET_SENTENCE_HINTS = {
    "sentence",
    "answer",
    "pattern",
    "reply",
    "say",
    "句",
    "回答",
    "作答",
}
_GENERIC_SEMANTIC_PROGRESS_HINTS = {
    "help",
    "need",
    "needs",
    "practice",
    "response",
    "retry",
    "still",
    "support",
    "try",
    "guided",
}
_GENERIC_SEMANTIC_PROGRESS_STRUCTURE_HINTS = {
    "answer",
    "here",
    "page",
    "pattern",
    "practice",
    "response",
    "retry",
    "sentence",
    "turn",
}
_RELEVANCE_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "could",
    "does",
    "for",
    "from",
    "help",
    "how",
    "i",
    "is",
    "like",
    "me",
    "mean",
    "my",
    "of",
    "on",
    "please",
    "some",
    "the",
    "this",
    "to",
    "what",
    "with",
    "would",
    "you",
}


def _normalize(value: str) -> str:
    lowered = value.casefold()
    cleaned = re.sub(r"[^a-z0-9\u4e00-\u9fff'\s]", " ", lowered)
    return " ".join(cleaned.split())


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


@dataclass(frozen=True)
class _PromptMemorySignal:
    category: Literal["mistake", "preference", "mastery"]
    text: str
    facts: dict[str, Any]
    timestamp: str = ""
    memory_session_id: str = ""


class LayeredMemoryItem(BaseModel):
    """Prompt-safe fact/episode/procedure view of a memory signal."""

    model_config = ConfigDict(extra="forbid")

    layer: Literal["fact", "episode", "procedure"]
    category: Literal["mistake", "preference", "mastery", "semantic"]
    text: str
    stability: Literal["current", "stable"]
    prompt_use: str


class MemoryConflictResolution(BaseModel):
    """Explain which progress memory wins when stable signals disagree."""

    model_config = ConfigDict(extra="forbid")

    target: str
    chosen_category: Literal["mistake", "mastery"]
    suppressed_category: Literal["mistake", "mastery"]
    reason: str


class LearnerMemorySummary(BaseModel):
    """Compact learner-memory payload safe to inject into prompts."""

    model_config = ConfigDict(extra="forbid")

    student_id: str
    common_mistakes: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    mastery_signals: list[str] = Field(default_factory=list)
    stable_common_mistakes: list[str] = Field(default_factory=list)
    stable_preferences: list[str] = Field(default_factory=list)
    stable_mastery_signals: list[str] = Field(default_factory=list)
    semantic_memories: list[str] = Field(default_factory=list)
    memory_layers: list[LayeredMemoryItem] = Field(default_factory=list)
    memory_conflicts: list[MemoryConflictResolution] = Field(default_factory=list)
    summary_text: str = ""

    def has_content(self) -> bool:
        return bool(
            self.common_mistakes
            or self.preferences
            or self.mastery_signals
            or self.stable_common_mistakes
            or self.stable_preferences
            or self.stable_mastery_signals
            or self.summary_text
            or self.semantic_memories
            or self.memory_layers
            or self.memory_conflicts
        )

    def to_prompt_payload(self) -> dict[str, Any]:
        return self.model_dump()


class SimpleMemSQLitePromptMemoryProvider:
    """Read learner-specific prompt memory from SimpleMem-Cross SQLite."""

    def __init__(
        self,
        *,
        db_path: str | Path,
        project: str,
        max_summaries: int = 4,
        max_observations: int = 8,
        category_limit: int = 2,
        semantic_recall_provider: SimpleMemSemanticRecallProvider | None = None,
    ) -> None:
        self.db_path = Path(db_path).expanduser()
        self.project = project
        self.max_summaries = max(1, max_summaries)
        self.max_observations = max(1, max_observations)
        self.category_limit = max(1, category_limit)
        self.semantic_recall_provider = semantic_recall_provider

    def get_summary(
        self,
        *,
        student_id: str,
        learner_input: str,
        state_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
        exclude_memory_session_id: str | None = None,
    ) -> LearnerMemorySummary:
        if not self.db_path.exists():
            return LearnerMemorySummary(student_id=student_id)

        try:
            with self._connect() as conn:
                summaries = self._fetch_recent_summaries(
                    conn,
                    student_id,
                    exclude_memory_session_id=exclude_memory_session_id,
                )
                observations = self._fetch_recent_observations(
                    conn,
                    student_id,
                    exclude_memory_session_id=exclude_memory_session_id,
                )
        except Exception as exc:
            logger.warning("SimpleMem prompt-memory lookup failed: %s", exc)
            return LearnerMemorySummary(student_id=student_id)

        relevance_context = self._build_relevance_context(
            learner_input=learner_input,
            state_snapshot=state_snapshot,
            block_snapshot=block_snapshot,
        )
        all_signals = [
            self._canonicalize_signal(signal, relevance_context=relevance_context)
            for signal in [*summaries, *observations]
        ]
        current_common_mistake_keys: set[str] = set()
        current_preference_keys: set[str] = set()
        current_mastery_keys: set[str] = set()
        common_mistakes = self._select_signals_for_category(
            signals=all_signals,
            category="mistake",
            relevance_context=relevance_context,
            selected_signal_keys=current_common_mistake_keys,
        )
        preferences = self._select_signals_for_category(
            signals=all_signals,
            category="preference",
            relevance_context=relevance_context,
            selected_signal_keys=current_preference_keys,
        )
        mastery_signals = self._select_signals_for_category(
            signals=all_signals,
            category="mastery",
            relevance_context=relevance_context,
            selected_signal_keys=current_mastery_keys,
        )
        current_common_mistake_texts = self._normalized_texts(common_mistakes)
        current_preference_texts = self._normalized_texts(preferences)
        current_mastery_texts = self._normalized_texts(mastery_signals)
        stable_common_mistake_keys: set[str] = set()
        stable_preference_keys: set[str] = set()
        stable_mastery_keys: set[str] = set()
        stable_common_mistakes = self._select_stable_signals_for_category(
            signals=all_signals,
            category="mistake",
            relevance_context=relevance_context,
            excluded_texts=current_common_mistake_texts,
            excluded_signal_keys=current_common_mistake_keys,
            selected_signal_keys=stable_common_mistake_keys,
        )
        stable_preferences = self._select_stable_signals_for_category(
            signals=all_signals,
            category="preference",
            relevance_context=relevance_context,
            excluded_texts=(
                current_preference_texts
                | self._current_block_preference_texts(
                    all_signals,
                    relevance_context=relevance_context,
                )
            ),
            excluded_signal_keys=current_preference_keys,
            selected_signal_keys=stable_preference_keys,
        )
        stable_mastery_signals = self._select_stable_signals_for_category(
            signals=all_signals,
            category="mastery",
            relevance_context=relevance_context,
            excluded_texts=current_mastery_texts,
            excluded_signal_keys=current_mastery_keys,
            selected_signal_keys=stable_mastery_keys,
        )
        semantic_memories: list[str] = []
        if self.semantic_recall_provider is not None:
            try:
                semantic_memories = self.semantic_recall_provider.recall(
                    student_id=student_id,
                    learner_input=learner_input,
                    state_snapshot=state_snapshot,
                    block_snapshot=block_snapshot,
                    exclude_memory_session_id=exclude_memory_session_id,
                )
                semantic_memories = self._filter_semantic_memories(
                    semantic_memories,
                    relevance_context=relevance_context,
                    excluded_texts=(
                        current_common_mistake_texts
                        | current_preference_texts
                        | current_mastery_texts
                        | self._normalized_texts(stable_common_mistakes)
                        | self._normalized_texts(stable_preferences)
                        | self._normalized_texts(stable_mastery_signals)
                    ),
                    excluded_signal_keys=(
                        current_common_mistake_keys
                        | current_preference_keys
                        | current_mastery_keys
                        | stable_common_mistake_keys
                        | stable_preference_keys
                        | stable_mastery_keys
                    ),
                )
            except Exception as exc:
                logger.warning("SimpleMem semantic recall failed: %s", exc)
        memory_conflicts = self._build_memory_conflict_resolutions(
            signals=all_signals,
            relevance_context=relevance_context,
        )
        memory_layers = self._build_layered_memory_items(
            signals=all_signals,
            common_mistakes=common_mistakes,
            preferences=preferences,
            mastery_signals=mastery_signals,
            stable_common_mistakes=stable_common_mistakes,
            stable_preferences=stable_preferences,
            stable_mastery_signals=stable_mastery_signals,
            semantic_memories=semantic_memories,
            relevance_context=relevance_context,
        )
        summary_text = self._render_summary_text(
            common_mistakes=common_mistakes,
            preferences=preferences,
            mastery_signals=mastery_signals,
            stable_common_mistakes=stable_common_mistakes,
            stable_preferences=stable_preferences,
            stable_mastery_signals=stable_mastery_signals,
            semantic_memories=semantic_memories,
            memory_conflicts=memory_conflicts,
        )
        return LearnerMemorySummary(
            student_id=student_id,
            common_mistakes=common_mistakes,
            preferences=preferences,
            mastery_signals=mastery_signals,
            stable_common_mistakes=stable_common_mistakes,
            stable_preferences=stable_preferences,
            stable_mastery_signals=stable_mastery_signals,
            semantic_memories=semantic_memories,
            memory_layers=memory_layers,
            memory_conflicts=memory_conflicts,
            summary_text=summary_text,
        )

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self.db_path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _fetch_recent_summaries(
        self,
        conn: sqlite3.Connection,
        student_id: str,
        *,
        exclude_memory_session_id: str | None = None,
    ) -> list[_PromptMemorySignal]:
        params: list[Any] = [student_id, self.project]
        exclude_clause = ""
        if exclude_memory_session_id:
            exclude_clause = "AND ss.memory_session_id != ?"
            params.append(exclude_memory_session_id)
        params.append(self.max_summaries)
        cursor = conn.execute(
            f"""
            SELECT
                ss.memory_session_id,
                ss.timestamp,
                ss.learned,
                ss.completed,
                ss.next_steps,
                s.metadata_json
            FROM session_summaries AS ss
            JOIN sessions AS s ON s.memory_session_id = ss.memory_session_id
            WHERE s.tenant_id = ? AND s.project = ?
            {exclude_clause}
            ORDER BY ss.timestamp DESC
            LIMIT ?
            """,
            params,
        )
        rows = cursor.fetchall()
        result: list[_PromptMemorySignal] = []
        for row in rows:
            base_facts = self._merge_session_metadata_facts({}, row["metadata_json"])
            summary_parts = (
                ("mistake", row["learned"]),
                ("mastery", row["completed"]),
                ("preference", row["next_steps"]),
            )
            for category, part in summary_parts:
                text = _clean_text(part)
                if text:
                    result.append(
                        _PromptMemorySignal(
                            category=category,
                            text=text,
                            facts=dict(base_facts),
                            timestamp=_clean_text(row["timestamp"]),
                            memory_session_id=_clean_text(row["memory_session_id"]),
                        )
                    )
        return result

    def _fetch_recent_observations(
        self,
        conn: sqlite3.Connection,
        student_id: str,
        *,
        exclude_memory_session_id: str | None = None,
    ) -> list[_PromptMemorySignal]:
        params: list[Any] = [student_id, self.project]
        exclude_clause = ""
        if exclude_memory_session_id:
            exclude_clause = "AND o.memory_session_id != ?"
            params.append(exclude_memory_session_id)
        params.append(self.max_observations)
        cursor = conn.execute(
            f"""
            SELECT
                o.memory_session_id,
                o.timestamp,
                o.title,
                o.subtitle,
                o.narrative,
                o.facts_json,
                s.metadata_json
            FROM observations AS o
            JOIN sessions AS s ON s.memory_session_id = o.memory_session_id
            WHERE s.tenant_id = ? AND s.project = ?
            {exclude_clause}
            ORDER BY o.timestamp DESC
            LIMIT ?
            """,
            params,
        )
        rows = cursor.fetchall()
        result: list[_PromptMemorySignal] = []
        for row in rows:
            facts = self._merge_session_metadata_facts(
                self._parse_json(row["facts_json"]),
                row["metadata_json"],
            )
            category = self._coerce_category(facts.get("candidate_kind"))
            fallback_text = self._render_fallback_observation_text(row)
            if category is None:
                category = self._classify_text(fallback_text)
            if category is None:
                continue
            text = self._render_observation_signal_text(
                category=category,
                row=row,
                facts=facts,
            )
            if text:
                result.append(
                    _PromptMemorySignal(
                        category=category,
                        text=text,
                        facts=facts,
                        timestamp=_clean_text(row["timestamp"]),
                        memory_session_id=_clean_text(row["memory_session_id"]),
                    )
                )
        return result

    def _merge_session_metadata_facts(
        self,
        facts: dict[str, Any],
        metadata_json: Any,
    ) -> dict[str, Any]:
        metadata = self._parse_json(metadata_json)
        if not metadata:
            return facts
        merged = dict(facts)
        for key in ("page_uid", "page_type", "block_uid", "block_type"):
            if not _clean_text(merged.get(key)) and _clean_text(metadata.get(key)):
                merged[key] = _clean_text(metadata.get(key))
        return merged

    def _parse_json(self, value: Any) -> dict[str, Any]:
        if not value:
            return {}
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _classify_text(self, text: str) -> str | None:
        normalized = _normalize(text)
        if not normalized:
            return None
        if self._contains_any(normalized, _MISTAKE_HINTS):
            return "mistake"
        if self._contains_any(normalized, _MASTERY_HINTS):
            return "mastery"
        if self._contains_any(normalized, _PREFERENCE_HINTS):
            return "preference"
        return None

    def _contains_any(self, normalized_text: str, hints: set[str]) -> bool:
        return any(hint in normalized_text for hint in hints)

    def _coerce_category(
        self,
        value: Any,
    ) -> Literal["mistake", "preference", "mastery"] | None:
        candidate = _clean_text(value).casefold()
        if candidate in {"mistake", "preference", "mastery"}:
            return candidate
        return None

    def _render_observation_signal_text(
        self,
        *,
        category: Literal["mistake", "preference", "mastery"],
        row: sqlite3.Row,
        facts: dict[str, Any],
    ) -> str:
        if category == "mistake":
            return self._render_mistake_signal(row=row, facts=facts)
        if category == "preference":
            return self._render_preference_signal(row=row, facts=facts)
        return self._render_mastery_signal(row=row, facts=facts)

    def _render_mistake_signal(
        self,
        *,
        row: sqlite3.Row,
        facts: dict[str, Any],
    ) -> str:
        return self._render_mistake_text(
            facts=facts,
            fallback_text=self._render_fallback_observation_text(row),
        )

    def _render_mistake_text(
        self,
        *,
        facts: dict[str, Any],
        fallback_text: str,
    ) -> str:
        model_answer = _clean_text(facts.get("model_answer"))
        mistake_focus = _clean_text(facts.get("mistake_focus")).casefold()
        if model_answer:
            if mistake_focus == "missing_full_pattern":
                return f'Learner still needs the full sentence "{model_answer}"'
            if mistake_focus == "off_topic_answer":
                return f'Learner needs to stay on the target sentence "{model_answer}"'
            if mistake_focus == "unclear_answer":
                return f'Learner still cannot produce "{model_answer}" clearly'
            return f'Learner still needs the target sentence "{model_answer}"'
        return fallback_text

    def _render_preference_signal(
        self,
        *,
        row: sqlite3.Row,
        facts: dict[str, Any],
    ) -> str:
        return self._render_preference_text(
            facts=facts,
            fallback_text=self._render_fallback_observation_text(row),
        )

    def _render_preference_text(
        self,
        *,
        facts: dict[str, Any],
        fallback_text: str,
    ) -> str:
        preference_key = _clean_text(facts.get("preference_key")).casefold()
        if preference_key in _PREFERENCE_TEXT_BY_KEY:
            return _PREFERENCE_TEXT_BY_KEY[preference_key]
        return fallback_text

    def _render_mastery_signal(
        self,
        *,
        row: sqlite3.Row,
        facts: dict[str, Any],
    ) -> str:
        return self._render_mastery_text(
            facts=facts,
            fallback_text=self._render_fallback_observation_text(row),
        )

    def _render_mastery_text(
        self,
        *,
        facts: dict[str, Any],
        fallback_text: str,
    ) -> str:
        model_answer = _clean_text(facts.get("model_answer"))
        if model_answer:
            return f'Learner can now answer "{model_answer}" correctly'
        return fallback_text

    def _render_fallback_observation_text(self, row: sqlite3.Row) -> str:
        title = _clean_text(row["title"])
        subtitle = _clean_text(row["subtitle"])
        if title and subtitle:
            return f"{title} | {subtitle}"
        return title or subtitle or _clean_text(row["narrative"])

    def _select_signals_for_category(
        self,
        *,
        signals: list[_PromptMemorySignal],
        category: Literal["mistake", "preference", "mastery"],
        relevance_context: dict[str, Any],
        selected_signal_keys: set[str] | None = None,
    ) -> list[str]:
        support_counts = self._build_support_counts(signals=signals, category=category)
        current_block_preference_exists = (
            category == "preference"
            and any(
                self._preference_scope(signal, relevance_context=relevance_context)
                == "current_block"
                for signal in signals
                if signal.category == "preference"
            )
        )
        ranked = sorted(
            (
                signal
                for signal in signals
                if signal.category == category
                and self._should_include_current_signal(
                    signal,
                    category=category,
                    relevance_context=relevance_context,
                    current_block_preference_exists=current_block_preference_exists,
                )
            ),
            key=lambda signal: (
                self._signal_specificity_rank(signal),
                self._score_signal(
                    signal,
                    relevance_context=relevance_context,
                    support_counts=support_counts,
                ),
                signal.timestamp,
            ),
            reverse=True,
        )
        result: list[str] = []
        seen: set[str] = set()
        seen_signal_keys: set[str] = set()
        for signal in ranked:
            signal_key = self._selection_signal_key(signal)
            if signal_key and signal_key in seen_signal_keys:
                continue
            appended = self._append_unique(result, signal.text, seen=seen)
            if appended and signal_key:
                seen_signal_keys.add(signal_key)
                if selected_signal_keys is not None:
                    selected_signal_keys.add(signal_key)
            if len(result) >= self.category_limit:
                break
        return result

    def _should_include_current_signal(
        self,
        signal: _PromptMemorySignal,
        *,
        category: Literal["mistake", "preference", "mastery"],
        relevance_context: dict[str, Any],
        current_block_preference_exists: bool,
    ) -> bool:
        if category != "preference":
            return True
        scope = self._preference_scope(signal, relevance_context=relevance_context)
        if scope == "other_scope":
            return False
        if current_block_preference_exists and scope in {"current_page", "global"}:
            return False
        return True

    def _current_block_preference_texts(
        self,
        signals: list[_PromptMemorySignal],
        *,
        relevance_context: dict[str, Any],
    ) -> set[str]:
        result: set[str] = set()
        for signal in signals:
            if signal.category != "preference":
                continue
            if self._preference_scope(signal, relevance_context=relevance_context) != "current_block":
                continue
            normalized = _normalize(signal.text)
            if normalized:
                result.add(normalized)
        return result

    def _canonicalize_signal(
        self,
        signal: _PromptMemorySignal,
        *,
        relevance_context: dict[str, Any],
    ) -> _PromptMemorySignal:
        facts = dict(signal.facts)
        text = signal.text

        if signal.category == "preference":
            preference_key = self._preference_key(signal)
            if not preference_key:
                preference_key = self._infer_preference_key_from_text(text)
            if preference_key:
                facts["preference_key"] = preference_key
            text = self._render_preference_text(facts=facts, fallback_text=text)
        elif signal.category == "mistake":
            facts = self._enrich_progress_facts(
                category="mistake",
                text=text,
                facts=facts,
                relevance_context=relevance_context,
            )
            text = self._render_mistake_text(facts=facts, fallback_text=text)
        elif signal.category == "mastery":
            facts = self._enrich_progress_facts(
                category="mastery",
                text=text,
                facts=facts,
                relevance_context=relevance_context,
            )
            text = self._render_mastery_text(facts=facts, fallback_text=text)

        if text != signal.text and not _clean_text(facts.get("source_text")):
            facts["source_text"] = signal.text

        if facts == signal.facts and text == signal.text:
            return signal

        return _PromptMemorySignal(
            category=signal.category,
            text=text,
            facts=facts,
            timestamp=signal.timestamp,
            memory_session_id=signal.memory_session_id,
        )

    def _enrich_progress_facts(
        self,
        *,
        category: Literal["mistake", "mastery"],
        text: str,
        facts: dict[str, Any],
        relevance_context: dict[str, Any],
    ) -> dict[str, Any]:
        enriched = dict(facts)
        if not _clean_text(enriched.get("model_answer")):
            model_answer = self._infer_target_answer_from_context(
                text=text,
                relevance_context=relevance_context,
            )
            if not model_answer:
                model_answer = self._infer_target_answer_from_session_scope(
                    facts=enriched,
                    relevance_context=relevance_context,
                )
            if model_answer:
                enriched["model_answer"] = model_answer
        if (
            category == "mistake"
            and _clean_text(enriched.get("model_answer"))
            and not _clean_text(enriched.get("mistake_focus"))
        ):
            mistake_focus = self._infer_mistake_focus_from_text(text)
            if mistake_focus:
                enriched["mistake_focus"] = mistake_focus
        return enriched

    def _infer_preference_key_from_text(self, text: str) -> str:
        normalized_text = _normalize(text)
        if not normalized_text:
            return ""
        for key, hints in _PREFERENCE_HINTS_BY_KEY.items():
            if any(hint in normalized_text for hint in hints):
                return key
        return ""

    def _infer_target_answer_from_context(
        self,
        *,
        text: str,
        relevance_context: dict[str, Any],
    ) -> str:
        primary_target_answer = _clean_text(relevance_context.get("primary_target_answer"))
        if not primary_target_answer:
            return ""
        normalized_text = _normalize(text)
        if not normalized_text:
            return ""
        if not any(hint in normalized_text for hint in _TARGET_SENTENCE_HINTS):
            return ""
        signal_tokens = self._tokenize_text(text)
        if not signal_tokens:
            return ""
        if signal_tokens & relevance_context["context_tokens"]:
            return primary_target_answer
        return ""

    def _infer_target_answer_from_session_scope(
        self,
        *,
        facts: dict[str, Any],
        relevance_context: dict[str, Any],
    ) -> str:
        primary_target_answer = _clean_text(relevance_context.get("primary_target_answer"))
        if not primary_target_answer:
            return ""
        current_block_uid = _clean_text(relevance_context.get("current_block_uid"))
        current_page_uid = _clean_text(relevance_context.get("current_page_uid"))
        signal_block_uid = _clean_text(facts.get("block_uid"))
        signal_page_uid = _clean_text(facts.get("page_uid"))
        if signal_block_uid and current_block_uid and signal_block_uid == current_block_uid:
            return primary_target_answer
        if signal_page_uid and current_page_uid and signal_page_uid == current_page_uid:
            return primary_target_answer
        return ""

    def _infer_mistake_focus_from_text(self, text: str) -> str:
        normalized_text = _normalize(text)
        if ("full" in normalized_text and "sentence" in normalized_text) or "完整句" in normalized_text:
            return "missing_full_pattern"
        if "off topic" in normalized_text or "离题" in normalized_text:
            return "off_topic_answer"
        if "unclear" in normalized_text or "不清楚" in normalized_text:
            return "unclear_answer"
        return ""

    def _build_support_counts(
        self,
        *,
        signals: list[_PromptMemorySignal],
        category: Literal["mistake", "preference", "mastery"],
    ) -> dict[str, int]:
        support_sessions: dict[str, set[str]] = {}
        for signal in signals:
            if signal.category != category:
                continue
            key = self._support_key(signal)
            if not key:
                continue
            support_sessions.setdefault(key, set()).add(
                signal.memory_session_id or signal.timestamp or key
            )
        return {
            key: len(session_ids)
            for key, session_ids in support_sessions.items()
            if session_ids
        }

    def _select_stable_signals_for_category(
        self,
        *,
        signals: list[_PromptMemorySignal],
        category: Literal["mistake", "preference", "mastery"],
        relevance_context: dict[str, Any],
        excluded_texts: set[str] | None = None,
        excluded_signal_keys: set[str] | None = None,
        selected_signal_keys: set[str] | None = None,
    ) -> list[str]:
        support_counts = self._build_support_counts(signals=signals, category=category)
        progress_support_counts: dict[str, int] = {}
        for progress_category in ("mistake", "mastery"):
            progress_support_counts.update(
                self._build_support_counts(signals=signals, category=progress_category)
            )
        stable_progress_by_target = self._build_stable_progress_by_target(
            signals=signals,
            relevance_context=relevance_context,
            support_counts=progress_support_counts,
        )
        ranked = sorted(
            (
                signal
                for signal in signals
                if signal.category == category
                and support_counts.get(self._support_key(signal), 0) > 1
                and self._is_stable_signal_specific_enough(signal)
                and self._is_stable_scope_relevant(
                    signal,
                    category=category,
                    relevance_context=relevance_context,
                )
                and self._should_keep_stable_signal(
                    signal,
                    stable_progress_by_target=stable_progress_by_target,
                )
            ),
            key=lambda signal: (
                self._stable_scope_priority(
                    signal,
                    category=category,
                    relevance_context=relevance_context,
                ),
                support_counts.get(self._support_key(signal), 0),
                self._signal_specificity_rank(signal),
                self._score_signal(
                    signal,
                    relevance_context=relevance_context,
                    support_counts=support_counts,
                ),
                signal.timestamp,
            ),
            reverse=True,
        )
        result: list[str] = []
        seen: set[str] = set(excluded_texts or set())
        seen_signal_keys: set[str] = set(excluded_signal_keys or set())
        for signal in ranked:
            signal_key = self._selection_signal_key(signal)
            if signal_key and signal_key in seen_signal_keys:
                continue
            appended = self._append_unique(result, signal.text, seen=seen)
            if appended and signal_key:
                seen_signal_keys.add(signal_key)
                if selected_signal_keys is not None:
                    selected_signal_keys.add(signal_key)
            if len(result) >= self.category_limit:
                break
        return result

    def _support_key(self, signal: _PromptMemorySignal) -> str:
        if signal.category == "preference":
            preference_key = self._preference_key(signal)
            if preference_key:
                scope_key = self._scope_key(signal)
                if scope_key:
                    return f"preference:{preference_key}@{scope_key}"
                return f"preference:{preference_key}"
        if signal.category in {"mistake", "mastery"}:
            target_key = self._target_key(signal)
            if target_key:
                return f"{signal.category}:{target_key}"
        return _normalize(signal.text)

    def _scope_key(self, signal: _PromptMemorySignal) -> str:
        block_uid = _clean_text(signal.facts.get("block_uid"))
        if block_uid:
            return f"block:{block_uid}"
        page_uid = _clean_text(signal.facts.get("page_uid"))
        if page_uid:
            return f"page:{page_uid}"
        return ""

    def _preference_scope(
        self,
        signal: _PromptMemorySignal,
        *,
        relevance_context: dict[str, Any],
    ) -> Literal["current_block", "current_page", "global", "other_scope"]:
        block_uid = _clean_text(signal.facts.get("block_uid"))
        page_uid = _clean_text(signal.facts.get("page_uid"))
        current_block_uid = _clean_text(relevance_context.get("current_block_uid"))
        current_page_uid = _clean_text(relevance_context.get("current_page_uid"))
        if block_uid:
            if current_block_uid and block_uid == current_block_uid:
                return "current_block"
            if current_page_uid and page_uid and page_uid == current_page_uid:
                return "current_page"
            return "other_scope"
        if page_uid:
            if current_page_uid and page_uid == current_page_uid:
                return "current_page"
            return "other_scope"
        return "global"

    def _is_stable_scope_relevant(
        self,
        signal: _PromptMemorySignal,
        *,
        category: Literal["mistake", "preference", "mastery"],
        relevance_context: dict[str, Any],
    ) -> bool:
        if category != "preference":
            return True
        scope = self._preference_scope(signal, relevance_context=relevance_context)
        if scope == "global":
            return True
        return scope in {"current_block", "current_page"}

    def _stable_scope_priority(
        self,
        signal: _PromptMemorySignal,
        *,
        category: Literal["mistake", "preference", "mastery"],
        relevance_context: dict[str, Any],
    ) -> int:
        if category != "preference":
            return 0
        scope = self._preference_scope(signal, relevance_context=relevance_context)
        return {
            "global": 2,
            "current_page": 1,
            "current_block": 0,
            "other_scope": -1,
        }[scope]

    def _preference_key(self, signal: _PromptMemorySignal) -> str:
        preference_key = _clean_text(signal.facts.get("preference_key")).casefold()
        if preference_key in _PREFERENCE_TEXT_BY_KEY:
            return preference_key
        normalized_text = _normalize(signal.text)
        for key, canonical_text in _PREFERENCE_TEXT_BY_KEY.items():
            if normalized_text == _normalize(canonical_text):
                return key
        return self._infer_preference_key_from_text(signal.text)

    def _target_key(self, signal: _PromptMemorySignal) -> str:
        if signal.category not in {"mistake", "mastery"}:
            return ""
        model_answer = _clean_text(signal.facts.get("model_answer"))
        if not model_answer:
            model_answer = self._extract_quoted_target(signal.text)
        return _normalize(model_answer)

    def _extract_quoted_target(self, text: str) -> str:
        match = re.search(r'"([^"]+)"', text)
        if match is None:
            return ""
        return _clean_text(match.group(1))

    def _build_stable_progress_by_target(
        self,
        *,
        signals: list[_PromptMemorySignal],
        relevance_context: dict[str, Any],
        support_counts: dict[str, int],
    ) -> dict[str, Literal["mistake", "mastery"]]:
        latest_by_target: dict[
            str,
            tuple[Literal["mistake", "mastery"], tuple[str, float, int]],
        ] = {}
        for signal in signals:
            if signal.category not in {"mistake", "mastery"}:
                continue
            if support_counts.get(self._support_key(signal), 0) <= 1:
                continue
            target_key = self._target_key(signal)
            if not target_key:
                continue
            candidate_rank = (
                signal.timestamp,
                self._score_signal(
                    signal,
                    relevance_context=relevance_context,
                    support_counts=support_counts,
                ),
                1 if signal.category == "mastery" else 0,
            )
            existing = latest_by_target.get(target_key)
            if existing is None or candidate_rank > existing[1]:
                latest_by_target[target_key] = (signal.category, candidate_rank)
        return {
            target_key: category
            for target_key, (category, _) in latest_by_target.items()
        }

    def _should_keep_stable_signal(
        self,
        signal: _PromptMemorySignal,
        *,
        stable_progress_by_target: dict[str, Literal["mistake", "mastery"]],
    ) -> bool:
        target_key = self._target_key(signal)
        if signal.category not in {"mistake", "mastery"} or not target_key:
            return True
        latest_category = stable_progress_by_target.get(target_key)
        return latest_category is None or latest_category == signal.category

    def _build_relevance_context(
        self,
        *,
        learner_input: str,
        state_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        target_answers = [
            _clean_text(value)
            for value in (
                list(block_snapshot.get("allowed_answer_scope") or [])
                + list(block_snapshot.get("core_patterns") or [])
            )
            if _clean_text(value)
        ]
        target_answers = list(dict.fromkeys(target_answers[:4]))
        context_parts: list[str] = [_clean_text(learner_input)]
        for key in (
            "teaching_goal",
            "teaching_summary",
            "page_uid",
            "block_uid",
            "block_type",
        ):
            value = _clean_text(block_snapshot.get(key))
            if value:
                context_parts.append(value)
        for key in (
            "current_page_uid",
            "current_block_uid",
            "current_activity_type",
            "branch_reason",
            "return_anchor",
        ):
            value = _clean_text(state_snapshot.get(key))
            if value:
                context_parts.append(value)
        for key in (
            "focus_vocabulary",
            "core_patterns",
            "allowed_answer_scope",
            "repair_modes",
            "branchable_topics",
            "return_anchors",
        ):
            raw_values = block_snapshot.get(key) or []
            if isinstance(raw_values, list):
                context_parts.extend(_clean_text(value) for value in raw_values if _clean_text(value))
        target_answer_tokens = [
            self._tokenize_text(value)
            for value in target_answers
            if self._tokenize_text(value)
        ]
        context_tokens: set[str] = set()
        for part in context_parts:
            context_tokens.update(self._tokenize_text(part))
        return {
            "current_page_uid": _clean_text(state_snapshot.get("current_page_uid")),
            "current_block_uid": _clean_text(state_snapshot.get("current_block_uid")),
            "current_block_type": _clean_text(block_snapshot.get("block_type")),
            "context_tokens": context_tokens,
            "primary_target_answer": target_answers[0] if target_answers else "",
            "target_answers": {_normalize(value) for value in target_answers if _normalize(value)},
            "target_answer_tokens": target_answer_tokens,
        }

    def _score_signal(
        self,
        signal: _PromptMemorySignal,
        *,
        relevance_context: dict[str, Any],
        support_counts: dict[str, int],
    ) -> float:
        score = 0.0
        signal_tokens = self._tokenize_text(signal.text)
        source_text = _clean_text(signal.facts.get("source_text"))
        if source_text:
            signal_tokens.update(self._tokenize_text(source_text))
        score += float(min(len(signal_tokens & relevance_context["context_tokens"]), 4))

        support_count = support_counts.get(self._support_key(signal), 1)
        if support_count > 1:
            score += float(min(support_count - 1, 3)) * 1.5

        facts = signal.facts
        if _clean_text(facts.get("page_uid")) == relevance_context["current_page_uid"]:
            score += 5.0
        if _clean_text(facts.get("block_uid")) == relevance_context["current_block_uid"]:
            score += 7.0
        if _clean_text(facts.get("block_type")) == relevance_context["current_block_type"]:
            score += 1.0
        if signal.category == "preference":
            if (
                _clean_text(facts.get("block_uid"))
                and relevance_context["current_block_uid"]
                and _clean_text(facts.get("block_uid")) != relevance_context["current_block_uid"]
            ):
                score -= 2.5
            elif (
                _clean_text(facts.get("page_uid"))
                and relevance_context["current_page_uid"]
                and _clean_text(facts.get("page_uid")) != relevance_context["current_page_uid"]
            ):
                score -= 1.5

        model_answer = _normalize(_clean_text(facts.get("model_answer")))
        if model_answer:
            if model_answer in relevance_context["target_answers"]:
                score += 6.0
            else:
                model_tokens = self._tokenize_text(model_answer)
                if model_tokens and relevance_context["target_answer_tokens"]:
                    best_overlap = max(
                        len(model_tokens & target_tokens)
                        for target_tokens in relevance_context["target_answer_tokens"]
                    )
                    score += float(min(best_overlap, 3)) * 1.5

        return score

    def _tokenize_text(self, value: str) -> set[str]:
        normalized = _normalize(value)
        if not normalized:
            return set()
        raw_tokens = re.findall(r"[a-z0-9']+|[\u4e00-\u9fff]+", normalized)
        result: set[str] = set()
        for token in raw_tokens:
            if token in _RELEVANCE_STOPWORDS:
                continue
            if len(token) == 1 and token.isascii():
                continue
            result.add(token)
        return result

    def _append_unique(self, bucket: list[str], text: str, *, seen: set[str]) -> bool:
        normalized = _normalize(text)
        if not normalized or normalized in seen:
            return False
        bucket.append(text)
        seen.add(normalized)
        return True

    def _normalized_texts(self, values: list[str]) -> set[str]:
        return {
            normalized
            for value in values
            if (normalized := _normalize(value))
        }

    def _selection_signal_key(self, signal: _PromptMemorySignal) -> str:
        support_key = self._support_key(signal)
        if support_key:
            return support_key
        return _normalize(signal.text)

    def _canonicalize_recalled_memory_text(
        self,
        text: str,
        *,
        relevance_context: dict[str, Any],
    ) -> tuple[str, str]:
        signal = self._canonicalize_recalled_memory_signal(
            text,
            relevance_context=relevance_context,
        )
        if signal is None:
            return _clean_text(text), ""
        return signal.text, self._selection_signal_key(signal)

    def _canonicalize_recalled_memory_signal(
        self,
        text: str,
        *,
        relevance_context: dict[str, Any],
    ) -> _PromptMemorySignal | None:
        cleaned_text = _clean_text(text)
        if not cleaned_text:
            return None
        signal = self._infer_recalled_memory_signal(
            cleaned_text,
            relevance_context=relevance_context,
        )
        if signal is None:
            return None
        return self._canonicalize_signal(
            signal,
            relevance_context=relevance_context,
        )

    def _infer_recalled_memory_signal(
        self,
        text: str,
        *,
        relevance_context: dict[str, Any],
    ) -> _PromptMemorySignal | None:
        facts: dict[str, Any] = {}
        category: Literal["mistake", "preference", "mastery"] | None = None
        preference_key = self._infer_preference_key_from_text(text)
        if preference_key:
            category = "preference"
            facts["preference_key"] = preference_key
        else:
            normalized_text = _normalize(text)
            model_answer = self._infer_target_answer_from_context(
                text=text,
                relevance_context=relevance_context,
            )
            if model_answer:
                if self._contains_any(normalized_text, _MASTERY_HINTS):
                    category = "mastery"
                    facts["model_answer"] = model_answer
                elif (
                    self._contains_any(normalized_text, _MISTAKE_HINTS)
                    or "need" in normalized_text
                    or "needs" in normalized_text
                    or "still" in normalized_text
                ):
                    category = "mistake"
                    facts["model_answer"] = model_answer
                    mistake_focus = self._infer_mistake_focus_from_text(text)
                    if mistake_focus:
                        facts["mistake_focus"] = mistake_focus
        if category is None:
            category = self._classify_text(text)
        if category is None:
            return None
        return _PromptMemorySignal(category=category, text=text, facts=facts)

    def _filter_semantic_memories(
        self,
        values: list[str],
        *,
        relevance_context: dict[str, Any],
        excluded_texts: set[str],
        excluded_signal_keys: set[str],
    ) -> list[str]:
        result: list[str] = []
        seen_texts = set(excluded_texts)
        seen_signal_keys = set(excluded_signal_keys)
        selected_progress_by_target = self._selected_progress_categories_by_target(
            excluded_signal_keys
        )
        for value in values:
            cleaned_text = _clean_text(value)
            if not cleaned_text:
                continue
            if self._looks_like_generic_semantic_progress_noise(
                cleaned_text,
                relevance_context=relevance_context,
            ):
                continue
            signal = self._canonicalize_recalled_memory_signal(
                cleaned_text,
                relevance_context=relevance_context,
            )
            if signal is not None and self._conflicts_with_selected_progress(
                signal,
                selected_progress_by_target=selected_progress_by_target,
            ):
                continue
            candidate_text = signal.text if signal is not None else cleaned_text
            signal_key = self._selection_signal_key(signal) if signal is not None else ""
            normalized_text = _normalize(candidate_text)
            if not normalized_text or normalized_text in seen_texts:
                continue
            if signal_key and signal_key in seen_signal_keys:
                continue
            result.append(candidate_text)
            seen_texts.add(normalized_text)
            if signal_key:
                seen_signal_keys.add(signal_key)
        return result

    def _selected_progress_categories_by_target(
        self,
        signal_keys: set[str],
    ) -> dict[str, set[Literal["mistake", "mastery"]]]:
        result: dict[str, set[Literal["mistake", "mastery"]]] = {}
        for signal_key in signal_keys:
            if signal_key.startswith("mistake:"):
                result.setdefault(signal_key.removeprefix("mistake:"), set()).add("mistake")
            elif signal_key.startswith("mastery:"):
                result.setdefault(signal_key.removeprefix("mastery:"), set()).add("mastery")
        return result

    def _build_memory_conflict_resolutions(
        self,
        *,
        signals: list[_PromptMemorySignal],
        relevance_context: dict[str, Any],
    ) -> list[MemoryConflictResolution]:
        support_counts: dict[str, int] = {}
        for progress_category in ("mistake", "mastery"):
            support_counts.update(
                self._build_support_counts(
                    signals=signals,
                    category=progress_category,
                )
            )
        stable_progress_by_target = self._build_stable_progress_by_target(
            signals=signals,
            relevance_context=relevance_context,
            support_counts=support_counts,
        )
        supported_by_target: dict[str, dict[Literal["mistake", "mastery"], str]] = {}
        target_display: dict[str, str] = {}
        for signal in signals:
            if signal.category not in {"mistake", "mastery"}:
                continue
            if support_counts.get(self._support_key(signal), 0) <= 1:
                continue
            target_key = self._target_key(signal)
            if not target_key:
                continue
            target_display.setdefault(target_key, self._target_display(signal))
            supported_by_target.setdefault(target_key, {})[signal.category] = signal.text

        result: list[MemoryConflictResolution] = []
        for target_key in sorted(supported_by_target):
            categories = supported_by_target[target_key]
            if not {"mistake", "mastery"}.issubset(categories):
                continue
            chosen = stable_progress_by_target.get(target_key)
            if chosen not in {"mistake", "mastery"}:
                continue
            suppressed: Literal["mistake", "mastery"] = (
                "mastery" if chosen == "mistake" else "mistake"
            )
            result.append(
                MemoryConflictResolution(
                    target=target_display.get(target_key, target_key),
                    chosen_category=chosen,
                    suppressed_category=suppressed,
                    reason=(
                        "Repeated progress signals conflict; choose the better "
                        "supported and more recent stable category for prompt use."
                    ),
                )
            )
        return result

    def _build_layered_memory_items(
        self,
        *,
        signals: list[_PromptMemorySignal],
        common_mistakes: list[str],
        preferences: list[str],
        mastery_signals: list[str],
        stable_common_mistakes: list[str],
        stable_preferences: list[str],
        stable_mastery_signals: list[str],
        semantic_memories: list[str],
        relevance_context: dict[str, Any],
    ) -> list[LayeredMemoryItem]:
        result: list[LayeredMemoryItem] = []
        seen: set[str] = set()

        progress_support_counts: dict[str, int] = {}
        for progress_category in ("mistake", "mastery"):
            progress_support_counts.update(
                self._build_support_counts(
                    signals=signals,
                    category=progress_category,
                )
            )
        stable_progress_by_target = self._build_stable_progress_by_target(
            signals=signals,
            relevance_context=relevance_context,
            support_counts=progress_support_counts,
        )
        self._append_promoted_progress_facts(
            result=result,
            seen=seen,
            signals=signals,
            support_counts=progress_support_counts,
            stable_progress_by_target=stable_progress_by_target,
        )

        preference_support_counts = self._build_support_counts(
            signals=signals,
            category="preference",
        )
        self._append_promoted_procedures(
            result=result,
            seen=seen,
            signals=signals,
            support_counts=preference_support_counts,
            relevance_context=relevance_context,
        )

        for text in stable_common_mistakes:
            self._append_layered_memory_item(
                result=result,
                seen=seen,
                layer="fact",
                category="mistake",
                text=text,
                stability="stable",
            )
        for text in stable_mastery_signals:
            self._append_layered_memory_item(
                result=result,
                seen=seen,
                layer="fact",
                category="mastery",
                text=text,
                stability="stable",
            )
        for text in stable_preferences:
            self._append_layered_memory_item(
                result=result,
                seen=seen,
                layer="procedure",
                category="preference",
                text=text,
                stability="stable",
            )
        for text in preferences:
            self._append_layered_memory_item(
                result=result,
                seen=seen,
                layer="procedure",
                category="preference",
                text=text,
                stability="current",
            )
        for text in common_mistakes:
            self._append_layered_memory_item(
                result=result,
                seen=seen,
                layer="episode",
                category="mistake",
                text=text,
                stability="current",
            )
        for text in mastery_signals:
            self._append_layered_memory_item(
                result=result,
                seen=seen,
                layer="episode",
                category="mastery",
                text=text,
                stability="current",
            )
        for text in semantic_memories:
            self._append_layered_memory_item(
                result=result,
                seen=seen,
                layer="episode",
                category="semantic",
                text=text,
                stability="current",
            )
        return result[:8]

    def _append_promoted_progress_facts(
        self,
        *,
        result: list[LayeredMemoryItem],
        seen: set[str],
        signals: list[_PromptMemorySignal],
        support_counts: dict[str, int],
        stable_progress_by_target: dict[str, Literal["mistake", "mastery"]],
    ) -> None:
        ranked = sorted(
            (
                signal
                for signal in signals
                if signal.category in {"mistake", "mastery"}
                and support_counts.get(self._support_key(signal), 0) > 1
                and self._target_key(signal)
                and stable_progress_by_target.get(self._target_key(signal))
                == signal.category
            ),
            key=lambda signal: (
                support_counts.get(self._support_key(signal), 0),
                signal.timestamp,
            ),
            reverse=True,
        )
        seen_targets: set[str] = set()
        for signal in ranked:
            target_key = self._target_key(signal)
            if target_key in seen_targets:
                continue
            seen_targets.add(target_key)
            self._append_layered_memory_item(
                result=result,
                seen=seen,
                layer="fact",
                category=signal.category,
                text=signal.text,
                stability="stable",
            )

    def _append_promoted_procedures(
        self,
        *,
        result: list[LayeredMemoryItem],
        seen: set[str],
        signals: list[_PromptMemorySignal],
        support_counts: dict[str, int],
        relevance_context: dict[str, Any],
    ) -> None:
        ranked = sorted(
            (
                signal
                for signal in signals
                if signal.category == "preference"
                and support_counts.get(self._support_key(signal), 0) > 1
                and self._is_stable_signal_specific_enough(signal)
                and self._is_stable_scope_relevant(
                    signal,
                    category="preference",
                    relevance_context=relevance_context,
                )
            ),
            key=lambda signal: (
                support_counts.get(self._support_key(signal), 0),
                signal.timestamp,
            ),
            reverse=True,
        )
        seen_preferences: set[str] = set()
        for signal in ranked:
            preference_key = self._preference_key(signal) or _normalize(signal.text)
            if preference_key in seen_preferences:
                continue
            seen_preferences.add(preference_key)
            self._append_layered_memory_item(
                result=result,
                seen=seen,
                layer="procedure",
                category="preference",
                text=signal.text,
                stability="stable",
            )

    def _append_layered_memory_item(
        self,
        *,
        result: list[LayeredMemoryItem],
        seen: set[str],
        layer: Literal["fact", "episode", "procedure"],
        category: Literal["mistake", "preference", "mastery", "semantic"],
        text: str,
        stability: Literal["current", "stable"],
    ) -> None:
        normalized = _normalize(text)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        result.append(
            LayeredMemoryItem(
                layer=layer,
                category=category,
                text=text,
                stability=stability,
                prompt_use=self._prompt_use_boundary(
                    layer=layer,
                    category=category,
                    stability=stability,
                ),
            )
        )

    def _prompt_use_boundary(
        self,
        *,
        layer: Literal["fact", "episode", "procedure"],
        category: Literal["mistake", "preference", "mastery", "semantic"],
        stability: Literal["current", "stable"],
    ) -> str:
        if layer == "procedure":
            return "Shape teaching style only; do not change lesson targets."
        if layer == "fact" and category == "mistake":
            return "Predict likely difficulty; keep lesson correctness authoritative."
        if layer == "fact" and category == "mastery":
            return "Avoid unnecessary over-drill; still follow current evaluation."
        if category == "semantic":
            return "Use as background only when relevant to the current turn."
        if stability == "current":
            return "Treat as recent episode; do not promote without repetition."
        return "Use as stable learner profile signal within the active lesson scope."

    def _target_display(self, signal: _PromptMemorySignal) -> str:
        model_answer = _clean_text(signal.facts.get("model_answer"))
        if model_answer:
            return model_answer
        quoted = self._extract_quoted_target(signal.text)
        if quoted:
            return quoted
        return self._target_key(signal)

    def _conflicts_with_selected_progress(
        self,
        signal: _PromptMemorySignal,
        *,
        selected_progress_by_target: dict[str, set[Literal["mistake", "mastery"]]],
    ) -> bool:
        if signal.category not in {"mistake", "mastery"}:
            return False
        target_key = self._target_key(signal)
        if not target_key:
            return False
        selected_categories = selected_progress_by_target.get(target_key, set())
        if signal.category == "mistake":
            return "mastery" in selected_categories
        return "mistake" in selected_categories

    def _looks_like_generic_semantic_progress_noise(
        self,
        text: str,
        *,
        relevance_context: dict[str, Any],
    ) -> bool:
        normalized_text = _normalize(text)
        if not normalized_text:
            return False
        if self._infer_preference_key_from_text(text):
            return False
        if self._extract_quoted_target(text):
            return False
        if self._infer_target_answer_from_context(
            text=text,
            relevance_context=relevance_context,
        ):
            return False
        if not self._contains_any(normalized_text, _GENERIC_SEMANTIC_PROGRESS_HINTS):
            return False
        return self._contains_any(
            normalized_text,
            _GENERIC_SEMANTIC_PROGRESS_STRUCTURE_HINTS,
        )

    def _signal_specificity_rank(self, signal: _PromptMemorySignal) -> int:
        if signal.category == "preference":
            return 1 if self._preference_key(signal) else 0
        if signal.category == "mastery":
            return 1 if self._target_key(signal) else 0
        if signal.category == "mistake":
            if not self._target_key(signal):
                return 0
            return 2 if _clean_text(signal.facts.get("mistake_focus")) else 1
        return 0

    def _is_stable_signal_specific_enough(self, signal: _PromptMemorySignal) -> bool:
        if signal.category == "preference":
            return bool(self._preference_key(signal))
        if signal.category in {"mistake", "mastery"}:
            return bool(self._target_key(signal))
        return False

    def _render_summary_text(
        self,
        *,
        common_mistakes: list[str],
        preferences: list[str],
        mastery_signals: list[str],
        stable_common_mistakes: list[str],
        stable_preferences: list[str],
        stable_mastery_signals: list[str],
        semantic_memories: list[str],
        memory_conflicts: list[MemoryConflictResolution],
    ) -> str:
        lines: list[str] = []
        if common_mistakes:
            lines.append("Common mistakes:")
            lines.extend(f"- {item}" for item in common_mistakes)
        if preferences:
            lines.append("Preferences:")
            lines.extend(f"- {item}" for item in preferences)
        if mastery_signals:
            lines.append("Mastery signals:")
            lines.extend(f"- {item}" for item in mastery_signals)
        if stable_common_mistakes or stable_preferences or stable_mastery_signals:
            lines.append("Stable learner profile:")
            if stable_common_mistakes:
                lines.extend(f"- Stable mistake: {item}" for item in stable_common_mistakes)
            if stable_preferences:
                lines.extend(f"- Stable preference: {item}" for item in stable_preferences)
            if stable_mastery_signals:
                lines.extend(f"- Stable mastery: {item}" for item in stable_mastery_signals)
        if semantic_memories:
            lines.append("Relevant past memories:")
            lines.extend(f"- {item}" for item in semantic_memories)
        if memory_conflicts:
            lines.append("Resolved memory conflicts:")
            lines.extend(
                "- "
                f"{item.target}: use {item.chosen_category}, "
                f"suppress {item.suppressed_category}. {item.reason}"
                for item in memory_conflicts
            )
        return "\n".join(lines)


def build_simplemem_prompt_memory_provider_from_env(
    *,
    semantic_recall_provider: SimpleMemSemanticRecallProvider | None = None,
) -> SimpleMemSQLitePromptMemoryProvider | None:
    """Create a read-only SimpleMem prompt-memory provider from env settings."""

    enabled = os.getenv("PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION")
    if enabled is None or enabled.strip().casefold() not in {"1", "true", "yes", "on"}:
        return None

    db_path = os.getenv("PEPTUTOR_SIMPLEMEM_CROSS_DB_PATH")
    if not db_path:
        db_path = str(Path.home() / ".simplemem-cross" / "cross_memory.db")

    project = os.getenv("PEPTUTOR_SIMPLEMEM_PROJECT", "peptutor-lesson")
    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project=project,
        max_summaries=int(os.getenv("PEPTUTOR_SIMPLEMEM_MAX_SUMMARIES", "4")),
        max_observations=int(os.getenv("PEPTUTOR_SIMPLEMEM_MAX_OBSERVATIONS", "8")),
        category_limit=int(os.getenv("PEPTUTOR_SIMPLEMEM_CATEGORY_LIMIT", "2")),
        semantic_recall_provider=semantic_recall_provider,
    )
    if not provider.db_path.exists():
        logger.warning(
            "SimpleMem prompt injection requested but SQLite DB was not found: %s",
            provider.db_path,
        )
        return None
    return provider
