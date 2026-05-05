# PepTutor Demo Risk Checklist

Date: 2026-05-05

## Principle

The demo should show the live classroom if it starts cleanly. If a live piece fails, switch to documented evidence. Do not run full smoke during recording.

## Startup Risk

Risk:

```text
./scripts/start_lesson_dev.sh fails or one service does not become ready.
```

Likely causes:

- backend port already in use
- frontend dependency/bin path problem
- local proxy interfering with localhost
- stale process from previous run

Fallback:

```text
Show docs/submission-demo-checklist-20260508.md.
Show docs/submission-one-page-scorecard-20260508.md.
Explain the intended route and recorded validation.
```

Do not:

```text
Do not run full 20-page smoke during the video.
```

## Browser / Vite Risk

Risk:

```text
Vite or browser test tooling cannot resolve a local binary.
```

Fallback:

```text
Show PR #9/#11 summary in docs/submission-readiness-summary-20260508.md.
Open static docs instead of debugging Vite live.
```

Do not:

```text
Do not reinstall dependencies live unless this is a separate setup recording.
```

## Backend `.venv` Risk

Risk:

```text
backend/LightRAG/.venv is missing or points to stale dependencies.
```

Fallback:

```text
Explain that the demo expects the project-local LightRAG virtual environment.
Show docs/submission-readiness-summary-20260508.md validation records.
```

Do not:

```text
Do not switch to global Python for an unplanned live run.
```

## TTS Unavailable Risk

Risk:

```text
TTS provider is unavailable, muted, or slow.
```

Fallback:

```text
Show teacher reply and Sidebar TTS fields.
Say that TTS state is observable, but provider availability can vary by local setup.
```

Boundary:

```text
Do not claim TTS naturalness is fully certified.
```

## Live2D mouthOpen Uncertain Risk

Risk:

```text
Live2D mouthOpen does not move naturally or is hard to judge on recording.
```

Fallback:

```text
Show the observable mouthOpen/debug fields where available.
Say true synchronization naturalness requires human AV judgement.
```

Boundary:

```text
Do not claim mouthOpen sync is fully certified.
```

## RAGFlow Disabled Risk

Risk:

```text
RAGFlow service is not configured or not running.
```

Expected state:

```text
This is acceptable. RAGFlow is disabled by default.
```

Fallback:

```text
Show docs/ragflow-service-integration-plan-20260505.md.
Show docs/ragflow-to-peptutor-mapping-report-20260505.md.
Explain that RAGFlow is offline evidence only and does not need to run live.
```

Boundary:

```text
Do not claim RAGFlow powers lesson routing.
```

## Agentic CLI Provider Risk

Risk:

```text
Kimi/deepagents/bub/generic provider is not installed or configured.
```

Expected state:

```text
This is acceptable. provider=none is the default.
```

Fallback:

```text
Show docs/agentic-cli-harness-config-20260505.md.
Show docs/curriculum-evidence-review-queue-20260505.md.
Explain that the harness prepares prompt/evidence review packages and does not control classroom runtime.
```

Boundary:

```text
Do not claim external agents teach the lesson.
```

## Classroom Page Risk

Risk:

```text
Selected classroom page is slow or unexpected.
```

Fallback pages:

```text
TB-G6S1U1-P4
TB-G5S2U1-P6
TB-G5S1U3-P31
```

Fallback statement:

```text
The core demo point is the auditable TeachingMove contract and Sidebar observability, not a perfect free-form conversation.
```

## Final Fallback Order

If the live demo fails, use this sequence:

1. `docs/submission-one-page-scorecard-20260508.md`
2. `docs/submission-project-book-final-draft-20260508.md`
3. `docs/submission-demo-checklist-20260508.md`
4. `docs/submission-readiness-summary-20260508.md`
5. `docs/no-runtime-external-agent-boundary-20260508.md`

The fallback message:

```text
The live browser stack is a demo surface. The project evidence is the auditable runtime design, targeted validation, curriculum graph coverage, and documented boundaries.
```
