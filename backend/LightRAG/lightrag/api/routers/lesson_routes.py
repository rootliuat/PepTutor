"""Text-first lesson endpoints for the PepTutor pilot."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from lightrag.api.config import global_args
from lightrag.api.utils_api import (
    get_combined_auth_dependency,
    get_rate_limit_dependency,
)
from lightrag.orchestrator.lesson_runtime import (
    LessonCatalogOutline,
    LessonRuntime,
    LessonTeacherResponseStreamSink,
    LessonTurnResult,
    stream_lesson_teacher_response,
)
from lightrag.orchestrator.lesson_state import LessonRuntimeState
from lightrag.utils import logger


class LessonTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_uid: str = Field(min_length=1)
    student_id: str = Field(default="demo-student", min_length=1)
    learner_input: Optional[str] = None
    state: Optional[LessonRuntimeState] = None
    turn_client_id: Optional[str] = Field(default=None, min_length=1)


_LESSON_TEXT_SPLIT_RE = re.compile(r".+?(?:[。！？!?\.]+(?:\s+|$)|$)")

_LESSON_AIRI_EVALUATION_PROFILES: dict[str, dict[str, Any]] = {
    "correct": {
        "emotion": {"name": "happy", "intensity": 0.92},
        "motion": "Happy",
        "expression": "happy",
        "duration_ms": 2600,
    },
    "acceptable": {
        "emotion": {"name": "happy", "intensity": 0.86},
        "motion": "Happy",
        "expression": "happy",
        "duration_ms": 2400,
    },
    "partially_correct": {
        "emotion": {"name": "curious", "intensity": 0.82},
        "motion": "Curious",
        "expression": "think",
        "duration_ms": 3200,
    },
    "incorrect": {
        "emotion": {"name": "question", "intensity": 0.86},
        "motion": "Question",
        "expression": "think",
        "duration_ms": 3400,
    },
    "off_topic": {
        "emotion": {"name": "awkward", "intensity": 0.76},
        "motion": "Awkward",
        "expression": "neutral",
        "duration_ms": 3000,
    },
    "unclear": {
        "emotion": {"name": "question", "intensity": 0.78},
        "motion": "Question",
        "expression": "think",
        "duration_ms": 2800,
    },
}

_LESSON_AIRI_TEACHING_ACTION_PROFILES: dict[str, dict[str, Any]] = {
    "page_intro": {
        "emotion": {"name": "curious", "intensity": 0.78},
        "motion": "Curious",
        "expression": "think",
        "duration_ms": 3200,
    },
    "probe": {
        "emotion": {"name": "question", "intensity": 0.8},
        "motion": "Question",
        "expression": "think",
        "duration_ms": 3000,
    },
    "confirm": {
        "emotion": {"name": "happy", "intensity": 0.86},
        "motion": "Happy",
        "expression": "happy",
        "duration_ms": 2600,
    },
    "hint": {
        "emotion": {"name": "curious", "intensity": 0.78},
        "motion": "Curious",
        "expression": "think",
        "duration_ms": 3400,
    },
    "model": {
        "emotion": {"name": "think", "intensity": 0.8},
        "motion": "Think",
        "expression": "think",
        "duration_ms": 3600,
    },
    "repeat_drill": {
        "emotion": {"name": "question", "intensity": 0.8},
        "motion": "Question",
        "expression": "think",
        "duration_ms": 3400,
    },
    "explain": {
        "emotion": {"name": "think", "intensity": 0.78},
        "motion": "Think",
        "expression": "think",
        "duration_ms": 3600,
    },
    "redirect": {
        "emotion": {"name": "awkward", "intensity": 0.72},
        "motion": "Awkward",
        "expression": "neutral",
        "duration_ms": 3000,
    },
    "complete": {
        "emotion": {"name": "happy", "intensity": 0.9},
        "motion": "Happy",
        "expression": "happy",
        "duration_ms": 3200,
    },
}

_LESSON_AIRI_PERFORMANCE_EMOTION_PROFILES: dict[str, dict[str, Any]] = {
    "neutral": {"name": "neutral", "intensity": 0.7},
    "encouraging": {"name": "curious", "intensity": 0.82},
    "joy": {"name": "happy", "intensity": 0.92},
    "thinking": {"name": "think", "intensity": 0.78},
    "concerned": {"name": "awkward", "intensity": 0.76},
    "correction": {"name": "question", "intensity": 0.86},
}

_LESSON_AIRI_PERFORMANCE_MOTION_MAP: dict[str, str] = {
    "Idle": "Idle",
    "Listen": "Question",
    "Explain": "Think",
    "Nod": "Happy",
    "Encourage": "Curious",
    "Interrupted": "Surprise",
}

_LESSON_AIRI_PERFORMANCE_EXPRESSION_MAP: dict[str, str] = {
    "neutral": "neutral",
    "soft_smile": "happy",
    "thinking": "think",
    "concerned": "neutral",
    "focused": "think",
}

_LESSON_AIRI_PERFORMANCE_SPEECH_STYLE_DURATION_MS: dict[str, int] = {
    "normal": 2800,
    "slow_split": 3600,
    "short_prompt": 2200,
    "gentle_correction": 3400,
}


def _json_payload(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _sse_event(event: str, payload: Any) -> str:
    return f"event: {event}\ndata: {_json_payload(payload)}\n\n"


def _lesson_result_payload(result: LessonTurnResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


def _lesson_text_chunks(text: str) -> list[str]:
    normalized = " ".join(text.strip().split())
    if not normalized:
        return []

    chunks = [
        match.group(0)
        for match in _LESSON_TEXT_SPLIT_RE.finditer(normalized)
        if match.group(0)
    ]
    if not chunks:
        return [normalized]

    return chunks


def _airi_action_payload(result: LessonTurnResult) -> dict[str, Any]:
    airi_performance: dict[str, Any] | None = None
    if result.debug_signals is not None and result.debug_signals.persona is not None:
        airi_performance = result.debug_signals.persona.airi_performance.model_dump(
            mode="json"
        )

    return _airi_action_payload_from_metadata(
        teaching_action=result.teaching_action,
        evaluation=result.evaluation,
        branch_active=result.state.branch_active,
        turn_label=result.turn_label,
        airi_performance=airi_performance,
    )


def _bounded_unit_float(value: Any, *, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return round(max(0.0, min(1.0, float(value))), 2)


def _airi_profile_from_performance_plan(
    airi_performance: Any,
) -> dict[str, Any] | None:
    if not isinstance(airi_performance, dict):
        return None

    raw_emotion = airi_performance.get("emotion")
    raw_motion = airi_performance.get("motion")
    raw_expression = airi_performance.get("expression")
    raw_speech_style = airi_performance.get("speech_style")
    raw_interrupt_policy = airi_performance.get("interrupt_policy")
    raw_content_source = airi_performance.get("content_source")

    emotion_key = raw_emotion if isinstance(raw_emotion, str) else ""
    motion_key = raw_motion if isinstance(raw_motion, str) else ""
    expression_key = raw_expression if isinstance(raw_expression, str) else ""
    speech_style = raw_speech_style if isinstance(raw_speech_style, str) else "normal"
    interrupt_policy = (
        raw_interrupt_policy
        if isinstance(raw_interrupt_policy, str)
        else "barge_in_allowed"
    )
    content_source = (
        raw_content_source
        if isinstance(raw_content_source, str)
        else "lesson_runtime_teacher_response"
    )
    fallback_allowed = airi_performance.get("fallback_allowed")
    if not isinstance(fallback_allowed, bool):
        fallback_allowed = True

    emotion = dict(
        _LESSON_AIRI_PERFORMANCE_EMOTION_PROFILES.get(
            emotion_key,
            _LESSON_AIRI_PERFORMANCE_EMOTION_PROFILES["neutral"],
        )
    )

    return {
        "emotion": emotion,
        "motion": _LESSON_AIRI_PERFORMANCE_MOTION_MAP.get(motion_key, "Idle"),
        "expression": _LESSON_AIRI_PERFORMANCE_EXPRESSION_MAP.get(
            expression_key,
            "neutral",
        ),
        "duration_ms": _LESSON_AIRI_PERFORMANCE_SPEECH_STYLE_DURATION_MS.get(
            speech_style,
            _LESSON_AIRI_PERFORMANCE_SPEECH_STYLE_DURATION_MS["normal"],
        ),
        "speech_style": speech_style,
        "mouth_intensity": _bounded_unit_float(
            airi_performance.get("mouth_intensity"),
            default=0.8,
        ),
        "interrupt_policy": interrupt_policy,
        "content_source": content_source,
        "fallback_allowed": fallback_allowed,
        "performance_source": "lesson_persona_context",
    }


def _airi_action_payload_from_metadata(
    *,
    teaching_action: str,
    evaluation: str | None,
    branch_active: bool,
    turn_label: str,
    airi_performance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = _airi_profile_from_performance_plan(airi_performance) or (
        _LESSON_AIRI_EVALUATION_PROFILES.get(evaluation or "")
        or _LESSON_AIRI_TEACHING_ACTION_PROFILES.get(teaching_action)
        or {
            "emotion": {"name": "neutral", "intensity": 0.7},
            "motion": "Idle",
            "expression": "neutral",
            "duration_ms": 3000,
        }
    )

    payload = {
        "emotion": profile["emotion"],
        "motion": profile["motion"],
        "expression": profile["expression"],
        "duration_ms": profile["duration_ms"],
        "teaching_action": teaching_action,
        "evaluation": evaluation,
        "reason": "lesson_branch_turn" if branch_active else "lesson_turn",
        "turn_label": turn_label,
    }
    for key in (
        "speech_style",
        "mouth_intensity",
        "interrupt_policy",
        "content_source",
        "fallback_allowed",
        "performance_source",
    ):
        if key in profile:
            payload[key] = profile[key]
    return payload


def _run_lesson_turn(runtime: LessonRuntime, request: LessonTurnRequest) -> LessonTurnResult:
    if request.state is None:
        if request.learner_input:
            raise HTTPException(
                status_code=400,
                detail="learner_input is only allowed after state initialization",
            )
        return runtime.start_page(request.page_uid, request.student_id)

    if not request.learner_input:
        raise HTTPException(
            status_code=400,
            detail="learner_input is required when state is provided",
        )

    return runtime.handle_turn(
        state=request.state,
        learner_input=request.learner_input,
        requested_page_uid=request.page_uid,
    )


def _lesson_turn_exception_context(
    runtime: LessonRuntime,
    request: LessonTurnRequest,
) -> dict[str, Any]:
    selected_block = None
    if request.state is not None:
        selected_block = request.state.current_block_uid
    if selected_block is None:
        try:
            selected_block = runtime.catalog.first_block_for_page(request.page_uid).block_uid
        except Exception:  # noqa: BLE001 - best-effort logging context.
            selected_block = None
    route = "page_entry" if request.state is None else "stateful_turn"
    return {
        "route": route,
        "pageUid": request.page_uid,
        "selected_block": selected_block,
    }


def _log_lesson_turn_exception(
    *,
    runtime: LessonRuntime,
    request: LessonTurnRequest,
    trace_id: str,
    started_at: float,
    exc: Exception,
) -> None:
    context = _lesson_turn_exception_context(runtime, request)
    logger.exception(
        "Lesson turn exception %s",
        json.dumps(
            {
                "trace_id": trace_id,
                "exception_type": type(exc).__name__,
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                "route": context["route"],
                "pageUid": context["pageUid"],
                "selected_block": context["selected_block"],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )


def create_lesson_routes(
    runtime: LessonRuntime,
    api_key: Optional[str] = None,
) -> APIRouter:
    router = APIRouter(prefix="/lesson", tags=["lesson"])
    combined_auth = get_combined_auth_dependency(api_key)
    lesson_rate_limit = get_rate_limit_dependency(
        "peptutor-lesson",
        global_args.peptutor_lesson_rate_limit_requests,
        global_args.peptutor_lesson_rate_limit_window_seconds,
    )

    @router.get(
        "/catalog",
        response_model=LessonCatalogOutline,
        dependencies=[Depends(combined_auth), Depends(lesson_rate_limit)],
    )
    async def lesson_catalog() -> LessonCatalogOutline:
        return runtime.catalog.catalog_outline()

    @router.post(
        "/turn",
        response_model=LessonTurnResult,
        dependencies=[Depends(combined_auth), Depends(lesson_rate_limit)],
    )
    async def lesson_turn(request: LessonTurnRequest) -> LessonTurnResult:
        started_at = time.perf_counter()
        trace_id = request.turn_client_id or uuid4().hex
        try:
            return _run_lesson_turn(runtime, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            _log_lesson_turn_exception(
                runtime=runtime,
                request=request,
                trace_id=trace_id,
                started_at=started_at,
                exc=exc,
            )
            raise

    @router.post(
        "/turn/stream",
        dependencies=[Depends(combined_auth), Depends(lesson_rate_limit)],
    )
    async def lesson_turn_stream(request: LessonTurnRequest) -> StreamingResponse:
        async def event_stream():
            started_at = time.perf_counter()
            trace_id = request.turn_client_id or uuid4().hex
            try:
                yield _sse_event(
                    "meta",
                    {
                        "turn_client_id": request.turn_client_id,
                        "page_uid": request.page_uid,
                    },
                )
                loop = asyncio.get_running_loop()
                stream_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

                def enqueue_stream_event(event: str, payload: Any) -> None:
                    future = asyncio.run_coroutine_threadsafe(
                        stream_queue.put((event, payload)),
                        loop,
                    )
                    future.result()

                sink = LessonTeacherResponseStreamSink(
                    on_text_delta=lambda text: enqueue_stream_event(
                        "text_delta",
                        text,
                    ),
                    on_action_metadata=lambda metadata: enqueue_stream_event(
                        "action",
                        metadata,
                    ),
                )

                def run_streamed_turn() -> LessonTurnResult:
                    with stream_lesson_teacher_response(sink):
                        return _run_lesson_turn(runtime, request)

                turn_task = asyncio.create_task(asyncio.to_thread(run_streamed_turn))
                text_index = 0
                action_emitted = False
                text_emitted = False

                while not turn_task.done() or not stream_queue.empty():
                    try:
                        event, payload = await asyncio.wait_for(
                            stream_queue.get(),
                            timeout=0.05,
                        )
                    except asyncio.TimeoutError:
                        continue

                    if event == "action":
                        if action_emitted:
                            continue
                        action_emitted = True
                        action = _airi_action_payload_from_metadata(**payload)
                        yield _sse_event(
                            "action",
                            {
                                "turn_client_id": request.turn_client_id,
                                **action,
                            },
                        )
                        continue

                    if event != "text_delta":
                        continue

                    text = str(payload)
                    if not text:
                        continue
                    text_emitted = True
                    yield _sse_event(
                        "text_delta",
                        {
                            "turn_client_id": request.turn_client_id,
                            "index": text_index,
                            "text": text,
                        },
                    )
                    text_index += 1
                    await asyncio.sleep(0)

                result = await turn_task
                if not action_emitted:
                    action = _airi_action_payload(result)
                    yield _sse_event(
                        "action",
                        {
                            "turn_client_id": request.turn_client_id,
                            **action,
                        },
                    )

                if not text_emitted:
                    for chunk in _lesson_text_chunks(result.teacher_response):
                        yield _sse_event(
                            "text_delta",
                            {
                                "turn_client_id": request.turn_client_id,
                                "index": text_index,
                                "text": chunk,
                            },
                        )
                        text_index += 1
                        await asyncio.sleep(0)

                yield _sse_event(
                    "done",
                    {
                        "turn_client_id": request.turn_client_id,
                        "result": _lesson_result_payload(result),
                    },
                )
            except HTTPException as exc:
                yield _sse_event(
                    "error",
                    {
                        "turn_client_id": request.turn_client_id,
                        "status_code": exc.status_code,
                        "detail": exc.detail,
                    },
                )
            except KeyError as exc:
                yield _sse_event(
                    "error",
                    {
                        "turn_client_id": request.turn_client_id,
                        "status_code": 404,
                        "detail": str(exc),
                    },
                )
            except ValueError as exc:
                yield _sse_event(
                    "error",
                    {
                        "turn_client_id": request.turn_client_id,
                        "status_code": 400,
                        "detail": str(exc),
                    },
                )
            except Exception as exc:
                _log_lesson_turn_exception(
                    runtime=runtime,
                    request=request,
                    trace_id=trace_id,
                    started_at=started_at,
                    exc=exc,
                )
                yield _sse_event(
                    "error",
                    {
                        "turn_client_id": request.turn_client_id,
                        "status_code": 500,
                        "detail": f"lesson_turn_exception:{trace_id}",
                    },
                )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
