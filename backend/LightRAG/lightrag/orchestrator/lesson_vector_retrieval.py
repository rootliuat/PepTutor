"""Optional Qdrant-backed retrieval reranking for lesson knowledge turns."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lightrag.orchestrator.lesson_retrieval import RetrievalSelection, ScopedRetriever
from lightrag.orchestrator.lesson_state import LessonRuntimeState
from lightrag.orchestrator.qdrant_teaching_store import QdrantTeachingStore
from lightrag.orchestrator.teaching_block_index import build_unit_index_records
from lightrag.pedagogy.types import RetrievalMode


class QdrantLessonRetriever:
    """Use deterministic scope selection, then rerank within that scope via Qdrant."""

    def __init__(
        self,
        *,
        catalog,
        store: QdrantTeachingStore,
        embed_texts: Callable[[list[str]], Any],
        embedding_batch_size: int = 10,
    ):
        self.catalog = catalog
        self.scope_retriever = ScopedRetriever(catalog)
        self.store = store
        self.embed_texts = embed_texts
        self.embedding_batch_size = max(1, embedding_batch_size)
        self._indexed = False

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
        selection = self.scope_retriever.select_mode(
            current_page_uid=current_page_uid,
            current_block_uid=current_block_uid,
            query=query,
            mode=mode,
        )
        if selection.mode == "none":
            return selection

        self.ensure_indexed()
        query_vector = self._embed_one(query)
        results = self.store.search(
            query_vector=query_vector,
            selection=selection,
            state=self._build_state(
                current_page_uid=current_page_uid,
                current_block_uid=current_block_uid,
            ),
            limit=self._result_limit(selection),
        )
        block_uids = [
            block_uid
            for item in results
            if (block_uid := item.get("block_uid"))
        ]
        if not block_uids:
            return selection
        return selection.model_copy(update={"block_uids": block_uids})

    def ensure_indexed(self) -> None:
        if self._indexed:
            return

        records = build_unit_index_records(self.catalog)
        embeddings = self._embed_many([record.embedding_text for record in records])
        self.store.upsert_records(records, embeddings)
        self._indexed = True

    def _build_state(
        self,
        *,
        current_page_uid: str,
        current_block_uid: str,
    ) -> LessonRuntimeState:
        page = self.catalog.get_page(current_page_uid)
        scope = self.catalog.get_scope_for_page(current_page_uid)
        return LessonRuntimeState(
            student_id="vector-retrieval",
            current_grade=scope.grade,
            current_semester=scope.semester,
            current_unit=scope.unit,
            current_page=self._extract_page_number(current_page_uid),
            current_page_uid=current_page_uid,
            current_page_type=page.page_type,
            current_block_uid=current_block_uid,
        )

    def _extract_page_number(self, page_uid: str) -> int:
        suffix = page_uid.rsplit("-P", 1)[1]
        return int(suffix.split("-", 1)[0])

    def _result_limit(self, selection: RetrievalSelection) -> int:
        if selection.mode in {"block", "branch"}:
            return max(len(selection.block_uids), 1)
        return max(len(selection.block_uids), 3)

    def _embed_one(self, text: str) -> list[float]:
        vectors = self._embed_many([text])
        return vectors[0]

    def _embed_many(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for offset in range(0, len(texts), self.embedding_batch_size):
            batch = texts[offset : offset + self.embedding_batch_size]
            raw_vectors = self.embed_texts(batch)
            if hasattr(raw_vectors, "tolist"):
                raw_vectors = raw_vectors.tolist()
            vectors.extend(
                [float(value) for value in vector]
                for vector in raw_vectors
            )
        return vectors
