# PepTutor One-Page Scorecard

Date: 2026-05-05

## Project

PepTutor：面向小学英语教材的可审计 AI 陪练老师系统。

## Architecture Summary

```text
app/knowledge/structured
-> backend/LightRAG lesson_runtime
-> TeachingMove action contract
-> redirect/responder policy
-> frontend /lesson + Sidebar + TTS + Live2D
-> smoke/audit/budget guard
```

Canonical curriculum source:

```text
app/knowledge/structured
```

Classroom control layer:

```text
TeachingMove
```

External evidence tools:

```text
RAGFlow offline evidence pipeline
Agentic CLI offline review harness
```

They do not control runtime.

## Completed Modules

- Lesson runtime classroom path
- TeachingMove action contract
- Redirect quality/audit loop
- Mili persona capsule boundary
- TTS / Live2D / Sidebar observability
- Browser smoke report metadata
- Test Budget Guard
- Full curriculum graph audit
- Curriculum data tightening candidate planner
- Offline RAGFlow evidence integration
- Offline agentic curriculum review harness

## Validation Summary

- PR #13 protects location Q/A preservation for the May 8 demo path.
- PR #15 covers full curriculum graph audit and candidate planner.
- PR #16 adds RAGFlow as offline evidence only.
- PR #17 adds agentic review harness as offline tooling only.
- No full/browser/deep smoke was run after the docs-only delivery commit.
- GRPO is not implemented.
- Model training is not implemented.
- LLM extraction is not implemented.

## Key Numbers

| Metric | Value |
|---|---:|
| Books | 4 |
| Units | 30 |
| Pages | 255 |
| Blocks | 581 |
| Graph nodes | 9328 |
| Graph edges | 22475 |
| Curriculum findings triaged | 988 |
| Anchor pages present | 6/6 |

## Merged PR List

| PR | Role |
|---|---|
| #8 | Mili visible tone/manual test prep |
| #9 | Browser tool binary startup fix |
| #11 | Browser backend preflight before budget |
| #13 | P5 location Q/A preservation handoff |
| #15 | Curriculum graph audit + candidate planner |
| #16 | Offline RAGFlow evidence integration |
| #17 | Offline agentic curriculum retrieval harness |

## Demo Route

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

Open:

```text
http://127.0.0.1:5173/lesson
```

Recommended page:

```text
TB-G6S1U1-P4
```

Show:

- teacher reply
- Sidebar route/action
- `question_target`
- `answer_frame`
- persona/TTS fields

## Known Limitations

- Mili is not claimed to be fully human-like.
- TTS naturalness is not fully certified.
- mouthOpen sync is not fully certified.
- RAGFlow does not control lesson routing.
- Agentic CLI does not control classroom.
- GRPO and model training are deferred.
- Full autonomous teacher behavior is not claimed.
