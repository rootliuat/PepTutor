"""Shared environment/config helpers for PepTutor speech proxies."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from dotenv import dotenv_values

_BACKEND_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_REPO_ENV_PATH = Path(__file__).resolve().parents[4] / ".env"


@lru_cache(maxsize=1)
def load_speech_proxy_env_fallbacks() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (_REPO_ENV_PATH, _BACKEND_ENV_PATH):
        if not path.exists():
            continue
        for key, value in dotenv_values(path).items():
            if key and value:
                values[key] = value
    return values


def get_env_with_fallback(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value

    fallback_values = load_speech_proxy_env_fallbacks()
    for name in names:
        value = fallback_values.get(name, "").strip()
        if value:
            return value

    return ""
