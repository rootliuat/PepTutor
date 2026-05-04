# P5.9.7 Dynamic Context Next Plan

Generated: 2026-05-04

## Executive Summary

P5.9.6 enabled readiness was sampled once with
`PEPTUTOR_ANSWER_TURN_MINIMAL_RUNTIME_STATE=1`. The backend smoke stayed green and
the TeachingMove/Classroom audits passed, but default-on is not yet recommended:
Redirect audit still reports `answer_scope_issue=1` on `TB-G6S2U2-P13`.

Dynamic context work should therefore remain a planning slice until the runtime
state switch has a clean readiness gate. The next trim should be active-scope
textbook slimming, not another policy-rubric diet.

## Latest Evidence

- Smoke: `temp/lesson-smoke-artifacts/lesson_smoke_matrix_20260504_202025.json`
- TeachingMove audit: `temp/lesson-smoke-artifacts/teaching_move_audit_20260504_202815.json`
- Context audit: `temp/lesson-smoke-artifacts/llm_context_breakdown_audit_20260504_202815.json`
- Runtime shadow audit: `temp/lesson-smoke-artifacts/runtime_state_minimal_view_shadow_audit_20260504_202815.json`

Key numbers from the enabled sample:

- `fallback_count=0`, `http_error_count=0`, `state_drift_count=0`, `issue_count=0`
- `teaching_action_semantic_warning_count=0`
- `unknown_context_bytes=0`
- `runtime_state_bytes=155083`
- `answer_turn_policy_runtime_state.avg_runtime_state_bytes=695`
- `avg/p95/max prompt tokens=1854/3172/3583`

## Recommended Trim Objects

1. `textbook_block_bytes`

   Keep the current block and same-page boundary facts, but stop sending all
   neighboring block detail to answer-turn policy when the current block is
   already locked. This is the next highest-value trim after fixed rubric and
   runtime-state slimming.

2. `page_overview_bytes`

   Keep page identity and block count, but replace long overview text with a
   compact page/task summary for answer turns. Page entry can keep richer
   overview; answer turns should not need it every time.

3. `other_bytes`

   Current unknown attribution is already clean (`unknown_context_bytes=0`).
   Remaining `other_bytes` is explained overhead, so it should not be trimmed
   until textbook and page overview are handled.

## Fields That Must Not Be Trimmed

- `teacherasked`
- `currentblockuid`
- `allowedcurrentblockuids`
- `currentblockcanstay`
- `canwriteotherblocks`
- `matchedblockuids`
- `matchedblockfields`
- `activequestionkind`
- `currentblockscope`
- `hasmultiplecurrenttargets`
- `samepageblockroles`
- TeachingMove action contract fields:
  `target_role`, `expected_student_action`, `question_target`,
  `answer_target`, `answer_frame`, `action_source`
- Persona safety flags:
  `full_soul_injected=false`, bounded capsule source/version
- State write schema and route/page/block guardrails

## Active-Scope Textbook Slimming Proposal

Implement as an env-gated shadow first:

```text
PEPTUTOR_ANSWER_TURN_ACTIVE_SCOPE_TEXTBOOK=1
```

For `answer_turn_policy`, build a compact textbook view:

- current block UID/type/task/goal
- current block core patterns
- current block return anchors
- current block allowed answer scope
- same-page block role map only, without full prose for inactive blocks
- page label and total block count

Do not use the active-scope view for:

- page entry
- module choice
- RAG retrieval
- classification policy
- S4/browser paths

## Guardrails

- Do not trim answer scope.
- Do not trim current block return anchors.
- Do not trim module-choice allowed block IDs.
- Do not infer missing textbook facts with LLM.
- Do not alter page/block progression.
- Do not write page UID or smoke-input special cases.
- Do not modify the 20-page matrix or audit thresholds.

## Verification Plan

L1:

```bash
PEPTUTOR_TEST_GOAL_ID=active-scope-textbook-shadow \
backend/LightRAG/.venv/bin/python -m pytest \
backend/LightRAG/tests/test_lesson_runtime.py \
backend/LightRAG/tests/test_lesson_smoke_scripts.py -q

PEPTUTOR_TEST_GOAL_ID=active-scope-textbook-shadow \
backend/LightRAG/.venv/bin/ruff check \
backend/LightRAG/lightrag/orchestrator/lesson_runtime.py \
backend/LightRAG/lightrag/orchestrator/lesson_llm_metering.py \
backend/LightRAG/tests/test_lesson_runtime.py \
backend/LightRAG/tests/test_lesson_smoke_scripts.py
```

L3, only after L1:

```bash
PEPTUTOR_TEST_GOAL_ID=active-scope-textbook-shadow \
PEPTUTOR_TEST_GOAL_TYPE=backend \
PEPTUTOR_ANSWER_TURN_MINIMAL_RUNTIME_STATE=1 \
PEPTUTOR_ANSWER_TURN_ACTIVE_SCOPE_TEXTBOOK=1 \
bash scripts/smoke_lesson_regression_20.sh
```

## Default-On Dependency

Do not make active-scope textbook slimming default-on until the minimal runtime
state default-on gate is clean. The current blocker is not token cost; it is the
remaining P13 redirect `answer_scope_issue` under enabled readiness.
