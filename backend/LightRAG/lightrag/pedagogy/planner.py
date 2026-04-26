"""Live planner prompt helpers for lesson open turns."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any, Literal

from json_repair import repair_json
from pydantic import BaseModel, ConfigDict, Field

from lightrag.pedagogy.types import RetrievalMode, TeachingAction
from lightrag.utils import logger


OpenTurnLabel = Literal["ask_help", "ask_knowledge", "social"]


class PlannerDecision(BaseModel):
    """Structured planner output for one open lesson turn."""

    model_config = ConfigDict(extra="forbid")

    teaching_action: TeachingAction
    retrieval_mode: RetrievalMode
    branch_reason: str | None = None
    return_anchor: str | None = None
    response_focus: str = Field(
        default="Keep the reply short, supportive, and lesson-aware.",
        min_length=1,
        max_length=200,
    )


class OpenTurnRouteDecision(BaseModel):
    """Structured route-classification output for one open lesson turn."""

    model_config = ConfigDict(extra="forbid")

    turn_label: OpenTurnLabel
    reason: str | None = None


class LessonPlanner:
    """Wrap a text-completion function as a structured lesson planner."""

    def __init__(self, complete_text: Callable[..., str]):
        self.complete_text = complete_text

    def plan_turn(
        self,
        *,
        turn_kind: str,
        learner_input: str,
        state_snapshot: dict[str, Any],
        page_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
        learner_memory: dict[str, Any] | None,
        allowed_actions: Sequence[TeachingAction],
        allowed_modes: Sequence[RetrievalMode],
        fallback: PlannerDecision,
    ) -> PlannerDecision:
        system_prompt = (
            "You are the lesson planner for a lively elementary English tutor. "
            "Do not answer the learner directly. "
            "Return exactly one JSON object and nothing else. "
            "Use only the allowed teaching_action and retrieval_mode values. "
            "Keep retrieval narrow unless the learner clearly needs a broader scope. "
            "Use branch only for short topic extensions that can return to the lesson."
        )
        prompt = self._build_turn_prompt(
            turn_kind=turn_kind,
            learner_input=learner_input,
            state_snapshot=state_snapshot,
            page_snapshot=page_snapshot,
            block_snapshot=block_snapshot,
            learner_memory=learner_memory,
            allowed_actions=allowed_actions,
            allowed_modes=allowed_modes,
            fallback=fallback,
        )

        try:
            raw = self.complete_text(
                prompt,
                system_prompt=system_prompt,
                history_messages=[],
                max_tokens=240,
                _lesson_audit_tag=f"planner.plan_turn.{turn_kind}",
            )
            decision = PlannerDecision.model_validate(
                repair_json(raw, return_objects=True)
            )
            self._validate_allowed(
                decision,
                allowed_actions=allowed_actions,
                allowed_modes=allowed_modes,
            )
            return decision
        except Exception as exc:
            logger.warning(
                "Lesson planner failed, using deterministic %s plan: %s",
                turn_kind,
                exc,
            )
            return fallback

    def classify_open_turn(
        self,
        *,
        learner_input: str,
        state_snapshot: dict[str, Any],
        page_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
        learner_memory: dict[str, Any] | None,
        allowed_turn_labels: Sequence[OpenTurnLabel],
        fallback: OpenTurnRouteDecision,
    ) -> OpenTurnRouteDecision:
        system_prompt = (
            "You are the route classifier for a lively elementary English lesson runtime. "
            "Do not answer the learner directly. "
            "Return exactly one JSON object and nothing else. "
            "Use only the allowed turn_label values. "
            "Classify whether this open turn should be treated as ask_help, ask_knowledge, or social."
        )
        prompt = self._build_route_prompt(
            learner_input=learner_input,
            state_snapshot=state_snapshot,
            page_snapshot=page_snapshot,
            block_snapshot=block_snapshot,
            learner_memory=learner_memory,
            allowed_turn_labels=allowed_turn_labels,
            fallback=fallback,
        )

        try:
            raw = self.complete_text(
                prompt,
                system_prompt=system_prompt,
                history_messages=[],
                max_tokens=120,
                _lesson_audit_tag="planner.classify_open_turn",
            )
            decision = OpenTurnRouteDecision.model_validate(
                repair_json(raw, return_objects=True)
            )
            self._validate_route_label(
                decision,
                allowed_turn_labels=allowed_turn_labels,
            )
            return decision
        except Exception as exc:
            logger.warning(
                "Lesson route classifier failed, using deterministic route: %s",
                exc,
            )
            return fallback

    def plan_knowledge_turn(
        self,
        *,
        learner_input: str,
        state_snapshot: dict[str, Any],
        page_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
        learner_memory: dict[str, Any] | None,
        allowed_actions: Sequence[TeachingAction],
        allowed_modes: Sequence[RetrievalMode],
        fallback: PlannerDecision,
    ) -> PlannerDecision:
        return self.plan_turn(
            turn_kind="ask_knowledge",
            learner_input=learner_input,
            state_snapshot=state_snapshot,
            page_snapshot=page_snapshot,
            block_snapshot=block_snapshot,
            learner_memory=learner_memory,
            allowed_actions=allowed_actions,
            allowed_modes=allowed_modes,
            fallback=fallback,
        )

    def _build_route_prompt(
        self,
        *,
        learner_input: str,
        state_snapshot: dict[str, Any],
        page_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
        learner_memory: dict[str, Any] | None,
        allowed_turn_labels: Sequence[OpenTurnLabel],
        fallback: OpenTurnRouteDecision,
    ) -> str:
        payload = {
            "turn_kind": "route_classifier",
            "learner_input": learner_input,
            "state": state_snapshot,
            "page": page_snapshot,
            "current_block": block_snapshot,
            "learner_memory": learner_memory or {},
            "allowed_turn_labels": list(allowed_turn_labels),
            "fallback_route": fallback.model_dump(),
            "required_output_schema": {
                "turn_label": "<one allowed value>",
                "reason": "<short explanation or null>",
            },
        }
        return json.dumps(payload, ensure_ascii=True, indent=2)

    def _build_turn_prompt(
        self,
        *,
        turn_kind: str,
        learner_input: str,
        state_snapshot: dict[str, Any],
        page_snapshot: dict[str, Any],
        block_snapshot: dict[str, Any],
        learner_memory: dict[str, Any] | None,
        allowed_actions: Sequence[TeachingAction],
        allowed_modes: Sequence[RetrievalMode],
        fallback: PlannerDecision,
    ) -> str:
        payload = {
            "turn_kind": turn_kind,
            "learner_input": learner_input,
            "state": state_snapshot,
            "page": page_snapshot,
            "current_block": block_snapshot,
            "learner_memory": learner_memory or {},
            "allowed_actions": list(allowed_actions),
            "allowed_modes": list(allowed_modes),
            "fallback_plan": fallback.model_dump(),
            "required_output_schema": {
                "teaching_action": "<one allowed value>",
                "retrieval_mode": "<one allowed value>",
                "branch_reason": "<short snake_case string or null>",
                "return_anchor": "<short lesson sentence or null>",
                "response_focus": "<one short sentence for the responder>",
            },
        }
        return json.dumps(payload, ensure_ascii=True, indent=2)

    def _validate_allowed(
        self,
        decision: PlannerDecision,
        *,
        allowed_actions: Sequence[TeachingAction],
        allowed_modes: Sequence[RetrievalMode],
    ) -> None:
        if decision.teaching_action not in allowed_actions:
            raise ValueError(
                f"planner teaching_action {decision.teaching_action!r} not allowed"
            )
        if decision.retrieval_mode not in allowed_modes:
            raise ValueError(
                f"planner retrieval_mode {decision.retrieval_mode!r} not allowed"
            )

    def _validate_route_label(
        self,
        decision: OpenTurnRouteDecision,
        *,
        allowed_turn_labels: Sequence[OpenTurnLabel],
    ) -> None:
        if decision.turn_label not in allowed_turn_labels:
            raise ValueError(
                f"planner turn_label {decision.turn_label!r} not allowed"
            )
