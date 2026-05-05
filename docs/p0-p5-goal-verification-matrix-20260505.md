# PepTutor P0-P5 Goal Verification Matrix

Updated: 2026-05-05 11:30 CST

This file maps the P0-P5 goal requirements to concrete evidence. It is intentionally stricter than a progress summary: a requirement is not marked complete unless the artifact directly covers it.

## Summary

| area | status | evidence |
| --- | --- | --- |
| P0 startup chain | complete | `./scripts/start_lesson_dev.sh` verified locally; PR #9 and PR #11 included in main |
| P1 browser smoke | complete | `temp/lesson-smoke-artifacts/lesson_browser_smoke_20260505_101008.json` passed |
| P2 manual test preparation | complete | `docs/manual-test-s3-mili-tts-20260504.md` |
| P3 manual test execution | partially complete | technical observation plus human AV blocker record exist; human listener/viewer ratings remain pending |
| P4 issue classification | complete for technical pass | `docs/manual-test-record-s3-mili-tts-20260505.md` |
| P5 minimal fix and demo package | complete | PR #13 merged; post-PR G6S1 P4 re-observation recorded; `docs/demo-handoff-p0-p5-20260505.md` |

## P0 Startup Chain

| requirement | evidence | status |
| --- | --- | --- |
| PR #9 Vite/Vitest bin path fix confirmed | main history includes browser bin resolver fixes; startup audit records PR #9 | complete |
| PR #11 browser smoke preflight budget fix confirmed | main history includes preflight-before-budget behavior; startup audit records PR #11 | complete |
| Git working copy frontend deps fixed | browser smoke closure records local node_modules/symlink repair | complete |
| `./scripts/start_lesson_dev.sh` usable | `docs/p0-p5-completion-audit-20260505.md` records backend ready and Vite ready output | complete |
| backend ready | local startup evidence shows `/lesson/catalog` ready | complete |
| frontend Vite ready | local startup evidence shows Vite ready and lesson URL | complete |
| `/lesson` openable | local startup evidence records `http://127.0.0.1:5173/lesson` | complete |
| browser smoke enters real browser tests instead of dependency/preflight failure | latest browser smoke passed real-backend tests | complete |

## P1 Browser Smoke Closure

| requirement | evidence | status |
| --- | --- | --- |
| new goal id used | browser closure records distinct goal ids for each infrastructure step | complete |
| no full smoke | completion audit records full smoke 0 for browser closure | complete |
| no deep smoke | completion audit records deep smoke 0 for browser closure | complete |
| browser smoke passed | `lesson_browser_smoke_20260505_101008.json`: `status=passed`, `acceptance_passed=true` | complete |
| browser smoke count controlled | final passing browser run under closure path is recorded; earlier failed runs are documented as separate infrastructure blockers | complete |
| failure reasons recorded | `PROGRESS.md` records dependency symlink and Vite optimizeDeps failures with resolutions | complete |

## P2 Manual Test Preparation

| requirement | evidence | status |
| --- | --- | --- |
| checklist exists | `docs/manual-test-s3-mili-tts-20260504.md` | complete |
| startup method clear | checklist has startup command and browser entry | complete |
| test entry clear | checklist has `http://127.0.0.1:5173/lesson` | complete |
| all six target pages listed | checklist covers P22, G6S1 P4, G6S2 P4, P31, P6, P13 | complete |
| test inputs per page | checklist includes input lists for each page | complete |
| expected teacher behavior per page | checklist includes expected behavior per page | complete |
| expected Sidebar state per page | checklist includes target/action/speech/TTS Sidebar expectations | complete |
| expected TTS state per page | checklist includes TTS playback expectations | complete |
| human observation points per page | checklist includes teacher-likeness, overload, mechanical wording, route, TTS, interrupt, mouthOpen | complete |

## P3 Manual Test Execution

| requirement | evidence | status |
| --- | --- | --- |
| each target page has an observation record | `docs/manual-test-record-s3-mili-tts-20260505.md` and `docs/manual-test-record-s3-mili-tts-human-av-20260505.md` cover all six pages | complete |
| learner input recorded | record includes learner input for each page | complete |
| teacher response recorded | record includes teacher response excerpt for each page | complete |
| Sidebar display recorded | record includes route/action/speech/persona/interrupt/overlap fields | complete |
| TTS playback recorded | record includes synthesis/playback state for each page | complete |
| mechanical/overloaded/off-route recorded | record includes these flags for each page | complete |
| mouthOpen abnormality recorded | human AV blocker record preserves numeric mouthOpen/Sidebar observations and marks true synchronization rating as `human-required` | partially complete |
| interrupt abnormality recorded | record includes interrupt status for each page | complete |
| can clearly judge whether Mili feels like a real teacher | text/DOM proxy ratings exist; true audio/visual teacher-likeness requires human listener/viewer judgement | pending human judgement |
| real issues listed instead of vague "unnatural" | technical record lists the single concrete P5 candidate and acceptable pages | complete |

## P4 Issue Classification

| requirement | evidence | status |
| --- | --- | --- |
| S3 wording/naturalness separated | classification table distinguishes acceptable S3 replies from the P5 candidate | complete |
| redirect helper issue identified | `TB-G6S1U1-P4` classified as redirect helper / TeachingMove target-action issue | complete |
| TeachingMove action contract risk considered | owner notes include `redirect_reply_policy.py` and possible `teaching_move_planner.py` | complete |
| TTS playback issue considered | technical record includes TTS state; no concrete TTS content fix identified | complete |
| interrupt/barge-in issue considered | technical record includes interrupt status; no current S4 fix scoped | complete |
| Sidebar/debug issue considered | technical record includes Sidebar values; no current Sidebar fix scoped | complete |
| mouthOpen/Live2D issue considered | marked as pending human judgement | partially complete |
|教材结构 issue considered | P13 and route behavior are classified without data change | complete |
| browser infra issue separated | startup/browser failures are recorded separately from classroom behavior | complete |
| smoke deliberate probes separated | off-topic learner inputs are not treated as automatic classroom failures | complete |
| each issue has owner/priority/next-slice eligibility | classification table includes owner, priority, and next action | complete |
| no RAG/P49/P13/S4 mis-scoping | completion docs explicitly prohibit and record no such changes | complete |

## P5 Minimal Fix And Demo Package

| requirement | evidence | status |
| --- | --- | --- |
| only highest-value small issue fixed | PR #13 covers only location QA preservation regression/test/docs; post-PR observation confirms `Where is the museum shop?` and `It's near ...` are preserved | complete |
| no RAG changes | PR #13 files do not include RAG files | complete |
| no P49/classification changes | PR #13 files do not include classification policy files | complete |
| no P13 answer_scope data changes | PR #13 files do not include P13 data or answer-scope changes | complete |
| no smoke matrix change | PR #13 files do not include smoke matrix changes | complete |
| no full `soul.md` prompt injection | PR #13 does not touch persona/soul prompt files | complete |
| no interest chatter | PR #13 does not touch persona interest logic | complete |
| no page_uid special cases | PR #13 adds tests/docs only; runtime already held shared location QA behavior | complete |
| no smoke-input special cases | PR #13 adds regression coverage only | complete |
| no deterministic teacher reply template | PR #13 adds assertions, not production reply templates | complete |
| `PROGRESS.md` updated | updated and pushed to main | complete |
| manual test report exists | `docs/manual-test-record-s3-mili-tts-20260505.md`; human AV blocker record `docs/manual-test-record-s3-mili-tts-human-av-20260505.md` | complete |
| known issue list exists | `docs/p0-p5-long-task-checklist-20260505.md` and completion audit | complete |
| demo startup instructions exist | `docs/demo-handoff-p0-p5-20260505.md` | complete |
| GitHub PR exists and merged | PR #13 merged | complete |
| post-merge L1 validation | pytest 396 passed; ruff passed | complete |
| full/browser/deep smoke budget for P5 | full=0, browser=0, deep=0 | complete |

## Remaining Requirement

The only remaining P0-P5 requirement that cannot be closed by automated or text-based inspection is human audio/visual judgement:

- TTS naturalness;
- mouthOpen synchronization;
- whether Mili feels like a real English teacher during actual use.

Use `docs/manual-test-s3-mili-tts-20260504.md` and fill the unresolved `human-required` fields in `docs/manual-test-record-s3-mili-tts-human-av-20260505.md`. Do not run full smoke for that judgement.
