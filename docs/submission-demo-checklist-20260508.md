# PepTutor May 8 Demo Checklist

Date: 2026-05-05

## 1. Start Local Stack

Use the project startup helper:

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

Expected services:

```text
backend: http://127.0.0.1:9625
frontend: http://127.0.0.1:5173/lesson
```

If local requests fail in WSL, verify `NO_PROXY=127.0.0.1,localhost,::1` or use `curl --noproxy '*'` for one-off checks.

## 2. Open `/lesson`

Open:

```text
http://127.0.0.1:5173/lesson
```

Confirm the catalog loads, a lesson page can be selected, and Sidebar debug fields are visible.

## 3. Classroom Pages To Demo

Use one or two pages, not every regression page.

Recommended:

```text
TB-G6S1U1-P4
```

Purpose:

```text
Show location Q/A preservation after PR #13:
Where is the museum shop?
It's near ...
```

Optional second page:

```text
TB-G5S2U1-P6
```

Purpose:

```text
Show phonics scaffold and that "cl' as in" does not leak as a bad visible target.
```

Optional story page if time permits:

```text
TB-G5S1U3-P31
```

Purpose:

```text
Show story question / answer-frame style scaffold.
```

## 4. Sidebar Fields To Show

Show only the fields that explain why PepTutor is controllable:

- route / source
- TeachingMove type
- `target_role`
- `expected_student_action`
- `question_target`
- `answer_target`
- `answer_frame`
- persona source/version
- TTS playback state
- stop reason / normalized stop reason if visible
- playback overlap if visible

## 5. PR #13 Location QA Preservation

Safe explanation:

```text
Earlier the location page could collapse the target into the bare noun "museum shop".
PR #13 locks the classroom contract so the system preserves the question/answer pair:
Where is the museum shop?
It's near ...
```

Do not claim this solves every possible location dialogue or role-play case.

## 6. Curriculum Graph Audit Talking Points

Use these exact facts:

```text
books=4
units=30
pages=255
blocks=581
six anchors present=6/6
```

Safe explanation:

```text
The graph audit is full structured-curriculum coverage, not a six-page sample.
It is deterministic offline analysis, not model training or LLM extraction.
```

## 7. RAGFlow Talking Points

Safe claims:

- RAGFlow support is disabled by default.
- It is an offline evidence pipeline.
- It can support parser/chunk/retrieval evidence review.
- It does not replace `app/knowledge/structured`.
- It has no live runtime dependency.
- It does not control lesson route, page, block, TeachingMove, prompt, or student-visible reply.

Avoid:

- saying RAGFlow powers the live lesson
- saying RAGFlow controls routing
- saying RAGFlow has replaced the structured curriculum

## 8. Agentic Harness Talking Points

Safe claims:

- Provider defaults to `none`.
- With provider `none`, the harness only prepares prompts and evidence review packages.
- Non-none providers are future slow-path review tools.
- No agent controls the classroom.
- No agent edits `app/knowledge/structured`.

Avoid:

- saying an agent teaches the lesson
- saying Kimi/deepagents/bub are required for the demo
- saying agentic retrieval is connected to runtime

## 9. What Not To Claim

Do not claim:

- GRPO is implemented
- model training is done
- RAGFlow controls lesson routing
- agentic CLI controls classroom
- TTS naturalness is fully certified
- mouthOpen sync is fully certified
- Mili is fully human-like
- PepTutor is a complete autonomous teacher

## 10. One-Minute Demo Flow

```text
1. Start stack.
2. Open /lesson.
3. Select TB-G6S1U1-P4.
4. Enter a representative student input.
5. Show teacher reply.
6. Show Sidebar TeachingMove fields.
7. Say: location Q/A pair is preserved after PR #13.
8. Show graph audit facts: 4 books, 30 units, 255 pages, 581 blocks, anchors 6/6.
9. Say: RAGFlow and agentic harness are offline evidence tooling, not runtime control.
```
