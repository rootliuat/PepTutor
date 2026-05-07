import json
from pathlib import Path

import pytest

from lightrag.pedagogy.page_teaching_strategy import (
    STRATEGY_PRIORITY_ORDER,
    PageTeachingStrategyRepository,
    load_page_teaching_strategy,
)


def _strategy_path(name: str) -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "app"
        / "knowledge"
        / "teaching_strategies"
        / name
    )


def test_reviewed_strategy_json_files_load_and_validate():
    repo = PageTeachingStrategyRepository.default()

    p26 = repo.get("TB-G5S1U3-P26")
    p24 = repo.get("TB-G5S1U3-P24")

    assert p26 is not None
    assert p26.initial_step().step_id == "p26_s1_notice_ow"
    assert "copy_task_drift" in p26.strategy_lock.blocked_actions
    assert p24 is not None
    assert p24.initial_step().step_id == "p24_s1_scene_intro"
    assert "merge_food_and_drink_scope" in p24.strategy_lock.blocked_actions


def test_strategy_loader_rejects_malformed_strategy(tmp_path):
    payload = json.loads(_strategy_path("g5s1u3-p26-ow-phonics.json").read_text())
    payload["steps"][0]["allowed_actions"] = []
    malformed = tmp_path / "bad-strategy.json"
    malformed.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed page teaching strategy"):
        load_page_teaching_strategy(malformed)


def test_strategy_lock_priority_is_explicit_and_stable():
    assert STRATEGY_PRIORITY_ORDER == (
        "Strategy State",
        "TeachingMove",
        "Page Strategy",
        "Scoped Evidence",
        "RAG",
    )

