# S3 + Mili Visible Tone Next Plan

Generated: 2026-05-04

## Executive Summary

Backend route stability is now strong, but the visible classroom experience is
not complete. The next S3/Mili slice should be small and public-rule based:
improve visible redirect wording only where TeachingMove action fields already
make the intended teaching action explicit.

Do not inject `soul.md`, sample lines, or interests into lesson prompts. Mili's
visible tone should remain bounded: warm acknowledgement, short Chinese
scaffold, clear English target, one next action.

## Current Evidence

- Smoke: `temp/lesson-smoke-artifacts/lesson_smoke_matrix_20260504_202025.json`
- TeachingMove audit: `temp/lesson-smoke-artifacts/teaching_move_audit_20260504_202815.json`
- Classroom quality audit: `temp/lesson-smoke-artifacts/classroom_quality_audit_20260504_202823.json`
- Redirect audit: `temp/lesson-smoke-artifacts/redirect_experience_audit_20260504_202823.json`

Current redirect classifications:

- `normal_test_artifact=5`
- `needs_runtime_review=3`
- `missing_scaffold_translation=1`
- `answer_scope_issue=1`

The `answer_scope_issue` is still `TB-G6S2U2-P13` and should not be mixed with
Mili visible tone work.

## Candidate Pages And Public Rules

### TB-G5S1U3-P22

Issue class: favourite-food redirect can still feel repetitive when smoke inputs
are deliberately off-task.

Public rule:

- If action contract is `question + answer_frame`, render:
  warm acknowledgement, question with short Chinese meaning, answer frame.
- Do not add multiple actions.
- Do not turn drinks into food targets.

### TB-G6S1U1-P4

Issue class: directions dialogue needs question/answer role clarity.

Public rule:

- If `question_target=Where is the museum shop?` and
  `answer_target=It's near the door.`, do not collapse the visible target to
  `museum shop`.
- If expected action is answer, show the question and answer frame.
- If expected action is repeat, show the answer sentence only.

### TB-G6S2U1-P4

Issue class: height dialogue is structurally stable after target-source lock,
but visible replies must not drift back to `How tall are you?` for object-height
turns.

Public rule:

- For object height, visible target is `How tall is it?`.
- Use `It's ... metres tall.` only when the action contract supplies it.
- Never derive the target from learner input.

### TB-G5S1U3-P31

Issue class: story redirect can still feel stiff or overloaded.

Public rule:

- Use `story + answer_frame` contract.
- Keep one turn to: acknowledge story word, ask story question, give frame.
- Do not add background recap plus answer plus drill in the same reply.

### TB-G5S2U1-P6

Issue class: phonics scaffold should be teacher-like without leaking target
fragments.

Public rule:

- Use `phonics + repeat` contract only when `answer_target` is validated.
- Render one phonics note and one repeat action.
- `cl' as in` must never be visible.

## Mili Visible Tone Micro-Slice

Allowed tone changes:

- "我听到你说 X" instead of mechanical "你刚才说的是 X"
- one short Chinese scaffold when known
- concise English target line
- one action line

Disallowed:

- interest references such as food, sea, notebook, detective animation
- full `soul.md`
- sample-line copying
- page UID special cases
- smoke input special cases
- fixed teacher reply templates
- changes to route/page/block/progression

## What Not To Handle In This Slice

- P13 answer_scope/module-choice boundary
- S4/TTS/browser behavior
- P49/classification policy
- RAG retrieval
- dynamic context trim
- 40-44 page expansion
- smoke matrix changes

## Suggested Implementation Slice

Name:

```text
P6.4 Mili Visible Tone Safe Renderer v1
```

Scope:

- Only use already validated TeachingMove action fields.
- Only touch redirect visible rendering.
- Add tests for P22, G6S1P4, G6S2P4, P31, and P6.
- Do not modify answer-turn policy prompt or responder prompt.

L1 gate:

```bash
PEPTUTOR_TEST_GOAL_ID=mili-visible-tone-safe-renderer \
backend/LightRAG/.venv/bin/python -m pytest \
backend/LightRAG/tests/test_lesson_runtime.py \
backend/LightRAG/tests/test_teaching_move_planner.py \
backend/LightRAG/tests/test_lesson_smoke_scripts.py -q

PEPTUTOR_TEST_GOAL_ID=mili-visible-tone-safe-renderer \
backend/LightRAG/.venv/bin/ruff check \
backend/LightRAG/lightrag/pedagogy/redirect_reply_policy.py \
backend/LightRAG/lightrag/orchestrator/teaching_move_planner.py \
backend/LightRAG/tests/test_lesson_runtime.py \
backend/LightRAG/tests/test_teaching_move_planner.py \
backend/LightRAG/tests/test_lesson_smoke_scripts.py
```

L3:

Run one full 20-page backend smoke only after L1 passes and only if the change
affects visible lesson replies.

## Acceptance

- 20-page smoke remains green.
- TeachingMove audit remains passed.
- Classroom quality remains passed.
- P6 `cl' as in` does not return.
- P13 is unchanged and tracked separately.
- No full `soul.md`, interests, or sample lines enter the prompt.
