"""Build a lesson runtime with optional Qdrant-backed retrieval."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from queue import Queue
from threading import Event, Thread
from typing import Any, Literal

from lightrag.pedagogy.planner import LessonPlanner
from lightrag.pedagogy.responder import LessonResponder
from lightrag.orchestrator.lesson_readiness_judge import ReadinessJudge
from lightrag.orchestrator.lesson_runtime import LessonRuntime, PilotLessonCatalog
from lightrag.orchestrator.lesson_llm_metering import (
    default_lesson_llm_model,
    record_lesson_llm_call,
)
from lightrag.orchestrator.simplemem_prompt_memory import (
    SimpleMemSQLitePromptMemoryProvider,
)
from lightrag.orchestrator.simplemem_semantic_memory import (
    SimpleMemSemanticRecallProvider,
    SimpleMemLanceVectorStore,
)
from lightrag.orchestrator.simplemem_writeback import (
    SimpleMemSQLiteLessonMemoryWriter,
)
from lightrag.orchestrator.support_asset_retrieval import SupportAssetRetriever
from lightrag.orchestrator.lesson_vector_retrieval import QdrantLessonRetriever
from lightrag.orchestrator.qdrant_teaching_store import QdrantTeachingStore
from lightrag.utils import EmbeddingFunc, logger


def _resolve_lesson_manifest_path(manifest_path: Path | None = None) -> Path:
    if manifest_path is not None:
        return manifest_path.expanduser().resolve()

    env_path = os.getenv("PEPTUTOR_LESSON_MANIFEST") or os.getenv(
        "PEPTUTOR_PILOT_MANIFEST"
    )
    if env_path:
        return Path(env_path).expanduser().resolve()

    current = Path(__file__).resolve()
    for ancestor in current.parents:
        overlay_candidate = (
            ancestor
            / "app"
            / "knowledge"
            / "structured"
            / "general"
            / "general-with-pilot-overrides-manifest.json"
        )
        if overlay_candidate.exists():
            return overlay_candidate.resolve()

        general_candidate = (
            ancestor / "app" / "knowledge" / "structured" / "general" / "general-manifest.json"
        )
        if general_candidate.exists():
            return general_candidate.resolve()

        pilot_candidate = ancestor / "app" / "knowledge" / "structured" / "g5s1u3-pilot-manifest.json"
        if pilot_candidate.exists():
            return pilot_candidate.resolve()

    raise FileNotFoundError(
        "Unable to locate a lesson manifest. Set PEPTUTOR_LESSON_MANIFEST to a valid manifest path."
    )


def _is_enabled(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _is_disabled(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().casefold() in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class FeatureStatus:
    enabled: bool
    mode: Literal["auto", "explicit", "disabled"]
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("FeatureStatus reason must be non-empty")


@dataclass(frozen=True)
class _FeatureRequest:
    requested: bool | None
    mode: Literal["auto", "explicit", "disabled"]
    reason: str


def _strip_internal_runtime_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Remove internal scheduler hints before calling external model clients."""
    return {
        key: value
        for key, value in kwargs.items()
        if key not in {"_priority", "_lesson_audit_tag"}
    }


def _lesson_audit_tag(kwargs: dict[str, Any]) -> str:
    value = kwargs.get("_lesson_audit_tag")
    return value.strip() if isinstance(value, str) and value.strip() else "unknown"


def _sha256_prefix(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]


def _log_lesson_llm_start(
    *,
    call_id: str,
    mode: Literal["complete", "stream"],
    audit_tag: str,
    llm_provider: str,
    prompt: str,
    system_prompt: str | None,
    history_messages: list[dict[str, Any]] | None,
    call_kwargs: dict[str, Any],
    llm_model: str,
) -> None:
    logger.info(
        "Lesson LLM audit start call_id=%s mode=%s tag=%s llmcalled=true llmprovider=%s llmmodel=%s prompt_chars=%d system_chars=%d history_messages=%d prompt_sha256=%s system_sha256=%s kwargs=%s",
        call_id,
        mode,
        audit_tag,
        llm_provider,
        llm_model,
        len(prompt),
        len(system_prompt or ""),
        len(history_messages or []),
        _sha256_prefix(prompt),
        _sha256_prefix(system_prompt),
        sorted(call_kwargs.keys()),
    )


def _log_lesson_llm_end(
    *,
    call_id: str,
    mode: Literal["complete", "stream"],
    audit_tag: str,
    llm_provider: str,
    llm_model: str,
    started_at: float,
    status: Literal["success", "error"],
    response_chars: int = 0,
    chunk_count: int = 0,
    error: BaseException | None = None,
) -> None:
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    if status == "error":
        logger.warning(
            "Lesson LLM audit end call_id=%s mode=%s tag=%s llmcalled=true llmprovider=%s llmmodel=%s status=error latencyms=%d fallbackused=true fallbackreason=llm_exception teacherresponse_source=fallback error=%s",
            call_id,
            mode,
            audit_tag,
            llm_provider,
            llm_model,
            duration_ms,
            error,
        )
        return

    logger.info(
        "Lesson LLM audit end call_id=%s mode=%s tag=%s llmcalled=true llmprovider=%s llmmodel=%s status=success latencyms=%d fallbackused=false fallbackreason=none teacherresponse_source=llm response_chars=%d chunk_count=%d",
        call_id,
        mode,
        audit_tag,
        llm_provider,
        llm_model,
        duration_ms,
        response_chars,
        chunk_count,
    )


class EmbeddingLoopRunner:
    """Run async embedding calls on a dedicated background loop."""

    def __init__(self, embedding_func: EmbeddingFunc):
        self.embedding_func = embedding_func
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: Thread | None = None
        self._started = Event()
        self._closed = False

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        loop = self._ensure_loop()
        call_kwargs = _strip_internal_runtime_kwargs({"_priority": 5})
        future = asyncio.run_coroutine_threadsafe(
            self.embedding_func(texts, **call_kwargs),
            loop,
        )
        raw_vectors = future.result()
        if hasattr(raw_vectors, "tolist"):
            raw_vectors = raw_vectors.tolist()
        return [[float(value) for value in vector] for vector in raw_vectors]

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None:
            return self._loop

        def _run_loop() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._started.set()
            loop.run_forever()
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.close()

        self._thread = Thread(target=_run_loop, name="lesson-embedding-loop", daemon=True)
        self._thread.start()
        self._started.wait(timeout=5)
        if self._loop is None:
            raise RuntimeError("Failed to start lesson embedding loop")
        return self._loop


class LLMCallLoopRunner:
    """Run async lesson prompt calls on a dedicated background loop."""

    def __init__(
        self,
        llm_model_func: Callable[..., Any],
        *,
        llm_provider: str = "unknown",
        llm_model: str = "unknown",
    ):
        self.llm_model_func = llm_model_func
        self.llm_provider = llm_provider
        self.llm_model = llm_model or default_lesson_llm_model()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: Thread | None = None
        self._started = Event()
        self._closed = False

    def complete_text(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        history_messages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> str:
        loop = self._ensure_loop()
        audit_tag = _lesson_audit_tag(kwargs)
        call_kwargs = _strip_internal_runtime_kwargs(
            {
                "_priority": 5,
                **kwargs,
            }
        )
        call_id = f"lesson-llm-{time.time_ns()}"
        started_at = time.perf_counter()
        _log_lesson_llm_start(
            call_id=call_id,
            mode="complete",
            audit_tag=audit_tag,
            llm_provider=self.llm_provider,
            prompt=prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            call_kwargs=call_kwargs,
            llm_model=self.llm_model,
        )
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.llm_model_func(
                    prompt,
                    system_prompt=system_prompt,
                    history_messages=history_messages or [],
                    **call_kwargs,
                ),
                loop,
            )
            result = future.result()
            if not isinstance(result, str):
                raise TypeError("Lesson prompt model returned a non-text response")
            _log_lesson_llm_end(
                call_id=call_id,
                mode="complete",
                audit_tag=audit_tag,
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
                started_at=started_at,
                status="success",
                response_chars=len(result),
            )
            record_lesson_llm_call(
                prompt=prompt,
                completion=result,
                system_prompt=system_prompt,
                history_messages=history_messages,
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
                audit_tag=audit_tag,
                mode="complete",
                status="success",
                call_id=call_id,
            )
            return result
        except BaseException as exc:
            record_lesson_llm_call(
                prompt=prompt,
                completion="",
                system_prompt=system_prompt,
                history_messages=history_messages,
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
                audit_tag=audit_tag,
                mode="complete",
                status="error",
                call_id=call_id,
            )
            _log_lesson_llm_end(
                call_id=call_id,
                mode="complete",
                audit_tag=audit_tag,
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
                started_at=started_at,
                status="error",
                error=exc,
            )
            raise

    def stream_text(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        history_messages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ):
        loop = self._ensure_loop()
        output_queue: Queue[str | BaseException | object] = Queue()
        sentinel = object()
        audit_tag = _lesson_audit_tag(kwargs)
        call_kwargs = _strip_internal_runtime_kwargs(
            {
                "_priority": 5,
                "stream": True,
                **kwargs,
            }
        )
        call_id = f"lesson-llm-{time.time_ns()}"
        started_at = time.perf_counter()
        response_chars = 0
        chunk_count = 0
        chunks_for_metering: list[str] = []
        _log_lesson_llm_start(
            call_id=call_id,
            mode="stream",
            audit_tag=audit_tag,
            llm_provider=self.llm_provider,
            prompt=prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            call_kwargs=call_kwargs,
            llm_model=self.llm_model,
        )

        async def _run_stream() -> None:
            try:
                result = await self.llm_model_func(
                    prompt,
                    system_prompt=system_prompt,
                    history_messages=history_messages or [],
                    **call_kwargs,
                )
                if isinstance(result, str):
                    output_queue.put(result)
                    return
                if hasattr(result, "__aiter__"):
                    async for chunk in result:
                        text = self._stream_chunk_to_text(chunk)
                        if text:
                            output_queue.put(text)
                    return
                try:
                    iterator = iter(result)
                except TypeError:
                    text = self._stream_chunk_to_text(result)
                    if text:
                        output_queue.put(text)
                    return
                for chunk in iterator:
                    text = self._stream_chunk_to_text(chunk)
                    if text:
                        output_queue.put(text)
            except BaseException as exc:
                output_queue.put(exc)
            finally:
                output_queue.put(sentinel)

        asyncio.run_coroutine_threadsafe(_run_stream(), loop)
        while True:
            item = output_queue.get()
            if item is sentinel:
                _log_lesson_llm_end(
                    call_id=call_id,
                    mode="stream",
                    audit_tag=audit_tag,
                    llm_provider=self.llm_provider,
                    llm_model=self.llm_model,
                    started_at=started_at,
                    status="success",
                    response_chars=response_chars,
                    chunk_count=chunk_count,
                )
                record_lesson_llm_call(
                    prompt=prompt,
                    completion="".join(chunks_for_metering),
                    system_prompt=system_prompt,
                    history_messages=history_messages,
                    llm_provider=self.llm_provider,
                    llm_model=self.llm_model,
                    audit_tag=audit_tag,
                    mode="stream",
                    status="success",
                    call_id=call_id,
                )
                break
            if isinstance(item, BaseException):
                record_lesson_llm_call(
                    prompt=prompt,
                    completion="".join(chunks_for_metering),
                    system_prompt=system_prompt,
                    history_messages=history_messages,
                    llm_provider=self.llm_provider,
                    llm_model=self.llm_model,
                    audit_tag=audit_tag,
                    mode="stream",
                    status="error",
                    call_id=call_id,
                )
                _log_lesson_llm_end(
                    call_id=call_id,
                    mode="stream",
                    audit_tag=audit_tag,
                    llm_provider=self.llm_provider,
                    llm_model=self.llm_model,
                    started_at=started_at,
                    status="error",
                    error=item,
                )
                raise item
            response_chars += len(item)
            chunk_count += 1
            chunks_for_metering.append(item)
            yield item

    @staticmethod
    def _stream_chunk_to_text(chunk: Any) -> str:
        if isinstance(chunk, str):
            return chunk
        if isinstance(chunk, bytes):
            return chunk.decode("utf-8", errors="ignore")
        if isinstance(chunk, dict):
            for key in ("text", "content", "delta"):
                value = chunk.get(key)
                if isinstance(value, str):
                    return value
            choices = chunk.get("choices")
            if isinstance(choices, list) and choices:
                delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
                if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                    return delta["content"]
        text = getattr(chunk, "text", None)
        if isinstance(text, str):
            return text
        return ""

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None:
            return self._loop

        def _run_loop() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._started.set()
            loop.run_forever()
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.close()

        self._thread = Thread(target=_run_loop, name="lesson-llm-loop", daemon=True)
        self._thread.start()
        self._started.wait(timeout=5)
        if self._loop is None:
            raise RuntimeError("Failed to start lesson LLM loop")
        return self._loop


@dataclass
class LessonRuntimeBundle:
    runtime: LessonRuntime
    close: Callable[[], None] | None = None
    feature_statuses: dict[str, FeatureStatus] = field(default_factory=dict)


def _resolve_simplemem_cross_db_path() -> Path:
    env_value = os.getenv("PEPTUTOR_SIMPLEMEM_CROSS_DB_PATH")
    if env_value:
        return Path(env_value).expanduser()
    return Path.home() / ".simplemem-cross" / "cross_memory.db"


def _resolve_simplemem_project() -> str:
    return os.getenv("PEPTUTOR_SIMPLEMEM_PROJECT", "peptutor-lesson")


def _resolve_simplemem_lancedb_path() -> str:
    return os.getenv("PEPTUTOR_SIMPLEMEM_LANCEDB_PATH") or str(
        Path.home() / ".simplemem-cross" / "lancedb_cross"
    )


def _resolve_feature_request(
    *,
    feature_name: str,
    env_var: str,
    explicit_value: bool | None = None,
    argument_name: str | None = None,
) -> _FeatureRequest:
    if explicit_value is not None:
        if explicit_value:
            source = argument_name or "argument"
            return _FeatureRequest(
                requested=True,
                mode="explicit",
                reason=f"{feature_name} explicitly enabled via {source}",
            )
        source = argument_name or "argument"
        return _FeatureRequest(
            requested=False,
            mode="disabled",
            reason=f"{feature_name} explicitly disabled via {source}",
        )

    raw_value = os.getenv(env_var)
    if raw_value is None:
        return _FeatureRequest(
            requested=None,
            mode="auto",
            reason=f"{feature_name} auto-detection engaged because {env_var} is unset",
        )
    if _is_enabled(raw_value):
        return _FeatureRequest(
            requested=True,
            mode="explicit",
            reason=f"{feature_name} explicitly enabled via {env_var}",
        )
    if _is_disabled(raw_value):
        return _FeatureRequest(
            requested=False,
            mode="disabled",
            reason=f"{feature_name} explicitly disabled via {env_var}",
        )
    return _FeatureRequest(
        requested=False,
        mode="disabled",
        reason=f"{feature_name} disabled because {env_var} has an unrecognized value {raw_value!r}",
    )


def _enabled_feature_status(
    request: _FeatureRequest,
    reason: str,
) -> FeatureStatus:
    return FeatureStatus(enabled=True, mode=request.mode, reason=reason)


def _disabled_feature_status(
    request: _FeatureRequest,
    reason: str,
) -> FeatureStatus:
    mode = request.mode
    if mode == "disabled":
        return FeatureStatus(enabled=False, mode=mode, reason=reason)
    return FeatureStatus(enabled=False, mode=mode, reason=reason)


def _record_feature_status(
    feature_statuses: dict[str, FeatureStatus],
    feature_key: str,
    feature_name: str,
    status: FeatureStatus,
) -> None:
    _ = feature_name
    feature_statuses[feature_key] = status


def _feature_status_log_order(feature_statuses: dict[str, FeatureStatus]) -> list[str]:
    preferred_order = [
        "support_assets",
        "live_prompts",
        "semantic_recall",
        "prompt_injection",
        "writeback",
        "vector_retrieval",
    ]
    remaining = [key for key in feature_statuses if key not in preferred_order]
    return [*preferred_order, *remaining]


def _format_feature_status_summary(feature_statuses: dict[str, FeatureStatus]) -> str:
    lines = ["Lesson feature status summary:"]
    for feature_key in _feature_status_log_order(feature_statuses):
        status = feature_statuses.get(feature_key)
        if status is None:
            continue
        state_label = "ENABLED" if status.enabled else "DOWNGRADED"
        lines.append(
            f"- {feature_key}: {state_label} [{status.mode}] {status.reason}"
        )
    return "\n".join(lines)


def _build_simplemem_semantic_store(
    *,
    embed_texts,
    embedding_dim: int,
) -> tuple[SimpleMemLanceVectorStore | None, str]:
    db_path = _resolve_simplemem_lancedb_path()
    table_name = os.getenv("PEPTUTOR_SIMPLEMEM_LANCEDB_TABLE", "cross_memory_entries")
    try:
        store = SimpleMemLanceVectorStore(
            db_path=db_path,
            embed_texts=embed_texts,
            embedding_dim=embedding_dim,
            table_name=table_name,
        )
    except Exception as exc:
        return None, f"SimpleMem semantic store unavailable: {exc}"
    return store, f"SimpleMem semantic store ready at {db_path}"


def _build_simplemem_writeback_adapter(
    *,
    semantic_store: SimpleMemLanceVectorStore | None = None,
) -> tuple[SimpleMemSQLiteLessonMemoryWriter | None, str]:
    db_path = _resolve_simplemem_cross_db_path()
    project = _resolve_simplemem_project()
    try:
        writer = SimpleMemSQLiteLessonMemoryWriter(
            db_path=db_path,
            project=project,
            semantic_store=semantic_store,
        )
    except Exception as exc:
        return None, f"SimpleMem writeback unavailable: {exc}"
    return writer, f"SimpleMem writeback ready at {writer.db_path}"


def _build_simplemem_prompt_memory_provider(
    *,
    semantic_recall_provider: SimpleMemSemanticRecallProvider | None = None,
) -> tuple[SimpleMemSQLitePromptMemoryProvider | None, str]:
    db_path = _resolve_simplemem_cross_db_path()
    project = _resolve_simplemem_project()
    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project=project,
        max_summaries=int(os.getenv("PEPTUTOR_SIMPLEMEM_MAX_SUMMARIES", "4")),
        max_observations=int(os.getenv("PEPTUTOR_SIMPLEMEM_MAX_OBSERVATIONS", "8")),
        category_limit=int(os.getenv("PEPTUTOR_SIMPLEMEM_CATEGORY_LIMIT", "2")),
        semantic_recall_provider=semantic_recall_provider,
    )
    if not provider.db_path.exists():
        return None, f"SimpleMem prompt injection unavailable because SQLite DB was not found: {provider.db_path}"
    return provider, f"SimpleMem prompt injection ready from {provider.db_path}"


def _resolve_qdrant_client_kwargs() -> dict[str, Any]:
    location = os.getenv("PEPTUTOR_LESSON_QDRANT_LOCATION")
    if location:
        if location == ":memory:":
            return {"location": location}
        return {"path": location}

    url = os.getenv("PEPTUTOR_LESSON_QDRANT_URL") or os.getenv("QDRANT_URL")
    if not url:
        return {}

    kwargs: dict[str, Any] = {"url": url}
    api_key = os.getenv("PEPTUTOR_LESSON_QDRANT_API_KEY") or os.getenv("QDRANT_API_KEY")
    if api_key:
        kwargs["api_key"] = api_key
    return kwargs


def _compose_close_callbacks(callbacks: list[Callable[[], None]]) -> Callable[[], None] | None:
    callbacks = [callback for callback in callbacks if callback is not None]
    if not callbacks:
        return None

    def _close_all() -> None:
        for callback in reversed(callbacks):
            try:
                callback()
            except Exception as exc:
                logger.warning("Lesson runtime cleanup failed: %s", exc)

    return _close_all


def build_lesson_runtime(
    *,
    workspace: str = "",
    embedding_func: EmbeddingFunc | None = None,
    llm_model_func: Callable[..., Any] | None = None,
    llm_model_kwargs: dict[str, Any] | None = None,
    llm_hashing_kv: Any | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    manifest_path: Path | None = None,
    vector_enabled: bool | None = None,
    live_prompts_enabled: bool | None = None,
    semantic_recall_enabled: bool | None = None,
    prompt_injection_enabled: bool | None = None,
    writeback_enabled: bool | None = None,
    qdrant_client_kwargs: dict[str, Any] | None = None,
    collection_name: str | None = None,
) -> LessonRuntimeBundle:
    """Build lesson runtime and optionally enable Qdrant-backed scoped reranking."""
    resolved_manifest_path = _resolve_lesson_manifest_path(manifest_path)
    catalog = PilotLessonCatalog(manifest_path=resolved_manifest_path)
    logger.info("Lesson catalog loaded from %s", resolved_manifest_path)
    close_callbacks: list[Callable[[], None]] = []
    feature_statuses: dict[str, FeatureStatus] = {}

    def _bundle(runtime: LessonRuntime) -> LessonRuntimeBundle:
        logger.info("%s", _format_feature_status_summary(feature_statuses))
        return LessonRuntimeBundle(
            runtime=runtime,
            close=_compose_close_callbacks(close_callbacks),
            feature_statuses=dict(feature_statuses),
        )

    embedding_runner: EmbeddingLoopRunner | None = None
    embedding_runner_registered = False

    def _ensure_embedding_runner() -> EmbeddingLoopRunner:
        nonlocal embedding_runner
        if embedding_func is None:
            raise RuntimeError("embedding_func was not provided")
        if embedding_runner is None:
            embedding_runner = EmbeddingLoopRunner(embedding_func)
        return embedding_runner

    def _register_embedding_runner_close() -> None:
        nonlocal embedding_runner_registered
        if embedding_runner is None or embedding_runner_registered:
            return
        close_callbacks.append(embedding_runner.close)
        embedding_runner_registered = True

    def _discard_unused_embedding_runner() -> None:
        nonlocal embedding_runner
        if embedding_runner is None or embedding_runner_registered:
            return
        embedding_runner.close()
        embedding_runner = None

    support_retriever = SupportAssetRetriever(catalog)
    if support_retriever.has_assets():
        _record_feature_status(
            feature_statuses,
            "support_assets",
            "Lesson support retrieval",
            FeatureStatus(
                enabled=True,
                mode="auto",
                reason="Structured support assets were found in configured or default support paths",
            ),
        )
    else:
        support_retriever = None
        _record_feature_status(
            feature_statuses,
            "support_assets",
            "Lesson support retrieval",
            FeatureStatus(
                enabled=False,
                mode="auto",
                reason="No structured support assets were found in configured or default support paths",
            ),
        )

    planner = None
    readiness_judge = None
    responder = None
    provider = (
        llm_provider
        or os.getenv("PEPTUTOR_LESSON_LLM_PROVIDER")
        or os.getenv("LLM_BINDING")
        or "unknown"
    )
    model_name = llm_model or default_lesson_llm_model()
    live_request = _resolve_feature_request(
        feature_name="Lesson live prompts",
        env_var="PEPTUTOR_LESSON_LIVE_PROMPTS",
        explicit_value=live_prompts_enabled,
        argument_name="live_prompts_enabled",
    )
    if live_request.requested is False:
        _record_feature_status(
            feature_statuses,
            "live_prompts",
            "Lesson live prompts",
            _disabled_feature_status(live_request, live_request.reason),
        )
    elif llm_model_func is None:
        _record_feature_status(
            feature_statuses,
            "live_prompts",
            "Lesson live prompts",
            _disabled_feature_status(
                live_request,
                "No llm_model_func was provided for lesson planner/responder calls",
            ),
        )
    else:
        lesson_llm_model_func = llm_model_func
        if llm_hashing_kv is not None or llm_model_kwargs:
            lesson_llm_model_func = partial(
                llm_model_func,
                hashing_kv=llm_hashing_kv,
                **(llm_model_kwargs or {}),
            )
        llm_runner = LLMCallLoopRunner(
            lesson_llm_model_func,
            llm_provider=provider,
            llm_model=model_name,
        )
        close_callbacks.append(llm_runner.close)
        planner = LessonPlanner(llm_runner.complete_text)
        readiness_judge = ReadinessJudge(llm_runner.complete_text)
        responder = LessonResponder(
            llm_runner.complete_text,
            stream_text=llm_runner.stream_text,
            llm_provider=provider,
            llm_model=model_name,
        )
        _record_feature_status(
            feature_statuses,
            "live_prompts",
            "Lesson live prompts",
            _enabled_feature_status(
                live_request,
                "Planner, readiness judge, and responder LLM calls are available through llm_model_func",
            ),
        )

    semantic_store = None
    semantic_recall_provider = None
    semantic_request = _resolve_feature_request(
        feature_name="Lesson SimpleMem semantic recall",
        env_var="PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL",
        explicit_value=semantic_recall_enabled,
        argument_name="semantic_recall_enabled",
    )
    if semantic_request.requested is False:
        _record_feature_status(
            feature_statuses,
            "semantic_recall",
            "Lesson SimpleMem semantic recall",
            _disabled_feature_status(semantic_request, semantic_request.reason),
        )
    elif embedding_func is None:
        _record_feature_status(
            feature_statuses,
            "semantic_recall",
            "Lesson SimpleMem semantic recall",
            _disabled_feature_status(
                semantic_request,
                "No embedding_func was provided for semantic recall indexing and search",
            ),
        )
    else:
        runner = _ensure_embedding_runner()
        semantic_store, semantic_reason = _build_simplemem_semantic_store(
            embed_texts=runner.embed_texts,
            embedding_dim=embedding_func.embedding_dim,
        )
        if semantic_store is None:
            _discard_unused_embedding_runner()
            _record_feature_status(
                feature_statuses,
                "semantic_recall",
                "Lesson SimpleMem semantic recall",
                _disabled_feature_status(semantic_request, semantic_reason),
            )
        else:
            semantic_recall_provider = SimpleMemSemanticRecallProvider(
                semantic_store,
                project=_resolve_simplemem_project(),
            )
            close_callbacks.append(semantic_store.close)
            _register_embedding_runner_close()
            _record_feature_status(
                feature_statuses,
                "semantic_recall",
                "Lesson SimpleMem semantic recall",
                _enabled_feature_status(semantic_request, semantic_reason),
            )

    memory_provider = None
    prompt_request = _resolve_feature_request(
        feature_name="Lesson SimpleMem prompt injection",
        env_var="PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION",
        explicit_value=prompt_injection_enabled,
        argument_name="prompt_injection_enabled",
    )
    if prompt_request.requested is False:
        _record_feature_status(
            feature_statuses,
            "prompt_injection",
            "Lesson SimpleMem prompt injection",
            _disabled_feature_status(prompt_request, prompt_request.reason),
        )
    else:
        memory_provider, prompt_reason = _build_simplemem_prompt_memory_provider(
            semantic_recall_provider=semantic_recall_provider,
        )
        if memory_provider is None:
            _record_feature_status(
                feature_statuses,
                "prompt_injection",
                "Lesson SimpleMem prompt injection",
                _disabled_feature_status(prompt_request, prompt_reason),
            )
        else:
            _record_feature_status(
                feature_statuses,
                "prompt_injection",
                "Lesson SimpleMem prompt injection",
                _enabled_feature_status(prompt_request, prompt_reason),
            )

    memory_writer = None
    writeback_request = _resolve_feature_request(
        feature_name="Lesson SimpleMem writeback",
        env_var="PEPTUTOR_SIMPLEMEM_WRITEBACK",
        explicit_value=writeback_enabled,
        argument_name="writeback_enabled",
    )
    if writeback_request.requested is False:
        _record_feature_status(
            feature_statuses,
            "writeback",
            "Lesson SimpleMem writeback",
            _disabled_feature_status(writeback_request, writeback_request.reason),
        )
    else:
        memory_writer, writeback_reason = _build_simplemem_writeback_adapter(
            semantic_store=semantic_store,
        )
        if memory_writer is None:
            _record_feature_status(
                feature_statuses,
                "writeback",
                "Lesson SimpleMem writeback",
                _disabled_feature_status(writeback_request, writeback_reason),
            )
        else:
            close_callbacks.append(memory_writer.close)
            _record_feature_status(
                feature_statuses,
                "writeback",
                "Lesson SimpleMem writeback",
                _enabled_feature_status(writeback_request, writeback_reason),
            )

    runtime = LessonRuntime(
        catalog,
        support_retriever=support_retriever,
        memory_provider=memory_provider,
        memory_writer=memory_writer,
        planner=planner,
        readiness_judge=readiness_judge,
        responder=responder,
        feature_statuses=feature_statuses,
        llm_provider=provider if llm_model_func is not None else llm_provider,
        llm_model=model_name if llm_model_func is not None else llm_model,
        policy_reply_review_enabled=readiness_judge is not None,
    )

    vector_request = _resolve_feature_request(
        feature_name="Lesson vector retrieval",
        env_var="PEPTUTOR_LESSON_VECTOR_RETRIEVAL",
        explicit_value=vector_enabled,
        argument_name="vector_enabled",
    )
    if vector_request.requested is False:
        _record_feature_status(
            feature_statuses,
            "vector_retrieval",
            "Lesson vector retrieval",
            _disabled_feature_status(vector_request, vector_request.reason),
        )
        return _bundle(runtime)
    if embedding_func is None:
        _record_feature_status(
            feature_statuses,
            "vector_retrieval",
            "Lesson vector retrieval",
            _disabled_feature_status(
                vector_request,
                "No embedding_func was provided for vector retrieval",
            ),
        )
        return _bundle(runtime)

    client_kwargs = (
        _resolve_qdrant_client_kwargs()
        if qdrant_client_kwargs is None
        else qdrant_client_kwargs
    )
    if not client_kwargs:
        _record_feature_status(
            feature_statuses,
            "vector_retrieval",
            "Lesson vector retrieval",
            _disabled_feature_status(
                vector_request,
                "No Qdrant connection settings were found for lesson vector retrieval",
            ),
        )
        return _bundle(runtime)

    vector_runner = _ensure_embedding_runner()
    try:
        store = QdrantTeachingStore(
            collection_name=collection_name
            or os.getenv("PEPTUTOR_LESSON_QDRANT_COLLECTION", "peptutor_teaching_blocks"),
            workspace=workspace or "default",
            client_kwargs=client_kwargs,
        )
        retriever = QdrantLessonRetriever(
            catalog=catalog,
            store=store,
            embed_texts=vector_runner.embed_texts,
            embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_NUM", "10")),
        )
        retriever.ensure_indexed()
        _register_embedding_runner_close()
        _record_feature_status(
            feature_statuses,
            "vector_retrieval",
            "Lesson vector retrieval",
            _enabled_feature_status(
                vector_request,
                "Qdrant connection settings and embedding_func are available for scoped reranking",
            ),
        )
        return _bundle(
            LessonRuntime(
                catalog,
                retriever=retriever,
                support_retriever=support_retriever,
                memory_provider=memory_provider,
                memory_writer=memory_writer,
                planner=planner,
                readiness_judge=readiness_judge,
                responder=responder,
                feature_statuses=feature_statuses,
            )
        )
    except Exception as exc:
        _discard_unused_embedding_runner()
        _record_feature_status(
            feature_statuses,
            "vector_retrieval",
            "Lesson vector retrieval",
            _disabled_feature_status(
                vector_request,
                f"Vector retrieval initialization failed: {exc}",
            ),
        )
        return _bundle(runtime)
