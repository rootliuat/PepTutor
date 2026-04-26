# Implementation Plan

## Goal
Translate the architecture into an executable build order. This plan focuses on a stable MVP first, then adds personalization and richer pedagogy.

The accepted teacher-mind constraints from `docs/lesson-teacher-mind-roundtable-consensus.md` are part of this plan: PepTutor should behave like a prepared teacher, not like a broad RAG answer bot.

## Phase 1: Curriculum Core
Deliver a lesson-aware system that stays in context and answers from textbook knowledge reliably.

### Scope
- build an offline `CurriculumMap` for the four PEP books from current raw textbook sources, word lists, Useful expressions, and structured general artifacts
- define and freeze `TeachingBlock` schema
- convert one pilot unit into normalized `TeachingBlock` records
- define stable `page_type` labels, but derive page focus from loaded textbook content rather than page-number assumptions or fixed page templates
- build scoped textbook retrieval with `LightRAG`
- build `LessonBriefBuilder` so live turns use a compact page/block preparation artifact instead of broad unit or whole-book context
- build `LessonState` and turn routing with `LangGraph`
- add page-entry overview and lightweight probe logic
- support `answer_question`, `ask_knowledge`, and `navigation`

### Deliverables
- `CurriculumMap` generator and checked output containing `grade / semester / unit / pages`, unit theme, core vocabulary, core patterns, page types, block UIDs, learning targets, source refs, and confidence
- textbook ingestion script for pilot data
- `LightRAG` adapter with `block -> page -> unit -> global` retrieval
- `LessonBriefBuilder` that consumes exact page/block evidence plus the map and emits a private teacher preparation payload
- `LangGraph` state schema and router node
- page-entry probe node with `mastered | shaky | not_mastered` estimation
- answer evaluation against `allowed_answer_scope`
- basic AIRI text output integration

## Phase 2: Teaching Behavior
Add explicit pedagogy decisions so the system behaves like a tutor, not a search wrapper.

### Scope
- implement `explain`, `hint`, `correct`, `confirm`, `follow_up`
- add `hint_level` progression
- support lightweight repair modes such as `word_drill`, `sentence_drill`, and `asr_clarify`
- add `ask_help` and `social` routes
- attach AIRI expression and action cues

### Deliverables
- pedagogy planner node
- response planner with action labels
- prompt templates for explanation, correction, hinting, and page-entry probing

## Phase 3: Learner Memory
Introduce personalized teaching through distilled long-term memory.

### Scope
- write `LessonTrace` records
- track `assumed_prior_knowledge` as a verifiable hypothesis
- distill `LessonTrace -> TeachingUnit`
- synthesize `LearningCrystal`
- connect `SimpleMem` for storage and recall
- support `meta_learning`

### Deliverables
- memory write-back pipeline
- learner profile recall node
- EVOLVES relation assignment
- progress summary response mode

## Phase 4: Expansion
Scale from pilot unit to broader curriculum and richer interaction.

### Scope
- convert more units and grades
- add prerequisite review
- add voice-first flow and stronger Live2D coupling
- refine common mistake templates and reranking

## Agent Upgrade Backlog
These items capture the next architectural upgrades from the recent agent-engineering review. The target is a constrained teaching agent, not an open-ended autonomous agent. Runtime behavior must continue to obey the lesson state machine, current page scope, branch budget, and `return_anchor` rules.

### 0. Curriculum Map + LessonBrief Runtime Boundary
Create the missing layer between raw curriculum assets and per-turn LLM prompting. PepTutor should behave like a prepared teacher: broad textbook structure is prepared offline, current page evidence is distilled into a lesson brief, and the responder only receives the compact context needed for the current turn.

This slice implements the first part of the roundtable consensus in `docs/lesson-teacher-mind-roundtable-consensus.md`.

Required artifacts:
- `CurriculumMap`: offline four-book index with grade, semester, unit, pages, unit theme, core vocabulary, core patterns, page types, block UIDs, learning targets, source refs, and confidence
- `LessonEvidence`: exact page/block evidence retrieved by UID and metadata before any vector search supplement
- `LessonBrief`: page/block teacher preparation distilled from `CurriculumMap` plus `LessonEvidence`
- `TurnBrief`: compact runtime slice containing current learner signal, teaching move, memory hints, and only the scoped evidence needed for one answer

Rules:
- do not inject the whole book, whole unit, or full curriculum map into `/lesson/turn`
- do not hand-author unit goals from memory; generated fields must retain source refs and confidence
- do not turn the map or brief into fixed per-page wording
- exact UID and metadata lookup wins over semantic retrieval when the current page/block is known
- vector retrieval is a scoped supplement, not the teacher's main brain

Acceptance criteria:
- generated map covers all current `30` catalog scopes without requiring manual page scripts
- P31 and P49 briefs are derived from their actual content, not from preset page-type assumptions
- tests fail if live prompt payloads include broad curriculum dumps instead of compact brief fields
- strategy and dialogue evals check brief quality, source grounding, and natural teacher delivery without enforcing fixed phrases

### 1. Tool Boundary Hardening
Convert implicit backend capabilities into explicit lesson-safe tools so Planner and Responder depend on stable contracts instead of directly assembling context.

Required tool contracts:
- `get_lesson_page(page_uid)`
- `get_current_block(state)`
- `retrieve_support(scope, query)`
- `evaluate_answer(prompt, learner_input)`
- `write_memory(event)`
- `recall_memory(student_id, scope)`

Acceptance criteria:
- tools enforce `page_uid`, unit, and block metadata constraints before returning data
- live prompts receive compact tool outputs instead of raw broad curriculum payloads
- tool results are represented in `debug_signals` for observability
- deterministic fallbacks remain available when live prompts or external providers fail

### 2. Lesson-Scoped Agentic RAG
Add a constrained agentic retrieval layer for knowledge interruptions and branch turns. This is not free-form RAG: the agent may choose and refine retrieval only inside the active lesson scope.

Rules:
- allowed retrieval modes stay `none / block / page / unit / branch`
- metadata filters are mandatory for grade, semester, unit, page, and block where available
- query rewriting is capped at one or two attempts
- no unbounded search loops
- short branches must preserve `return_anchor` and return to the active answer prompt
- exact search, vector search, metadata filtering, support assets, and API-backed lookups should be composed as retrieval tools instead of treated as "vector DB only"

Acceptance criteria:
- `ask_knowledge` can retry or reformulate a weak retrieval result without leaving the current lesson scope
- cross-grade and cross-unit leakage are measured against `app/knowledge/evals/lesson-retrieval-gold.json`
- browser smoke still proves page routing stability after knowledge interruptions

### 3. VFS For Offline Content Workflows
Use a virtual-file-system style workflow for large offline artifacts and debugging, not as the first path in student real-time turns.

Useful targets:
- textbook PDF and structured JSON inspection
- lesson draft generation and review
- long backend/frontend log analysis
- retrieval evaluation reports
- large tool outputs that should be stored as files with previews instead of injected into model context

Runtime boundary:
- real-time `/lesson/turn` should continue to pass compact, state-scoped context
- VFS-style chunking can support development, ingestion, evals, and reviewer workflows
- any VFS output used by runtime must first be distilled into stable `TeachingBlock`, support asset, memory summary, or eval artifact formats

## Recommended Module Breakdown
- `app/knowledge/`
  - source curriculum data
  - normalized `TeachingBlock` outputs
- `backend/`
  - `orchestrator/`: LangGraph workflow
  - `knowledge/`: LightRAG adapter and ingestion
  - `memory/`: SimpleMem adapter and distillation
  - `pedagogy/`: evaluation and teaching strategy rules
- `frontend/airi/`
  - AIRI integration, speech, streaming UI, action mapping

## MVP Acceptance Criteria
- the system can stay on the current page without drifting to unrelated textbook content
- when entering a page, the system gives a short page overview before deep teaching
- the system can use one or two short probe questions to decide whether the learner is `mastered`, `shaky`, or `not_mastered`
- student answers are evaluated locally before global retrieval
- textbook questions can be answered from scoped curriculum knowledge
- the teacher can give at least three levels of hints
- learner traces are recorded, even if long-term memory synthesis is still basic

## Risks
- over-embedding raw textbook text instead of normalized teaching blocks
- letting `CurriculumMap` become a live prompt dump instead of an offline index
- using generated unit/theme summaries without source refs or confidence
- letting `LessonBrief` become fixed teacher wording rather than private preparation
- mixing runtime lesson state with long-term learner memory
- adding too many routes before the core three routes are stable
- building free-form agent behavior before pedagogy rules are explicit

## Immediate Next Tasks
1. Generate the first offline `CurriculumMap` from the current four-book raw and structured assets.
2. Add source-ref and confidence checks so generated curriculum summaries do not become unsupported facts.
3. Implement `LessonEvidence` exact UID/metadata retrieval for current page/block evidence.
4. Implement `LessonBriefBuilder` and keep live turn payloads compact.
5. Add evals that prove P31 and P49 briefs come from actual content rather than fixed templates.
