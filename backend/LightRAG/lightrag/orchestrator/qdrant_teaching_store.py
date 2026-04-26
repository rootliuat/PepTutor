"""Qdrant-backed TeachingBlock store for PepTutor lesson retrieval."""

from __future__ import annotations

import time
import uuid
from typing import Any

from lightrag.orchestrator.lesson_retrieval import RetrievalSelection
from lightrag.orchestrator.lesson_state import LessonRuntimeState
from lightrag.orchestrator.teaching_block_index import IndexedTeachingBlock

WORKSPACE_ID_FIELD = "workspace_id"
ID_FIELD = "id"
CREATED_AT_FIELD = "created_at"
EMBEDDING_TEXT_FIELD = "embedding_text"
POINT_ID_NAMESPACE = uuid.UUID("2c7736f8-9079-4504-8fc0-7c17c3cf1c8c")


class QdrantTeachingStore:
    """Optional Qdrant adapter for indexed teaching blocks."""

    def __init__(
        self,
        *,
        collection_name: str = "peptutor_teaching_blocks",
        workspace: str = "default",
        client: Any | None = None,
        models_module: Any | None = None,
        client_kwargs: dict[str, Any] | None = None,
    ):
        self.collection_name = collection_name
        self.workspace = workspace
        self._client = client
        self._models = models_module
        self._client_kwargs = client_kwargs or {}

    @property
    def client(self):
        if self._client is None:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(**self._client_kwargs)
        return self._client

    @property
    def models(self):
        if self._models is None:
            from qdrant_client import models

            self._models = models
        return self._models

    def ensure_collection(self, vector_size: int) -> None:
        models = self.models
        client = self.client
        if not client.collection_exists(self.collection_name):
            client.create_collection(
                self.collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

        for field_name in (
            WORKSPACE_ID_FIELD,
            "grade",
            "semester",
            "unit",
            "page_uid",
            "block_uid",
            "page_type",
            "block_type",
            "branchable_topics",
        ):
            client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field_name,
                field_schema=models.KeywordIndexParams(
                    type=models.KeywordIndexType.KEYWORD,
                    is_tenant=(field_name == WORKSPACE_ID_FIELD),
                ),
            )

        client.create_payload_index(
            collection_name=self.collection_name,
            field_name="page",
            field_schema=models.IntegerIndexParams(
                type=models.IntegerIndexType.INTEGER,
            ),
        )

    def reset_collection(self) -> None:
        if self.client.collection_exists(self.collection_name):
            self.client.delete_collection(collection_name=self.collection_name)

    def upsert_records(
        self,
        records: list[IndexedTeachingBlock],
        embeddings: list[list[float]],
    ) -> None:
        if len(records) != len(embeddings):
            raise ValueError("records and embeddings must have the same length")
        if not records:
            return

        self.ensure_collection(len(embeddings[0]))
        models = self.models
        timestamp = int(time.time())
        points = []
        for record, vector in zip(records, embeddings, strict=True):
            payload = {
                ID_FIELD: record.point_id,
                WORKSPACE_ID_FIELD: self.workspace,
                CREATED_AT_FIELD: timestamp,
                EMBEDDING_TEXT_FIELD: record.embedding_text,
                **record.payload,
            }
            points.append(
                models.PointStruct(
                    id=self._make_point_id(record.point_id),
                    vector=vector,
                    payload=payload,
                )
            )

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )

    def build_query_filter(
        self,
        selection: RetrievalSelection,
        state: LessonRuntimeState,
    ):
        models = self.models
        must = [
            models.FieldCondition(
                key=WORKSPACE_ID_FIELD,
                match=models.MatchValue(value=self.workspace),
            )
        ]

        if selection.mode == "block":
            must.append(
                self._block_condition(selection.block_uids or [state.current_block_uid])
            )
        elif selection.mode == "page":
            must.append(
                models.FieldCondition(
                    key="page_uid",
                    match=models.MatchValue(value=state.current_page_uid),
                )
            )
        elif selection.mode == "unit":
            must.extend(
                [
                    models.FieldCondition(
                        key="grade",
                        match=models.MatchValue(value=state.current_grade),
                    ),
                    models.FieldCondition(
                        key="semester",
                        match=models.MatchValue(value=state.current_semester),
                    ),
                    models.FieldCondition(
                        key="unit",
                        match=models.MatchValue(value=state.current_unit),
                    ),
                ]
            )
        elif selection.mode == "branch" and selection.block_uids:
            must.append(self._block_condition(selection.block_uids))

        return models.Filter(must=must)

    def search(
        self,
        *,
        query_vector: list[float],
        selection: RetrievalSelection,
        state: LessonRuntimeState,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        points = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            with_payload=True,
            query_filter=self.build_query_filter(selection, state),
        ).points
        return [
            {
                **(point.payload or {}),
                "distance": point.score,
            }
            for point in points
        ]

    def _block_condition(self, block_uids: list[str | None]):
        models = self.models
        values = [value for value in block_uids if value]
        if len(values) == 1:
            return models.FieldCondition(
                key="block_uid",
                match=models.MatchValue(value=values[0]),
            )
        return models.FieldCondition(
            key="block_uid",
            match=models.MatchAny(any=values),
        )

    def _make_point_id(self, point_id: str) -> str:
        """Map business ids to stable UUIDs accepted by Qdrant."""
        return str(uuid.uuid5(POINT_ID_NAMESPACE, f"{self.workspace}:{point_id}"))
