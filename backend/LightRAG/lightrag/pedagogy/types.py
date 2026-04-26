"""Shared lesson-runtime type aliases."""

from typing import Literal

EvaluationResult = Literal[
    "correct",
    "acceptable",
    "partially_correct",
    "incorrect",
    "off_topic",
    "unclear",
]

TurnLabel = Literal[
    "page_entry",
    "answer_question",
    "ask_knowledge",
    "ask_help",
    "navigation",
    "social",
]

TeachingAction = Literal[
    "page_intro",
    "probe",
    "confirm",
    "hint",
    "model",
    "repeat_drill",
    "explain",
    "redirect",
    "complete",
]

RetrievalMode = Literal["none", "block", "page", "unit", "branch"]
