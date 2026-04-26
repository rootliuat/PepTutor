# Test Data Samples

## Purpose
This document records the main lesson-core test samples so they do not live only inside test files or chat history.

## 1. TeacherReasoning Opening Sample
Source:
- [test_pilot_teacher_reasoning.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_reasoning.py)

Sample:
```python
{
    "user_text": "学习五年级上册第31页",
    "current_page_uid": "TB-G5S1U3-P31",
    "current_page_type": "story",
    "current_block_uid": "TB-G5S1U3-P31-D1",
    "teacher_action": "follow_story_and_retell",
    "last_teacher_question": "What would Zoom like to eat?",
    "entry_result": {
        "intro": (
            "这一页是 Zoom 和 Zip 做沙拉的小故事，重点会练到食物表达和说自己想吃什么。"
            "重点句型是 \"I'm hungry.\"、\"Let's make a salad.\" 和 \"I'd like a salad.\"。"
        ),
        "metadata": {
            "page_teaching_goal": "Follow the salad story and reuse Unit 3 food language in context.",
            "page_focus_patterns": ["I'm hungry.", "Let's make a salad.", "I'd like a salad."],
            "page_focus_vocabulary": ["hungry", "salad", "tomatoes"],
        },
    },
    "evaluation": {},
}
```

Expected reasoning behavior:
- `student_state == "unknown"`
- `chosen_skill == "page_intro"`
- decision mentions first responding to which page the student wants to learn
- next step remains a very short probe

## 2. TeacherReasoning Partial-Answer Sample
Source:
- [test_pilot_teacher_reasoning.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_reasoning.py)

Sample:
```python
{
    "learner_text": "I am hungry.",
    "repair_mode": "sentence_drill",
    "evaluation": {
        "verdict": "partial",
        "mastery_level": "shaky",
        "recommended_action": "sentence_drill",
    },
    "retrieval": {
        "candidates": [
            {
                "matched_terms": ["hungry"],
                "teaching_summary": "Zoom is hungry and would like a salad.",
            }
        ]
    },
}
```

Expected reasoning behavior:
- `student_state == "shaky"`
- `chosen_skill == "sentence_drill"`
- decision points to shrinking the task to a minimum full sentence

## 3. TeacherResponse Prompt Sample
Source:
- [test_pilot_teacher_response.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_response.py)

Sample:
```python
{
    "user_text": "学习五年级上册第31页",
    "learner_text": "I am hungry.",
    "current_page_uid": "TB-G5S1U3-P31",
    "current_page_type": "story",
    "current_block_uid": "TB-G5S1U3-P31-D1",
    "teacher_action": "follow_story_and_retell",
    "last_teacher_question": "What would Zoom like to eat?",
    "repair_mode": "sentence_drill",
    "evaluation": {
        "verdict": "partial",
        "mastery_level": "shaky",
        "recommended_action": "sentence_drill",
    },
    "teacher_reasoning": {
        "student_state": "shaky",
        "decision": "学生会一点但还不稳，应该缩回到最小完整句。",
        "chosen_skill": "sentence_drill",
        "next_step": "让学生围绕当前问题再说一个完整短句：What would Zoom like to eat?",
        "focus": "本轮聚焦当前页核心表达：I'm hungry.",
    },
}
```

Expected prompt contract:
- includes exact user request
- includes page intro and key patterns
- includes teacher reasoning fields
- constrains the model to one small classroom move

## 4. Opening-Prompt Contract Sample
Source:
- [test_pilot_teacher_response_opening_prompt.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_response_opening_prompt.py)

Sample:
```python
{
    "user_text": "学习五年级上册第31页",
    "learner_text": "",
    "current_page_uid": "TB-G5S1U3-P31",
    "current_page_type": "story",
    "current_block_uid": "TB-G5S1U3-P31-D1",
    "teacher_action": "follow_story_and_retell",
    "last_teacher_question": "What would Zoom like to eat?",
    "repair_mode": "none",
    "teacher_reasoning": {
        "student_state": "unknown",
        "decision": "先回应学生要学哪一页，再用中文点出本页主题和重点句型。",
        "chosen_skill": "page_intro",
        "next_step": "先给一个很短的试探题：What would Zoom like to eat?",
        "focus": "先抓本页核心句型：I'm hungry.",
    },
    "evaluation": {},
}
```

Expected opening contract:
- acknowledge the exact page request
- give a short Chinese overview
- mention one or two key sentence patterns
- do not jump straight into “story time”
- ask one tiny probe

## 5. LessonGraph Scenario Samples
Source:
- [test_pilot_lesson_graph.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_lesson_graph.py)

Key inputs:
```python
{"user_text": "学习五年级上册第31页"}
{"user_text": "学习五年级上册第31页", "learner_text": "Zoom would like a salad."}
{"user_text": "五年级上第三单元", "learner_text": "能拆开练吗？这个太长了"}
{"user_text": "学习五年级上册第28页", "current_block_uid": "TB-G5S1U3-P28-D2", "learner_text": "sandwich"}
```

Covered behaviors:
- page entry only
- story-page happy path
- split-practice request
- vocabulary correction
- disabled SimpleMem writeback path

## 6. Lesson API Request Samples
Source:
- [test_pilot_lesson_api.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_lesson_api.py)

Page request:
```json
{
  "thread_id": "api-001",
  "student_id": "stu-001",
  "user_text": "学习五年级上册第31页"
}
```

Interaction request:
```json
{
  "thread_id": "api-002",
  "student_id": "stu-001",
  "user_text": "五年级上第三单元",
  "learner_text": "能拆开练吗？这个太长了"
}
```

Protected-route sample:
```json
{
  "user_text": "学习五年级上册第31页"
}
```

Expected API checks:
- lesson state lands on the correct page/block
- interaction flow returns `repair_request` and `sentence_drill`
- missing API key returns `403` when route protection is enabled

## 7. Real LLM Validation Note
These samples are used in two different validation layers:

- stable pytest regression:
  - mostly logic tests and mock tests
  - no dependency on live model output
- live LLM smoke validation:
  - manual or ad hoc validation with real DeepSeek calls
  - confirms the runtime actually reaches:
    - `teacher_reasoning.used_llm = true`
    - `response_generation.used_llm = true`

This separation is intentional. Stable regression and live-model validation should not be mixed into one fragile suite.
