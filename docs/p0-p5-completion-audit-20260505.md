# PepTutor P0-P5 Completion Audit

Updated: 2026-05-05 11:22 CST

Scope: P0-P5 manual test readiness and browser infrastructure closure.

This audit maps the requested checklist to concrete evidence. Passing browser smoke is not treated as a substitute for human classroom observation.

## GitHub State

Repository:

```text
https://github.com/rootliuat/PepTutor
```

Latest merged evidence handoff PR:

```text
https://github.com/rootliuat/PepTutor/pull/12
```

Merged P5 handoff PR:

```text
https://github.com/rootliuat/PepTutor/pull/13
```

PR #13 merge commit:

```text
a1b7cb7b76397c56be3510e55e670ec52046bd28
```

## P0 Startup Chain Closure

Status: done.

Evidence:

- PR #9 is included in main through the existing main history.
- PR #11 is included in main through the existing main history.
- `scripts/start_lesson_dev.sh` uses the stable Node bin resolver.
- Local startup was verified with:

```bash
cd /root/my-project/PepTutor
timeout 18s bash scripts/start_lesson_dev.sh
```

Observed:

```text
backend ready after 2s: http://127.0.0.1:9625/lesson/catalog
VITE v8.0.0-beta.15 ready
Local: http://localhost:5173/
lesson URL: http://127.0.0.1:5173/lesson
```

## P1 Browser Smoke Closure

Status: done.

Latest passing browser smoke:

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

Budget:

```text
full smoke=0
deep smoke=0
```

Browser attempts during closure:

```text
browser-frontend-node-modules-closure: 1 failed, dependency symlink issue
browser-post-symlink-closure: 1 failed, Vite optimizeDeps reload issue
browser-optimize-deps-closure: 1 passed
```

Reason for multiple browser goals:

- Each run used a distinct goal id after a distinct browser infrastructure fix.
- No full smoke or deep smoke was run.
- The final browser run passed and collected screenshot, network, DOM, and history artifacts.

## P2 Manual Test Preparation

Status: done.

Checklist:

```text
docs/manual-test-s3-mili-tts-20260504.md
```

Coverage verified:

- Startup command documented.
- Browser entry URL documented.
- `TB-G5S1U3-P22` has test inputs, expected teacher behavior, expected Sidebar/TTS state, and observation items.
- `TB-G6S1U1-P4` has test inputs, expected teacher behavior, expected Sidebar/TTS state, and observation items.
- `TB-G6S2U1-P4` has test inputs, expected teacher behavior, expected Sidebar/TTS state, and observation items.
- `TB-G5S1U3-P31` has test inputs, expected teacher behavior, expected Sidebar/TTS state, and observation items.
- `TB-G5S2U1-P6` has test inputs, expected teacher behavior, expected Sidebar/TTS state, and observation items.
- `TB-G6S2U2-P13` has test inputs, expected teacher behavior, expected Sidebar/TTS state, and observation items.

## P3 Manual Test Execution And Record

Status: technical browser observation complete; human audio/visual judgement still pending.

Record file:

```text
temp/lesson-smoke-artifacts/manual_test_s3_mili_tts_20260505.md
```

Current record status:

```text
technical observation completed; human audio/visual judgement still pending
```

Evidence captured:

- Live browser UI observations for all six target pages.
- Learner input, teacher response excerpt, Sidebar values, TTS state, mechanical/overloaded/off-route flags, interrupt status, classification, owner, priority, and next-slice eligibility.
- P13 `had a cold` vocabulary return was observed returning to `What did you do last weekend?`, not module choice.
- P6 phonics was observed without `cl' as in`.

Remaining caveat:

```text
Browser observation can inspect text, Sidebar/debug state, TTS state, stop reason, and overlap.
It still cannot replace human judgement of spoken TTS quality, mouthOpen naturalness, and whether Mili feels like a real teacher.
```

## P4 Issue Classification

Status: initial technical classification complete.

Classification summary:

```text
TB-G5S1U3-P22: acceptable S3 visible reply.
TB-G6S1U1-P4: redirect helper / TeachingMove target-action issue; off-topic input still collapses the location dialogue to the noun phrase museum shop.
TB-G6S2U1-P4: acceptable S3 visible reply; object-height answer frame is used.
TB-G5S1U3-P31: acceptable story scaffold.
TB-G5S2U1-P6: acceptable phonics scaffold; cl' as in did not appear.
TB-G6S2U2-P13: acceptable P13 vocab return; monitor rag_plus_llm return-anchor boundary.
```

Only concrete next-slice candidate from this pass:

```text
TB-G6S1U1-P4 should keep the public location question/answer target pair instead of narrowing the redirect to museum shop.
Fix only through a public question/answer target-action rule. Do not add page_uid or smoke-input special cases.
```

## P5 Minimal Fix And Demo Package

Status: L1 implementation complete; PR #13 merged; demo handoff package written; not browser-reobserved.

Reason:

```text
The technical P5 candidate was narrow enough to fix safely before human audio/visual judgement:
preserve a public location question/answer frame when a valid TeachingMove action contract is phrase-shaped but still carries a reliable question_target and answer_frame.
```

Implemented local files:

```text
backend/LightRAG/lightrag/pedagogy/redirect_reply_policy.py
backend/LightRAG/tests/test_lesson_runtime.py
backend/LightRAG/tests/test_lesson_smoke_scripts.py
```

Validation:

```text
Focused P5 regression: 8 passed.
Pre-merge L1 pytest: 396 passed.
Post-merge L1 pytest: 396 passed.
Ruff: All checks passed.
full 20-page smoke: 0
browser smoke: 0
deep smoke: 0
```

What changed:

- `target_role=phrase` with a known location `question_target` and `answer_frame=It's near ...` now renders the question/answer frame instead of falling back to a noun phrase such as `museum shop`.
- Valid `where ...?` question contracts with `It's near ...` answer frames can use the answer frame.
- Malformed empty-slot questions such as `Where is the ?` are still rejected because the question must have a known scaffold.
- No page_uid or smoke-input special cases were added.

Allowed future fixes remain:

- obvious punctuation errors
- wrapper leaks
- overloaded one-turn actions
- unclear Sidebar labels
- inaccurate TTS state display
- narrow mechanical wording replacements

Still prohibited:

- RAG changes
- P49/classification changes
- P13 answer_scope data changes
- smoke matrix changes
- full `soul.md` prompt injection
- Mili interest chatter in classroom replies
- page_uid special cases
- smoke input special cases
- large prompt rewrite

Merged GitHub PR:

```text
https://github.com/rootliuat/PepTutor/pull/13
```

Demo handoff:

```text
docs/demo-handoff-p0-p5-20260505.md
```

## Current Recommendation

Proceed with one of two bounded next steps:

1. Human review of spoken TTS quality, mouthOpen naturalness, and whether Mili feels like a real teacher.
2. Perform one explicitly budgeted browser or manual re-observation pass only if needed for `TB-G6S1U1-P4`.
