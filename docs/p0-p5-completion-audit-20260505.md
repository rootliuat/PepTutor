# PepTutor P0-P5 Completion Audit

Updated: 2026-05-05 10:18 CST

Scope: P0-P5 manual test readiness and browser infrastructure closure.

This audit maps the requested checklist to concrete evidence. Passing browser smoke is not treated as a substitute for human classroom observation.

## GitHub State

Repository:

```text
https://github.com/rootliuat/PepTutor
```

Merged PR:

```text
https://github.com/rootliuat/PepTutor/pull/10
```

Main commit:

```text
a861a8881cc534fc8c2124139d841e688a608ecc
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

Status: blocked on human observation.

Record file:

```text
temp/lesson-smoke-artifacts/manual_test_s3_mili_tts_20260505.md
```

Current record status:

```text
pending human execution
```

Why not complete:

- P3 requires human observation of spoken TTS quality, visible classroom tone, mouthOpen behavior, interrupt behavior, and whether Mili feels like a real teacher.
- Browser smoke verifies the real-browser harness and selected route behavior. It does not replace human classroom observation.

Required next action:

```text
Run ./scripts/start_lesson_dev.sh and manually test the six pages using docs/manual-test-s3-mili-tts-20260504.md.
Fill temp/lesson-smoke-artifacts/manual_test_s3_mili_tts_20260505.md.
```

## P4 Issue Classification

Status: not started.

Reason:

```text
P4 depends on actual P3 manual observations.
```

Required output after P3:

- S3 visible tone issues
- redirect helper issues
- TeachingMove action contract issues
- TTS playback issues
- interrupt / barge-in issues
- Sidebar/debug readability issues
- mouthOpen/Live2D issues
- curriculum structure issues
- browser infrastructure issues
- acceptable smoke deliberate probes

## P5 Minimal Fix And Demo Package

Status: not started.

Reason:

```text
P5 depends on P4 classification, and should only fix the highest-value small issues.
```

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

## Current Recommendation

Proceed to P3 manual test execution. Do not start P4/P5 fixes until the manual observation record is filled.
