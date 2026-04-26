"""Optional semantic memory bridge over SimpleMem-Cross LanceDB storage."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lightrag.utils import logger


def build_semantic_tenant_namespace(*, project: str, student_id: str) -> str:
    """Scope semantic memory by both project and learner without requiring schema changes."""

    normalized_project = project.strip() or "default"
    normalized_student = student_id.strip() or "default"
    return f"{normalized_project}::{normalized_student}"


class LessonSemanticMemoryEntry(BaseModel):
    """A lesson-memory record stored in the SimpleMem-compatible vector table."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str
    lossless_restatement: str
    keywords: list[str] = Field(default_factory=list)
    timestamp: str = ""
    location: str = ""
    persons: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    topic: str = ""
    tenant_id: str
    memory_session_id: str
    source_kind: str = "lesson_trace"
    source_id: int = 0
    importance: float = Field(default=0.7, ge=0.0, le=1.0)
    valid_from: str = ""
    valid_to: str = ""
    superseded_by: str = ""


class SemanticMemoryHit(BaseModel):
    """Compact semantic recall hit for prompt injection."""

    model_config = ConfigDict(extra="ignore")

    entry_id: str
    lossless_restatement: str
    keywords: list[str] = Field(default_factory=list)
    topic: str = ""
    tenant_id: str
    memory_session_id: str
    source_kind: str = ""
    importance: float = 0.0
    score: float | None = None


class SimpleMemLanceVectorStore:
    """Lightweight LanceDB access layer using the SimpleMem-Cross schema."""

    def __init__(
        self,
        *,
        db_path: str | Path,
        embed_texts,
        embedding_dim: int,
        table_name: str = "cross_memory_entries",
    ) -> None:
        self.db_path = str(Path(db_path).expanduser())
        self.embed_texts = embed_texts
        self.embedding_dim = embedding_dim
        self.table_name = table_name
        self._lancedb = self._import_module("lancedb")
        self._pa = self._import_module("pyarrow")
        if not self.db_path.startswith(("gs://", "s3://", "az://")):
            Path(self.db_path).mkdir(parents=True, exist_ok=True)
        self.db = self._lancedb.connect(self.db_path)
        self.table = self._init_table()

    def close(self) -> None:
        close_fn = getattr(self.db, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except Exception as exc:
                logger.warning("SimpleMem LanceDB close failed: %s", exc)

    def add_entries(self, entries: list[LessonSemanticMemoryEntry]) -> None:
        if not entries:
            return
        vectors = self.embed_texts([entry.lossless_restatement for entry in entries])
        data = []
        for entry, vector in zip(entries, vectors, strict=True):
            payload = entry.model_dump()
            payload["vector"] = vector
            data.append(payload)
        self.table.add(data)

    def semantic_search(
        self,
        *,
        query: str,
        tenant_id: str,
        top_k: int = 2,
        exclude_memory_session_ids: list[str] | None = None,
        source_kinds: list[str] | None = None,
    ) -> list[SemanticMemoryHit]:
        if not query.strip():
            return []
        if self.table.count_rows() == 0:
            return []
        query_vector = self.embed_texts([query])[0]
        search_query = self.table.search(query_vector)
        where_clause = self._build_where_clause(
            tenant_id=tenant_id,
            exclude_memory_session_ids=exclude_memory_session_ids or [],
            source_kinds=source_kinds or [],
        )
        if where_clause:
            search_query = search_query.where(where_clause, prefilter=True)
        raw_results = search_query.limit(top_k).to_list()
        hits: list[SemanticMemoryHit] = []
        for item in raw_results:
            payload = {
                "entry_id": str(item.get("entry_id", "")),
                "lossless_restatement": str(item.get("lossless_restatement", "")),
                "keywords": [str(value) for value in item.get("keywords", []) or []],
                "topic": str(item.get("topic", "")),
                "tenant_id": str(item.get("tenant_id", "")),
                "memory_session_id": str(item.get("memory_session_id", "")),
                "source_kind": str(item.get("source_kind", "")),
                "importance": float(item.get("importance", 0.0) or 0.0),
            }
            score = item.get("_distance")
            if score is not None:
                payload["score"] = float(score)
            hits.append(SemanticMemoryHit.model_validate(payload))
        return hits

    def _init_table(self):
        pa = self._pa
        schema = pa.schema(
            [
                pa.field("entry_id", pa.string()),
                pa.field("lossless_restatement", pa.string()),
                pa.field("keywords", pa.list_(pa.string())),
                pa.field("timestamp", pa.string()),
                pa.field("location", pa.string()),
                pa.field("persons", pa.list_(pa.string())),
                pa.field("entities", pa.list_(pa.string())),
                pa.field("topic", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.embedding_dim)),
                pa.field("tenant_id", pa.string()),
                pa.field("memory_session_id", pa.string()),
                pa.field("source_kind", pa.string()),
                pa.field("source_id", pa.int64()),
                pa.field("importance", pa.float32()),
                pa.field("valid_from", pa.string()),
                pa.field("valid_to", pa.string()),
                pa.field("superseded_by", pa.string()),
            ]
        )
        if self.table_name not in self.db.table_names():
            return self.db.create_table(self.table_name, schema=schema)
        return self.db.open_table(self.table_name)

    def _build_where_clause(
        self,
        *,
        tenant_id: str,
        exclude_memory_session_ids: list[str],
        source_kinds: list[str],
    ) -> str:
        clauses = [f"tenant_id = '{self._escape(tenant_id)}'"]
        clauses.append("(superseded_by = '' OR superseded_by IS NULL)")
        if exclude_memory_session_ids:
            excluded = ", ".join(
                f"'{self._escape(value)}'" for value in exclude_memory_session_ids if value
            )
            if excluded:
                clauses.append(f"memory_session_id NOT IN ({excluded})")
        if source_kinds:
            allowed = ", ".join(
                f"'{self._escape(value)}'" for value in source_kinds if value
            )
            if allowed:
                clauses.append(f"source_kind IN ({allowed})")
        return " AND ".join(clauses)

    def _escape(self, value: str) -> str:
        return value.replace("'", "''")

    def _import_module(self, name: str):
        try:
            return __import__(name)
        except Exception as exc:  # pragma: no cover - exercised via env builder warnings
            raise RuntimeError(f"Required module '{name}' is not available: {exc}") from exc


class SimpleMemSemanticRecallProvider:
    """Turn vector hits into a tiny prompt-safe semantic memory payload."""

    def __init__(
        self,
        semantic_store: SimpleMemLanceVectorStore,
        *,
        project: str,
        top_k: int = 2,
        max_items: int = 2,
    ) -> None:
        self.semantic_store = semantic_store
        self.project = project
        self.top_k = max(1, top_k)
        self.max_items = max(1, max_items)

    def recall(
        self,
        *,
        student_id: str,
        learner_input: str,
        state_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
        exclude_memory_session_id: str | None = None,
    ) -> list[str]:
        query = self._build_query(
            learner_input=learner_input,
            state_snapshot=state_snapshot,
            block_snapshot=block_snapshot,
        )
        hits = self.semantic_store.semantic_search(
            query=query,
            tenant_id=build_semantic_tenant_namespace(
                project=self.project,
                student_id=student_id,
            ),
            top_k=self.top_k,
            exclude_memory_session_ids=[exclude_memory_session_id]
            if exclude_memory_session_id
            else [],
            source_kinds=["lesson_trace"],
        )
        result: list[str] = []
        for hit in hits:
            text = hit.lossless_restatement.strip()
            if text and text not in result:
                result.append(text)
            if len(result) >= self.max_items:
                break
        return result

    def _build_query(
        self,
        *,
        learner_input: str,
        state_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
    ) -> str:
        parts = [learner_input.strip()]
        for value in (
            block_snapshot.get("teaching_goal"),
            block_snapshot.get("teaching_summary"),
            state_snapshot.get("current_page_uid"),
        ):
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        for key in ("focus_vocabulary", "core_patterns"):
            raw = block_snapshot.get(key) or []
            if isinstance(raw, list):
                parts.extend(str(item).strip() for item in raw[:2] if str(item).strip())
        return " ".join(parts)


def build_simplemem_lance_store_from_env(
    *,
    embed_texts,
    embedding_dim: int,
) -> SimpleMemLanceVectorStore | None:
    """Create the optional LanceDB semantic-memory store from env settings."""

    enabled = os.getenv("PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL")
    if enabled is None or enabled.strip().casefold() not in {"1", "true", "yes", "on"}:
        return None
    db_path = os.getenv("PEPTUTOR_SIMPLEMEM_LANCEDB_PATH")
    if not db_path:
        db_path = str(Path.home() / ".simplemem-cross" / "lancedb_cross")
    table_name = os.getenv("PEPTUTOR_SIMPLEMEM_LANCEDB_TABLE", "cross_memory_entries")
    try:
        return SimpleMemLanceVectorStore(
            db_path=db_path,
            embed_texts=embed_texts,
            embedding_dim=embedding_dim,
            table_name=table_name,
        )
    except Exception as exc:
        logger.warning("SimpleMem semantic recall disabled: %s", exc)
        return None
