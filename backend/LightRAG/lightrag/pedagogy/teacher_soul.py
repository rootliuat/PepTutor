"""Helpers for loading the PepTutor teacher persona prompt."""

from __future__ import annotations

import os
from pathlib import Path


def _default_soul_path() -> Path:
    env_path = os.getenv("PEPTUTOR_TEACHER_SOUL_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()

    current = Path(__file__).resolve()
    for ancestor in current.parents:
        candidate = ancestor / "soul.md"
        if candidate.exists():
            return candidate

    raise FileNotFoundError("Unable to locate PepTutor soul.md")


def _default_kernel_path() -> Path:
    env_path = os.getenv("PEPTUTOR_TEACHER_KERNEL_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()

    current = Path(__file__).resolve()
    for ancestor in current.parents:
        candidate = ancestor / "prompts" / "teacher_kernel.md"
        if candidate.exists():
            return candidate

    raise FileNotFoundError("Unable to locate PepTutor teacher_kernel.md")


def load_teacher_soul(path: str | Path | None = None) -> str:
    """Load the teacher soul markdown and normalize a possible UTF-8 BOM."""

    soul_path = Path(path).expanduser().resolve() if path is not None else _default_soul_path()
    return soul_path.read_text(encoding="utf-8-sig").strip()


def load_teacher_kernel(path: str | Path | None = None) -> str:
    """Load the compact runtime teacher kernel."""

    kernel_path = (
        Path(path).expanduser().resolve() if path is not None else _default_kernel_path()
    )
    return kernel_path.read_text(encoding="utf-8-sig").strip()
