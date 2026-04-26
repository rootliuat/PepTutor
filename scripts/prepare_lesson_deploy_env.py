#!/usr/bin/env python3
"""Generate deploy/lesson env files from the current local PepTutor env files."""

from __future__ import annotations

import argparse
import sys
from collections import OrderedDict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = [
    ROOT_DIR / ".env",
    ROOT_DIR / "backend" / "LightRAG" / ".env",
]
DEFAULT_BACKEND_OUT = ROOT_DIR / "deploy" / "lesson" / "backend.env"
DEFAULT_FRONTEND_OUT = ROOT_DIR / "deploy" / "lesson" / "frontend.env"


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            continue
        if value and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _load_sources(paths: list[Path]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in paths:
        merged.update(_parse_env_file(path))
    return merged


def _first_non_empty(env: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = env.get(key, "").strip()
        if value:
            return value
    return ""


def _require(env: dict[str, str], label: str, *keys: str) -> str:
    value = _first_non_empty(env, *keys)
    if value:
        return value
    raise ValueError(f"Missing required value for {label}: expected one of {', '.join(keys)}")


def _build_backend_env(env: dict[str, str]) -> OrderedDict[str, str]:
    backend = OrderedDict[str, str]()
    backend["HOST"] = _first_non_empty(env, "HOST") or "0.0.0.0"
    backend["PORT"] = _first_non_empty(env, "PORT") or "9621"
    backend["PEPTUTOR_REQUIRE_REMOTE_MODELS"] = "1"
    backend["LLM_BINDING"] = _require(env, "LLM binding", "LLM_BINDING")
    backend["LLM_BINDING_HOST"] = _require(
        env,
        "LLM binding host",
        "LLM_BINDING_HOST",
        "OPENAI_API_BASE",
        "OPENAI_BASE_URL",
    )
    backend["LLM_BINDING_API_KEY"] = _require(
        env,
        "LLM API key",
        "LLM_BINDING_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
    )
    backend["LLM_MODEL"] = _require(env, "LLM model", "LLM_MODEL")
    backend["EMBEDDING_BINDING"] = _require(env, "Embedding binding", "EMBEDDING_BINDING")
    backend["EMBEDDING_BINDING_HOST"] = _require(
        env,
        "Embedding binding host",
        "EMBEDDING_BINDING_HOST",
    )
    backend["EMBEDDING_BINDING_API_KEY"] = _require(
        env,
        "Embedding API key",
        "EMBEDDING_BINDING_API_KEY",
        "OPENAI_API_KEY",
    )
    backend["EMBEDDING_MODEL"] = _require(env, "Embedding model", "EMBEDDING_MODEL")
    backend["EMBEDDING_DIM"] = _require(env, "Embedding dimension", "EMBEDDING_DIM")

    backend["PEPTUTOR_LESSON_LIVE_PROMPTS"] = _first_non_empty(
        env, "PEPTUTOR_LESSON_LIVE_PROMPTS"
    ) or "1"
    backend["PEPTUTOR_LESSON_VECTOR_RETRIEVAL"] = "0"
    backend["PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION"] = _first_non_empty(
        env, "PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION"
    ) or "1"
    backend["PEPTUTOR_SIMPLEMEM_WRITEBACK"] = _first_non_empty(
        env, "PEPTUTOR_SIMPLEMEM_WRITEBACK"
    ) or "1"
    backend["PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL"] = _first_non_empty(
        env, "PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL"
    ) or "1"
    backend["PEPTUTOR_SIMPLEMEM_PROJECT"] = _first_non_empty(
        env, "PEPTUTOR_SIMPLEMEM_PROJECT"
    ) or "peptutor-lesson"

    backend["PEPTUTOR_LESSON_RATE_LIMIT_REQUESTS"] = _first_non_empty(
        env, "PEPTUTOR_LESSON_RATE_LIMIT_REQUESTS"
    ) or "60"
    backend["PEPTUTOR_LESSON_RATE_LIMIT_WINDOW_SECONDS"] = _first_non_empty(
        env, "PEPTUTOR_LESSON_RATE_LIMIT_WINDOW_SECONDS"
    ) or "60"
    backend["PEPTUTOR_SPEECH_TTS_RATE_LIMIT_REQUESTS"] = _first_non_empty(
        env, "PEPTUTOR_SPEECH_TTS_RATE_LIMIT_REQUESTS"
    ) or "20"
    backend["PEPTUTOR_SPEECH_TTS_RATE_LIMIT_WINDOW_SECONDS"] = _first_non_empty(
        env, "PEPTUTOR_SPEECH_TTS_RATE_LIMIT_WINDOW_SECONDS"
    ) or "60"
    backend["PEPTUTOR_SPEECH_ASR_CONNECT_RATE_LIMIT_REQUESTS"] = _first_non_empty(
        env, "PEPTUTOR_SPEECH_ASR_CONNECT_RATE_LIMIT_REQUESTS"
    ) or "6"
    backend["PEPTUTOR_SPEECH_ASR_CONNECT_RATE_LIMIT_WINDOW_SECONDS"] = _first_non_empty(
        env, "PEPTUTOR_SPEECH_ASR_CONNECT_RATE_LIMIT_WINDOW_SECONDS"
    ) or "60"

    backend["PEPTUTOR_DOUBAO_TTS_APP_ID"] = _require(
        env,
        "Doubao TTS app id",
        "PEPTUTOR_DOUBAO_TTS_APP_ID",
        "VITE_PEPTUTOR_TTS_APP_ID",
        "VITE_DOUBAO_TTS_APP_ID",
        "PEPTUTOR_DOUBAO_ASR_APP_ID",
        "VITE_PEPTUTOR_ASR_APP_ID",
        "VITE_DOUBAO_ASR_APP_ID",
    )
    backend["PEPTUTOR_DOUBAO_TTS_API_KEY"] = _require(
        env,
        "Doubao TTS API key",
        "PEPTUTOR_DOUBAO_TTS_API_KEY",
        "VITE_PEPTUTOR_TTS_API_KEY",
        "VITE_DOUBAO_TTS_API_KEY",
        "PEPTUTOR_DOUBAO_ASR_API_KEY",
        "VITE_PEPTUTOR_ASR_API_KEY",
        "VITE_DOUBAO_ASR_API_KEY",
    )
    backend["PEPTUTOR_DOUBAO_TTS_CLUSTER"] = _first_non_empty(
        env,
        "PEPTUTOR_DOUBAO_TTS_CLUSTER",
        "VITE_PEPTUTOR_TTS_CLUSTER",
        "VITE_DOUBAO_TTS_CLUSTER",
    ) or "volcano_tts"

    backend["PEPTUTOR_DOUBAO_ASR_APP_ID"] = _require(
        env,
        "Doubao ASR app id",
        "PEPTUTOR_DOUBAO_ASR_APP_ID",
        "VITE_PEPTUTOR_ASR_APP_ID",
        "VITE_DOUBAO_ASR_APP_ID",
        "PEPTUTOR_DOUBAO_TTS_APP_ID",
        "VITE_PEPTUTOR_TTS_APP_ID",
        "VITE_DOUBAO_TTS_APP_ID",
    )
    backend["PEPTUTOR_DOUBAO_ASR_API_KEY"] = _require(
        env,
        "Doubao ASR API key",
        "PEPTUTOR_DOUBAO_ASR_API_KEY",
        "VITE_PEPTUTOR_ASR_API_KEY",
        "VITE_DOUBAO_ASR_API_KEY",
        "PEPTUTOR_DOUBAO_TTS_API_KEY",
        "VITE_PEPTUTOR_TTS_API_KEY",
        "VITE_DOUBAO_TTS_API_KEY",
    )
    backend["PEPTUTOR_DOUBAO_ASR_MODEL"] = _first_non_empty(
        env,
        "PEPTUTOR_DOUBAO_ASR_MODEL",
        "VITE_PEPTUTOR_ASR_MODEL",
        "VITE_DOUBAO_ASR_MODEL",
    ) or "1.2.1.1"
    backend["PEPTUTOR_DOUBAO_ASR_RESOURCE_ID"] = _first_non_empty(
        env,
        "PEPTUTOR_DOUBAO_ASR_RESOURCE_ID",
        "VITE_PEPTUTOR_ASR_RESOURCE_ID",
        "VITE_DOUBAO_ASR_RESOURCE_ID",
    ) or "volc.speech.dialog"
    backend["PEPTUTOR_DOUBAO_ASR_APP_KEY"] = _first_non_empty(
        env,
        "PEPTUTOR_DOUBAO_ASR_APP_KEY",
        "VITE_PEPTUTOR_ASR_APP_KEY",
        "VITE_DOUBAO_ASR_APP_KEY",
    ) or "PlgvMymc7f3tQnJ6"

    return backend


def _build_frontend_env(env: dict[str, str]) -> OrderedDict[str, str]:
    frontend = OrderedDict[str, str]()
    frontend["PEPTUTOR_BACKEND_UPSTREAM"] = _first_non_empty(
        env, "PEPTUTOR_BACKEND_UPSTREAM"
    ) or "http://peptutor-backend:9621"
    frontend["PEPTUTOR_RUNTIME_LESSON_API_URL"] = _first_non_empty(
        env,
        "PEPTUTOR_RUNTIME_LESSON_API_URL",
        "VITE_PEPTUTOR_LESSON_API_URL",
    ) or "/peptutor-api"
    frontend["PEPTUTOR_RUNTIME_TTS_PROVIDER"] = _first_non_empty(
        env,
        "PEPTUTOR_RUNTIME_TTS_PROVIDER",
        "VITE_PEPTUTOR_TTS_PROVIDER",
    ) or "volcengine"
    frontend["PEPTUTOR_RUNTIME_TTS_MODEL"] = _first_non_empty(
        env,
        "PEPTUTOR_RUNTIME_TTS_MODEL",
        "VITE_PEPTUTOR_TTS_MODEL",
    ) or "v1"
    frontend["PEPTUTOR_RUNTIME_TTS_VOICE"] = _first_non_empty(
        env,
        "PEPTUTOR_RUNTIME_TTS_VOICE",
        "VITE_PEPTUTOR_TTS_VOICE",
    ) or "zh_female_vv_uranus_bigtts"
    frontend["PEPTUTOR_RUNTIME_TTS_CLUSTER"] = _first_non_empty(
        env,
        "PEPTUTOR_RUNTIME_TTS_CLUSTER",
        "VITE_PEPTUTOR_TTS_CLUSTER",
    ) or "volcano_tts"
    frontend["PEPTUTOR_RUNTIME_ASR_PROVIDER"] = _first_non_empty(
        env,
        "PEPTUTOR_RUNTIME_ASR_PROVIDER",
        "VITE_PEPTUTOR_ASR_PROVIDER",
    ) or "volcengine-realtime-transcription"
    frontend["PEPTUTOR_RUNTIME_ASR_MODEL"] = _first_non_empty(
        env,
        "PEPTUTOR_RUNTIME_ASR_MODEL",
        "VITE_PEPTUTOR_ASR_MODEL",
    ) or "1.2.1.1"
    frontend["PEPTUTOR_RUNTIME_ASR_RESOURCE_ID"] = _first_non_empty(
        env,
        "PEPTUTOR_RUNTIME_ASR_RESOURCE_ID",
        "VITE_PEPTUTOR_ASR_RESOURCE_ID",
    ) or "volc.speech.dialog"
    frontend["PEPTUTOR_RUNTIME_ASR_APP_KEY"] = _first_non_empty(
        env,
        "PEPTUTOR_RUNTIME_ASR_APP_KEY",
        "VITE_PEPTUTOR_ASR_APP_KEY",
    ) or "PlgvMymc7f3tQnJ6"
    return frontend


def _render_env(title: str, values: OrderedDict[str, str]) -> str:
    lines = [
        f"# Generated by scripts/prepare_lesson_deploy_env.py for {title}.",
        "# Review before using in production; do not commit secrets.",
        "",
    ]
    lines.extend(f"{key}={value}" for key, value in values.items())
    lines.append("")
    return "\n".join(lines)


def _write_env_file(path: Path, title: str, values: OrderedDict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_env(title, values), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deploy/lesson env files from the current local env files."
    )
    parser.add_argument(
        "--backend-out",
        type=Path,
        default=DEFAULT_BACKEND_OUT,
        help=f"Backend env output path (default: {DEFAULT_BACKEND_OUT})",
    )
    parser.add_argument(
        "--frontend-out",
        type=Path,
        default=DEFAULT_FRONTEND_OUT,
        help=f"Frontend env output path (default: {DEFAULT_FRONTEND_OUT})",
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        type=Path,
        help="Additional env source file. Can be provided multiple times.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    sources = list(DEFAULT_SOURCES)
    if args.sources:
        sources.extend(args.sources)

    merged_env = _load_sources(sources)
    backend_values = _build_backend_env(merged_env)
    frontend_values = _build_frontend_env(merged_env)

    _write_env_file(args.backend_out, "deploy/lesson backend", backend_values)
    _write_env_file(args.frontend_out, "deploy/lesson frontend", frontend_values)

    print(f"[PASS] wrote {args.backend_out}")
    print(f"[PASS] wrote {args.frontend_out}")
    print("[INFO] lesson vector retrieval kept off for the competition deployment baseline")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
