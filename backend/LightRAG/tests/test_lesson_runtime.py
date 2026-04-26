import json
import importlib
import re
import sqlite3
import sys
import warnings
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

_PYTEST_ARGV = sys.argv[:]
sys.argv = [sys.argv[0]]
lesson_routes_module = importlib.import_module("lightrag.api.routers.lesson_routes")
create_lesson_routes = lesson_routes_module.create_lesson_routes
_airi_action_payload = lesson_routes_module._airi_action_payload
_airi_action_payload_from_metadata = (
    lesson_routes_module._airi_action_payload_from_metadata
)
_lesson_text_chunks = lesson_routes_module._lesson_text_chunks
utils_api = importlib.import_module("lightrag.api.utils_api")
LessonRuntime = importlib.import_module(
    "lightrag.orchestrator.lesson_runtime"
).LessonRuntime
LessonTurnResult = importlib.import_module(
    "lightrag.orchestrator.lesson_runtime"
).LessonTurnResult
LessonTurnDebugSignals = importlib.import_module(
    "lightrag.orchestrator.lesson_runtime"
).LessonTurnDebugSignals
LessonRuntimeState = importlib.import_module(
    "lightrag.orchestrator.lesson_state"
).LessonRuntimeState
readiness_module = importlib.import_module("lightrag.orchestrator.lesson_readiness_judge")
ReadinessJudge = readiness_module.ReadinessJudge
ReadinessJudgeResult = readiness_module.ReadinessJudgeResult
PilotLessonCatalog = importlib.import_module(
    "lightrag.orchestrator.lesson_runtime"
).PilotLessonCatalog
QdrantTeachingStore = importlib.import_module(
    "lightrag.orchestrator.qdrant_teaching_store"
).QdrantTeachingStore
QdrantLessonRetriever = importlib.import_module(
    "lightrag.orchestrator.lesson_vector_retrieval"
).QdrantLessonRetriever
SupportAssetRetriever = importlib.import_module(
    "lightrag.orchestrator.support_asset_retrieval"
).SupportAssetRetriever
LessonPlanner = importlib.import_module("lightrag.pedagogy.planner").LessonPlanner
PlannerDecision = importlib.import_module("lightrag.pedagogy.planner").PlannerDecision
LessonResponder = importlib.import_module("lightrag.pedagogy.responder").LessonResponder
system_contract_module = importlib.import_module("lightrag.pedagogy.system_contract")
LESSON_AUTHORITY_ORDER = system_contract_module.LESSON_AUTHORITY_ORDER
BANNED_TEACHER_PHRASES = system_contract_module.BANNED_TEACHER_PHRASES
load_teacher_soul = importlib.import_module(
    "lightrag.pedagogy.teacher_soul"
).load_teacher_soul
load_teacher_kernel = importlib.import_module(
    "lightrag.pedagogy.teacher_soul"
).load_teacher_kernel
LearnerMemorySummary = importlib.import_module(
    "lightrag.orchestrator.simplemem_prompt_memory"
).LearnerMemorySummary
SimpleMemSQLiteLessonMemoryWriter = importlib.import_module(
    "lightrag.orchestrator.simplemem_writeback"
).SimpleMemSQLiteLessonMemoryWriter
FeatureStatus = importlib.import_module(
    "lightrag.orchestrator.lesson_runtime_factory"
).FeatureStatus
sys.argv = _PYTEST_ARGV


def _write_test_pilot(tmp_path):
    pilot_file = tmp_path / "pilot.json"
    manifest_file = tmp_path / "manifest.json"

    pilot_payload = {
        "pilot_id": "g5s1u3-test",
        "scope": {"grade": "G5", "semester": "S1", "unit": "U3", "pages": [24, 25, 26]},
        "page_lessons": [
            {
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "page_intro_cn": "这一页练习点餐和饮料表达。",
                "entry_probe_questions": ["Can you say: What would you like to drink?"],
                "priority_blocks": ["TB-G5S1U3-P24-D1", "TB-G5S1U3-P24-D2"],
            },
            {
                "page_uid": "TB-G5S1U3-P25",
                "page_type": "reading",
                "page_intro_cn": "这一页练习菜单和沙拉。",
                "entry_probe_questions": ["Can you say salad?"],
                "priority_blocks": ["TB-G5S1U3-P25-D1"],
            },
            {
                "page_uid": "TB-G5S1U3-P26",
                "page_type": "dialogue",
                "page_intro_cn": "这一页允许短暂聊早餐话题。",
                "entry_probe_questions": ["What do you eat for breakfast?"],
                "priority_blocks": ["TB-G5S1U3-P26-D1"],
            },
        ],
        "teaching_blocks": [
            {
                "block_uid": "TB-G5S1U3-P24-D1",
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_type": "dialogue_core",
                "teaching_goal": "Use the target drink question and answer.",
                "teaching_summary": "Restaurant ordering with the drink question.",
                "focus_vocabulary": ["water", "juice"],
                "core_patterns": [
                    "What would you like to drink?",
                    "I'd like some water.",
                ],
                "allowed_answer_scope": [
                    "I'd like some water.",
                    "I'd like some juice.",
                ],
                "entry_probe_questions": ["Can you answer: What would you like to drink?"],
                "repair_modes": ["repeat", "sentence_drill"],
                "next_block_uids": ["TB-G5S1U3-P24-D2"],
                "learning_target_uids": ["LT-1"],
                "branchable_topics": ["drink"],
                "return_anchors": ["What would you like to drink?"],
            },
            {
                "block_uid": "TB-G5S1U3-P24-D2",
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_type": "roleplay_task",
                "teaching_goal": "Do a short drink role-play.",
                "teaching_summary": "One-step role-play with a drink choice.",
                "focus_vocabulary": ["water", "juice"],
                "core_patterns": ["I'd like some water."],
                "allowed_answer_scope": ["I'd like some water."],
                "entry_probe_questions": ["Now say one full drink sentence."],
                "repair_modes": ["repeat"],
                "next_block_uids": [],
                "learning_target_uids": ["LT-2"],
                "branchable_topics": ["drink"],
                "return_anchors": ["I'd like some water."],
            },
            {
                "block_uid": "TB-G5S1U3-P25-D1",
                "page_uid": "TB-G5S1U3-P25",
                "page_type": "reading",
                "block_type": "reading_passage",
                "teaching_goal": "Read about salad on a menu.",
                "teaching_summary": "A short menu text about salad and soup.",
                "focus_vocabulary": ["salad", "soup"],
                "core_patterns": ["The salad is fresh."],
                "allowed_answer_scope": ["The salad is fresh."],
                "entry_probe_questions": ["Can you read salad?"],
                "repair_modes": ["repeat"],
                "next_block_uids": [],
                "learning_target_uids": ["LT-3"],
                "branchable_topics": [],
                "return_anchors": ["What would you like to eat?"],
            },
            {
                "block_uid": "TB-G5S1U3-P26-D1",
                "page_uid": "TB-G5S1U3-P26",
                "page_type": "dialogue",
                "block_type": "extension_task",
                "teaching_goal": "Talk about breakfast food briefly.",
                "teaching_summary": "A short breakfast extension with noodles and eggs.",
                "focus_vocabulary": ["breakfast", "noodles", "eggs"],
                "core_patterns": ["I'd like noodles for breakfast."],
                "allowed_answer_scope": ["I'd like noodles for breakfast."],
                "entry_probe_questions": ["What do you eat for breakfast?"],
                "repair_modes": ["repeat"],
                "next_block_uids": [],
                "learning_target_uids": ["LT-4"],
                "branchable_topics": ["breakfast", "noodles", "eggs"],
                "return_anchors": ["What would you like to eat?"],
            },
        ],
    }
    manifest_payload = {"files": [str(pilot_file)]}

    pilot_file.write_text(json.dumps(pilot_payload), encoding="utf-8")
    manifest_file.write_text(json.dumps(manifest_payload), encoding="utf-8")
    return manifest_file


def _write_shopping_list_task_pilot(tmp_path):
    pilot_file = tmp_path / "shopping-list-task.json"
    manifest_file = tmp_path / "manifest.json"

    pilot_payload = {
        "pilot_id": "g6s2-recycle2-task",
        "scope": {"grade": "G6", "semester": "S2", "unit": "Recycle2", "pages": [49]},
        "page_lessons": [
            {
                "page_uid": "TB-G6S2Recycle2-P49",
                "page_type": "phonics",
                "page_intro_cn": (
                    "Theme: A farewell party. 一个开放性的活动，鼓励学生结合所学词汇，"
                    "为自己的派对列出一份物品清单。"
                ),
                "entry_probe_questions": [
                    "Can you say: Create a personal party shopping list."
                ],
                "priority_blocks": [
                    "TB-G6S2Recycle2-P49-D4",
                    "TB-G6S2Recycle2-P49-D1",
                ],
            },
        ],
        "teaching_blocks": [
            {
                "block_uid": "TB-G6S2Recycle2-P49-D4",
                "page_uid": "TB-G6S2Recycle2-P49",
                "page_type": "phonics",
                "block_type": "extension_task",
                "teaching_goal": "Transfer the page language into a new speaking task.",
                "teaching_summary": (
                    "一个开放性的活动，鼓励学生结合所学词汇，为自己的派对列出一份物品清单。 "
                    "Key patterns: Create a personal party shopping list."
                ),
                "focus_vocabulary": [],
                "core_patterns": ["Create a personal party shopping list."],
                "allowed_answer_scope": ["Create a personal party shopping list."],
                "entry_probe_questions": [
                    "Can you say: Create a personal party shopping list."
                ],
                "repair_modes": ["choice_probe", "word_drill", "sentence_drill"],
                "next_block_uids": [],
                "learning_target_uids": ["LT-G6S2Recycle2-P49-D4-goal"],
                "branchable_topics": ["A farewell party"],
                "return_anchors": ["Create a personal party shopping list."],
            },
            {
                "block_uid": "TB-G6S2Recycle2-P49-D1",
                "page_uid": "TB-G6S2Recycle2-P49",
                "page_type": "phonics",
                "block_type": "picture_scene",
                "teaching_goal": "Work on the picture scene activity.",
                "teaching_summary": "Party food, drinks, and supplies.",
                "focus_vocabulary": ["brown bread", "cheese", "cake", "orange juice"],
                "core_patterns": [
                    "Identify and match vocabulary related to party food, drinks, and supplies."
                ],
                "allowed_answer_scope": [
                    "brown bread",
                    "cheese",
                    "cake",
                    "orange juice",
                ],
                "entry_probe_questions": ["Do you know the word brown bread?"],
                "repair_modes": ["repeat"],
                "next_block_uids": [],
                "learning_target_uids": ["LT-G6S2Recycle2-P49-D1-goal"],
                "branchable_topics": ["brown bread", "cheese", "cake", "orange juice"],
                "return_anchors": [
                    "Identify and match vocabulary related to party food, drinks, and supplies."
                ],
            },
        ],
    }
    manifest_payload = {"files": [str(pilot_file)]}

    pilot_file.write_text(json.dumps(pilot_payload), encoding="utf-8")
    manifest_file.write_text(json.dumps(manifest_payload), encoding="utf-8")
    return manifest_file


def _write_multi_module_review_pilot(tmp_path):
    pilot_file = tmp_path / "multi-module-review.json"
    manifest_file = tmp_path / "manifest.json"

    pilot_payload = {
        "pilot_id": "multi-module-review-test",
        "scope": {"grade": "G5", "semester": "S2", "unit": "U9", "pages": [12]},
        "page_lessons": [
            {
                "page_uid": "TB-G5S2U9-P12",
                "page_type": "writing",
                "page_intro_cn": (
                    "Theme: Unit review. 听录音完成检测，再整理日期表达。"
                ),
                "entry_probe_questions": ["Can you say: Listen and number."],
                "priority_blocks": [
                    "TB-G5S2U9-P12-D1",
                    "TB-G5S2U9-P12-D2",
                    "TB-G5S2U9-P12-D3",
                    "TB-G5S2U9-P12-D4",
                ],
            },
        ],
        "teaching_blocks": [
            {
                "block_uid": "TB-G5S2U9-P12-D1",
                "page_uid": "TB-G5S2U9-P12",
                "page_type": "writing",
                "block_type": "listening_probe",
                "teaching_goal": "Catch birthday dates from the listening task.",
                "teaching_summary": (
                    "听录音，根据听到的生日日期，为四张日期卡片排序。 "
                    "Key patterns: Listen and number."
                ),
                "focus_vocabulary": [],
                "core_patterns": ["Listen and number."],
                "allowed_answer_scope": ["4", "3", "2", "1"],
                "entry_probe_questions": ["Can you say: Listen and number."],
                "repair_modes": ["repeat"],
                "next_block_uids": ["TB-G5S2U9-P12-D2"],
                "learning_target_uids": ["LT-review-D1"],
                "branchable_topics": ["Unit review", "Let's check"],
                "return_anchors": ["Listen and number."],
            },
            {
                "block_uid": "TB-G5S2U9-P12-D2",
                "page_uid": "TB-G5S2U9-P12",
                "page_type": "writing",
                "block_type": "listening_probe",
                "teaching_goal": "Judge statements from the listening task.",
                "teaching_summary": (
                    "再次听录音，根据听到的内容判断生日陈述是否正确。 "
                    "Key patterns: Listen again and tick or cross."
                ),
                "focus_vocabulary": [],
                "core_patterns": ["Listen again and tick or cross."],
                "allowed_answer_scope": ["tick", "cross"],
                "entry_probe_questions": [
                    "Can you say: Listen again and tick or cross."
                ],
                "repair_modes": ["repeat"],
                "next_block_uids": ["TB-G5S2U9-P12-D3"],
                "learning_target_uids": ["LT-review-D2"],
                "branchable_topics": ["Unit review"],
                "return_anchors": ["Listen again and tick or cross."],
            },
            {
                "block_uid": "TB-G5S2U9-P12-D3",
                "page_uid": "TB-G5S2U9-P12",
                "page_type": "writing",
                "block_type": "practice_fill_blank",
                "teaching_goal": "Review cardinal and ordinal numbers.",
                "teaching_summary": (
                    "总结和巩固基数词与序数词的对应关系。 "
                    "Key patterns: Fill in the table."
                ),
                "focus_vocabulary": [],
                "core_patterns": ["Fill in the table."],
                "allowed_answer_scope": ["1st", "2nd", "3rd"],
                "entry_probe_questions": ["Can you say: Fill in the table."],
                "repair_modes": ["choice_probe"],
                "next_block_uids": ["TB-G5S2U9-P12-D4"],
                "learning_target_uids": ["LT-review-D3"],
                "branchable_topics": ["Unit review", "Let's wrap it up"],
                "return_anchors": ["Fill in the table."],
            },
            {
                "block_uid": "TB-G5S2U9-P12-D4",
                "page_uid": "TB-G5S2U9-P12",
                "page_type": "writing",
                "block_type": "practice_write",
                "teaching_goal": "Finish sentences with number forms.",
                "teaching_summary": (
                    "根据括号内的提示，使用正确的基数词或序数词形式完成句子。 "
                    "Key patterns: Finish the sentences."
                ),
                "focus_vocabulary": [],
                "core_patterns": ["Finish the sentences."],
                "allowed_answer_scope": ["ten", "second"],
                "entry_probe_questions": ["Can you say: Finish the sentences."],
                "repair_modes": ["repeat"],
                "next_block_uids": [],
                "learning_target_uids": ["LT-review-D4"],
                "branchable_topics": ["Unit review"],
                "return_anchors": ["Finish the sentences."],
            },
        ],
    }
    manifest_payload = {"files": [str(pilot_file)]}

    pilot_file.write_text(json.dumps(pilot_payload), encoding="utf-8")
    manifest_file.write_text(json.dumps(manifest_payload), encoding="utf-8")
    return manifest_file


def _make_runtime(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    return LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))


class _StaticReadinessJudge:
    def __init__(self, result):
        self.result = result
        self.contexts = []

    def judge(self, context):
        self.contexts.append(context)
        return self.result


def _readiness_result(readiness, can_advance):
    return ReadinessJudgeResult(
        readiness=readiness,
        can_advance=can_advance,
        signals=["test_signal"],
        reason="test readiness decision",
        allowed_next_step="test next step",
        blocked_moves=[] if can_advance else ["advance_block"],
    )


def test_readiness_gate_advances_only_after_independent_judgment(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    judge = _StaticReadinessJudge(_readiness_result("independent", True))
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=judge,
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "I'd like some water.")

    assert result.state.current_block_uid == "TB-G5S1U3-P24-D2"
    assert result.teaching_action == "confirm"
    assert judge.contexts[0]["answer_evaluation"] == "correct"
    assert judge.contexts[0]["current_goal"] == "Use the target drink question and answer."
    assert judge.contexts[0]["current_block"]["block_uid"] == "TB-G5S1U3-P24-D1"
    assert judge.contexts[0]["last_teacher_response"] == start.teacher_response
    assert judge.contexts[0]["recent_turns"] == [
        {
            "turn_label": "page_entry",
            "teacher_text": start.teacher_response,
            "learner_text": "",
        }
    ]


def test_readiness_gate_keeps_correct_guided_answer_on_current_block(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    judge = _StaticReadinessJudge(_readiness_result("guided", False))
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=judge,
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "I'd like some water.")

    assert result.state.current_block_uid == "TB-G5S1U3-P24-D1"
    assert result.block_uid == "TB-G5S1U3-P24-D1"
    assert result.state.awaiting_answer is True
    assert result.evaluation == "correct"
    assert result.teaching_action == "hint"


def test_runtime_readiness_gate_to_kernel_responder_advances_when_independent(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    judge = _StaticReadinessJudge(_readiness_result("independent", True))
    captured_prompts: list[dict[str, object]] = []
    captured_system_prompts: list[str] = []

    def _responder_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (history_messages, kwargs)
        captured_prompts.append(json.loads(prompt))
        captured_system_prompts.append(system_prompt or "")
        return "Theme: leaked internal metadata. 鼓励学生继续。"

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(
            _responder_llm,
            teacher_kernel="# Teacher Kernel\n- compact runtime teacher voice",
        ),
        readiness_judge=judge,
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "I'd like some water.")

    assert result.state.current_block_uid == "TB-G5S1U3-P24-D2"
    assert result.teaching_action == "confirm"
    assert judge.contexts[-1]["answer_evaluation"] == "correct"
    assert judge.contexts[-1]["learner_input"] == "I'd like some water."
    assert captured_prompts[-1]["teacher_kernel_source"] == "system_prompt"
    assert captured_prompts[-1]["plan"]["teaching_action"] == "confirm"
    assert captured_system_prompts[-1] == "# Teacher Kernel\n- compact runtime teacher voice"
    assert not system_contract_module.matches_banned_teacher_phrase(
        result.teacher_response
    )


def test_runtime_readiness_gate_to_kernel_responder_stays_when_guided(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    judge = _StaticReadinessJudge(_readiness_result("guided", False))
    captured_prompts: list[dict[str, object]] = []
    captured_system_prompts: list[str] = []

    def _responder_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (history_messages, kwargs)
        parsed = json.loads(prompt)
        captured_prompts.append(parsed)
        captured_system_prompts.append(system_prompt or "")
        return f"我们先停在这一步，再练一次：{parsed['safety_fallback_response']}"

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(
            _responder_llm,
            teacher_kernel="# Teacher Kernel\n- compact runtime teacher voice",
        ),
        readiness_judge=judge,
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    hinted = runtime.handle_turn(start.state, "banana")
    result = runtime.handle_turn(hinted.state, "I'd like some water.")

    assert result.state.current_block_uid == "TB-G5S1U3-P24-D1"
    assert result.block_uid == "TB-G5S1U3-P24-D1"
    assert result.teaching_action != "confirm"
    assert result.evaluation == "correct"
    assert judge.contexts[-1]["answer_evaluation"] == "correct"
    assert judge.contexts[-1]["learner_input"] == "I'd like some water."
    assert judge.contexts[-1]["recent_turns"][-1]["learner_text"] == "banana"
    assert captured_prompts[-1]["teacher_kernel_source"] == "system_prompt"
    assert captured_system_prompts[-1] == "# Teacher Kernel\n- compact runtime teacher voice"
    assert not system_contract_module.matches_banned_teacher_phrase(
        result.teacher_response
    )


def test_readiness_context_carries_last_three_turn_texts(tmp_path):
    runtime = _make_runtime(tmp_path)
    state = _minimal_lesson_state()
    for index in range(4):
        state.push_turn_text(
            turn_label=f"turn_{index}",
            teacher_text=f"teacher {index}",
            learner_text=f"learner {index}",
        )
    block = runtime.catalog.get_block("TB-G5S1U3-P24-D1")

    context = runtime._build_readiness_judge_context(
        learner_input="learner current",
        state=state,
        block=block,
        answer_scope=["expected answer"],
        evaluation="correct",
    )

    assert context["learner_input"] == "learner current"
    assert context["last_teacher_response"] == "teacher 3"
    assert context["recent_turns"] == [
        {"turn_label": "turn_1", "teacher_text": "teacher 1", "learner_text": "learner 1"},
        {"turn_label": "turn_2", "teacher_text": "teacher 2", "learner_text": "learner 2"},
        {"turn_label": "turn_3", "teacher_text": "teacher 3", "learner_text": "learner 3"},
    ]


def test_readiness_judge_invalid_output_falls_back_to_no_advance():
    judge = ReadinessJudge(lambda *args, **kwargs: "not json")

    result = judge.judge({"learner_input": "short answer"})

    assert result.readiness == "not_ready"
    assert result.can_advance is False
    assert result.signals == ["judge_unavailable"]
    assert result.blocked_moves == ["advance_block", "introduce_new_pattern"]


def test_readiness_judge_has_no_curriculum_literal_rules():
    source = Path(readiness_module.__file__).read_text(encoding="utf-8").casefold()

    for word in ["hungry", "tea", "water", "sandwich"]:
        assert re.search(rf"(?<![a-z]){word}(?![a-z])", source) is None
    assert "learner_input ==" not in source
    assert " in learner_input" not in source


def _parse_sse_events(text):
    events = []
    for block in text.strip().split("\n\n"):
        event = "message"
        data_lines = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ").strip()
            elif line.startswith("data: "):
                data_lines.append(line.removeprefix("data: "))
        if data_lines:
            events.append((event, json.loads("\n".join(data_lines))))
    return events


def _minimal_lesson_state(**overrides):
    payload = {
        "student_id": "student-action-test",
        "current_grade": "G5",
        "current_semester": "S1",
        "current_unit": "U3",
        "current_page": 24,
        "current_page_uid": "TB-G5S1U3-P24",
        "current_page_type": "dialogue",
        "current_block_uid": "TB-G5S1U3-P24-D1",
        "current_activity_type": "practice",
        "awaiting_answer": True,
        "last_teacher_question": "What would you like to drink?",
        "hint_level": 0,
        "pedagogy_level": 0,
        "page_entry_probe_done": True,
        "repair_mode": "none",
        "recent_turn_labels": [],
        "same_goal_attempt_count": 0,
        "last_eval_result": None,
        "model_already_given": False,
        "branch_active": False,
        "branch_reason": None,
        "branch_origin_block_uid": None,
        "branch_turn_budget": None,
        "branch_resume_awaiting_answer": False,
        "return_anchor": None,
        "return_target": None,
        "simplemem_content_session_id": None,
        "simplemem_memory_session_id": None,
    }
    payload.update(overrides)
    return LessonRuntimeState(**payload)


def _minimal_turn_result(**overrides):
    payload = {
        "page_uid": "TB-G5S1U3-P24",
        "block_uid": "TB-G5S1U3-P24-D1",
        "turn_label": "answer_question",
        "teaching_action": "confirm",
        "retrieval_mode": "none",
        "teacher_response": "Good job. Now say one full drink sentence.",
        "state": _minimal_lesson_state(),
        "evaluation": "correct",
        "retrieved_block_uids": [],
        "support_entry_uids": [],
        "return_anchor": None,
        "branch_reason": None,
    }
    payload.update(overrides)
    return LessonTurnResult(**payload)


def _write_test_support_assets(tmp_path):
    support_file = tmp_path / "support.json"
    support_payload = {
        "asset_id": "g5s1u3-support-test",
        "scope": {"grade": "G5", "semester": "S1", "unit": "U3", "pages": [24, 25, 26]},
        "source_files": ["raw_wordlist_g5s1", "raw_useful_expressions_g5s1"],
        "lexicon_entries": [
            {
                "entry_uid": "LEX-G5S1U3-sandwich",
                "entry_type": "word",
                "english": "sandwich",
                "chinese": "三明治",
                "phonetic": "/'sænwɪtʃ/",
                "source_refs": ["raw_wordlist_g5s1"],
                "page_refs": ["p.24", "p.25"],
                "linked_page_uids": ["TB-G5S1U3-P24", "TB-G5S1U3-P25"],
                "linked_block_uids": ["TB-G5S1U3-P24-D2", "TB-G5S1U3-P25-D1"],
            },
            {
                "entry_uid": "LEX-G5S1U3-salad",
                "entry_type": "word",
                "english": "salad",
                "chinese": "沙拉",
                "phonetic": "/'sæləd/",
                "source_refs": ["raw_wordlist_g5s1"],
                "page_refs": ["p.25"],
                "linked_page_uids": ["TB-G5S1U3-P25"],
                "linked_block_uids": ["TB-G5S1U3-P25-D1"],
            },
            {
                "entry_uid": "LEX-G5S1U3-noodles",
                "entry_type": "word",
                "english": "noodles",
                "chinese": "面条",
                "source_refs": ["raw_wordlist_g5s1"],
                "page_refs": ["p.26"],
                "linked_page_uids": ["TB-G5S1U3-P26"],
                "linked_block_uids": ["TB-G5S1U3-P26-D1"],
            },
        ],
        "expression_entries": [
            {
                "entry_uid": "EXP-G5S1U3-what-would-you-like-to-drink",
                "english": "What would you like to drink?",
                "chinese": "你想喝什么？",
                "page_refs": ["p.24"],
                "source_refs": ["raw_useful_expressions_g5s1"],
                "linked_page_uids": ["TB-G5S1U3-P24"],
                "linked_block_uids": ["TB-G5S1U3-P24-D1"],
            }
        ],
    }
    support_file.write_text(json.dumps(support_payload), encoding="utf-8")
    return support_file


def _make_runtime_with_support(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    support_retriever = SupportAssetRetriever(
        catalog,
        support_paths=[_write_test_support_assets(tmp_path)],
    )
    return LessonRuntime(catalog, support_retriever=support_retriever)


def _make_runtime_with_live_prompts(
    tmp_path,
    *,
    planner_payload,
    responder_text="老师的 live responder 输出。",
):
    manifest_path = _write_test_pilot(tmp_path)
    catalog = PilotLessonCatalog(manifest_path=manifest_path)

    def _planner_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        payload = planner_payload
        if isinstance(planner_payload, dict) and "turn_kind" not in planner_payload:
            parsed = json.loads(prompt)
            payload = planner_payload.get(
                parsed["turn_kind"],
                planner_payload.get("default", planner_payload),
            )
        return json.dumps(payload)

    def _responder_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (prompt, system_prompt, history_messages, kwargs)
        return responder_text

    return LessonRuntime(
        catalog,
        planner=LessonPlanner(_planner_llm),
        responder=LessonResponder(_responder_llm),
    )


class _StubMemoryProvider:
    def __init__(self, summary, *, project="peptutor-lesson"):
        self.summary = summary
        self.project = project

    def get_summary(self, **kwargs):
        _ = kwargs
        return self.summary


class _FailingMemoryProvider(_StubMemoryProvider):
    def get_summary(self, **kwargs):
        _ = kwargs
        raise RuntimeError("memory lookup boom")


class _StubMemoryWriter:
    def __init__(
        self,
        *,
        project="peptutor-lesson",
        ensure_session_id="memory-session-1",
        fail_on_record=False,
        fail_on_ensure=False,
    ):
        self.project = project
        self.ensure_session_id = ensure_session_id
        self.fail_on_record = fail_on_record
        self.fail_on_ensure = fail_on_ensure
        self.recorded_turns = []

    def ensure_session(self, **kwargs):
        _ = kwargs
        if self.fail_on_ensure:
            raise RuntimeError("ensure session boom")
        return self.ensure_session_id

    def record_turn(self, **kwargs):
        if self.fail_on_record:
            raise RuntimeError("record turn boom")
        self.recorded_turns.append(kwargs)

    def summarize_session(self, **kwargs):
        _ = kwargs

    def finalize_session(self, **kwargs):
        _ = kwargs


def _fake_embed_texts(texts):
    vectors = []
    for text in texts:
        lower = text.casefold()
        if "role play" in lower or "role-play" in lower:
            vectors.append([1.0, 0.0, 0.0])
        elif "salad" in lower:
            vectors.append([0.0, 1.0, 0.0])
        elif "breakfast" in lower or "noodles" in lower:
            vectors.append([0.0, 0.0, 1.0])
        else:
            vectors.append([0.1, 0.1, 0.1])
    return vectors


def test_start_page_returns_intro_and_probe(tmp_path):
    runtime = _make_runtime(tmp_path)

    result = runtime.start_page("TB-G5S1U3-P24", "student-1")

    assert result.turn_label == "page_entry"
    assert result.retrieval_mode == "none"
    assert result.state.awaiting_answer is True
    assert result.block_uid == "TB-G5S1U3-P24-D1"
    assert "点餐和饮料表达" in result.teacher_response


def test_page_entry_overviews_multi_module_page_before_drilling(tmp_path):
    manifest_path = _write_multi_module_review_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))

    result = runtime.start_page("TB-G5S2U9-P12", "student-1")

    assert result.turn_label == "page_entry"
    assert result.teaching_action == "page_intro"
    assert result.state.awaiting_answer is True
    assert result.state.current_activity_type == "page_entry"
    assert result.state.last_teacher_question == (
        "你想先学哪一块？可以说 Let's check 或 Let's wrap it up。"
    )
    assert "Let's check" in result.teacher_response
    assert "Let's wrap it up" in result.teacher_response
    assert "你想先学哪一块" in result.teacher_response
    assert "先试着说一遍" not in result.teacher_response
    assert "Listen and number" not in result.teacher_response
    assert "TB-G5S2U4-P44" not in Path(
        "lightrag/orchestrator/page_overview_skill.py"
    ).read_text(encoding="utf-8")


def test_page_entry_overview_is_passed_to_live_responder(tmp_path):
    manifest_path = _write_multi_module_review_pilot(tmp_path)
    captured: list[dict[str, object]] = []

    def _teacher_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        parsed = json.loads(prompt)
        captured.append(parsed)
        return "这一页有两块：Let's check 和 Let's wrap it up。你想先学哪一块？"

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(_teacher_llm),
    )

    result = runtime.start_page("TB-G5S2U9-P12", "student-1")

    assert "Let's check" in result.teacher_response
    assert captured[0]["page"]["page_overview"]["source"] == "page_overview_skill"
    assert [module["label"] for module in captured[0]["page"]["page_overview"]["modules"]] == [
        "Let's check",
        "Let's wrap it up",
    ]
    assert any(
        "page.page_overview" in rule for rule in captured[0]["output_rules"]
    )


def test_page_entry_overview_choice_starts_selected_module(tmp_path):
    manifest_path = _write_multi_module_review_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G5S2U9-P12", "student-1")

    result = runtime.handle_turn(start.state, "Let's wrap it up")

    assert result.turn_label == "navigation"
    assert result.teaching_action == "probe"
    assert result.block_uid == "TB-G5S2U9-P12-D3"
    assert result.state.current_block_uid == "TB-G5S2U9-P12-D3"
    assert result.state.current_activity_type == "teaching"
    assert result.state.awaiting_answer is True
    assert "Let's wrap it up" in result.teacher_response
    assert "基数词和序数词" in result.teacher_response


def test_page_entry_fallback_hides_curriculum_metadata_when_model_unavailable(tmp_path):
    manifest_path = _write_shopping_list_task_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))

    result = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")

    assert "Theme:" not in result.teacher_response
    assert "开放性的活动" not in result.teacher_response
    assert "Create a personal party shopping list" not in result.teacher_response
    assert "小表达任务" in result.teacher_response
    assert "不用重复任务句" in result.teacher_response


def test_page_entry_prefers_llm_teacher_voice_over_fixed_fallback(tmp_path):
    manifest_path = _write_shopping_list_task_pilot(tmp_path)
    captured: list[dict[str, object]] = []
    captured_system_prompts: list[str] = []

    def _teacher_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (history_messages, kwargs)
        parsed = json.loads(prompt)
        captured.append(parsed)
        captured_system_prompts.append(system_prompt or "")
        return "我们今天要为告别派对准备清单，你先说一个想放进去的东西就好。"

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(_teacher_llm),
    )

    result = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")

    assert result.teacher_response == "我们今天要为告别派对准备清单，你先说一个想放进去的东西就好。"
    assert captured[0]["turn_label"] == "page_entry"
    assert captured[0]["teacher_kernel_source"] == "system_prompt"
    assert "teacher_soul" not in captured[0]
    assert "lesson_brief" in captured[0]
    assert "teaching_move" in captured[0]
    assert "fallback_response" not in captured[0]
    assert "safety_fallback_response" in captured[0]
    assert any(
        "not recommended wording" in rule
        for rule in captured[0]["response_contract"]
    )
    assert captured[0]["lesson_brief"]["page_context"]["page_uid"] == "TB-G6S2Recycle2-P49"
    assert captured[0]["teaching_move"]["detected_signal"] == "page_entry"
    assert captured[0]["teaching_move"]["move"] == "open_with_probe"
    assert (
        captured[0]["lesson_brief"]["answer_rubric"]["expected_answer_shape"]
        == "A concrete party-list item or a short first-person list sentence, for example: cake / orange juice / I'm going to bring cake."
    )
    assert "# Teacher Kernel" in captured_system_prompts[0]
    assert "# Lesson System Contract" not in captured_system_prompts[0]
    assert "# Teacher Soul" not in captured_system_prompts[0]
    assert len(captured_system_prompts[0]) < 2000
    assert LESSON_AUTHORITY_ORDER.index("lesson_brief") < LESSON_AUTHORITY_ORDER.index(
        "teacher_soul"
    )
    assert "Theme: A farewell party" in captured[0]["page"]["page_intro_cn"]
    assert any("transform page.page_intro_cn" in rule for rule in captured[0]["output_rules"])


def test_banned_teacher_phrase_matching_does_not_reject_personal_party_text():
    assert not system_contract_module.matches_banned_teacher_phrase(
        "你可以说：Create a personal party shopping list."
    )
    assert system_contract_module.matches_banned_teacher_phrase(
        "Do not mention the persona profile."
    )


def test_page_entry_rejects_llm_curriculum_metadata_copy(tmp_path):
    manifest_path = _write_shopping_list_task_pilot(tmp_path)
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(lambda *args, **kwargs: "Theme: A farewell party. 鼓励学生列清单。"),
    )

    result = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")

    assert "Theme:" not in result.teacher_response
    assert "鼓励学生" not in result.teacher_response
    assert "小表达任务" in result.teacher_response


def test_task_instruction_page_accepts_concrete_list_items(tmp_path):
    manifest_path = _write_shopping_list_task_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")

    result = runtime.handle_turn(start.state, "cake")

    assert result.evaluation == "correct"
    assert result.teaching_action == "confirm"


def test_task_instruction_page_rejects_task_echo_as_student_answer(tmp_path):
    manifest_path = _write_shopping_list_task_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")

    result = runtime.handle_turn(start.state, "Create a personal party shopping list.")

    assert result.evaluation == "incorrect"
    assert result.teaching_action == "hint"
    assert "开头带起来" not in result.teacher_response


def test_task_instruction_page_lightly_repairs_rough_item_sentence(tmp_path):
    manifest_path = _write_shopping_list_task_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")

    result = runtime.handle_turn(start.state, "I bring apple.")

    assert result.evaluation == "partially_correct"
    assert result.teaching_action == "hint"


def test_task_instruction_page_accepts_full_party_list_sentence(tmp_path):
    manifest_path = _write_shopping_list_task_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")

    result = runtime.handle_turn(start.state, "I'm going to bring some fruit and drinks.")

    assert result.evaluation == "correct"
    assert result.teaching_action == "confirm"


def test_roleplay_task_instruction_is_converted_to_classroom_action():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P25", "student-1")
    vocab = runtime.handle_turn(start.state, "tea")
    service_question = runtime.handle_turn(vocab.state, "What would you like to eat?")
    result = runtime.handle_turn(service_question.state, "I'd like a sandwich, please.")

    assert result.evaluation == "correct"
    assert result.teaching_action == "confirm"
    assert result.state.current_block_uid == "TB-G5S1U3-P25-D3"
    assert "Practice ordering food and drinks" not in result.teacher_response
    assert "小对话" in result.teacher_response or "顾客" in result.teacher_response


def test_answer_turn_uses_local_evaluation_before_retrieval(tmp_path):
    runtime = _make_runtime(tmp_path)
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    result = runtime.handle_turn(start.state, "I'd like some water.")

    assert result.evaluation == "correct"
    assert result.retrieval_mode == "none"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D2"


def test_lesson_runtime_uses_langgraph_turn_graph(tmp_path):
    runtime = _make_runtime(tmp_path)

    graph_nodes = set(runtime.turn_graph.get_graph().nodes)
    assert {
        "start_page",
        "switch_page",
        "normalize_turn",
        "answer_turn",
        "open_turn",
        "after_turn",
    }.issubset(graph_nodes)

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "I'd like some water.")

    assert start.turn_label == "page_entry"
    assert result.turn_label == "answer_question"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D2"


def test_lesson_turn_route_omits_debug_signals_by_default(tmp_path):
    runtime = _make_runtime(tmp_path)
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    response = client.post("/lesson/turn", json={"page_uid": "TB-G5S1U3-P24"})

    assert response.status_code == 200
    assert "debug_signals" not in response.json()


def test_lesson_turn_route_includes_debug_signals_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("PEPTUTOR_DEBUG_SIGNALS", "1")
    runtime = _make_runtime(tmp_path)
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    response = client.post("/lesson/turn", json={"page_uid": "TB-G5S1U3-P24"})

    assert response.status_code == 200
    debug_signals = response.json()["debug_signals"]
    persona = debug_signals.pop("persona")
    assert debug_signals == {
        "live_prompts": {"enabled": False},
        "vector_retrieval": {"enabled": False, "hit_modes": []},
        "prompt_memory": {"enabled": False, "injected_buckets": []},
        "semantic_recall": {"enabled": False, "recalled_memories": []},
        "memory_runtime": {
            "student_id": "demo-student",
            "project": "peptutor-lesson",
            "memory_session_id": None,
            "last_recall_status": "skipped",
            "last_recall_summary": "Backend prompt-memory recall is disabled or unavailable.",
            "last_writeback_status": "skipped",
            "last_writeback_summary": "Backend learner-memory writeback is disabled or unavailable.",
            "degradation_state": "memory_disabled",
        },
    }
    assert persona == {
        "enabled": True,
        "schema_version": "lesson-persona-context/v1",
        "profile_id": "peptutor-teacher-v1",
        "profile_version": "2026-04-24",
        "display_name": "米粒",
        "voice_hint": "zh-CN-XiaoxiaoNeural",
        "allowed_to_shape": [
            "tone",
            "pacing",
            "encouragement",
            "scaffold_granularity",
            "classroom_habits",
            "speech_style",
            "embodied_performance",
        ],
        "protected_authorities": [
            "target_answer",
            "correctness_judgment",
            "page_progression",
            "retrieval_scope",
            "teaching_block",
            "required_teaching_action",
        ],
        "relationship_student_id": "demo-student",
        "relationship_signals": [],
        "common_mistakes": [],
        "preferences": [],
        "mastery_signals": [],
        "semantic_memories": [],
        "affect_state": {
            "student_confidence": "unknown",
            "teacher_energy": "calm",
            "stuckness": 0.0,
            "interruption_state": "none",
            "recent_turn_labels": ["page_entry"],
        },
        "airi_performance": {
            "emotion": "encouraging",
            "expression": "soft_smile",
            "motion": "Encourage",
            "speech_style": "normal",
            "mouth_intensity": 0.75,
            "interrupt_policy": "barge_in_allowed",
            "content_source": "lesson_runtime_teacher_response",
            "fallback_allowed": True,
        },
    }


def test_lesson_turn_stream_route_emits_action_text_and_done_events(tmp_path):
    runtime = _make_runtime(tmp_path)
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    start = client.post("/lesson/turn", json={"page_uid": "TB-G5S1U3-P24"})
    assert start.status_code == 200

    response = client.post(
        "/lesson/turn/stream",
        json={
            "page_uid": "TB-G5S1U3-P24",
            "state": start.json()["state"],
            "learner_input": "I'd like some water.",
            "turn_client_id": "browser-turn-1",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse_events(response.text)
    event_names = [name for name, _payload in events]
    assert event_names[0] == "meta"
    assert "action" in event_names
    assert "text_delta" in event_names
    assert event_names[-1] == "done"

    meta = events[0][1]
    assert meta == {
        "turn_client_id": "browser-turn-1",
        "page_uid": "TB-G5S1U3-P24",
    }

    action = next(payload for name, payload in events if name == "action")
    assert action["turn_client_id"] == "browser-turn-1"
    assert action["emotion"] == {"name": "happy", "intensity": 0.92}
    assert action["motion"] == "Happy"
    assert action["expression"] == "happy"
    assert action["teaching_action"] == "confirm"
    assert action["evaluation"] == "correct"
    assert action["speech_style"] == "normal"
    assert action["mouth_intensity"] == 0.8
    assert action["interrupt_policy"] == "barge_in_allowed"
    assert action["performance_source"] == "lesson_persona_context"

    text_chunks = [payload["text"] for name, payload in events if name == "text_delta"]
    done = events[-1][1]
    assert done["turn_client_id"] == "browser-turn-1"
    assert "".join(text_chunks) == done["result"]["teacher_response"]
    assert done["result"]["turn_label"] == "answer_question"


def test_lesson_turn_stream_route_prefers_persona_performance_plan_for_action(tmp_path):
    runtime = _make_runtime(tmp_path)
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    start = client.post("/lesson/turn", json={"page_uid": "TB-G5S1U3-P24"})
    assert start.status_code == 200

    response = client.post(
        "/lesson/turn/stream",
        json={
            "page_uid": "TB-G5S1U3-P24",
            "state": start.json()["state"],
            "learner_input": "banana",
            "turn_client_id": "browser-turn-action-plan",
        },
    )

    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    action = next(payload for name, payload in events if name == "action")
    assert action["teaching_action"] == "hint"
    assert action["evaluation"] == "unclear"
    assert action["emotion"] == {"name": "question", "intensity": 0.86}
    assert action["motion"] == "Think"
    assert action["expression"] == "think"
    assert action["duration_ms"] == 3400
    assert action["speech_style"] == "gentle_correction"
    assert action["mouth_intensity"] == 0.7
    assert action["interrupt_policy"] == "barge_in_allowed"
    assert action["content_source"] == "lesson_runtime_teacher_response"
    assert action["performance_source"] == "lesson_persona_context"


def test_lesson_turn_stream_route_streams_responder_deltas_before_done(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)

    def complete_text(*_args, **_kwargs):
        return "Start response."

    def stream_text(*_args, **_kwargs):
        yield "现场"
        yield "老师。"

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(complete_text, stream_text=stream_text),
    )
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    start = client.post("/lesson/turn", json={"page_uid": "TB-G5S1U3-P24"})
    assert start.status_code == 200

    response = client.post(
        "/lesson/turn/stream",
        json={
            "page_uid": "TB-G5S1U3-P24",
            "state": start.json()["state"],
            "learner_input": "I'd like some water.",
            "turn_client_id": "browser-turn-live",
        },
    )

    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    event_names = [name for name, _payload in events]
    assert event_names.index("action") < event_names.index("text_delta")
    assert event_names[-1] == "done"

    text_chunks = [payload["text"] for name, payload in events if name == "text_delta"]
    done = events[-1][1]
    assert text_chunks == ["现场", "老师。"]
    assert done["result"]["teacher_response"] == "现场老师。"


def test_lesson_turn_stream_route_keeps_done_text_equal_to_streamed_text(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)

    def complete_text(*_args, **_kwargs):
        return "Fallback response."

    def stream_text(*_args, **_kwargs):
        yield "现场老师"
        yield "\n"
        yield "继续。"

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(complete_text, stream_text=stream_text),
    )
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    start = client.post("/lesson/turn", json={"page_uid": "TB-G5S1U3-P24"})
    assert start.status_code == 200

    response = client.post(
        "/lesson/turn/stream",
        json={
            "page_uid": "TB-G5S1U3-P24",
            "state": start.json()["state"],
            "learner_input": "I'd like some water.",
            "turn_client_id": "browser-turn-live-whitespace",
        },
    )

    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    text_chunks = [payload["text"] for name, payload in events if name == "text_delta"]
    done = events[-1][1]
    assert text_chunks == ["现场老师", "\n", "继续。"]
    assert done["result"]["teacher_response"] == "".join(text_chunks)


def test_lesson_turn_stream_route_strips_markdown_tokens_before_tts(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)

    def complete_text(*_args, **_kwargs):
        return "Fallback response."

    def stream_text(*_args, **_kwargs):
        yield "请说 **cake**"
        yield " 或 `tea`。"

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(complete_text, stream_text=stream_text),
    )
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    start = client.post("/lesson/turn", json={"page_uid": "TB-G5S1U3-P24"})
    assert start.status_code == 200

    response = client.post(
        "/lesson/turn/stream",
        json={
            "page_uid": "TB-G5S1U3-P24",
            "state": start.json()["state"],
            "learner_input": "I'd like some water.",
            "turn_client_id": "browser-turn-live-markdown",
        },
    )

    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    text_chunks = [payload["text"] for name, payload in events if name == "text_delta"]
    done = events[-1][1]
    assert text_chunks == ["请说 cake", " 或 tea。"]
    assert done["result"]["teacher_response"] == "请说 cake 或 tea。"


def test_lesson_turn_stream_route_does_not_duplicate_partial_stream_failure(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)

    def complete_text(*_args, **_kwargs):
        return "Fallback response."

    def stream_text(*_args, **_kwargs):
        yield "Partial "
        raise RuntimeError("upstream stream closed")

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(complete_text, stream_text=stream_text),
    )
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    start = client.post("/lesson/turn", json={"page_uid": "TB-G5S1U3-P24"})
    assert start.status_code == 200

    response = client.post(
        "/lesson/turn/stream",
        json={
            "page_uid": "TB-G5S1U3-P24",
            "state": start.json()["state"],
            "learner_input": "I'd like some water.",
            "turn_client_id": "browser-turn-partial",
        },
    )

    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    text_chunks = [payload["text"] for name, payload in events if name == "text_delta"]
    done = events[-1][1]
    assert text_chunks == ["Partial "]
    assert done["result"]["teacher_response"] == "Partial "


def test_lesson_stream_text_chunks_preserve_english_sentence_spacing():
    teacher_response = "Good job. Now say one full drink sentence."

    chunks = _lesson_text_chunks(teacher_response)

    assert chunks == ["Good job. ", "Now say one full drink sentence."]
    assert "".join(chunks) == teacher_response


def test_lesson_airi_action_payload_covers_all_evaluation_profiles():
    cases = {
        "correct": ("happy", "Happy", "happy"),
        "acceptable": ("happy", "Happy", "happy"),
        "partially_correct": ("curious", "Curious", "think"),
        "incorrect": ("question", "Question", "think"),
        "off_topic": ("awkward", "Awkward", "neutral"),
        "unclear": ("question", "Question", "think"),
    }

    for evaluation, expected in cases.items():
        action = _airi_action_payload(
            _minimal_turn_result(evaluation=evaluation, teaching_action="confirm")
        )

        assert (
            action["emotion"]["name"],
            action["motion"],
            action["expression"],
        ) == expected
        assert action["duration_ms"] > 0
        assert action["reason"] == "lesson_turn"


def test_lesson_airi_action_payload_uses_performance_plan_before_static_profiles():
    action = _airi_action_payload_from_metadata(
        teaching_action="hint",
        evaluation="incorrect",
        branch_active=False,
        turn_label="answer_question",
        airi_performance={
            "emotion": "thinking",
            "motion": "Explain",
            "expression": "thinking",
            "speech_style": "slow_split",
            "mouth_intensity": 0.65,
            "interrupt_policy": "finish_current_sentence",
            "content_source": "lesson_runtime_teacher_response",
            "fallback_allowed": False,
        },
    )

    assert action["emotion"] == {"name": "think", "intensity": 0.78}
    assert action["motion"] == "Think"
    assert action["expression"] == "think"
    assert action["duration_ms"] == 3600
    assert action["speech_style"] == "slow_split"
    assert action["mouth_intensity"] == 0.65
    assert action["interrupt_policy"] == "finish_current_sentence"
    assert action["fallback_allowed"] is False
    assert action["performance_source"] == "lesson_persona_context"


def test_lesson_airi_action_payload_covers_all_teaching_action_profiles():
    cases = {
        "page_intro": ("curious", "Curious", "think"),
        "probe": ("question", "Question", "think"),
        "confirm": ("happy", "Happy", "happy"),
        "hint": ("curious", "Curious", "think"),
        "model": ("think", "Think", "think"),
        "repeat_drill": ("question", "Question", "think"),
        "explain": ("think", "Think", "think"),
        "redirect": ("awkward", "Awkward", "neutral"),
        "complete": ("happy", "Happy", "happy"),
    }

    for teaching_action, expected in cases.items():
        action = _airi_action_payload(
            _minimal_turn_result(evaluation=None, teaching_action=teaching_action)
        )

        assert (
            action["emotion"]["name"],
            action["motion"],
            action["expression"],
        ) == expected
        assert action["duration_ms"] > 0


def test_lesson_airi_action_payload_marks_branch_turn_reason():
    action = _airi_action_payload(
        _minimal_turn_result(
            evaluation=None,
            teaching_action="explain",
            state=_minimal_lesson_state(branch_active=True),
        )
    )

    assert action["reason"] == "lesson_branch_turn"


def test_lesson_turn_stream_route_returns_error_event_for_invalid_state(tmp_path):
    runtime = _make_runtime(tmp_path)
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    response = client.post(
        "/lesson/turn/stream",
        json={
            "page_uid": "TB-G5S1U3-P24",
            "learner_input": "I'd like some water.",
            "turn_client_id": "browser-turn-error",
        },
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert [name for name, _payload in events] == ["meta", "error"]
    assert events[-1][1] == {
        "turn_client_id": "browser-turn-error",
        "status_code": 400,
        "detail": "learner_input is only allowed after state initialization",
    }


def test_lesson_turn_route_surfaces_memory_recall_degradation_in_debug_signals(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PEPTUTOR_DEBUG_SIGNALS", "1")
    manifest_path = _write_test_pilot(tmp_path)
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        memory_provider=_FailingMemoryProvider(
            LearnerMemorySummary(student_id="student-route"),
            project="peptutor-debug",
        ),
        memory_writer=_StubMemoryWriter(
            project="peptutor-debug",
            ensure_session_id="memory-session-route-recall",
        ),
        feature_statuses={
            "prompt_injection": FeatureStatus(
                enabled=True, mode="explicit", reason="test prompt memory"
            ),
            "writeback": FeatureStatus(
                enabled=True, mode="explicit", reason="test writeback"
            ),
        },
    )
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    start = client.post(
        "/lesson/turn",
        json={"page_uid": "TB-G5S1U3-P24", "student_id": "student-route"},
    )
    assert start.status_code == 200

    response = client.post(
        "/lesson/turn",
        json={
            "page_uid": "TB-G5S1U3-P24",
            "student_id": "student-route",
            "state": start.json()["state"],
            "learner_input": "What does salad mean?",
        },
    )

    assert response.status_code == 200
    assert response.json()["debug_signals"]["memory_runtime"] == {
        "student_id": "student-route",
        "project": "peptutor-debug",
        "memory_session_id": "memory-session-route-recall",
        "last_recall_status": "degraded",
        "last_recall_summary": (
            "Learner-memory recall failed; continuing without backend injection."
        ),
        "last_writeback_status": "success",
        "last_writeback_summary": "Recorded learner turn in backend memory.",
        "degradation_state": "recall_degraded",
    }


def test_lesson_turn_route_surfaces_memory_writeback_degradation_in_debug_signals(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PEPTUTOR_DEBUG_SIGNALS", "1")
    manifest_path = _write_test_pilot(tmp_path)
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        memory_provider=_StubMemoryProvider(
            LearnerMemorySummary(
                student_id="student-route",
                stable_preferences=[
                    "Learner prefers Chinese explanation before retry."
                ],
            ),
            project="peptutor-debug",
        ),
        memory_writer=_StubMemoryWriter(
            project="peptutor-debug",
            ensure_session_id="memory-session-route-writeback",
            fail_on_record=True,
        ),
        feature_statuses={
            "prompt_injection": FeatureStatus(
                enabled=True, mode="explicit", reason="test prompt memory"
            ),
            "writeback": FeatureStatus(
                enabled=True, mode="explicit", reason="test writeback"
            ),
        },
    )
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    start = client.post(
        "/lesson/turn",
        json={"page_uid": "TB-G5S1U3-P24", "student_id": "student-route"},
    )
    assert start.status_code == 200

    response = client.post(
        "/lesson/turn",
        json={
            "page_uid": "TB-G5S1U3-P24",
            "student_id": "student-route",
            "state": start.json()["state"],
            "learner_input": "What does salad mean?",
        },
    )

    assert response.status_code == 200
    assert response.json()["debug_signals"]["memory_runtime"] == {
        "student_id": "student-route",
        "project": "peptutor-debug",
        "memory_session_id": "memory-session-route-writeback",
        "last_recall_status": "success",
        "last_recall_summary": "Injected buckets: stable_preferences.",
        "last_writeback_status": "degraded",
        "last_writeback_summary": "Backend learner-memory writeback failed for this turn.",
        "degradation_state": "writeback_degraded",
    }


def test_knowledge_question_during_answer_turn_reroutes_to_open_turn(tmp_path):
    runtime = _make_runtime_with_support(tmp_path)
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    start = client.post("/lesson/turn", json={"page_uid": "TB-G5S1U3-P24"})
    assert start.status_code == 200

    response = client.post(
        "/lesson/turn",
        json={
            "page_uid": "TB-G5S1U3-P24",
            "state": start.json()["state"],
            "learner_input": "What does salad mean?",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["turn_label"] == "ask_knowledge"
    assert payload["retrieval_mode"] == "unit"
    assert payload["retrieved_block_uids"] == ["TB-G5S1U3-P25-D1"]
    assert payload["support_entry_uids"] == ["LEX-G5S1U3-salad"]
    assert payload["state"]["same_goal_attempt_count"] == 0
    assert payload["state"]["awaiting_answer"] is True
    assert "沙拉" in payload["teacher_response"]


def test_catalog_route_returns_loaded_scope_outline(tmp_path):
    runtime = _make_runtime(tmp_path)
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    response = client.get("/lesson/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope_count"] == 1
    assert payload["page_count"] == 3
    assert payload["block_count"] == 4
    assert payload["scopes"] == [
        {
            "grade": "G5",
            "semester": "S1",
            "unit": "U3",
            "pages": [
                {
                    "page_uid": "TB-G5S1U3-P24",
                    "page": 24,
                    "page_type": "dialogue",
                    "page_intro_cn": "这一页练习点餐和饮料表达。",
                },
                {
                    "page_uid": "TB-G5S1U3-P25",
                    "page": 25,
                    "page_type": "reading",
                    "page_intro_cn": "这一页练习菜单和沙拉。",
                },
                {
                    "page_uid": "TB-G5S1U3-P26",
                    "page": 26,
                    "page_type": "dialogue",
                    "page_intro_cn": "这一页允许短暂聊早餐话题。",
                },
            ],
        }
    ]


def test_lesson_routes_apply_rate_limit(tmp_path, monkeypatch):
    utils_api.reset_request_rate_limit_state()
    monkeypatch.setattr(
        lesson_routes_module.global_args,
        "peptutor_lesson_rate_limit_requests",
        1,
        raising=False,
    )
    monkeypatch.setattr(
        lesson_routes_module.global_args,
        "peptutor_lesson_rate_limit_window_seconds",
        60,
        raising=False,
    )

    runtime = _make_runtime(tmp_path)
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    first = client.post("/lesson/turn", json={"page_uid": "TB-G5S1U3-P24"})
    second = client.post("/lesson/turn", json={"page_uid": "TB-G5S1U3-P24"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json() == {"detail": "Too many requests. Please try again later."}
    assert second.headers["retry-after"] == "60"


def test_help_request_during_answer_turn_reroutes_without_consuming_attempt(tmp_path):
    runtime = _make_runtime(tmp_path)
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    result = runtime.handle_turn(start.state, "help")

    assert result.turn_label == "ask_help"
    assert result.retrieval_mode == "none"
    assert result.state.same_goal_attempt_count == 0
    assert result.state.awaiting_answer is True
    assert result.teacher_response.startswith("没关系，")


def test_social_input_during_answer_turn_reroutes_to_social_redirect(tmp_path):
    runtime = _make_runtime(tmp_path)
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")
    current_block_uid = advanced.state.current_block_uid

    result = runtime.handle_turn(advanced.state, "I played soccer yesterday.")

    assert result.turn_label == "social"
    assert result.teaching_action == "redirect"
    assert result.retrieval_mode == "none"
    assert result.state.current_block_uid == current_block_uid
    assert result.state.awaiting_answer is True
    assert "继续这一页" in result.teacher_response or "What would you like to drink?" in result.teacher_response


def test_wrong_domain_answer_still_stays_in_answer_path(tmp_path):
    runtime = _make_runtime(tmp_path)
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")

    result = runtime.handle_turn(advanced.state, "I'd like chicken and bread.")

    assert result.turn_label == "answer_question"
    assert result.teaching_action == "hint"
    assert result.evaluation == "incorrect"


def test_open_knowledge_turn_uses_block_retrieval(tmp_path):
    runtime = _make_runtime(tmp_path)
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    response = client.post(
        "/lesson/turn",
        json={
            "page_uid": "TB-G5S1U3-P24",
            "state": open_state.model_dump(),
            "learner_input": "What does water mean?",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["turn_label"] == "ask_knowledge"
    assert payload["retrieval_mode"] == "block"
    assert payload["retrieved_block_uids"] == ["TB-G5S1U3-P24-D1"]


def test_open_knowledge_turn_can_expand_to_page_scope(tmp_path):
    runtime = _make_runtime(tmp_path)
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "How do I do the role play?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "page"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P24-D2"]


def test_open_knowledge_turn_can_expand_to_unit_scope(tmp_path):
    runtime = _make_runtime(tmp_path)
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does salad mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P25-D1"]


def test_open_knowledge_turn_can_use_support_lexicon_entry(tmp_path):
    runtime = _make_runtime_with_support(tmp_path)
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does sandwich mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "block"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P24-D1"]
    assert result.support_entry_uids == ["LEX-G5S1U3-sandwich"]
    assert "三明治" in result.teacher_response


def test_lexicon_query_prefers_unit_scope_over_branch(tmp_path):
    runtime = _make_runtime_with_support(tmp_path)
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does noodles mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P26-D1"]
    assert result.support_entry_uids == ["LEX-G5S1U3-noodles"]
    assert "面条" in result.teacher_response


def test_branch_scope_sets_return_anchor_and_branch_state(tmp_path):
    runtime = _make_runtime(tmp_path)
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "Can I eat noodles for breakfast?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "branch"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P26-D1"]
    assert result.return_anchor == "What would you like to eat?"
    assert result.state.branch_active is True

    follow_up = runtime.handle_turn(result.state, "okay")
    assert follow_up.retrieval_mode == "none"
    assert follow_up.turn_label == "social"
    assert "What would you like to eat?" in follow_up.teacher_response


def test_live_prompts_can_override_knowledge_retrieval_mode_and_response(tmp_path):
    runtime = _make_runtime_with_live_prompts(
        tmp_path,
        planner_payload={
            "teaching_action": "explain",
            "retrieval_mode": "block",
            "response_focus": "Stay close to the current block.",
        },
        responder_text="先看当前这句，再慢慢扩展。",
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "How do I do the role play?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "block"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P24-D1"]
    assert result.teacher_response == "先看当前这句，再慢慢扩展。"


def test_live_route_classifier_can_promote_social_input_to_knowledge_turn(tmp_path):
    runtime = _make_runtime_with_live_prompts(
        tmp_path,
        planner_payload={
            "route_classifier": {
                "turn_label": "ask_knowledge",
                "reason": "The learner wants word knowledge.",
            },
            "ask_knowledge": {
                "teaching_action": "explain",
                "retrieval_mode": "block",
                "response_focus": "Answer from the current block.",
            },
        },
        responder_text="先贴着这句理解一下。",
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "sandwich please")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "block"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P24-D1"]
    assert result.teacher_response == "先贴着这句理解一下。"


def test_live_planner_falls_back_to_deterministic_knowledge_selection(tmp_path):
    runtime = _make_runtime_with_live_prompts(
        tmp_path,
        planner_payload={"teaching_action": "complete", "retrieval_mode": "page"},
        responder_text="",
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does salad mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P25-D1"]
    assert "本单元里还能连到" in result.teacher_response


def test_live_route_classifier_falls_back_to_deterministic_label(tmp_path):
    runtime = _make_runtime_with_live_prompts(
        tmp_path,
        planner_payload={
            "route_classifier": {
                "turn_label": "navigation",
                "reason": "invalid on purpose",
            }
        },
        responder_text="",
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "help me")

    assert result.turn_label == "ask_help"
    assert result.teaching_action in {"hint", "redirect"}
    assert result.retrieval_mode == "none"
    assert "先拆小一点" in result.teacher_response or "回到这一页" in result.teacher_response


def test_live_prompts_can_drive_ask_help_action_and_response(tmp_path):
    runtime = _make_runtime_with_live_prompts(
        tmp_path,
        planner_payload={
            "ask_help": {
                "teaching_action": "redirect",
                "retrieval_mode": "none",
                "response_focus": "Redirect to the active page prompt.",
            }
        },
        responder_text="我们先回到这一页的问题，再试一次。",
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "help me")

    assert result.turn_label == "ask_help"
    assert result.teaching_action == "redirect"
    assert result.retrieval_mode == "none"
    assert result.teacher_response == "我们先回到这一页的问题，再试一次。"


def test_live_route_classifier_does_not_downgrade_emotional_help_to_social(tmp_path):
    runtime = _make_runtime_with_live_prompts(
        tmp_path,
        planner_payload={
            "route_classifier": {
                "turn_label": "social",
                "reason": "invalid emotional downgrade on purpose",
            },
            "ask_help": {
                "teaching_action": "hint",
                "retrieval_mode": "none",
                "response_focus": "Receive the feeling first, then give one small next step.",
            },
        },
        responder_text="先别急，我们慢慢来。你可以说：I'd like water. 或者 I'd like some tea.",
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")

    result = runtime.handle_turn(advanced.state, "老师我有点紧张")

    assert result.turn_label == "ask_help"
    assert result.retrieval_mode == "none"
    assert "先别急" in result.teacher_response


def test_live_prompts_can_update_branch_close_anchor(tmp_path):
    runtime = _make_runtime_with_live_prompts(
        tmp_path,
        planner_payload={
            "ask_knowledge": {
                "teaching_action": "explain",
                "retrieval_mode": "branch",
                "return_anchor": "What would you like to eat?",
                "branch_reason": "topic_extension",
                "response_focus": "Keep the branch short.",
            },
            "branch_close": {
                "teaching_action": "redirect",
                "retrieval_mode": "none",
                "return_anchor": "I'd like some water.",
                "response_focus": "Bridge back with the drink sentence.",
            },
        },
        responder_text="我们绕回本页，用这句接上：I'd like some water.",
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    branch_result = runtime.handle_turn(open_state, "Can I eat noodles for breakfast?")
    follow_up = runtime.handle_turn(branch_result.state, "okay")

    assert branch_result.retrieval_mode == "branch"
    assert follow_up.turn_label == "social"
    assert follow_up.retrieval_mode == "none"
    assert follow_up.return_anchor == "I'd like some water."
    assert follow_up.teacher_response == "我们绕回本页，用这句接上：I'd like some water."


def test_live_prompts_receive_learner_memory_payload(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    learner_memory = LearnerMemorySummary(
        student_id="student-1",
        common_mistakes=["Student often omits some when ordering drinks."],
        preferences=["Student prefers Chinese explanation before retry."],
        mastery_signals=["Student can now answer I'd like some water correctly."],
        stable_preferences=["Student prefers Chinese explanation before retry."],
        summary_text=(
            "Common mistakes:\n"
            "- Student often omits some when ordering drinks.\n"
            "Preferences:\n"
            "- Student prefers Chinese explanation before retry.\n"
            "Mastery signals:\n"
            "- Student can now answer I'd like some water correctly.\n"
            "Stable learner profile:\n"
            "- Stable preference: Student prefers Chinese explanation before retry."
        ),
    )
    captured = {}

    def _planner_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        parsed = json.loads(prompt)
        captured[parsed["turn_kind"]] = parsed["learner_memory"]
        if parsed["turn_kind"] == "route_classifier":
            return json.dumps(
                {
                    "turn_label": "ask_help",
                    "reason": "The learner needs scaffolded help.",
                }
            )
        return json.dumps(
            {
                "teaching_action": "redirect",
                "retrieval_mode": "none",
                "response_focus": "Use the learner preference for Chinese scaffolding.",
            }
        )

    def _responder_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        parsed = json.loads(prompt)
        captured["responder"] = parsed["learner_memory"]
        return "按你更喜欢的中文拆解，我们先回到这一页。"

    runtime = LessonRuntime(
        catalog,
        planner=LessonPlanner(_planner_llm),
        responder=LessonResponder(_responder_llm),
        memory_provider=_StubMemoryProvider(learner_memory),
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "help me")

    assert captured["route_classifier"]["preferences"] == [
        "Student prefers Chinese explanation before retry."
    ]
    assert captured["ask_help"]["common_mistakes"] == [
        "Student often omits some when ordering drinks."
    ]
    assert captured["ask_help"]["stable_preferences"] == [
        "Student prefers Chinese explanation before retry."
    ]
    assert "Mastery signals:" in captured["responder"]["summary_text"]
    assert result.teacher_response == "按你更喜欢的中文拆解，我们先回到这一页。"


def test_debug_signals_report_live_vector_prompt_memory_and_semantic_usage(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("PEPTUTOR_DEBUG_SIGNALS", "1")
    qdrant_client = importlib.import_module("qdrant_client")
    manifest_path = _write_test_pilot(tmp_path)
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    store = QdrantTeachingStore(
        client=qdrant_client.QdrantClient(location=":memory:"),
        collection_name="lesson_runtime_debug_signals",
    )
    retriever = QdrantLessonRetriever(
        catalog=catalog,
        store=store,
        embed_texts=_fake_embed_texts,
    )
    learner_memory = LearnerMemorySummary(
        student_id="student-1",
        common_mistakes=["Student often omits some when ordering drinks."],
        preferences=["Student prefers Chinese explanation before retry."],
        stable_preferences=["Student prefers Chinese explanation before retry."],
        semantic_memories=["Learner gets shy when asked to answer aloud."],
        summary_text="Prompt memory summary for debug signals.",
    )
    memory_writer = _StubMemoryWriter(
        project="peptutor-debug",
        ensure_session_id="memory-session-debug",
    )

    def _planner_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        parsed = json.loads(prompt)
        if parsed["turn_kind"] == "route_classifier":
            return json.dumps(
                {
                    "turn_label": "ask_knowledge",
                    "reason": "Use the unit retrieval path.",
                }
            )
        return json.dumps(
            {
                "teaching_action": "explain",
                "retrieval_mode": "unit",
                "response_focus": "Use the unit-level salad evidence.",
            }
        )

    def _responder_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (prompt, system_prompt, history_messages, kwargs)
        return "我们先把 salad 这一句弄明白。"

    runtime = LessonRuntime(
        catalog,
        retriever=retriever,
        planner=LessonPlanner(_planner_llm),
        responder=LessonResponder(_responder_llm),
        memory_provider=_StubMemoryProvider(learner_memory, project="peptutor-debug"),
        memory_writer=memory_writer,
        feature_statuses={
            "live_prompts": FeatureStatus(enabled=True, mode="explicit", reason="test live prompts"),
            "vector_retrieval": FeatureStatus(enabled=True, mode="explicit", reason="test vector retrieval"),
            "prompt_injection": FeatureStatus(enabled=True, mode="explicit", reason="test prompt memory"),
            "semantic_recall": FeatureStatus(enabled=True, mode="explicit", reason="test semantic recall"),
            "writeback": FeatureStatus(enabled=True, mode="explicit", reason="test writeback"),
        },
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Payload indexes have no effect in the local Qdrant.*",
        )
        result = runtime.handle_turn(open_state, "What does salad mean?")

    assert isinstance(result.debug_signals, LessonTurnDebugSignals)
    assert result.debug_signals.live_prompts.enabled is True
    assert result.debug_signals.vector_retrieval.enabled is True
    assert result.debug_signals.vector_retrieval.hit_modes == ["unit"]
    assert result.debug_signals.prompt_memory.enabled is True
    assert result.debug_signals.prompt_memory.injected_buckets == [
        "common_mistakes",
        "preferences",
        "stable_preferences",
    ]
    assert result.debug_signals.semantic_recall.enabled is True
    assert result.debug_signals.semantic_recall.recalled_memories == [
        "Learner gets shy when asked to answer aloud."
    ]
    assert result.debug_signals.persona.profile_id == "peptutor-teacher-v1"
    assert result.debug_signals.persona.profile_version == "2026-04-24"
    assert result.debug_signals.persona.voice_hint == "zh-CN-XiaoxiaoNeural"
    assert result.debug_signals.persona.relationship_student_id == "student-1"
    assert result.debug_signals.persona.relationship_signals == [
        "stored_mistake_pattern",
        "chinese_scaffold",
        "target_sentence_completion_risk",
        "low_confidence_risk",
    ]
    assert result.debug_signals.persona.affect_state.teacher_energy == "focused"
    assert result.debug_signals.persona.affect_state.stuckness == 0.1
    assert result.debug_signals.persona.airi_performance.emotion == "thinking"
    assert result.debug_signals.persona.airi_performance.motion == "Explain"
    assert result.debug_signals.memory_runtime.student_id == "student-1"
    assert result.debug_signals.memory_runtime.project == "peptutor-debug"
    assert result.debug_signals.memory_runtime.memory_session_id == "memory-session-debug"
    assert result.debug_signals.memory_runtime.last_recall_status == "success"
    assert (
        result.debug_signals.memory_runtime.last_recall_summary
        == "Injected buckets: common_mistakes / preferences / stable_preferences. Semantic hits: 1. Prompt summary available."
    )
    assert result.debug_signals.memory_runtime.last_writeback_status == "success"
    assert (
        result.debug_signals.memory_runtime.last_writeback_summary
        == "Recorded learner turn in backend memory."
    )
    assert result.debug_signals.memory_runtime.degradation_state == "healthy"
    assert len(memory_writer.recorded_turns) == 1


def test_debug_signals_mark_memory_recall_as_degraded_on_lookup_failure(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("PEPTUTOR_DEBUG_SIGNALS", "1")
    manifest_path = _write_test_pilot(tmp_path)
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    runtime = LessonRuntime(
        catalog,
        memory_provider=_FailingMemoryProvider(
            LearnerMemorySummary(student_id="student-1"),
            project="peptutor-debug",
        ),
        memory_writer=_StubMemoryWriter(
            project="peptutor-debug",
            ensure_session_id="memory-session-degraded",
        ),
        feature_statuses={
            "prompt_injection": FeatureStatus(enabled=True, mode="explicit", reason="test prompt memory"),
            "writeback": FeatureStatus(enabled=True, mode="explicit", reason="test writeback"),
        },
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "What does salad mean?")

    assert result.debug_signals is not None
    assert result.debug_signals.memory_runtime.last_recall_status == "degraded"
    assert (
        result.debug_signals.memory_runtime.last_recall_summary
        == "Learner-memory recall failed; continuing without backend injection."
    )
    assert result.debug_signals.memory_runtime.last_writeback_status == "success"
    assert result.debug_signals.memory_runtime.degradation_state == "recall_degraded"


def test_debug_signals_mark_memory_writeback_as_degraded_on_record_failure(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("PEPTUTOR_DEBUG_SIGNALS", "1")
    manifest_path = _write_test_pilot(tmp_path)
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    learner_memory = LearnerMemorySummary(
        student_id="student-1",
        stable_preferences=["Learner prefers Chinese explanation before retry."],
    )
    runtime = LessonRuntime(
        catalog,
        memory_provider=_StubMemoryProvider(learner_memory, project="peptutor-debug"),
        memory_writer=_StubMemoryWriter(
            project="peptutor-debug",
            ensure_session_id="memory-session-writeback-degraded",
            fail_on_record=True,
        ),
        feature_statuses={
            "prompt_injection": FeatureStatus(enabled=True, mode="explicit", reason="test prompt memory"),
            "writeback": FeatureStatus(enabled=True, mode="explicit", reason="test writeback"),
        },
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "What does salad mean?")

    assert result.debug_signals is not None
    assert result.debug_signals.memory_runtime.last_recall_status == "success"
    assert result.debug_signals.memory_runtime.last_writeback_status == "degraded"
    assert (
        result.debug_signals.memory_runtime.last_writeback_summary
        == "Backend learner-memory writeback failed for this turn."
    )
    assert result.debug_signals.memory_runtime.degradation_state == "writeback_degraded"


def test_default_manifest_start_page_localizes_opening_prompt():
    runtime = LessonRuntime(PilotLessonCatalog())

    result = runtime.start_page("TB-G5S1U3-P24", "student-1")

    assert "This page teaches" not in result.teacher_response
    assert "这一页" in result.teacher_response
    assert "点餐" in result.teacher_response
    assert "hungry" in result.teacher_response


def test_default_manifest_hint_uses_probe_aligned_model_answer():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    result = runtime.handle_turn(start.state, "banana")

    assert result.evaluation == "unclear"
    assert "A sandwich, please." not in result.teacher_response
    assert "hungry" in result.teacher_response


def test_default_manifest_page25_opening_uses_localized_vocab_probe():
    runtime = LessonRuntime(PilotLessonCatalog())

    result = runtime.start_page("TB-G5S1U3-P25", "student-1")

    assert "This page teaches" not in result.teacher_response
    assert "这一页" in result.teacher_response
    assert "认不认识" in result.teacher_response
    assert "salad" in result.teacher_response


def test_default_manifest_help_scaffolds_sentence_probe():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "help")

    assert result.turn_label == "ask_help"
    assert "假设你饿了" in result.teacher_response or "饿了" in result.teacher_response
    assert "I am hungry." in result.teacher_response


def test_default_manifest_help_after_answer_prompt_prefers_learner_answer():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")
    block = runtime.catalog.get_block(advanced.state.current_block_uid)
    targets = runtime._best_model_answers(
        block,
        advanced.state.last_teacher_question,
        limit=2,
    )

    result = runtime.handle_turn(advanced.state, "help")

    assert result.turn_label == "ask_help"
    assert targets[0] in result.teacher_response
    assert targets[1] in result.teacher_response
    assert "..." not in result.teacher_response
    assert "chicken and bread" not in result.teacher_response
    assert "What would you like to" not in result.teacher_response


def test_default_manifest_slow_split_request_during_answer_routes_to_help():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")
    block = runtime.catalog.get_block(advanced.state.current_block_uid)
    targets = runtime._best_model_answers(
        block,
        advanced.state.last_teacher_question,
        limit=2,
    )

    result = runtime.handle_turn(advanced.state, "老师请慢一点拆开讲，我有点跟不上。")

    assert result.turn_label == "ask_help"
    assert result.teaching_action == "hint"
    assert result.retrieval_mode == "none"
    assert targets[0] in result.teacher_response
    assert targets[1] in result.teacher_response
    assert result.evaluation is None


def test_default_manifest_hint_after_answer_prompt_prefers_learner_answer():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")
    block = runtime.catalog.get_block(advanced.state.current_block_uid)
    targets = runtime._best_model_answers(
        block,
        advanced.state.last_teacher_question,
        limit=2,
    )

    result = runtime.handle_turn(advanced.state, "A sandwich, please.")

    assert result.turn_label == "answer_question"
    assert result.teaching_action == "hint"
    assert targets[0] in result.teacher_response
    assert targets[1] in result.teacher_response
    assert "..." not in result.teacher_response
    assert "chicken and bread" not in result.teacher_response
    assert "What would you like to" not in result.teacher_response


def test_default_manifest_drink_prompt_rejects_food_answer():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")

    result = runtime.handle_turn(advanced.state, "I'd like chicken and bread.")

    assert result.turn_label == "answer_question"
    assert result.evaluation == "incorrect"
    assert result.teaching_action == "hint"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D3"
    assert "I'd like some tea." in result.teacher_response
    assert "I'd like water." in result.teacher_response


def test_default_manifest_drink_prompt_keeps_single_word_answer_in_practice():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")

    result = runtime.handle_turn(advanced.state, "water")

    assert result.turn_label == "answer_question"
    assert result.evaluation == "partially_correct"
    assert result.teaching_action == "hint"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D3"
    assert result.state.awaiting_answer is True
    assert "I'd like" in result.teacher_response
    assert "口渴" not in result.teacher_response


def test_default_manifest_correct_drink_answer_advances_to_food_prompt():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")

    result = runtime.handle_turn(advanced.state, "I'd like some tea.")

    assert result.turn_label == "answer_question"
    assert result.evaluation == "correct"
    assert result.teaching_action == "confirm"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D4"
    assert result.state.awaiting_answer is True
    assert result.state.last_teacher_question == "Can you repeat: What would you like to eat?"
    assert "服务员会问你" in result.teacher_response
    assert "What - would - you - like - to - eat?" in result.teacher_response


def test_default_manifest_food_question_echo_stays_on_same_block_then_promotes_answer_prompt():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")
    drink_step = runtime.handle_turn(advanced.state, "I'd like some tea.")

    result = runtime.handle_turn(drink_step.state, "What would you like to eat?")

    assert result.turn_label == "answer_question"
    assert result.evaluation == "correct"
    assert result.teaching_action == "confirm"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D4"
    assert result.state.awaiting_answer is True
    assert result.state.last_teacher_question == "现在你想点吃的，跟老师选一句说：I'd like chicken and bread. 或 I'd like rice and vegetables."
    assert "好，这句服务员的话会了" in result.teacher_response
    assert "I'd like chicken and bread." in result.teacher_response


def test_default_manifest_food_prompt_accepts_food_answer_after_drink_step():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")
    drink_step = runtime.handle_turn(advanced.state, "I'd like some tea.")
    question_echo = runtime.handle_turn(drink_step.state, "What would you like to eat?")

    result = runtime.handle_turn(question_echo.state, "I'd like chicken and bread.")

    assert result.turn_label == "answer_question"
    assert result.evaluation == "correct"
    assert result.teaching_action == "confirm"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D1"
    assert result.state.awaiting_answer is True
    assert "bread and noodles" in result.teacher_response


def test_default_manifest_emotion_input_during_answer_turn_reroutes_to_help():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")

    result = runtime.handle_turn(advanced.state, "老师我有点紧张")

    assert result.turn_label == "ask_help"
    assert result.retrieval_mode == "none"
    assert result.state.current_block_uid == advanced.state.current_block_uid
    assert result.state.awaiting_answer is True
    assert "先别急" in result.teacher_response


def test_responder_marks_concrete_fallback_answer_as_must_keep_phrase():
    responder = LessonResponder(lambda *args, **kwargs: "")
    prompt = responder._build_prompt(
        learner_input="help",
        turn_label="ask_help",
        decision=PlannerDecision(
            teaching_action="hint",
            retrieval_mode="none",
            response_focus="Give a calm hint and keep the learner trying.",
        ),
        state_snapshot={},
        page_snapshot={},
        block_snapshot={
            "allowed_answer_scope": ["I'd like some tea.", "I'd like water."],
            "core_patterns": ["What would you like to drink?", "I'd like ..."],
            "return_anchors": ["What would you like to drink?"],
        },
        learner_memory={},
        retrieval_evidence=[],
        support_evidence=[],
        return_anchor=None,
        fallback_response="没关系，你可以这样回答：I'd like some tea. 或 I'd like water.",
        must_keep_phrases=["I'd like some tea.", "I'd like water."],
    )

    payload = json.loads(prompt)

    assert payload["must_keep_phrases"] == ["I'd like some tea.", "I'd like water."]
    assert payload["teacher_kernel_source"] == "system_prompt"
    assert "teacher_soul" not in payload
    assert "fallback_response" not in payload
    assert "safety_fallback_response" in payload
    assert payload["natural_response_contract"]["mili_transfer_filters"] == [
        "hear_child_before_teaching",
        "one_small_step",
        "follow_child_readiness",
        "help_changes_method",
        "role_logic_stays_clear",
        "teacher_may_resize_method",
    ]
    assert payload["natural_response_contract"]["voice"].startswith("one fresh")
    assert "fixed catchphrases as a required sign-off" in payload[
        "natural_response_contract"
    ]["must_not_copy"]
    assert any("not recommended wording" in rule for rule in payload["response_contract"])
    assert not any("teacher_soul" in rule for rule in payload["response_contract"])
    assert any("must_keep_phrases" in rule for rule in payload["output_rules"])
    assert any("learner_memory.memory_layers" in rule for rule in payload["output_rules"])
    assert any("persona_context only" in rule for rule in payload["output_rules"])
    assert any("Never quote JSON keys" in rule for rule in payload["output_rules"])
    assert not any("Do you know the word hungry?" in rule for rule in payload["output_rules"])
    assert any("do not merely copy a keyword" in rule for rule in payload["output_rules"])
    assert any("Correct only the most important reachable point" in rule for rule in payload["output_rules"])


def test_responder_falls_back_when_live_response_is_english_only():
    responder = LessonResponder(lambda *args, **kwargs: "Alright, welcome to our story page.")
    fallback_response = "欢迎来到这一页！先听老师说一遍故事里的新词。"

    response = responder.render_teacher_turn(
        learner_input="",
        turn_label="page_entry",
        decision=PlannerDecision(
            teaching_action="page_intro",
            retrieval_mode="none",
            response_focus="Open the page in a child-facing way.",
        ),
        state_snapshot={},
        page_snapshot={},
        block_snapshot={},
        learner_memory={},
        retrieval_evidence=[],
        support_evidence=[],
        return_anchor=None,
        fallback_response=fallback_response,
    )

    assert response == fallback_response


def test_responder_falls_back_when_live_response_leaks_private_brief_or_move_fields():
    responder = LessonResponder(
        lambda *args, **kwargs: (
            "根据 lesson_brief 的 answer_scope 和 teaching_move.detected_signal，"
            "我应该让你说 cake。"
        )
    )
    fallback_response = "这句是任务说明，还不是你的清单。你换成一个东西就行，比如 cake。"

    response = responder.render_teacher_turn(
        learner_input="Create a personal party shopping list.",
        turn_label="answer_question",
        decision=PlannerDecision(
            teaching_action="hint",
            retrieval_mode="none",
            response_focus="Repair the task echo naturally.",
        ),
        state_snapshot={},
        page_snapshot={},
        block_snapshot={},
        learner_memory={},
        retrieval_evidence=[],
        support_evidence=[],
        return_anchor=None,
        fallback_response=fallback_response,
        lesson_brief={"answer_scope": {"acceptable_answers": ["cake"]}},
        teaching_move={
            "detected_signal": "task_echo",
            "move": "convert_task_echo_to_answer",
        },
    )

    assert response == fallback_response


def test_responder_falls_back_when_live_response_lets_memory_override_lesson():
    responder = LessonResponder(
        lambda *args, **kwargs: (
            "因为 memory 里说你喜欢果汁，所以这题 target_answer 改成 juice。"
        )
    )
    fallback_response = "先不改答案范围，我们贴着这一题来：Zoom would like a salad."

    response = responder.render_teacher_turn(
        learner_input="juice",
        turn_label="answer_question",
        decision=PlannerDecision(
            teaching_action="hint",
            retrieval_mode="none",
            response_focus="Keep the learner on the active target answer.",
        ),
        state_snapshot={},
        page_snapshot={},
        block_snapshot={},
        learner_memory={"preferences": ["likes juice"]},
        retrieval_evidence=[],
        support_evidence=[],
        return_anchor=None,
        fallback_response=fallback_response,
        persona_context={"relationship": {"preferences": ["likes juice"]}},
    )

    assert response == fallback_response


def test_responder_strips_markdown_from_live_teacher_voice():
    responder = LessonResponder(lambda *args, **kwargs: "对了。先跟老师说一遍——**cake**，意思是蛋糕。")

    response = responder.render_teacher_turn(
        learner_input="cake",
        turn_label="answer_question",
        decision=PlannerDecision(
            teaching_action="confirm",
            retrieval_mode="none",
            response_focus="Confirm a concrete party-list item.",
        ),
        state_snapshot={},
        page_snapshot={},
        block_snapshot={},
        learner_memory={},
        retrieval_evidence=[],
        support_evidence=[],
        return_anchor=None,
        fallback_response="对了，cake 可以放进清单里。",
    )

    assert response == "对了。先跟老师说一遍——cake，意思是蛋糕。"


def test_responder_falls_back_when_live_response_drops_required_question_phrase():
    responder = LessonResponder(lambda *args, **kwargs: "我们来练吃东西，先跟老师说一句。")
    fallback_response = (
        "服务员会问你：What would you like to eat? "
        "这句有点长，我们慢慢来：What - would - you - like - to - eat?"
    )

    response = responder.render_teacher_turn(
        learner_input="tea",
        turn_label="answer_question",
        decision=PlannerDecision(
            teaching_action="confirm",
            retrieval_mode="none",
            response_focus="Bridge into the next service question.",
        ),
        state_snapshot={},
        page_snapshot={},
        block_snapshot={
            "allowed_answer_scope": ["tea"],
            "core_patterns": ["What would you like to eat?"],
            "return_anchors": ["What would you like to eat?"],
        },
        learner_memory={},
        retrieval_evidence=[],
        support_evidence=[],
        return_anchor=None,
        fallback_response=fallback_response,
    )

    assert response == fallback_response


def test_load_teacher_soul_reads_repo_file():
    soul = load_teacher_soul()

    assert soul.startswith("# Teacher Soul")
    assert "pedagogy first" in soul
    assert "Transferable Teaching Principles" in soul
    assert "先听见孩子，再教课本" in soul
    assert "help 是求救信号，不是错误答案" in soul


def test_load_teacher_kernel_reads_compact_runtime_prompt():
    kernel = load_teacher_kernel()

    assert kernel.startswith("# Teacher Kernel")
    assert "You are Mili (米粒)" in kernel
    assert "Runtime context provides the active lesson goal" in kernel
    assert "retrieval" not in kernel.casefold()
    assert len(kernel) < 2000


def test_responder_system_prompt_uses_teacher_kernel_not_full_soul_or_contract():
    responder = LessonResponder(
        lambda *args, **kwargs: "",
        teacher_kernel="# Teacher Kernel\n- compact runtime teacher voice",
    )

    system_prompt = responder._build_system_prompt()

    assert system_prompt == "# Teacher Kernel\n- compact runtime teacher voice"
    assert "# Lesson System Contract" not in system_prompt
    assert "# Teacher Soul" not in system_prompt
    assert "Authority order:" not in system_prompt
    assert "Theme:" in BANNED_TEACHER_PHRASES
    assert "lesson_brief" in BANNED_TEACHER_PHRASES
    assert "teaching_move" in BANNED_TEACHER_PHRASES


def test_teacher_kernel_prompt_does_not_regress_to_soul_contract_or_banned_policy():
    kernel = load_teacher_kernel()
    responder = LessonResponder(lambda *args, **kwargs: "")
    system_prompt = responder._build_system_prompt()

    assert system_prompt == kernel
    assert len(system_prompt) < 2000
    assert "# Teacher Soul" not in system_prompt
    assert "Transferable Teaching Principles" not in system_prompt
    assert "## Sample Lines" not in system_prompt
    assert "这一页我们学点好吃的" not in system_prompt
    assert "差一点点" not in system_prompt
    assert "pedagogy first" not in system_prompt
    assert "help 是求救信号，不是错误答案" not in system_prompt
    assert "# Lesson System Contract" not in system_prompt
    assert "Authority order:" not in system_prompt
    assert "LESSON_AUTHORITY_ORDER" not in system_prompt
    assert "RAG policy" not in system_prompt
    assert "RAG_POLICY_RULES" not in system_prompt
    for rule in system_contract_module.RAG_POLICY_RULES:
        assert rule not in system_prompt
    assert not system_contract_module.matches_banned_teacher_phrase(system_prompt)


def test_live_responder_can_cover_page_entry_and_answer_turns(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    captured: list[dict[str, object]] = []
    captured_system_prompts: list[str] = []

    def _responder_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (history_messages, kwargs)
        parsed = json.loads(prompt)
        captured.append(parsed)
        captured_system_prompts.append(system_prompt or "")
        if (
            parsed["plan"]["teaching_action"] == "confirm"
            and parsed.get("must_keep_phrases")
        ):
            return (
                f"现场:{parsed['turn_label']}:{parsed['plan']['teaching_action']} "
                f"{parsed['must_keep_phrases'][0]}"
            )
        return f"现场:{parsed['turn_label']}:{parsed['plan']['teaching_action']}"

    runtime = LessonRuntime(
        catalog,
        responder=LessonResponder(
            _responder_llm,
            teacher_kernel="# Teacher Kernel\n- compact runtime teacher voice",
        ),
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    hint = runtime.handle_turn(start.state, "banana")
    restart = runtime.start_page("TB-G5S1U3-P24", "student-1")
    confirm = runtime.handle_turn(restart.state, "I'd like some water.")

    assert start.teacher_response == "现场:page_entry:page_intro"
    assert hint.teacher_response == "现场:answer_question:hint"
    assert confirm.teacher_response.startswith("现场:answer_question:confirm")
    assert captured[0]["teacher_kernel_source"] == "system_prompt"
    assert "teacher_soul" not in captured[0]
    assert captured_system_prompts[0] == "# Teacher Kernel\n- compact runtime teacher voice"
    assert captured[1]["plan"]["teaching_action"] == "hint"
    assert captured[2]["plan"]["teaching_action"] == "page_intro"
    assert captured[3]["plan"]["teaching_action"] == "confirm"
    assert captured[0]["persona_context"]["teacher_profile"]["profile_id"] == (
        "peptutor-teacher-v1"
    )
    assert captured[1]["persona_context"]["airi_performance"]["speech_style"] == (
        "gentle_correction"
    )
    assert captured[3]["persona_context"]["boundaries"] == {
        "content_authority": "lesson_runtime",
        "presentation_authority": "airi_runtime",
        "allowed_to_shape": [
            "tone",
            "pacing",
            "encouragement",
            "scaffold_granularity",
            "classroom_habits",
            "speech_style",
            "embodied_performance",
        ],
        "must_not_change": [
            "target_answer",
            "correctness_judgment",
            "page_progression",
            "retrieval_scope",
            "teaching_block",
            "required_teaching_action",
        ],
        "can_change_target_answer": False,
        "can_change_correctness_judgment": False,
        "can_change_page_progression": False,
    }


def test_live_responder_prompt_receives_persona_context_from_memory(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    captured: list[dict[str, object]] = []
    summary = LearnerMemorySummary(
        student_id="student-1",
        common_mistakes=["often omits some in full sentence answers"],
        preferences=["likes slow Chinese scaffold"],
        mastery_signals=["can answer the drink question"],
        semantic_memories=["Student feels nervous when asked to speak aloud."],
    )

    def _responder_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        parsed = json.loads(prompt)
        captured.append(parsed)
        persona = parsed["persona_context"]
        catchphrase = persona["teacher_profile"]["catchphrases"][0]
        return f"{catchphrase}，先抓住这一小句：I'd like some water."

    runtime = LessonRuntime(
        catalog,
        memory_provider=_StubMemoryProvider(summary),
        responder=LessonResponder(_responder_llm),
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    help_turn = runtime.handle_turn(start.state, "老师我很紧张")

    assert help_turn.turn_label == "ask_help"
    assert help_turn.teacher_response.startswith("我们慢慢来")

    persona = captured[-1]["persona_context"]
    assert persona["relationship"]["relationship_signals"] == [
        "stored_mistake_pattern",
        "slow_split_practice",
        "chinese_scaffold",
        "target_sentence_completion_risk",
        "low_confidence_risk",
        "recent_mastery_available",
    ]
    assert persona["relationship"]["common_mistakes"] == [
        "often omits some in full sentence answers"
    ]
    assert persona["relationship"]["semantic_memories"] == [
        "Student feels nervous when asked to speak aloud."
    ]
    assert persona["affect_state"]["student_confidence"] == "low"
    assert persona["airi_performance"]["speech_style"] == "slow_split"
    assert any("Lesson runtime remains the authority" in item for item in persona["prompt_contract"])


def test_persona_prompt_cannot_change_evaluation_or_page_progression(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    captured: list[dict[str, object]] = []

    def _responder_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        captured.append(json.loads(prompt))
        return "我们慢慢来，答对了就继续下一步。"

    runtime = LessonRuntime(catalog, responder=LessonResponder(_responder_llm))

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "I'd like some water.")

    assert result.evaluation == "correct"
    assert result.teaching_action == "confirm"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D2"
    assert result.state.awaiting_answer is True

    boundaries = captured[-1]["persona_context"]["boundaries"]
    assert boundaries["can_change_correctness_judgment"] is False
    assert boundaries["can_change_page_progression"] is False
    assert "correctness_judgment" in boundaries["must_not_change"]


def test_default_manifest_lexicon_question_prefers_unit_over_branch():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does salad mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.retrieved_block_uids[0] == "TB-G5S1U3-P25-D1"


def test_default_manifest_knowledge_query_during_answer_turn_returns_to_current_prompt():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    result = runtime.handle_turn(start.state, "What does salad mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.state.awaiting_answer is True
    assert "I am hungry." in result.teacher_response
    assert "What would you like to eat?" not in result.teacher_response


def test_default_manifest_roleplay_question_can_open_breakfast_branch():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P25", "student-1")
    roleplay_state = start.state.model_copy(
        update={
            "current_block_uid": "TB-G5S1U3-P25-D3",
            "awaiting_answer": True,
            "last_teacher_question": "如果你是顾客，你会怎么点餐？",
        }
    )

    result = runtime.handle_turn(roleplay_state, "Can I eat noodles for breakfast?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "branch"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P27-D4"]
    assert result.return_anchor == "What would you like to eat?"
    assert result.state.branch_active is True
    assert result.state.awaiting_answer is False
    assert result.state.current_block_uid == "TB-G5S1U3-P25-D3"

    follow_up = runtime.handle_turn(result.state, "okay")

    assert follow_up.turn_label == "social"
    assert follow_up.retrieval_mode == "none"
    assert follow_up.state.awaiting_answer is True
    assert "What would you like to eat?" in follow_up.teacher_response


def test_default_manifest_branch_prefers_nearby_teaching_page_over_later_review_page():
    runtime = LessonRuntime(
        PilotLessonCatalog(
            manifest_path=(
                Path(__file__).resolve().parents[3]
                / "app/knowledge/structured/general/general-manifest.json"
            )
        )
    )
    start = runtime.start_page("TB-G6S2U1-P2", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "How heavy is it?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "branch"
    assert result.retrieved_block_uids == ["TB-G6S2U1-P3-D1"]
    assert result.return_anchor == "How heavy is it?"


def test_default_manifest_lexicon_query_prefers_vocabulary_core_over_nearer_dialogue_core():
    runtime = LessonRuntime(
        PilotLessonCatalog(
            manifest_path=(
                Path(__file__).resolve().parents[3]
                / "app/knowledge/structured/general/general-manifest.json"
            )
        )
    )
    start = runtime.start_page("TB-G6S2U2-P13", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does stayed at home mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.retrieved_block_uids == [
        "TB-G6S2U2-P15-D1",
        "TB-G6S2U2-P14-D2",
    ]


def test_default_manifest_lexicon_query_prefers_vocabulary_core_for_same_phrase_family():
    runtime = LessonRuntime(
        PilotLessonCatalog(
            manifest_path=(
                Path(__file__).resolve().parents[3]
                / "app/knowledge/structured/general/general-manifest.json"
            )
        )
    )
    start = runtime.start_page("TB-G6S2U2-P13", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does had a cold mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.retrieved_block_uids == [
        "TB-G6S2U2-P17-D1",
        "TB-G6S2U2-P16-D2",
    ]


def test_default_manifest_lexicon_query_prefers_vocabulary_core_over_current_dialogue_hit():
    runtime = LessonRuntime(
        PilotLessonCatalog(
            manifest_path=(
                Path(__file__).resolve().parents[3]
                / "app/knowledge/structured/general/general-manifest.json"
            )
        )
    )
    start = runtime.start_page("TB-G6S2U2-P13", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does washed my clothes mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.retrieved_block_uids == [
        "TB-G6S2U2-P15-D1",
        "TB-G6S2U2-P14-D2",
    ]


def test_default_manifest_lexicon_query_prefers_vocabulary_core_over_current_dialogue_word_hit():
    runtime = LessonRuntime(
        PilotLessonCatalog(
            manifest_path=(
                Path(__file__).resolve().parents[3]
                / "app/knowledge/structured/general/general-manifest.json"
            )
        )
    )
    start = runtime.start_page("TB-G6S2U2-P14", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does watched mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.retrieved_block_uids == ["TB-G6S2U2-P15-D1"]


def test_default_manifest_lexicon_query_prefers_comparative_vocabulary_core_over_dialogue_hit():
    runtime = LessonRuntime(
        PilotLessonCatalog(
            manifest_path=(
                Path(__file__).resolve().parents[3]
                / "app/knowledge/structured/general/general-manifest.json"
            )
        )
    )
    start = runtime.start_page("TB-G6S2U1-P6", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does heavier mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.retrieved_block_uids == [
        "TB-G6S2U1-P7-D1",
        "TB-G6S2U1-P10-D2",
    ]


def test_default_manifest_answer_turn_knowledge_query_is_not_swallowed_by_matching_token():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P26", "student-1")
    advanced = runtime.handle_turn(start.state, "cow uses the cow sound")

    result = runtime.handle_turn(advanced.state, "What does snow mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode in {"block", "page", "unit"}
    assert result.state.awaiting_answer is True
    assert result.state.current_block_uid == "TB-G5S1U3-P26-D2"


def test_default_manifest_phonics_help_prefers_probe_word_over_explanatory_sentence():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P26", "student-1")

    result = runtime.handle_turn(start.state, "help")

    assert result.turn_label == "ask_help"
    assert "cow" in result.teacher_response
    assert "cow uses the cow sound" not in result.teacher_response


def test_default_manifest_phonics_hint_prefers_probe_word_over_explanatory_sentence():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P26", "student-1")

    result = runtime.handle_turn(start.state, "banana")

    assert result.turn_label == "answer_question"
    assert result.teaching_action == "hint"
    assert "cow" in result.teacher_response
    assert "cow uses the cow sound" not in result.teacher_response


def test_live_planner_keeps_deterministic_branch_selection(tmp_path):
    runtime = _make_runtime_with_live_prompts(
        tmp_path,
        planner_payload={
            "ask_knowledge": {
                "teaching_action": "explain",
                "retrieval_mode": "block",
                "response_focus": "Stay narrow even when the fallback wants a branch.",
            }
        },
        responder_text="我们先短讲一下，再回到主线。",
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "Can I eat noodles for breakfast?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "branch"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P26-D1"]


def test_live_planner_keeps_deterministic_unit_selection_for_lexicon_query(tmp_path):
    runtime = _make_runtime_with_live_prompts(
        tmp_path,
        planner_payload={
            "ask_knowledge": {
                "teaching_action": "explain",
                "retrieval_mode": "block",
                "response_focus": "Stay narrow even when the fallback wants a unit lookup.",
            }
        },
        responder_text="我们先解释词义，再回到主线。",
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does salad mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.retrieved_block_uids[0] == "TB-G5S1U3-P25-D1"


def test_live_route_classifier_cannot_downgrade_explicit_lexicon_query_to_help(tmp_path):
    runtime = _make_runtime_with_live_prompts(
        tmp_path,
        planner_payload={
            "route_classifier": {
                "turn_label": "ask_help",
                "reason": "invalid downgrade on purpose",
            },
            "ask_knowledge": {
                "teaching_action": "explain",
                "retrieval_mode": "block",
                "response_focus": "Explain the vocabulary item clearly.",
            },
        },
        responder_text="我们先解释这个词，再回到主线。",
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does salad mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.retrieved_block_uids[0] == "TB-G5S1U3-P25-D1"


def test_runtime_can_use_optional_qdrant_retriever(tmp_path):
    qdrant_client = importlib.import_module("qdrant_client")
    manifest_path = _write_test_pilot(tmp_path)
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    store = QdrantTeachingStore(
        client=qdrant_client.QdrantClient(location=":memory:"),
        collection_name="lesson_runtime_vectors",
    )
    retriever = QdrantLessonRetriever(
        catalog=catalog,
        store=store,
        embed_texts=_fake_embed_texts,
    )
    runtime = LessonRuntime(catalog, retriever=retriever)
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Payload indexes have no effect in the local Qdrant.*",
        )

        page_result = runtime.handle_turn(
            start.state.model_copy(update={"awaiting_answer": False}),
            "How do I do the role play?",
        )
        unit_result = runtime.handle_turn(
            start.state.model_copy(update={"awaiting_answer": False}),
            "What does salad mean?",
        )
        branch_result = runtime.handle_turn(
            start.state.model_copy(update={"awaiting_answer": False}),
            "Can I eat noodles for breakfast?",
        )

    assert page_result.retrieval_mode == "page"
    assert page_result.retrieved_block_uids[0] == "TB-G5S1U3-P24-D2"
    assert unit_result.retrieval_mode == "unit"
    assert unit_result.retrieved_block_uids[0] == "TB-G5S1U3-P25-D1"
    assert branch_result.retrieval_mode == "branch"
    assert branch_result.retrieved_block_uids[0] == "TB-G5S1U3-P26-D1"


def test_runtime_can_write_lesson_trace_into_simplemem(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    db_path = tmp_path / "simplemem-cross.db"
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        memory_writer=SimpleMemSQLiteLessonMemoryWriter(
            db_path=db_path,
            project="peptutor-lesson",
        ),
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    wrong = runtime.handle_turn(start.state, "want tea")
    help_state = wrong.state.model_copy(update={"awaiting_answer": False})
    help_result = runtime.handle_turn(help_state, "again slowly")
    correct_state = help_result.state.model_copy(update={"awaiting_answer": True})
    correct = runtime.handle_turn(correct_state, "I'd like some water.")
    switched = runtime.handle_turn(
        correct.state,
        "next page",
        requested_page_uid="TB-G5S1U3-P25",
    )

    conn = sqlite3.connect(db_path)
    try:
        status_row = conn.execute(
            "SELECT status FROM sessions WHERE tenant_id = ? ORDER BY id ASC LIMIT 1",
            ("student-1",),
        ).fetchone()
        observation_titles = [
            row[0]
            for row in conn.execute(
                "SELECT title FROM observations ORDER BY obs_id ASC"
            ).fetchall()
        ]
        summary_row = conn.execute(
            "SELECT learned, completed, next_steps FROM session_summaries LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    assert start.state.simplemem_content_session_id is not None
    assert start.state.simplemem_memory_session_id is not None
    assert switched.state.simplemem_content_session_id != start.state.simplemem_content_session_id
    assert status_row == ("completed",)
    assert observation_titles == [
        "Learner struggles to answer with 'I'd like some water.' independently.",
        "Learner prefers slower split practice when stuck.",
        "Learner can now answer 'I'd like some water.' correctly.",
    ]
    assert summary_row == (
        'Learner still needs the target sentence "I\'d like some water."',
        'Learner can now answer "I\'d like some water." correctly',
        "Learner prefers slower split practice when stuck.",
    )
