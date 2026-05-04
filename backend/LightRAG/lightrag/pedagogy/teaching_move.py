"""Auditable teaching-move payloads for one lesson turn."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    ValidationError,
    model_validator,
)

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

TeachingMoveTargetRole = Literal["question", "answer", "phrase", "phonics", "story"]
TeachingMoveExpectedStudentAction = Literal[
    "read",
    "answer",
    "repeat",
    "choose",
    "role_play",
]
TeachingMoveActionSource = Literal[
    "block_core_pattern",
    "active_prompt",
    "return_anchor",
    "answer_scope",
    "phonics_context",
    "story_context",
    "fallback_conservative",
]


class TeachingMoveActionContract(BaseModel):
    """Typed action payload shared by TeachingMove audit and redirect rendering."""

    model_config = ConfigDict(extra="forbid")

    target_role: TeachingMoveTargetRole
    expected_student_action: TeachingMoveExpectedStudentAction
    question_target: StrictStr = ""
    answer_target: StrictStr = ""
    answer_frame: StrictStr = ""
    action_source: TeachingMoveActionSource
    preserve_page_uid: StrictStr = ""
    preserve_block_uid: StrictStr = ""
    active_prompt: StrictStr = ""
    return_anchor: StrictStr = ""
    target_phrase: StrictStr = ""

    @model_validator(mode="after")
    def _validate_contract_semantics(self) -> "TeachingMoveActionContract":
        if self.target_role == "phonics" and not self.answer_target.strip():
            raise ValueError("phonics action contract requires answer_target")
        if (
            self.target_role == "question"
            and self.expected_student_action == "answer"
            and _question_action_needs_answer_target_or_frame(self.question_target)
            and not self.answer_target.strip()
            and not self.answer_frame.strip()
        ):
            raise ValueError(
                "question answer action contract requires answer_target or answer_frame"
            )
        return self

    @classmethod
    def from_payload_fields(cls, payload_fields: dict[str, Any]) -> "TeachingMoveActionContract":
        """Validate a TeachingMove payload subset as an action contract."""

        return cls.model_validate(
            {
                "target_role": payload_fields.get("target_role"),
                "expected_student_action": payload_fields.get(
                    "expected_student_action"
                ),
                "question_target": _optional_payload_string(
                    payload_fields.get("question_target")
                ),
                "answer_target": _optional_payload_string(
                    payload_fields.get("answer_target")
                ),
                "answer_frame": _optional_payload_string(
                    payload_fields.get("answer_frame")
                ),
                "action_source": payload_fields.get("action_source"),
                "preserve_page_uid": _optional_payload_string(
                    payload_fields.get("preserve_page_uid")
                ),
                "preserve_block_uid": _optional_payload_string(
                    payload_fields.get("preserve_block_uid")
                ),
                "active_prompt": _optional_payload_string(
                    payload_fields.get("active_prompt")
                ),
                "return_anchor": _optional_payload_string(
                    payload_fields.get("return_anchor")
                ),
                "target_phrase": _optional_payload_string(
                    payload_fields.get("target_phrase")
                ),
            }
        )

    @classmethod
    def try_from_payload_fields(
        cls,
        payload_fields: dict[str, Any] | None,
    ) -> "TeachingMoveActionContract | None":
        """Return a validated action contract, or None for malformed payloads."""

        if not isinstance(payload_fields, dict):
            return None
        try:
            return cls.from_payload_fields(payload_fields)
        except ValidationError:
            return None

    def to_payload_fields(self) -> dict[str, str]:
        """Return only the validated action fields consumed by runtime helpers."""

        return self.model_dump(mode="json")


def _optional_payload_string(value: Any) -> Any:
    return "" if value is None else value


def _question_action_needs_answer_target_or_frame(value: str) -> bool:
    normalized = " ".join(str(value or "").strip().split()).casefold()
    normalized = normalized.strip("。！？!?.")
    if not normalized:
        return False
    return normalized.startswith(
        (
            "what ",
            "what's ",
            "what is ",
            "what did ",
            "what would ",
            "where ",
            "when ",
            "how tall ",
        )
    )


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
