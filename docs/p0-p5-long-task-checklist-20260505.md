# PepTutor P0-P5 Long Task Checklist

Updated: 2026-05-05 11:22 CST

Purpose: keep the next conversation focused on the correct order of work: start the project, verify browser testing, prepare manual testing, observe the real classroom experience, classify issues, then choose one minimal fix. This file is the long-task checklist and handoff map; it should be read before starting another broad `/goal`.

## Current Status

| phase | status | evidence |
| --- | --- | --- |
| P0 Startup chain | done | `./scripts/start_lesson_dev.sh` starts backend and Vite; `/lesson/catalog` and `/lesson` both return 200 |
| P1 Browser smoke | done | `temp/lesson-smoke-artifacts/lesson_browser_smoke_20260505_101008.json` passed |
| P2 Manual test prep | done | `docs/manual-test-s3-mili-tts-20260504.md` |
| P3 Manual test execution | technical observation done; human audio/visual judgement pending | `temp/lesson-smoke-artifacts/manual_test_s3_mili_tts_20260505.md`, `docs/manual-test-record-s3-mili-tts-20260505.md` |
| P4 Issue classification | initial technical classification done | G6S1 P4 `museum shop` collapse is the only current P5 candidate |
| P5 Minimal fix/demo package | L1 implementation complete; PR #13 merged; demo handoff package written | public location question/answer preservation merged to main; no smoke re-run |

## Long Task Queue

### Immediate Task Queue

| priority | task | status | next action | budget |
| --- | --- | --- | --- | --- |
| P0 | Startup chain closure | done | keep `./scripts/start_lesson_dev.sh` as the canonical local start command | no smoke |
| P1 | Browser smoke closure | done | do not rerun unless frontend/S4/browser work needs it | browser smoke max 1 per goal |
| P2 | Manual test preparation | done | use the checklist for human observation | no smoke |
| P3 | Manual test execution | technical observation done | complete human audio/visual judgement for TTS and Live2D mouthOpen | no automated smoke |
| P4 | Issue classification | initial pass done | keep separating real issues from deliberate probes | no smoke |
| P5 | Minimal visible-experience fix | L1 done, PR #13 merged, demo package written | decide whether to re-observe G6S1 P4 | L1 only unless final acceptance needs one budgeted browser/manual pass |

### Pending Closure Items

1. Finish human judgement for six S3/Mili/TTS pages:
   - TTS naturalness;
   - mouthOpen synchronization;
   - whether Mili feels like a real teacher rather than only a routed response engine.
2. Re-observe `TB-G6S1U1-P4` only if a fresh budgeted goal explicitly needs browser/manual confirmation after PR #13.
3. Keep the minimal runtime state default-on work env-gated unless a fresh readiness goal passes its gated L1/L3 plan.

### Broader Backlog After P0-P5

These are not part of the immediate P0-P5 closure unless a new goal explicitly scopes them.

| area | unfinished work | why it matters |
| --- | --- | --- |
| P13 return-anchor | monitor `rag_plus_llm` vocab return boundary after P13 answer-scope fixes | avoids falling back to module-choice wording after answering vocabulary |
| Minimal runtime state | default-on readiness remains gated | saves prompt cost, but must not regress P13/P24/P6 routing boundaries |
| S4 interruption | backend natural trigger still not product-complete | frontend can handle branches, but backend policy natural production still needs closure |
| Mili visible tone | wiring is clean, visible personality is not fully judged | capsule exists, but human classroom feel is still pending |
| Browser smoke productization | real-backend suite passes, many mock tests are intentionally skipped | reports are clearer, but suite packaging can still improve |
| Token/context trim | metering and attribution exist, more trimming remains | controls cost before expanding the page matrix |
| Contest package | code/docs/resources need final packaging | required for competition submission and reproducibility |

## P0: Startup Chain Closure

Goal: local project starts reliably.

Current verification:

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

Expected:

```text
backend ready: http://127.0.0.1:9625/lesson/catalog
frontend ready: http://127.0.0.1:5173/lesson
```

Closed startup failures:

- `Cannot find module '/root/root/.local/.../vite.js'`
- bad pnpm-generated Vite/Vitest bin shim paths
- missing Git-clone backend `.venv` before budget accounting
- frontend workspace symlinks pointing at a clone without built package entries
- Vite optimizeDeps reload during browser-test import

Startup rule:

- If `./scripts/start_lesson_dev.sh` fails with a Vite module path under `/root/root/.local/share/pnpm/...`, treat it as a frontend dependency/bin-shim problem first, not a backend lesson-runtime bug.
- If backend `/lesson/catalog` is reachable but frontend fails, do not rerun backend smoke; inspect pnpm/Vite/node module resolution.
- If frontend starts but browser smoke import reloads, inspect Vite optimizeDeps and browser-test dependency preloading before changing lesson code.

## P1: Browser Smoke Closure

Goal: real-browser test can enter and pass the real backend suite.

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

Do not rerun browser smoke casually. Use Test Budget Guard and only run browser smoke for frontend/S4/browser work.

## P2: Manual Test Preparation

Checklist:

```text
docs/manual-test-s3-mili-tts-20260504.md
```

Pages:

- `TB-G5S1U3-P22`
- `TB-G6S1U1-P4`
- `TB-G6S2U1-P4`
- `TB-G5S1U3-P31`
- `TB-G5S2U1-P6`
- `TB-G6S2U2-P13`

Each page has:

- learner inputs;
- expected teacher behavior;
- expected Sidebar/TTS state;
- human observation points.

## P3: Manual Test Execution

Technical browser observation is recorded:

```text
temp/lesson-smoke-artifacts/manual_test_s3_mili_tts_20260505.md
docs/manual-test-record-s3-mili-tts-20260505.md
```

Observed technically:

- teacher response text;
- Sidebar route/action/speech/persona/interrupt/TTS fields;
- TTS state and stop reason;
- overlap state;
- mechanical / overloaded / off-route flags.

Still needs human judgement:

- whether TTS sounds natural;
- whether mouthOpen follows speech naturally;
- whether Mili feels like a real English teacher.

## P4: Issue Classification

Current classification:

| page_uid | result |
| --- | --- |
| `TB-G5S1U3-P22` | acceptable favourite-food redirect |
| `TB-G6S1U1-P4` | issue: off-topic `turn left` collapses target to `museum shop` noun phrase |
| `TB-G6S2U1-P4` | acceptable object-height answer frame |
| `TB-G5S1U3-P31` | acceptable story scaffold |
| `TB-G5S2U1-P6` | acceptable phonics scaffold; `cl' as in` absent |
| `TB-G6S2U2-P13` | acceptable vocab return; monitor rag_plus_llm return-anchor boundary |

Do not collapse every concern into "Mili is not alive." The only technical P5 candidate right now is the public question/answer target-action issue on G6S1 P4-style location dialogue.

## P5: Minimal Fix / Demo Package

Implemented L1 slice:

```text
Public location question/answer target-action preservation.
```

Intent:

- keep location dialogue targets as a question/answer pair;
- avoid redirecting only to a noun phrase like `museum shop`;
- do it as a shared rule, not a page-specific patch.

Local implementation:

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

Still pending:

- human audio/visual judgement;
- optional browser/manual re-observation with a fresh budgeted goal.

Demo handoff:

```text
docs/demo-handoff-p0-p5-20260505.md
```

Clean PR requirements:

- branch from current `rootliuat/PepTutor` main;
- include only the P5 regression/test/doc handoff files;
- do not carry unrelated dirty files from `/root/my-project/PepTutor`;
- validation must remain L1-only unless a fresh goal budgets broader verification;
- final report must say full smoke, browser smoke, and deep smoke counts.

Strict boundaries:

- no RAG changes;
- no P49/classification changes;
- no P13 answer_scope data changes;
- no smoke matrix changes;
- no full `soul.md` prompt injection;
- no persona interest chatter;
- no `page_uid == ...` special cases;
- no smoke-input special cases;
- no fixed deterministic teacher reply templates;
- no full/browser/deep smoke unless a fresh goal explicitly budgets it.

## Next Prompt

Use this in a new conversation if continuing:

```text
We are in /root/my-project/PepTutor. P0 startup and P1 browser smoke are closed. Latest passing browser smoke is temp/lesson-smoke-artifacts/lesson_browser_smoke_20260505_101008.json. P2 manual checklist is docs/manual-test-s3-mili-tts-20260504.md. P3 technical browser observation is recorded in temp/lesson-smoke-artifacts/manual_test_s3_mili_tts_20260505.md and docs/manual-test-record-s3-mili-tts-20260505.md, but human audio/visual judgement is still pending. P4 initial classification found the only current P5 candidate: TB-G6S1U1-P4 collapsed location dialogue to the noun phrase museum shop. PR #13 is merged into main at commit a1b7cb7b76397c56be3510e55e670ec52046bd28 and adds the location question/answer preservation regression plus docs; post-merge L1 pytest was 396 passed and ruff passed. It has not been browser-reobserved. Do not change RAG, P49, P13 data, S4, persona/soul, smoke matrix, or add page_uid/smoke-input special cases.
```
