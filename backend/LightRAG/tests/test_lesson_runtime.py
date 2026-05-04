import json
import importlib
import re
import sqlite3
import sys
import warnings
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

LIGHTRAG_ROOT = Path(__file__).resolve().parents[1]
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
AnswerTurnPolicyOutput = importlib.import_module(
    "lightrag.orchestrator.lesson_runtime"
).AnswerTurnPolicyOutput
AnswerTurnPolicyStatePatch = importlib.import_module(
    "lightrag.orchestrator.lesson_runtime"
).AnswerTurnPolicyStatePatch
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
TeachingMovePlanner = importlib.import_module(
    "lightrag.orchestrator.teaching_move_planner"
).TeachingMovePlanner
responder_module = importlib.import_module("lightrag.pedagogy.responder")
LessonResponder = responder_module.LessonResponder
LessonResponderTurnResult = responder_module.LessonResponderTurnResult
render_classification_short_answer_reply = (
    responder_module.render_classification_short_answer_reply
)
redirect_policy_module = importlib.import_module("lightrag.pedagogy.redirect_reply_policy")
maybe_render_redirect_reply = redirect_policy_module.maybe_render_redirect_reply
classification_policy_module = importlib.import_module(
    "lightrag.pedagogy.classification_task_policy"
)
classify_short_answer_for_task = (
    classification_policy_module.classify_short_answer_for_task
)
system_contract_module = importlib.import_module("lightrag.pedagogy.system_contract")
LESSON_AUTHORITY_ORDER = system_contract_module.LESSON_AUTHORITY_ORDER
BANNED_TEACHER_PHRASES = system_contract_module.BANNED_TEACHER_PHRASES
lesson_policy_prompts_module = importlib.import_module(
    "lightrag.orchestrator.lesson_policy_prompts"
)
ANSWER_TURN_POLICY_RUBRIC_V1 = (
    lesson_policy_prompts_module.ANSWER_TURN_POLICY_RUBRIC_V1
)
REPLY_QUALITY_REVISION_RUBRIC_V1 = (
    lesson_policy_prompts_module.REPLY_QUALITY_REVISION_RUBRIC_V1
)
lesson_persona_module = importlib.import_module("lightrag.orchestrator.lesson_persona")
MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_BYTES = (
    lesson_persona_module.MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_BYTES
)
MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1 = (
    lesson_persona_module.MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1
)
MILI_PERSONA_CAPSULE_V1 = lesson_persona_module.MILI_PERSONA_CAPSULE_V1
MILI_PERSONA_CAPSULE_VERSION = lesson_persona_module.MILI_PERSONA_CAPSULE_VERSION
MILI_PERSONA_SOUL_PATH = lesson_persona_module.MILI_PERSONA_SOUL_PATH
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


def _general_manifest_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "app/knowledge/structured/general/general-manifest.json"
    )


def _general_overlay_manifest_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "app/knowledge/structured/general/general-with-pilot-overrides-manifest.json"
    )


def _assert_priority_edges_follow_classroom_order(catalog) -> None:
    for page in catalog.pages.values():
        priority_blocks = list(page.priority_blocks)
        assert len(priority_blocks) == len(set(priority_blocks)), page.page_uid
        for index, block_uid in enumerate(priority_blocks):
            block = catalog.get_block(block_uid)
            assert block.page_uid == page.page_uid, block_uid
            assert block.next_block_uids == priority_blocks[index + 1 :], block_uid


def _compact_json_bytes(value) -> int:
    return len(
        json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    )


def _legacy_answer_policy_runtime_state_bytes(frame: dict[str, object]) -> int:
    return sum(
        _compact_json_bytes(frame[key])
        for key in (
            "teacherasked",
            "taskboundary",
            "recentdialogue",
            "allowedstatewrites",
            "learnerinputmatches",
        )
        if key in frame
    )


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


def _write_answer_policy_progression_pilot(tmp_path):
    pilot_file = tmp_path / "answer-policy-progression.json"
    manifest_file = tmp_path / "manifest.json"

    pilot_payload = {
        "pilot_id": "answer-policy-progression-test",
        "scope": {"grade": "G5", "semester": "S1", "unit": "U3", "pages": [24]},
        "page_lessons": [
            {
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "page_intro_cn": "这一页练习点餐里的吃和喝。",
                "entry_probe_questions": ["D2_QUESTION_SENTINEL"],
                "priority_blocks": [
                    "TB-G5S1U3-P24-D2",
                    "TB-G5S1U3-P24-D3",
                    "TB-G5S1U3-P24-D4",
                    "TB-G5S1U3-P24-D1",
                ],
            },
        ],
        "teaching_blocks": [
            {
                "block_uid": "TB-G5S1U3-P24-D2",
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_type": "dialogue_core",
                "teaching_goal": "Answer a drink request with a full sentence.",
                "teaching_summary": "The learner answers a drink request.",
                "focus_vocabulary": ["water", "tea"],
                "core_patterns": ["I'd like some water."],
                "allowed_answer_scope": ["I'd like some water."],
                "entry_probe_questions": ["D2_QUESTION_SENTINEL"],
                "repair_modes": ["repeat"],
                "next_block_uids": ["TB-G5S1U3-P24-D3"],
                "learning_target_uids": ["LT-D2"],
                "branchable_topics": ["drink"],
                "return_anchors": ["I'd like some water."],
            },
            {
                "block_uid": "TB-G5S1U3-P24-D3",
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_type": "dialogue_practice",
                "teaching_goal": "Keep practicing the current drink task.",
                "teaching_summary": "The learner stays on the current task after a related wrong answer.",
                "focus_vocabulary": ["water", "tea"],
                "core_patterns": ["I'd like water.", "I'd like some tea."],
                "allowed_answer_scope": ["I'd like water.", "I'd like some tea."],
                "entry_probe_questions": ["D3_QUESTION_SENTINEL"],
                "repair_modes": ["repeat"],
                "next_block_uids": ["TB-G5S1U3-P24-D4", "TB-G5S1U3-P24-D1"],
                "learning_target_uids": ["LT-D3"],
                "branchable_topics": ["drink"],
                "return_anchors": ["I'd like water."],
            },
            {
                "block_uid": "TB-G5S1U3-P24-D4",
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_type": "dialogue_practice",
                "teaching_goal": "Practice the matching food task.",
                "teaching_summary": "The learner answers a food request after the drink task.",
                "focus_vocabulary": ["chicken and bread", "rice and vegetables"],
                "core_patterns": ["What would you like to eat?", "I'd like ..."],
                "allowed_answer_scope": [
                    "I'd like chicken and bread.",
                    "I'd like rice and vegetables.",
                ],
                "entry_probe_questions": ["D4_QUESTION_SENTINEL"],
                "repair_modes": ["repeat"],
                "next_block_uids": [],
                "learning_target_uids": ["LT-D4"],
                "branchable_topics": ["food"],
                "return_anchors": ["I'd like chicken and bread."],
            },
            {
                "block_uid": "TB-G5S1U3-P24-D1",
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_type": "listening_probe",
                "teaching_goal": "A previous listening block that must not be reset to.",
                "teaching_summary": "Regression guard for avoiding old reset behavior.",
                "focus_vocabulary": ["bread", "noodles"],
                "core_patterns": ["She would like some ..."],
                "allowed_answer_scope": ["bread and noodles"],
                "entry_probe_questions": ["D1_QUESTION_SENTINEL"],
                "repair_modes": ["repeat"],
                "next_block_uids": [],
                "learning_target_uids": ["LT-D1"],
                "branchable_topics": ["listening"],
                "return_anchors": ["bread and noodles"],
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


def _write_try_talk_module_pilot(tmp_path):
    pilot_file = tmp_path / "try-talk-module.json"
    manifest_file = tmp_path / "manifest.json"

    pilot_payload = {
        "pilot_id": "try-talk-module-test",
        "scope": {"grade": "G5", "semester": "S1", "unit": "U1", "pages": [4]},
        "page_lessons": [
            {
                "page_uid": "TB-G5S1U1-P4",
                "page_type": "dialogue",
                "page_intro_cn": "Theme: places in school. 听一段对话，再练核心问路句。",
                "entry_probe_questions": ["Can you say: Where is the museum shop?"],
                "priority_blocks": [
                    "TB-G5S1U1-P4-D1",
                    "TB-G5S1U1-P4-D2",
                    "TB-G5S1U1-P4-D3",
                ],
            },
        ],
        "teaching_blocks": [
            {
                "block_uid": "TB-G5S1U1-P4-D1",
                "page_uid": "TB-G5S1U1-P4",
                "page_type": "dialogue",
                "block_type": "listening_probe",
                "teaching_goal": "Catch the place from the listening task.",
                "teaching_summary": (
                    "先听一段对话，抓住人物要去哪里。 Key patterns: Listen and choose."
                ),
                "focus_vocabulary": ["museum", "shop"],
                "core_patterns": ["Listen and choose."],
                "allowed_answer_scope": ["museum shop"],
                "entry_probe_questions": ["Can you say: Listen and choose."],
                "repair_modes": ["repeat"],
                "next_block_uids": ["TB-G5S1U1-P4-D2"],
                "learning_target_uids": ["LT-try-D1"],
                "branchable_topics": ["Let's try"],
                "return_anchors": ["Listen and choose."],
            },
            {
                "block_uid": "TB-G5S1U1-P4-D2",
                "page_uid": "TB-G5S1U1-P4",
                "page_type": "dialogue",
                "block_type": "dialogue_core",
                "teaching_goal": "Understand the main dialogue question.",
                "teaching_summary": (
                    "看 Mike 和 Wu Binbin 的问路对话，抓住核心句。 "
                    "Key patterns: Where is the museum shop?"
                ),
                "focus_vocabulary": ["museum", "shop"],
                "core_patterns": ["Where is the museum shop?"],
                "allowed_answer_scope": ["Where is the museum shop?"],
                "entry_probe_questions": ["Can you say: Where is the museum shop?"],
                "repair_modes": ["repeat"],
                "next_block_uids": ["TB-G5S1U1-P4-D3"],
                "learning_target_uids": ["LT-talk-D2"],
                "branchable_topics": ["Let's talk"],
                "return_anchors": ["Where is the museum shop?"],
            },
            {
                "block_uid": "TB-G5S1U1-P4-D3",
                "page_uid": "TB-G5S1U1-P4",
                "page_type": "dialogue",
                "block_type": "dialogue_practice",
                "teaching_goal": "Practice the place question in a short exchange.",
                "teaching_summary": "跟读并替换地点，练一小段问路对话。",
                "focus_vocabulary": ["museum", "shop"],
                "core_patterns": ["Where is ...?"],
                "allowed_answer_scope": ["Where is the museum shop?"],
                "entry_probe_questions": ["Can you ask one place question?"],
                "repair_modes": ["repeat"],
                "next_block_uids": [],
                "learning_target_uids": ["LT-talk-D3"],
                "branchable_topics": [],
                "return_anchors": ["Where is the museum shop?"],
            },
        ],
    }
    manifest_payload = {"files": [str(pilot_file)]}

    pilot_file.write_text(json.dumps(pilot_payload), encoding="utf-8")
    manifest_file.write_text(json.dumps(manifest_payload), encoding="utf-8")
    return manifest_file


def _write_source_split_page_pilot(tmp_path):
    pilot_file = tmp_path / "source-split-page.json"
    manifest_file = tmp_path / "manifest.json"

    pilot_payload = {
        "pilot_id": "source-split-page-test",
        "scope": {"grade": "G5", "semester": "S1", "unit": "U3", "pages": [44]},
        "page_lessons": [
            {
                "page_uid": "TB-G5S1U3-P44",
                "page_type": "dialogue",
                "page_intro_cn": "这一页练习在餐厅里说想吃什么、想喝什么。",
                "entry_probe_questions": ["Can you say: I am hungry?"],
                "priority_blocks": [
                    "TB-G5S1U3-P44-D1",
                    "TB-G5S1U3-P44-D2",
                    "TB-G5S1U3-P44-D3",
                ],
            },
        ],
        "teaching_blocks": [
            {
                "block_uid": "TB-G5S1U3-P44-D1",
                "page_uid": "TB-G5S1U3-P44",
                "page_type": "dialogue",
                "block_type": "dialogue_core",
                "teaching_goal": "Warm up the restaurant scene.",
                "teaching_summary": "先理解 hungry 和 thirsty，再看吃什么、喝什么的核心问句。",
                "focus_vocabulary": ["hungry", "thirsty", "water"],
                "core_patterns": ["I'd like some water."],
                "allowed_answer_scope": ["I am hungry."],
                "entry_probe_questions": ["Can you say: I am hungry?"],
                "repair_modes": ["repeat"],
                "next_block_uids": ["TB-G5S1U3-P44-D2"],
                "learning_target_uids": ["LT-source-D1"],
                "branchable_topics": ["restaurant", "food", "drink", "hungry"],
                "return_anchors": ["I am hungry."],
                "source_refs": ["TB-G5S1U3-P44-D1"],
            },
            {
                "block_uid": "TB-G5S1U3-P44-D2",
                "page_uid": "TB-G5S1U3-P44",
                "page_type": "dialogue",
                "block_type": "dialogue_practice",
                "teaching_goal": "Practice the drink choice.",
                "teaching_summary": (
                    "用饮料小词库练 What would you like to drink? 和 I'd like ..."
                ),
                "focus_vocabulary": ["water", "tea"],
                "core_patterns": ["What would you like to drink?", "I'd like ..."],
                "allowed_answer_scope": ["I'd like some water.", "I'd like some tea."],
                "entry_probe_questions": ["What would you like to drink?"],
                "repair_modes": ["repeat"],
                "next_block_uids": ["TB-G5S1U3-P44-D3"],
                "learning_target_uids": ["LT-source-D2"],
                "branchable_topics": ["restaurant", "drink choice"],
                "return_anchors": ["I'd like some water."],
                "source_refs": ["TB-G5S1U3-P44-D2"],
            },
            {
                "block_uid": "TB-G5S1U3-P44-D3",
                "page_uid": "TB-G5S1U3-P44",
                "page_type": "dialogue",
                "block_type": "dialogue_practice",
                "teaching_goal": "Practice the food choice.",
                "teaching_summary": (
                    "用食物小词库练 What would you like to eat? 和 I'd like ..."
                ),
                "focus_vocabulary": ["bread", "rice"],
                "core_patterns": ["What would you like to eat?", "I'd like ..."],
                "allowed_answer_scope": ["I'd like bread.", "I'd like rice."],
                "entry_probe_questions": ["What would you like to eat?"],
                "repair_modes": ["repeat"],
                "next_block_uids": [],
                "learning_target_uids": ["LT-source-D3"],
                "branchable_topics": ["restaurant", "food choice"],
                "return_anchors": ["I'd like bread."],
                "source_refs": ["TB-G5S1U3-P44-D3"],
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


def test_answer_turn_policy_repairs_related_wrong_answer_in_place(tmp_path, monkeypatch):
    manifest_path = _write_test_pilot(tmp_path)
    captured_prompts: list[dict[str, object]] = []

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (history_messages, kwargs)
        payload = json.loads(prompt)
        captured_prompts.append(payload)
        if payload["turn_kind"] == "readiness_judge":
            return json.dumps(
                {
                    "readiness": "not_ready",
                    "can_advance": False,
                    "signals": ["needs_current_answer"],
                    "reason": "The learner has not produced the expected answer.",
                    "allowed_next_step": "Stay on the current step.",
                    "blocked_moves": ["advance_block"],
                }
            )
        return json.dumps(
            {
                "teacherreply": "ANSWER_TURN_POLICY_REPLY_SENTINEL",
                "statepatch": {
                    "currentblockuid": "TB-G5S1U3-P24-D1",
                    "awaitinganswer": True,
                    "lastteacherquestion": "What would you like to drink?",
                },
            }
        )

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge unused by answer-turn policy test",
        ),
    )

    def _fail_if_interrupt_called(**kwargs):
        _ = kwargs
        raise AssertionError("answer-turn policy path must not pre-interrupt")

    def _fail_if_legacy_answer_route_called(*args, **kwargs):
        _ = (args, kwargs)
        raise AssertionError("answer-turn policy success must bypass legacy answer route")

    runtime._should_interrupt_answer_turn = _fail_if_interrupt_called
    runtime._judge_answer_readiness = _fail_if_legacy_answer_route_called
    runtime._handle_success = _fail_if_legacy_answer_route_called
    runtime._handle_readiness_stay = _fail_if_legacy_answer_route_called
    runtime._handle_difficulty = _fail_if_legacy_answer_route_called

    info_messages: list[str] = []

    def _capture_info(message, *args):
        info_messages.append(message % args)

    lesson_runtime_module = sys.modules[LessonRuntime.__module__]
    monkeypatch.setattr(lesson_runtime_module.logger, "info", _capture_info)

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "pizza")

    assert result.evaluation == "unclear"
    assert result.teaching_action == "hint"
    assert result.block_uid == "TB-G5S1U3-P24-D1"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D1"
    assert result.state.awaiting_answer is True
    assert result.state.same_goal_attempt_count == 1
    assert result.teacher_response == "ANSWER_TURN_POLICY_REPLY_SENTINEL"
    assert [prompt["turn_kind"] for prompt in captured_prompts] == [
        "answer_turn_policy",
    ]
    prompt_payload = captured_prompts[-1]
    assert prompt_payload["persona_capsule"] == (
        MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1
    )
    prompt_text = json.dumps(prompt_payload, ensure_ascii=False)
    assert "# Teacher Soul" not in prompt_text
    assert "Long-form Identity" not in prompt_text
    assert "Sample Lines" not in prompt_text
    assert "海鲜螺蛳粉" not in prompt_text
    assert "课堂手账" not in prompt_text
    assert "人格只影响语气和脚手架大小" in prompt_text
    assert captured_prompts[-1]["frame"]["studentsaid"] == "pizza"
    assert "answercheck" not in captured_prompts[-1]["frame"]
    assert "ruleevaluation" not in captured_prompts[-1]["frame"]
    assert "suggestedreadiness" not in captured_prompts[-1]["frame"]
    assert "expectedanswers" not in captured_prompts[-1]["frame"]
    assert "acceptablecontent" not in captured_prompts[-1]["frame"]
    assert "teacherlastquestion" not in captured_prompts[-1]["frame"]
    assert "currentblocksource" not in captured_prompts[-1]["frame"]
    assert "nextblocksource" not in captured_prompts[-1]["frame"]
    assert "textbookexamples" not in captured_prompts[-1]["frame"]
    assert "assessment" not in captured_prompts[-1]["required_output_schema"]
    assert "decision" not in captured_prompts[-1]["required_output_schema"]
    assert "stayoncurrentblock" not in captured_prompts[-1]["required_output_schema"]
    assert "samescenerelatedterms" not in captured_prompts[-1]["frame"]
    current_task_facts = captured_prompts[-1]["frame"]["currenttaskfacts"]
    for forbidden_key in (
        "teacherlastquestion",
        "currentblocksource",
        "nextblocksource",
        "textbookexamples",
    ):
        assert forbidden_key not in current_task_facts
    assert current_task_facts["classroomexchange"] == {
        "teacherasked": "Can you answer: What would you like to drink?",
        "studentsaid": "pizza",
    }
    assert current_task_facts["textbooksource"]["current"]["patterns"] == [
        "What would you like to drink?",
        "I'd like some water.",
    ]
    assert current_task_facts["textbooksource"]["current"]["examples"] == [
        "I'd like some water.",
        "I'd like some juice.",
    ]
    lesson_context = captured_prompts[-1]["frame"]["lessoncontext"]
    assert lesson_context["pageuid"] == "TB-G5S1U3-P24"
    same_page_blocks = captured_prompts[-1]["frame"]["samepageblocks"]
    assert [block["blockuid"] for block in same_page_blocks] == [
        "TB-G5S1U3-P24-D1",
        "TB-G5S1U3-P24-D2",
    ]
    assert same_page_blocks[0]["textbooksource_ref"] == (
        "currenttaskfacts.textbooksource.current"
    )
    assert same_page_blocks[1]["textbooksource_ref"] == (
        "currenttaskfacts.textbooksource.next"
    )
    assert all("textbooksource" not in block for block in same_page_blocks)
    assert current_task_facts["textbooksource"]["current"]["vocabulary"] == [
        "water",
        "juice",
    ]
    assert "pizza" not in json.dumps(lesson_context, ensure_ascii=False).casefold()
    joined_info = "\n".join(info_messages)
    assert "policy_used=true legacy_branch_used=false" in joined_info
    assert "legacy_branch_used=true" not in joined_info


def test_answer_turn_policy_does_not_swallow_explicit_lexicon_question(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    support_retriever = SupportAssetRetriever(
        catalog,
        support_paths=[_write_test_support_assets(tmp_path)],
    )
    captured_prompts: list[dict[str, object]] = []

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (history_messages, kwargs)
        payload = json.loads(prompt)
        captured_prompts.append(payload)
        return json.dumps(
            {
                "teacherreply": "water 是水。我们回到刚才这个问题：What would you like to drink?",
                "statepatch": {
                    "currentblockuid": "TB-G5S1U3-P24-D2",
                    "awaitinganswer": False,
                    "lastteacherquestion": None,
                },
            }
        )

    runtime = LessonRuntime(
        catalog,
        support_retriever=support_retriever,
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge must not be reached",
        ),
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "What does salad mean?")

    assert captured_prompts == []
    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P25-D1"]
    assert result.support_entry_uids == ["LEX-G5S1U3-salad"]
    assert result.block_uid == "TB-G5S1U3-P24-D1"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D1"
    assert result.state.awaiting_answer is True
    assert result.state.last_teacher_question == (
        "Can you answer: What would you like to drink?"
    )


def test_answer_turn_policy_uses_non_json_teacher_reply_without_legacy_fallback(
    tmp_path,
):
    manifest_path = _write_test_pilot(tmp_path)
    captured_prompts: list[dict[str, object]] = []
    teacher_reply = "NON_JSON_POLICY_REPLY_SENTINEL"

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (history_messages, kwargs)
        payload = json.loads(prompt)
        captured_prompts.append(payload)
        return teacher_reply

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge must not be reached",
        ),
    )

    def _fail_if_interrupt_called(**kwargs):
        _ = kwargs
        raise AssertionError("answer-turn policy path must not pre-interrupt")

    runtime._should_interrupt_answer_turn = _fail_if_interrupt_called

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "pizza")

    assert result.teacher_response == teacher_reply
    assert result.teaching_action == "hint"
    assert result.block_uid == "TB-G5S1U3-P24-D1"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D1"
    assert result.state.awaiting_answer is True
    assert [prompt["turn_kind"] for prompt in captured_prompts] == [
        "answer_turn_policy",
    ]


def test_answer_turn_policy_revises_reply_quality_without_changing_decision(
    tmp_path,
    monkeypatch,
):
    manifest_path = _write_test_pilot(tmp_path)
    captured_prompts: list[dict[str, object]] = []
    bad_reply = "跟老師學：I'd like some. water."
    revised_reply = "跟老师说完整一点：I'd like some water."

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (history_messages, kwargs)
        payload = json.loads(prompt)
        captured_prompts.append(payload)
        if payload["turn_kind"] == "answer_turn_policy_reply_quality_revision":
            return revised_reply
        return json.dumps(
            {
                "teacherreply": bad_reply,
                "statepatch": {
                    "currentblockuid": "TB-G5S1U3-P24-D1",
                    "awaitinganswer": True,
                    "lastteacherquestion": "What would you like to drink?",
                },
            }
        )

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge must not be reached",
        ),
    )

    def _fail_if_interrupt_called(**kwargs):
        _ = kwargs
        raise AssertionError("answer-turn policy path must not pre-interrupt")

    runtime._should_interrupt_answer_turn = _fail_if_interrupt_called

    info_messages: list[str] = []

    def _capture_info(message, *args):
        info_messages.append(message % args)

    lesson_runtime_module = sys.modules[LessonRuntime.__module__]
    monkeypatch.setattr(lesson_runtime_module.logger, "info", _capture_info)

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "water")

    assert result.teacher_response == revised_reply
    assert result.teaching_action == "hint"
    assert result.block_uid == "TB-G5S1U3-P24-D1"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D1"
    assert result.state.last_teacher_question == "What would you like to drink?"
    assert [prompt["turn_kind"] for prompt in captured_prompts] == [
        "answer_turn_policy",
        "answer_turn_policy_reply_quality_revision",
    ]
    revision_prompt = captured_prompts[-1]
    assert revision_prompt["frame"]["originalteacherreply"] == bad_reply
    revision_text = json.dumps(revision_prompt, ensure_ascii=False)
    for forbidden in (
        "answercheck",
        "expectedanswers",
        "acceptablecontent",
        "avoidtext",
        "assessment",
        "decision",
        "stayoncurrentblock",
        "statepatch",
        "太好了",
        "非常好",
        "很好",
        "真棒",
        "很棒",
        "太棒",
        "完全正确",
        "下一页",
    ):
        assert forbidden not in revision_text
    joined_info = "\n".join(info_messages)
    assert "quality_revision=applied" in joined_info
    assert "teacher_response=" + revised_reply in joined_info


def test_answer_turn_policy_contextual_reply_review_keeps_llm_as_rewriter(
    tmp_path,
    monkeypatch,
):
    manifest_path = _write_test_pilot(tmp_path)
    captured_prompts: list[dict[str, object]] = []
    first_reply = "学生已经说了一句完整回答，我们继续：What would you like to drink?"
    revised_reply = (
        "你刚才已经把上一句说完整了。我们看下一个小问题："
        "What would you like to drink?"
    )

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (history_messages, kwargs)
        payload = json.loads(prompt)
        captured_prompts.append(payload)
        if payload["turn_kind"] == "answer_turn_policy_reply_quality_revision":
            return revised_reply
        return json.dumps(
            {
                "teacherreply": first_reply,
                "statepatch": {
                    "currentblockuid": "TB-G5S1U3-P24-D2",
                    "awaitinganswer": True,
                    "lastteacherquestion": "What would you like to drink?",
                },
            }
        )

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge must not be reached",
        ),
        policy_reply_review_enabled=True,
    )

    def _fail_if_interrupt_called(**kwargs):
        _ = kwargs
        raise AssertionError("answer-turn policy path must not pre-interrupt")

    runtime._should_interrupt_answer_turn = _fail_if_interrupt_called

    info_messages: list[str] = []

    def _capture_info(message, *args):
        info_messages.append(message % args)

    lesson_runtime_module = sys.modules[LessonRuntime.__module__]
    monkeypatch.setattr(lesson_runtime_module.logger, "info", _capture_info)

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "I'd like some water.")

    assert result.teacher_response == revised_reply
    assert result.teaching_action == "confirm"
    assert result.block_uid == "TB-G5S1U3-P24-D2"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D2"
    assert [prompt["turn_kind"] for prompt in captured_prompts] == [
        "answer_turn_policy",
        "answer_turn_policy_reply_quality_revision",
    ]
    revision_prompt = captured_prompts[-1]
    assert revision_prompt["frame"]["originalteacherreply"] == first_reply
    assert revision_prompt["frame"]["qualitynotes"] == []
    assert revision_prompt["frame"]["currentblock"] == {"blockuid": "TB-G5S1U3-P24-D1"}
    assert revision_prompt["frame"]["nextblock"] == {"blockuid": "TB-G5S1U3-P24-D2"}
    assert set(revision_prompt["frame"]["currenttaskfacts"]["textbooksource"]) == {
        "current",
    }
    assert set(revision_prompt["frame"]["taskboundary"]) == {
        "activequestionkind",
        "currentblockscope",
        "currentblockhasmultipletargets",
    }
    assert {
        block["blockuid"] for block in revision_prompt["frame"]["samepageblocks"]
    } >= {"TB-G5S1U3-P24-D1", "TB-G5S1U3-P24-D2"}
    assert all(
        "textbooksource" not in block
        for block in revision_prompt["frame"]["samepageblocks"]
    )
    revision_text = json.dumps(revision_prompt, ensure_ascii=False)
    for forbidden in (
        "answercheck",
        "expectedanswers",
        "acceptablecontent",
        "assessment",
        "decision",
        "stayoncurrentblock",
        "statepatch",
    ):
        assert forbidden not in revision_text
    joined_info = "\n".join(info_messages)
    assert "quality_revision=reviewed_applied" in joined_info
    assert "teacher_response=" + revised_reply in joined_info


def test_answer_turn_policy_reply_review_rejects_non_oral_meta_output(
    tmp_path,
    monkeypatch,
):
    manifest_path = _write_test_pilot(tmp_path)
    captured_prompts: list[dict[str, object]] = []
    first_reply = "你问 eat 的意思，对，它就是吃。现在先回答老师这个问题：What would you like to eat?"
    meta_reply = (
        "好的，根据您的要求，我对原始教师回复进行了改写。以下是修改后的版本：\n\n"
        "eat 是吃。你可以回答：I'd like some chicken."
    )

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (history_messages, kwargs)
        payload = json.loads(prompt)
        captured_prompts.append(payload)
        if payload["turn_kind"] == "answer_turn_policy_reply_quality_revision":
            return meta_reply
        return json.dumps(
            {
                "teacherreply": first_reply,
                "statepatch": {
                    "currentblockuid": "TB-G5S1U3-P24-D1",
                    "awaitinganswer": True,
                    "lastteacherquestion": "What would you like to eat?",
                },
            }
        )

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge must not be reached",
        ),
        policy_reply_review_enabled=True,
    )

    info_messages: list[str] = []

    def _capture_info(message, *args):
        info_messages.append(message % args)

    lesson_runtime_module = sys.modules[LessonRuntime.__module__]
    monkeypatch.setattr(lesson_runtime_module.logger, "info", _capture_info)

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "eat 是什么意思？")

    assert result.teacher_response == first_reply
    assert [prompt["turn_kind"] for prompt in captured_prompts] == [
        "answer_turn_policy",
        "answer_turn_policy_reply_quality_revision",
    ]
    assert "non_oral_revision_meta" in runtime._answer_turn_policy_reply_warnings(
        meta_reply
    )
    joined_info = "\n".join(info_messages)
    assert "quality_revision=unresolved" in joined_info
    assert "quality_issues_after=['non_oral_revision_meta']" in joined_info


def test_answer_turn_policy_reply_warnings_cover_quality_smells(tmp_path):
    runtime = _make_runtime(tmp_path)

    warnings = runtime._answer_turn_policy_reply_warnings(
        "好的，根据您的要求，我对原始教师回复进行了改写。\n"
        "很棒！跟老師學：I'd like some. water. 我们去下一页。"
    )

    assert "broken_english_phrase" in warnings
    assert "traditional_chinese" in warnings
    assert "same_page_mislabel" in warnings
    assert "non_oral_revision_meta" in warnings
    assert "generic_praise" in warnings


def test_answer_turn_policy_reply_warnings_cover_praise_variants(tmp_path):
    runtime = _make_runtime(tmp_path)

    for reply in (
        "非常准确，完全正确。我们进入下一步。",
        '你说了 "I\'d like some water."，非常正确！我们继续。',
        "你的句子结构完全正确。现在看下一句。",
        "好，这句说得对！I'd like some water.",
        "你问 snow 是什么意思，很好！snow 就是雪。",
        "你读得很准。再试一个完整句。",
    ):
        assert "generic_praise" in runtime._answer_turn_policy_reply_warnings(reply)


def test_answer_turn_policy_revises_generic_praise_without_changing_decision(
    tmp_path,
):
    manifest_path = _write_test_pilot(tmp_path)
    captured_prompts: list[dict[str, object]] = []
    first_reply = "很棒！我们进入下一步：Now say one full drink sentence."
    revised_reply = "你刚才把饮料句说出来了。下一步说完整点：Now say one full drink sentence."

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (history_messages, kwargs)
        payload = json.loads(prompt)
        captured_prompts.append(payload)
        if payload["turn_kind"] == "answer_turn_policy_reply_quality_revision":
            return revised_reply
        return json.dumps(
            {
                "teacherreply": first_reply,
                "statepatch": {
                    "currentblockuid": "TB-G5S1U3-P24-D2",
                    "awaitinganswer": True,
                    "lastteacherquestion": "Now say one full drink sentence.",
                },
            }
        )

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge must not be reached",
        ),
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "I'd like some water.")

    assert result.teacher_response == revised_reply
    assert result.teaching_action == "confirm"
    assert result.block_uid == "TB-G5S1U3-P24-D2"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D2"
    assert [prompt["turn_kind"] for prompt in captured_prompts] == [
        "answer_turn_policy",
        "answer_turn_policy_reply_quality_revision",
    ]
    revision_prompt = captured_prompts[-1]
    assert revision_prompt["frame"]["originalteacherreply"] == first_reply
    assert "空泛表扬" in revision_prompt["frame"]["qualitynotes"][0]


_SMOKE_BROKEN_MIXED_ENGLISH_RE = re.compile(
    r"\b(?:I'd like|What would|you can|please|turn left|go straight)\b[^.!?。！？]*[\u4e00-\u9fff]",
    re.I,
)


def _run_policy_reply_style_case(
    *,
    page_uid: str,
    block_uid: str,
    last_teacher_question: str,
    learner_input: str,
    raw_teacher_reply: str,
    revision_reply: str | None = None,
    policy_last_teacher_question: str | None = None,
    stable_variant_index: int | None = None,
):
    requested_last_teacher_question = (
        policy_last_teacher_question
        if policy_last_teacher_question is not None
        else last_teacher_question
    )

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (history_messages, kwargs)
        payload = json.loads(prompt)
        if payload["turn_kind"] == "answer_turn_policy_reply_quality_revision":
            return revision_reply or raw_teacher_reply
        return json.dumps(
            {
                "teacherreply": raw_teacher_reply,
                "statepatch": {
                    "currentblockuid": block_uid,
                    "awaitinganswer": True,
                    "lastteacherquestion": requested_last_teacher_question,
                },
            }
        )

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge must not be reached",
        ),
        debug_signals_enabled=True,
    )
    if stable_variant_index is not None:
        runtime._stable_variant_index = lambda *parts: stable_variant_index
    start = runtime.start_page(page_uid, "student-1")
    state = start.state.model_copy(deep=True)
    state.current_activity_type = "teaching"
    state.current_block_uid = block_uid
    state.awaiting_answer = True
    state.last_teacher_question = last_teacher_question

    return runtime.handle_turn(state, learner_input)


def test_answer_turn_policy_practice_prompt_uses_natural_first_variant():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))
    runtime._stable_variant_index = lambda *parts: 0

    intro, read_prompt = runtime._answer_turn_policy_practice_prompt_pair("clean")

    assert intro == "我们先说这个：clean."
    assert read_prompt == "你来读：clean."
    assert "现在这一步先练" not in intro
    assert "跟我读" not in read_prompt


def test_answer_turn_policy_practice_prompt_naturalizes_second_variant():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))
    runtime._stable_variant_index = lambda *parts: 1

    intro, read_prompt = runtime._answer_turn_policy_practice_prompt_pair("clean")

    assert intro == "我们先说这个：clean."
    assert read_prompt == "你来读：clean."
    assert "这一步先抓住" not in intro
    assert "你读这一句" not in read_prompt


def test_answer_turn_policy_target_phrase_reduces_probe_question_from_reply():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))
    policy = AnswerTurnPolicyOutput(
        teacherreply="老师问的是 Do you know the word favourite food，不是整句跟读。",
        statepatch=AnswerTurnPolicyStatePatch(
            currentblockuid="TB-G5S1U3-P22-D1",
            awaitinganswer=True,
        ),
    )

    target = runtime._answer_turn_policy_target_phrase(
        policy=policy,
        frame={"teacherasked": ""},
        teacher_reply=policy.teacherreply,
    )

    assert target == "What's your favourite food?"


def test_answer_turn_policy_does_not_use_repeat_after_me_as_target_anchor():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S2U1-P2",
        block_uid="TB-G5S2U1-P2-D1",
        last_teacher_question="Can you say: Repeat after me.",
        learner_input="I played football yesterday.",
        raw_teacher_reply=(
            "你刚才说的是 I played football yesterday，"
            "但这一步老师想让你 Repeat after me。"
        ),
    )

    assert "Repeat after me" not in result.teacher_response
    assert "get up" in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert "classroom_phrasing" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_repairs_can_you_try_target_phrase():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U1-P2",
        block_uid="TB-G6S2U1-P2-D1",
        last_teacher_question="Can you try: I'm 1.6 metres tall.",
        learner_input="taller",
        raw_teacher_reply="这一步先抓住 Can you try. 你来读：Can you try.",
        stable_variant_index=0,
    )

    assert "taller" in result.teacher_response
    assert "更高" in result.teacher_response
    assert "I'm 1.6 metres tall." in result.teacher_response
    assert "我身高 1.6 米。" in result.teacher_response
    assert "Can you try" not in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert "target_phrase_quality" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_repairs_generic_module_title_target_phrase():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S1U1-P4",
        block_uid="TB-G6S1U1-P4-D2",
        last_teacher_question="你想先学哪一块？可以说 Let's talk 或 Let's try。",
        learner_input="turn left",
        raw_teacher_reply="先回到 Let's talk。我们先说这个：Let's talk.",
        stable_variant_index=0,
    )

    assert "turn left" in result.teacher_response
    assert "左转" in result.teacher_response
    assert "Where is the museum shop?" in result.teacher_response
    assert "博物馆商店在哪里" in result.teacher_response
    assert "先回到课本目标" not in result.teacher_response
    assert "这一步先听清这个问题" not in result.teacher_response
    assert "把这句读出来" not in result.teacher_response
    assert "Let's talk" not in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "target_phrase_quality" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_repairs_suggestion_fragment_target_phrase():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S1U2-P19",
        block_uid="TB-G6S1U2-P19-D3",
        last_teacher_question="Do you know the word suggestion?",
        learner_input="water",
        raw_teacher_reply="先别急，我们先把这句开头带起来：suggestion.",
        stable_variant_index=0,
    )

    assert result.teacher_response == (
        "你刚才说的是 water.\n"
        "我们先说这个：What suggestions will you give to your friends? Make a poster.\n"
        "你来读：What suggestions will you give to your friends? Make a poster."
    )
    assert "带起来：suggestion" not in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "target_phrase_quality" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_repairs_robin_fragment_to_story_question():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S1U1-P9",
        block_uid="TB-G6S1U1-P9-D1",
        last_teacher_question="Robin 的新特点是什么？选 He can find food 还是 He can find the way？",
        learner_input="right",
        raw_teacher_reply="我们先说这个：Robin.",
        stable_variant_index=0,
    )

    assert result.teacher_response == (
        "你刚才说的是 right.\n"
        "我们先说这个：1. What is Robin's new feature? □ He can find food. "
        "□ He can find the way.\n"
        "你来读：1. What is Robin's new feature? □ He can find food. "
        "□ He can find the way."
    )
    assert "我们先说这个：Robin" not in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "target_phrase_quality" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_repairs_story_character_fragment_to_sentence():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S1U3-P31",
        block_uid="TB-G5S1U3-P31-D1",
        last_teacher_question="Say this: Zoom would like a salad.",
        learner_input="Zip",
        raw_teacher_reply="我们先说这个：Zoom.",
        stable_variant_index=0,
    )

    assert result.teacher_response == (
        "你说 Zip，我听到了。\n"
        "Zip 是故事里的角色。\n"
        "故事里老师问：What would Zoom like to eat?（Zoom 想吃什么？）\n"
        "你可以这样回答：Zoom would like ..."
    )
    assert "我们先说这个：Zoom." not in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "target_phrase_quality" in result.debug_signals.response_audit.repair_reason
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_repairs_incomplete_sentence_tail():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S2U1-P6",
        block_uid="TB-G5S2U1-P6-D1",
        last_teacher_question="Do you know the word clean?",
        learner_input="clean",
        raw_teacher_reply="我们先继续这一页，",
    )

    assert result.teacher_response == "我们先继续这一页。"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert "sentence_tail_repaired" in (
        result.debug_signals.response_audit.repair_reason
    )


def test_answer_turn_policy_redirect_reply_adds_short_scaffold_for_p22_water():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S1U3-P22",
        block_uid="TB-G5S1U3-P22-D1",
        last_teacher_question="What's your favourite food?",
        learner_input="water",
        raw_teacher_reply=(
            "你刚才说的是 water. 这一步先听清这个问题：What's your favourite food?"
        ),
    )

    assert "water" in result.teacher_response
    assert "水" in result.teacher_response
    assert "What's your favourite food?" in result.teacher_response
    assert "你最喜欢的食物是什么" in result.teacher_response
    assert "可以用这个句型回答：My favourite food is ..." in result.teacher_response
    assert "这页的问题是" in result.teacher_response
    assert "这页先回答这个问题" not in result.teacher_response
    assert "你刚才说的是 water. 这一步先听清" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G5S1U3-P22-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_does_not_bind_target_meaning_to_learner():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S1U1-P2",
        block_uid="TB-G6S1U1-P2-D1",
        last_teacher_question="The science museum is near the door.",
        learner_input="It's near the door.",
        raw_teacher_reply=(
            "你刚才说的是 It's near the door. 它的意思是“科学博物馆”。 "
            "先回到课本目标：The science museum is near the door. "
            "把这句读出来：The science museum is near the door."
        ),
    )

    assert "It's near the door" in result.teacher_response
    assert "It's near the door. 它的意思是“科学博物馆”" not in result.teacher_response
    assert "water 跟科学博物馆有关" not in result.teacher_response
    assert "The science museum is near the door." in result.teacher_response
    assert "科学博物馆在门附近" in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S1U1-P2-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_naturalizes_science_museum_wording():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S1U1-P2",
        block_uid="TB-G6S1U1-P2-D1",
        last_teacher_question="Where is the ...?",
        learner_input="water",
        raw_teacher_reply="你刚才说的是 water. 先听，再说：science museum.",
    )

    assert "water" in result.teacher_response
    assert "水" in result.teacher_response
    assert "我听到你说 water，是“水”。" in result.teacher_response
    assert "你说的是：water" not in result.teacher_response
    assert "science museum" in result.teacher_response
    assert "科学博物馆" in result.teacher_response
    assert "我们先说这个：science museum" not in result.teacher_response
    assert "你来读：science museum" not in result.teacher_response
    assert "先听，再说：science museum" not in result.teacher_response
    assert "It's near the door. 它的意思是“科学博物馆”" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S1U1-P2-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_does_not_show_empty_slot_question():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S1U1-P2",
        block_uid="TB-G6S1U1-P2-D1",
        last_teacher_question="Where is the ...?",
        learner_input="water",
        raw_teacher_reply="你刚才说的是 water. 你来读：Where is the ?",
    )

    assert "Where is the ?" not in result.teacher_response
    assert "It's near the library." in result.teacher_response
    assert "图书馆旁边" in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S1U1-P2-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_naturalizes_get_up_wording():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S2U1-P2",
        block_uid="TB-G5S2U1-P2-D1",
        last_teacher_question="Do you know the word get up?",
        learner_input="I played football yesterday.",
        raw_teacher_reply=(
            "你刚才说的是 I played football yesterday. "
            "这一步老师问的是 get up. 先听，再说：get up."
        ),
    )

    assert "get up" in result.teacher_response
    assert "起床" in result.teacher_response
    assert "When do you get up?" in result.teacher_response
    assert "I get up at ..." in result.teacher_response
    assert "这一步老师问的是 get up" not in result.teacher_response
    assert "先听，再说：get up" not in result.teacher_response
    assert "你刚才说的是" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G5S2U1-P2-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_strips_try_to_say_wrapper():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S2U1-P2",
        block_uid="TB-G5S2U1-P2-D1",
        last_teacher_question="Try to say: I often get up at 7 o'clock.",
        learner_input="water",
        raw_teacher_reply=(
            "你刚才说的是 water. 你来读：Try to say: I often get up at 7 o'clock."
        ),
    )

    assert "Try to say" not in result.teacher_response
    assert "I often get up at 7 o'clock." in result.teacher_response
    assert "我经常七点起床" in result.teacher_response
    assert result.state.current_block_uid == "TB-G5S2U1-P2-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_frames_favourite_food_probe():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S1U3-P22",
        block_uid="TB-G5S1U3-P22-D1",
        last_teacher_question="What's your favourite food?",
        learner_input="Yesterday I played football.",
        raw_teacher_reply=(
            "你说昨天踢足球了！不过刚才问的是“你最喜欢的食物是什么？”"
            "答案可以用“Salad.”或“Sandwich.”。试着用英语回答一下吧。"
        ),
    )

    assert "我听到你说 Yesterday I played football." in result.teacher_response
    assert "What's your favourite food?" in result.teacher_response
    assert "你最喜欢的食物是什么" in result.teacher_response
    assert "可以用这个句型回答：My favourite food is ..." in result.teacher_response
    assert "Salad." not in result.teacher_response
    assert "Sandwich." not in result.teacher_response
    assert "不过刚才问的是" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G5S1U3-P22-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_naturalizes_museum_shop_wording():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S1U1-P4",
        block_uid="TB-G6S1U1-P4-D2",
        last_teacher_question="Where is the museum shop?",
        learner_input="turn left",
        raw_teacher_reply=(
            "你刚才说的是 turn left. 先回到课本目标：It's near the door. "
            "把这句读出来：It's near the door."
        ),
    )

    assert "turn left" in result.teacher_response
    assert "左转" in result.teacher_response
    assert (
        "Where is the museum shop?（博物馆商店在哪里？）" in result.teacher_response
        or "It's near the door.（它在门旁边。）" in result.teacher_response
    )
    assert "先回到课本目标" not in result.teacher_response
    assert "把这句读出来" not in result.teacher_response
    assert "这一步先听清这个问题" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S1U1-P4-D2"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_replaces_follow_teacher_reading_wrapper():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S1U1-P4",
        block_uid="TB-G6S1U1-P4-D2",
        last_teacher_question="Where is the museum shop?",
        learner_input="I want to play basketball.",
        raw_teacher_reply=(
            "你说你想打篮球，那很好。现在跟着老师读：Where is the museum shop?"
        ),
    )

    assert "I want to play basketball." in result.teacher_response
    assert "Where is the museum shop?" in result.teacher_response
    assert "博物馆商店在哪里" in result.teacher_response
    assert "可以用这个句型回答：It's near ..." in result.teacher_response
    assert "那很好" not in result.teacher_response
    assert "跟着老师读" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S1U1-P4-D2"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_normalizes_declarative_target_question_mark():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U1-P2",
        block_uid="TB-G6S2U1-P2-D1",
        last_teacher_question="I'm 1.6 metres tall?",
        learner_input="taller",
        raw_teacher_reply=(
            "你刚才说的是 taller. 我们先说这个：I'm 1.6 metres tall?"
        ),
    )

    assert "I'm 1.6 metres tall." in result.teacher_response
    assert "I'm 1.6 metres tall?" not in result.teacher_response
    assert "我身高 1.6 米。" in result.teacher_response
    assert "我身高 1.6 米？" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2U1-P2-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_normalizes_orphan_quote_before_period():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U1-P2",
        block_uid="TB-G6S2U1-P2-D1",
        last_teacher_question="I'm 1.6 metres tall'.",
        learner_input="taller",
        raw_teacher_reply=(
            "你刚才说的是 taller. 先听，再说：I'm 1.6 metres tall'."
        ),
    )

    assert "I'm 1.6 metres tall'." not in result.teacher_response
    assert "I'm 1.6 metres tall." in result.teacher_response
    assert "我身高 1.6 米" in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2U1-P2-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_strips_follow_me_target_fragment():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U1-P2",
        block_uid="TB-G6S2U1-P2-D1",
        last_teacher_question="tall' with me",
        policy_last_teacher_question="tall' with me",
        learner_input="I want to play basketball.",
        raw_teacher_reply=(
            "你刚才说的是 I want to play basketball. "
            "我们先说这个：tall' with me. 你来读：tall' with me."
        ),
    )

    assert "tall' with me" not in result.teacher_response
    assert "I'm 1.6 metres tall." in result.teacher_response
    assert "我身高 1.6 米" in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2U1-P2-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_strips_interest_generic_praise_modifier():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U1-P2",
        block_uid="TB-G6S2U1-P2-D1",
        last_teacher_question="I'm 1.60 metres tall.",
        learner_input="I want to play basketball.",
        raw_teacher_reply=(
            "米粒老师听到你说想打篮球，很棒的兴趣！"
            "不过现在我们在说身高：I'm 1.60 metres tall. "
            "你能试试补全这个句子吗？"
        ),
    )

    assert "很棒" not in result.teacher_response
    assert "兴趣" not in result.teacher_response
    assert "I'm 1.60 metres tall." in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "generic_praise_stripped" in (
        result.debug_signals.response_audit.repair_reason
    )


def test_answer_turn_policy_strips_activity_generic_praise_suffix():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U1-P4",
        block_uid="TB-G6S2U1-P4-D2",
        last_teacher_question="How tall is it?",
        learner_input="I want to play basketball.",
        raw_teacher_reply=(
            "你说想打篮球，很棒的活动哦。\n"
            "我们先把这句话说好：How tall is it?"
        ),
    )

    assert "很棒" not in result.teacher_response
    assert "活动哦" not in result.teacher_response
    assert "How tall is it?" in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "generic_praise_stripped" in (
        result.debug_signals.response_audit.repair_reason
    )


def test_answer_turn_policy_redirect_reply_distinguishes_g6_height_questions():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U1-P4",
        block_uid="TB-G6S2U1-P4-D2",
        last_teacher_question="How tall is it?",
        learner_input="How tall are you?",
        raw_teacher_reply=(
            "你刚才说的是 How tall are you. 这一步先听清这个问题：How tall is it?"
        ),
    )

    assert "How tall are you?" in result.teacher_response
    assert "How tall is it?" in result.teacher_response
    assert "你有多高" in result.teacher_response
    assert "它有多高" in result.teacher_response
    assert "这页的问题是：How tall is it?" in result.teacher_response
    assert "可以用这个句型回答：It's ... metres tall." in result.teacher_response
    assert "这页的问题是：How tall are you?" not in result.teacher_response
    assert "你先回答这个问题" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2U1-P4-D2"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_repairs_surface_target_sentence_claim():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U1-P4",
        block_uid="TB-G6S2U1-P4-D2",
        last_teacher_question="How tall is it?",
        learner_input="How tall are you?",
        raw_teacher_reply=(
            "你提到了目标句“How tall are you?”，这句话就是今天要学的核心句型。"
            "那接下来你来回答我这个问句：I'm ____ metres tall。"
        ),
    )

    assert "How tall is it?" in result.teacher_response
    assert "它有多高" in result.teacher_response
    assert "可以用这个句型回答：It's ... metres tall." in result.teacher_response
    assert "这句话就是今天要学的核心句型" not in result.teacher_response
    assert "你提到了目标句" not in result.teacher_response
    assert "这页的问题是：How tall are you?" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2U1-P4-D2"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_target_source_lock_keeps_g6_direction_dialogue_target():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S1U1-P4",
        block_uid="TB-G6S1U1-P4-D2",
        last_teacher_question="Where is the museum shop?",
        policy_last_teacher_question="跟老师读：museum shop",
        learner_input="turn left",
        raw_teacher_reply=(
            "你刚才说的是 turn left. "
            "我们先说这个：museum shop. 你来读：museum shop."
        ),
    )

    assert result.state.last_teacher_question == "Where is the museum shop?"
    assert "Where is the museum shop?" in result.teacher_response
    assert "博物馆商店在哪里" in result.teacher_response
    assert "这页我们先看地点词：museum shop" not in result.teacher_response
    assert "你来读：museum shop" not in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "target_source_lock" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_target_source_lock_keeps_g6_dinosaur_height_target():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U1-P4",
        block_uid="TB-G6S2U1-P4-D2",
        last_teacher_question="How tall is it?",
        policy_last_teacher_question="Can you follow me and say: How tall are you?",
        learner_input="How tall are you?",
        raw_teacher_reply="先听，再说：How tall are you.",
    )

    assert result.state.last_teacher_question == "How tall is it?"
    assert "How tall is it?" in result.teacher_response
    assert "它有多高" in result.teacher_response
    assert "这页的问题是：How tall is it?" in result.teacher_response
    assert "这页的问题是：How tall are you?" not in result.teacher_response
    assert "Can you follow me and say" not in result.state.last_teacher_question
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "target_source_lock" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_target_source_lock_strips_instruction_wrappers():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))
    block = runtime.catalog.get_block("TB-G6S1U1-P4-D2")
    state = runtime.start_page("TB-G6S1U1-P4", "student-1").state.model_copy(
        deep=True
    )
    state.current_activity_type = "teaching"
    state.current_block_uid = "TB-G6S1U1-P4-D2"
    state.last_teacher_question = "Where is the museum shop?"
    state.awaiting_answer = True
    frame = {
        "teacherasked": "Where is the museum shop?",
        "currentblock": {"blockuid": "TB-G6S1U1-P4-D2"},
    }

    wrappers = (
        "Can you follow me and say: museum shop",
        "跟我读：science museum",
        "先听，再说：get up",
        "把这句读出来：It's near the door.",
        "Can you say that in English: \"I get up at 7 o'clock.\"",
    )
    for wrapper in wrappers:
        policy = AnswerTurnPolicyOutput(
            teacherreply=f"请回到这一页。{wrapper}",
            statepatch=AnswerTurnPolicyStatePatch(
                currentblockuid="TB-G6S1U1-P4-D2",
                awaitinganswer=True,
                lastteacherquestion=wrapper,
            ),
        )

        locked, status = runtime._maybe_lock_answer_turn_policy_target_source(
            policy=policy,
            state=state,
            block=block,
            frame=frame,
            learner_input="water",
            evaluation="incorrect",
        )

        assert status == "applied"
        assert locked.statepatch.lastteacherquestion == "Where is the museum shop?"
        assert locked.statepatch.lastteacherquestion != wrapper


def test_answer_turn_policy_redirect_reply_keeps_p24_drink_boundary_for_pizza():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S1U3-P24",
        block_uid="TB-G5S1U3-P24-D2",
        last_teacher_question="What would you like to drink?",
        learner_input="pizza",
        raw_teacher_reply=(
            "你说的是pizza，这是食物的名字。老师刚才问的是“喝什么”。"
            "请你跟我读：What would you like to drink?"
        ),
    )

    assert "pizza" in result.teacher_response
    assert "披萨" in result.teacher_response
    assert "What would you like to drink?" in result.teacher_response
    assert "你想喝什么" in result.teacher_response
    assert "你先回答想喝什么" in result.teacher_response
    assert "What would you like to eat" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D2"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_repairs_phonics_fragment_read_target():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S2U1-P6",
        block_uid="TB-G5S2U1-P6-D1",
        last_teacher_question="Can you say: Learn the consonant blend 'cl' as in 'clean'.",
        learner_input="I want to play basketball.",
        raw_teacher_reply="你刚才说的是 I want to play basketball. 你来读：cl' as in.",
    )

    assert "cl' as in" not in result.teacher_response
    assert "clean" in result.teacher_response
    assert "我听到你说 I want to play basketball." in result.teacher_response
    assert "你说的是：I want to play basketball" not in result.teacher_response
    assert "clean 里的 cl 要连起来读" in result.teacher_response
    assert "跟我读：clean" in result.teacher_response
    assert "Learn the consonant blend" not in result.teacher_response
    assert "Say after me" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G5S2U1-P6-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_repairs_phonics_learner_word_target_leak():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S2U1-P6",
        block_uid="TB-G5S2U1-P6-D1",
        last_teacher_question="Learn the consonant blend 'cl' as in 'clean'.",
        learner_input="please",
        raw_teacher_reply="我们先说这个：please.\n你来读：please.",
    )

    assert "我们先说这个：please" not in result.teacher_response
    assert "你来读：please" not in result.teacher_response
    assert "please" in result.teacher_response
    assert "clean 里的 cl 要连起来读" in result.teacher_response
    assert "跟我读：clean" in result.teacher_response
    assert "cl' as in" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G5S2U1-P6-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_redirect_reply_uses_story_answer_frame():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S1U3-P31",
        block_uid="TB-G5S1U3-P31-D1",
        last_teacher_question="What would Zoom like to eat?",
        learner_input="Zip",
        raw_teacher_reply=(
            "你刚说到了Zip，没错，Zip是故事里的角色。"
            "老师问的是“Zoom would like a salad.”，"
            "这句话本身就是一个完整的句子。"
            "你已经认识Zip了，现在来试试完整说出Zoom的那句话："
            "Zoom would like a salad."
        ),
    )

    assert result.teacher_response == (
        "你说 Zip，我听到了。\n"
        "Zip 是故事里的角色。\n"
        "故事里老师问：What would Zoom like to eat?（Zoom 想吃什么？）\n"
        "你可以这样回答：Zoom would like ..."
    )
    assert "Zoom would like a salad. 你能跟老师读一遍吗" not in result.teacher_response
    assert result.teacher_response.count("\n") == 3
    assert result.state.current_block_uid == "TB-G5S1U3-P31-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_repairs_p13_answer_scope_module_choice_boundary():
    raw_reply = (
        "你的回答“I stayed at home.”和对话里的句子很像。"
        "我们先选一块吧：你想先看第一块（对话）还是第二块（朋友圈图文）？"
    )
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U2-P13",
        block_uid="TB-G6S2U2-P13-D2",
        last_teacher_question="What did you do last weekend?",
        learner_input="I stayed at home.",
        raw_teacher_reply=raw_reply,
    )

    assert "What did you do last weekend?" in result.teacher_response
    assert "你上个周末做了什么" in result.teacher_response
    assert "I ... last weekend." in result.teacher_response
    assert "第一块" not in result.teacher_response
    assert "第二块" not in result.teacher_response
    assert "哪一块" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2U2-P13-D2"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "module_choice_boundary" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_repairs_module_choice_without_redirect_marker():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U2-P13",
        block_uid="TB-G6S2U2-P13-D2",
        last_teacher_question="What did you do last weekend?",
        learner_input="I stayed at home.",
        raw_teacher_reply=(
            "你说的“I stayed at home.”，这是一个完整的回答，说明你在家。"
            "你还没有告诉我，你想先学第一块（John和Mike的对话）"
            "还是第二块（John的社交媒体图文）？"
        ),
    )

    assert "What did you do last weekend?" in result.teacher_response
    assert "你上个周末做了什么" in result.teacher_response
    assert "I ... last weekend." in result.teacher_response
    assert "第一块" not in result.teacher_response
    assert "第二块" not in result.teacher_response
    assert "想先学" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2U2-P13-D2"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "module_choice_boundary" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_repairs_single_module_label_leak():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U2-P13",
        block_uid="TB-G6S2U2-P13-D2",
        last_teacher_question="What did you do last weekend?",
        learner_input="I want to play basketball.",
        raw_teacher_reply=(
            "好的，你说“I want to play basketball.”，这是在说你上周末做的事情吗？"
            "我们可以先一起看看第二块的内容，把核心句型读一读。"
        ),
    )

    assert "What did you do last weekend?" in result.teacher_response
    assert "你上个周末做了什么" in result.teacher_response
    assert "I ... last weekend." in result.teacher_response
    assert "第二块" not in result.teacher_response
    assert "模块" not in result.teacher_response
    assert "核心句型读一读" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2U2-P13-D2"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "module_choice_boundary" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_repairs_module_choice_after_target_source_lock():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U2-P13",
        block_uid="TB-G6S2U2-P13-D2",
        last_teacher_question="你想先学哪一块？可以说 第一块 或 第二块。",
        policy_last_teacher_question="What did you do last weekend?",
        learner_input="water",
        raw_teacher_reply=(
            "你说的是“water”，和老师问的“先学第一块还是第二块”没有直接关系。"
            "那我们再选一下：你想先学第二块（对话）还是第一块（看图）？"
        ),
    )

    assert "What did you do last weekend?" in result.teacher_response
    assert "你上个周末做了什么" in result.teacher_response
    assert "I ... last weekend." in result.teacher_response
    assert "哪一块" not in result.teacher_response
    assert "第一块" not in result.teacher_response
    assert "第二块" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2U2-P13-D2"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "module_choice_boundary" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_repairs_module_choice_reintroduced_by_revision():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U2-P13",
        block_uid="TB-G6S2U2-P13-D2",
        last_teacher_question="What did you do last weekend?",
        learner_input="water",
        raw_teacher_reply="water 很棒！先回到刚才的问题：What did you do last weekend?",
        revision_reply=(
            '你说 "water"，是想选第几块呢？'
            "第二块是对话核心句，第一块是图片场景活动。"
        ),
    )

    assert "What did you do last weekend?" in result.teacher_response
    assert "I ... last weekend." in result.teacher_response
    assert "第几块" not in result.teacher_response
    assert "第一块" not in result.teacher_response
    assert "第二块" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2U2-P13-D2"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert (
        "module_choice_boundary" in result.debug_signals.response_audit.repair_reason
        or "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason
    )


def test_answer_turn_policy_redirect_reply_handles_last_weekend_phrase_target():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U2-P13",
        block_uid="TB-G6S2U2-P13-D1",
        last_teacher_question="Last weekend",
        learner_input="I want to play basketball.",
        raw_teacher_reply=(
            "你刚才说的是 I want to play basketball. "
            "先回到课本目标：Last weekend. 把这句读出来：Last weekend."
        ),
    )

    assert "Last weekend" in result.teacher_response
    assert "上周末" in result.teacher_response
    assert "先回到课本目标" not in result.teacher_response
    assert "把这句读出来" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2U2-P13-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "redirect_reply_policy" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_module_choice_boundary_repair_is_not_p13_specific():
    raw_reply = (
        "你说 water 了。我们先选一块开始：第一块 或 第二块。"
        "你想先看哪一块？"
    )
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S1U3-P24",
        block_uid="TB-G5S1U3-P24-D1",
        last_teacher_question="What would you like to drink?",
        learner_input="water",
        raw_teacher_reply=raw_reply,
    )

    assert "What would you like to drink?" in result.teacher_response
    assert "你想喝什么" in result.teacher_response
    assert "第一块" not in result.teacher_response
    assert "第二块" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "module_choice_boundary" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_separates_p24_drink_reply_from_hungry_target():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S1U3-P24",
        block_uid="TB-G5S1U3-P24-D2",
        last_teacher_question="假设你饿了，你可以说：I am hungry.",
        learner_input="I'd like some water.",
        raw_teacher_reply=(
            "你说了“I'd like some water”，这是表达想喝东西的句子，"
            "但刚才我们练的是“I am hungry”（我饿了）。"
            "来，先跟我把“I am hungry”说熟练：I am hungry。"
        ),
    )

    assert "I'd like some water." in result.teacher_response
    assert "What would you like to drink?" in result.teacher_response
    assert "老师刚才" not in result.teacher_response
    assert "但刚才" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D4"
    assert not _SMOKE_BROKEN_MIXED_ENGLISH_RE.search(result.teacher_response)
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert "matched_input_pullback" in result.debug_signals.response_audit.repair_reason
    assert result.debug_signals.response_audit.fallback_used is False


def test_answer_turn_policy_repairs_p24_pullback_after_pacing_compaction():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S1U3-P24",
        block_uid="TB-G5S1U3-P24-D2",
        last_teacher_question="假设你饿了，你可以说：I am hungry.",
        learner_input="I'd like some water.",
        raw_teacher_reply=(
            "你说了 I'd like some water. 这个句子可以表达想喝水。"
            "现在我们看第一块，先理解 hungry，然后回答。"
            "I am hungry. What would you like to drink? "
            "What would you like to eat? 老师会带你继续练。"
        ),
    )

    assert "I'd like some water." in result.teacher_response
    assert "What would you like to drink?" in result.teacher_response
    assert "What would you like to eat" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D4"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "classroom_pacing" in result.debug_signals.response_audit.repair_reason
    assert "matched_input_pullback" in result.debug_signals.response_audit.repair_reason


def test_answer_turn_policy_keeps_task_instruction_full_without_read_drill():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2Recycle2-P49",
        block_uid="TB-G6S2Recycle2-P49-D1",
        last_teacher_question="Find one food word in the party picture.",
        learner_input="water",
        raw_teacher_reply=(
            "你说 water，water 是水，属于 drinks。"
            "这一块我们先找 food。你再看看图上 brown bread、cheese、cake，哪个是吃的？"
        ),
        revision_reply=(
            "你说 water，water 是水，属于 drinks。"
            "这一块我们先找 food。你再看看图上 brown bread、cheese、cake，哪个是吃的？"
        ),
    )

    assert result.teacher_response == "water 属于 drinks；这一步先找 food，比如 brown bread 或 cheese。"
    assert "Find one food word in the." not in result.teacher_response
    assert "跟我读" not in result.teacher_response
    assert "先听，再说" not in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert result.debug_signals.response_audit.route == "classification_short_answer_policy"
    assert result.debug_signals.response_audit.repair_reason == "classification_short_answer_policy"


def test_answer_turn_policy_separates_p6_please_from_clean_target():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S2U1-P6",
        block_uid="TB-G5S2U1-P6-D1",
        last_teacher_question="Do you know the word clean?",
        learner_input="please",
        raw_teacher_reply=(
            "你说的是“please”，老师问的是“clean”。"
            "“clean”开头是“cl”，跟我读：clean。"
        ),
    )

    assert "please." in result.teacher_response
    assert "clean." in result.teacher_response
    assert re.search(
        r"(跟我读|你来读|你读这一句|把这句读出来|先听，再说)：clean\.",
        result.teacher_response,
    )
    assert "现在这一步先练" not in result.teacher_response
    assert not _SMOKE_BROKEN_MIXED_ENGLISH_RE.search(result.teacher_response)
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert "classroom_phrasing" in result.debug_signals.response_audit.repair_reason
    assert result.debug_signals.response_audit.fallback_used is False


def test_answer_turn_policy_separates_g6_direction_from_museum_shop_target():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S1U1-P4",
        block_uid="TB-G6S1U1-P4-D2",
        last_teacher_question="Do you know the word museum shop?",
        learner_input="turn left",
        raw_teacher_reply=(
            "嗯，你刚才说的 turn left 是“左转”的意思，"
            "和老师问的 museum shop 不一样哦。"
            "老师问的是“你知道 museum shop 是什么意思吗？”"
            "——它的意思是“博物馆商店”。"
            "来，你现在试着用英语说一遍“博物馆商店”吧。"
        ),
    )

    assert "turn left" in result.teacher_response
    assert "左转" in result.teacher_response
    assert "museum shop" in result.teacher_response
    assert "博物馆商店" in result.teacher_response
    assert "你来读：museum shop" not in result.teacher_response
    assert "把这句读出来" not in result.teacher_response
    assert "先听，再说：museum shop" not in result.teacher_response
    assert "Where is the museum shop?" in result.teacher_response
    assert "It's near ..." in result.teacher_response
    assert not _SMOKE_BROKEN_MIXED_ENGLISH_RE.search(result.teacher_response)
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert "classroom_phrasing" in result.debug_signals.response_audit.repair_reason
    assert result.debug_signals.response_audit.fallback_used is False


def test_answer_turn_policy_pacing_removes_extra_height_example():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U1-P4",
        block_uid="TB-G6S2U1-P4-D2",
        last_teacher_question="How tall are you?",
        learner_input="How tall are you?",
        raw_teacher_reply=(
            "你说的是'How tall are you?'，这正是Let's talk里的重点问句。"
            "那我们就先来学Let's talk吧。你听老师问：How tall are you? "
            "你试着回答一下，比如'I'm 1.65 metres.'"
        ),
    )
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))

    assert "I'm 1.65 metres" not in result.teacher_response
    assert "How tall are you" in result.teacher_response
    assert not runtime._teacher_reply_looks_overloaded(
        result.teacher_response,
        turn_label="answer_question",
    )
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert result.debug_signals.response_audit.repair_reason == "classroom_pacing"
    assert result.debug_signals.response_audit.fallback_used is False


def test_answer_turn_policy_pacing_compacts_redirect_question_example():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))
    reply = (
        "你说的'I want to play basketball.'，老师问的是'What's your favourite food?'，"
        "这是两个不同的话题。我们先回到食物上：What's your favourite food? "
        "你可以用'My favourite food is...'来回答，比如'My favourite food is pizza.'"
    )

    repaired = runtime._repair_answer_turn_policy_reply_pacing(
        teacher_reply=reply,
        learner_input="I want to play basketball.",
    )

    assert "I want to play basketball." in repaired
    assert "What's your favourite food?" in repaired
    assert "My favourite food is ..." in repaired
    assert "pizza" not in repaired
    assert not runtime._teacher_reply_looks_overloaded(
        repaired,
        turn_label="answer_question",
    )


def test_answer_turn_policy_pacing_compacts_near_next_to_redirect():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))
    reply = (
        "哦，你刚才说的是 I want to play basketball。"
        "这和老师问的 Where is the museum shop? 不是同一个内容呢。"
        "我们一起回到这个问题：Where is the museum shop? "
        "你试着回答一下好吗？可以用 It's near... 或 It's next to... 的句式。"
    )

    repaired = runtime._repair_answer_turn_policy_reply_pacing(
        teacher_reply=reply,
        learner_input="I want to play basketball.",
    )

    assert "I want to play basketball." in repaired
    assert "Where is the museum shop?" in repaired
    assert "It's near ..." in repaired
    assert "It's next to" not in repaired
    assert not runtime._teacher_reply_looks_overloaded(
        repaired,
        turn_label="answer_question",
    )


def test_answer_turn_policy_repairs_revised_generic_praise_with_mixed_phrasing():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U2-P16",
        block_uid="TB-G6S2U2-P16-D2",
        last_teacher_question="Can you repeat: film magazine.",
        learner_input="magazine",
        raw_teacher_reply=(
            "你说了magazine，很棒！电影杂志就是film magazine。跟我读：film magazine。"
        ),
        revision_reply=(
            '你说出了"magazine"这个词，跟老师刚才问的"film magazine"有关。'
            '电影杂志就叫"film magazine"。跟我读：film magazine。'
        ),
    )

    assert "很棒" not in result.teacher_response
    assert "magazine." in result.teacher_response
    assert "film magazine." in result.teacher_response
    assert re.search(
        r"(跟我读|你来读|你读这一句|把这句读出来|先听，再说)：film magazine\.",
        result.teacher_response,
    )
    assert not _SMOKE_BROKEN_MIXED_ENGLISH_RE.search(result.teacher_response)
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert "classroom_phrasing" in result.debug_signals.response_audit.repair_reason
    assert result.debug_signals.response_audit.fallback_used is False


def test_answer_turn_policy_strips_generic_praise_after_unresolved_revision():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S2U2-P19",
        block_uid="TB-G5S2U2-P19-D1",
        last_teacher_question="Can you repeat: spring.",
        learner_input="winter",
        raw_teacher_reply=(
            "嗯，老师刚才问的是spring，你说的是winter，"
            "不过winter也是季节词，很棒！现在我们回到spring，跟我读一遍：spring。"
        ),
        revision_reply=(
            "嗯，老师问的是spring，但你说了winter。"
            "winter也是一个季节词，你说对了，现在我们回到spring，跟我读：spring。"
        ),
    )

    assert "很棒" not in result.teacher_response
    assert "说对了" not in result.teacher_response
    assert "spring" in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert "generic_praise_stripped" in (
        result.debug_signals.response_audit.repair_reason
    )
    assert result.debug_signals.response_audit.fallback_used is False


def test_answer_turn_policy_strips_standalone_bucuo_generic_praise():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S1U3-P25",
        block_uid="TB-G5S1U3-P25-D3",
        last_teacher_question="Now order one food and one drink.",
        learner_input="中文回答可以吗",
        raw_teacher_reply=(
            "不错，你已经用 I'd like a sandwich, please. 回答了老师的问题。"
            "现在让我们把点餐扩大一点：同时点一种食物和一种饮料。先看看这个词：tea."
        ),
    )

    assert "不错" not in result.teacher_response
    assert "I'd like a sandwich, please." in result.teacher_response
    assert "tea." in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert "generic_praise_stripped" in (
        result.debug_signals.response_audit.repair_reason
    )
    assert result.debug_signals.response_audit.fallback_used is False


def test_answer_turn_policy_repairs_generic_praise_with_wrong_learner_echo():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S1U3-P25",
        block_uid="TB-G5S1U3-P25-D2",
        last_teacher_question="What would you like to eat?",
        learner_input="I'd like a sandwich, please.",
        raw_teacher_reply=(
            "你说了沙拉，很棒！现在试试用 I'd like ... 说一个完整句子吧。"
        ),
        revision_reply=(
            "你刚才说的是“I'd like a sandwich, please.”——这是用完整句子来点餐，"
            "很好。接下来我们试着用“I'd like ...”点一份沙拉，请跟我说。"
        ),
    )

    assert "很棒" not in result.teacher_response
    assert "我听到你说 I'd like a sandwich, please." in result.teacher_response
    assert "你说了沙拉" not in result.teacher_response
    assert "I'd like. 说" not in result.teacher_response
    assert not _SMOKE_BROKEN_MIXED_ENGLISH_RE.search(result.teacher_response)
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert "generic_praise_stripped" in (
        result.debug_signals.response_audit.repair_reason
    )
    assert "learner_echo" in result.debug_signals.response_audit.repair_reason
    assert result.debug_signals.response_audit.fallback_used is False


def test_answer_turn_policy_strips_sentence_success_generic_praise():
    result = _run_policy_reply_style_case(
        page_uid="TB-G6S2U2-P16",
        block_uid="TB-G6S2U2-P16-D2",
        last_teacher_question="What did you do last weekend?",
        learner_input="What did you do last weekend?",
        raw_teacher_reply=(
            "我听到了，你直接说出了对话里的句子真棒！"
            "看来你想从Let's talk开始。"
            "我们先一起看看这句：What did you do last weekend? "
            "你能先问我一遍吗？"
        ),
    )

    assert "真棒" not in result.teacher_response
    assert "What did you do last weekend?" in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert "generic_praise_stripped" in (
        result.debug_signals.response_audit.repair_reason
    )
    assert result.debug_signals.response_audit.fallback_used is False


def test_answer_turn_policy_normalizes_common_traditional_chinese_after_revision():
    result = _run_policy_reply_style_case(
        page_uid="TB-G5S1U3-P22",
        block_uid="TB-G5S1U3-P22-D1",
        last_teacher_question="How do you say 我喜欢三明治 in English?",
        learner_input="water",
        raw_teacher_reply=(
            "你刚才说的是water，意思是“水”。老师问的是“我喜歡三明治”用英语怎么说，"
            "完整句子是 I like sandwiches。你已經可以接下來聽一個關於恐龍的練習，"
            "看看你認識 dinosaur 是什麼詞嗎？後面你跟著讀食物類單詞。"
        ),
        revision_reply=(
            "你刚才说的是water，意思是“水”。老师问的是“我喜歡三明治”用英语怎么说，"
            "完整句子是 I like sandwiches。你已經可以接下來聽一個關於恐龍的練習，"
            "看看你認識 dinosaur 是什麼詞嗎？後面你跟著讀食物類單詞。"
        ),
    )

    assert "喜歡" not in result.teacher_response
    assert "已經" not in result.teacher_response
    assert "聽" not in result.teacher_response
    assert "恐龍" not in result.teacher_response
    assert "練習" not in result.teacher_response
    assert "認識" not in result.teacher_response
    assert "什麼" not in result.teacher_response
    assert "詞嗎" not in result.teacher_response
    assert "後面" not in result.teacher_response
    assert "跟著讀" not in result.teacher_response
    assert "食物類單詞" not in result.teacher_response
    assert "喜欢" in result.teacher_response
    assert "已经" in result.teacher_response
    assert "接下来听一个关于恐龙的练习" in result.teacher_response
    assert "认识 dinosaur 是什么词吗" in result.teacher_response
    assert "后面你跟着读食物类单词" in result.teacher_response
    assert "I like sandwiches" in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert (
        result.debug_signals.response_audit.repair_reason
        == "traditional_normalized"
    )
    assert result.debug_signals.response_audit.fallback_used is False


def test_responder_repairs_navigation_exemplar_mixed_phrasing():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好，那我们就学第二块——用 I'd like 来礼貌地点餐。 "
                "先听我读一遍示范： I'd like a sandwich, please. "
                "（意思是“请给我一个三明治。”） 来，你跟着说一遍吧。"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response=(
            "好，我们进入第二块。先听示范：I'd like a sandwich, please."
        ),
        learner_input="我想学第二块",
    )

    assert result.text == (
        "好，我们进入第二块。\n"
        "先听示范：I'd like a sandwich, please.\n"
        "意思是“请给我一个三明治”。\n"
        "跟我读：I'd like a sandwich, please."
    )
    assert not _SMOKE_BROKEN_MIXED_ENGLISH_RE.search(result.text)
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "classroom_phrasing"
    assert result.audit.fallback_used is False


def test_responder_strips_inline_generic_answer_praise_without_fallback():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "你刚才说了 spring，这个回答很棒，spring 是春天。"
                "接下来听这个句型：Which season do you like best?"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="你想先学哪一块？",
        learner_input="spring",
    )

    assert "很棒" not in result.text
    assert "Which season do you like best?" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_stripped"
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_strips_praise_modifier_without_fallback():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "嗯，老师听到你说想打篮球了，很棒的运动！"
                "不过现在我们上课，要先看看课本这一页。"
                "这一页讲的是张鹏和佩德罗的学校时间表，他们在聊上午几点下课、什么时候吃午饭。"
                "你想先学哪一块？可以说 Let's talk（看对话）或者 Let's try（先听一听）。"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response=(
            "我先把选择说清楚：可以选 Let's talk 或 Let's try。"
            "你想先学哪一块？"
        ),
        learner_input="I want to play basketball.",
    )

    assert "很棒" not in result.text
    assert "Let's talk" in result.text
    assert "Let's try" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_stripped"
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_strips_hobby_generic_praise_modifier_without_fallback():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "你说想打篮球，很棒的爱好！不过我们现在在学ow的发音。"
                "老师问你：Can you read cow？试试读一下cow。"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="老师问你：Can you read cow? 试试读一下 cow.",
        learner_input="I want to play basketball.",
    )

    assert "很棒" not in result.text
    assert "爱好" not in result.text
    assert "Can you read cow" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_stripped"
    assert result.audit.fallback_used is False


def test_responder_strips_short_answer_bucuo_praise_without_fallback():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "嗯，你昨天看电视了，那也不错。现在我们翻到这一页，"
                "John 和 Amy 在等公交车。你想先试哪个？"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="你想先学哪一块？",
        learner_input="I watched TV.",
    )

    assert "不错" not in result.text
    assert "John 和 Amy" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_stripped"
    assert result.audit.fallback_used is False


def test_responder_keeps_module_choice_after_generic_praise_strip():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "老师听到你喜欢打篮球了，真不错！不过我们现在要一起完成今天的课文任务哦。"
                "这一页是《How can I get there?》的阅读理解题。"
                "你可以选下面三个板块中的一个开始："
                "第一块：读课文，回答问题（比如：Robin的新功能是什么？）"
                "第二块：填空，然后把故事复述出来"
                "第三块：练习句子的语调"
                "你想先学哪一块？告诉我就好。"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response=(
            "我先把选择说清楚：可以选 第一块、第二块 或 第三块。"
            "你想先学哪一块？"
        ),
        learner_input="I want to play basketball.",
    )

    assert "真不错" not in result.text
    assert "第一块" in result.text
    assert "第二块" in result.text
    assert "第三块" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_stripped"
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_normalizes_traditional_chinese_without_fallback():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "我们来用英语试试吧。Which season do you like best? "
                "你最喜歡哪個季節？你可以先說一句簡單的，比如：Winter."
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="我们先回答这个问题：Which season do you like best?",
        learner_input="中文可以吗",
    )

    for fragment in ("喜歡", "哪個", "季節", "說", "簡單"):
        assert fragment not in result.text
    assert "喜欢哪个季节" in result.text
    assert "说一句简单的" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "traditional_normalized"
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_strips_short_answer_zhenhao_praise_without_fallback():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "你说了spring，真好，这是我们今天要聊的一个季节。"
                "这一页我们先做 Let's talk，学 Which season do you like best?"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="我们先看 Let's talk：Which season do you like best?",
        learner_input="spring",
    )

    assert "真好" not in result.text
    assert "spring" in result.text
    assert "Which season do you like best?" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_stripped"
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_strips_short_clause_generic_praise_without_fallback():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好的，你不挑食真棒！那老师先帮你选第一句："
                "I'd like chicken and bread. 你跟着老师念一遍就好。"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="先读这一句：I'd like chicken and bread.",
        learner_input="随便，你安排",
    )

    assert "真棒" not in result.text
    assert "I'd like chicken and bread." in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_stripped"
    assert result.audit.fallback_used is False


def test_responder_strips_saying_generic_praise_without_fallback():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "你说你想打篮球，这个说法很棒！"
                "不过我们这节课正在聊的是“上周末做了什么”。"
                "先来试试把这句话用上吧：I played basketball last weekend."
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="回到这个问题：What did you do last weekend?",
        learner_input="I want to play basketball.",
    )

    assert "说法很棒" not in result.text
    assert "What did you do last weekend?" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_deterministic_repair"
    assert result.audit.fallback_used is False


def test_rag_responder_generic_praise_uses_deterministic_repair_without_fallback():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text="你说 right，这个说法很棒！",
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="rag_plus_llm",
        fallback_response=(
            "这个问题可以短聊一下。等会儿我们再绕回："
            "What is Robin's new feature? He can find food. He can find the way."
        ),
        learner_input="right",
    )

    assert result.text.startswith("这个问题可以短聊一下")
    assert "What is Robin's new feature?" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_deterministic_repair"
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_strips_target_sentence_correctness_praise_without_fallback():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "你直接说对了目标句 'Where is the museum shop?'，非常好。"
                "那我们接着练这句，试试回答它：It's near the door."
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="回到这个问题：Where is the museum shop?",
        learner_input="Where is the museum shop?",
    )

    assert "说对了目标句" not in result.text
    assert "非常好" not in result.text
    assert "Where is the museum shop?" in result.text
    assert "It's near the door." in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_stripped"
    assert result.audit.fallback_used is False


def test_responder_strips_predicate_praise_from_module_choice_prompt():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好的，你想打篮球，这个想法很棒！不过我们今天的任务是先一起看一页新内容。"
                "页面里你可以选“Let's talk”或者“Let's try”，你想先试试哪一个？"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response=(
            "我先把选择说清楚：可以选 Let's talk 或 Let's try。"
            "你想先学哪一块？"
        ),
        learner_input="I want to play basketball.",
    )

    assert "想法很棒" not in result.text
    assert "Let's talk" in result.text
    assert "Let's try" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_stripped"
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_strips_that_is_good_praise_from_module_choice_prompt():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "哦，你说你想打篮球，那很棒呀！不过我们这节课先聊聊季节。"
                '你看，这一页有"Ask and answer"（问答练习）和"Let\'s try"（听力试试看），'
                "你想先学哪一块呢？"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response=(
            "我先把选择说清楚：可以选 Ask and answer 或 Let's try。"
            "你想先学哪一块？"
        ),
        learner_input="I want to play basketball.",
    )

    assert "很棒" not in result.text
    assert "Ask and answer" in result.text
    assert "Let's try" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_stripped"
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_strips_neuter_generic_correctness_without_fallback():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好，那我们开始 Let's try 这一块。"
                "听录音，抓住关键信息。先听这句话："
                "What is the weather like today? （今天的天气怎么样？）"
                "你听到的答案是 sunny and warm（晴朗又暖和）。"
                "这个说得对，我们继续往下走。"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response=(
            "好，我们先从 Let's try 开始。听录音抓关键信息。"
            "先看看这个词你认不认识：rainy and cold"
        ),
        learner_input="我想学第二块",
    )

    assert "这个说得对" not in result.text
    assert "Let's try" in result.text
    assert "What is the weather like today?" in result.text
    assert result.audit.source == "llm_repaired"
    assert (
        result.audit.repair_reason
        == "generic_praise_stripped;classroom_phrasing"
    )
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_answer_turn_policy_recovers_markdown_field_output(tmp_path):
    runtime = _make_runtime(tmp_path)

    policy = runtime._parse_answer_turn_policy(
        """
        **currentblockuid**: TB-G5S1U3-P24-D1
        **awaitinganswer**: true
        **lastteacherquestion**: What would you like to drink?
        **teacherreply**: MARKDOWN_FIELD_REPLY_SENTINEL
        """
    )

    assert policy.teacherreply == "MARKDOWN_FIELD_REPLY_SENTINEL"
    assert policy.statepatch.currentblockuid == "TB-G5S1U3-P24-D1"
    assert policy.statepatch.awaitinganswer is True
    assert policy.statepatch.lastteacherquestion == "What would you like to drink?"


def test_answer_turn_policy_advances_then_repairs_related_wrong_without_reset(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PEPTUTOR_ANSWER_TURN_MINIMAL_RUNTIME_STATE", "0")
    manifest_path = _write_answer_policy_progression_pilot(tmp_path)
    captured_prompts: list[dict[str, object]] = []

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (history_messages, kwargs)
        payload = json.loads(prompt)
        captured_prompts.append(payload)
        frame = payload["frame"]
        block_uid = frame["currentblock"]["blockuid"]

        if block_uid == "TB-G5S1U3-P24-D2":
            assert frame["studentsaid"] == "I'd like some water."
            assert frame["currenttaskfacts"]["classroomexchange"] == {
                "teacherasked": "D2_QUESTION_SENTINEL",
                "studentsaid": "I'd like some water.",
            }
            assert frame["currenttaskfacts"]["textbooksource"]["current"]["patterns"] == [
                "I'd like some water.",
            ]
            assert frame["currenttaskfacts"]["textbooksource"]["current"]["examples"] == [
                "I'd like some water.",
            ]
            assert "expectedanswers" not in frame
            assert "acceptablecontent" not in frame
            assert "teacherlastquestion" not in frame
            assert "currentblocksource" not in frame
            assert "nextblocksource" not in frame
            for forbidden_key in (
                "teacherlastquestion",
                "currentblocksource",
                "nextblocksource",
                "textbookexamples",
            ):
                assert forbidden_key not in frame["currenttaskfacts"]
            assert frame["nextblock"]["blockuid"] == "TB-G5S1U3-P24-D3"
            assert "answercheck" not in frame
            assert frame["allowedstatewrites"]["currentblockuids"] == [
                "TB-G5S1U3-P24-D2",
                "TB-G5S1U3-P24-D3",
            ]
            return json.dumps(
                {
                    "teacherreply": "ADVANCE_POLICY_REPLY_SENTINEL",
                    "statepatch": {
                        "currentblockuid": "TB-G5S1U3-P24-D3",
                        "awaitinganswer": True,
                        "lastteacherquestion": "D3_QUESTION_SENTINEL",
                    },
                }
            )

        if block_uid == "TB-G5S1U3-P24-D3":
            assert frame["studentsaid"] == "pizza"
            assert frame["nextblock"]["blockuid"] == "TB-G5S1U3-P24-D4"
            assert "answercheck" not in frame
            assert frame["allowedstatewrites"]["currentblockuids"] == [
                "TB-G5S1U3-P24-D3",
                "TB-G5S1U3-P24-D4",
            ]
            assert [
                block["blockuid"] for block in frame["samepageblocks"]
            ] == [
                "TB-G5S1U3-P24-D3",
                "TB-G5S1U3-P24-D4",
                "TB-G5S1U3-P24-D1",
                "TB-G5S1U3-P24-D2",
            ]
            assert frame["samepageblocks"][1]["textbooksource_ref"] == (
                "currenttaskfacts.textbooksource.next"
            )
            assert frame["currenttaskfacts"]["textbooksource"]["next"] == {
                "vocabulary": [],
                "patterns": ["What would you like to eat?", "I'd like ..."],
                "examples": [],
            }
            return json.dumps(
                {
                    "teacherreply": "REPAIR_IN_PLACE_POLICY_REPLY_SENTINEL",
                    "statepatch": {
                        "currentblockuid": "TB-G5S1U3-P24-D3",
                        "awaitinganswer": True,
                        "lastteacherquestion": "D3_REPAIR_QUESTION_SENTINEL",
                    },
                }
            )

        raise AssertionError(f"unexpected policy block: {block_uid}")

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge unused by answer-turn policy test",
        ),
    )

    def _fail_if_legacy_answer_route_called(*args, **kwargs):
        _ = (args, kwargs)
        raise AssertionError("answer-turn policy success must bypass legacy answer route")

    runtime._should_interrupt_answer_turn = _fail_if_legacy_answer_route_called
    runtime._judge_answer_readiness = _fail_if_legacy_answer_route_called
    runtime._handle_success = _fail_if_legacy_answer_route_called
    runtime._handle_readiness_stay = _fail_if_legacy_answer_route_called
    runtime._handle_difficulty = _fail_if_legacy_answer_route_called

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I'd like some water.")
    repaired = runtime.handle_turn(advanced.state, "pizza")

    assert advanced.teacher_response == "ADVANCE_POLICY_REPLY_SENTINEL"
    assert advanced.teaching_action == "confirm"
    assert advanced.evaluation == "correct"
    assert advanced.block_uid == "TB-G5S1U3-P24-D3"
    assert advanced.state.current_block_uid == "TB-G5S1U3-P24-D3"
    assert advanced.state.last_teacher_question == "D3_QUESTION_SENTINEL"

    assert repaired.teacher_response == "REPAIR_IN_PLACE_POLICY_REPLY_SENTINEL"
    assert repaired.teaching_action == "hint"
    assert repaired.evaluation == "unclear"
    assert repaired.block_uid == "TB-G5S1U3-P24-D3"
    assert repaired.state.current_block_uid == "TB-G5S1U3-P24-D3"
    assert repaired.state.last_teacher_question == "D3_REPAIR_QUESTION_SENTINEL"
    assert repaired.state.current_block_uid != "TB-G5S1U3-P24-D1"

    assert [prompt["turn_kind"] for prompt in captured_prompts] == [
        "answer_turn_policy",
        "answer_turn_policy",
    ]
    assert [
        prompt["frame"]["currentblock"]["blockuid"] for prompt in captured_prompts
    ] == [
        "TB-G5S1U3-P24-D2",
        "TB-G5S1U3-P24-D3",
    ]
    assert [
        prompt["frame"]["studentsaid"] for prompt in captured_prompts
    ] == [
        "I'd like some water.",
        "pizza",
    ]
    assert "pizza" not in json.dumps(
        captured_prompts[1]["frame"]["lessoncontext"],
        ensure_ascii=False,
    ).casefold()


def test_answer_turn_policy_treats_open_slot_examples_as_non_exhaustive(
    tmp_path,
):
    manifest_path = _write_answer_policy_progression_pilot(tmp_path)
    captured_prompts: list[dict[str, object]] = []

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (history_messages, kwargs)
        payload = json.loads(prompt)
        captured_prompts.append(payload)
        frame = payload["frame"]
        block_uid = frame["currentblock"]["blockuid"]

        if block_uid == "TB-G5S1U3-P24-D2":
            return json.dumps(
                {
                    "teacherreply": "D2_ADVANCE_SENTINEL",
                    "statepatch": {
                        "currentblockuid": "TB-G5S1U3-P24-D3",
                        "awaitinganswer": True,
                        "lastteacherquestion": "What would you like to drink?",
                    },
                }
            )

        if block_uid == "TB-G5S1U3-P24-D3":
            return json.dumps(
                {
                    "teacherreply": "D3_ADVANCE_SENTINEL",
                    "statepatch": {
                        "currentblockuid": "TB-G5S1U3-P24-D4",
                        "awaitinganswer": True,
                        "lastteacherquestion": "What would you like to eat?",
                    },
                }
            )

        if block_uid == "TB-G5S1U3-P24-D4":
            assert frame["studentsaid"] == "I'd like pizza."
            assert frame["teacherasked"] == "What would you like to eat?"
            assert frame["currenttaskfacts"]["textbooksource"]["current"] == {
                "vocabulary": [],
                "patterns": ["What would you like to eat?", "I'd like ..."],
                "examples": [],
            }
            prompt_text = json.dumps(payload, ensure_ascii=False).casefold()
            assert "pizza" not in json.dumps(
                {
                    "instructions": payload["instructions"],
                    "lessoncontext": frame["lessoncontext"],
                    "samepageblocks": frame["samepageblocks"],
                    "textbooksource": frame["currenttaskfacts"]["textbooksource"],
                },
                ensure_ascii=False,
            ).casefold()
            assert "教材例句，不是开放句型的穷举答案表" in prompt_text
            assert "不要把 textbooksource.vocabulary 或 examples 当成封闭选项" in prompt_text
            assert "真实偏好问答" in prompt_text
            assert "answercheck" not in prompt_text
            assert "acceptablecontent" not in prompt_text
            assert "samescenerelatedterms" not in prompt_text
            return json.dumps(
                {
                    "teacherreply": "D4_OPEN_SLOT_ADVANCE_SENTINEL",
                    "statepatch": {
                        "currentblockuid": "TB-G5S1U3-P24-D4",
                        "awaitinganswer": False,
                        "lastteacherquestion": None,
                    },
                }
            )

        raise AssertionError(f"unexpected policy block: {block_uid}")

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge unused by answer-turn policy test",
        ),
    )

    def _fail_if_legacy_answer_route_called(*args, **kwargs):
        _ = (args, kwargs)
        raise AssertionError("answer-turn policy success must bypass legacy answer route")

    runtime._should_interrupt_answer_turn = _fail_if_legacy_answer_route_called
    runtime._judge_answer_readiness = _fail_if_legacy_answer_route_called
    runtime._handle_success = _fail_if_legacy_answer_route_called
    runtime._handle_readiness_stay = _fail_if_legacy_answer_route_called
    runtime._handle_difficulty = _fail_if_legacy_answer_route_called

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    drink_block = runtime.handle_turn(start.state, "I'd like some water.")
    food_block = runtime.handle_turn(drink_block.state, "I'd like some tea.")
    result = runtime.handle_turn(food_block.state, "I'd like pizza.")

    assert result.teacher_response == "D4_OPEN_SLOT_ADVANCE_SENTINEL"
    assert result.teaching_action == "hint"
    assert result.block_uid == "TB-G5S1U3-P24-D4"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D4"
    assert result.state.awaiting_answer is False
    assert result.evaluation == "partially_correct"
    assert [
        prompt["frame"]["currentblock"]["blockuid"] for prompt in captured_prompts
    ] == [
        "TB-G5S1U3-P24-D2",
        "TB-G5S1U3-P24-D3",
        "TB-G5S1U3-P24-D4",
    ]


def test_answer_turn_policy_frames_default_p24_task_boundary(monkeypatch):
    monkeypatch.setenv("PEPTUTOR_ANSWER_TURN_MINIMAL_RUNTIME_STATE", "0")
    captured_prompts: list[dict[str, object]] = []

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (history_messages, kwargs)
        payload = json.loads(prompt)
        captured_prompts.append(payload)
        return json.dumps(
            {
                "teacherreply": "你刚才说 I am hungry，说明饿了。下一步我们练想吃什么。",
                "statepatch": {
                    "currentblockuid": "TB-G5S1U3-P24-D3",
                    "awaitinganswer": True,
                    "lastteacherquestion": "What would you like to eat?",
                },
            }
        )

    runtime = LessonRuntime(
        PilotLessonCatalog(),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge unused by answer-turn policy test",
        ),
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    selected = runtime.handle_turn(start.state, "第一块")
    result = runtime.handle_turn(selected.state, "I am hungry.")

    frame = captured_prompts[0]["frame"]
    boundary = frame["taskboundary"]
    roles = {
        role["blockuid"]: role
        for role in boundary["samepageblockroles"]
    }

    assert frame["currentblock"] == {"blockuid": "TB-G5S1U3-P24-D2"}
    assert boundary["completionunit"] == "teacherasked_not_full_block"
    assert boundary["activequestionkind"] == "need_state"
    assert boundary["currentblockscope"] == "mixed_food_drink_scene"
    assert boundary["currentblockhasmultipletargets"] is True
    assert roles["TB-G5S1U3-P24-D2"]["relation"] == "current"
    assert roles["TB-G5S1U3-P24-D2"]["topic"] == "mixed_food_drink_scene"
    assert roles["TB-G5S1U3-P24-D3"]["relation"] == "next"
    assert roles["TB-G5S1U3-P24-D3"]["topic"] == "food"
    assert roles["TB-G5S1U3-P24-D4"]["topic"] == "drink"
    assert roles["TB-G5S1U3-P24-D1"]["topic"] == "listening"
    assert any(
        "teacherasked" in rule
        for rule in boundary["progressionrules"]
    )
    assert result.teaching_action == "confirm"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D3"


def test_answer_turn_policy_keeps_extension_task_instruction_out_of_examples(
    tmp_path,
):
    runtime = _make_runtime(tmp_path)
    block = runtime.catalog.get_block("TB-G5S1U3-P26-D1")

    source = runtime._answer_turn_policy_textbook_source(block)

    assert block.block_type == "extension_task"
    assert source["patterns"] == ["I'd like noodles for breakfast."]
    assert source["examples"] == []


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
    assert "哪一块" in result.teacher_response
    assert "先试着说一遍" not in result.teacher_response
    assert "Listen and number" not in result.teacher_response
    assert "TB-G5S2U4-P44" not in (
        LIGHTRAG_ROOT / "lightrag/orchestrator/page_overview_skill.py"
    ).read_text(encoding="utf-8")


def test_page_entry_overviews_try_talk_page_before_drilling(tmp_path):
    manifest_path = _write_try_talk_module_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))

    result = runtime.start_page("TB-G5S1U1-P4", "student-1")

    assert result.turn_label == "page_entry"
    assert result.teaching_action == "page_intro"
    assert result.state.awaiting_answer is True
    assert result.state.current_activity_type == "page_entry"
    assert result.state.page_entry_probe_done is False
    assert result.state.last_teacher_question == (
        "你想先学哪一块？可以说 Let's try 或 Let's talk。"
    )
    assert "Let's try" in result.teacher_response
    assert "Let's talk" in result.teacher_response
    assert "哪一块" in result.teacher_response
    assert "Can you say" not in result.teacher_response
    assert "直接从第一个" not in result.teacher_response


def test_page_entry_overview_compacts_default_four_module_page():
    runtime = LessonRuntime(PilotLessonCatalog())

    result = runtime.start_page("TB-G5S1U3-P24", "student-1")

    assert len(result.teacher_response) < 120
    assert "第一块（hungry/thirsty）" in result.teacher_response
    assert "第二块（食物小词库）" in result.teacher_response
    assert "第三块（饮料小词库）" in result.teacher_response
    assert "第四块（听力）" in result.teacher_response
    assert "What would you like" not in result.teacher_response
    assert "I'd like" not in result.teacher_response
    assert "你想先学哪一块" in result.teacher_response


def test_page_entry_repairs_overloaded_live_overview_to_compact_choice():
    runtime = LessonRuntime(
        PilotLessonCatalog(),
        responder=LessonResponder(
            lambda *args, **kwargs: (
                "好的，这一页我们学在餐厅里点餐，看看怎么问别人想吃什么、想喝什么。"
                "这一页有4个小块可以学：第一块：先认识 hungry 和 thirsty，"
                "再练两个核心问句：What would you like to eat? 和 "
                "What would you like to drink? 第二块：用食物小词库练点餐，"
                "听懂 What would you like to eat?，然后用 I'd like ... 回答。"
                "第三块：用饮料小词库练点餐，听懂 What would you like to drink?，"
                "再用 I'd like ... 回答。第四块：听录音，听出 Sarah 想吃什么。"
                "你想先学哪一块？可以说 第一块、第二块、第三块 或 第四块。"
            )
        ),
        debug_signals_enabled=True,
    )

    result = runtime.start_page("TB-G5S1U3-P24", "student-1")

    assert len(result.teacher_response) < 120
    assert "两个核心问句" not in result.teacher_response
    assert "What would you like" not in result.teacher_response
    assert "第二块（食物小词库）" in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "llm_repaired"
    assert result.debug_signals.response_audit.repair_reason == "classroom_pacing"
    assert result.debug_signals.response_audit.fallback_used is False


def test_page_entry_overviews_source_split_page_without_explicit_labels(tmp_path):
    manifest_path = _write_source_split_page_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))

    result = runtime.start_page("TB-G5S1U3-P44", "student-1")

    assert result.turn_label == "page_entry"
    assert result.teaching_action == "page_intro"
    assert result.state.awaiting_answer is True
    assert result.state.current_activity_type == "page_entry"
    assert result.state.last_teacher_question == (
        "你想先学哪一块？可以说 第一块、第二块 或 第三块。"
    )
    assert "第一块" in result.teacher_response
    assert "第二块" in result.teacher_response
    assert "第三块" in result.teacher_response
    assert "饮料小词库" in result.teacher_response
    assert "食物小词库" in result.teacher_response
    assert "I am hungry" not in result.teacher_response


def test_module_choice_starts_tiny_task_without_module_summary_overload():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    result = runtime.handle_turn(start.state, "我想学第二块")

    assert result.turn_label == "navigation"
    assert result.block_uid == "TB-G5S1U3-P24-D3"
    assert len(result.teacher_response) < 90
    assert "先用食物小词库练习点餐对话" not in result.teacher_response
    assert "听懂 What would you like to eat" not in result.teacher_response
    assert "好，我们先从 第二块 开始。" in result.teacher_response
    assert "I'd like chicken and bread" in result.teacher_response


def test_module_choice_clarification_avoids_operational_learning_entry_phrase():
    catalog = PilotLessonCatalog(manifest_path=_general_overlay_manifest_path())
    runtime = LessonRuntime(catalog)
    runtime._stable_variant_index = lambda *parts: 1
    overview = runtime._build_page_overview(catalog.get_page("TB-G5S2U1-P4"))
    assert overview is not None

    reply = runtime._render_module_choice_clarification(
        overview=overview,
        learner_input="start class",
        page_uid="TB-G5S2U1-P4",
    )

    assert "先定学习入口" not in reply
    assert reply == "先选一块开始：Let's talk 或 Let's try。你想从哪一块开始？"


def test_source_split_page_choice_can_use_learner_content_not_only_index(tmp_path):
    manifest_path = _write_source_split_page_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G5S1U3-P44", "student-1")

    result = runtime.handle_turn(start.state, "I'd like some water.")

    assert result.turn_label == "navigation"
    assert result.teaching_action == "probe"
    assert result.block_uid == "TB-G5S1U3-P44-D2"
    assert result.state.current_block_uid == "TB-G5S1U3-P44-D2"
    assert result.state.current_activity_type == "teaching"
    assert "第二块" in result.teacher_response
    assert "What would you like to drink" in result.teacher_response


def test_page_entry_teacher_choice_input_starts_default_module(tmp_path):
    manifest_path = _write_source_split_page_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G5S1U3-P44", "student-1")

    result = runtime.handle_turn(start.state, "随便，你安排")

    assert result.turn_label == "navigation"
    assert result.teaching_action == "probe"
    assert result.block_uid == "TB-G5S1U3-P44-D1"
    assert result.state.current_block_uid == "TB-G5S1U3-P44-D1"
    assert result.state.current_activity_type == "teaching"
    assert "我来安排" in result.teacher_response
    assert "第一块" in result.teacher_response
    assert "你想先学哪一块" not in result.teacher_response


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


def test_page_entry_repairs_llm_that_skips_multi_module_choice(tmp_path):
    manifest_path = _write_multi_module_review_pilot(tmp_path)
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(
            lambda *args, **kwargs: "这一页我们先听录音抓日期。你可以先说一个数字。"
        ),
        debug_signals_enabled=True,
    )

    result = runtime.start_page("TB-G5S2U9-P12", "student-1")

    assert "Let's check" in result.teacher_response
    assert "Let's wrap it up" in result.teacher_response
    assert "哪一块" in result.teacher_response
    assert "先说一个数字" not in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "llm_repaired"
    assert (
        result.debug_signals.response_audit.repair_reason
        == "page_entry_module_choice_repaired"
    )
    assert result.debug_signals.response_audit.fallback_used is False
    assert result.debug_signals.response_audit.fallback_reason == "none"


def test_g5s2_p4_page_entry_none_input_does_not_force_fallback():
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        responder=LessonResponder(
            lambda *args, **kwargs: "这一页我们先看西班牙作息，听懂 Pedro 几点上课。"
        ),
        debug_signals_enabled=True,
    )

    result = runtime.start_page("TB-G5S2U1-P4", "student-1")

    assert "你想先学哪一块" in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "llm_repaired"
    assert (
        result.debug_signals.response_audit.repair_reason
        == "page_entry_module_choice_repaired"
    )
    assert result.debug_signals.response_audit.fallback_used is False
    assert result.debug_signals.response_audit.fallback_reason == "none"


def test_g5s2_p14_page_overview_keeps_lets_talk_priority_block():
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        debug_signals_enabled=True,
    )
    page = runtime.catalog.get_page("TB-G5S2U2-P14")

    overview = runtime._build_page_overview(page)

    assert overview is not None
    assert [module.label for module in overview.modules] == [
        "Let's talk",
        "Ask and answer",
        "Let's try",
    ]
    assert [list(module.block_uids) for module in overview.modules] == [
        ["TB-G5S2U2-P14-D2"],
        ["TB-G5S2U2-P14-D3"],
        ["TB-G5S2U2-P14-D1"],
    ]


def test_g6s2_p16_practice_overlay_widens_open_answer_scope():
    catalog = PilotLessonCatalog(manifest_path=_general_overlay_manifest_path())
    block = catalog.get_block("TB-G6S2U2-P16-D4")

    assert block.core_patterns == [
        "What did you do yesterday/last night ...?",
        "What do you usually do on weekends?",
    ]
    assert "I watched TV." in block.allowed_answer_scope
    assert "I cleaned my room." in block.allowed_answer_scope
    assert "I usually play football on weekends." in block.allowed_answer_scope
    assert len(block.allowed_answer_scope) >= 6


def test_g6s2_p49_party_scene_overlay_classifies_targets():
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        debug_signals_enabled=True,
    )
    page = runtime.catalog.get_page("TB-G6S2Recycle2-P49")
    block = runtime.catalog.get_block("TB-G6S2Recycle2-P49-D1")
    overview = runtime._build_page_overview(page)

    assert block.core_patterns == [
        "Classify party words into food, drinks, and supplies."
    ]
    assert "food: brown bread, cheese, cake, fresh fruit, chocolates" in block.allowed_answer_scope
    assert "drinks: milk, orange juice" in block.allowed_answer_scope
    assert "supplies: tea bags" in block.allowed_answer_scope
    assert block.task_type == "classify"
    assert block.answer_scope["related_terms_policy"] == (
        "acknowledge_but_prompt_page_item"
    )
    assert block.answer_scope["categories"][0]["name"] == "food"
    assert "pizza" not in block.answer_scope["categories"][0]["items"]
    assert block.answer_scope["categories"][0]["aliases"]["pizza"] == "pizza"
    assert overview is not None
    assert list(overview.modules[0].block_uids) == ["TB-G6S2Recycle2-P49-D1"]


def test_classification_short_answer_policy_uses_structured_scope_not_page_uid():
    block = {
        "block_uid": "TB-SYNTH-P1-D1",
        "task_type": "classify",
        "teaching_goal": "Classify classroom words into tools and places.",
        "teaching_summary": "A synthetic classification task.",
        "core_patterns": ["Classify classroom words."],
        "entry_probe_questions": ["Find one tool word."],
        "allowed_answer_scope": [],
        "answer_scope": {
            "categories": [
                {
                    "name": "tools",
                    "items": ["pencil", "ruler"],
                    "aliases": {"铅笔": "pencil", "pen": "pen"},
                },
                {"name": "places", "items": ["classroom"]},
            ],
        },
    }

    exact = classify_short_answer_for_task(
        learner_input="pencil",
        block=block,
        last_teacher_question="Find one tool word.",
    )
    related = classify_short_answer_for_task(
        learner_input="pen",
        block=block,
        last_teacher_question="Find one tool word.",
    )
    alias = classify_short_answer_for_task(
        learner_input="铅笔",
        block=block,
        last_teacher_question="Find one tool word.",
    )

    assert exact is not None
    assert exact.kind == "exact_page_item"
    assert related is not None
    assert related.kind == "related_category_term"
    assert alias is not None
    assert alias.kind == "alias_page_item"


def test_classification_short_answer_policy_requires_classification_task_boundary():
    block = {
        "block_uid": "TB-SYNTH-DIALOGUE-D1",
        "task_type": "dialogue",
        "teaching_goal": "Practice ordering food and drinks.",
        "teaching_summary": "A dialogue task with food and drink words.",
        "core_patterns": ["What would you like to eat?"],
        "entry_probe_questions": ["What would you like to eat?"],
        "answer_scope": {
            "categories": [
                {"name": "food", "items": ["sandwich", "salad"]},
                {"name": "drinks", "items": ["water", "tea"]},
            ],
        },
    }

    decision = classify_short_answer_for_task(
        learner_input="pizza",
        block=block,
        last_teacher_question="What would you like to eat?",
    )

    assert decision is None


def test_classification_short_answer_related_term_uses_generic_page_item_pullback():
    block = {
        "block_uid": "TB-SYNTH-P1-D1",
        "task_type": "classify",
        "teaching_goal": "Classify classroom words into tools and places.",
        "teaching_summary": "A synthetic classification task.",
        "core_patterns": ["Classify classroom words."],
        "entry_probe_questions": ["Find one tool word."],
        "answer_scope": {
            "categories": [
                {
                    "name": "tools",
                    "items": ["pencil", "ruler"],
                    "aliases": {"pen": "pen"},
                },
                {"name": "places", "items": ["classroom"]},
            ],
        },
    }

    decision = classify_short_answer_for_task(
        learner_input="pen",
        block=block,
        last_teacher_question="Find one tool word.",
    )

    assert decision is not None
    assert decision.kind == "related_category_term"
    assert render_classification_short_answer_reply(decision) == (
        "pen 可以算 tools，不过这页图上我们先找本页词，比如 pencil 或 ruler。"
    )


def test_classification_short_answer_policy_skips_dialogue_ordering_and_phonics_blocks():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))

    cases = [
        ("TB-G5S1U3-P24-D1", "pizza", "What would you like to drink?"),
        ("TB-G5S1U3-P25-D1", "water", "What would you like to eat?"),
        ("TB-G5S1U3-P26-D1", "snow", "Read the words with ow."),
    ]
    for block_uid, learner_input, question in cases:
        block = runtime.catalog.get_block(block_uid)
        decision = classify_short_answer_for_task(
            learner_input=learner_input,
            block=block,
            last_teacher_question=question,
        )
        assert decision is None, block_uid


def test_p49_classification_short_answer_replies_to_related_food_without_object_praise():
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        debug_signals_enabled=True,
    )
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")

    result = runtime.handle_turn(start.state, "pizza")

    assert result.block_uid == "TB-G6S2Recycle2-P49-D1"
    assert result.teacher_response == (
        "pizza 可以算 food，不过这页图上我们先找本页词，比如 brown bread 或 cheese。"
    )
    assert "很好吃" not in result.teacher_response
    assert "很棒" not in result.teacher_response
    assert "不错" not in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "policy_repaired"
    assert (
        result.debug_signals.response_audit.repair_reason
        == "classification_short_answer_policy"
    )
    assert result.debug_signals.response_audit.route == (
        "classification_short_answer_policy"
    )


def test_p49_classification_short_answer_pulls_wrong_category_back_to_target():
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        debug_signals_enabled=True,
    )
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")
    selected = runtime.handle_turn(start.state, "第一块")

    result = runtime.handle_turn(selected.state, "water")

    assert result.block_uid == "TB-G6S2Recycle2-P49-D1"
    assert result.evaluation == "partially_correct"
    assert "water 属于 drinks" in result.teacher_response
    assert "这一步先找 food" in result.teacher_response
    assert "brown bread" in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2Recycle2-P49-D1"


def test_p49_classification_short_answer_does_not_guess_unknown_term():
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        debug_signals_enabled=True,
    )
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")

    result = runtime.handle_turn(start.state, "news")

    assert result.block_uid == "TB-G6S2Recycle2-P49-D1"
    assert "news 属于" not in result.teacher_response
    assert "不在这个 party word 任务里" in result.teacher_response
    assert "food" in result.teacher_response


def test_p49_classification_short_answer_scaffolds_uncertainty_without_praise():
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        debug_signals_enabled=True,
    )
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")
    selected = runtime.handle_turn(start.state, "第一块")

    result = runtime.handle_turn(selected.state, "我不知道")

    assert result.block_uid == "TB-G6S2Recycle2-P49-D1"
    assert "没关系" in result.teacher_response
    assert "brown bread" in result.teacher_response
    assert "很棒" not in result.teacher_response
    assert "不错" not in result.teacher_response


def test_p49_classification_short_answer_does_not_intercept_module_navigation():
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        debug_signals_enabled=True,
    )
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")

    result = runtime.handle_turn(start.state, "我想学第二块")

    assert result.block_uid == "TB-G6S2Recycle2-P49-D2"
    assert result.state.current_block_uid == "TB-G6S2Recycle2-P49-D2"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.route != (
        "classification_short_answer_policy"
    )


def test_classification_short_answer_policy_does_not_touch_p24_drink_boundary():
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        debug_signals_enabled=True,
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    result = runtime.handle_turn(start.state, "I'd like some water.")

    assert result.page_uid == "TB-G5S1U3-P24"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.route != (
        "classification_short_answer_policy"
    )


def test_g5s1_p31_grounded_unit_vocabulary_question_does_not_fallback():
    def _teacher_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        parsed = json.loads(prompt)
        if parsed["turn_label"] == "ask_knowledge":
            return "It means needing a drink."
        return parsed["fallback"]

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        responder=LessonResponder(_teacher_llm),
        debug_signals_enabled=True,
    )

    start = runtime.start_page("TB-G5S1U3-P31", "student-1")
    result = runtime.handle_turn(start.state, "What does thirsty mean?")

    assert result.turn_label == "ask_knowledge"
    assert "thirsty" in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "llm_repaired"
    assert (
        result.debug_signals.response_audit.repair_reason
        == "grounded_lexicon_english_only_repaired"
    )
    assert result.debug_signals.response_audit.fallback_used is False
    assert result.debug_signals.response_audit.fallback_reason == "none"


def test_vocab_answer_return_plans_structural_move_without_changing_reply():
    planned_moves: list[dict[str, object]] = []
    captured_prompts: list[dict[str, object]] = []

    class CapturingTeachingMovePlanner(TeachingMovePlanner):
        def plan_vocab_answer_return(
            self,
            *,
            learner_input: str,
            retrieval_mode: str,
            return_anchor: str | None,
            active_prompt: str | None,
            retrieval_count: int,
            support_count: int,
        ):
            move = super().plan_vocab_answer_return(
                learner_input=learner_input,
                retrieval_mode=retrieval_mode,
                return_anchor=return_anchor,
                active_prompt=active_prompt,
                retrieval_count=retrieval_count,
                support_count=support_count,
            )
            planned_moves.append(move.to_prompt_payload())
            return move

    def _teacher_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        parsed = json.loads(prompt)
        captured_prompts.append(parsed)
        return parsed["fallback"]

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        responder=LessonResponder(_teacher_llm),
        teaching_move_planner=CapturingTeachingMovePlanner(),
        debug_signals_enabled=True,
    )

    start = runtime.start_page("TB-G5S1U3-P31", "student-1")
    result = runtime.handle_turn(start.state, "What does thirsty mean?")

    assert result.teacher_response == (
        "thirsty 是“渴的；口渴的”。回到刚才的小任务，先试试："
        "What would Zoom like to eat?"
    )
    assert result.turn_label == "ask_knowledge"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.route == "rag_plus_llm"
    assert result.debug_signals.response_audit.source == "llm"
    assert result.debug_signals.response_audit.repair_reason == "none"
    assert captured_prompts[-1]["teaching_move"]["move"] == "answer_briefly_then_return"
    assert planned_moves == [
        {
            "schema_version": "peptutor-teaching-move-v1",
            "detected_signal": "vocabulary_question",
            "move": "vocab_answer_return",
            "teaching_action": "explain",
            "rationale": (
                "The learner asked for a word meaning during the lesson; answer the "
                "word narrowly and return to the active classroom task."
            ),
            "evidence_fields_used": [
                "learner_input",
                "planner.retrieval_mode",
                "retrieval_selection.block_uids",
                "support_hits",
                "runtime_state.last_teacher_question",
                "return_anchor",
            ],
            "expected_next_learner_action": (
                "Use the short meaning, then continue with the current task prompt."
            ),
            "payload_fields": {
                "query_term": "thirsty",
                "retrieval_mode": "unit",
                "return_anchor": "先试试：What would Zoom like to eat?",
                "active_prompt": "先试试：What would Zoom like to eat?",
                "return_to_current_task": True,
                "retrieval_evidence_count": 1,
                "support_evidence_count": 1,
                "target_role": "question",
                    "expected_student_action": "answer",
                    "question_target": "What would Zoom like to eat?",
                    "answer_target": "",
                    "answer_frame": "Zoom would like ...",
                    "action_source": "active_prompt",
                "preserve_page_uid": "",
                "preserve_block_uid": "",
                "target_phrase": "What would Zoom like to eat?",
            },
            "constraints": [
                "Do not change the current page or block.",
                "Do not reopen module choice unless the active prompt is module choice.",
                "Ground the word meaning in retrieval or support evidence.",
            ],
        }
    ]


def test_vocab_answer_return_uses_current_block_anchor_when_not_awaiting_answer():
    planned_moves: list[dict[str, object]] = []

    class CapturingTeachingMovePlanner(TeachingMovePlanner):
        def plan_vocab_answer_return(
            self,
            *,
            learner_input: str,
            retrieval_mode: str,
            return_anchor: str | None,
            active_prompt: str | None,
            retrieval_count: int,
            support_count: int,
        ):
            move = super().plan_vocab_answer_return(
                learner_input=learner_input,
                retrieval_mode=retrieval_mode,
                return_anchor=return_anchor,
                active_prompt=active_prompt,
                retrieval_count=retrieval_count,
                support_count=support_count,
            )
            planned_moves.append(move.to_prompt_payload())
            return move

    def _teacher_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        parsed = json.loads(prompt)
        return parsed["fallback"]

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        responder=LessonResponder(_teacher_llm),
        teaching_move_planner=CapturingTeachingMovePlanner(),
        debug_signals_enabled=True,
    )

    start = runtime.start_page("TB-G5S2U2-P19", "student-1")
    after_answer = runtime.handle_turn(start.state, "I like spring.")
    result = runtime.handle_turn(after_answer.state, "What does because mean?")

    assert result.turn_label == "ask_knowledge"
    payload_fields = planned_moves[-1]["payload_fields"]
    assert payload_fields["return_anchor"] == "先试着说一遍：Read and tick."
    assert payload_fields["active_prompt"] == "先试着说一遍：Read and tick."
    assert payload_fields["return_to_current_task"] is True


def test_gentle_redirect_plans_structural_move_without_changing_reply(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    planned_moves: list[dict[str, object]] = []
    captured_prompts: list[dict[str, object]] = []

    class CapturingTeachingMovePlanner(TeachingMovePlanner):
        def plan_gentle_redirect(
            self,
            *,
            learner_input: str,
            interpreted_intent: str,
            current_target: str,
            target_phrase: str,
            active_prompt: str,
            return_anchor: str,
            next_action: str,
            correction_kind: str,
            route: str,
            turn_label: str,
            preserve_page_uid: str,
            preserve_block_uid: str,
            block=None,
        ):
            move = super().plan_gentle_redirect(
                learner_input=learner_input,
                interpreted_intent=interpreted_intent,
                current_target=current_target,
                target_phrase=target_phrase,
                active_prompt=active_prompt,
                return_anchor=return_anchor,
                next_action=next_action,
                correction_kind=correction_kind,
                route=route,
                turn_label=turn_label,
                preserve_page_uid=preserve_page_uid,
                preserve_block_uid=preserve_block_uid,
                block=block,
            )
            planned_moves.append(move.to_prompt_payload())
            return move

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (history_messages, kwargs)
        payload = json.loads(prompt)
        captured_prompts.append(payload)
        return json.dumps(
            {
                "teacherreply": "ANSWER_TURN_POLICY_REPLY_SENTINEL",
                "statepatch": {
                    "currentblockuid": "TB-G5S1U3-P24-D1",
                    "awaitinganswer": True,
                    "lastteacherquestion": "What would you like to drink?",
                },
            }
        )

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge unused by answer-turn policy test",
        ),
        teaching_move_planner=CapturingTeachingMovePlanner(),
        debug_signals_enabled=True,
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "I want to play basketball.")

    assert result.teacher_response == "ANSWER_TURN_POLICY_REPLY_SENTINEL"
    assert result.turn_label == "answer_question"
    assert result.evaluation == "incorrect"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.route == "answer_turn_policy"
    assert [prompt["turn_kind"] for prompt in captured_prompts] == [
        "answer_turn_policy",
    ]
    assert "teaching_move" not in captured_prompts[-1]["frame"]
    assert planned_moves == [
        {
            "schema_version": "peptutor-teaching-move-v1",
            "detected_signal": "off_topic",
            "move": "gentle_redirect",
            "teaching_action": "redirect",
            "rationale": (
                "The learner turn needs a small scaffold or pullback while preserving "
                "the current page, block, and classroom target."
            ),
            "evidence_fields_used": [
                "learner_input",
                "runtime_state.current_page_uid",
                "runtime_state.current_block_uid",
                "runtime_state.last_teacher_question",
                "teaching_block.teaching_goal",
                "teaching_block.core_patterns",
                "teaching_block.allowed_answer_scope",
                "teaching_block.return_anchors",
                "planner.route",
                "planner.turn_label",
            ],
            "expected_next_learner_action": (
                "Return to the active prompt with one short answer or use the offered scaffold."
            ),
            "payload_fields": {
                "learner_input": "I want to play basketball.",
                "interpreted_intent": "off_topic",
                "current_target": "Use the target drink question and answer.",
                "target_phrase": "What would you like to drink?",
                "active_prompt": "Can you answer: What would you like to drink?",
                "return_anchor": "What would you like to drink?",
                "next_action": "return_to_active_task",
                "correction_kind": "incorrect",
                "route": "answer_turn_policy",
                "turn_label": "answer_question",
                "preserve_page_uid": "TB-G5S1U3-P24",
                "preserve_block_uid": "TB-G5S1U3-P24-D1",
                "target_role": "question",
                "expected_student_action": "answer",
                "question_target": "What would you like to drink?",
                "answer_target": "I'd like some water.",
                "answer_frame": "I'd like ...",
                "action_source": "block_core_pattern",
            },
            "constraints": [
                "Do not change the current page or block.",
                "Do not change the runtime route.",
                "Do not reopen module choice unless the existing route already does.",
                "Keep the pullback grounded in the current target phrase or active prompt.",
            ],
        }
    ]


def _run_policy_case_with_captured_gentle_move(
    *,
    page_uid: str,
    block_uid: str,
    last_teacher_question: str,
    learner_input: str,
    raw_teacher_reply: str,
):
    planned_moves: list[dict[str, object]] = []

    class CapturingTeachingMovePlanner(TeachingMovePlanner):
        def plan_gentle_redirect(self, **kwargs):
            move = super().plan_gentle_redirect(**kwargs)
            planned_moves.append(move.to_prompt_payload())
            return move

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (history_messages, kwargs)
        payload = json.loads(prompt)
        if payload["turn_kind"] == "answer_turn_policy_reply_quality_revision":
            return raw_teacher_reply
        return json.dumps(
            {
                "teacherreply": raw_teacher_reply,
                "statepatch": {
                    "currentblockuid": block_uid,
                    "awaitinganswer": True,
                    "lastteacherquestion": last_teacher_question,
                },
            }
        )

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge unused by teaching move payload test",
        ),
        teaching_move_planner=CapturingTeachingMovePlanner(),
        debug_signals_enabled=True,
    )
    start = runtime.start_page(page_uid, "student-1")
    state = start.state.model_copy(deep=True)
    state.current_activity_type = "teaching"
    state.current_block_uid = block_uid
    state.awaiting_answer = True
    state.last_teacher_question = last_teacher_question

    result = runtime.handle_turn(state, learner_input)
    assert planned_moves
    return result, planned_moves[-1]["payload_fields"]


def test_gentle_redirect_runtime_payload_records_direction_question_answer_contract():
    result, fields = _run_policy_case_with_captured_gentle_move(
        page_uid="TB-G6S1U1-P4",
        block_uid="TB-G6S1U1-P4-D2",
        last_teacher_question="Where is the museum shop?",
        learner_input="turn left",
        raw_teacher_reply=(
            "你刚才说的是 turn left. 先回到课本目标：It's near the door. "
            "把这句读出来：It's near the door."
        ),
    )

    assert result.state.current_block_uid == "TB-G6S1U1-P4-D2"
    assert "Where is the museum shop?" in result.teacher_response
    assert fields["target_role"] == "question"
    assert fields["expected_student_action"] == "answer"
    assert fields["question_target"] == "Where is the museum shop?"
    assert fields["answer_target"] == "It's near the door."
    assert fields["answer_frame"] == "It's near ..."


def test_gentle_redirect_runtime_payload_keeps_height_answer_frame():
    result, fields = _run_policy_case_with_captured_gentle_move(
        page_uid="TB-G6S2U1-P4",
        block_uid="TB-G6S2U1-P4-D2",
        last_teacher_question="How tall is it?",
        learner_input="How tall are you?",
        raw_teacher_reply=(
            "你刚才说的是 How tall are you. "
            "这一步先听清这个问题：How tall is it?"
        ),
    )

    assert result.state.current_block_uid == "TB-G6S2U1-P4-D2"
    assert "How tall is it?" in result.teacher_response
    assert fields["target_phrase"] == "How tall is it?"
    assert fields["target_role"] == "question"
    assert fields["expected_student_action"] == "answer"
    assert fields["question_target"] == "How tall is it?"
    assert fields["question_target"] != "How tall are you"
    assert fields["answer_target"] == ""
    assert fields["answer_frame"] == "It's ... metres tall."


def test_gentle_redirect_runtime_payload_frames_listening_looking_at_question():
    result, fields = _run_policy_case_with_captured_gentle_move(
        page_uid="TB-G6S2U1-P4",
        block_uid="TB-G6S2U1-P4-D1",
        last_teacher_question="Listen and circle: What are the children looking at in the museum?",
        learner_input="heavier",
        raw_teacher_reply=(
            "你听到了heavier。问题是：孩子们在博物馆里看什么？"
            "再听一次，圈出答案：dinosaur, vegetables, 还是 meat？"
        ),
    )

    assert result.state.current_block_uid == "TB-G6S2U1-P4-D1"
    assert fields["target_role"] == "question"
    assert fields["expected_student_action"] == "answer"
    assert fields["question_target"] == "What are the children looking at in the museum?"
    assert fields["answer_target"] == ""
    assert fields["answer_frame"] == "They are looking at ..."
    assert fields["target_phrase"] != "heavier"


def test_gentle_redirect_runtime_payload_treats_height_sentence_as_answer():
    result, fields = _run_policy_case_with_captured_gentle_move(
        page_uid="TB-G6S2U1-P2",
        block_uid="TB-G6S2U1-P2-D1",
        last_teacher_question="I'm 1.6 metres tall?",
        learner_input="water",
        raw_teacher_reply=(
            "你刚才说的是 water. 先听，再说：I'm 1.6 metres tall?"
        ),
    )

    assert result.state.current_block_uid == "TB-G6S2U1-P2-D1"
    assert fields["target_phrase"] == "I'm 1.6 metres tall."
    assert fields["target_role"] == "answer"
    assert fields["expected_student_action"] == "repeat"
    assert fields["question_target"] == ""
    assert fields["answer_target"] == "I'm 1.6 metres tall."


def test_gentle_redirect_runtime_payload_records_story_action_contract():
    result, fields = _run_policy_case_with_captured_gentle_move(
        page_uid="TB-G5S1U3-P31",
        block_uid="TB-G5S1U3-P31-D1",
        last_teacher_question="What would Zoom like to eat?",
        learner_input="Zip",
        raw_teacher_reply=(
            "你提到了Zip，没错，故事里Zoom和Zip在一起。"
            "问题是Zoom想吃什么？试试用英语回答：Zoom would like a ___."
        ),
    )

    assert result.state.current_block_uid == "TB-G5S1U3-P31-D1"
    assert fields["target_role"] == "story"
    assert fields["expected_student_action"] == "answer"
    assert fields["question_target"] == "What would Zoom like to eat?"
    assert fields["answer_target"] == "Zoom would like a salad."
    assert fields["answer_frame"] == "Zoom would like ..."


def test_gentle_redirect_runtime_payload_records_phonics_action_contract():
    result, fields = _run_policy_case_with_captured_gentle_move(
        page_uid="TB-G5S2U1-P6",
        block_uid="TB-G5S2U1-P6-D1",
        last_teacher_question="Can you say: Learn the consonant blend 'cl' as in 'clean'.",
        learner_input="I want to play basketball.",
        raw_teacher_reply=(
            "你刚才说的是 I want to play basketball. 你来读：cl' as in."
        ),
    )

    assert result.state.current_block_uid == "TB-G5S2U1-P6-D1"
    assert "cl' as in" not in result.teacher_response
    assert fields["target_role"] == "phonics"
    assert fields["expected_student_action"] == "repeat"
    assert fields["question_target"] == ""
    assert fields["answer_target"] == "clean"


def test_gentle_redirect_runtime_payload_extracts_phonics_target_from_word_list():
    result, fields = _run_policy_case_with_captured_gentle_move(
        page_uid="TB-G5S2U1-P6",
        block_uid="TB-G5S2U1-P6-D2",
        last_teacher_question="Class, clock, plate, eggplant, clean, play.",
        learner_input="water",
        raw_teacher_reply=(
            "你说water，这是个有意思的词。不过我们这一页在学cl和pl的发音，"
            "你是想选第一块（说句子）、第二块（学发音）还是第三块（练习游戏）？"
        ),
    )

    assert result.state.current_block_uid == "TB-G5S2U1-P6-D2"
    assert fields["target_role"] == "phonics"
    assert fields["expected_student_action"] == "repeat"
    assert fields["question_target"] == ""
    assert fields["answer_target"] == "class"
    assert fields["answer_target"] != "water"


def test_gentle_redirect_runtime_payload_extracts_phonics_target_from_repeat_instruction():
    result, fields = _run_policy_case_with_captured_gentle_move(
        page_uid="TB-G5S2U1-P6",
        block_uid="TB-G5S2U1-P6-D2",
        last_teacher_question="Listen and repeat: clean.",
        learner_input="I want to play basketball.",
        raw_teacher_reply=(
            "你说想打篮球。这一页我们要学的是 cl 和 pl 的发音。"
            "我们先把第二块做好：听我说词，你来读。第一个词：clean."
        ),
    )

    assert result.state.current_block_uid == "TB-G5S2U1-P6-D2"
    assert "cl' as in" not in result.teacher_response
    assert fields["target_role"] == "phonics"
    assert fields["expected_student_action"] == "repeat"
    assert fields["question_target"] == ""
    assert fields["answer_target"] == "clean"
    assert fields["answer_target"] != "basketball"


def test_redirect_reply_policy_ignores_invalid_action_fields_and_uses_active_prompt():
    catalog = PilotLessonCatalog(manifest_path=_general_overlay_manifest_path())
    block = catalog.get_block("TB-G5S1U3-P22-D1")

    repaired = maybe_render_redirect_reply(
        learner_input="water",
        target_phrase="water",
        teacher_reply=(
            "你刚才说的是 water. 先听，再说：What's your favourite food?"
        ),
        block=block,
        active_prompt="What's your favourite food?",
        return_anchor="What's your favourite food?",
        action_fields={
            "target_role": "question",
            "expected_student_action": "answer",
            "question_target": 123,
            "answer_target": "",
            "answer_frame": "My favourite food is ...",
            "action_source": "block_core_pattern",
            "target_phrase": "water",
        },
    )

    assert repaired is not None
    assert "What's your favourite food?" in repaired
    assert "你最喜欢的食物是什么" in repaired
    assert "water（水）" in repaired or "water" in repaired


def test_redirect_reply_policy_uses_valid_contract_over_polluted_return_anchor():
    catalog = PilotLessonCatalog(manifest_path=_general_overlay_manifest_path())
    block = catalog.get_block("TB-G6S2U2-P13-D2")

    repaired = maybe_render_redirect_reply(
        learner_input="water",
        target_phrase="What did you do last weekend?",
        teacher_reply=(
            "你说了“water”，这是“水”的意思。我们这一页有两块内容可以学："
            "第一块是图片场景活动，第二块是核心对话。"
            "你想先学哪一块？可以说“第一块”或“第二块”。"
        ),
        block=block,
        active_prompt="What did you do last weekend?",
        return_anchor=(
            "你刚才说了water，那是单词。"
            "你想先学第一块的图片场景，还是第二块的核心对话？"
        ),
        action_fields={
            "target_role": "question",
            "expected_student_action": "answer",
            "question_target": "What did you do last weekend?",
            "answer_target": "Yes, I did. We played football on Sunday.",
            "answer_frame": "I ... last weekend.",
            "action_source": "block_core_pattern",
            "preserve_page_uid": "TB-G6S2U2-P13",
            "preserve_block_uid": "TB-G6S2U2-P13-D2",
            "active_prompt": "What did you do last weekend?",
            "return_anchor": (
                "你刚才说了water，那是单词。"
                "你想先学第一块的图片场景，还是第二块的核心对话？"
            ),
            "target_phrase": "What did you do last weekend?",
        },
    )

    assert repaired is not None
    assert "What did you do last weekend?" in repaired
    assert "I ... last weekend." in repaired
    assert "第一块" not in repaired
    assert "第二块" not in repaired


def test_redirect_reply_policy_promotes_phrase_contract_to_question_frame():
    catalog = PilotLessonCatalog(manifest_path=_general_overlay_manifest_path())
    block = catalog.get_block("TB-G6S2U2-P13-D2")

    repaired = maybe_render_redirect_reply(
        learner_input="I stayed at home.",
        target_phrase="I cleaned my room and washed my clothes on Saturday.",
        teacher_reply=(
            "你刚才说的是 I stayed at home. "
            "你来读：I cleaned my room and washed my clothes on Saturday."
        ),
        block=block,
        active_prompt="What did you do last weekend?",
        return_anchor="I cleaned my room and washed my clothes on Saturday.",
        action_fields={
            "target_role": "phrase",
            "expected_student_action": "read",
            "question_target": "What did you do last weekend?",
            "answer_target": "Yes, I did. We played football on Sunday.",
            "answer_frame": "I ... last weekend.",
            "action_source": "block_core_pattern",
            "preserve_page_uid": "TB-G6S2U2-P13",
            "preserve_block_uid": "TB-G6S2U2-P13-D2",
            "active_prompt": "What did you do last weekend?",
            "return_anchor": "I cleaned my room and washed my clothes on Saturday.",
            "target_phrase": "I cleaned my room and washed my clothes on Saturday.",
        },
    )

    assert repaired is not None
    assert "What did you do last weekend?" in repaired
    assert "I ... last weekend." in repaired
    assert "I cleaned my room and washed my clothes" not in repaired
    assert "你来读" not in repaired


def test_g5s2_p6_grounded_page_vocabulary_question_does_not_fallback():
    def _teacher_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        parsed = json.loads(prompt)
        if parsed["turn_label"] == "ask_knowledge":
            return "它的意思是钟表。知道这个意思后，我们回到刚才的发音小任务。"
        return parsed["fallback"]

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        responder=LessonResponder(_teacher_llm),
        debug_signals_enabled=True,
    )

    start = runtime.start_page("TB-G5S2U1-P6", "student-1")
    result = runtime.handle_turn(start.state, "What does clock mean?")

    assert result.turn_label == "ask_knowledge"
    assert "钟表" in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "llm_repaired"
    assert (
        result.debug_signals.response_audit.repair_reason
        == "grounded_lexicon_required_phrase_repaired"
    )
    assert result.debug_signals.response_audit.fallback_used is False
    assert result.debug_signals.response_audit.fallback_reason == "none"


def test_g6s1_p9_vocabulary_question_returns_to_active_prompt_not_stale_page_choice():
    class _StaleKnowledgePlanner:
        def classify_open_turn(self, **kwargs):
            return kwargs["fallback"]

        def plan_knowledge_turn(self, **kwargs):
            fallback = kwargs["fallback"]
            return PlannerDecision(
                teaching_action="explain",
                retrieval_mode=fallback.retrieval_mode,
                return_anchor="你想先学哪一块？可以说 第一块、第二块 或 第三块。",
                response_focus="Answer the vocabulary question.",
            )

    def _teacher_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        parsed = json.loads(prompt)
        if parsed["turn_label"] == "ask_knowledge":
            return (
                "feature 在这里是“特点、功能”的意思。"
                "回到刚才的问题：What is Robin's new feature? "
                "你选 He can find food 还是 He can find the way?"
            )
        return parsed["fallback"]

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()),
        planner=_StaleKnowledgePlanner(),
        responder=LessonResponder(_teacher_llm),
        debug_signals_enabled=True,
    )
    start = runtime.start_page("TB-G6S1U1-P9", "student-1")
    state = start.state.model_copy(deep=True)
    state.current_activity_type = "teaching"
    state.awaiting_answer = True
    state.last_teacher_question = (
        "1. What is Robin's new feature? □ He can find food. □ He can find the way."
    )

    result = runtime.handle_turn(state, "What does feature mean?")

    assert result.turn_label == "ask_knowledge"
    assert "What is Robin's new feature?" in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "llm"
    assert result.debug_signals.response_audit.fallback_used is False
    assert result.debug_signals.response_audit.fallback_reason == "none"


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
    assert "Fill in the table." in result.teacher_response
    assert "基数词和序数词" not in result.teacher_response


def test_page_entry_try_talk_choice_starts_selected_module(tmp_path):
    manifest_path = _write_try_talk_module_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G5S1U1-P4", "student-1")

    result = runtime.handle_turn(start.state, "第二块")

    assert result.turn_label == "navigation"
    assert result.teaching_action == "probe"
    assert result.block_uid == "TB-G5S1U1-P4-D2"
    assert result.state.current_block_uid == "TB-G5S1U1-P4-D2"
    assert result.state.current_activity_type == "teaching"
    assert result.state.awaiting_answer is True
    assert "Let's talk" in result.teacher_response
    assert "Where is the museum shop?" in result.teacher_response
    assert "看对话抓关键句" not in result.teacher_response


def test_general_manifest_p49_keeps_source_order_and_fourth_module_choice():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")
    selected = runtime.handle_turn(start.state, "第四块")

    assert runtime.catalog.get_page("TB-G6S2Recycle2-P49").priority_blocks == [
        "TB-G6S2Recycle2-P49-D1",
        "TB-G6S2Recycle2-P49-D2",
        "TB-G6S2Recycle2-P49-D3",
        "TB-G6S2Recycle2-P49-D4",
    ]
    assert start.block_uid == "TB-G6S2Recycle2-P49-D1"
    assert start.state.current_block_uid == "TB-G6S2Recycle2-P49-D1"
    assert "第一块" in start.teacher_response
    assert "第四块" in start.teacher_response
    assert selected.turn_label == "navigation"
    assert selected.teaching_action == "probe"
    assert selected.block_uid == "TB-G6S2Recycle2-P49-D4"
    assert selected.state.current_block_uid == "TB-G6S2Recycle2-P49-D4"


def test_g5_unit3_pilot_priority_edges_follow_classroom_order():
    _assert_priority_edges_follow_classroom_order(PilotLessonCatalog())


def test_general_overlay_priority_edges_follow_classroom_order():
    _assert_priority_edges_follow_classroom_order(
        PilotLessonCatalog(manifest_path=_general_overlay_manifest_path())
    )


def test_answer_turn_policy_keeps_plain_p49_task_answer_on_current_block():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")
    selected = runtime.handle_turn(start.state, "第四块")
    block = runtime.catalog.get_block(selected.state.current_block_uid)

    plain_frame = runtime._build_answer_turn_policy_frame(
        block=block,
        state=selected.state,
        learner_input="climb",
    )
    explicit_frame = runtime._build_answer_turn_policy_frame(
        block=block,
        state=selected.state,
        learner_input="我想学第二块",
    )

    assert plain_frame["allowedstatewrites"]["currentblockuids"] == [
        "TB-G6S2Recycle2-P49-D4"
    ]
    assert set(explicit_frame["allowedstatewrites"]["currentblockuids"]) == {
        "TB-G6S2Recycle2-P49-D1",
        "TB-G6S2Recycle2-P49-D2",
        "TB-G6S2Recycle2-P49-D3",
        "TB-G6S2Recycle2-P49-D4",
    }


def test_answer_turn_policy_frame_allows_matching_later_p24_drink_block():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    selected = runtime.handle_turn(start.state, "第一块")
    block = runtime.catalog.get_block(selected.state.current_block_uid)

    frame = runtime._build_answer_turn_policy_frame(
        block=block,
        state=selected.state,
        learner_input="I'd like some water.",
    )

    assert frame["allowedstatewrites"]["currentblockuids"] == [
        "TB-G5S1U3-P24-D2",
        "TB-G5S1U3-P24-D3",
        "TB-G5S1U3-P24-D4",
    ]
    matches = {
        item["blockuid"]: item["matches"]
        for item in frame["learnerinputmatches"]
    }
    assert matches["TB-G5S1U3-P24-D2"]
    assert matches["TB-G5S1U3-P24-D4"]


def test_answer_turn_policy_runtime_state_view_preserves_allowed_writes():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")
    selected = runtime.handle_turn(start.state, "第四块")
    block = runtime.catalog.get_block(selected.state.current_block_uid)
    frame = runtime._build_answer_turn_policy_frame(
        block=block,
        state=selected.state,
        learner_input="climb",
    )

    view = runtime._answer_turn_policy_runtime_state_view(frame=frame)

    assert set(view) == {
        "teacherasked",
        "currentblockuid",
        "allowedcurrentblockuids",
        "currentblockcanstay",
        "canwriteotherblocks",
        "matchedblockuids",
        "matchedblockfields",
        "activequestionkind",
        "currentblockscope",
        "hasmultiplecurrenttargets",
        "samepageblockroles",
    }
    assert view["currentblockuid"] == frame["currentblock"]["blockuid"]
    assert view["allowedcurrentblockuids"] == frame["allowedstatewrites"][
        "currentblockuids"
    ]
    assert view["currentblockcanstay"] is True
    assert view["canwriteotherblocks"] is False
    assert _compact_json_bytes(view) < _legacy_answer_policy_runtime_state_bytes(frame)


def test_answer_turn_policy_prompt_uses_minimal_runtime_state_by_default(monkeypatch):
    monkeypatch.delenv("PEPTUTOR_ANSWER_TURN_MINIMAL_RUNTIME_STATE", raising=False)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")
    selected = runtime.handle_turn(start.state, "第四块")
    block = runtime.catalog.get_block(selected.state.current_block_uid)
    frame = runtime._build_answer_turn_policy_frame(
        block=block,
        state=selected.state,
        learner_input="climb",
    )

    payload = json.loads(runtime._build_answer_turn_policy_prompt(frame=frame))
    prompt_frame = payload["frame"]

    assert payload["minimal_runtime_state_prompt_enabled"] is True
    assert prompt_frame["runtimestate"] == (
        runtime._answer_turn_policy_runtime_state_view(frame=frame)
    )
    for key in (
        "taskboundary",
        "recentdialogue",
        "allowedstatewrites",
        "learnerinputmatches",
    ):
        assert key not in prompt_frame
    assert payload["required_output_schema"] == {
        "teacherreply": "<final teacher speech>",
        "statepatch": {
            "currentblockuid": "<one of frame.allowedstatewrites.currentblockuids>",
            "awaitinganswer": "<boolean>",
            "lastteacherquestion": (
                "<teacher's current question for the next student reply, or null>"
            ),
        },
    }
    assert payload["instructions"] == list(ANSWER_TURN_POLICY_RUBRIC_V1)
    assert _compact_json_bytes(prompt_frame["runtimestate"]) < (
        _legacy_answer_policy_runtime_state_bytes(frame)
    )


def test_answer_turn_policy_prompt_can_disable_minimal_runtime_state(monkeypatch):
    monkeypatch.setenv("PEPTUTOR_ANSWER_TURN_MINIMAL_RUNTIME_STATE", "0")
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")
    selected = runtime.handle_turn(start.state, "第四块")
    block = runtime.catalog.get_block(selected.state.current_block_uid)
    frame = runtime._build_answer_turn_policy_frame(
        block=block,
        state=selected.state,
        learner_input="climb",
    )

    payload = json.loads(runtime._build_answer_turn_policy_prompt(frame=frame))

    assert "minimal_runtime_state_prompt_enabled" not in payload
    assert "runtimestate" not in payload["frame"]
    for key in (
        "taskboundary",
        "recentdialogue",
        "allowedstatewrites",
        "learnerinputmatches",
    ):
        assert key in payload["frame"]
    assert payload["instructions"] == list(ANSWER_TURN_POLICY_RUBRIC_V1)


def test_answer_turn_policy_prompt_uses_minimal_runtime_state_when_enabled(
    monkeypatch,
):
    monkeypatch.setenv("PEPTUTOR_ANSWER_TURN_MINIMAL_RUNTIME_STATE", "1")
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")
    selected = runtime.handle_turn(start.state, "第四块")
    block = runtime.catalog.get_block(selected.state.current_block_uid)
    frame = runtime._build_answer_turn_policy_frame(
        block=block,
        state=selected.state,
        learner_input="climb",
    )

    payload = json.loads(runtime._build_answer_turn_policy_prompt(frame=frame))
    prompt_frame = payload["frame"]

    assert payload["minimal_runtime_state_prompt_enabled"] is True
    assert prompt_frame["runtimestate"] == (
        runtime._answer_turn_policy_runtime_state_view(frame=frame)
    )
    for key in (
        "taskboundary",
        "recentdialogue",
        "allowedstatewrites",
        "learnerinputmatches",
    ):
        assert key not in prompt_frame
    assert set(prompt_frame["runtimestate"]) == {
        "teacherasked",
        "currentblockuid",
        "allowedcurrentblockuids",
        "currentblockcanstay",
        "canwriteotherblocks",
        "matchedblockuids",
        "matchedblockfields",
        "activequestionkind",
        "currentblockscope",
        "hasmultiplecurrenttargets",
        "samepageblockroles",
    }
    assert payload["required_output_schema"] == {
        "teacherreply": "<final teacher speech>",
        "statepatch": {
            "currentblockuid": "<one of frame.allowedstatewrites.currentblockuids>",
            "awaitinganswer": "<boolean>",
            "lastteacherquestion": (
                "<teacher's current question for the next student reply, or null>"
            ),
        },
    }
    assert payload["instructions"] == list(ANSWER_TURN_POLICY_RUBRIC_V1)
    assert _compact_json_bytes(prompt_frame["runtimestate"]) < (
        _legacy_answer_policy_runtime_state_bytes(frame)
    )


def test_answer_turn_policy_runtime_state_view_preserves_p24_food_drink_boundary():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    selected = runtime.handle_turn(start.state, "第一块")
    block = runtime.catalog.get_block(selected.state.current_block_uid)
    frame = runtime._build_answer_turn_policy_frame(
        block=block,
        state=selected.state,
        learner_input="I'd like some water.",
    )

    view = runtime._answer_turn_policy_runtime_state_view(frame=frame)

    assert view["allowedcurrentblockuids"] == [
        "TB-G5S1U3-P24-D2",
        "TB-G5S1U3-P24-D3",
        "TB-G5S1U3-P24-D4",
    ]
    assert view["currentblockcanstay"] is True
    assert view["canwriteotherblocks"] is True
    assert view["matchedblockuids"] == [
        "TB-G5S1U3-P24-D2",
        "TB-G5S1U3-P24-D4",
    ]
    assert any(
        "I'd like some water." in value
        for value in view["matchedblockfields"]["TB-G5S1U3-P24-D2"]
    )
    assert any(role["relation"] == "current" for role in view["samepageblockroles"])
    assert any(role["relation"] == "next" for role in view["samepageblockroles"])
    assert _compact_json_bytes(view) < _legacy_answer_policy_runtime_state_bytes(frame)


def test_answer_turn_policy_runtime_state_view_preserves_p13_vocab_return_boundary():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))
    start = runtime.start_page("TB-G6S2U2-P13", "student-1")
    block = runtime.catalog.get_block(start.state.current_block_uid)
    frame = runtime._build_answer_turn_policy_frame(
        block=block,
        state=start.state,
        learner_input="had a cold是什么意思",
    )

    view = runtime._answer_turn_policy_runtime_state_view(frame=frame)

    assert view["teacherasked"] == frame["teacherasked"]
    assert view["currentblockuid"] == "TB-G6S2U2-P13-D2"
    assert view["allowedcurrentblockuids"] == ["TB-G6S2U2-P13-D2"]
    assert view["currentblockcanstay"] is True
    assert view["canwriteotherblocks"] is False
    assert view["activequestionkind"] == frame["taskboundary"]["activequestionkind"]
    assert view["currentblockscope"] == frame["taskboundary"]["currentblockscope"]
    assert _compact_json_bytes(view) < _legacy_answer_policy_runtime_state_bytes(frame)


def test_answer_turn_policy_runtime_state_view_preserves_g6s1_p4_question_boundary():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))
    state = runtime.start_page("TB-G6S1U1-P4", "student-1").state.model_copy(
        deep=True
    )
    state.current_block_uid = "TB-G6S1U1-P4-D2"
    state.last_teacher_question = "Where is the museum shop?"
    block = runtime.catalog.get_block("TB-G6S1U1-P4-D2")
    frame = runtime._build_answer_turn_policy_frame(
        block=block,
        state=state,
        learner_input="turn left",
    )

    view = runtime._answer_turn_policy_runtime_state_view(frame=frame)

    assert view["teacherasked"] == "Where is the museum shop?"
    assert view["currentblockuid"] == "TB-G6S1U1-P4-D2"
    assert view["allowedcurrentblockuids"] == [
        "TB-G6S1U1-P4-D2",
        "TB-G6S1U1-P4-D3",
    ]
    assert view["currentblockcanstay"] is True
    assert view["canwriteotherblocks"] is True
    assert _compact_json_bytes(view) < _legacy_answer_policy_runtime_state_bytes(frame)


def test_answer_turn_policy_runtime_state_view_preserves_g6s2_p4_height_boundary():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))
    state = runtime.start_page("TB-G6S2U1-P4", "student-1").state.model_copy(
        deep=True
    )
    state.current_block_uid = "TB-G6S2U1-P4-D2"
    state.last_teacher_question = "How tall is it?"
    block = runtime.catalog.get_block("TB-G6S2U1-P4-D2")
    frame = runtime._build_answer_turn_policy_frame(
        block=block,
        state=state,
        learner_input="How tall are you?",
    )

    view = runtime._answer_turn_policy_runtime_state_view(frame=frame)
    fields = runtime._answer_turn_policy_redirect_action_fields(
        block=block,
        learner_input="How tall are you?",
        target_phrase="How tall is it?",
        active_prompt="How tall is it?",
        return_anchor="How tall is it?",
    )

    assert view["teacherasked"] == "How tall is it?"
    assert view["currentblockuid"] == "TB-G6S2U1-P4-D2"
    assert view["allowedcurrentblockuids"] == [
        "TB-G6S2U1-P4-D2",
        "TB-G6S2U1-P4-D1",
        "TB-G6S2U1-P4-D4",
    ]
    assert view["currentblockcanstay"] is True
    assert view["canwriteotherblocks"] is True
    assert fields["question_target"] == "How tall is it?"
    assert fields["answer_frame"] == "It's ... metres tall."
    assert _compact_json_bytes(view) < _legacy_answer_policy_runtime_state_bytes(frame)


def test_answer_turn_policy_frame_marks_same_page_phonics_word_match():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))
    start = runtime.start_page("TB-G5S2U1-P6", "student-1")
    block = runtime.catalog.get_block(start.state.current_block_uid)

    frame = runtime._build_answer_turn_policy_frame(
        block=block,
        state=start.state,
        learner_input="please",
    )

    assert frame["allowedstatewrites"]["currentblockuids"] == [
        "TB-G5S2U1-P6-D2",
        "TB-G5S2U1-P6-D1",
    ]
    matches = {
        item["blockuid"]: item["matches"]
        for item in frame["learnerinputmatches"]
    }
    assert matches["TB-G5S2U1-P6-D1"] == [
        {"field": "vocabulary", "text": "please"}
    ]


def test_answer_turn_policy_runtime_state_view_preserves_p6_phonics_match():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_overlay_manifest_path()))
    start = runtime.start_page("TB-G5S2U1-P6", "student-1")
    block = runtime.catalog.get_block(start.state.current_block_uid)
    frame = runtime._build_answer_turn_policy_frame(
        block=block,
        state=start.state,
        learner_input="please",
    )

    view = runtime._answer_turn_policy_runtime_state_view(frame=frame)

    assert view["allowedcurrentblockuids"] == [
        "TB-G5S2U1-P6-D2",
        "TB-G5S2U1-P6-D1",
    ]
    assert view["matchedblockuids"] == ["TB-G5S2U1-P6-D1"]
    assert view["matchedblockfields"]["TB-G5S2U1-P6-D1"] == [
        "vocabulary:please"
    ]
    assert view["currentblockcanstay"] is True
    assert view["canwriteotherblocks"] is True
    assert _compact_json_bytes(view) < _legacy_answer_policy_runtime_state_bytes(frame)


def test_module_choice_responder_generic_praise_uses_deterministic_repair(tmp_path):
    manifest_path = _write_try_talk_module_pilot(tmp_path)
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(lambda *args, **kwargs: "好，这句说得对！我们进入第二块。"),
        debug_signals_enabled=True,
    )
    start = runtime.start_page("TB-G5S1U1-P4", "student-1")

    result = runtime.handle_turn(start.state, "第二块")

    assert "这句说得对" not in result.teacher_response
    assert "Let's talk" in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "llm_repaired"
    assert (
        result.debug_signals.response_audit.repair_reason
        == "generic_praise_deterministic_repair"
    )
    assert result.debug_signals.response_audit.fallback_used is False
    assert result.debug_signals.response_audit.fallback_reason == "none"


def test_module_choice_responder_strips_generic_praise_when_reply_has_anchor(
    tmp_path,
):
    manifest_path = _write_try_talk_module_pilot(tmp_path)
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(
            lambda *args, **kwargs: (
                "很棒！我们先从 Let's talk 开始。"
                "先听 What would you like to drink?，你试着用 I'd like water. 回答。"
            )
        ),
        debug_signals_enabled=True,
    )
    start = runtime.start_page("TB-G5S1U1-P4", "student-1")

    result = runtime.handle_turn(start.state, "第二块")

    assert "很棒" not in result.teacher_response
    assert "Let's talk" in result.teacher_response
    assert "I'd like water" in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "llm_repaired"
    assert (
        result.debug_signals.response_audit.repair_reason
        == "generic_praise_stripped"
    )
    assert result.debug_signals.response_audit.fallback_used is False
    assert result.debug_signals.response_audit.fallback_reason == "none"


def test_module_choice_responder_strips_inline_specific_generic_praise(tmp_path):
    manifest_path = _write_try_talk_module_pilot(tmp_path)
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(
            lambda *args, **kwargs: (
                "你选了 Let's talk，说得对；"
                "你刚才的句子非常正确。"
                "现在听 What would you like to drink?，再说 I'd like water."
            )
        ),
        debug_signals_enabled=True,
    )
    start = runtime.start_page("TB-G5S1U1-P4", "student-1")

    result = runtime.handle_turn(start.state, "第二块")

    assert "说得对" not in result.teacher_response
    assert "非常正确" not in result.teacher_response
    assert "你选了 Let's talk" in result.teacher_response
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.source == "llm_repaired"
    assert (
        result.debug_signals.response_audit.repair_reason
        == "generic_praise_stripped"
    )
    assert result.debug_signals.response_audit.fallback_used is False


def test_responder_repair_keeps_learner_phrase_when_next_step_is_concrete():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "你说 I'd like some water，说得很好。"
                "现在练饮料，选一句用英语回答。"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="现在你口渴了，跟老师选一句说：I'd like water. 或 I'd like some tea.",
        learner_input="I'd like some water.",
    )

    assert "说得很好" not in result.text
    assert "I'd like some water" in result.text
    assert "选一句用英语回答" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_stripped"
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_repair_strips_clear_but_generic_correctness_praise():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好！你说得很清楚——\"I'd like some water.\"，"
                "这个回答完全正确，这个句子很好，很标准。"
                "那现在我们继续，老师来问你：What would you like to drink? "
                "你口渴了，想喝什么？选一句说吧：I'd like water. 或者 I'd like some tea."
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="现在你口渴了，跟老师选一句说：I'd like water. 或 I'd like some tea.",
        learner_input="I'd like some water.",
    )

    assert "说得很清楚" not in result.text
    assert "完全正确" not in result.text
    assert "句子很好" not in result.text
    assert "很标准" not in result.text
    assert "What would you like to drink?" in result.text
    assert "I'd like water" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "generic_praise_stripped"
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_pacing_uses_compact_module_choice_fallback():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "你刚才说想打篮球，我也喜欢运动！不过现在我们来先完成页面上的任务，好吗？"
                "你看，这一页讲的是张鹏和西班牙小朋友佩德罗的学校作息时间。"
                "页面有两个选项：Let's talk（看对话，练短句）或 Let's try（听录音抓信息）。"
                "你选哪个先学？可以说 Let's talk 或者 Let's try."
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        turn_label="navigation",
        fallback_response=(
            "我先把选择说清楚：可以选 Let's talk 或 Let's try。你想先学哪一块？"
        ),
        learner_input="I want to play basketball.",
    )

    assert result.text == "我先把选择说清楚：可以选 Let's talk 或 Let's try。你想先学哪一块？"
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "classroom_pacing"
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_page_entry_phrasing_repair_preserves_module_choice():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    fallback_response = (
        "这一页有 2 块：Let's talk：看对话抓关键句。"
        "Let's try：听录音抓关键信息。"
        "你想先学哪一块？可以说 Let's talk 或 Let's try。"
    )
    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "我们把目标句放小：Let's talk."
                "先听，再说：Let's talk."
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        turn_label="page_entry",
        fallback_response=fallback_response,
        learner_input="",
    )

    assert result.text == fallback_response
    assert "跟我读：Let's talk" not in result.text
    assert "你想先学哪一块" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "page_entry_module_choice_repaired"
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_repairs_broken_id_like_answer_frame():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "你说了一句 I'd like some water.——想喝水。"
                "不过这一块我们先用食物来练习。"
                "老师问你：What would you like to eat?（你想吃什么？）"
                "你来回答，用 I'd like. 开头，"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        turn_label="navigation",
        fallback_response="现在先回答：What would you like to eat? 可以用 I'd like ... 开头。",
        learner_input="I'd like some water.",
    )

    assert "I'd like. 开头" not in result.text
    assert "I'd like ..." in result.text
    assert "What would you like to eat?" in result.text
    assert "I'd like some water." in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "classroom_phrasing"
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_compacts_overloaded_lexicon_return():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "哦，问得好！Because 就是“因为”的意思。"
                "你看我们正在读的这句："
                "I like spring because there are beautiful flowers everywhere. "
                "—— 我喜欢春天，因为到处都有漂亮的花。"
                "所以 because 后面跟着的就是原因。"
                "现在我们再试着一起读一遍这句好吗？"
                "来，跟我读：I like spring because there are beautiful flowers everywhere."
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        turn_label="ask_knowledge",
        fallback_response="because 是“因为”。现在回到刚才这句：I like spring because there are beautiful flowers everywhere.",
        learner_input="What does because mean?",
    )

    assert "问得好" not in result.text
    assert "because" in result.text.casefold()
    assert "因为" in result.text
    assert "I like spring because there are beautiful flowers everywhere." in result.text
    assert "跟我读" not in result.text
    assert not runtime._teacher_reply_looks_overloaded(
        result.text,
        turn_label="ask_knowledge",
    )
    assert result.audit.source == "llm_repaired"
    assert "classroom_pacing" in result.audit.repair_reason
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_strips_embedded_question_praise_from_lexicon_reply():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "哎呀，这个问题问得好。Because就是“因为”的意思。"
                "你看，课文里有句话："
                "I like spring because there are beautiful flowers everywhere. "
                "那米粒再问你一次：你知道spring这个单词是什么意思吗？"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="rag_plus_llm",
        turn_label="ask_knowledge",
        fallback_response=(
            "Because... 是“因为...”。这个点在本单元里还能连到这句："
            "Because I like summer vacation! 现在先回到刚才这句："
            "你知道spring这个单词是什么意思吗？"
        ),
        learner_input="What does because mean?",
    )

    assert "问得好" not in result.text
    assert "Because" in result.text
    assert "因为" in result.text
    assert result.audit.source == "llm_repaired"
    assert "generic_praise_stripped" in result.audit.repair_reason
    assert result.audit.fallback_used is False


def test_responder_strips_haowenti_and_wendehenbang_from_lexicon_reply():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                '好问题！"must"就是"必须"的意思。'
                "比如过马路的时候，我们看见红灯要说："
                "We must stop and wait. "
                "你刚才问得很棒，现在回到课堂任务。"
                "你想先学哪一块？可以说 第一块、第二块、第三块 或 第四块。"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="rag_plus_llm",
        turn_label="ask_knowledge",
        fallback_response=(
            'must 是“必须”。例如：We must stop and wait. '
            "回到刚才的小任务：你想先学哪一块？"
        ),
        learner_input="What does must mean?",
    )

    assert "好问题" not in result.text
    assert "问得很棒" not in result.text
    assert "must" in result.text
    assert "必须" in result.text
    assert "We must stop and wait." in result.text
    assert "你想先学哪一块" in result.text
    assert result.audit.source == "llm_repaired"
    assert "generic_praise_stripped" in result.audit.repair_reason
    assert result.audit.fallback_used is False


def test_responder_strips_you_asked_well_from_short_lexicon_reply():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "cow 是“奶牛”的意思。你问得好！"
                "这个单词我们正在学，它有个特别的发音：ow 在这里发 /aʊ/。"
                "来，先跟老师读一读：cow。"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="rag_plus_llm",
        turn_label="ask_knowledge",
        fallback_response="cow 是“奶牛”。现在回到刚才这句：先跟老师读一读：cow。",
        learner_input="What does cow mean?",
    )

    assert "问得好" not in result.text
    assert "cow 是“奶牛”" in result.text
    assert "/aʊ/" in result.text
    assert result.audit.source == "llm_repaired"
    assert "generic_praise_stripped" in result.audit.repair_reason
    assert result.audit.fallback_used is False


def test_responder_strips_wave_punctuated_generic_praise_from_lexicon_reply():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "嗯，stay at home 就是留在家里、没有出门的意思。"
                "你说对了～我们回到刚才的任务：老师问你，"
                "What did you do last weekend？你周末做了什么呀？"
                "你可以用完整的句子回答我。"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="rag_plus_llm",
        turn_label="ask_knowledge",
        fallback_response=(
            "stayed at home 是“呆在家里”。"
            "回到刚才的小任务：What did you do last weekend?"
        ),
        learner_input="What does stayed at home mean?",
    )

    assert "你说对了" not in result.text
    assert "stay at home" in result.text
    assert "留在家里" in result.text
    assert "What did you do last weekend" in result.text
    assert result.audit.source == "llm_repaired"
    assert "generic_praise_stripped" in result.audit.repair_reason
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_uses_tighter_fallback_for_overloaded_navigation_reply():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    fallback_response = (
        "好，我们先从第二块开始。先听服务员的问题："
        "What would you like to eat? 你可以回答：I'd like chicken and bread."
    )
    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好，我们开始第二块。在餐厅里，服务员会问你："
                "What would you like to eat? （你想吃什么？） "
                "现在你来当顾客，试试用 I'd like ... 来回答。"
                "先跟我说这盘菜：chicken and bread. "
                "跟我说：I'd like chicken and bread."
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        turn_label="navigation",
        fallback_response=fallback_response,
        learner_input="我想学第二块",
    )

    assert result.text == fallback_response
    assert not runtime._teacher_reply_looks_overloaded(
        result.text,
        turn_label="navigation",
    )
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "classroom_pacing"
    assert result.audit.fallback_used is False


def test_responder_compacts_navigation_reply_that_re_lists_page_modules():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    fallback_response = (
        "我们先回到这一页，选一个入口：第一块、第二块、第三块 或 第四块。"
    )
    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好，pizza很好吃。那我们先回到这一页的任务。"
                "这一课我们要学两个不同的 ow 发音。"
                "这一页有四块内容。"
                "第一块：学 ow 的两个发音，像 cow 和 snow。"
                "第二块：听音找出不同的 ow 发音。"
                "第三块：听音填词，比如 flower，down。"
                "第四块：写一个短句子。"
                "你想先做哪一块？"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        turn_label="navigation",
        fallback_response=fallback_response,
        learner_input="pizza",
    )

    assert result.text == fallback_response
    assert "很好" not in result.text
    assert "第一块：" not in result.text
    assert not runtime._teacher_reply_looks_overloaded(
        result.text,
        turn_label="navigation",
    )
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "classroom_pacing"
    assert result.audit.fallback_used is False


def test_responder_repair_strips_clear_praise_before_quoted_learner_phrase():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好，你说得很清楚：“I'd like some water.” 听。"
                "现在老师来问你一个问题，你听听看："
                "What would you like to drink? ——意思是“你想喝什么？”"
                "你可以说 I'd like water. 或者 I'd like some tea."
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="现在你口渴了，跟老师选一句说：I'd like water. 或 I'd like some tea.",
        learner_input="I'd like some water.",
    )

    assert "说得很清楚" not in result.text
    assert "I'd like some water" in result.text
    assert "What would you like to drink?" in result.text
    assert "I'd like water" in result.text
    assert result.audit.source == "llm_repaired"
    assert "generic_praise_stripped" in result.audit.repair_reason
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_repair_strips_completely_correct_sentence_praise():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好，这句说得完全正确！\"I'd like some water.\"——很标准。"
                "现在老师来问你，What would you like to drink? "
                "你口渴了，想喝什么？选一句跟我说："
                "I'd like water. 或者 I'd like some tea."
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="现在你口渴了，跟老师选一句说：I'd like water. 或 I'd like some tea.",
        learner_input="I'd like some water.",
    )

    assert "说得完全正确" not in result.text
    assert "很标准" not in result.text
    assert "I'd like some water" in result.text
    assert "What would you like to drink?" in result.text
    assert result.audit.source == "llm_repaired"
    assert "generic_praise_stripped" in result.audit.repair_reason
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_repair_strips_sentence_correctness_from_real_navigation_sample():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好，很好！你说了\"I'd like some water.\"，这句话完全正确。"
                "那我们接着练习：你听到服务员问\"What would you like to drink?\"，"
                "你已经会回答了。现在我们换一种饮料试试——你可以说\"I'd like some tea.\"。"
                "来，跟着老师说一遍：I'd like some tea."
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="现在你口渴了，跟老师选一句说：I'd like water. 或 I'd like some tea.",
        learner_input="I'd like some water.",
    )

    assert "很好" not in result.text
    assert "完全正确" not in result.text
    assert "What would you like to drink?" in result.text
    assert "I'd like some tea" in result.text
    assert result.audit.source == "llm_repaired"
    assert "generic_praise_stripped" in result.audit.repair_reason
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_repair_strips_clear_and_answered_right_from_real_navigation_sample():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好的，你说想要一些水，非常清楚！听老师问一句： "
                "What would you like to drink?（你想喝什么？） "
                "你刚才答得对，可以说 I'd like water. 或者 I'd like some tea. "
                "那现在老师再问你一次，你来选一句回答： "
                "What would you like to drink?"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="现在你口渴了，跟老师选一句说：I'd like water. 或 I'd like some tea.",
        learner_input="I'd like some water.",
    )

    assert "非常清楚" not in result.text
    assert "答得对" not in result.text
    assert "What would you like to drink?" in result.text
    assert "I'd like water" in result.text
    assert result.audit.source == "llm_repaired"
    assert "generic_praise_stripped" in result.audit.repair_reason
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_repair_strips_teacher_heard_clear_from_real_navigation_sample():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好！你说了 I'd like some water.，这个回答完全正确，"
                "老师听得很清楚。 现在老师是服务员，我来问你一句："
                "What would you like to drink?（你想喝什么？） "
                "你选一句来回答就好： - I'd like water. - I'd like some tea."
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="现在你口渴了，跟老师选一句说：I'd like water. 或 I'd like some tea.",
        learner_input="I'd like some water.",
    )

    assert "完全正确" not in result.text
    assert "听得很清楚" not in result.text
    assert "What would you like to drink?" in result.text
    assert "I'd like some tea" in result.text
    assert result.audit.source == "llm_repaired"
    assert "generic_praise_stripped" in result.audit.repair_reason
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_repair_strips_very_good_praise_without_orphan_colon():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "你说得很棒：I'd like some water. 非常棒！"
                "现在我问你：What would you like to drink? "
                "你可以说 I'd like water. 或者 I'd like some tea."
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="现在你口渴了，跟老师选一句说：I'd like water. 或 I'd like some tea.",
        learner_input="I'd like some water.",
    )

    assert "说得很棒" not in result.text
    assert "非常棒" not in result.text
    assert result.text.startswith("I'd like some water.")
    assert "What would you like to drink?" in result.text
    assert result.audit.source == "llm_repaired"
    assert "generic_praise_stripped" in result.audit.repair_reason
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_repair_normalizes_english_phrase_sentence_punctuation():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "你说得很棒：I'd like some water。非常棒！"
                "你已经会回答想喝什么了。"
                "现在老师问你：What would you like to drink?"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="现在你口渴了，跟老师选一句说：I'd like water. 或 I'd like some tea.",
        learner_input="I'd like some water.",
    )

    assert "非常棒" not in result.text
    assert "water。" not in result.text
    assert "I'd like some water. 你已经" in result.text
    assert result.audit.source == "llm_repaired"
    assert "generic_praise_stripped" in result.audit.repair_reason
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_repair_strips_you_are_right_before_specific_phonics_step():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好，你说对了。cow 用的是 cow 的 /aʊ/ 音。"
                "那你知道 snow 用的是哪个音吗？雪的那个 ow 怎么读？"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="先读 cow，再看 snow 里的 ow 怎么读。",
        learner_input="cow",
    )

    assert "说对了" not in result.text
    assert "cow" in result.text
    assert "snow" in result.text
    assert result.audit.source == "llm_repaired"
    assert "generic_praise_stripped" in result.audit.repair_reason
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_repair_keeps_concrete_phonics_step_without_fallback_anchor():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好，你说对了。cow 用的是 cow sound，像 /aʊ/。"
                "那我们来看第一块，第一个重点：ow 有两种发音。"
                "第一种像 cow，读 /aʊ/；第二种像 snow，读 /oʊ/。"
                "来，先跟老师读两个词：cow — /aʊ/ snow — /oʊ/。"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        fallback_response="先看这个发音点，跟老师读一遍。",
        learner_input="第一块",
    )

    assert "说对了" not in result.text
    assert "cow" in result.text
    assert "snow" in result.text
    assert result.audit.source == "llm_repaired"
    assert "generic_praise_stripped" in result.audit.repair_reason
    assert result.audit.fallback_used is False
    assert result.audit.fallback_reason == "none"


def test_responder_repairs_phonics_tautology_from_navigation_sample():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "好，你说 第一块 —— 我们开始学 ow 的两种声音。"
                "听老师读：cow — /aʊ/，像牛叫的声音。"
                "现在你试试，跟我说：cow 用的是 cow sound。"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="llm_only",
        turn_label="navigation",
        fallback_response="好，我们从第一块开始。先跟老师读一读：cow。",
        learner_input="第一块",
    )

    assert "cow sound" not in result.text
    assert "cow uses the cow sound" not in result.text
    assert "cow 里的 ow 读 /aʊ/" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "phonics_tautology_repaired"
    assert result.audit.fallback_used is False


def test_responder_repairs_phonics_tautology_from_lexicon_sample():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))

    result = runtime._teacher_response_result_from_responder(
        LessonResponderTurnResult(
            text=(
                "哦，你问cow是什么意思呀？cow是“奶牛”。"
                "不过现在我们在学发音——cow这个词里面，ow发的是/aʊ/的音。"
                "记住了吗？cow uses the cow sound。先跟老师读一读：cow。"
            ),
            source="llm",
            llm_called=True,
            llm_provider="test",
            latency_ms=12,
            fallback_used=False,
            fallback_reason="none",
        ),
        route="rag_plus_llm",
        turn_label="ask_knowledge",
        fallback_response="cow 是“奶牛”。现在回到刚才这句：先跟老师读一读：cow。",
        learner_input="What does cow mean?",
    )

    assert "cow uses the cow sound" not in result.text
    assert "cow sound" not in result.text
    assert "cow是“奶牛”" in result.text
    assert "cow 里的 ow 读 /aʊ/" in result.text
    assert result.audit.source == "llm_repaired"
    assert result.audit.repair_reason == "phonics_tautology_repaired"
    assert result.audit.fallback_used is False


def test_answer_turn_policy_repairs_phonics_tautology_without_losing_prompt():
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=_general_manifest_path()))
    policy = AnswerTurnPolicyOutput(
        teacherreply=(
            "你读的是snow。老师问的是cow。"
            "cow里的ow是cow sound，snow里的ow是snow sound。"
            "请你再试一次，读cow。"
        ),
        statepatch=AnswerTurnPolicyStatePatch(
            currentblockuid="TB-G5S1U3-P26-D1",
            awaitinganswer=True,
            lastteacherquestion="Can you read cow?",
        ),
    )
    frame = {
        "studentsaid": "snow",
        "teacherasked": "Can you read cow?",
        "currentblock": {"blockuid": "TB-G5S1U3-P26-D1"},
    }

    repaired, status = runtime._maybe_repair_answer_turn_policy_phonics_tautology(
        policy=policy,
        frame=frame,
        learner_input="snow",
    )

    assert status == "applied"
    assert "cow sound" not in repaired.teacherreply
    assert "snow sound" not in repaired.teacherreply
    assert "cow 里的 ow 读 /aʊ/" in repaired.teacherreply
    assert "snow 里的 ow 读 /oʊ/" in repaired.teacherreply
    assert "读cow" in repaired.teacherreply


def test_module_choice_understands_chinese_selection_phrase(tmp_path):
    manifest_path = _write_multi_module_review_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G5S2U9-P12", "student-1")

    result = runtime.handle_turn(start.state, "我想学 Let's check")

    assert result.turn_label == "navigation"
    assert result.teaching_action == "probe"
    assert result.block_uid == "TB-G5S2U9-P12-D1"
    assert result.state.current_activity_type == "teaching"
    assert "Let's check" in result.teacher_response


def test_module_choice_switches_modules_before_answer_evaluation(tmp_path):
    manifest_path = _write_multi_module_review_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G5S2U9-P12", "student-1")
    selected = runtime.handle_turn(start.state, "Let's check")

    result = runtime.handle_turn(selected.state, "换一个")

    assert result.turn_label == "navigation"
    assert result.teaching_action == "probe"
    assert result.evaluation == "acceptable"
    assert result.block_uid == "TB-G5S2U9-P12-D3"
    assert result.state.current_block_uid == "TB-G5S2U9-P12-D3"
    assert "Let's wrap it up" in result.teacher_response


def test_module_choice_next_moves_to_next_page_module(tmp_path):
    manifest_path = _write_multi_module_review_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G5S2U9-P12", "student-1")
    selected = runtime.handle_turn(start.state, "Let's check")

    result = runtime.handle_turn(selected.state, "下一个")

    assert result.turn_label == "navigation"
    assert result.teaching_action == "probe"
    assert result.block_uid == "TB-G5S2U9-P12-D3"
    assert "Let's wrap it up" in result.teacher_response


def test_module_choice_does_not_treat_plain_numeric_answer_as_module_choice(tmp_path):
    manifest_path = _write_multi_module_review_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G5S2U9-P12", "student-1")
    selected = runtime.handle_turn(start.state, "Let's check")

    result = runtime.handle_turn(selected.state, "2")

    assert result.turn_label == "answer_question"
    assert result.teaching_action == "confirm"
    assert result.block_uid == "TB-G5S2U9-P12-D2"
    assert result.state.current_block_uid == "TB-G5S2U9-P12-D2"


def test_single_block_page_rejects_unavailable_module_navigation(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G5S1U3-P25", "student-1")

    result = runtime.handle_turn(start.state, "我想学第二块")

    assert result.turn_label == "navigation"
    assert result.teaching_action == "redirect"
    assert result.retrieval_mode == "none"
    assert result.block_uid == "TB-G5S1U3-P25-D1"
    assert result.state.current_block_uid == "TB-G5S1U3-P25-D1"
    assert result.state.awaiting_answer is True
    assert "这一页只有这一块" in result.teacher_response
    assert "第二块" not in result.teacher_response
    assert "转到第二块" not in result.teacher_response


def test_single_block_guard_plans_structural_move_without_changing_reply(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    planned_moves: list[dict[str, object]] = []

    class CapturingTeachingMovePlanner(TeachingMovePlanner):
        def plan_single_block_guard(self, *, learner_input: str):
            move = super().plan_single_block_guard(learner_input=learner_input)
            planned_moves.append(move.to_prompt_payload())
            return move

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        teaching_move_planner=CapturingTeachingMovePlanner(),
        debug_signals_enabled=True,
    )
    start = runtime.start_page("TB-G5S1U3-P25", "student-1")

    result = runtime.handle_turn(start.state, "我想学第二块")

    assert result.teacher_response == (
        "这一页只有这一块，我们继续这一块。先跟老师读一读：salad"
    )
    assert result.turn_label == "navigation"
    assert result.teaching_action == "redirect"
    assert result.block_uid == "TB-G5S1U3-P25-D1"
    assert result.state.current_block_uid == "TB-G5S1U3-P25-D1"
    assert result.debug_signals is not None
    assert result.debug_signals.response_audit is not None
    assert result.debug_signals.response_audit.route == "single_module_navigation_guard"
    assert result.debug_signals.response_audit.source == "deterministic"
    assert planned_moves == [
        {
            "schema_version": "peptutor-teaching-move-v1",
            "detected_signal": "module_navigation_unavailable",
            "move": "single_block_guard",
            "teaching_action": "redirect",
            "rationale": (
                "The learner requested another page module, but the active page has "
                "no available module choice; keep the learner in the current block."
            ),
            "evidence_fields_used": [
                "module_choice_skill.navigation_request",
                "page_overview.modules",
                "runtime_state.current_block_uid",
                "runtime_state.last_teacher_question",
                "learner_input",
            ],
            "expected_next_learner_action": (
                "Continue with the current single-block prompt instead of choosing "
                "another module."
            ),
        }
    ]


def test_task_resize_shrinks_answer_turn_before_readiness_judgment(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    judge = _StaticReadinessJudge(_readiness_result("independent", True))
    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=judge,
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    result = runtime.handle_turn(start.state, "太长了，能不能分段")

    assert result.turn_label == "ask_help"
    assert result.teaching_action == "hint"
    assert result.retrieval_mode == "none"
    assert result.evaluation is None
    assert result.state.same_goal_attempt_count == 0
    assert result.state.repair_mode == "task_resize_chunk"
    assert result.state.return_anchor == start.state.last_teacher_question
    assert result.state.return_target
    assert result.state.last_teacher_question == (
        f"Can you repeat: {result.state.return_target}"
    )
    assert result.state.return_target in result.teacher_response
    assert judge.contexts == []


def test_task_resize_uses_live_responder_when_available(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    captured: list[dict[str, object]] = []

    def _teacher_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        parsed = json.loads(prompt)
        captured.append(parsed)
        return f"可以，我们缩小一步，就先读 {parsed['mustsay']}。"

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(_teacher_llm),
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    result = runtime.handle_turn(start.state, "太长了，能不能分段")

    assert result.turn_label == "ask_help"
    assert result.teaching_action == "hint"
    assert result.teacher_response.startswith("可以，我们缩小一步")
    assert captured[-1]["teachermove"] == "resize"
    assert captured[-1]["turn_label"] == "ask_help"


def test_task_resize_word_request_uses_current_vocabulary(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    result = runtime.handle_turn(start.state, "先教单词")

    assert result.turn_label == "ask_help"
    assert result.teaching_action == "hint"
    assert result.state.repair_mode == "task_resize_word"
    assert result.state.return_target == "water"
    assert result.state.last_teacher_question == "Can you repeat: water"
    assert "water" in result.teacher_response


def test_task_resize_follow_up_returns_to_original_task_without_advancing(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    resized = runtime.handle_turn(start.state, "先教单词")

    result = runtime.handle_turn(resized.state, "water")

    assert result.turn_label == "answer_question"
    assert result.teaching_action == "confirm"
    assert result.block_uid == "TB-G5S1U3-P24-D1"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D1"
    assert result.state.last_teacher_question == start.state.last_teacher_question
    assert result.state.return_anchor is None
    assert result.state.return_target is None
    assert result.state.repair_mode == "none"
    assert result.state.awaiting_answer is True
    assert "完整任务" in result.teacher_response


def test_task_resize_does_not_capture_definition_questions(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    result = runtime.handle_turn(start.state, "water 这个单词是什么意思")

    assert result.turn_label == "ask_knowledge"
    assert not result.state.repair_mode.startswith("task_resize")


def test_related_current_task_instruction_does_not_route_back_to_help(tmp_path):
    manifest_path = _write_multi_module_review_pilot(tmp_path)
    runtime = LessonRuntime(PilotLessonCatalog(manifest_path=manifest_path))
    start = runtime.start_page("TB-G5S2U9-P12", "student-1")
    selected = runtime.handle_turn(start.state, "Let's check")
    advanced = runtime.handle_turn(selected.state, "4")

    result = runtime.handle_turn(advanced.state, "Listen again and tick or cross.")

    assert result.turn_label == "answer_question"
    assert result.teaching_action == "hint"
    assert result.block_uid == "TB-G5S2U9-P12-D2"
    assert result.state.current_block_uid == "TB-G5S2U9-P12-D2"
    assert result.state.last_teacher_question == advanced.state.last_teacher_question
    assert "当前听力小题" in result.teacher_response


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


def test_answer_turn_policy_rubrics_are_compact_and_keep_guardrails() -> None:
    answer_rubric_json = json.dumps(
        ANSWER_TURN_POLICY_RUBRIC_V1,
        ensure_ascii=True,
    )
    revision_rubric_json = json.dumps(
        REPLY_QUALITY_REVISION_RUBRIC_V1,
        ensure_ascii=True,
    )
    answer_rubric_text = "\n".join(ANSWER_TURN_POLICY_RUBRIC_V1)
    revision_rubric_text = "\n".join(REPLY_QUALITY_REVISION_RUBRIC_V1)

    assert len(ANSWER_TURN_POLICY_RUBRIC_V1) <= 20
    assert len(answer_rubric_json.encode()) < 5500
    assert len(REPLY_QUALITY_REVISION_RUBRIC_V1) <= 8
    assert len(revision_rubric_json.encode()) < 1400
    for guardrail in (
        "allowedstatewrites",
        "samepageblocks",
        "简体中文",
        "一轮最多一个新目标句和一个动作",
        "开放问答",
        "问词义",
        "不要编造教材",
    ):
        assert guardrail in answer_rubric_text
    for guardrail in (
        "只改写 teacherreply",
        "不重新判断课堂状态",
        "不得改变 block",
        "progression/推进",
        "不编造教材",
        "简体中文",
        "不要加入新模块",
        "英文目标完整",
        "一轮只保留一个下一步动作",
    ):
        assert guardrail in revision_rubric_text


def test_answer_turn_policy_exposes_response_audit_when_debug_enabled(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        _ = (prompt, history_messages, kwargs)
        return json.dumps(
            {
                "teacherreply": "你想到 pizza 了。这里先回到饮料句：I'd like some water.",
                "statepatch": {
                    "currentblockuid": "TB-G5S1U3-P24-D1",
                    "awaitinganswer": True,
                    "lastteacherquestion": "What would you like to drink?",
                },
            }
        )

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge unused by answer-turn policy test",
        ),
        debug_signals_enabled=True,
        llm_provider="test-llm",
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "pizza")

    assert result.debug_signals is not None
    audit = result.debug_signals.response_audit
    assert audit is not None
    assert audit.source == "policy_repaired"
    assert "redirect_reply_policy" in audit.repair_reason
    assert audit.llm_called is True
    assert audit.llm_provider == "test-llm"
    assert audit.latency_ms >= 0
    assert audit.fallback_used is False
    assert audit.fallback_reason == "none"
    assert audit.route == "answer_turn_policy"
    assert audit.llm_token_usage is not None
    assert audit.llm_token_usage["llm_call_count"] >= 1
    assert audit.llm_token_usage["prompt_token_estimate"] > 0
    assert audit.llm_token_usage["completion_token_estimate"] > 0
    assert audit.llm_token_usage["token_count_source"] == "byte_estimate"
    assert audit.llm_token_usage["calls"][0]["page_uid"] == "TB-G5S1U3-P24"
    assert audit.llm_token_usage["calls"][0]["llm_provider"] == "test-llm"
    assert audit.llm_token_usage["calls"][0]["lesson_context_bytes"] > 0
    assert audit.llm_token_usage["calls"][0]["textbook_block_bytes"] > 0
    assert audit.llm_token_usage["calls"][0]["runtime_state_legacy_frame_bytes"] > 0
    assert audit.llm_token_usage["calls"][0]["runtime_state_minimal_view_bytes"] > 0
    assert (
        audit.llm_token_usage["calls"][0]["minimal_runtime_state_prompt_enabled"]
        is True
    )
    assert (
        audit.llm_token_usage["calls"][0]["runtime_state_savings_candidate_bytes"]
        > 0
    )
    assert (
        audit.llm_token_usage["calls"][0]["runtime_state_minimal_view_bytes"]
        < audit.llm_token_usage["calls"][0]["runtime_state_legacy_frame_bytes"]
    )
    expected_metered_capsule_bytes = len(
        json.dumps(
            MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    assert audit.llm_token_usage["calls"][0]["persona_capsule_bytes"] == (
        expected_metered_capsule_bytes
    )
    persona = result.debug_signals.persona
    assert persona.answer_turn_policy_persona_capsule_enabled is True
    assert persona.current_llm_call_persona_capsule_injected is True
    assert persona.persona_capsule_bytes_configured == (
        MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_BYTES
    )
    assert persona.persona_capsule_bytes_metered == expected_metered_capsule_bytes
    assert audit.llm_token_usage["calls"][0]["persona_prompt_bytes"] >= (
        expected_metered_capsule_bytes
    )
    assert audit.llm_token_usage["calls"][0]["policy_instruction_bytes"] > 0
    assert audit.llm_token_usage["calls"][0]["output_schema_bytes"] > 0
    assert audit.llm_token_usage["calls"][0]["json_serialization_overhead_bytes"] == 0
    assert audit.llm_token_usage["calls"][0]["prompt_frame_overhead_bytes"] > 0
    assert audit.llm_token_usage["calls"][0]["unclassified_context_bytes"] == 0
    assert "unknown_context_bytes" in audit.llm_token_usage["calls"][0]
    assert audit.llm_token_usage["calls"][0]["unknown_context_bytes"] == 0


def test_answer_turn_policy_minimal_runtime_state_metering_when_enabled(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PEPTUTOR_ANSWER_TURN_MINIMAL_RUNTIME_STATE", "1")
    manifest_path = _write_test_pilot(tmp_path)

    def _policy_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        assert system_prompt is None
        payload = json.loads(prompt)
        assert payload["minimal_runtime_state_prompt_enabled"] is True
        assert "runtimestate" in payload["frame"]
        assert "allowedstatewrites" not in payload["frame"]
        _ = (history_messages, kwargs)
        return json.dumps(
            {
                "teacherreply": "你想到 pizza 了。这里先回到饮料句：I'd like some water.",
                "statepatch": {
                    "currentblockuid": "TB-G5S1U3-P24-D1",
                    "awaitinganswer": True,
                    "lastteacherquestion": "What would you like to drink?",
                },
            }
        )

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        readiness_judge=ReadinessJudge(
            _policy_llm,
            system_prompt="# readiness judge unused by answer-turn policy test",
        ),
        debug_signals_enabled=True,
        llm_provider="test-llm",
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    result = runtime.handle_turn(start.state, "pizza")

    assert result.debug_signals is not None
    audit = result.debug_signals.response_audit
    assert audit is not None
    assert audit.llm_token_usage is not None
    call = audit.llm_token_usage["calls"][0]
    assert call["minimal_runtime_state_prompt_enabled"] is True
    assert call["runtime_state_legacy_frame_bytes"] > 0
    assert call["runtime_state_minimal_view_bytes"] > 0
    assert call["runtime_state_savings_candidate_bytes"] > 0
    assert call["runtime_state_bytes"] < call["runtime_state_legacy_frame_bytes"]
    assert audit.llm_token_usage[
        "minimal_runtime_state_prompt_enabled_call_count"
    ] == 1
    assert call["unknown_context_bytes"] == 0


def test_responder_llm_exposes_response_audit_when_debug_enabled(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)

    def _responder_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (prompt, system_prompt, history_messages, kwargs)
        return "现场回复 SENTINEL"

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(
            _responder_llm,
            teacher_kernel="# Teacher Kernel\n- test",
            llm_provider="test-responder",
        ),
        debug_signals_enabled=True,
    )

    result = runtime.start_page("TB-G5S1U3-P24", "student-1")

    assert result.teacher_response == "现场回复 SENTINEL"
    assert result.debug_signals is not None
    audit = result.debug_signals.response_audit
    assert audit is not None
    assert audit.source == "llm"
    assert audit.llm_called is True
    assert audit.llm_provider == "test-responder"
    assert audit.latency_ms >= 0
    assert audit.fallback_used is False
    assert audit.fallback_reason == "none"
    assert audit.route == "llm_only"
    assert audit.llm_token_usage is not None
    assert audit.llm_token_usage["llm_call_count"] == 1
    assert audit.llm_token_usage["prompt_bytes"] > 0
    assert audit.llm_token_usage["completion_bytes"] > 0
    assert audit.llm_token_usage["token_count_source"] == "byte_estimate"
    assert audit.llm_token_usage["calls"][0]["audit_tag"] == (
        "responder.render_teacher_turn.page_entry"
    )
    assert audit.llm_token_usage["calls"][0]["lesson_context_bytes"] > 0
    assert audit.llm_token_usage["calls"][0]["page_overview_bytes"] > 0
    assert audit.llm_token_usage["calls"][0]["policy_instruction_bytes"] > 0
    assert audit.llm_token_usage["calls"][0]["responder_prompt_overhead_bytes"] > 0
    assert audit.llm_token_usage["calls"][0]["json_serialization_overhead_bytes"] >= 0
    assert "unknown_context_bytes" in audit.llm_token_usage["calls"][0]
    assert audit.llm_token_usage["calls"][0]["unknown_context_bytes"] == 0
    persona = result.debug_signals.persona
    assert persona.answer_turn_policy_persona_capsule_enabled is True
    assert persona.current_llm_call_persona_capsule_injected is False
    assert persona.persona_capsule_bytes_configured == (
        MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_BYTES
    )
    assert persona.persona_capsule_bytes_metered == 0


def test_responder_fallback_exposes_response_audit_when_debug_enabled(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)

    def _responder_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (prompt, system_prompt, history_messages, kwargs)
        return "English only response"

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(
            _responder_llm,
            teacher_kernel="# Teacher Kernel\n- test",
            llm_provider="test-responder",
        ),
        debug_signals_enabled=True,
    )

    result = runtime.start_page("TB-G5S1U3-P24", "student-1")

    assert result.teacher_response != "English only response"
    assert result.debug_signals is not None
    audit = result.debug_signals.response_audit
    assert audit is not None
    assert audit.source == "fallback"
    assert audit.llm_called is True
    assert audit.llm_provider == "test-responder"
    assert audit.latency_ms >= 0
    assert audit.fallback_used is True
    assert audit.fallback_reason == "response_rejected"
    assert audit.route == "llm_only"


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
        "response_audit": {
            "source": "deterministic",
            "llm_called": False,
            "llm_provider": "unknown",
            "latency_ms": 0,
            "fallback_used": False,
            "fallback_reason": "none",
            "repair_reason": "none",
            "route": "deterministic_only",
        },
    }
    assert persona == {
        "enabled": True,
        "schema_version": "lesson-persona-context/v1",
        "profile_id": "peptutor-teacher-v1",
        "profile_version": "2026-04-24",
        "display_name": "米粒",
        "persona_source": "mili_persona_capsule",
        "persona_version": "v1",
        "capsule_name": "米粒",
        "full_soul_injected": False,
        "answer_turn_policy_persona_capsule_enabled": True,
        "current_llm_call_persona_capsule_injected": False,
        "persona_capsule_bytes_configured": (
            MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_BYTES
        ),
        "persona_capsule_bytes_metered": 0,
        "soul_path": MILI_PERSONA_SOUL_PATH,
        "teacher_kernel_used": True,
        "interests_available": True,
        "interests_runtime_usage": "low_frequency_flavor_only",
        "interests_answer_turn_policy_usage": (
            "low_frequency_flavor_only_not_in_answer_turn_policy_v1"
        ),
        "capsule_prompt_status": (
            "bounded capsule injected into answer_turn_policy"
        ),
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
            "target_role": "",
            "expected_student_action": "",
            "speech_style_tag": "",
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
    assert action["target_role"] == ""
    assert action["expected_student_action"] == ""
    assert action["speech_style_tag"] == ""

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
    assert text_chunks == ["现场老师。"]
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
    assert text_chunks == ["现场老师\n继续。"]
    assert done["result"]["teacher_response"] == "".join(text_chunks)


def test_lesson_turn_stream_route_emits_filtered_fallback_for_generic_praise(
    tmp_path,
):
    manifest_path = _write_try_talk_module_pilot(tmp_path)

    def complete_text(*_args, **_kwargs):
        return "我们先看这一页。"

    def stream_text(*_args, **_kwargs):
        yield "好，这句说得对！"
        yield "我们进入第二块。"

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=manifest_path),
        responder=LessonResponder(complete_text, stream_text=stream_text),
        debug_signals_enabled=True,
    )
    app = FastAPI()
    app.include_router(create_lesson_routes(runtime))
    client = TestClient(app)

    start = client.post("/lesson/turn", json={"page_uid": "TB-G5S1U1-P4"})
    assert start.status_code == 200

    response = client.post(
        "/lesson/turn/stream",
        json={
            "page_uid": "TB-G5S1U1-P4",
            "state": start.json()["state"],
            "learner_input": "第二块",
            "turn_client_id": "browser-turn-generic-praise",
        },
    )

    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    text_chunks = [payload["text"] for name, payload in events if name == "text_delta"]
    done = events[-1][1]
    teacher_response = done["result"]["teacher_response"]
    audit = done["result"]["debug_signals"]["response_audit"]

    assert text_chunks == [teacher_response]
    assert "说得对" not in teacher_response
    assert "Let's talk" in teacher_response
    assert audit["source"] == "llm_repaired"
    assert audit["fallback_used"] is False
    assert audit["fallback_reason"] == "none"
    assert audit["repair_reason"] == "generic_praise_deterministic_repair"


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
    assert text_chunks == ["请说 cake 或 tea。"]
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
    assert result.return_anchor == "What would you like to drink?"
    assert result.state.branch_active is True

    follow_up = runtime.handle_turn(result.state, "okay")
    assert follow_up.retrieval_mode == "none"
    assert follow_up.turn_label == "social"
    assert "What would you like to drink?" in follow_up.teacher_response


def test_branch_scope_after_active_probe_returns_to_current_teacher_question():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    selected = runtime.handle_turn(start.state, "第一块")

    result = runtime.handle_turn(selected.state, "What is your favourite food?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "branch"
    assert result.return_anchor == selected.state.last_teacher_question
    assert result.state.return_anchor == selected.state.last_teacher_question
    assert result.state.branch_active is True
    assert result.state.awaiting_answer is False
    assert "favourite food" in result.teacher_response
    assert "I am hungry" in result.teacher_response

    follow_up = runtime.handle_turn(result.state, "okay")

    assert follow_up.turn_label == "social"
    assert follow_up.retrieval_mode == "none"
    assert follow_up.state.awaiting_answer is True
    assert follow_up.return_anchor == selected.state.last_teacher_question
    assert "I am hungry" in follow_up.teacher_response


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

    assert result.turn_label == "navigation"
    assert result.teaching_action == "redirect"
    assert result.evaluation == "unclear"
    assert "A sandwich, please." not in result.teacher_response
    assert "哪一块" in result.teacher_response


def test_default_manifest_teacher_choice_starts_p24_first_module():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    result = runtime.handle_turn(start.state, "你安排吧")

    assert result.turn_label == "navigation"
    assert result.teaching_action == "probe"
    assert result.block_uid == "TB-G5S1U3-P24-D2"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D2"
    assert result.state.current_activity_type == "teaching"
    assert "我来安排" in result.teacher_response
    assert "hungry" in result.teacher_response
    assert "你想先学哪一块" not in result.teacher_response


def test_default_manifest_page25_opening_uses_localized_vocab_probe():
    runtime = LessonRuntime(PilotLessonCatalog())

    result = runtime.start_page("TB-G5S1U3-P25", "student-1")

    assert "This page teaches" not in result.teacher_response
    assert "这一页" in result.teacher_response
    assert "你想先学哪一块" in result.teacher_response
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
    assert "What would you like to" not in result.teacher_response
    assert "water" not in result.teacher_response


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
    assert result.state.repair_mode == "task_resize_chunk"
    assert result.state.return_target in result.teacher_response
    assert result.state.return_target != targets[0]
    assert result.state.return_target != targets[1]
    assert result.state.last_teacher_question == f"Can you repeat: {result.state.return_target}"
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
    assert "What would you like to" not in result.teacher_response
    assert "water" not in result.teacher_response


def test_default_manifest_food_prompt_rejects_drink_answer():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")

    result = runtime.handle_turn(advanced.state, "I'd like some tea.")

    assert result.turn_label == "answer_question"
    assert result.evaluation == "incorrect"
    assert result.teaching_action == "hint"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D3"
    assert "I'd like chicken and bread." in result.teacher_response
    assert "I'd like rice and vegetables." in result.teacher_response


def test_default_manifest_food_prompt_keeps_single_word_answer_in_practice():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")

    result = runtime.handle_turn(advanced.state, "chicken")

    assert result.turn_label == "answer_question"
    assert result.evaluation == "partially_correct"
    assert result.teaching_action == "hint"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D3"
    assert result.state.awaiting_answer is True
    assert "I'd like" in result.teacher_response
    assert "口渴" not in result.teacher_response


def test_default_manifest_correct_food_answer_advances_to_drink_prompt():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")

    result = runtime.handle_turn(advanced.state, "I'd like chicken and bread.")

    assert result.turn_label == "answer_question"
    assert result.evaluation == "correct"
    assert result.teaching_action == "confirm"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D4"
    assert result.state.awaiting_answer is True
    assert result.state.last_teacher_question == "Can you repeat: What would you like to drink?"
    assert "服务员会问你" in result.teacher_response
    assert "What - would - you - like - to - drink?" in result.teacher_response


def test_default_manifest_drink_question_echo_stays_on_same_block_then_promotes_answer_prompt():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")
    food_step = runtime.handle_turn(advanced.state, "I'd like chicken and bread.")

    result = runtime.handle_turn(food_step.state, "What would you like to drink?")

    assert result.turn_label == "answer_question"
    assert result.evaluation == "correct"
    assert result.teaching_action == "confirm"
    assert result.state.current_block_uid == "TB-G5S1U3-P24-D4"
    assert result.state.awaiting_answer is True
    assert (
        result.state.last_teacher_question
        == "现在你口渴了，跟老师说一句：I'd like some water."
    )
    assert "好，这句服务员的话会了" in result.teacher_response
    assert "I'd like some water." in result.teacher_response


def test_default_manifest_drink_prompt_accepts_drink_answer_after_food_step():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    advanced = runtime.handle_turn(start.state, "I am hungry.")
    food_step = runtime.handle_turn(advanced.state, "I'd like chicken and bread.")
    question_echo = runtime.handle_turn(food_step.state, "What would you like to drink?")

    result = runtime.handle_turn(question_echo.state, "I'd like some tea.")

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
        "concrete_acknowledgement_not_generic_praise",
    ]
    assert "AIRI handles expression and motion outside text" in payload[
        "natural_response_contract"
    ]["delivery_hygiene"][0]
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
    assert any("Do not put emojis" in rule for rule in payload["output_rules"])
    assert any("Avoid generic celebration" in rule for rule in payload["output_rules"])
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


def test_responder_strips_emojis_from_live_teacher_voice():
    responder = LessonResponder(lambda *args, **kwargs: "嗨，小朋友！😊 我们先看两块内容。")

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
        fallback_response="我们先看这一页。",
    )

    assert response == "嗨，小朋友！ 我们先看两块内容。"


def test_responder_strips_emojis_from_streamed_teacher_voice():
    deltas: list[str] = []
    responder = LessonResponder(
        lambda *args, **kwargs: "",
        stream_text=lambda *args, **kwargs: iter(["好，", "我们开始👍"]),
    )

    response = responder.render_teacher_turn_stream(
        learner_input="",
        turn_label="navigation",
        decision=PlannerDecision(
            teaching_action="probe",
            retrieval_mode="none",
            response_focus="Start the selected module.",
        ),
        state_snapshot={},
        page_snapshot={},
        block_snapshot={},
        learner_memory={},
        retrieval_evidence=[],
        support_evidence=[],
        return_anchor=None,
        fallback_response="我们开始。",
        on_delta=deltas.append,
    )

    assert response == "好，我们开始"
    assert deltas == ["好，", "我们开始"]


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


def test_responder_repairs_knowledge_answer_that_drops_return_anchor_phrase():
    responder = LessonResponder(
        lambda *args, **kwargs: (
            '你问的是 "had a cold" 的意思，它指的是“感冒了”。'
            "你想先学第一块还是第二块呢？"
        )
    )
    fallback_response = (
        'had a cold 是“感冒了”。现在先回到刚才这句：'
        "What did you do last weekend?"
    )

    result = responder.render_teacher_turn_result(
        learner_input="had a cold是什么意思",
        turn_label="ask_knowledge",
        decision=PlannerDecision(
            teaching_action="explain",
            retrieval_mode="unit",
            response_focus="Answer briefly, then return to the active task.",
        ),
        state_snapshot={},
        page_snapshot={},
        block_snapshot={
            "allowed_answer_scope": ["What did you do last weekend?"],
            "core_patterns": ["What did you do last weekend?"],
            "return_anchors": ["What did you do last weekend?"],
        },
        learner_memory={},
        retrieval_evidence=[],
        support_evidence=[{"english": "had a cold", "chinese": "感冒了"}],
        return_anchor="What did you do last weekend?",
        fallback_response=fallback_response,
    )

    assert result.text == fallback_response
    assert result.source == "llm_repaired"
    assert result.repair_reason == "grounded_lexicon_required_phrase_repaired"
    assert result.fallback_used is False
    assert result.fallback_reason == "none"


def test_responder_accepts_module_choice_anchor_with_spacing_variation():
    responder = LessonResponder(
        lambda *args, **kwargs: (
            "你问“stayed at home”是什么意思，很好呀。"
            "它就是说“呆在家里”，没有出门的意思。"
            "比如你周末一直在家，就可以说：I stayed at home.\n\n"
            "好，现在先回到我们刚才这一步，"
            "你想先学哪一块？可以说第一块，或者第二块。"
        )
    )
    anchor = "你想先学哪一块？可以说 第一块 或 第二块。"
    fallback_response = (
        "stayed at home 是“呆在家里”。这个点在本单元里还能连到这句："
        "stayed at home 现在先回到刚才这句："
        f"{anchor}"
    )

    result = responder.render_teacher_turn_result(
        learner_input="What does stayed at home mean?",
        turn_label="ask_knowledge",
        decision=PlannerDecision(
            teaching_action="explain",
            retrieval_mode="unit",
            response_focus="Answer briefly, then return to the active module choice.",
        ),
        state_snapshot={},
        page_snapshot={},
        block_snapshot={
            "allowed_answer_scope": [anchor],
            "core_patterns": [anchor],
            "return_anchors": [anchor],
        },
        learner_memory={},
        retrieval_evidence=[],
        support_evidence=[{"english": "stayed at home", "chinese": "呆在家里"}],
        return_anchor=anchor,
        fallback_response=fallback_response,
    )

    assert "stayed at home" in result.text
    assert "你想先学哪一块" in result.text
    assert result.source == "llm"
    assert result.repair_reason == "none"
    assert result.fallback_used is False
    assert result.fallback_reason == "none"


def test_responder_accepts_module_choice_anchor_with_choose_between_wording():
    responder = LessonResponder(
        lambda *args, **kwargs: (
            "好的，这个短语就是我们今天要学的。"
            "stayed at home 就是“呆在家里”，比如周末没出门。 "
            "那我们回到对话练习，你先选一下：第一块 还是 第二块？"
        )
    )
    anchor = "你想先学哪一块？可以说 第一块 或 第二块。"
    fallback_response = (
        "stayed at home 是“呆在家里”。这个点在本单元里还能连到这句："
        f"stayed at home 现在先回到刚才这句：{anchor}"
    )

    result = responder.render_teacher_turn_result(
        learner_input="What does stayed at home mean?",
        turn_label="ask_knowledge",
        decision=PlannerDecision(
            teaching_action="explain",
            retrieval_mode="unit",
            response_focus="Answer briefly, then return to module choice.",
        ),
        state_snapshot={},
        page_snapshot={},
        block_snapshot={
            "allowed_answer_scope": [anchor],
            "core_patterns": [anchor],
            "return_anchors": [anchor],
        },
        learner_memory={},
        retrieval_evidence=[],
        support_evidence=[{"english": "stayed at home", "chinese": "呆在家里"}],
        return_anchor=anchor,
        fallback_response=fallback_response,
    )

    assert "stayed at home" in result.text
    assert "第一块 还是 第二块" in result.text
    assert "你想先学哪一块" not in result.text
    assert result.source == "llm"
    assert result.repair_reason == "none"
    assert result.fallback_used is False
    assert result.fallback_reason == "none"


def test_responder_accepts_module_choice_anchor_with_markdown_and_wording_variation():
    responder = LessonResponder(
        lambda *args, **kwargs: (
            "嗯，你问must是什么意思，这是个好问题。\n\n"
            "Must表示“必须”，是一个很强烈的词，用来告诉别人一定要做某事。\n\n"
            "比如这一句：**We must stop and wait.** 我们必须停下来等。\n\n"
            "你先选一下想学哪一块吧——可以说 **第一块、第二块、第三块** 或 **第四块**。"
        )
    )
    anchor = "你想先学哪一块？可以说 第一块、第二块、第三块 或 第四块。"
    fallback_response = (
        "这个点在本单元里还能连到这句："
        "Please wait! It's red now. We must stop and wait. "
        f"现在先回到刚才这句：{anchor}"
    )

    result = responder.render_teacher_turn_result(
        learner_input="What does must mean?",
        turn_label="ask_knowledge",
        decision=PlannerDecision(
            teaching_action="explain",
            retrieval_mode="unit",
            response_focus="Answer briefly, then return to module choice.",
        ),
        state_snapshot={},
        page_snapshot={},
        block_snapshot={
            "allowed_answer_scope": [anchor],
            "core_patterns": [anchor],
            "return_anchors": [anchor],
        },
        learner_memory={},
        retrieval_evidence=[
            {
                "english": "We must stop and wait.",
                "chinese": "我们必须停下来等。",
            }
        ],
        support_evidence=[],
        return_anchor=anchor,
        fallback_response=fallback_response,
    )

    assert "Must表示" in result.text
    assert "We must stop and wait." in result.text
    assert "第四块" in result.text
    assert "**" not in result.text
    assert result.source == "llm"
    assert result.repair_reason == "none"
    assert result.fallback_used is False
    assert result.fallback_reason == "none"


def test_responder_accepts_module_choice_anchor_with_continue_wording():
    responder = LessonResponder(
        lambda *args, **kwargs: (
            '好问题！"feature"在这里是"特点"的意思——就像Robin有一个新特点、新本领。\n\n'
            "你看这句话：**1. What is Robin's new feature?** 有两个选项：\n"
            "□ He can find food.\n"
            "□ He can find the way.\n\n"
            "根据课文，Robin的新特点是能找路：**He can find the way.**\n\n"
            "我们先记住这个词。现在，你想继续学哪一块？可以说 第一块、第二块 或 第三块。"
        )
    )
    anchor = "你想先学哪一块？可以说 第一块、第二块 或 第三块。"
    fallback_response = (
        "feature 是“特点”。先贴着当前这一块理解。"
        "先抓这句：1. What is Robin's new feature? □ He can find food. "
        f"□ He can find the way. 现在先回到刚才这句：{anchor}"
    )

    result = responder.render_teacher_turn_result(
        learner_input="What does feature mean?",
        turn_label="ask_knowledge",
        decision=PlannerDecision(
            teaching_action="explain",
            retrieval_mode="block",
            response_focus="Answer briefly, then return to module choice.",
        ),
        state_snapshot={},
        page_snapshot={},
        block_snapshot={
            "allowed_answer_scope": [anchor],
            "core_patterns": [anchor],
            "return_anchors": [anchor],
        },
        learner_memory={},
        retrieval_evidence=[
            {
                "english": "feature",
                "chinese": "特点",
            }
        ],
        support_evidence=[
            {
                "english": "What is Robin's new feature?",
                "chinese": "Robin的新特点是什么？",
            }
        ],
        return_anchor=anchor,
        fallback_response=fallback_response,
    )

    assert "feature" in result.text
    assert "He can find the way." in result.text
    assert "第三块" in result.text
    assert result.source == "llm"
    assert result.fallback_used is False
    assert result.fallback_reason == "none"


def test_responder_repairs_grounded_lexicon_reply_that_forces_module_choice():
    responder = LessonResponder(
        lambda *args, **kwargs: (
            "哦，你问了stayed at home的意思啊！"
            "stayed at home就是“呆在家里”，stay是“待着”，at home是“在家”。\n\n"
            "比方说这句：I stayed at home last weekend. 我上周末待在家里了。\n\n"
            "好，那我们先把这个问题放一下，回到刚才的页面——"
            "我帮你选了“第一块”，你来试试这个对话。"
        )
    )
    anchor = "你想先学哪一块？可以说 第一块 或 第二块。"
    fallback_response = (
        "stayed at home 是“呆在家里”。这个点在本单元里还能连到这句："
        f"stayed at home 现在先回到刚才这句：{anchor}"
    )

    result = responder.render_teacher_turn_result(
        learner_input="What does stayed at home mean?",
        turn_label="ask_knowledge",
        decision=PlannerDecision(
            teaching_action="explain",
            retrieval_mode="unit",
            response_focus="Answer briefly, then return to module choice.",
        ),
        state_snapshot={},
        page_snapshot={},
        block_snapshot={
            "allowed_answer_scope": [anchor],
            "core_patterns": [anchor],
            "return_anchors": [anchor],
        },
        learner_memory={},
        retrieval_evidence=[],
        support_evidence=[{"english": "stayed at home", "chinese": "呆在家里"}],
        return_anchor=anchor,
        fallback_response=fallback_response,
    )

    assert result.text == fallback_response
    assert "我帮你选" not in result.text
    assert result.source == "llm_repaired"
    assert result.repair_reason == "grounded_lexicon_required_phrase_repaired"
    assert result.fallback_used is False
    assert result.fallback_reason == "none"


def test_responder_repairs_grounded_lexicon_reply_back_to_active_prompt():
    responder = LessonResponder(
        lambda *args, **kwargs: (
            "tea 是“茶”的意思，读音是 /tiː/。"
            "我们先记住这个单词，然后回到图上。"
            "图上爸爸正在吃三明治，他说：The sandwich is delicious."
        )
    )
    active_prompt = "What's your favourite food?"
    fallback_response = (
        "tea 是“茶；茶水”，读音 /tiː/。"
        "先贴着当前这一块理解。先抓这句：The sandwich is delicious."
    )

    result = responder.render_teacher_turn_result(
        learner_input="tea",
        turn_label="ask_knowledge",
        decision=PlannerDecision(
            teaching_action="redirect",
            retrieval_mode="block",
            response_focus="Answer briefly, then return to the active prompt.",
        ),
        state_snapshot={"awaiting_answer": True},
        page_snapshot={},
        block_snapshot={
            "allowed_answer_scope": [active_prompt],
            "core_patterns": [active_prompt],
            "return_anchors": [active_prompt],
        },
        learner_memory={},
        retrieval_evidence=[{"english": "tea", "chinese": "茶；茶水"}],
        support_evidence=[{"english": "tea", "chinese": "茶；茶水"}],
        return_anchor=active_prompt,
        fallback_response=fallback_response,
    )

    assert result.source == "llm_repaired"
    assert result.repair_reason == "grounded_lexicon_required_phrase_repaired"
    assert result.fallback_used is False
    assert result.fallback_reason == "none"
    assert "tea 是" in result.text
    assert active_prompt in result.text


def test_load_teacher_soul_reads_repo_file():
    soul = load_teacher_soul()

    assert soul.startswith("# Teacher Soul")
    assert "long-form design source for Mili" in soul
    assert "Runtime prompts should use the compact Mili Persona Capsule" in soul
    assert "## Runtime Summary" in soul
    assert "## Interests / Personal Flavor" in soul
    assert "pedagogy first" in soul
    assert "先听见孩子，再教课本" in soul
    assert "help 是求救信号，不是错误答案" in soul


def test_mili_persona_capsule_records_structured_low_frequency_flavor():
    assert MILI_PERSONA_CAPSULE_VERSION == "v1"
    assert MILI_PERSONA_SOUL_PATH.endswith("/soul.md")
    assert MILI_PERSONA_CAPSULE_V1["name"] == "米粒"
    assert MILI_PERSONA_CAPSULE_V1["nickname"] == "Mili"
    assert MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_BYTES < 400
    assert "米粒老师风格" in MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1
    assert "人格只影响语气和脚手架大小" in (
        MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1
    )
    assert "# Teacher Soul" not in MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1
    assert "Sample Lines" not in MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1
    assert "海鲜螺蛳粉" not in MILI_ANSWER_TURN_POLICY_PERSONA_CAPSULE_V1
    assert "海鲜螺蛳粉" in MILI_PERSONA_CAPSULE_V1["interests"]
    assert "周末去海边看日落" in MILI_PERSONA_CAPSULE_V1["interests"]
    assert "兴趣爱好只作为低频人格味道" in MILI_PERSONA_CAPSULE_V1[
        "interest_usage_policy"
    ]
    assert "不要影响教材目标和教学路线" in MILI_PERSONA_CAPSULE_V1[
        "interest_usage_policy"
    ]


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


def test_default_manifest_support_asset_gloss_preferred_over_catalog_atom_gloss():
    catalog = PilotLessonCatalog(manifest_path=_general_overlay_manifest_path())
    runtime = LessonRuntime(catalog, support_retriever=SupportAssetRetriever(catalog))
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does salad mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.support_entry_uids[0] == "LEX-G5S1U3-salad"
    assert "沙拉" in result.teacher_response
    assert "a salad item" not in result.teacher_response


def test_default_manifest_knowledge_query_during_answer_turn_returns_to_current_prompt():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    result = runtime.handle_turn(start.state, "What does salad mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.state.awaiting_answer is True
    assert "选入口" in result.teacher_response or "选一块" in result.teacher_response
    assert "What would you like to eat?" not in result.teacher_response


def test_default_manifest_feature_query_at_module_choice_keeps_one_return_step():
    catalog = PilotLessonCatalog(manifest_path=_general_overlay_manifest_path())
    runtime = LessonRuntime(catalog, support_retriever=SupportAssetRetriever(catalog))
    start = runtime.start_page("TB-G6S1U1-P9", "student-1")

    result = runtime.handle_turn(start.state, "What does feature mean?")

    assert result.turn_label == "ask_knowledge"
    assert "feature" in result.teacher_response
    assert "选入口" in result.teacher_response or "先选" in result.teacher_response
    assert "What is Robin's new feature?" not in result.teacher_response
    assert "He can find food" not in result.teacher_response
    assert not runtime._teacher_reply_looks_overloaded(
        result.teacher_response,
        turn_label="ask_knowledge",
    )


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
    assert result.return_anchor == "如果你是顾客，你会怎么点餐？"
    assert result.state.branch_active is True
    assert result.state.awaiting_answer is False
    assert result.state.current_block_uid == "TB-G5S1U3-P25-D3"

    follow_up = runtime.handle_turn(result.state, "okay")

    assert follow_up.turn_label == "social"
    assert follow_up.retrieval_mode == "none"
    assert follow_up.state.awaiting_answer is True
    assert "如果你是顾客，你会怎么点餐？" in follow_up.teacher_response


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
    assert result.return_anchor == "I'm 1.6 metres tall."


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


def test_default_manifest_live_knowledge_reply_must_return_to_active_g6_task():
    catalog = PilotLessonCatalog(manifest_path=_general_overlay_manifest_path())
    runtime = LessonRuntime(
        catalog,
        support_retriever=SupportAssetRetriever(catalog),
        responder=LessonResponder(
            lambda *args, **kwargs: (
                '你问的是 "had a cold" 的意思，它指的是“感冒了”。'
                "现在你想先学第一块还是第二块呢？"
            )
        ),
        debug_signals_enabled=True,
    )
    start = runtime.start_page("TB-G6S2U2-P13", "student-1")
    selected = runtime.handle_turn(start.state, "第一块")

    result = runtime.handle_turn(selected.state, "had a cold是什么意思")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.debug_signals is not None
    audit = result.debug_signals.response_audit
    assert audit.source == "llm_repaired"
    assert audit.repair_reason == "grounded_lexicon_required_phrase_repaired"
    assert audit.fallback_used is False
    assert audit.fallback_reason == "none"
    assert "had a cold" in result.teacher_response
    assert "What did you do last weekend?" in result.teacher_response
    assert "想先学第一块还是第二块" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2U2-P13-D2"
    assert result.state.awaiting_answer is True


def test_default_manifest_page_entry_vocab_return_prefers_concrete_task_anchor():
    catalog = PilotLessonCatalog(manifest_path=_general_overlay_manifest_path())
    runtime = LessonRuntime(
        catalog,
        support_retriever=SupportAssetRetriever(catalog),
        responder=LessonResponder(
            lambda *args, **kwargs: (
                "stayed at home 就是“呆在家里”。"
                "现在你想先学第一块还是第二块呢？"
            )
        ),
        debug_signals_enabled=True,
    )
    start = runtime.start_page("TB-G6S2U2-P13", "student-1")

    result = runtime.handle_turn(start.state, "What does stayed at home mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.return_anchor == "What did you do last weekend?"
    assert result.debug_signals is not None
    audit = result.debug_signals.response_audit
    assert audit.source == "llm_repaired"
    assert audit.repair_reason == "grounded_lexicon_required_phrase_repaired"
    assert audit.fallback_used is False
    assert audit.fallback_reason == "none"
    assert "stayed at home" in result.teacher_response
    assert "What did you do last weekend?" in result.teacher_response
    assert "想先学第一块还是第二块" not in result.teacher_response
    assert result.state.current_block_uid == "TB-G6S2U2-P13-D2"
    assert result.state.awaiting_answer is True


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
    assert result.support_entry_uids == ["KA-G5S1U3-word-snow"]
    assert "snow" in result.teacher_response
    assert "雪" in result.teacher_response


def test_live_planner_cannot_downgrade_same_block_lexicon_selection_to_none():
    def _planner_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        parsed = json.loads(prompt)
        if parsed["turn_kind"] == "route_classifier":
            return json.dumps(
                {
                    "turn_label": "ask_knowledge",
                    "reason": "The learner asks for a word meaning.",
                }
            )
        return json.dumps(
            {
                "teaching_action": "explain",
                "retrieval_mode": "none",
                "response_focus": "Planner intentionally asks for no retrieval.",
            }
        )

    runtime = LessonRuntime(
        PilotLessonCatalog(),
        planner=LessonPlanner(_planner_llm),
        responder=LessonResponder(lambda *args, **kwargs: "snow 是“雪”。先跟老师读 cow。"),
    )
    start = runtime.start_page("TB-G5S1U3-P26", "student-1")
    selected = runtime.handle_turn(start.state, "第一块")

    result = runtime.handle_turn(selected.state, "What does snow mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "block"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P26-D1"]
    assert result.support_entry_uids == ["KA-G5S1U3-word-snow"]
    assert result.state.current_block_uid == "TB-G5S1U3-P26-D1"
    assert result.state.awaiting_answer is True


def test_default_manifest_same_page_phonics_gloss_returns_to_active_task():
    runtime = LessonRuntime(PilotLessonCatalog())
    start = runtime.start_page("TB-G5S1U3-P26", "student-1")
    selected = runtime.handle_turn(start.state, "第三块")

    result = runtime.handle_turn(selected.state, "snow是什么意思")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode in {"block", "page", "unit"}
    assert result.support_entry_uids == ["KA-G5S1U3-word-snow"]
    assert "snow" in result.teacher_response
    assert "雪" in result.teacher_response
    assert "flower" in result.teacher_response
    assert "先贴着当前" not in result.teacher_response
    assert "先抓这句" not in result.teacher_response
    assert "回到刚才的小任务" in result.teacher_response
    assert result.state.current_block_uid == "TB-G5S1U3-P26-D3"
    assert result.state.awaiting_answer is True


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
    selected = runtime.handle_turn(start.state, "第一块")

    result = runtime.handle_turn(selected.state, "banana")

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


def test_responder_prompt_and_turn_audit_use_effective_retrieval_mode(
    tmp_path,
    monkeypatch,
):
    manifest_path = _write_test_pilot(tmp_path)
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    support_retriever = SupportAssetRetriever(
        catalog,
        support_paths=[_write_test_support_assets(tmp_path)],
    )
    captured_responder_prompt: dict[str, object] = {}
    info_messages: list[str] = []

    def _planner_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        parsed = json.loads(prompt)
        if parsed["turn_kind"] == "route_classifier":
            return json.dumps(
                {
                    "turn_label": "ask_knowledge",
                    "reason": "The learner asks for a word meaning.",
                }
            )
        return json.dumps(
            {
                "teaching_action": "explain",
                "retrieval_mode": "none",
                "response_focus": "Planner intentionally asks for no retrieval.",
            }
        )

    def _responder_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        captured_responder_prompt.update(json.loads(prompt))
        return "salad 是“沙拉”。"

    def _capture_info(message, *args):
        info_messages.append(message % args)

    lesson_runtime_module = sys.modules[LessonRuntime.__module__]
    monkeypatch.setattr(lesson_runtime_module.logger, "info", _capture_info)

    runtime = LessonRuntime(
        catalog,
        support_retriever=support_retriever,
        planner=LessonPlanner(_planner_llm),
        responder=LessonResponder(_responder_llm),
    )
    start = runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})

    result = runtime.handle_turn(open_state, "What does salad mean?")

    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "unit"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P25-D1"]
    assert captured_responder_prompt["plan"]["retrieval_mode"] == "unit"
    turn_audits = [
        message for message in info_messages if message.startswith("Lesson turn audit")
    ]
    assert any(
        "turn_label=ask_knowledge" in message and "retrieval_mode=unit" in message
        for message in turn_audits
    )
    assert not any(
        "turn_label=ask_knowledge" in message and "retrieval_mode=none" in message
        for message in turn_audits
    )


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
