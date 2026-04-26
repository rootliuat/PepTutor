#!/usr/bin/env python3
"""Offline-ingest structured PepTutor general drafts into Qdrant."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lightrag.api.config import get_default_host
from lightrag.orchestrator.lesson_runtime import PilotLessonCatalog
from lightrag.orchestrator.qdrant_teaching_store import QdrantTeachingStore
from lightrag.orchestrator.teaching_block_index import build_unit_index_records
from lightrag.utils import EmbeddingFunc, get_env_value


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    manifest_path = (
        repo_root / "app" / "knowledge" / "structured" / "general" / "general-manifest.json"
    )
    report_path = (
        repo_root
        / "app"
        / "knowledge"
        / "structured"
        / "general"
        / "general-qdrant-ingest-report.json"
    )
    qdrant_location = _default_qdrant_location(repo_root)

    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    records = build_unit_index_records(catalog)
    embeddings = asyncio.run(
        _embed_texts(
            [record.embedding_text for record in records],
            batch_size=max(1, get_env_value("EMBEDDING_BATCH_NUM", 10, int)),
        )
    )
    store = QdrantTeachingStore(
        collection_name="peptutor_teaching_blocks",
        workspace=os.getenv("LIGHTRAG_WORKSPACE", "default"),
        client_kwargs=_qdrant_client_kwargs(qdrant_location),
    )
    store.reset_collection()
    store.upsert_records(records, embeddings)

    count = store.client.count(
        collection_name=store.collection_name,
        exact=True,
    ).count
    report_payload = {
        "kind": "peptutor_general_qdrant_ingest_report",
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest_path": manifest_path.relative_to(repo_root).as_posix(),
        "qdrant_location": str(qdrant_location),
        "collection_name": store.collection_name,
        "workspace": store.workspace,
        "record_count": len(records),
        "stored_point_count": count,
        "embedding": _embedding_report(),
    }
    report_path.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(qdrant_location)
    print(report_path)
    print(f"stored_point_count={count}")
    return 0


def _default_qdrant_location(repo_root: Path) -> Path:
    configured = os.getenv("PEPTUTOR_LESSON_QDRANT_LOCATION")
    if configured and configured != ":memory:":
        return Path(configured).expanduser().resolve()
    return (
        repo_root / "app" / "knowledge" / "structured" / "vector" / "qdrant"
    ).resolve()


def _qdrant_client_kwargs(qdrant_location: Path) -> dict[str, Any]:
    return {"path": str(qdrant_location)}


def _embedding_report() -> dict[str, Any]:
    return {
        "binding": get_env_value("EMBEDDING_BINDING", "ollama"),
        "model": get_env_value("EMBEDDING_MODEL", None, special_none=True),
        "host": get_env_value(
            "EMBEDDING_BINDING_HOST",
            get_default_host(get_env_value("EMBEDDING_BINDING", "ollama")),
        ),
        "embedding_dim": get_env_value("EMBEDDING_DIM", None, int, special_none=True),
    }


async def _embed_texts(texts: list[str], *, batch_size: int) -> list[list[float]]:
    binding = get_env_value("EMBEDDING_BINDING", "ollama")
    model = get_env_value("EMBEDDING_MODEL", None, special_none=True)
    host = get_env_value("EMBEDDING_BINDING_HOST", get_default_host(binding))
    api_key = get_env_value("EMBEDDING_BINDING_API_KEY", "")
    embedding_dim = get_env_value("EMBEDDING_DIM", None, int, special_none=True)

    vectors: list[list[float]] = []
    for offset in range(0, len(texts), batch_size):
        batch = texts[offset : offset + batch_size]
        raw_vectors = await _embed_batch(
            binding=binding,
            texts=batch,
            model=model,
            host=host,
            api_key=api_key,
            embedding_dim=embedding_dim,
        )
        if hasattr(raw_vectors, "tolist"):
            raw_vectors = raw_vectors.tolist()
        vectors.extend(
            [float(value) for value in vector]
            for vector in raw_vectors
        )
    return vectors


async def _embed_batch(
    *,
    binding: str,
    texts: list[str],
    model: str | None,
    host: str | None,
    api_key: str | None,
    embedding_dim: int | None,
):
    if binding == "openai":
        from lightrag.llm.openai import openai_embed

        actual_func = openai_embed.func if isinstance(openai_embed, EmbeddingFunc) else openai_embed
        kwargs: dict[str, Any] = {
            "texts": texts,
            "base_url": host,
            "api_key": api_key,
            "embedding_dim": embedding_dim,
        }
        if model:
            kwargs["model"] = model
        return await actual_func(**kwargs)

    if binding == "ollama":
        from lightrag.llm.ollama import ollama_embed

        actual_func = ollama_embed.func if isinstance(ollama_embed, EmbeddingFunc) else ollama_embed
        kwargs = {
            "texts": texts,
            "host": host,
            "api_key": api_key,
            "options": {},
        }
        if model:
            kwargs["embed_model"] = model
        return await actual_func(**kwargs)

    if binding == "jina":
        from lightrag.llm.jina import jina_embed

        actual_func = jina_embed.func if isinstance(jina_embed, EmbeddingFunc) else jina_embed
        kwargs = {
            "texts": texts,
            "base_url": host,
            "api_key": api_key,
            "embedding_dim": embedding_dim,
        }
        if model:
            kwargs["model"] = model
        return await actual_func(**kwargs)

    if binding == "gemini":
        from lightrag.llm.gemini import gemini_embed

        actual_func = gemini_embed.func if isinstance(gemini_embed, EmbeddingFunc) else gemini_embed
        kwargs = {
            "texts": texts,
            "base_url": host,
            "api_key": api_key,
            "embedding_dim": embedding_dim,
            "task_type": "RETRIEVAL_DOCUMENT",
        }
        if model:
            kwargs["model"] = model
        return await actual_func(**kwargs)

    if binding == "azure_openai":
        from lightrag.llm.azure_openai import azure_openai_embed

        actual_func = (
            azure_openai_embed.func
            if isinstance(azure_openai_embed, EmbeddingFunc)
            else azure_openai_embed
        )
        kwargs = {
            "texts": texts,
            "api_key": api_key,
            "embedding_dim": embedding_dim,
        }
        if model:
            kwargs["model"] = model
        return await actual_func(**kwargs)

    if binding == "aws_bedrock":
        from lightrag.llm.bedrock import bedrock_embed

        actual_func = bedrock_embed.func if isinstance(bedrock_embed, EmbeddingFunc) else bedrock_embed
        kwargs = {"texts": texts}
        if model:
            kwargs["model"] = model
        return await actual_func(**kwargs)

    if binding == "lollms":
        from lightrag.llm.lollms import lollms_embed

        actual_func = lollms_embed.func if isinstance(lollms_embed, EmbeddingFunc) else lollms_embed
        return await actual_func(texts, base_url=host, api_key=api_key)

    raise ValueError(f"Unsupported embedding binding for offline ingest: {binding}")


if __name__ == "__main__":
    raise SystemExit(main())
