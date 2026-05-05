# PepTutor Progress

Updated: 2026-05-05

## Current Working Context

Project: PepTutor

Primary local project path:

```text
/root/my-project/PepTutor
```

Latest git working clone used for PR verification:

```text
/tmp/peptutor-main-postmerge
```

GitHub repository:

```text
https://github.com/rootliuat/PepTutor
```

Current verified `main` commit after PR #8 merge:

```text
963252585b8a951db269a68f1cf8e616d4abdd6a
```

## Most Recent Goal

Goal:

Merge PR #8 and verify that the S3 Mili visible tone changes, frontend Sidebar/TTS state display, and manual test checklist are ready for manual classroom testing.

PR:

```text
https://github.com/rootliuat/PepTutor/pull/8
```

Status:

```text
MERGED
```

PR #8 merged branch:

```text
s3-mili-visible-tone-manual-prep-20260504
```

## What PR #8 Added

PR #8 prepared the project for manual S3 Mili classroom testing.

Main changes:

- Improved visible classroom redirect replies for selected safe cases.
- Made replies more aligned with Mili's desired teaching shape:
  - warm acknowledgement;
  - short Chinese scaffold;
  - clear English target;
  - one next action.
- Added frontend state display so manual testers can inspect classroom/TTS state.
- Added manual testing checklist:

```text
docs/manual-test-s3-mili-tts-20260504.md
```

Important boundaries preserved:

- Did not change RAG.
- Did not change P49/classification policy.
- Did not change P13 answer_scope data.
- Did not change smoke matrix.
- Did not inject full `soul.md`.
- Did not inject Mili interests into every classroom prompt.
- Did not add page_uid special cases.
- Did not add smoke-input special cases.
- Did not add fixed deterministic teacher reply templates.

## Validation Results After PR #8 Merge

### Backend L1

Command run:

```bash
PEPTUTOR_TEST_GOAL_ID=pr8-post-merge-clean-verification \
PYTHONPATH=/tmp/peptutor-main-postmerge/backend/LightRAG \
/root/my-project/PepTutor/backend/LightRAG/.venv/bin/python -m pytest \
backend/LightRAG/tests/test_teaching_move_planner.py \
backend/LightRAG/tests/test_lesson_runtime.py \
backend/LightRAG/tests/test_lesson_smoke_scripts.py -q
```

Result:

```text
395 passed in 34.98s
```

Ruff result:

```text
All checks passed!
```

### Frontend Targeted Tests And Typecheck

Targeted Vitest:

```text
3 test files passed
35 tests passed
```

Typecheck:

```text
@proj-airi/stage-ui typecheck: passed
@proj-airi/stage-layouts typecheck: passed
```

### Full 20-page Smoke

Goal ID:

```text
pr8-post-merge-clean-verification
```

Full smoke run count:

```text
1
```

Report:

```text
temp/lesson-smoke-artifacts/lesson_smoke_matrix_20260505_010901.json
```

Summary:

```text
page_count=20
turn_count=160
http_error_count=0
fallback_count=0
state_drift_count=0
issue_count=0
acceptance_passed=true
```

### Audits Generated

TeachingMove audit:

```text
temp/lesson-smoke-artifacts/teaching_move_audit_20260505_011733.json
```

Result:

```text
audit_passed=true
teaching_action_semantic_warning_count=0
```

Classroom quality audit:

```text
temp/lesson-smoke-artifacts/classroom_quality_audit_20260505_011742.json
```

Result:

```text
audit_passed=true
target_phrase_revision_candidate_count=0
bad_anchor_candidate_count=0
review_target_phrase_count=0
```

Redirect experience audit:

```text
temp/lesson-smoke-artifacts/redirect_experience_audit_20260505_011751.json
```

Result:

```text
audit_passed=true
experience_classification_counts={
  needs_runtime_review: 1,
  normal_test_artifact: 7,
  overloaded_redirect: 2
}
```

Important:

```text
P13 answer_scope_issue is 0 in this redirect audit.
```

Token audit:

```text
temp/lesson-smoke-artifacts/llm_token_usage_audit_20260505_011800.json
```

Summary:

```text
total_llm_calls=250
avg_prompt_tokens=1947
p95_prompt_tokens=3172
max_prompt_tokens=3583
```

Context breakdown audit:

```text
temp/lesson-smoke-artifacts/llm_context_breakdown_audit_20260505_011800.json
```

Important:

```text
unknown_context_bytes=0
```

Persona consistency audit:

```text
temp/lesson-smoke-artifacts/mili_persona_consistency_audit_20260505_011812.json
```

Result:

```text
audit_passed=true
full_soul_leak_count=0
interest_leak_count=0
sample_line_copy_count=0
answer_turn_policy_injected_call_count=75
llm_only_injected_call_count=0
deterministic_injected_turn_count=0
```

## Current Blocker

The PR #8 clean verification goal is not fully complete because browser smoke was run once and failed before browser assertions started.

Browser smoke report:

```text
temp/lesson-smoke-artifacts/lesson_browser_smoke_20260505_011706.json
```

Result:

```text
status=failed
acceptance_passed=false
browser_exit_code=1
browser_test_counts={passed: 0, failed: 0, skipped: 0}
```

Failure reason:

```text
Cannot find module '/.local/share/pnpm/store/.../vitest.mjs'
```

Interpretation:

- This is a local pnpm/Vitest binary path resolution problem.
- Browser assertions did not actually run.
- It is not evidence of a lesson runtime failure.
- Because the goal allowed browser smoke at most once, it must not be rerun under the same goal.

Budget status for `pr8-post-merge-clean-verification`:

```text
full smoke=1
browser smoke=1
deep smoke=0
```

## Current Project State

Ready:

- PR #8 is merged into `main`.
- Backend L1 is green.
- Frontend targeted tests and typecheck are green.
- Full 20-page backend smoke is green.
- TeachingMove audit passes.
- Classroom quality audit passes.
- Redirect audit passes and has no P13 answer_scope_issue.
- Persona audit passes with no full soul, interest, or sample-line leak.
- Manual testing checklist exists and covers required pages.

Not fully ready:

- Browser smoke needs a separate infrastructure closure because the single allowed browser run failed due pnpm/Vitest path resolution.

## Manual Test Checklist

Manual test file:

```text
docs/manual-test-s3-mili-tts-20260504.md
```

It covers these pages:

```text
TB-G5S1U3-P22
TB-G6S1U1-P4
TB-G6S2U1-P4
TB-G5S1U3-P31
TB-G5S2U1-P6
TB-G6S2U2-P13
```

It includes:

- test inputs;
- expected teacher behavior;
- expected TTS / Sidebar state;
- manual observation points:
  - whether Mili feels like a real teacher;
  - whether the reply is overloaded;
  - whether the reply is mechanical;
  - whether the lesson runs off textbook route;
  - whether TTS plays;
  - whether interrupt behavior is normal;
  - whether mouthOpen moves incorrectly.

## Recommended Next Goal

Next goal should not add classroom features.

Recommended next goal:

```text
Browser Smoke pnpm/Vitest Bin Path Closure
```

Purpose:

- Fix the local pnpm/Vitest binary path resolution issue.
- Do not change lesson runtime, prompt, RAG, S4 behavior, P49, P13, persona, or matrix.
- Run only frontend/browser infrastructure checks.
- Allow exactly one browser smoke after the fix.
- Keep full smoke at 0 for this new goal unless explicitly needed later.

Expected scope:

- Inspect frontend pnpm scripts and browser smoke wrapper.
- Fix the path issue that resolves Vitest as `/.local/...` instead of `/root/.local/...`.
- Prefer a wrapper-safe invocation that uses the repository's pnpm/node resolution.
- Do not modify classroom-visible behavior.
- Do not modify backend lesson routing.

After browser infra closure:

- Run one browser smoke with a new goal id.
- If it passes, manual test readiness is complete.

## Browser/Vite Local Startup Fix

Updated after local startup failure on 2026-05-05.

Observed local failure:

```text
Cannot find module '/root/root/.local/share/pnpm/store/.../vite.js'
```

Related browser smoke failure:

```text
Cannot find module '/.local/share/pnpm/store/.../vitest.mjs'
```

Root cause:

- pnpm-generated package-local `.bin` shims under `frontend/airi/apps/stage-web/node_modules/.bin/` use brittle deep relative paths.
- In this WSL/root layout, those paths resolve incorrectly to `/root/root/.local/...` or `/.local/...`.
- Vite/Vitest packages are installed; the issue is only the shim path.

Local fix applied in `/root/my-project/PepTutor`:

```text
frontend/airi/scripts/resolve-node-bin.mjs
scripts/start_lesson_dev.sh
frontend/airi/scripts/run-lesson-browser-real-smoke.sh
frontend/airi/scripts/dev-lesson-https.sh
scripts/smoke_lesson_deep_browser.sh
```

Validation:

```text
vite/8.0.0-beta.15 resolved and runs
vitest/4.0.18 resolved and runs
scripts/start_lesson_dev.sh reached Vite ready at http://localhost:5173/
```

GitHub PR for the same fix:

```text
https://github.com/rootliuat/PepTutor/pull/9
```

Branch:

```text
browser-vitest-bin-path-closure-20260505
```

PR #9 validation performed:

```text
bash -n scripts/start_lesson_dev.sh scripts/smoke_lesson_deep_browser.sh frontend/airi/scripts/run-lesson-browser-real-smoke.sh frontend/airi/scripts/dev-lesson-https.sh
node frontend/airi/scripts/resolve-node-bin.mjs vite bin/vite.js frontend/airi/apps/stage-web
node frontend/airi/scripts/resolve-node-bin.mjs vitest vitest.mjs frontend/airi/apps/stage-web
node <resolved vite> --version
node <resolved vitest> --version
```

Smoke budget for this fix:

```text
full smoke=0
browser smoke=0
deep smoke=0
```

After PR #9 is merged, run at most one browser smoke with a fresh goal id.

## PR #9 Merge And Follow-up Browser Smoke Attempt

Updated: 2026-05-05 07:55.

PR #9:

```text
https://github.com/rootliuat/PepTutor/pull/9
```

Status:

```text
MERGED
```

Main commit after merge:

```text
7d6c98c60cb416a78483a684b1b796dfaae3306b
```

Goal id used:

```text
manual-test-readiness-browser-infra-closure
```

Budget used:

```text
full smoke=0
browser smoke=1
deep smoke=0
```

Browser smoke command attempted:

```bash
PEPTUTOR_TEST_GOAL_ID=manual-test-readiness-browser-infra-closure \
PEPTUTOR_TEST_GOAL_TYPE=frontend,s4,browser \
NO_PROXY=127.0.0.1,localhost,::1 \
bash scripts/smoke_lesson_browser.sh
```

Result:

```text
FAILED before backend/browser startup
```

Failure:

```text
Missing LightRAG server binary: /tmp/peptutor-main-postmerge/backend/LightRAG/.venv/bin/lightrag-server
Install backend/LightRAG/.venv first.
```

Interpretation:

- PR #9 fixed the pnpm/Vite/Vitest path problem.
- The next browser-smoke attempt did not reach that part of the flow.
- It failed earlier because the Git working clone `/tmp/peptutor-main-postmerge` did not have `backend/LightRAG/.venv`.
- The shared venv still exists at `/root/my-project/PepTutor/backend/LightRAG/.venv`.
- Because browser smoke was already counted once for this goal, do not rerun under the same goal.

Next required goal:

```text
Browser Smoke Backend Venv Preflight Closure
```

Recommended next action:

- Create or restore the project-local LightRAG venv in the Git working clone, or make the browser smoke wrapper fail before budget accounting when the server binary is missing.
- Use a new goal id.
- Do not run full smoke.
- Run browser smoke at most once after preflight is corrected.

## Browser Smoke Budget Preflight PR

Updated: 2026-05-05 08:00.

After the missing `.venv` failure, a small browser smoke wrapper fix was prepared so missing backend binaries fail before Test Budget Guard accounting.

PR:

```text
https://github.com/rootliuat/PepTutor/pull/11
```

Status:

```text
MERGED
```

Main commit after merge:

```text
7014b1e
```

Branch:

```text
browser-smoke-preflight-before-budget-20260505
```

Commit:

```text
c377e58
```

Change:

```text
scripts/smoke_lesson_browser.sh
```

What changed:

- Check `backend/LightRAG/.venv/bin/lightrag-server` before calling `peptutor_test_budget_guard`.
- Check `wait-for-lesson-backend.sh` before budget accounting.
- Select backend port before budget accounting.
- Keep actual browser smoke behavior unchanged after preflight passes.

Validation:

```bash
bash -n scripts/smoke_lesson_browser.sh
PEPTUTOR_TEST_GOAL_ID=browser-preflight-no-budget-test \
PEPTUTOR_TEST_GOAL_TYPE=frontend,s4,browser \
bash scripts/smoke_lesson_browser.sh
```

Expected result:

```text
Missing LightRAG server binary: /tmp/peptutor-main-postmerge/backend/LightRAG/.venv/bin/lightrag-server
Install backend/LightRAG/.venv first.
NO_BUDGET_WRITTEN
```

Smoke budget for PR #11:

```text
full smoke=0
browser smoke=0 guard-counted
deep smoke=0
```

Next step after PR #11:

- Restore or create `backend/LightRAG/.venv` in the Git working clone.
- Use a fresh goal id for exactly one browser smoke.

## New Conversation Bootstrap Prompt

Use this prompt at the start of the next conversation:

```text
We are working on PepTutor at /root/my-project/PepTutor, with the GitHub repo rootliuat/PepTutor.

Latest verified git clone used for PR work was /tmp/peptutor-main-postmerge.
Main now includes PR #8:
https://github.com/rootliuat/PepTutor/pull/8

Main commit after merge:
963252585b8a951db269a68f1cf8e616d4abdd6a

PR #8 prepared S3 Mili visible tone and manual testing:
- classroom replies use warmer Mili-style visible tone where safe;
- replies aim for warm ack, short Chinese scaffold, clear English target, one action;
- frontend Sidebar exposes teaching_action, target_role, expected_student_action, speech_style, interrupt/TTS state, persona capsule status;
- manual test checklist exists at docs/manual-test-s3-mili-tts-20260504.md.

Do not change RAG, P49/classification, P13 answer_scope data, smoke matrix, full soul.md injection, persona interests, page_uid special cases, smoke input special cases, or deterministic fixed teacher reply templates.

Clean verification after PR #8:
- Backend L1: 395 passed.
- Ruff: passed.
- Frontend targeted Vitest: 35 passed.
- stage-ui typecheck: passed.
- stage-layouts typecheck: passed.
- Full 20-page smoke ran exactly once and passed:
  temp/lesson-smoke-artifacts/lesson_smoke_matrix_20260505_010901.json
  page_count=20, turn_count=160, http=0, fallback=0, drift=0, issue=0.
- TeachingMove audit passed:
  temp/lesson-smoke-artifacts/teaching_move_audit_20260505_011733.json
- Classroom quality audit passed:
  temp/lesson-smoke-artifacts/classroom_quality_audit_20260505_011742.json
- Redirect audit passed and P13 answer_scope_issue is 0:
  temp/lesson-smoke-artifacts/redirect_experience_audit_20260505_011751.json
- Persona audit passed with no full_soul/interests/sample-line leak:
  temp/lesson-smoke-artifacts/mili_persona_consistency_audit_20260505_011812.json
- Token/context audits:
  temp/lesson-smoke-artifacts/llm_token_usage_audit_20260505_011800.json
  temp/lesson-smoke-artifacts/llm_context_breakdown_audit_20260505_011800.json
  unknown_context_bytes=0.

Current blocker:
Browser smoke was allowed once in the clean verification goal and failed before browser assertions due local pnpm/Vitest bin path resolution:
Cannot find module '/.local/share/pnpm/store/.../vitest.mjs'
Report:
temp/lesson-smoke-artifacts/lesson_browser_smoke_20260505_011706.json

This is not a classroom runtime failure. It is a browser smoke infrastructure issue.

Next task should be:
Browser Smoke pnpm/Vitest Bin Path Closure.

Rules for next task:
- Do not add classroom functionality.
- Do not change lesson runtime behavior.
- Do not change prompt, RAG, S4 playback behavior, P49, P13, persona, or smoke matrix.
- Fix only browser smoke execution infrastructure.
- Use a fresh PEPTUTOR_TEST_GOAL_ID.
- Do not run full smoke.
- Run browser smoke at most once after the infra fix.
- Deep smoke must remain 0.
```
