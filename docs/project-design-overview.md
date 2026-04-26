# Project Design Overview

## 1. Project Positioning
This project is not a generic English chat bot, and it is not a plain textbook RAG demo. The target is a curriculum-aware teaching agent that can stay inside the current lesson, judge student answers in context, and adapt its teaching behavior over time.

The system should gradually evolve from a stable lesson assistant into a personalized teacher. The first priority is not "stronger retrieval." The first priority is stable classroom behavior.

## 2. Core Problem
The earlier RAG prototype exposed a clear issue: when a student answer overlaps with indexed textbook content, retrieval is triggered too early and the system jumps out of the current lesson context. This breaks conversational continuity and makes the teacher feel mechanical.

The redesign solves this by separating:
- lesson state
- textbook knowledge
- learner memory
- pedagogy decisions

## 3. Design Goal
The agent should have four visible qualities:
- understand where the current lesson is
- answer from textbook knowledge without drifting
- behave like a teacher, not a search engine
- remember how a specific student learns

## 4. System Architecture
```text
AIRI
-> LangGraph Orchestrator
-> Pedagogy Layer
-> Knowledge and Memory Layer
-> Model Layer
```

### AIRI
Handles input and output only: ASR, text, TTS, streaming reply, and Live2D actions.

### LangGraph Orchestrator
Controls the runtime flow. It owns short-term lesson state, routes each turn, and decides when to call retrieval, memory, or response planning.

### Pedagogy Layer
Defines teaching behavior such as explain, hint, correct, confirm, follow-up, and prerequisite review. This is the layer that makes the system act like a teacher.

### Knowledge and Memory Layer
- `LightRAG`: textbook structure and teaching knowledge
- `SimpleMem`: distilled long-term learner memory

### Model Layer
Provides chat models, embeddings, and optional reranking.

## 5. Knowledge Strategy
Textbook data should be normalized into `TeachingBlock` records, not embedded as full pages. Each block represents a real teaching unit such as a dialogue core, vocabulary block, pattern block, or exercise block.

Each textbook page should also carry a stable `page_type`, because teaching progression should be driven by page type before free-form chat intent. Recommended page types:
- `unit_intro`
- `dialogue`
- `vocabulary`
- `phonics`
- `listening`
- `reading`
- `exercise`
- `review`
- `story`

Only compact teaching summaries should be embedded. Retrieval is a support tool, not the default entry for every turn.

## 6. Conversation Strategy
The runtime should inspect lesson state and current page type before routing a turn. If the learner has just entered a new page, the system should first do:
- a short Chinese page overview
- one or two lightweight probe questions
- a quick estimate of whether the learner is `mastered`, `shaky`, or `not_mastered` for the current page goal

Every user turn is then classified:
- `answer_question`
- `ask_knowledge`
- `ask_help`
- `navigation`
- `social`
- `meta_learning`

If the teacher is waiting for an answer, the system must evaluate the student response against the current block before any global retrieval.

This means the teaching flow is:
`page_type -> page_entry_probe -> turn routing -> pedagogy action -> retrieval if needed`

## 7. Memory Strategy
The project uses a teaching version of `Trace -> Unit -> Crystal`:
- `LessonTrace`: raw classroom trace
- `TeachingUnit`: atomic learning fact
- `LearningCrystal`: synthesized learner understanding

Knowledge should evolve through `EVOLVES` relations such as `replaces`, `enriches`, `confirms`, and `challenges`.

The system should also track `assumed_prior_knowledge` as a hypothesis rather than a fact. It can come from grade-level prerequisites, recent page history, or learner memory, but it must be verified through lightweight page-entry probes before it affects pacing.

## 8. MVP Scope
The first version should only prove five things:
- one pilot unit can be converted into `TeachingBlock`
- the pilot data includes stable `page_type` labels
- lesson state is explicit and stable
- page entry can be handled with a short overview and lightweight probe
- local answer evaluation works before retrieval
- scoped textbook retrieval can answer lesson questions
- basic hints and correction can be generated

## 9. What This Project Is Not
The V1 system should not aim for:
- a fully autonomous multi-agent team
- blind whole-book embedding
- storing all raw dialogue as long-term memory
- unrestricted global retrieval during answer evaluation

## 10. Current Development Principle
Build the teaching workflow first. Expand models, memory depth, and personality only after the lesson loop is stable.
