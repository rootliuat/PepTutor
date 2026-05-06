"""Runtime state models for the text-first lesson loop."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lightrag.pedagogy.types import EvaluationResult


class LessonRuntimeState(BaseModel):
    """Serializable lesson state returned by the lesson endpoint."""

    model_config = ConfigDict(extra="forbid")

    student_id: str = Field(min_length=1)
    current_grade: str = Field(min_length=1)
    current_semester: str = Field(min_length=1)
    current_unit: str = Field(min_length=1)
    current_page: int = Field(ge=1)
    current_page_uid: str = Field(min_length=1)
    current_page_type: str = Field(min_length=1)
    current_block_uid: str | None = None
    current_activity_type: Literal[
        "page_entry",
        "teaching",
        "practice",
        "review",
        "branch",
    ] = "page_entry"
    awaiting_answer: bool = False
    last_teacher_question: str | None = None
    hint_level: int = Field(default=0, ge=0)
    pedagogy_level: int = Field(default=0, ge=0)
    page_entry_probe_done: bool = False
    repair_mode: str = "none"
    recent_turn_labels: list[str] = Field(default_factory=list)
    recent_turns: list[dict[str, str | None]] = Field(default_factory=list)
    same_goal_attempt_count: int = Field(default=0, ge=0)
    last_eval_result: EvaluationResult | None = None
    model_already_given: bool = False
    branch_active: bool = False
    branch_reason: str | None = None
    branch_origin_block_uid: str | None = None
    branch_turn_budget: int | None = Field(default=None, ge=0)
    branch_resume_awaiting_answer: bool = False
    return_anchor: str | None = None
    return_target: str | None = None
    simplemem_content_session_id: str | None = None
    simplemem_memory_session_id: str | None = None
    strategy_state: dict[str, object] | None = None

    @field_validator(
        "student_id",
        "current_grade",
        "current_semester",
        "current_unit",
        "current_page_uid",
        "current_page_type",
        mode="after",
    )
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be empty")
        return stripped

    def push_turn_label(self, label: str) -> None:
        """Keep the recent turn label window short and readable."""
        self.recent_turn_labels = [*self.recent_turn_labels[-4:], label]

    def push_turn_text(
        self,
        *,
        turn_label: str,
        teacher_text: str | None,
        learner_text: str | None,
    ) -> None:
        """Keep a short dialogue window for readiness judgments."""
        self.recent_turns = [
            *self.recent_turns[-2:],
            {
                "turn_label": turn_label,
                "teacher_text": teacher_text,
                "learner_text": learner_text,
            },
        ]
