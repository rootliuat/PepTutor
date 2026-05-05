# PepTutor Progress

Updated: 2026-05-05

## Current Working Context

Project: PepTutor

Primary local project path:

```text
/root/my-project/PepTutor
```

## P0-P5 Long Task State

Updated: 2026-05-05 11:22 CST.

This is the current handoff state for the P0-P5 long task: start the project first, then verify browser testing, then prepare and execute manual classroom observation, then classify only real issues, and only then choose a minimal visible-experience fix.

### Current Local Dev Stack

Local startup is working on this machine:

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

Verified endpoints:

```text
backend catalog: http://127.0.0.1:9625/lesson/catalog -> 200
frontend lesson: http://127.0.0.1:5173/lesson -> 200
```

The dev stack was running during the latest manual technical observation:

```text
scripts/start_lesson_dev.sh
lightrag-server on port 9625
Vite on port 5173
```

### P0 Startup Closure

Status:

```text
done
```

Evidence:

- PR #9 fixed brittle Vite/Vitest pnpm bin path resolution.
- PR #11 made browser-smoke preflight fail before Test Budget Guard accounting when required backend binaries are missing.
- Local frontend workspace node_modules/symlinks were repaired.
- `./scripts/start_lesson_dev.sh` starts backend and frontend.
- The earlier `Cannot find module '/root/root/.local/.../vite.js'` startup failure is closed for this machine.

### Previous Startup / Browser Failures

These were real blockers and are now recorded so they are not rediscovered as vague "project cannot start" failures:

| goal id | result | failure | resolution |
| --- | --- | --- | --- |
| `pr8-post-merge-clean-verification` | browser smoke failed before assertions | bad pnpm Vitest shim path like `/.local/.../vitest.mjs` | PR #9 stable Node bin resolver |
| `manual-test-readiness-browser-infra-closure` | failed before browser startup | missing `backend/LightRAG/.venv/bin/lightrag-server` in Git working clone | PR #11 preflight before budget accounting; local venv restored where needed |
| `browser-venv-preflight-closure` | failed before tests | frontend `node_modules` missing in working clone | use local project with materialized frontend deps |
| `browser-frontend-node-modules-closure` | failed during import | workspace package symlinks pointed at clone without built package entries | `pnpm install --offline --ignore-scripts` repaired local symlinks |
| `browser-post-symlink-closure` | failed during import | Vite optimized deps during browser-test import and reloaded test context | stage-web browser Vitest optimizeDeps closure |
| `browser-optimize-deps-closure` | passed | none | current browser smoke baseline |

### P1 Browser Smoke Closure

Status:

```text
done
```

Latest passing report:

```text
temp/lesson-smoke-artifacts/lesson_browser_smoke_20260505_101008.json
```

Result:

```text
status=passed
acceptance_passed=true
browser_test_counts={passed:10, failed:0, skipped:21}
real_backend_passed=10
mock_suite_skipped=21
skipped_due_real_backend_mode=21
```

Budget note:

```text
No full 20-page smoke and no deep smoke were run for this closure path.
Multiple browser smoke attempts happened under separate goal ids because each exposed and then closed a distinct infrastructure blocker.
```

### P2 Manual Test Preparation

Status:

```text
done
```

Checklist:

```text
docs/manual-test-s3-mili-tts-20260504.md
```

The checklist covers:

- `TB-G5S1U3-P22`
- `TB-G6S1U1-P4`
- `TB-G6S2U1-P4`
- `TB-G5S1U3-P31`
- `TB-G5S2U1-P6`
- `TB-G6S2U2-P13`

Each page has test inputs, expected teacher behavior, expected Sidebar/TTS state, and human observation points.

### P3 Manual Test Execution

Status:

```text
technical observation completed; human audio/visual judgement still pending
```

Records:

```text
temp/lesson-smoke-artifacts/manual_test_s3_mili_tts_20260505.md
docs/manual-test-record-s3-mili-tts-20260505.md
```

What has been observed through the live browser UI:

- learner input
- teacher response text
- Sidebar route/action/speech/persona/interrupt/TTS fields
- TTS synthesis/playback state
- stop reason / overlap state
- mechanical / overloaded / off-route flags
- first-pass issue classification and owner

What still needs human judgement:

- spoken TTS quality;
- mouthOpen naturalness;
- whether Mili feels like a real teacher in actual use.

### P4 Issue Classification

Status:

```text
initial technical classification complete
```

Current issue table:

| page_uid | classification | status |
| --- | --- | --- |
| `TB-G5S1U3-P22` | acceptable S3 visible reply | no fix |
| `TB-G6S1U1-P4` | redirect helper / TeachingMove target-action issue | next visible-experience candidate |
| `TB-G6S2U1-P4` | acceptable S3 visible reply | no fix |
| `TB-G5S1U3-P31` | acceptable story scaffold | no fix |
| `TB-G5S2U1-P6` | acceptable phonics scaffold; `cl' as in` absent | no fix |
| `TB-G6S2U2-P13` | acceptable vocab return; monitor rag_plus_llm return-anchor boundary | no immediate fix |

The only concrete P5 candidate from the technical pass is `TB-G6S1U1-P4`: off-topic input can still collapse the location dialogue into the noun phrase `museum shop`. Any fix must be a public question/answer target-action rule, not a page_uid or smoke-input special case.

### P5 Minimal Fix / Demo Package

Status:

```text
L1 implementation complete; PR #13 merged; demo handoff package written
```

Implemented local slice:

```text
Public location question/answer target-action preservation.
```

Local files touched:

```text
backend/LightRAG/lightrag/pedagogy/redirect_reply_policy.py
backend/LightRAG/tests/test_lesson_runtime.py
backend/LightRAG/tests/test_lesson_smoke_scripts.py
```

Validation:

```text
Focused P5 regression: 8 passed.
L1 pytest: 387 passed.
Ruff: All checks passed.
full smoke=0
browser smoke=0
deep smoke=0
```

What changed:

- `target_role=phrase` with a reliable location `question_target` and `answer_frame=It's near ...` renders the question/answer frame instead of falling back to a noun phrase.
- Valid `where ...?` question contracts with `It's near ...` answer frames can use the answer frame.
- Empty-slot questions like `Where is the ?` still do not pass the safe frame gate.
- No page_uid or smoke-input special cases were added.

Merged GitHub PR:

```text
https://github.com/rootliuat/PepTutor/pull/13
```

Main commit:

```text
a1b7cb7b76397c56be3510e55e670ec52046bd28
```

Post-merge validation:

```text
L1 pytest: 396 passed.
Ruff: All checks passed.
full smoke=0
browser smoke=0
deep smoke=0
```

Demo handoff:

```text
docs/demo-handoff-p0-p5-20260505.md
```

Still pending:

- human audio/visual judgement;
- optional browser/manual re-observation under a fresh budgeted goal.

Scope constraints:

- no RAG changes;
- no P49/classification changes;
- no P13 answer_scope data changes;
- no smoke matrix changes;
- no full `soul.md` prompt injection;
- no Mili interest chatter in classroom replies;
- no page_uid special cases;
- no smoke-input special cases;
- no fixed deterministic teacher reply templates;
- no full/browser/deep smoke unless a new goal explicitly budgets it.

### Current Long Task Checklist

Standalone checklist:

```text
docs/p0-p5-long-task-checklist-20260505.md
```

Next concrete tasks:

1. Get human judgement for TTS quality, mouthOpen naturalness, and visible teacher-likeness using `docs/manual-test-s3-mili-tts-20260504.md`.
2. Optionally re-observe `TB-G6S1U1-P4` in browser/manual mode under a fresh budgeted goal.

Latest git working clone used for PR verification:

```text
/tmp/peptutor-main-postmerge
```

GitHub repository:

```text
https://github.com/rootliuat/PepTutor
```

Current verified GitHub `main` commit after PR #12 evidence handoff merge:

```text
1e1813bfda56914a5f8fba51ab1484ae6814c52d
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

## Browser Venv Preflight Closure Attempt

Updated: 2026-05-05 09:52.

Git working clone:

```text
/tmp/peptutor-main-postmerge
```

Main commit:

```text
7014b1e
```

Action:

- Restored `backend/LightRAG/.venv` in the Git working clone by linking to the existing local venv:

```bash
ln -s /root/my-project/PepTutor/backend/LightRAG/.venv /tmp/peptutor-main-postmerge/backend/LightRAG/.venv
```

Verified:

```text
backend/LightRAG/.venv/bin/lightrag-server --help
```

Goal id:

```text
browser-venv-preflight-closure
```

Browser smoke command:

```bash
PEPTUTOR_TEST_GOAL_ID=browser-venv-preflight-closure \
PEPTUTOR_TEST_GOAL_TYPE=frontend,s4,browser \
NO_PROXY=127.0.0.1,localhost,::1 \
bash scripts/smoke_lesson_browser.sh
```

Budget:

```text
full smoke=0
browser smoke=1
deep smoke=0
```

Report:

```text
temp/lesson-smoke-artifacts/lesson_browser_smoke_20260505_095207.json
```

Result:

```text
status=failed
acceptance_passed=false
browser_exit_code=1
browser_test_counts={passed:0, failed:0, skipped:0}
```

What improved:

- Backend started successfully.
- `/lesson/catalog` became ready.
- The previous missing `.venv` preflight failure is resolved.
- The previous bad pnpm shim path failure is not the active blocker anymore.

Current failure:

```text
Error: Cannot find module 'vitest/package.json'
Require stack:
- /tmp/peptutor-main-postmerge/frontend/airi/apps/stage-web/package.json
WARN Local package.json exists, but node_modules missing, did you mean to install?
```

Interpretation:

- This Git working clone lacks frontend `node_modules`.
- Browser tests still did not execute.
- The failure is frontend dependency/materialization, not classroom runtime.
- Do not rerun browser smoke under `browser-venv-preflight-closure`; budget is already consumed.

Next required goal:

```text
Browser Smoke Frontend Node Modules Closure
```

Recommended next action:

- Restore or materialize `frontend/airi/node_modules` and workspace package node_modules in the Git working clone without running expensive smoke first.
- Avoid `pnpm install` if it triggers heavy postinstall downloads; prefer linking or reusing the known working `/root/my-project/PepTutor/frontend/airi/node_modules` if appropriate.
- Use a fresh goal id.
- Run browser smoke at most once after dependency materialization is verified with cheap `node scripts/resolve-node-bin.mjs vitest vitest.mjs apps/stage-web`.

## P0/P1 Manual Readiness Attempt

Updated: 2026-05-05 10:05.

Goal:

```text
P0 startup closure + P1 browser smoke closure
```

Local project path:

```text
/root/my-project/PepTutor
```

What was verified before browser smoke:

```bash
cd /root/my-project/PepTutor/frontend/airi
node scripts/resolve-node-bin.mjs vite bin/vite.js apps/stage-web
node scripts/resolve-node-bin.mjs vitest vitest.mjs apps/stage-web
```

Result:

```text
vite resolved to /root/.local/share/pnpm/store/v10/links/@/vite/8.0.0-beta.15/.../node_modules/vite/bin/vite.js
vitest resolved to /root/.local/share/pnpm/store/v10/links/@/vitest/4.0.18/.../node_modules/vitest/vitest.mjs
```

Browser smoke goal id:

```text
browser-frontend-node-modules-closure
```

Browser smoke command:

```bash
PEPTUTOR_TEST_GOAL_ID=browser-frontend-node-modules-closure \
PEPTUTOR_TEST_GOAL_TYPE=frontend,s4,browser \
NO_PROXY=127.0.0.1,localhost,::1 \
bash scripts/smoke_lesson_browser.sh
```

Budget:

```text
full smoke=0
browser smoke=1
deep smoke=0
```

Report:

```text
temp/lesson-smoke-artifacts/lesson_browser_smoke_20260505_100334.json
```

Result:

```text
status=failed
acceptance_passed=false
browser_exit_code=1
browser_test_counts={passed:0, failed:0, skipped:0}
```

What improved:

- Browser smoke no longer failed on missing backend `.venv`.
- Browser smoke no longer failed on missing `vitest/package.json`.
- Backend started successfully.
- `/lesson/catalog` became ready.
- Real-browser Vitest process started.

Failure observed during the single allowed browser smoke:

```text
Failed to resolve entry for package "@proj-airi/pipelines-audio"
Failed to resolve entry for package "@proj-airi/stream-kit"
```

Root cause:

```text
frontend/airi/apps/stage-web/node_modules/@proj-airi/*
frontend/airi/packages/stage-ui/node_modules/@proj-airi/*
frontend/airi/packages/stage-layouts/node_modules/@proj-airi/*
```

had workspace symlinks pointing at:

```text
/tmp/peptutor-main-postmerge/frontend/airi/packages/*
```

That Git clone did not contain built `dist` outputs for packages such as:

```text
@proj-airi/stream-kit
@proj-airi/pipelines-audio
```

Local dependency closure performed after the failed browser smoke:

```bash
cd /root/my-project/PepTutor/frontend/airi
pnpm install --offline --ignore-scripts
```

Why this was safe:

- It did not edit source files.
- It did not run frontend postinstall hooks.
- It repaired local workspace symlinks only.

Post-fix evidence:

```bash
cd /root/my-project/PepTutor/frontend/airi/apps/stage-web
node -e "import('@proj-airi/stream-kit').then(m=>console.log(Object.keys(m).slice(0,5)))"
node -e "import('@proj-airi/pipelines-audio').then(m=>console.log(Object.keys(m).slice(0,8)))"
```

Result:

```text
@proj-airi/stream-kit import: ok
@proj-airi/pipelines-audio import: ok
```

P0 startup command verified after symlink repair:

```bash
cd /root/my-project/PepTutor
timeout 18s bash scripts/start_lesson_dev.sh
```

Result:

```text
backend ready after 2s: http://127.0.0.1:9625/lesson/catalog
VITE v8.0.0-beta.15 ready
Local: http://localhost:5173/
lesson URL: http://127.0.0.1:5173/lesson
```

Current status:

- P0 local startup is closed for the current machine.
- P1 browser smoke is not closed because the single allowed browser run happened before symlink repair and failed before tests executed.
- Do not rerun browser smoke under `browser-frontend-node-modules-closure`; that budget is consumed.

Next required goal:

```text
Browser Smoke Post-Symlink Closure
```

Rules for that next goal:

- Use a fresh goal id.
- Do not run full smoke.
- Do not run deep smoke.
- Run browser smoke at most once.
- Browser smoke should now reach real test execution because workspace package symlinks have been repaired.

## Browser Smoke Post-Symlink Closure

Updated: 2026-05-05 10:12.

Goal id:

```text
browser-post-symlink-closure
```

Browser smoke command:

```bash
PEPTUTOR_TEST_GOAL_ID=browser-post-symlink-closure \
PEPTUTOR_TEST_GOAL_TYPE=frontend,s4,browser \
NO_PROXY=127.0.0.1,localhost,::1 \
bash scripts/smoke_lesson_browser.sh
```

Budget:

```text
full smoke=0
browser smoke=1
deep smoke=0
```

Report:

```text
temp/lesson-smoke-artifacts/lesson_browser_smoke_20260505_100844.json
```

Result:

```text
status=failed
acceptance_passed=false
browser_test_counts={passed:0, failed:0, skipped:0}
```

What improved:

- The previous workspace package entry failures for `@proj-airi/stream-kit` and `@proj-airi/pipelines-audio` were gone.
- Browser Vitest imported further into the test graph.

Failure:

```text
Vite optimized new dependencies during test import, then reloaded the browser test context.
The test import failed fetching an optimized vue-router dependency URL.
```

Fix applied:

```text
frontend/airi/apps/stage-web/vitest.browser.config.ts
```

The real-browser Vitest config now pre-includes the dependency set that was being discovered during test import, preventing Vite from reloading after the test starts.

Validation:

```bash
cd /root/my-project/PepTutor/frontend/airi
pnpm -F @proj-airi/stage-web typecheck
```

Result:

```text
passed
```

## Browser Optimize-Deps Closure

Updated: 2026-05-05 10:12.

Goal id:

```text
browser-optimize-deps-closure
```

Browser smoke command:

```bash
PEPTUTOR_TEST_GOAL_ID=browser-optimize-deps-closure \
PEPTUTOR_TEST_GOAL_TYPE=frontend,s4,browser \
NO_PROXY=127.0.0.1,localhost,::1 \
bash scripts/smoke_lesson_browser.sh
```

Budget:

```text
full smoke=0
browser smoke=1
deep smoke=0
```

Report:

```text
temp/lesson-smoke-artifacts/lesson_browser_smoke_20260505_101008.json
```

Result:

```text
status=passed
acceptance_passed=true
browser_test_counts={passed:10, failed:0, skipped:21}
browser_suite_summary={
  real_backend_passed: 10,
  real_backend_failed: 0,
  real_backend_skipped: 0,
  mock_suite_skipped: 21,
  skipped_due_real_backend_mode: 21
}
```

Important evidence:

- Real backend browser suite passed.
- S4.1 barge-in evidence was collected.
- S4.1 finish-current-sentence evidence was collected.
- Screenshot, network events, history debug, and DOM snapshot artifacts were collected.

P0/P1 status:

```text
P0 startup closure: done
P1 browser smoke closure: done
```

Known browser infra note:

```text
The browser log still prints non-fatal optimizeDeps warnings for a few nested dependencies that are not resolvable from stage-web root. The suite passes, so this is a cleanup candidate, not a blocker.
```

## Manual Test Preparation Closure

Updated: 2026-05-05 10:12.

Manual checklist:

```text
docs/manual-test-s3-mili-tts-20260504.md
```

Status:

```text
ready for human manual testing
```

Verified checklist coverage:

- Startup command is documented.
- Browser entry URL is documented.
- `TB-G5S1U3-P22` has inputs, expected teacher behavior, expected Sidebar/TTS state, and observation items.
- `TB-G6S1U1-P4` has inputs, expected teacher behavior, expected Sidebar/TTS state, and observation items.
- `TB-G6S2U1-P4` has inputs, expected teacher behavior, expected Sidebar/TTS state, and observation items.
- `TB-G5S1U3-P31` has inputs, expected teacher behavior, expected Sidebar/TTS state, and observation items.
- `TB-G5S2U1-P6` has inputs, expected teacher behavior, expected Sidebar/TTS state, and observation items.
- `TB-G6S2U2-P13` has inputs, expected teacher behavior, expected Sidebar/TTS state, and observation items.

Next required phase:

```text
P3 manual test execution by a human observer
```

Reason:

```text
The remaining P3 checks require real human observation of classroom tone, spoken TTS quality, mouthOpen behavior, and whether Mili feels like a real teacher. Browser smoke proves the route and harness; it is not a substitute for the P3 manual observation report.
```

## P0-P5 Evidence Handoff

Updated: 2026-05-05 10:20.

Local required output paths:

```text
temp/lesson-smoke-artifacts/manual_test_s3_mili_tts_20260505.md
temp/lesson-smoke-artifacts/p0_p5_completion_audit_20260505.md
```

Tracked GitHub copies:

```text
docs/manual-test-record-s3-mili-tts-20260505.md
docs/p0-p5-completion-audit-20260505.md
```

Reason:

```text
temp/ is intentionally ignored by git, so docs/ copies preserve the handoff in the repository while the requested temp paths remain available locally.
```

## New Conversation Bootstrap Prompt

Use this prompt at the start of the next conversation:

```text
We are working on PepTutor at /root/my-project/PepTutor, with the GitHub repo rootliuat/PepTutor.

Latest verified git clone used for PR work was /tmp/peptutor-main-postmerge.
Main now includes PR #8, PR #9, PR #11, and PR #12:
- PR #8: S3 Mili visible tone/manual test prep
- PR #9: Vite/Vitest bin path resolver closure
- PR #11: browser smoke backend preflight before Test Budget Guard accounting
- PR #12: P0-P5 evidence handoff

Latest known main commit after PR #12:
1e1813bfda56914a5f8fba51ab1484ae6814c52d

PR #8 prepared S3 Mili visible tone and manual testing:
- classroom replies use warmer Mili-style visible tone where safe;
- replies aim for warm ack, short Chinese scaffold, clear English target, one action;
- frontend Sidebar exposes teaching_action, target_role, expected_student_action, speech_style, interrupt/TTS state, persona capsule status;
- manual test checklist exists at docs/manual-test-s3-mili-tts-20260504.md.

PR #9 fixed local Vite/Vitest bin path resolution:
- scripts/start_lesson_dev.sh now uses frontend/airi/scripts/resolve-node-bin.mjs;
- scripts/smoke_lesson_browser.sh route calls now resolve Vitest through the same stable resolver path;
- the old /root/root/.local pnpm-store path failure should not recur.

PR #11 fixed browser smoke budget accounting:
- missing backend server binary/wait-script/preflight failures happen before Test Budget Guard accounting.

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

Current state:
P0/P1 are now closed on /root/my-project/PepTutor:
- backend ready;
- Vite ready;
- lesson URL: http://127.0.0.1:5173/lesson.
- browser smoke passed after dependency symlink and optimizeDeps closure.

Latest browser smoke report:
temp/lesson-smoke-artifacts/lesson_browser_smoke_20260505_101008.json

Result:
- status=passed
- browser_test_counts={passed:10, failed:0, skipped:21}
- real_backend_passed=10
- mock_suite_skipped=21 because real backend mode skips the mock suite

Manual test checklist is ready:
docs/manual-test-s3-mili-tts-20260504.md

Technical manual observation record is filled:
temp/lesson-smoke-artifacts/manual_test_s3_mili_tts_20260505.md
docs/manual-test-record-s3-mili-tts-20260505.md

P4 initial classification:
- TB-G5S1U3-P22: acceptable.
- TB-G6S1U1-P4: visible redirect still collapses location dialogue to noun phrase museum shop; next candidate, only fix through public question/answer target-action rule.
- TB-G6S2U1-P4: acceptable.
- TB-G5S1U3-P31: acceptable.
- TB-G5S2U1-P6: acceptable, cl' as in absent.
- TB-G6S2U2-P13: acceptable vocab return; monitor rag_plus_llm return-anchor boundary.

P5 local L1 implementation:
- redirect_reply_policy.py now preserves public location question/answer frames when a validated contract is phrase-shaped but carries a reliable Where question and It's near ... answer frame.
- tests added in test_lesson_runtime.py.
- smoke-script tests were updated to match the stable node/vite resolver path instead of the old pnpm exec vite path.
- L1 pytest: 387 passed.
- Ruff: All checks passed.
- full/browser/deep smoke: 0.
- This P5 slice is not yet isolated into a clean GitHub PR.

Next task should be one of:
1. Human review of TTS quality, mouthOpen naturalness, and whether Mili feels like a real teacher.
2. Isolate the local P5 changes into a clean GitHub branch/PR.

Rules for next task:
- Use docs/manual-test-s3-mili-tts-20260504.md.
- Run the local stack with ./scripts/start_lesson_dev.sh.
- Do not treat browser smoke as a substitute for human audio/visual judgement.
- Do not add page_uid or smoke-input special cases.
- Do not run full/browser/deep smoke unless a fresh goal explicitly budgets it.
```
