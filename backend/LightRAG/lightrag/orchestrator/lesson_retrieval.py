"""Scoped retrieval helpers for the structured pilot catalog."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from lightrag.pedagogy.types import RetrievalMode

if TYPE_CHECKING:
    from lightrag.orchestrator.lesson_runtime import (
        PilotLessonCatalog,
        TeachingBlockRecord,
    )


def _normalize(value: str) -> str:
    lowered = value.casefold()
    cleaned = re.sub(r"[^a-z0-9\u4e00-\u9fff'\s]", " ", lowered)
    return " ".join(cleaned.split())


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
    "it",
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
}


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in _normalize(value).split()
        if token and token not in _STOP_WORDS
    }


def _looks_like_lexicon_query(query: str) -> bool:
    lower = query.casefold()
    return any(
        token in lower
        for token in ("what does", " meaning", " mean", "怎么说", "什么意思")
    )


class RetrievalSelection(BaseModel):
    """Structured retrieval decision for a single open turn."""

    model_config = ConfigDict(extra="forbid")

    mode: RetrievalMode
    block_uids: list[str] = Field(default_factory=list)
    return_anchor: str | None = None
    branch_reason: str | None = None


class ScopedRetriever:
    """Resolve block, page, unit, and branch scopes over structured pilot data."""

    def __init__(self, catalog: PilotLessonCatalog):
        self.catalog = catalog

    def select(
        self,
        *,
        current_page_uid: str,
        current_block_uid: str,
        query: str,
    ) -> RetrievalSelection:
        return self.select_mode(
            current_page_uid=current_page_uid,
            current_block_uid=current_block_uid,
            query=query,
            mode=None,
        )

    def select_mode(
        self,
        *,
        current_page_uid: str,
        current_block_uid: str,
        query: str,
        mode: RetrievalMode | None,
    ) -> RetrievalSelection:
        query_tokens = _tokenize(query)
        lexicon_query = _looks_like_lexicon_query(query)
        current_block = self.catalog.get_block(current_block_uid)
        if mode is not None:
            return self._select_for_mode(
                current_page_uid=current_page_uid,
                current_block=current_block,
                query_tokens=query_tokens,
                query=query,
                mode=mode,
            )
        if not query_tokens:
            return RetrievalSelection(mode="none")

        current_block_score = self._overlap_score(current_block, query_tokens)
        unit_blocks = self.catalog.blocks_for_unit(
            current_page_uid,
            exclude_page_uid=current_page_uid,
        )
        branch_hits = self._rank_branch_blocks(
            unit_blocks,
            query_tokens,
            current_page_uid=current_page_uid,
        )
        if branch_hits and not lexicon_query:
            top_branch = branch_hits[0]
            if self._branch_overlap_score(top_branch, query_tokens) > current_block_score:
                anchor = top_branch.return_anchors[0] if top_branch.return_anchors else None
                return RetrievalSelection(
                    mode="branch",
                    block_uids=[top_branch.block_uid],
                    return_anchor=anchor,
                    branch_reason="topic_extension",
                )

        if current_block_score > 0 and not lexicon_query:
            return RetrievalSelection(mode="block", block_uids=[current_block_uid])

        if branch_hits and not lexicon_query:
            top_block = branch_hits[0]
            anchor = top_block.return_anchors[0] if top_block.return_anchors else None
            return RetrievalSelection(
                mode="branch",
                block_uids=[top_block.block_uid],
                return_anchor=anchor,
                branch_reason="topic_extension",
            )

        unit_hits = self._rank_blocks(
            unit_blocks,
            query_tokens,
            current_page_uid=current_page_uid,
            lexicon_query=lexicon_query,
        )

        page_hits = self._rank_blocks(
            self.catalog.blocks_for_page(current_page_uid, exclude_block_uid=current_block_uid),
            query_tokens,
            current_page_uid=current_page_uid,
            lexicon_query=lexicon_query,
        )
        if lexicon_query:
            current_block_key = self._block_rank_key(
                current_block,
                query_tokens,
                current_page_uid=current_page_uid,
                index=-1,
                lexicon_query=True,
            )
            best_mode, best_hits, best_key = self._best_ranked_scope(
                page_hits=page_hits,
                unit_hits=unit_hits,
                query_tokens=query_tokens,
                current_page_uid=current_page_uid,
            )
            if current_block_key is not None and (
                best_key is None or current_block_key <= best_key
            ):
                return RetrievalSelection(mode="block", block_uids=[current_block_uid])
            if best_mode is not None:
                return RetrievalSelection(
                    mode=best_mode,
                    block_uids=[block.block_uid for block in best_hits[:2]],
                )
        if page_hits:
            return RetrievalSelection(
                mode="page",
                block_uids=[block.block_uid for block in page_hits[:2]],
            )

        if unit_hits:
            return RetrievalSelection(
                mode="unit",
                block_uids=[block.block_uid for block in unit_hits[:2]],
            )

        return RetrievalSelection(mode="block", block_uids=[current_block_uid])

    def _select_for_mode(
        self,
        *,
        current_page_uid: str,
        current_block,
        query_tokens: set[str],
        query: str,
        mode: RetrievalMode,
    ) -> RetrievalSelection:
        if mode == "none":
            return RetrievalSelection(mode="none")
        if mode == "block":
            return RetrievalSelection(mode="block", block_uids=[current_block.block_uid])
        if mode == "page":
            page_blocks = self.catalog.blocks_for_page(
                current_page_uid,
                exclude_block_uid=current_block.block_uid,
            )
            ranked = self._rank_blocks(
                page_blocks,
                query_tokens,
                current_page_uid=current_page_uid,
                lexicon_query=_looks_like_lexicon_query(query),
            ) or list(page_blocks)
            return RetrievalSelection(
                mode="page",
                block_uids=[block.block_uid for block in ranked[:2]],
            )
        if mode == "unit":
            unit_blocks = self.catalog.blocks_for_unit(
                current_page_uid,
                exclude_page_uid=current_page_uid,
            )
            ranked = self._rank_blocks(
                unit_blocks,
                query_tokens,
                current_page_uid=current_page_uid,
                lexicon_query=_looks_like_lexicon_query(query),
            ) or list(unit_blocks)
            return RetrievalSelection(
                mode="unit",
                block_uids=[block.block_uid for block in ranked[:2]],
            )

        unit_blocks = self.catalog.blocks_for_unit(
            current_page_uid,
            exclude_page_uid=current_page_uid,
        )
        if _looks_like_lexicon_query(query):
            ranked = self._rank_blocks(
                unit_blocks,
                query_tokens,
                current_page_uid=current_page_uid,
                lexicon_query=True,
            )
            if ranked:
                return RetrievalSelection(
                    mode="unit",
                    block_uids=[block.block_uid for block in ranked[:2]],
                )
            return RetrievalSelection(mode="block", block_uids=[current_block.block_uid])
        branch_hits = self._rank_branch_blocks(
            unit_blocks,
            query_tokens,
            current_page_uid=current_page_uid,
        )
        fallback_hits = branch_hits or self._rank_blocks(
            unit_blocks,
            query_tokens,
            current_page_uid=current_page_uid,
        ) or list(
            unit_blocks
        )
        top_block = fallback_hits[0] if fallback_hits else None
        anchor = None
        if top_block and top_block.return_anchors:
            anchor = top_block.return_anchors[0]
        elif current_block.return_anchors:
            anchor = current_block.return_anchors[0]
        return RetrievalSelection(
            mode="branch",
            block_uids=[top_block.block_uid] if top_block else [],
            return_anchor=anchor,
            branch_reason="topic_extension",
        )

    def _rank_blocks(
        self,
        blocks: Iterable[TeachingBlockRecord],
        query_tokens: set[str],
        *,
        current_page_uid: str,
        lexicon_query: bool = False,
    ) -> list[TeachingBlockRecord]:
        scored = []
        for index, block in enumerate(blocks):
            rank_key = self._block_rank_key(
                block,
                query_tokens,
                current_page_uid=current_page_uid,
                index=index,
                lexicon_query=lexicon_query,
            )
            if rank_key is not None:
                scored.append((*rank_key, block))
        scored.sort()
        return [block for _, _, _, _, block in scored]

    def _best_ranked_scope(
        self,
        *,
        page_hits: list[TeachingBlockRecord],
        unit_hits: list[TeachingBlockRecord],
        query_tokens: set[str],
        current_page_uid: str,
    ) -> tuple[RetrievalMode | None, list[TeachingBlockRecord], tuple[int, int, int, int] | None]:
        best_mode: RetrievalMode | None = None
        best_hits: list[TeachingBlockRecord] = []
        best_key: tuple[int, int, int, int] | None = None
        for mode, hits in (("page", page_hits), ("unit", unit_hits)):
            if not hits:
                continue
            rank_key = self._block_rank_key(
                hits[0],
                query_tokens,
                current_page_uid=current_page_uid,
                index=0,
                lexicon_query=True,
            )
            if rank_key is None:
                continue
            if best_key is None or rank_key < best_key:
                best_mode = mode
                best_hits = hits
                best_key = rank_key
        return best_mode, best_hits, best_key

    def _rank_branch_blocks(
        self,
        blocks: Iterable[TeachingBlockRecord],
        query_tokens: set[str],
        *,
        current_page_uid: str,
    ) -> list[TeachingBlockRecord]:
        scored = []
        for index, block in enumerate(blocks):
            score = self._branch_overlap_score(block, query_tokens)
            if score > 0:
                scored.append(
                    (
                        -score,
                        self._page_distance(current_page_uid, block.page_uid),
                        index,
                        block,
                    )
                )
        scored.sort()
        return [block for _, _, _, block in scored]

    def _branch_overlap_score(
        self,
        block: TeachingBlockRecord,
        query_tokens: set[str],
    ) -> int:
        topics = " ".join(block.branchable_topics)
        return len(_tokenize(topics) & query_tokens)

    def _block_rank_key(
        self,
        block: TeachingBlockRecord,
        query_tokens: set[str],
        *,
        current_page_uid: str,
        index: int,
        lexicon_query: bool,
    ) -> tuple[int, int, int, int] | None:
        score = self._overlap_score(block, query_tokens)
        if score <= 0:
            return None
        block_type_rank = self._lexicon_block_type_rank(block) if lexicon_query else 0
        return (
            -score,
            block_type_rank,
            self._page_distance(current_page_uid, block.page_uid),
            index,
        )

    def _overlap_score(
        self,
        block: TeachingBlockRecord,
        query_tokens: set[str],
    ) -> int:
        haystack = " ".join(
            [
                block.teaching_goal,
                block.teaching_summary,
                *block.focus_vocabulary,
                *block.core_patterns,
                block.block_type,
            ]
        )
        return len(_tokenize(haystack) & query_tokens)

    def _lexicon_block_type_rank(self, block: TeachingBlockRecord) -> int:
        order = {
            "vocabulary_core": 0,
            "dialogue_core": 1,
            "dialogue_practice": 2,
            "practice_matching": 3,
            "practice_fill_blank": 4,
            "reading_passage": 5,
            "extension_task": 6,
            "picture_scene": 7,
        }
        return order.get(block.block_type, 99)

    def _page_distance(self, current_page_uid: str, candidate_page_uid: str) -> int:
        return abs(
            self._extract_page_number(candidate_page_uid)
            - self._extract_page_number(current_page_uid)
        )

    def _extract_page_number(self, page_uid: str) -> int:
        if "-P" not in page_uid:
            return 0
        suffix = page_uid.rsplit("-P", 1)[1]
        head = suffix.split("-", 1)[0]
        try:
            return int(head)
        except ValueError:
            return 0
