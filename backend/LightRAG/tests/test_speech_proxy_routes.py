from __future__ import annotations

import asyncio
import hashlib
import importlib
import sys
from datetime import datetime, timedelta
from struct import unpack_from
from types import SimpleNamespace

import pytest
from aiohttp import WSMsgType
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

_PYTEST_ARGV = sys.argv[:]
sys.argv = [sys.argv[0]]
speech_routes_module = importlib.import_module("lightrag.api.speech_proxy_routes")
speech_ws_module = importlib.import_module("lightrag.api.speech_proxy_ws")
utils_api = importlib.import_module("lightrag.api.utils_api")
SpeechProxyError = speech_routes_module.SpeechProxyError
create_speech_proxy_routes = speech_routes_module.create_speech_proxy_routes
sys.argv = _PYTEST_ARGV


def _make_app(api_key: str | None = None):
    app = FastAPI()
    app.include_router(create_speech_proxy_routes(api_key))
    return app


def _frame_event(payload: bytes) -> int:
    return unpack_from(">i", payload, 4)[0]


def test_doubao_tts_route_returns_audio(monkeypatch):
    info_logs: list[str] = []

    def fake_info(message, *args):
        info_logs.append(message % args if args else message)

    async def fake_fetch(_request):
        return b"fake-mp3", "audio/mpeg"

    monkeypatch.setattr(speech_routes_module, "fetch_doubao_tts_audio", fake_fetch)
    monkeypatch.setattr(speech_routes_module.logger, "info", fake_info)

    client = TestClient(_make_app())
    response = client.post(
        "/api/peptutor/doubao-tts",
        headers={
            "Origin": "https://lesson.example.test",
            "Referer": "https://lesson.example.test/lesson?page_uid=TB-G5S1U3-P24",
            "User-Agent": "pytest-audit-agent",
            "X-Forwarded-For": "198.51.100.88",
            "X-PepTutor-Source-Tag": "lesson-runtime",
            "X-PepTutor-Source-Path": "/lesson",
            "X-PepTutor-Source-Page-Uid": "TB-G5S1U3-P24",
        },
        json={
            "input": "Hello world from lesson",
            "voice": "zh_female_vv_uranus_bigtts",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"fake-mp3"
    assert any("Speech proxy TTS start" in entry for entry in info_logs)
    assert any("Speech proxy TTS success" in entry for entry in info_logs)
    assert any("voice=zh_female_vv_uranus_bigtts" in entry for entry in info_logs)
    assert any("client_chain=198.51.100.88" in entry for entry in info_logs)
    assert any("source_tag=lesson-runtime" in entry for entry in info_logs)
    assert any("source_path=/lesson" in entry for entry in info_logs)
    assert any("source_page_uid=TB-G5S1U3-P24" in entry for entry in info_logs)
    assert any("origin=https://lesson.example.test" in entry for entry in info_logs)
    assert any("referer=https://lesson.example.test/lesson?page_uid=TB-G5S1U3-P24" in entry for entry in info_logs)
    assert any("user_agent=pytest-audit-agent" in entry for entry in info_logs)
    assert any("text_preview=Hello world from lesson" in entry for entry in info_logs)
    assert any(
        f"text_sha1={hashlib.sha1('Hello world from lesson'.encode('utf-8')).hexdigest()[:12]}" in entry
        for entry in info_logs
    )


def test_doubao_tts_route_rejects_unallowlisted_voice():
    client = TestClient(_make_app())
    response = client.post(
        "/api/peptutor/doubao-tts",
        json={
            "input": "Hello world",
            "voice": "zh_female_vv_u",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "speech_proxy_invalid_request",
            "message": "Doubao TTS proxy rejected an unallowlisted voice.",
            "details": {
                "allowed_voices": ["zh_female_vv_uranus_bigtts"],
                "voice": "zh_female_vv_u",
            },
        }
    }


def test_edge_tts_route_returns_audio(monkeypatch):
    info_logs: list[str] = []

    def fake_info(message, *args):
        info_logs.append(message % args if args else message)

    async def fake_fetch(_request):
        return b"fake-edge-mp3", "audio/mpeg"

    monkeypatch.setattr(speech_routes_module, "fetch_edge_tts_audio", fake_fetch)
    monkeypatch.setattr(speech_routes_module.logger, "info", fake_info)

    client = TestClient(_make_app())
    response = client.post(
        "/api/peptutor/edge-tts",
        headers={
            "Referer": "https://lesson.example.test/lesson?page_uid=TB-G5S1U3-P24",
            "X-PepTutor-Source-Tag": "lesson-runtime",
            "X-PepTutor-Source-Path": "/lesson",
            "X-PepTutor-Source-Page-Uid": "TB-G5S1U3-P24",
        },
        json={
            "input": "Hello from Edge Xiaoxiao",
            "voice": "zh-CN-XiaoxiaoNeural",
            "model": "edge-tts",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"fake-edge-mp3"
    assert any("Speech proxy TTS start" in entry for entry in info_logs)
    assert any("Speech proxy TTS success" in entry for entry in info_logs)
    assert any("provider=edge" in entry for entry in info_logs)
    assert any("voice=zh-CN-XiaoxiaoNeural" in entry for entry in info_logs)
    assert any("source_tag=lesson-runtime" in entry for entry in info_logs)
    assert any("source_page_uid=TB-G5S1U3-P24" in entry for entry in info_logs)
    assert any("text_preview=Hello from Edge Xiaoxiao" in entry for entry in info_logs)


def test_edge_tts_route_rejects_unallowlisted_voice():
    client = TestClient(_make_app())
    response = client.post(
        "/api/peptutor/edge-tts",
        json={
            "input": "Hello world",
            "voice": "en-US-GuyNeural",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "speech_proxy_invalid_request",
            "message": "Edge TTS proxy rejected an unallowlisted voice.",
            "details": {
                "allowed_voices": ["zh-CN-XiaoxiaoNeural"],
                "voice": "en-US-GuyNeural",
            },
        }
    }


def test_doubao_tts_route_normalizes_upstream_error(monkeypatch):
    warning_logs: list[str] = []

    def fake_warning(message, *args):
        warning_logs.append(message % args if args else message)

    async def fake_fetch(_request):
        raise SpeechProxyError(
            code="speech_proxy_upstream_error",
            message="Doubao TTS upstream returned an invalid response.",
            status_code=502,
            details={
                "upstream_status": 403,
                "upstream_code": 3001,
                "upstream_message": "resource not granted",
            },
        )

    monkeypatch.setattr(speech_routes_module, "fetch_doubao_tts_audio", fake_fetch)
    monkeypatch.setattr(speech_routes_module.logger, "warning", fake_warning)

    client = TestClient(_make_app())
    response = client.post(
        "/api/peptutor/doubao-tts",
        headers={
            "Referer": "https://lesson.example.test/lesson?page_uid=TB-G5S1U3-P24",
        },
        json={
            "input": "Hello world",
            "voice": "zh_female_vv_uranus_bigtts",
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "speech_proxy_upstream_error",
            "message": "Doubao TTS upstream returned an invalid response.",
            "details": {
                "upstream_status": 403,
                "upstream_code": 3001,
                "upstream_message": "resource not granted",
            },
        }
    }
    assert any("Speech proxy TTS error" in entry for entry in warning_logs)
    assert any("code=speech_proxy_upstream_error" in entry for entry in warning_logs)
    assert any("source_path=/lesson" in entry for entry in warning_logs)
    assert any("source_page_uid=TB-G5S1U3-P24" in entry for entry in warning_logs)
    assert any("text_preview=Hello world" in entry for entry in warning_logs)


def test_doubao_tts_route_requires_api_key_when_configured(monkeypatch):
    async def fake_fetch(_request):
        return b"fake-mp3", "audio/mpeg"

    monkeypatch.setattr(speech_routes_module, "fetch_doubao_tts_audio", fake_fetch)

    client = TestClient(_make_app(api_key="secret-key"))
    denied = client.post(
        "/api/peptutor/doubao-tts",
        json={
            "input": "Hello world",
            "voice": "zh_female_vv_uranus_bigtts",
        },
    )

    assert denied.status_code == 403
    assert denied.json() == {"detail": "API Key required"}

    allowed = client.post(
        "/api/peptutor/doubao-tts",
        headers={"X-API-Key": "secret-key"},
        json={
            "input": "Hello world",
            "voice": "zh_female_vv_uranus_bigtts",
        },
    )

    assert allowed.status_code == 200
    assert allowed.content == b"fake-mp3"


def test_doubao_tts_route_accepts_bearer_token_when_auth_configured(monkeypatch):
    async def fake_fetch(_request):
        return b"fake-mp3", "audio/mpeg"

    def fake_validate_token(token: str):
        assert token == "lesson-token"
        return {
            "username": "teacher",
            "role": "user",
            "metadata": {"auth_mode": "enabled"},
            "exp": datetime.utcnow() + timedelta(hours=4),
        }

    monkeypatch.setattr(speech_routes_module, "fetch_doubao_tts_audio", fake_fetch)
    monkeypatch.setattr(utils_api.auth_handler, "accounts", {"teacher": "secret"})
    monkeypatch.setattr(utils_api.auth_handler, "validate_token", fake_validate_token)

    client = TestClient(_make_app())
    response = client.post(
        "/api/peptutor/doubao-tts",
        headers={"Authorization": "Bearer lesson-token"},
        json={
            "input": "Hello world",
            "voice": "zh_female_vv_uranus_bigtts",
        },
    )

    assert response.status_code == 200
    assert response.content == b"fake-mp3"


def test_doubao_tts_route_applies_rate_limit(monkeypatch):
    async def fake_fetch(_request):
        return b"fake-mp3", "audio/mpeg"

    utils_api.reset_request_rate_limit_state()
    monkeypatch.setattr(speech_routes_module, "fetch_doubao_tts_audio", fake_fetch)
    monkeypatch.setattr(
        speech_routes_module.global_args,
        "peptutor_speech_tts_rate_limit_requests",
        1,
        raising=False,
    )
    monkeypatch.setattr(
        speech_routes_module.global_args,
        "peptutor_speech_tts_rate_limit_window_seconds",
        60,
        raising=False,
    )

    client = TestClient(_make_app())
    first = client.post(
        "/api/peptutor/doubao-tts",
        json={
            "input": "Hello world",
            "voice": "zh_female_vv_uranus_bigtts",
        },
    )
    second = client.post(
        "/api/peptutor/doubao-tts",
        json={
            "input": "Hello again",
            "voice": "zh_female_vv_uranus_bigtts",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json() == {"detail": "Too many requests. Please try again later."}
    assert second.headers["retry-after"] == "60"


class _FakeClientSession:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class _FakeUpstreamWebSocket:
    def __init__(self):
        self.closed = False
        self.sent_frames: list[bytes] = []
        self.messages: asyncio.Queue[SimpleNamespace] = asyncio.Queue()
        self._exception: Exception | None = None
        self._enqueue_event(50, {})
        self._enqueue_event(150, {"dialog_id": "dlg-1"})

    def _enqueue_event(self, event: int, payload: dict):
        frame = speech_ws_module.build_doubao_realtime_frame(
            message_type=speech_ws_module.DoubaoRealtimeMessageType.FULL_SERVER_RESPONSE,
            message_flags=speech_ws_module.DOUBAO_REALTIME_EVENT_FLAG,
            serialization=speech_ws_module.DoubaoRealtimeSerializationMethod.JSON,
            event=event,
            session_id="session-test",
            payload=speech_ws_module.json.dumps(payload),
        )
        self.messages.put_nowait(
            SimpleNamespace(type=WSMsgType.BINARY, data=frame, extra=None)
        )

    async def send_bytes(self, payload: bytes):
        self.sent_frames.append(payload)
        frame = speech_ws_module.parse_doubao_realtime_frame(payload)
        if frame.event == 400:
            self._enqueue_event(459, {})

    async def receive(self):
        if self.closed:
            return SimpleNamespace(type=WSMsgType.CLOSED, data=None, extra=None)
        return await self.messages.get()

    async def close(self):
        self.closed = True

    def exception(self):
        return self._exception


def test_doubao_asr_websocket_bridges_events_and_audio(monkeypatch):
    holder = {}

    async def fake_open(_start_message):
        connection = speech_ws_module.DoubaoRealtimeUpstreamConnection(
            client_session=_FakeClientSession(),
            websocket=_FakeUpstreamWebSocket(),
            session_id="session-test",
            connect_id="connect-test",
        )
        holder["connection"] = connection
        return connection

    monkeypatch.setattr(
        speech_ws_module, "open_doubao_realtime_upstream", fake_open
    )
    info_logs: list[str] = []

    def fake_info(message, *args):
        info_logs.append(message % args if args else message)

    monkeypatch.setattr(speech_ws_module.logger, "info", fake_info)

    client = TestClient(_make_app())
    with client.websocket_connect("/api/peptutor/doubao-realtime-asr") as websocket:
        websocket.send_json({"type": "start"})
        assert websocket.receive_json() == {"type": "connection-started"}
        assert websocket.receive_json() == {
            "type": "ready",
            "sessionId": "session-test",
            "dialogId": "dlg-1",
        }
        websocket.send_bytes(b"\x00\x01\x02")
        websocket.send_json({"type": "end_asr"})
        assert websocket.receive_json() == {"type": "asr-ended"}

    upstream = holder["connection"].websocket
    sent_events = [_frame_event(frame) for frame in upstream.sent_frames]
    assert sent_events == [200, 400, 102, 2]
    assert any("Speech proxy ASR connected" in entry for entry in info_logs)
    assert any("Speech proxy ASR start" in entry for entry in info_logs)
    assert any("Speech proxy ASR ready" in entry for entry in info_logs)
    assert any("upstream_session_id=session-test" in entry for entry in info_logs)
    assert any("Speech proxy ASR closed" in entry for entry in info_logs)
    assert any("audio_bytes=3" in entry for entry in info_logs)


def test_doubao_asr_websocket_rejects_missing_api_key_when_configured():
    client = TestClient(_make_app(api_key="secret-key"))

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/api/peptutor/doubao-realtime-asr"):
            pass

    assert excinfo.value.code == 1008


def test_doubao_asr_websocket_accepts_api_key_query_param_when_configured(monkeypatch):
    holder = {}

    async def fake_open(_start_message):
        connection = speech_ws_module.DoubaoRealtimeUpstreamConnection(
            client_session=_FakeClientSession(),
            websocket=_FakeUpstreamWebSocket(),
            session_id="session-test",
            connect_id="connect-test",
        )
        holder["connection"] = connection
        return connection

    monkeypatch.setattr(
        speech_ws_module, "open_doubao_realtime_upstream", fake_open
    )

    client = TestClient(_make_app(api_key="secret-key"))
    with client.websocket_connect(
        "/api/peptutor/doubao-realtime-asr?api_key=secret-key"
    ) as websocket:
        websocket.send_json({"type": "start"})
        assert websocket.receive_json() == {"type": "connection-started"}
        assert websocket.receive_json() == {
            "type": "ready",
            "sessionId": "session-test",
            "dialogId": "dlg-1",
        }
        websocket.send_json({"type": "end_asr"})
        assert websocket.receive_json() == {"type": "asr-ended"}

    assert holder["connection"].websocket.closed


def test_doubao_asr_websocket_applies_connection_rate_limit(monkeypatch):
    holder = {}

    async def fake_open(_start_message):
        connection = speech_ws_module.DoubaoRealtimeUpstreamConnection(
            client_session=_FakeClientSession(),
            websocket=_FakeUpstreamWebSocket(),
            session_id="session-test",
            connect_id="connect-test",
        )
        holder["connection"] = connection
        return connection

    utils_api.reset_request_rate_limit_state()
    monkeypatch.setattr(
        speech_ws_module, "open_doubao_realtime_upstream", fake_open
    )
    monkeypatch.setattr(
        speech_routes_module.global_args,
        "peptutor_speech_asr_connect_rate_limit_requests",
        1,
        raising=False,
    )
    monkeypatch.setattr(
        speech_routes_module.global_args,
        "peptutor_speech_asr_connect_rate_limit_window_seconds",
        60,
        raising=False,
    )

    client = TestClient(_make_app())
    with client.websocket_connect("/api/peptutor/doubao-realtime-asr") as websocket:
        websocket.send_json({"type": "start"})
        assert websocket.receive_json() == {"type": "connection-started"}
        assert websocket.receive_json() == {
            "type": "ready",
            "sessionId": "session-test",
            "dialogId": "dlg-1",
        }
        websocket.send_json({"type": "end_asr"})
        assert websocket.receive_json() == {"type": "asr-ended"}

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/api/peptutor/doubao-realtime-asr"):
            pass

    assert excinfo.value.code == 1008


def test_doubao_asr_websocket_normalizes_upstream_error(monkeypatch):
    fake_ws = _FakeUpstreamWebSocket()
    fake_ws.messages = asyncio.Queue()
    error_frame = speech_ws_module.build_doubao_realtime_frame(
        message_type=speech_ws_module.DoubaoRealtimeMessageType.FULL_SERVER_RESPONSE,
        message_flags=speech_ws_module.DOUBAO_REALTIME_EVENT_FLAG,
        serialization=speech_ws_module.DoubaoRealtimeSerializationMethod.JSON,
        event=153,
        session_id="session-test",
        payload=speech_ws_module.json.dumps(
            {
                "status_code": 401,
                "message": "authentication failed",
                "request_id": "req-1",
            }
        ),
    )
    fake_ws.messages.put_nowait(
        SimpleNamespace(type=WSMsgType.BINARY, data=error_frame, extra=None)
    )

    async def fake_open(_start_message):
        return speech_ws_module.DoubaoRealtimeUpstreamConnection(
            client_session=_FakeClientSession(),
            websocket=fake_ws,
            session_id="session-test",
            connect_id="connect-test",
        )

    monkeypatch.setattr(
        speech_ws_module, "open_doubao_realtime_upstream", fake_open
    )
    warning_logs: list[str] = []

    def fake_warning(message, *args):
        warning_logs.append(message % args if args else message)

    monkeypatch.setattr(speech_ws_module.logger, "warning", fake_warning)

    client = TestClient(_make_app())
    with client.websocket_connect("/api/peptutor/doubao-realtime-asr") as websocket:
        websocket.send_json({"type": "start"})
        assert websocket.receive_json() == {
            "type": "error",
            "error": "Doubao realtime ASR upstream returned an error event.",
            "code": "speech_proxy_upstream_error",
            "details": {
                "event": 153,
                "upstream_status": 401,
                "upstream_message": "authentication failed",
                "request_id": "req-1",
            },
            "statusCode": 401,
        }
    assert any("Speech proxy ASR error" in entry for entry in warning_logs)
    assert any("code=speech_proxy_upstream_error" in entry for entry in warning_logs)
