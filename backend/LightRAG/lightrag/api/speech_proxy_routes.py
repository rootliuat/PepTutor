"""PepTutor speech proxy HTTP routes."""

from __future__ import annotations

import base64
import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import edge_tts
from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from lightrag.api.config import global_args
from lightrag.api.speech_proxy_config import get_env_with_fallback
from lightrag.api.speech_proxy_ws import handle_doubao_realtime_asr_websocket
from lightrag.api.utils_api import (
    authorize_websocket,
    enforce_websocket_rate_limit,
    get_rate_limit_dependency,
    get_strict_auth_dependency,
)
from lightrag.utils import logger

DOUBAO_TTS_HTTP_URL = "https://openspeech.bytedance.com/api/v1/tts"
DOUBAO_TTS_DEFAULT_CLUSTER = "volcano_tts"
DOUBAO_TTS_DEFAULT_ENCODING = "mp3"
DOUBAO_TTS_ALLOWED_VOICES = ("zh_female_vv_uranus_bigtts",)
EDGE_TTS_DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
EDGE_TTS_ALLOWED_VOICES = (EDGE_TTS_DEFAULT_VOICE,)
EDGE_TTS_MAX_ATTEMPTS = 2


class DoubaoTtsAudioOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    encoding: str = Field(default=DOUBAO_TTS_DEFAULT_ENCODING, min_length=1)
    speed_ratio: float | None = None
    volume_ratio: float | None = None
    pitch_ratio: float | None = None


class DoubaoTtsUserOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: str | None = None


class DoubaoTtsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str = Field(min_length=1)
    voice: str = Field(min_length=1)
    model: str | None = None
    appId: str | None = None
    apiKey: str | None = None
    cluster: str | None = None
    user: DoubaoTtsUserOptions | None = None
    audio: DoubaoTtsAudioOptions | None = None


class EdgeTtsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str = Field(min_length=1)
    voice: str = Field(default=EDGE_TTS_DEFAULT_VOICE, min_length=1)
    model: str | None = None
    rate: str = "+0%"
    volume: str = "+0%"
    pitch: str = "+0Hz"


@dataclass(slots=True)
class SpeechProxyError(Exception):
    code: str
    message: str
    status_code: int = 500
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class DoubaoTtsConfig:
    app_id: str
    api_key: str
    cluster: str
    allowed_voices: tuple[str, ...]


@dataclass(slots=True)
class TtsAuditContext:
    client: str
    client_chain: str
    source_tag: str
    source_path: str
    source_page_uid: str
    origin: str
    referer: str
    user_agent: str
    text_preview: str
    text_sha1: str


def _error_payload(error: SpeechProxyError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": error.code,
            "message": error.message,
        }
    }
    if error.details:
        payload["error"]["details"] = error.details
    return payload


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _client_label(request: Request) -> str:
    client = request.client
    if client is None or not client.host:
        return "unknown"
    return f"{client.host}:{client.port}" if client.port else client.host


def _sanitize_log_value(value: str | None, *, max_length: int = 160) -> str:
    normalized = re.sub(r"\s+", " ", (value or "").strip())
    if not normalized:
        return "-"
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 1]}…"


def _build_text_preview(input_text: str, *, max_length: int = 72) -> str:
    sanitized = _sanitize_log_value(input_text, max_length=max_length)
    if sanitized == "-":
        return sanitized
    return sanitized


def _extract_source_path_and_page_uid(
    source_path_header: str,
    source_page_uid_header: str,
    referer: str,
) -> tuple[str, str]:
    source_path = _sanitize_log_value(source_path_header, max_length=120)
    source_page_uid = _sanitize_log_value(source_page_uid_header, max_length=80)
    if referer == "-":
        return source_path, source_page_uid

    try:
        parsed_referer = urlsplit(referer)
    except Exception:
        return source_path, source_page_uid

    if source_path == "-" and parsed_referer.path:
        source_path = _sanitize_log_value(parsed_referer.path, max_length=120)

    if source_page_uid == "-":
        page_uid = parse_qs(parsed_referer.query).get("page_uid", [""])[0]
        source_page_uid = _sanitize_log_value(page_uid, max_length=80)

    return source_path, source_page_uid


def _resolve_tts_audit_context(
    http_request: Request,
    request: DoubaoTtsRequest | EdgeTtsRequest,
) -> TtsAuditContext:
    headers = http_request.headers
    input_text = request.input.strip()
    referer = _sanitize_log_value(headers.get("referer"), max_length=240)
    source_path, source_page_uid = _extract_source_path_and_page_uid(
        headers.get("x-peptutor-source-path", ""),
        headers.get("x-peptutor-source-page-uid", ""),
        referer,
    )

    source_tag = _sanitize_log_value(headers.get("x-peptutor-source-tag"), max_length=80)
    if source_tag == "-" and source_path != "-":
        source_tag = "lesson-runtime" if source_path.startswith("/lesson") else "browser-runtime"

    return TtsAuditContext(
        client=_client_label(http_request),
        client_chain=_sanitize_log_value(
            headers.get("x-forwarded-for") or headers.get("x-real-ip"),
            max_length=160,
        ),
        source_tag=source_tag,
        source_path=source_path,
        source_page_uid=source_page_uid,
        origin=_sanitize_log_value(headers.get("origin"), max_length=200),
        referer=referer,
        user_agent=_sanitize_log_value(headers.get("user-agent"), max_length=200),
        text_preview=_build_text_preview(input_text),
        text_sha1=hashlib.sha1(input_text.encode("utf-8")).hexdigest()[:12] if input_text else "-",
    )


def _error_response(
    error: SpeechProxyError,
    *,
    proxy_request_id: str | None = None,
    audit_context: TtsAuditContext | None = None,
    voice: str | None = None,
    provider: str | None = None,
    input_chars: int | None = None,
    duration_ms: int | None = None,
) -> JSONResponse:
    logger.warning(
        "Speech proxy TTS error request_id=%s client=%s client_chain=%s voice=%s provider=%s input_chars=%s text_sha1=%s text_preview=%s source_tag=%s source_path=%s source_page_uid=%s origin=%s referer=%s user_agent=%s duration_ms=%s code=%s details=%s",
        proxy_request_id or "unknown",
        audit_context.client if audit_context else "unknown",
        audit_context.client_chain if audit_context else "unknown",
        voice or "unknown",
        provider or "unknown",
        input_chars if input_chars is not None else "unknown",
        audit_context.text_sha1 if audit_context else "unknown",
        audit_context.text_preview if audit_context else "unknown",
        audit_context.source_tag if audit_context else "unknown",
        audit_context.source_path if audit_context else "unknown",
        audit_context.source_page_uid if audit_context else "unknown",
        audit_context.origin if audit_context else "unknown",
        audit_context.referer if audit_context else "unknown",
        audit_context.user_agent if audit_context else "unknown",
        duration_ms if duration_ms is not None else "unknown",
        error.code,
        error.details or {},
    )
    return JSONResponse(status_code=error.status_code, content=_error_payload(error))


def resolve_doubao_tts_config() -> DoubaoTtsConfig:
    app_id = get_env_with_fallback(
        "PEPTUTOR_DOUBAO_TTS_APP_ID",
        "VITE_PEPTUTOR_TTS_APP_ID",
        "VITE_DOUBAO_TTS_APP_ID",
        "PEPTUTOR_DOUBAO_ASR_APP_ID",
        "VITE_PEPTUTOR_ASR_APP_ID",
        "VITE_DOUBAO_ASR_APP_ID",
    )
    api_key = get_env_with_fallback(
        "PEPTUTOR_DOUBAO_TTS_API_KEY",
        "VITE_PEPTUTOR_TTS_API_KEY",
        "VITE_DOUBAO_TTS_API_KEY",
        "PEPTUTOR_DOUBAO_ASR_API_KEY",
        "VITE_PEPTUTOR_ASR_API_KEY",
        "VITE_DOUBAO_ASR_API_KEY",
    )
    cluster = (
        get_env_with_fallback(
            "PEPTUTOR_DOUBAO_TTS_CLUSTER",
            "VITE_PEPTUTOR_TTS_CLUSTER",
            "VITE_DOUBAO_TTS_CLUSTER",
        )
        or DOUBAO_TTS_DEFAULT_CLUSTER
    )

    if not app_id or not api_key:
        raise SpeechProxyError(
            code="speech_proxy_missing_config",
            message="Doubao TTS proxy is missing server-side credentials.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details={
                "missing": [
                    name
                    for name, value in (
                        ("app_id", app_id),
                        ("api_key", api_key),
                    )
                    if not value
                ]
            },
        )

    return DoubaoTtsConfig(
        app_id=app_id,
        api_key=api_key,
        cluster=cluster,
        allowed_voices=DOUBAO_TTS_ALLOWED_VOICES,
    )


def validate_doubao_tts_request(request: DoubaoTtsRequest) -> tuple[str, str]:
    input_text = request.input.strip()
    voice = request.voice.strip()

    if not input_text:
        raise SpeechProxyError(
            code="speech_proxy_invalid_request",
            message="Doubao TTS proxy requires non-empty input text.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if voice not in DOUBAO_TTS_ALLOWED_VOICES:
        raise SpeechProxyError(
            code="speech_proxy_invalid_request",
            message="Doubao TTS proxy rejected an unallowlisted voice.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"allowed_voices": list(DOUBAO_TTS_ALLOWED_VOICES), "voice": voice},
        )

    return input_text, voice


def build_doubao_tts_http_request(
    request: DoubaoTtsRequest,
    config: DoubaoTtsConfig,
) -> tuple[dict[str, str], dict[str, Any]]:
    input_text, voice = validate_doubao_tts_request(request)

    audio_options = request.audio or DoubaoTtsAudioOptions()
    encoding = audio_options.encoding or DOUBAO_TTS_DEFAULT_ENCODING
    headers = {
        "Authorization": f"Bearer;{config.api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "app": {
            "appid": config.app_id,
            "token": config.api_key,
            "cluster": config.cluster,
        },
        "user": {
            "uid": request.user.uid if request.user and request.user.uid else "peptutor-backend",
        },
        "audio": {
            "voice_type": voice,
            "encoding": encoding,
        },
        "request": {
            "reqid": str(uuid4()),
            "text": input_text,
            "text_type": "plain",
            "operation": "query",
        },
    }

    for key in ("speed_ratio", "volume_ratio", "pitch_ratio"):
        value = getattr(audio_options, key)
        if isinstance(value, (int, float)):
            payload["audio"][key] = value

    return headers, payload


async def fetch_doubao_tts_audio(
    request: DoubaoTtsRequest,
) -> tuple[bytes, str]:
    validate_doubao_tts_request(request)
    config = resolve_doubao_tts_config()
    headers, payload = build_doubao_tts_http_request(request, config)
    timeout = httpx.Timeout(60.0, connect=15.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            upstream = await client.post(DOUBAO_TTS_HTTP_URL, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise SpeechProxyError(
                code="speech_proxy_upstream_error",
                message="Doubao TTS upstream request failed.",
                status_code=status.HTTP_502_BAD_GATEWAY,
                details={"upstream_error": str(exc)},
            ) from exc

    try:
        upstream_json = upstream.json()
    except ValueError:
        upstream_json = None

    if (
        not upstream.is_success
        or not isinstance(upstream_json, dict)
        or upstream_json.get("code") != 3000
        or not upstream_json.get("data")
    ):
        details = {"upstream_status": upstream.status_code}
        if isinstance(upstream_json, dict):
            details.update(
                {
                    "upstream_code": upstream_json.get("code"),
                    "upstream_message": upstream_json.get("message"),
                    "request_id": upstream_json.get("reqid")
                    or upstream_json.get("request_id"),
                }
            )
        else:
            details["upstream_body"] = upstream.text[:500]
        raise SpeechProxyError(
            code="speech_proxy_upstream_error",
            message="Doubao TTS upstream returned an invalid response.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=details,
        )

    try:
        audio = base64.b64decode(str(upstream_json["data"]), validate=True)
    except Exception as exc:
        raise SpeechProxyError(
            code="speech_proxy_upstream_error",
            message="Doubao TTS upstream returned invalid audio data.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details={"error": str(exc)},
        ) from exc

    content_type = (
        "audio/wav"
        if payload["audio"].get("encoding") == "wav"
        else "audio/mpeg"
    )
    return audio, content_type


def validate_edge_tts_request(request: EdgeTtsRequest) -> tuple[str, str]:
    input_text = request.input.strip()
    voice = request.voice.strip() or EDGE_TTS_DEFAULT_VOICE

    if not input_text:
        raise SpeechProxyError(
            code="speech_proxy_invalid_request",
            message="Edge TTS proxy requires non-empty input text.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if voice not in EDGE_TTS_ALLOWED_VOICES:
        raise SpeechProxyError(
            code="speech_proxy_invalid_request",
            message="Edge TTS proxy rejected an unallowlisted voice.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"allowed_voices": list(EDGE_TTS_ALLOWED_VOICES), "voice": voice},
        )

    return input_text, voice


async def fetch_edge_tts_audio(request: EdgeTtsRequest) -> tuple[bytes, str]:
    input_text, voice = validate_edge_tts_request(request)
    last_error: SpeechProxyError | None = None

    for attempt in range(1, EDGE_TTS_MAX_ATTEMPTS + 1):
        audio_chunks: list[bytes] = []
        try:
            communicator = edge_tts.Communicate(
                input_text,
                voice=voice,
                rate=request.rate,
                volume=request.volume,
                pitch=request.pitch,
            )
            async for message in communicator.stream():
                if message["type"] == "audio" and message.get("data"):
                    audio_chunks.append(message["data"])
        except Exception as exc:
            last_error = SpeechProxyError(
                code="speech_proxy_upstream_error",
                message="Edge TTS upstream request failed.",
                status_code=status.HTTP_502_BAD_GATEWAY,
                details={
                    "upstream_error": str(exc),
                    "attempt": attempt,
                    "max_attempts": EDGE_TTS_MAX_ATTEMPTS,
                },
            )
            if attempt < EDGE_TTS_MAX_ATTEMPTS:
                continue
            raise last_error from exc

        audio = b"".join(audio_chunks)
        if audio:
            return audio, "audio/mpeg"

        last_error = SpeechProxyError(
            code="speech_proxy_upstream_error",
            message="Edge TTS upstream returned no audio.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details={
                "attempt": attempt,
                "max_attempts": EDGE_TTS_MAX_ATTEMPTS,
            },
        )
        if attempt < EDGE_TTS_MAX_ATTEMPTS:
            continue

    if last_error:
        raise last_error
    raise SpeechProxyError(
        code="speech_proxy_upstream_error",
        message="Edge TTS upstream returned no audio.",
        status_code=status.HTTP_502_BAD_GATEWAY,
    )


def create_speech_proxy_routes(api_key: str | None = None) -> APIRouter:
    router = APIRouter(tags=["peptutor-speech"])
    strict_auth = get_strict_auth_dependency(api_key)
    tts_rate_limit = get_rate_limit_dependency(
        "peptutor-speech-tts",
        global_args.peptutor_speech_tts_rate_limit_requests,
        global_args.peptutor_speech_tts_rate_limit_window_seconds,
    )

    @router.post(
        "/api/peptutor/doubao-tts",
        dependencies=[Depends(strict_auth), Depends(tts_rate_limit)],
    )
    async def doubao_tts(http_request: Request, request: DoubaoTtsRequest) -> Response:
        proxy_request_id = str(uuid4())
        audit_context = _resolve_tts_audit_context(http_request, request)
        voice = request.voice.strip() or "unknown"
        input_chars = len(request.input.strip())
        started_at = time.perf_counter()
        logger.info(
            "Speech proxy TTS start request_id=%s client=%s client_chain=%s voice=%s input_chars=%s text_sha1=%s text_preview=%s source_tag=%s source_path=%s source_page_uid=%s origin=%s referer=%s user_agent=%s",
            proxy_request_id,
            audit_context.client,
            audit_context.client_chain,
            voice,
            input_chars,
            audit_context.text_sha1,
            audit_context.text_preview,
            audit_context.source_tag,
            audit_context.source_path,
            audit_context.source_page_uid,
            audit_context.origin,
            audit_context.referer,
            audit_context.user_agent,
        )
        try:
            audio, content_type = await fetch_doubao_tts_audio(request)
        except SpeechProxyError as exc:
            return _error_response(
                exc,
                proxy_request_id=proxy_request_id,
                audit_context=audit_context,
                voice=voice,
                provider="doubao",
                input_chars=input_chars,
                duration_ms=_elapsed_ms(started_at),
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            return _error_response(
                SpeechProxyError(
                    code="speech_proxy_internal_error",
                    message="Doubao TTS proxy crashed while handling the request.",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    details={"error": str(exc)},
                ),
                proxy_request_id=proxy_request_id,
                audit_context=audit_context,
                voice=voice,
                provider="doubao",
                input_chars=input_chars,
                duration_ms=_elapsed_ms(started_at),
            )

        duration_ms = _elapsed_ms(started_at)
        logger.info(
            "Speech proxy TTS success request_id=%s client=%s client_chain=%s voice=%s input_chars=%s text_sha1=%s text_preview=%s source_tag=%s source_path=%s source_page_uid=%s origin=%s referer=%s user_agent=%s duration_ms=%s content_type=%s bytes=%s",
            proxy_request_id,
            audit_context.client,
            audit_context.client_chain,
            voice,
            input_chars,
            audit_context.text_sha1,
            audit_context.text_preview,
            audit_context.source_tag,
            audit_context.source_path,
            audit_context.source_page_uid,
            audit_context.origin,
            audit_context.referer,
            audit_context.user_agent,
            duration_ms,
            content_type,
            len(audio),
        )
        return Response(content=audio, media_type=content_type)

    @router.post(
        "/api/peptutor/edge-tts",
        dependencies=[Depends(strict_auth), Depends(tts_rate_limit)],
    )
    async def edge_tts_proxy(http_request: Request, request: EdgeTtsRequest) -> Response:
        proxy_request_id = str(uuid4())
        audit_context = _resolve_tts_audit_context(http_request, request)
        voice = request.voice.strip() or EDGE_TTS_DEFAULT_VOICE
        input_chars = len(request.input.strip())
        started_at = time.perf_counter()
        logger.info(
            "Speech proxy TTS start request_id=%s client=%s client_chain=%s voice=%s input_chars=%s text_sha1=%s text_preview=%s source_tag=%s source_path=%s source_page_uid=%s origin=%s referer=%s user_agent=%s provider=edge",
            proxy_request_id,
            audit_context.client,
            audit_context.client_chain,
            voice,
            input_chars,
            audit_context.text_sha1,
            audit_context.text_preview,
            audit_context.source_tag,
            audit_context.source_path,
            audit_context.source_page_uid,
            audit_context.origin,
            audit_context.referer,
            audit_context.user_agent,
        )
        try:
            audio, content_type = await fetch_edge_tts_audio(request)
        except SpeechProxyError as exc:
            return _error_response(
                exc,
                proxy_request_id=proxy_request_id,
                audit_context=audit_context,
                voice=voice,
                provider="edge",
                input_chars=input_chars,
                duration_ms=_elapsed_ms(started_at),
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            return _error_response(
                SpeechProxyError(
                    code="speech_proxy_internal_error",
                    message="Edge TTS proxy crashed while handling the request.",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    details={"error": str(exc)},
                ),
                proxy_request_id=proxy_request_id,
                audit_context=audit_context,
                voice=voice,
                provider="edge",
                input_chars=input_chars,
                duration_ms=_elapsed_ms(started_at),
            )

        duration_ms = _elapsed_ms(started_at)
        logger.info(
            "Speech proxy TTS success request_id=%s client=%s client_chain=%s voice=%s input_chars=%s text_sha1=%s text_preview=%s source_tag=%s source_path=%s source_page_uid=%s origin=%s referer=%s user_agent=%s duration_ms=%s content_type=%s bytes=%s provider=edge",
            proxy_request_id,
            audit_context.client,
            audit_context.client_chain,
            voice,
            input_chars,
            audit_context.text_sha1,
            audit_context.text_preview,
            audit_context.source_tag,
            audit_context.source_path,
            audit_context.source_page_uid,
            audit_context.origin,
            audit_context.referer,
            audit_context.user_agent,
            duration_ms,
            content_type,
            len(audio),
        )
        return Response(content=audio, media_type=content_type)

    @router.websocket("/api/peptutor/doubao-realtime-asr")
    async def doubao_realtime_asr(websocket: WebSocket):
        try:
            authorize_websocket(
                websocket,
                api_key=api_key,
                honor_whitelist=False,
            )
            enforce_websocket_rate_limit(
                websocket,
                rate_limit_name="peptutor-speech-asr-connect",
                max_requests=(
                    global_args.peptutor_speech_asr_connect_rate_limit_requests
                ),
                window_seconds=(
                    global_args.peptutor_speech_asr_connect_rate_limit_window_seconds
                ),
            )
        except HTTPException as exc:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason=str(exc.detail),
            ) from exc

        await handle_doubao_realtime_asr_websocket(websocket)

    return router
