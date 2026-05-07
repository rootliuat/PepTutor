"""Reviewed page-teaching strategies for deterministic classroom control."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


StrategyModuleType = Literal[
    "lets_spell",
    "lets_learn",
    "lets_try",
    "lets_talk",
    "story_time",
    "lets_check",
    "lets_wrap_it_up",
    "read_and_write",
    "ask_and_answer",
]

StrategyReviewStatus = Literal[
    "reviewed_demo_slice",
    "human_reviewed",
    "draft",
]

STRATEGY_PRIORITY_ORDER = (
    "Strategy State",
    "TeachingMove",
    "Page Strategy",
    "Scoped Evidence",
    "RAG",
)


class StrategyLock(BaseModel):
    """Runtime guardrail copied from a reviewed page strategy."""

    model_config = ConfigDict(extra="forbid")

    page_uid: str = Field(min_length=1)
    module_type: StrategyModuleType
    step_id: str = Field(min_length=1)
    allowed_words: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)
    completion_rule: str = Field(min_length=1)
    transition_rule: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_lock(self) -> "StrategyLock":
        if not self.allowed_actions:
            raise ValueError("strategy lock requires allowed_actions")
        if not self.blocked_actions:
            raise ValueError("strategy lock requires blocked_actions")
        return self


class PageTeachingStrategyStep(BaseModel):
    """One reviewed strategy step."""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    block_uid: str = Field(min_length=1)
    module_type: StrategyModuleType
    step_type: str = Field(min_length=1)
    teacher_prompt: str = Field(min_length=1)
    question_target: str = ""
    answer_frames: list[str] = Field(default_factory=list)
    sound_group: str = ""
    target_words: list[str] = Field(default_factory=list)
    allowed_words: list[str] = Field(default_factory=list)
    food_words: list[str] = Field(default_factory=list)
    drink_words: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)
    repair_rules: list[str] = Field(default_factory=list)
    completion_rules: list[str] = Field(default_factory=list)
    completion_rule: str = Field(min_length=1)
    transition_rule: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_step(self) -> "PageTeachingStrategyStep":
        if not self.allowed_actions:
            raise ValueError(f"{self.step_id} requires allowed_actions")
        if not self.blocked_actions:
            raise ValueError(f"{self.step_id} requires blocked_actions")
        if not self.repair_rules:
            raise ValueError(f"{self.step_id} requires repair_rules")
        if not self.completion_rules:
            raise ValueError(f"{self.step_id} requires completion_rules")
        return self


class PageTeachingStrategy(BaseModel):
    """A reviewed, data-driven teaching strategy for one page."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["peptutor-page-teaching-strategy-v1"]
    strategy_version: str = Field(min_length=1)
    page_uid: str = Field(min_length=1)
    book_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    module_type: StrategyModuleType
    review_status: StrategyReviewStatus
    strategy_summary: str = Field(min_length=1)
    strategy_lock: StrategyLock
    steps: list[PageTeachingStrategyStep] = Field(min_length=1)
    evidence_policy: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_strategy(self) -> "PageTeachingStrategy":
        if self.strategy_lock.page_uid != self.page_uid:
            raise ValueError("strategy_lock.page_uid must match strategy page_uid")
        if self.strategy_lock.module_type != self.module_type:
            raise ValueError("strategy_lock.module_type must match strategy module_type")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("strategy steps must have unique step_id values")
        if self.strategy_lock.step_id not in set(step_ids):
            raise ValueError("strategy_lock.step_id must name a strategy step")
        for step in self.steps:
            if step.block_uid and not step.block_uid.startswith(f"{self.page_uid}-"):
                raise ValueError(
                    f"{step.step_id} block_uid must belong to {self.page_uid}"
                )
        return self

    def step_by_id(self, step_id: str) -> PageTeachingStrategyStep:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        raise KeyError(step_id)

    def initial_step(self) -> PageTeachingStrategyStep:
        return self.step_by_id(self.strategy_lock.step_id)

    def next_step(self, step: PageTeachingStrategyStep) -> PageTeachingStrategyStep:
        index = self.steps.index(step)
        if index + 1 < len(self.steps):
            return self.steps[index + 1]
        return step


class PageTeachingStrategyRepository:
    """Load reviewed page strategies from disk without touching runtime prompts."""

    def __init__(self, strategies: dict[str, PageTeachingStrategy]):
        self._strategies = dict(strategies)

    @classmethod
    def load_dir(cls, strategy_dir: Path) -> "PageTeachingStrategyRepository":
        strategies: dict[str, PageTeachingStrategy] = {}
        if not strategy_dir.exists():
            return cls(strategies)
        for path in sorted(strategy_dir.glob("*.json")):
            strategy = load_page_teaching_strategy(path)
            strategies[strategy.page_uid] = strategy
        return cls(strategies)

    @classmethod
    def default(cls) -> "PageTeachingStrategyRepository":
        return load_default_page_teaching_strategy_repository()

    def get(self, page_uid: str) -> PageTeachingStrategy | None:
        return self._strategies.get(page_uid)

    def has_strategy(self, page_uid: str) -> bool:
        return page_uid in self._strategies


def load_page_teaching_strategy(path: Path) -> PageTeachingStrategy:
    """Load and validate one reviewed strategy JSON file."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid strategy JSON: {path}") from exc
    try:
        return PageTeachingStrategy.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Malformed page teaching strategy: {path}") from exc


@lru_cache(maxsize=1)
def load_default_page_teaching_strategy_repository() -> PageTeachingStrategyRepository:
    current = Path(__file__).resolve()
    for ancestor in current.parents:
        candidate = ancestor / "app/knowledge/teaching_strategies"
        if candidate.exists():
            return PageTeachingStrategyRepository.load_dir(candidate)
    return PageTeachingStrategyRepository({})

