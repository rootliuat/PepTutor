"""Auditable teaching-move payloads for one lesson turn."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from lightrag.pedagogy.types import TeachingAction


LearnerSignal = Literal[
    "page_entry",
    "refusal",
    "task_echo",
    "incomplete_answer",
    "small_error",
    "help_request",
    "knowledge_question",
    "vocabulary_question",
    "module_navigation_unavailable",
    "off_topic",
    "good_answer",
]

TeachingMoveName = Literal[
    "open_with_probe",
    "lower_pressure_reinvite",
    "convert_task_echo_to_answer",
    "prompt_missing_piece",
    "light_recast",
    "give_one_step_hint",
    "answer_briefly_then_return",
    "vocab_answer_return",
    "redirect_to_active_task",
    "gentle_redirect",
    "single_block_guard",
    "confirm_and_advance",
]


class TeachingMovePlan(BaseModel):
    """Reusable classroom move selected from learner signal plus lesson brief."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "peptutor-teaching-move-v1"
    detected_signal: LearnerSignal
    move: TeachingMoveName
    teaching_action: TeachingAction
    rationale: str = Field(min_length=1, max_length=240)
    evidence_fields_used: list[str] = Field(default_factory=list)
    expected_next_learner_action: str = Field(min_length=1, max_length=240)
    payload_fields: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)

    def to_prompt_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        return {
            key: value
            for key, value in payload.items()
            if not (key in {"payload_fields", "constraints"} and not value)
        }
