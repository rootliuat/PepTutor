"""Private current-turn lesson brief passed to the live responder."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LessonBriefPageContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_uid: str
    page_type: str
    lesson_title: str | None = None
    target_language: list[str] = Field(default_factory=list)
    block_sequence_summary: list[str] = Field(default_factory=list)


class LessonBriefTurnContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_block_uid: str
    current_block_type: str
    turn_label: str
    learner_input: str
    evaluation: str | None = None
    awaiting_answer: bool
    last_teacher_question: str | None = None
    recent_turn_labels: list[str] = Field(default_factory=list)


class LessonBriefAnswerRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    teaching_goal: str
    expected_answer_shape: str
    acceptable_variants: list[str] = Field(default_factory=list)
    must_not_accept: list[str] = Field(default_factory=list)
    progression_condition: str


class LessonBriefMisconceptionHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    likely_error: str
    repair_move: str
    scaffold_example: str | None = None


class LessonBriefTeacherMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    response_focus: str
    should_retrieve: bool
    banned_phrases: list[str] = Field(default_factory=list)


class LessonBriefMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["exact_page", "exact_block", "same_page_support"]
    uid: str
    kind: str
    summary: str
    source_refs: list[str] = Field(default_factory=list)


class LessonBriefAnswerScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_answer_shape: str
    acceptable_answers: list[str] = Field(default_factory=list)
    must_not_accept: list[str] = Field(default_factory=list)
    evidence_source_block_uid: str | None = None


class LessonBriefProgression(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: str
    authority: str = "runtime_state_controls_progression"


class CurrentTurnLessonBrief(BaseModel):
    """Compact private brief for one teacher response."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "peptutor-current-turn-brief-v2"
    teaching_focus: list[str] = Field(default_factory=list)
    materials: list[LessonBriefMaterial] = Field(default_factory=list)
    answer_scope: LessonBriefAnswerScope
    support_vocabulary: list[str] = Field(default_factory=list)
    likely_mistakes: list[LessonBriefMisconceptionHint] = Field(default_factory=list)
    progression: LessonBriefProgression
    page_context: LessonBriefPageContext
    turn_context: LessonBriefTurnContext
    answer_rubric: LessonBriefAnswerRubric
    misconception_map: list[LessonBriefMisconceptionHint] = Field(default_factory=list)
    teacher_move: LessonBriefTeacherMove

    def to_prompt_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
