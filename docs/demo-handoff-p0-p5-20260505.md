# PepTutor Demo Handoff: P0-P5

Updated: 2026-05-05 11:22 CST

This is the short handoff for running and demonstrating the current PepTutor lesson experience after the P0-P5 closure work.

## What Is Ready

- Local startup chain is closed.
- Real-backend browser smoke has passed.
- Manual S3/Mili/TTS test checklist exists.
- Technical browser observation covers the six target pages.
- P5 location question/answer preservation regression is merged through PR #13.

## Start The Demo

Run from the project root:

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

Expected backend signal:

```text
Lesson backend ready after ...: http://127.0.0.1:9625/lesson/catalog
```

Expected frontend signal:

```text
Starting AIRI stage-web frontend: http://127.0.0.1:5173/lesson
```

Open:

```text
http://127.0.0.1:5173/lesson
```

If local requests are checked from WSL, bypass proxies:

```bash
curl --noproxy '*' http://127.0.0.1:9625/lesson/catalog
curl --noproxy '*' http://127.0.0.1:5173/lesson
```

## Browser Smoke Baseline

Latest passing browser smoke:

```text
temp/lesson-smoke-artifacts/lesson_browser_smoke_20260505_101008.json
```

Result:

```text
status=passed
acceptance_passed=true
real_backend_passed=10
mock_suite_skipped=21
skipped_due_real_backend_mode=21
```

Do not rerun browser smoke unless the active goal is frontend, S4, TTS, Live2D, or browser-harness work.

## Manual Demo Script

Use this checklist:

```text
docs/manual-test-s3-mili-tts-20260504.md
```

Recommended pages:

- `TB-G5S1U3-P22`: favourite food scaffold
- `TB-G6S1U1-P4`: location question/answer pair
- `TB-G6S2U1-P4`: object-height answer frame
- `TB-G5S1U3-P31`: story answer scaffold
- `TB-G5S2U1-P6`: phonics `cl` / `clean`
- `TB-G6S2U2-P13`: vocabulary answer and return anchor

Technical observation record:

```text
docs/manual-test-record-s3-mili-tts-20260505.md
```

## Known Limitations

- Human audio judgement is still pending:
  - TTS naturalness;
  - mouthOpen synchronization;
  - whether Mili feels like a real teacher.
- `TB-G6S1U1-P4` location QA preservation is covered by tests and merged, but it has not been browser-reobserved after PR #13.
- Browser smoke passes real-backend tests, but mock-only browser cases are intentionally skipped in real-backend mode.
- Minimal runtime state default-on remains env-gated.
- Broader token/context trimming remains a later optimization.

## P5 PR Merge Commit

```text
a1b7cb7b76397c56be3510e55e670ec52046bd28
```

Merged P5 PR:

```text
https://github.com/rootliuat/PepTutor/pull/13
```

## Boundaries For The Next Demo Fix

Do not change these unless a new goal explicitly scopes them:

- RAG
- P49/classification
- P13 answer_scope data
- S4 interruption behavior
- persona/soul prompt injection
- smoke matrix
- page_uid special cases
- smoke-input special cases
- deterministic teacher reply templates
