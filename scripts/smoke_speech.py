#!/usr/bin/env python3
"""Backend-native PepTutor speech smoke against a running LightRAG instance."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import aiohttp


DEFAULT_BASE_URL = "http://127.0.0.1:9625"
DEFAULT_TTS_TEXT = "PepTutor speech smoke test."
DEFAULT_TTS_PATH = "/api/peptutor/edge-tts"
DEFAULT_EDGE_TTS_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_DOUBAO_TTS_VOICE = "zh_female_vv_uranus_bigtts"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_ASR_SAMPLE_RATE = 16000
DEFAULT_ASR_CHANNELS = 1
DEFAULT_ASR_SECONDS = 1.0
DEFAULT_ASR_CHUNK_MS = 200


class SmokeFailure(RuntimeError):
    """A smoke check failed."""


@dataclass(slots=True)
class TtsSmokeResult:
    elapsed_ms: int
    content_type: str
    audio_bytes: int


@dataclass(slots=True)
class AsrSmokeResult:
    ready_ms: int
    elapsed_ms: int
    event_types: list[str]
    transcript_texts: list[str]


def _read_env(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _resolve_base_url() -> str:
    return _read_env("PEPTUTOR_SPEECH_SMOKE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _resolve_timeout_seconds() -> float:
    raw = _read_env("PEPTUTOR_SPEECH_SMOKE_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        return max(1.0, float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _resolve_asr_seconds() -> float:
    raw = _read_env("PEPTUTOR_SPEECH_SMOKE_ASR_SECONDS", str(DEFAULT_ASR_SECONDS))
    try:
        return max(0.2, float(raw))
    except ValueError:
        return DEFAULT_ASR_SECONDS


def _resolve_asr_chunk_ms() -> int:
    raw = _read_env("PEPTUTOR_SPEECH_SMOKE_ASR_CHUNK_MS", str(DEFAULT_ASR_CHUNK_MS))
    try:
        return max(20, int(raw))
    except ValueError:
        return DEFAULT_ASR_CHUNK_MS


def _resolve_tts_path() -> str:
    path = _read_env("PEPTUTOR_SPEECH_SMOKE_TTS_PATH", DEFAULT_TTS_PATH)
    return path if path.startswith("/") else f"/{path}"


def _resolve_tts_voice(path: str) -> str:
    configured_voice = _read_env("PEPTUTOR_SPEECH_SMOKE_TTS_VOICE")
    if configured_voice:
        return configured_voice
    if path.endswith("/doubao-tts"):
        return DEFAULT_DOUBAO_TTS_VOICE
    return DEFAULT_EDGE_TTS_VOICE


def _build_ws_url(base_url: str, path: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https", "ws", "wss"}:
        raise SmokeFailure(f"Unsupported base URL scheme: {base_url}")

    ws_scheme = parsed.scheme
    if ws_scheme == "http":
        ws_scheme = "ws"
    elif ws_scheme == "https":
        ws_scheme = "wss"

    normalized_path = path if path.startswith("/") else f"/{path}"
    return urlunparse((ws_scheme, parsed.netloc, normalized_path, "", "", ""))


def _load_pcm_bytes() -> bytes:
    audio_file = _read_env("PEPTUTOR_SPEECH_SMOKE_AUDIO_FILE")
    if audio_file:
        return Path(audio_file).read_bytes()

    sample_count = int(DEFAULT_ASR_SAMPLE_RATE * _resolve_asr_seconds())
    return b"\x00\x00" * sample_count * DEFAULT_ASR_CHANNELS


def _chunk_audio(audio_bytes: bytes) -> list[bytes]:
    bytes_per_sample = 2
    chunk_samples = int(DEFAULT_ASR_SAMPLE_RATE * (_resolve_asr_chunk_ms() / 1000.0))
    chunk_size = max(bytes_per_sample, chunk_samples * bytes_per_sample * DEFAULT_ASR_CHANNELS)
    return [audio_bytes[index : index + chunk_size] for index in range(0, len(audio_bytes), chunk_size)]


def _shorten(value: str, limit: int = 200) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def _extract_transcript(message: dict[str, Any]) -> str:
    strings: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                strings.append(normalized)
            return
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if isinstance(value, dict):
            for key in (
                "text",
                "transcript",
                "utterance",
                "sentence",
                "content",
                "message",
                "result",
                "results",
                "utterances",
                "sentences",
                "alternatives",
                "chunks",
                "paragraphs",
                "payload",
            ):
                if key in value:
                    visit(value[key])

    visit(message.get("results"))
    visit(message.get("payload"))

    deduped: list[str] = []
    for value in strings:
        if value not in deduped:
            deduped.append(value)
    return "\n".join(deduped).strip()


async def run_tts_smoke(session: aiohttp.ClientSession, base_url: str, timeout_seconds: float) -> TtsSmokeResult:
    tts_path = _resolve_tts_path()
    request_url = f"{base_url}{tts_path}"
    request_body = {
        "input": _read_env("PEPTUTOR_SPEECH_SMOKE_TTS_TEXT", DEFAULT_TTS_TEXT),
        "voice": _resolve_tts_voice(tts_path),
    }

    started_at = time.perf_counter()
    try:
        async with session.post(request_url, json=request_body, timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as response:
            payload = await response.read()
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            content_type = response.headers.get("Content-Type", "")

            if response.status != 200:
                raise SmokeFailure(
                    f"TTS returned HTTP {response.status}: {_shorten(payload.decode('utf-8', errors='replace'))}"
                )
            if not payload:
                raise SmokeFailure("TTS returned HTTP 200 with an empty body.")
            if not content_type.startswith("audio/"):
                raise SmokeFailure(f"TTS returned unexpected content type: {content_type or '<missing>'}")

            return TtsSmokeResult(
                elapsed_ms=elapsed_ms,
                content_type=content_type,
                audio_bytes=len(payload),
            )
    except aiohttp.ClientError as exc:
        raise SmokeFailure(f"TTS request failed: {exc}") from exc


async def _receive_json(
    websocket: aiohttp.ClientWebSocketResponse,
    timeout_seconds: float,
) -> dict[str, Any]:
    while True:
        try:
            message = await asyncio.wait_for(websocket.receive(), timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise SmokeFailure("ASR timed out while waiting for a websocket event.") from exc

        if message.type == aiohttp.WSMsgType.TEXT:
            try:
                payload = json.loads(message.data)
            except json.JSONDecodeError as exc:
                raise SmokeFailure(f"ASR returned invalid JSON: {message.data}") from exc
            if isinstance(payload, dict):
                return payload
            raise SmokeFailure(f"ASR returned a non-object JSON message: {payload!r}")

        if message.type == aiohttp.WSMsgType.CLOSED:
            raise SmokeFailure("ASR websocket closed before the smoke completed.")
        if message.type == aiohttp.WSMsgType.ERROR:
            raise SmokeFailure(f"ASR websocket errored: {websocket.exception()}")
        if message.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING}:
            raise SmokeFailure("ASR websocket is closing before the smoke completed.")


async def run_asr_smoke(session: aiohttp.ClientSession, base_url: str, timeout_seconds: float) -> AsrSmokeResult:
    request_url = _build_ws_url(base_url, "/api/peptutor/doubao-realtime-asr")
    audio_chunks = _chunk_audio(_load_pcm_bytes())
    started_at = time.perf_counter()
    ready_ms: int | None = None
    event_types: list[str] = []
    transcript_texts: list[str] = []

    try:
        async with session.ws_connect(
            request_url,
            autoping=True,
            heartbeat=15.0,
            timeout=timeout_seconds,
        ) as websocket:
            await websocket.send_json({"type": "start"})

            while ready_ms is None:
                payload = await _receive_json(websocket, timeout_seconds)
                event_type = str(payload.get("type") or "")
                if event_type:
                    event_types.append(event_type)

                if event_type == "error":
                    raise SmokeFailure(f"ASR returned an error before ready: {_shorten(json.dumps(payload, ensure_ascii=False))}")
                if event_type == "ready":
                    ready_ms = int((time.perf_counter() - started_at) * 1000)
                    break

            for chunk in audio_chunks:
                await websocket.send_bytes(chunk)

            await websocket.send_json({"type": "end_asr"})

            deadline = time.perf_counter() + timeout_seconds
            while time.perf_counter() < deadline:
                payload = await _receive_json(websocket, max(0.1, deadline - time.perf_counter()))
                event_type = str(payload.get("type") or "")
                if event_type:
                    event_types.append(event_type)

                if event_type == "error":
                    raise SmokeFailure(f"ASR returned an error after streaming audio: {_shorten(json.dumps(payload, ensure_ascii=False))}")

                if event_type in {"asr-info", "asr-response"}:
                    transcript = _extract_transcript(payload)
                    if transcript:
                        transcript_texts.append(transcript)

                if event_type == "asr-ended":
                    return AsrSmokeResult(
                        ready_ms=ready_ms,
                        elapsed_ms=int((time.perf_counter() - started_at) * 1000),
                        event_types=event_types,
                        transcript_texts=transcript_texts,
                    )

            raise SmokeFailure("ASR did not emit asr-ended before the timeout elapsed.")
    except aiohttp.ClientError as exc:
        raise SmokeFailure(f"ASR websocket connection failed: {exc}") from exc


async def async_main() -> int:
    base_url = _resolve_base_url()
    timeout_seconds = _resolve_timeout_seconds()
    session_timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    print(f"[INFO] Speech smoke target: {base_url}")
    tts_path = _resolve_tts_path()
    print(f"[INFO] TTS route: {tts_path}")
    print(f"[INFO] TTS voice: {_resolve_tts_voice(tts_path)}")
    if _read_env("PEPTUTOR_SPEECH_SMOKE_AUDIO_FILE"):
        print(f"[INFO] ASR audio file: {_read_env('PEPTUTOR_SPEECH_SMOKE_AUDIO_FILE')}")
    else:
        print(
            "[INFO] ASR audio source: generated silence "
            f"({DEFAULT_ASR_SAMPLE_RATE}Hz, mono, s16le, {_resolve_asr_seconds():.1f}s)"
        )

    async with aiohttp.ClientSession(timeout=session_timeout) as session:
        try:
            tts_result = await run_tts_smoke(session, base_url, timeout_seconds)
            print(
                f"[PASS] TTS HTTP 200 in {tts_result.elapsed_ms}ms "
                f"({tts_result.content_type}, {tts_result.audio_bytes} bytes)"
            )

            asr_result = await run_asr_smoke(session, base_url, timeout_seconds)
            transcript_summary = (
                _shorten(" | ".join(asr_result.transcript_texts))
                if asr_result.transcript_texts
                else "<none>"
            )
            print(
                f"[PASS] ASR websocket ready in {asr_result.ready_ms}ms, "
                f"completed in {asr_result.elapsed_ms}ms "
                f"(events={','.join(asr_result.event_types)}, transcripts={transcript_summary})"
            )
            print("[PASS] Speech smoke completed.")
            return 0
        except SmokeFailure as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            print("[FAIL] Speech smoke failed.", file=sys.stderr)
            return 1


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
