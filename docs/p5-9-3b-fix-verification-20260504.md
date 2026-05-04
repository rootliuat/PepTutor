# P5.9.3b-fix Verification

Date: 2026-05-04

## Scope

This verification only checked the `return_anchor=None` typed contract fix from P5.9.3b.
It did not enter P5.9.4 and did not switch the live prompt to the minimal runtime state view.

## Code Fix Location

The fix is already present on `rootliuat/PepTutor` main in commit `24ab3a8`.

- `backend/LightRAG/lightrag/pedagogy/teaching_move.py`
- `TeachingMoveActionContract.from_payload_fields()` normalizes optional string payload fields through `_optional_payload_string()`.
- `return_anchor=None` is normalized to `""` before Pydantic strict string validation.
- Required enum fields remain strict.

Relevant test:

- `backend/LightRAG/tests/test_teaching_move_planner.py::test_teaching_move_action_contract_treats_optional_none_as_empty_string`

## Verification Commands Run

```bash
PEPTUTOR_TEST_GOAL_ID=runtime-state-shadow-audit-verify \
backend/LightRAG/.venv/bin/python -m pytest \
backend/LightRAG/tests/test_teaching_move_planner.py \
backend/LightRAG/tests/test_lesson_runtime.py \
backend/LightRAG/tests/test_lesson_smoke_scripts.py -q
```

Result: `369 passed`

```bash
PEPTUTOR_TEST_GOAL_ID=runtime-state-shadow-audit-verify \
PEPTUTOR_TEST_GOAL_TYPE=backend \
PEPTUTOR_TEST_BUDGET_OVERRIDE_REASON="verify return_anchor None contract fix after failed P5.9.3b L3 smoke" \
bash scripts/smoke_lesson_regression_20.sh
```

Result: PASS.

## Full Smoke Result

Latest smoke report generated locally:

- `temp/lesson-smoke-artifacts/lesson_smoke_matrix_20260504_151754.json`

Summary:

```text
page_count=20
turn_count=160
fallback_count=0
http_error_count=0
state_drift_count=0
issue_count=0
acceptance_passed=true
```

This confirms the previous `return_anchor=None` 400 regression is resolved.

## Follow-up Audits Generated Locally

These reports were generated locally as verification artifacts and are intentionally not committed as report payloads:

- `temp/lesson-smoke-artifacts/teaching_move_audit_20260504_152611.json`
- `temp/lesson-smoke-artifacts/classroom_quality_audit_20260504_152615.json`
- `temp/lesson-smoke-artifacts/redirect_experience_audit_20260504_152620.json`
- `temp/lesson-smoke-artifacts/runtime_state_minimal_view_shadow_audit_20260504_152627.json`

Audit summaries:

```text
TeachingMove audit passed=true
teaching_action_semantic_warning_count=0
Classroom quality audit passed=true
bad_anchor_candidate_count=0
review_target_phrase_count=0
target_phrase_revision_candidate_count=0
Shadow audit generated=true
minimal_view_missing_count=0
```

Redirect experience audit remained diagnostic-only:

```text
missing_scaffold_translation=3
needs_runtime_review=1
normal_test_artifact=5
overloaded_redirect=1
```

## Budget

```text
full_20_page smoke runs=1
browser smoke runs=0
deep smoke runs=0
```

The full smoke used Test Budget Guard override with reason:

```text
verify return_anchor None contract fix after failed P5.9.3b L3 smoke
```

## Non-goals Confirmed

- Did not change live prompt.
- Did not switch answer_turn_policy to the minimal runtime state view.
- Did not change RAG.
- Did not change S4.
- Did not change P49/classification.
- Did not change P13 answer_scope.
- Did not change the smoke matrix.
- Did not change student-visible replies.
- Did not add page_uid or smoke-input special cases.
