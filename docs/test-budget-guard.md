# PepTutor Test Budget Guard

This guard applies to PepTutor `/goal` work. It keeps validation proportional to the change and prevents repeated full-smoke runs after every patch.

## Validation Ladder

### L1: Local Change Validation

Use for most code and audit changes.

- Run related unit tests.
- Run related lint/type checks.
- Do not run the full 20-page lesson smoke.
- Do not run browser or deep smoke.

Examples:

- Runtime helper change: targeted `test_lesson_runtime.py` cases plus ruff on touched files.
- Audit script change: `test_lesson_smoke_scripts.py` plus ruff on the script and tests.
- Documentation-only change: `git diff --check` or no executable test if no code changed.

### L2: Target-Page Validation

Use when a change affects one route, one page family, or one visible-reply pattern.

- Run target-page or direct route-contract checks only.
- Do not run the full 20-page lesson smoke.
- Do not run browser or deep smoke unless the change is frontend/S4-specific.

Examples:

- One P13 boundary repair: direct P13 turn checks.
- One phonics redirect fix: P6 unit/runtime checks.
- One visible target-scaffold repair: target pages only.

### L3: Final Acceptance

Use once at the end of a goal when the change can affect shared runtime behavior.

- Run the full 20-page lesson smoke at most once.
- Run browser smoke at most once only for frontend, S4, TTS, Live2D, or browser harness changes.
- Run deep browser smoke at most once only when the change specifically requires deep S4/TTS/Live2D evidence.

Do not rerun the full 20-page smoke after every patch. If L3 fails, fix with L1/L2 first, then run one final L3 again only after the failure mode is isolated.

## Required Completion Report

Every `/goal` completion report must include:

- Full 20-page smoke runs: count and latest report path if any.
- Browser smoke runs: count and latest report path if any.
- Deep smoke runs: count and latest report path if any.
- Estimated LLM token cost caused by this goal.
- Whether the goal exceeded the test budget.

## Executable Guard

The smoke wrappers enforce this budget before starting any backend, frontend,
browser, deep observer, or LLM-consuming smoke.

Required environment:

- `PEPTUTOR_TEST_GOAL_ID`: stable id for the current `/goal`. It is used as
  the budget metadata filename, so it must not contain slashes or `..`.
- `PEPTUTOR_TEST_GOAL_TYPE`: required for browser/deep smoke. Browser smoke
  only allows goal types containing `frontend`, `s4`, or `browser`. Deep smoke
  only allows goal types containing `deep`, `s4`, `tts`, or `live2d`.

Override environment:

- `PEPTUTOR_TEST_BUDGET_OVERRIDE_REASON`: required for a second run of the
  same smoke type under the same goal id. This should only be used after a
  failing L3 has been isolated by L1/L2 checks.

Metadata:

- Each allowed smoke writes
  `temp/lesson-smoke-artifacts/test-budget/<goal_id>.json`.
- The metadata records `goal_id`, `goal_type`, `smoke_type`, `run_count`,
  `timestamp`, `override_reason`, `report_path`, `runs_by_type`, and the
  per-run history.

## Current Budget Defaults

- Documentation or read-only audit: L1 only.
- Backend deterministic helper: L1, plus L2 if visible behavior is touched.
- Backend shared runtime behavior: L1 + L2 + one L3 final smoke.
- Frontend/S4/browser harness: L1 + one browser smoke; add deep smoke only for S4/TTS/Live2D evidence.
