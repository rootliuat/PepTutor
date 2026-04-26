"""Scoped lookup over unit-level lexicon and useful-expression support assets."""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from lightrag.orchestrator.lesson_retrieval import RetrievalSelection
from lightrag.orchestrator.support_asset_types import (
    ExpressionEntryRecord,
    LexiconEntryRecord,
    SupportAssetFile,
)

if TYPE_CHECKING:
    from lightrag.orchestrator.lesson_runtime import PilotLessonCatalog

_NORMALIZE_RE = re.compile(r"[^a-z0-9\u4e00-\u9fff]+")
_STOP_WORDS = {
    "a",
    "an",
    "the",
    "to",
    "of",
    "i",
    "you",
    "my",
    "your",
    "is",
    "are",
    "do",
    "does",
    "did",
    "what",
    "how",
    "can",
    "could",
    "would",
    "like",
    "mean",
    "means",
    "for",
    "say",
}
_CONTRACTIONS = {
    "what's": "what is",
    "it's": "it is",
    "i'm": "i am",
    "they're": "they are",
    "don't": "do not",
    "can't": "cannot",
    "isn't": "is not",
    "aren't": "are not",
    "i'd": "id",
}


class SupportMatch(BaseModel):
    """One support-asset hit selected for a knowledge or branch turn."""

    model_config = ConfigDict(extra="forbid")

    entry_uid: str
    entry_kind: str
    english: str
    chinese: str
    phonetic: str | None = None
    page_refs: list[str] = Field(default_factory=list)
    linked_page_uids: list[str] = Field(default_factory=list)
    linked_block_uids: list[str] = Field(default_factory=list)
    score: int


class SupportAssetRetriever:
    """Resolve scope-aware support hits from structured unit-level support assets."""

    def __init__(
        self,
        catalog: PilotLessonCatalog,
        *,
        support_paths: list[Path] | None = None,
    ):
        self.catalog = catalog
        self.support_paths = support_paths or _resolve_support_paths()
        self.assets_by_scope: dict[tuple[str, str, str], SupportAssetFile] = {}
        self._load()

    def search(
        self,
        *,
        current_page_uid: str,
        current_block_uid: str,
        selection: RetrievalSelection,
        query: str,
        limit: int = 2,
    ) -> list[SupportMatch]:
        scope = self.catalog.get_scope_for_page(current_page_uid)
        asset = self.assets_by_scope.get((scope.grade, scope.semester, scope.unit))
        if asset is None:
            return []

        selected_block_uids = selection.block_uids or [current_block_uid]
        selected_page_uids = _dedupe(
            [current_page_uid]
            + [
                self.catalog.get_block(block_uid).page_uid
                for block_uid in selected_block_uids
                if block_uid in self.catalog.blocks
            ]
        )
        matches: list[SupportMatch] = []
        for entry in asset.lexicon_entries:
            score = _score_lexicon_entry(
                query=query,
                entry=entry,
                selected_block_uids=selected_block_uids,
                selected_page_uids=selected_page_uids,
            )
            if score > 0:
                matches.append(
                    SupportMatch(
                        entry_uid=entry.entry_uid,
                        entry_kind="lexicon",
                        english=entry.english,
                        chinese=entry.chinese,
                        phonetic=entry.phonetic,
                        page_refs=entry.page_refs,
                        linked_page_uids=entry.linked_page_uids,
                        linked_block_uids=entry.linked_block_uids,
                        score=score,
                    )
                )

        for entry in asset.expression_entries:
            score = _score_expression_entry(
                query=query,
                entry=entry,
                selected_block_uids=selected_block_uids,
                selected_page_uids=selected_page_uids,
            )
            if score > 0:
                matches.append(
                    SupportMatch(
                        entry_uid=entry.entry_uid,
                        entry_kind="expression",
                        english=entry.english,
                        chinese=entry.chinese,
                        page_refs=entry.page_refs,
                        linked_page_uids=entry.linked_page_uids,
                        linked_block_uids=entry.linked_block_uids,
                        score=score,
                    )
                )

        matches.sort(
            key=lambda item: (
                item.score,
                1 if item.entry_kind == "expression" else 0,
                len(item.linked_block_uids),
            ),
            reverse=True,
        )
        return matches[:limit]

    def has_assets(self) -> bool:
        return bool(self.assets_by_scope)

    def _load(self) -> None:
        for path in self.support_paths:
            if not path.exists():
                continue
            payload = SupportAssetFile.model_validate_json(path.read_text(encoding="utf-8"))
            key = (
                payload.scope.grade,
                payload.scope.semester,
                payload.scope.unit,
            )
            self.assets_by_scope[key] = payload


def _score_lexicon_entry(
    *,
    query: str,
    entry: LexiconEntryRecord,
    selected_block_uids: list[str],
    selected_page_uids: list[str],
) -> int:
    base_score = _base_score(query, entry.english, entry.chinese, exact_bonus=14, contains_bonus=10)
    if base_score <= 0:
        return 0
    return base_score + _scope_bonus(
        linked_block_uids=entry.linked_block_uids,
        linked_page_uids=entry.linked_page_uids,
        selected_block_uids=selected_block_uids,
        selected_page_uids=selected_page_uids,
    )


def _score_expression_entry(
    *,
    query: str,
    entry: ExpressionEntryRecord,
    selected_block_uids: list[str],
    selected_page_uids: list[str],
) -> int:
    base_score = _base_score(query, entry.english, entry.chinese, exact_bonus=18, contains_bonus=12)
    if base_score <= 0:
        return 0
    return base_score + _scope_bonus(
        linked_block_uids=entry.linked_block_uids,
        linked_page_uids=entry.linked_page_uids,
        selected_block_uids=selected_block_uids,
        selected_page_uids=selected_page_uids,
    )


def _base_score(
    query: str,
    english: str,
    chinese: str,
    *,
    exact_bonus: int,
    contains_bonus: int,
) -> int:
    normalized_query = _normalize(query)
    normalized_english = _normalize(english)
    normalized_chinese = _normalize(chinese)
    query_tokens = _tokenize(query)
    english_tokens = _tokenize(english)

    if not normalized_query or not normalized_english:
        return 0

    score = 0
    if normalized_query == normalized_english:
        score += exact_bonus
    elif normalized_english in normalized_query or normalized_query in normalized_english:
        score += contains_bonus

    overlap = query_tokens & english_tokens
    score += len(overlap) * 4

    if normalized_chinese and normalized_chinese in normalized_query:
        score += 4

    return score


def _scope_bonus(
    *,
    linked_block_uids: list[str],
    linked_page_uids: list[str],
    selected_block_uids: list[str],
    selected_page_uids: list[str],
) -> int:
    if set(linked_block_uids) & set(selected_block_uids):
        return 6
    if set(linked_page_uids) & set(selected_page_uids):
        return 3
    return 1 if linked_page_uids else 0


def _normalize(value: str) -> str:
    lowered = value.casefold()
    for source, replacement in _CONTRACTIONS.items():
        lowered = lowered.replace(source, replacement)
    cleaned = _NORMALIZE_RE.sub(" ", lowered)
    return " ".join(cleaned.split())


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in _normalize(value).split()
        if token and token not in _STOP_WORDS
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _resolve_support_paths() -> list[Path]:
    env_value = os.getenv("PEPTUTOR_SUPPORT_ASSET_PATH")
    if env_value:
        return [Path(part.strip()).resolve() for part in env_value.split(",") if part.strip()]

    current = Path(__file__).resolve()
    for ancestor in current.parents:
        support_dir = ancestor / "app/knowledge/structured/support"
        if support_dir.exists():
            return sorted(path.resolve() for path in support_dir.glob("*.json"))
    return []
