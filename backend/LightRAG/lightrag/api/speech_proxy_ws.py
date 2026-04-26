"""PepTutor Doubao realtime ASR websocket bridge."""

from __future__ import annotations

import asyncio
import contextlib
import gzip
import json
import time
from dataclasses import dataclass
from struct import pack, unpack_from
from typing import Any
from uuid import uuid4

import aiohttp
from aiohttp import WSMessage, WSMsgType
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from lightrag.api.speech_proxy_config import get_env_with_fallback
from lightrag.utils import logger

DOUBAO_REALTIME_WS_URL = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
DOUBAO_REALTIME_RESOURCE_ID = "volc.speech.dialog"
DOUBAO_REALTIME_APP_KEY = "PlgvMymc7f3tQnJ6"
DOUBAO_REALTIME_DEFAULT_MODEL = "1.2.1.1"

DOUBAO_REALTIME_PROTOCOL_VERSION = 0x1
DOUBAO_REALTIME_HEADER_SIZE_WORDS = 0x1
DOUBAO_REALTIME_EVENT_FLAG = 0b0100

DOUBAO_REALTIME_CONNECT_EVENT_IDS = {
    1,
    2,
    50,
    51,
    52,
}

DOUBAO_REALTIME_SESSION_EVENT_IDS = {
    100,
    102,
    150,
    152,
    153,
    154,
    200,
    201,
    251,
    300,
    350,
    351,
    352,
    359,
    400,
    450,
    451,
    459,
    500,
    501,
    502,
    510,
    511,
    512,
    513,
    514,
    515,
    550,
    553,
    559,
    567,
    568,
    569,
    570,
    571,
    599,
}


class DoubaoRealtimeMessageType:
    FULL_CLIENT_REQUEST = 0x1
    AUDIO_ONLY_REQUEST = 0x2
    FULL_SERVER_RESPONSE = 0x9
    AUDIO_ONLY_RESPONSE = 0xB
    ERROR_INFORMATION = 0xF


class DoubaoRealtimeSerializationMethod:
    RAW = 0x0
    JSON = 0x1


class DoubaoRealtimeCompressionMethod:
    NONE = 0x0
    GZIP = 0x1


@dataclass(slots=True)
class SpeechProxyError(Exception):
    code: str
    message: str
    status_code: int = 500
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class DoubaoRealtimeConfig:
    app_id: str
    access_key: str
    resource_id: str
    app_key: str
    model: str


@dataclass(slots=True)
class ParsedDoubaoRealtimeFrame:
    protocol_version: int
    header_size_words: int
    message_type: int
    message_flags: int
    serialization: int
    compression: int
    error_code: int | None
    sequence: int | None
    event: int | None
    connect_id: str | None
    session_id: str | None
    payload_size: int
    payload: bytes


@dataclass(slots=True)
class DoubaoRealtimeUpstreamConnection:
    client_session: aiohttp.ClientSession
    websocket: Any
    session_id: str
    connect_id: str


def _ws_error_payload(error: SpeechProxyError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "error",
        "error": error.message,
        "code": error.code,
    }
    if error.details:
        payload["details"] = error.details
        upstream_status = error.details.get("upstream_status") or error.details.get(
            "status_code"
        )
        if isinstance(upstream_status, int):
            payload["statusCode"] = upstream_status
    return payload


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _ready_elapsed_ms(started_at: float, ready_at: float | None) -> int | None:
    if ready_at is None:
        return None
    return int((ready_at - started_at) * 1000)


def _client_label(websocket: WebSocket) -> str:
    client = websocket.client
    if client is None or not client.host:
        return "unknown"
    return f"{client.host}:{client.port}" if client.port else client.host


def resolve_doubao_realtime_config() -> DoubaoRealtimeConfig:
    app_id = get_env_with_fallback(
        "PEPTUTOR_DOUBAO_ASR_APP_ID",
        "VITE_PEPTUTOR_ASR_APP_ID",
        "VITE_DOUBAO_ASR_APP_ID",
        "PEPTUTOR_DOUBAO_TTS_APP_ID",
        "VITE_PEPTUTOR_TTS_APP_ID",
        "VITE_DOUBAO_TTS_APP_ID",
    )
    access_key = get_env_with_fallback(
        "PEPTUTOR_DOUBAO_ASR_API_KEY",
        "VITE_PEPTUTOR_ASR_API_KEY",
        "VITE_DOUBAO_ASR_API_KEY",
        "PEPTUTOR_DOUBAO_TTS_API_KEY",
        "VITE_PEPTUTOR_TTS_API_KEY",
        "VITE_DOUBAO_TTS_API_KEY",
    )
    resource_id = get_env_with_fallback(
        "PEPTUTOR_DOUBAO_ASR_RESOURCE_ID",
        "VITE_PEPTUTOR_ASR_RESOURCE_ID",
        "VITE_DOUBAO_ASR_RESOURCE_ID",
    ) or DOUBAO_REALTIME_RESOURCE_ID
    app_key = get_env_with_fallback(
        "PEPTUTOR_DOUBAO_ASR_APP_KEY",
        "VITE_PEPTUTOR_ASR_APP_KEY",
        "VITE_DOUBAO_ASR_APP_KEY",
    ) or DOUBAO_REALTIME_APP_KEY
    model = get_env_with_fallback(
        "PEPTUTOR_DOUBAO_ASR_MODEL",
        "VITE_PEPTUTOR_ASR_MODEL",
        "VITE_DOUBAO_ASR_MODEL",
    ) or DOUBAO_REALTIME_DEFAULT_MODEL

    if not app_id or not access_key:
        raise SpeechProxyError(
            code="speech_proxy_missing_config",
            message="Doubao realtime ASR proxy is missing server-side credentials.",
            status_code=500,
            details={
                "missing": [
                    name
                    for name, value in (
                        ("app_id", app_id),
                        ("api_key", access_key),
                    )
                    if not value
                ]
            },
        )

    return DoubaoRealtimeConfig(
        app_id=app_id,
        access_key=access_key,
        resource_id=resource_id,
        app_key=app_key,
        model=model,
    )


def _to_bytes(payload: str | bytes | bytearray | memoryview | None) -> bytes:
    if payload is None:
        return b""
    if isinstance(payload, str):
        return payload.encode("utf-8")
    if isinstance(payload, memoryview):
        return payload.tobytes()
    return bytes(payload)


def _has_sequence_field(message_flags: int) -> bool:
    sequence_mode = message_flags & 0b0011
    return sequence_mode in {0b0001, 0b0011}


def build_doubao_realtime_frame(
    *,
    message_type: int,
    message_flags: int = 0,
    serialization: int = DoubaoRealtimeSerializationMethod.RAW,
    compression: int = DoubaoRealtimeCompressionMethod.NONE,
    error_code: int | None = None,
    sequence: int | None = None,
    event: int | None = None,
    connect_id: str | None = None,
    session_id: str | None = None,
    payload: str | bytes | bytearray | memoryview | None = None,
) -> bytes:
    payload_bytes = _to_bytes(payload)
    connect_id_bytes = connect_id.encode("utf-8") if connect_id else b""
    session_id_bytes = session_id.encode("utf-8") if session_id else b""
    has_event = (message_flags & DOUBAO_REALTIME_EVENT_FLAG) != 0

    optional_size = 0
    if message_type == DoubaoRealtimeMessageType.ERROR_INFORMATION:
        optional_size += 4
    if _has_sequence_field(message_flags):
        optional_size += 4
    if has_event:
        optional_size += 4
    if connect_id_bytes:
        optional_size += 4 + len(connect_id_bytes)
    if session_id_bytes:
        optional_size += 4 + len(session_id_bytes)

    total_size = 4 + optional_size + 4 + len(payload_bytes)
    output = bytearray(total_size)
    output[0] = (DOUBAO_REALTIME_PROTOCOL_VERSION << 4) | DOUBAO_REALTIME_HEADER_SIZE_WORDS
    output[1] = ((message_type & 0x0F) << 4) | (message_flags & 0x0F)
    output[2] = ((serialization & 0x0F) << 4) | (compression & 0x0F)
    output[3] = 0

    offset = 4

    def write_int32(value: int) -> None:
        nonlocal offset
        output[offset : offset + 4] = pack(">i", value)
        offset += 4

    if message_type == DoubaoRealtimeMessageType.ERROR_INFORMATION:
        write_int32(error_code or 0)
    if _has_sequence_field(message_flags):
        write_int32(sequence or 0)
    if has_event:
        write_int32(event or 0)
    if connect_id_bytes:
        write_int32(len(connect_id_bytes))
        output[offset : offset + len(connect_id_bytes)] = connect_id_bytes
        offset += len(connect_id_bytes)
    if session_id_bytes:
        write_int32(len(session_id_bytes))
        output[offset : offset + len(session_id_bytes)] = session_id_bytes
        offset += len(session_id_bytes)

    write_int32(len(payload_bytes))
    output[offset : offset + len(payload_bytes)] = payload_bytes
    return bytes(output)


def parse_doubao_realtime_frame(input_bytes: bytes | bytearray | memoryview) -> ParsedDoubaoRealtimeFrame:
    data = bytes(input_bytes)
    if len(data) < 8:
        raise SpeechProxyError(
            code="speech_proxy_protocol_error",
            message="Doubao realtime frame is too short.",
            status_code=502,
        )

    protocol_version = (data[0] >> 4) & 0x0F
    header_size_words = data[0] & 0x0F
    message_type = (data[1] >> 4) & 0x0F
    message_flags = data[1] & 0x0F
    serialization = (data[2] >> 4) & 0x0F
    compression = data[2] & 0x0F
    has_event = (message_flags & DOUBAO_REALTIME_EVENT_FLAG) != 0

    offset = header_size_words * 4
    error_code: int | None = None
    sequence: int | None = None
    event: int | None = None
    connect_id: str | None = None
    session_id: str | None = None

    def read_int32() -> int:
        nonlocal offset
        value = unpack_from(">i", data, offset)[0]
        offset += 4
        return value

    if message_type == DoubaoRealtimeMessageType.ERROR_INFORMATION:
        error_code = read_int32()
    if _has_sequence_field(message_flags):
        sequence = read_int32()
    if has_event:
        event = read_int32()
    if event is not None and event in DOUBAO_REALTIME_CONNECT_EVENT_IDS:
        connect_id_size = read_int32()
        if connect_id_size > 0:
            connect_id = data[offset : offset + connect_id_size].decode("utf-8")
            offset += connect_id_size
    if event is not None and event in DOUBAO_REALTIME_SESSION_EVENT_IDS:
        session_id_size = read_int32()
        if session_id_size > 0:
            session_id = data[offset : offset + session_id_size].decode("utf-8")
            offset += session_id_size

    payload_size = read_int32()
    payload = data[offset : offset + payload_size]
    return ParsedDoubaoRealtimeFrame(
        protocol_version=protocol_version,
        header_size_words=header_size_words,
        message_type=message_type,
        message_flags=message_flags,
        serialization=serialization,
        compression=compression,
        error_code=error_code,
        sequence=sequence,
        event=event,
        connect_id=connect_id,
        session_id=session_id,
        payload_size=payload_size,
        payload=payload,
    )


def decode_doubao_realtime_text_payload(payload: bytes) -> str:
    return payload.decode("utf-8")


def _decode_frame_payload(frame: ParsedDoubaoRealtimeFrame) -> str:
    payload = frame.payload
    if frame.compression == DoubaoRealtimeCompressionMethod.GZIP:
        payload = gzip.decompress(payload)
    return decode_doubao_realtime_text_payload(payload)


def _normalize_upstream_payload_text(payload_text: str) -> dict[str, Any]:
    if not payload_text:
        return {}
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError:
        return {"raw_payload": payload_text}


def _build_start_session_payload(message: dict[str, Any], config: DoubaoRealtimeConfig) -> str:
    asr = message.get("asr") if isinstance(message.get("asr"), dict) else {}
    audio_info = asr.get("audio_info") if isinstance(asr.get("audio_info"), dict) else {}
    dialog = message.get("dialog") if isinstance(message.get("dialog"), dict) else {}
    dialog_extra = dialog.get("extra") if isinstance(dialog.get("extra"), dict) else {}
    return json.dumps(
        {
            "asr": {
                "audio_info": {
                    "format": audio_info.get("format") or "pcm",
                    "sample_rate": audio_info.get("sample_rate") or 16000,
                    "channel": audio_info.get("channel") or 1,
                },
                "extra": asr.get("extra") if isinstance(asr.get("extra"), dict) else {},
            },
            "dialog": {
                "extra": {
                    "input_mod": "push_to_talk",
                    "model": dialog_extra.get("model")
                    or message.get("model")
                    or config.model,
                    **dialog_extra,
                }
            },
        }
    )


async def open_doubao_realtime_upstream(
    start_message: dict[str, Any],
) -> DoubaoRealtimeUpstreamConnection:
    config = resolve_doubao_realtime_config()
    session_id = str(uuid4())
    connect_id = str(uuid4())
    client_session = aiohttp.ClientSession()
    try:
        websocket = await client_session.ws_connect(
            DOUBAO_REALTIME_WS_URL,
            headers={
                "X-Api-App-ID": config.app_id,
                "X-Api-Access-Key": config.access_key,
                "X-Api-Resource-Id": config.resource_id,
                "X-Api-App-Key": config.app_key,
                "X-Api-Connect-Id": connect_id,
            },
            autoping=True,
        )
    except Exception as exc:
        await client_session.close()
        raise SpeechProxyError(
            code="speech_proxy_upstream_error",
            message="Doubao realtime ASR upstream connection failed.",
            status_code=502,
            details={"upstream_error": str(exc)},
        ) from exc

    try:
        await websocket.send_bytes(
            build_doubao_realtime_frame(
                message_type=DoubaoRealtimeMessageType.FULL_CLIENT_REQUEST,
                message_flags=DOUBAO_REALTIME_EVENT_FLAG,
                serialization=DoubaoRealtimeSerializationMethod.JSON,
                event=1,
                payload="{}",
            )
        )
        await websocket.send_bytes(
            build_doubao_realtime_frame(
                message_type=DoubaoRealtimeMessageType.FULL_CLIENT_REQUEST,
                message_flags=DOUBAO_REALTIME_EVENT_FLAG,
                serialization=DoubaoRealtimeSerializationMethod.JSON,
                event=100,
                session_id=session_id,
                payload=_build_start_session_payload(start_message, config),
            )
        )
    except Exception as exc:
        await websocket.close()
        await client_session.close()
        raise SpeechProxyError(
            code="speech_proxy_upstream_error",
            message="Doubao realtime ASR upstream bootstrap failed.",
            status_code=502,
            details={"upstream_error": str(exc)},
        ) from exc

    return DoubaoRealtimeUpstreamConnection(
        client_session=client_session,
        websocket=websocket,
        session_id=session_id,
        connect_id=connect_id,
    )


class DoubaoRealtimeAsrBridge:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.upstream: DoubaoRealtimeUpstreamConnection | None = None
        self.upstream_task: asyncio.Task[None] | None = None
        self.session_started = False
        self.closing = False
        self.bridge_id = str(uuid4())
        self.client = _client_label(websocket)
        self.started_at = time.perf_counter()
        self.ready_at: float | None = None
        self.audio_bytes_sent = 0

    async def run(self) -> None:
        await self.websocket.accept()
        logger.info(
            "Speech proxy ASR connected request_id=%s client=%s",
            self.bridge_id,
            self.client,
        )
        try:
            while True:
                message = await self.websocket.receive()
                message_type = message.get("type")
                if message_type == "websocket.disconnect":
                    break

                if message_type != "websocket.receive":
                    continue

                if message.get("bytes") is not None:
                    await self._handle_binary(message["bytes"])
                    continue

                if message.get("text") is not None:
                    await self._handle_text(message["text"])
        except WebSocketDisconnect:
            pass
        finally:
            await self._close_upstream()

    async def _handle_text(self, raw_text: str) -> None:
        try:
            message = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            await self._send_error(
                SpeechProxyError(
                    code="speech_proxy_invalid_request",
                    message="Doubao realtime ASR proxy received invalid JSON.",
                    status_code=400,
                    details={"error": str(exc)},
                )
            )
            return

        if not isinstance(message, dict):
            await self._send_error(
                SpeechProxyError(
                    code="speech_proxy_invalid_request",
                    message="Doubao realtime ASR proxy requires object messages.",
                    status_code=400,
                )
            )
            return

        message_type = message.get("type")
        if message_type == "end_asr":
            await self._send_end_asr()
            return

        if message_type != "start":
            await self._send_error(
                SpeechProxyError(
                    code="speech_proxy_invalid_request",
                    message="Doubao realtime ASR proxy requires a start message before streaming audio.",
                    status_code=400,
                )
            )
            return

        if self.upstream is not None:
            return

        logger.info(
            "Speech proxy ASR start request_id=%s client=%s model=%s",
            self.bridge_id,
            self.client,
            message.get("model") or "default",
        )
        try:
            self.upstream = await open_doubao_realtime_upstream(message)
        except SpeechProxyError as exc:
            await self._send_error(exc)
            return

        self.upstream_task = asyncio.create_task(self._relay_upstream_messages())

    async def _handle_binary(self, payload: bytes) -> None:
        if (
            self.upstream is None
            or not self.session_started
            or self.upstream.websocket.closed
        ):
            return

        self.audio_bytes_sent += len(payload)
        await self.upstream.websocket.send_bytes(
            build_doubao_realtime_frame(
                message_type=DoubaoRealtimeMessageType.AUDIO_ONLY_REQUEST,
                message_flags=DOUBAO_REALTIME_EVENT_FLAG,
                serialization=DoubaoRealtimeSerializationMethod.RAW,
                event=200,
                session_id=self.upstream.session_id,
                payload=payload,
            )
        )

    async def _send_end_asr(self) -> None:
        if (
            self.upstream is None
            or not self.session_started
            or self.upstream.websocket.closed
        ):
            return

        await self.upstream.websocket.send_bytes(
            build_doubao_realtime_frame(
                message_type=DoubaoRealtimeMessageType.FULL_CLIENT_REQUEST,
                message_flags=DOUBAO_REALTIME_EVENT_FLAG,
                serialization=DoubaoRealtimeSerializationMethod.JSON,
                event=400,
                session_id=self.upstream.session_id,
                payload="{}",
            )
        )

    async def _relay_upstream_messages(self) -> None:
        assert self.upstream is not None
        try:
            while True:
                message = await self.upstream.websocket.receive()
                if message.type == WSMsgType.BINARY:
                    await self._handle_upstream_binary(message)
                    continue
                if message.type == WSMsgType.ERROR:
                    raise SpeechProxyError(
                        code="speech_proxy_upstream_error",
                        message="Doubao realtime ASR upstream websocket failed.",
                        status_code=502,
                        details={"upstream_error": str(self.upstream.websocket.exception())},
                    )
                if message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING}:
                    break
        except SpeechProxyError as exc:
            await self._send_error(exc)
        except Exception as exc:
            await self._send_error(
                SpeechProxyError(
                    code="speech_proxy_internal_error",
                    message="Doubao realtime ASR proxy crashed while relaying upstream events.",
                    status_code=500,
                    details={"error": str(exc)},
                )
            )
        finally:
            if self.websocket.client_state == WebSocketState.CONNECTED:
                await self.websocket.close()

    async def _handle_upstream_binary(self, message: WSMessage) -> None:
        try:
            frame = parse_doubao_realtime_frame(message.data)
        except SpeechProxyError as exc:
            await self._send_error(exc)
            return

        if frame.message_type == DoubaoRealtimeMessageType.AUDIO_ONLY_RESPONSE:
            return

        payload = _normalize_upstream_payload_text(_decode_frame_payload(frame))
        event = frame.event

        if event == 50:
            await self.websocket.send_json({"type": "connection-started"})
            return
        if event == 150:
            self.session_started = True
            self.ready_at = time.perf_counter()
            logger.info(
                "Speech proxy ASR ready request_id=%s client=%s upstream_session_id=%s connect_id=%s dialog_id=%s ready_ms=%s",
                self.bridge_id,
                self.client,
                self.upstream.session_id if self.upstream else "unknown",
                self.upstream.connect_id if self.upstream else "unknown",
                payload.get("dialog_id"),
                _ready_elapsed_ms(self.started_at, self.ready_at),
            )
            await self.websocket.send_json(
                {
                    "type": "ready",
                    "sessionId": self.upstream.session_id if self.upstream else None,
                    "dialogId": payload.get("dialog_id"),
                }
            )
            return
        if event == 450:
            await self.websocket.send_json(
                {
                    "type": "asr-info",
                    "questionId": payload.get("question_id"),
                    "payload": payload,
                }
            )
            return
        if event == 451:
            await self.websocket.send_json(
                {
                    "type": "asr-response",
                    "results": payload.get("results") or [],
                    "payload": payload,
                }
            )
            return
        if event == 459:
            await self.websocket.send_json({"type": "asr-ended"})
            return
        if event in {51, 153, 599}:
            await self._send_error(
                SpeechProxyError(
                    code="speech_proxy_upstream_error",
                    message="Doubao realtime ASR upstream returned an error event.",
                    status_code=502,
                    details={
                        "event": event,
                        "upstream_status": payload.get("status_code")
                        or frame.error_code,
                        "upstream_message": payload.get("message")
                        or payload.get("error"),
                        "request_id": payload.get("request_id"),
                    },
                )
            )

    async def _send_error(self, error: SpeechProxyError) -> None:
        logger.warning(
            "Speech proxy ASR error request_id=%s client=%s upstream_session_id=%s ready_ms=%s code=%s details=%s",
            self.bridge_id,
            self.client,
            self.upstream.session_id if self.upstream else "unknown",
            _ready_elapsed_ms(self.started_at, self.ready_at)
            if self.ready_at is not None
            else "not-ready",
            error.code,
            error.details or {},
        )
        if self.websocket.client_state == WebSocketState.CONNECTED:
            await self.websocket.send_json(_ws_error_payload(error))

    async def _close_upstream(self) -> None:
        if self.closing:
            return
        self.closing = True

        if self.upstream_task is not None:
            self.upstream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.upstream_task

        if self.upstream is None:
            return

        try:
            if not self.upstream.websocket.closed and self.session_started:
                try:
                    await self.upstream.websocket.send_bytes(
                        build_doubao_realtime_frame(
                            message_type=DoubaoRealtimeMessageType.FULL_CLIENT_REQUEST,
                            message_flags=DOUBAO_REALTIME_EVENT_FLAG,
                            serialization=DoubaoRealtimeSerializationMethod.JSON,
                            event=102,
                            session_id=self.upstream.session_id,
                            payload="{}",
                        )
                    )
                    await self.upstream.websocket.send_bytes(
                        build_doubao_realtime_frame(
                            message_type=DoubaoRealtimeMessageType.FULL_CLIENT_REQUEST,
                            message_flags=DOUBAO_REALTIME_EVENT_FLAG,
                            serialization=DoubaoRealtimeSerializationMethod.JSON,
                            event=2,
                            payload="{}",
                        )
                    )
                except Exception:
                    pass
            await self.upstream.websocket.close()
        finally:
            await self.upstream.client_session.close()
            logger.info(
                "Speech proxy ASR closed request_id=%s client=%s upstream_session_id=%s connect_id=%s duration_ms=%s ready_ms=%s audio_bytes=%s",
                self.bridge_id,
                self.client,
                self.upstream.session_id,
                self.upstream.connect_id,
                _elapsed_ms(self.started_at),
                _ready_elapsed_ms(self.started_at, self.ready_at)
                if self.ready_at is not None
                else "not-ready",
                self.audio_bytes_sent,
            )


async def handle_doubao_realtime_asr_websocket(websocket: WebSocket) -> None:
    bridge = DoubaoRealtimeAsrBridge(websocket)
    await bridge.run()
