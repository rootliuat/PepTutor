"""Structured readiness judge for answer-turn advancement."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from json_repair import repair_json
from pydantic import BaseModel, ConfigDict, Field

from lightrag.utils import logger


ReadinessLabel = Literal["not_ready", "guided", "hesitant", "independent"]
BlockedMove = Literal["advance_block", "introduce_new_pattern"]

_DEFAULT_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "prompts" / "readiness_judge_contract.md"
)


class ReadinessJudgeResult(BaseModel):
    """Structured readiness decision consumed by the lesson runtime."""

    model_config = ConfigDict(extra="forbid")

    readiness: ReadinessLabel
    can_advance: bool
    signals: list[str] = Field(default_factory=list, max_length=8)
    reason: str = Field(default="", max_length=300)
    allowed_next_step: str = Field(default="", max_length=220)
    blocked_moves: list[BlockedMove] = Field(default_factory=list, max_length=4)


def load_readiness_judge_contract(path: str | Path | None = None) -> str:
    contract_path = Path(path).expanduser() if path is not None else _DEFAULT_CONTRACT_PATH
    return contract_path.read_text(encoding="utf-8").strip()


class ReadinessJudge:
    """Build a prompt, call the LLM, and validate the structured readiness schema."""

    def __init__(
        self,
        complete_text: Callable[..., str],
        *,
        system_prompt: str | None = None,
        system_prompt_path: str | Path | None = None,
    ):
        self.complete_text = complete_text
        self.system_prompt = (
            system_prompt.strip()
            if system_prompt is not None
            else load_readiness_judge_contract(system_prompt_path)
        )

    def judge(self, context: dict[str, Any]) -> ReadinessJudgeResult:
        prompt = self.build_judge_prompt(context)
        try:
            raw = self.complete_text(
                prompt,
                system_prompt=self.system_prompt,
                history_messages=[],
                max_tokens=220,
                _lesson_audit_tag="readiness_judge",
            )
            return self.parse_and_validate(raw)
        except Exception as exc:
            logger.warning("Readiness judge failed, using conservative fallback: %s", exc)
            return self.fallback()

    def build_judge_prompt(self, context: dict[str, Any]) -> str:
        payload = {
            "turn_kind": "readiness_judge",
            "context": context,
            "required_output_schema": {
                "readiness": "not_ready | guided | hesitant | independent",
                "can_advance": "<boolean>",
                "signals": ["<short_snake_case_signal>"],
                "reason": "<short runtime reason, not teacher speech>",
                "allowed_next_step": "<short runtime instruction, not teacher speech>",
                "blocked_moves": ["advance_block", "introduce_new_pattern"],
            },
        }
        return json.dumps(payload, ensure_ascii=True, indent=2)

    def parse_and_validate(self, raw: str) -> ReadinessJudgeResult:
        try:
            parsed = repair_json(raw, return_objects=True)
            return ReadinessJudgeResult.model_validate(parsed)
        except Exception as exc:
            logger.warning(
                "Readiness judge returned invalid JSON/schema, using fallback: %s",
                exc,
            )
            return self.fallback()

    def fallback(self) -> ReadinessJudgeResult:
        return ReadinessJudgeResult(
            readiness="not_ready",
            can_advance=False,
            signals=["judge_unavailable"],
            reason="Judge unavailable; keep the learner on the current step.",
            allowed_next_step="Stay on the current step and confirm independent production.",
            blocked_moves=["advance_block", "introduce_new_pattern"],
        )
