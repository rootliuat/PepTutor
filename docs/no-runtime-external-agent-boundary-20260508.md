# No Runtime External Agent Boundary

Date: 2026-05-05

This boundary applies to the May 8 PepTutor delivery.

## Rule

External evidence tools are slow-path review infrastructure. They must not control the live classroom.

## RAGFlow Boundary

RAGFlow is allowed for offline evidence work:

- service health checks
- upload planning
- document/chunk export
- chunk cleaning
- mapping chunks into PepTutor evidence fields
- building a curriculum evidence index
- supporting human review for later data tightening

RAGFlow must not be imported by:

- `lesson_runtime`
- TeachingMove planner
- redirect reply policy
- classroom prompt builders
- frontend lesson playback logic

RAGFlow must not decide:

- page
- block
- route
- answer scope
- TeachingMove
- state patch
- classroom visible reply

## Agentic Harness Boundary

The agentic curriculum harness is allowed for offline review:

- provider `none` generates prompts/evidence packages only
- optional provider commands may be used later as slow-path review
- command output is evidence for humans, not runtime authority

The agentic harness must not be imported by:

- `lesson_runtime`
- TeachingMove planner
- redirect reply policy
- classroom RAG chain
- S4/TTS/Live2D runtime

The agentic harness must not edit:

- `app/knowledge/structured`
- runtime code
- prompt code
- smoke matrix

## Canonical Source Boundary

`app/knowledge/structured` remains the canonical curriculum source.

RAGFlow chunks, audit summaries, candidate reports, and agentic review outputs are supporting evidence. They can guide later human-approved data edits, but they do not override structured curriculum automatically.

## Classroom Control Boundary

TeachingMove remains the classroom control layer.

The live classroom path is:

```text
structured curriculum
-> lesson_runtime
-> TeachingMove
-> redirect/responder policy
-> visible reply / TTS / Sidebar
```

External evidence pipelines are not part of that path for May 8.

## Claims Boundary

Safe claim:

```text
PepTutor has offline RAGFlow and agentic evidence-review tooling to support curriculum audit and future data tightening.
```

Unsafe claims:

```text
RAGFlow powers live lesson routing.
An external agent controls the classroom.
GRPO is implemented.
The system trains models from the curriculum graph.
```
