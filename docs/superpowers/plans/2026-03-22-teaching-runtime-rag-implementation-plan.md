# Teaching Runtime and RAG Implementation Plan

## Status
This plan translates the approved design in `docs/superpowers/specs/2026-03-22-teaching-runtime-rag-design.md` into a build order for the current repository state.

## Progress Snapshot
Current implementation status as of `2026-03-24`:
- `Phase 0` is sufficiently complete for local WSL work:
  - `backend/LightRAG/.venv` is in use
  - `backend/LightRAG/.env` is the active runtime config
  - Qwen3-compatible embedding config has been smoke-tested through the OpenAI-compatible binding
- `Phase 1` is partially complete:
  - structured pilot data is available for `G5 S1 U3`
  - branch-aware fields are present in the live pilot files
  - raw textbook `.js/.json` sources can be normalized
  - `raw -> normalized -> draft -> review` is working for `G5 S1 U3 p24-p25`
  - markdown word-list and useful-expression parsing is working
  - unit-level support assets can now be emitted for `G5 S1 U3`
  - support assets are now wired into lesson-side `ask_knowledge` and short `branch` turns
- `Phase 2` is complete enough for the first backend MVP slice:
  - text-first runtime exists
  - `POST /lesson/turn` exists
  - local answer evaluation and route handling exist
- `Phase 3` is complete for the first retrieval slice:
  - deterministic scope control exists for `none / block / page / unit / branch`
  - optional Qdrant-backed lesson reranking exists
  - `TeachingBlock` indexing helpers exist
- `Phase 4` is only partially represented today:
  - the escalation ladder exists in deterministic runtime logic
  - live route classification now exists for open turns behind deterministic fallback
  - live `Planner` wiring now exists for `ask_knowledge`, `ask_help`, branch-close redirect, and general social redirect behind the same retrieval contract
  - live `Responder` wiring now exists for open-turn phrasing behind deterministic fallback
  - answer-evaluation still remains deterministic
- `Phase 5` is now partially complete:
  - read-only `SimpleMem` prompt injection exists through a thin SQLite adapter in `LightRAG`
  - deterministic lesson-trace writeback now exists through a second thin SQLite adapter in `LightRAG`
  - optional semantic recall now exists through a thin LanceDB adapter in `LightRAG`
  - live route-classifier, planner, and responder payloads now receive compact learner-memory summaries
  - deterministic fallback remains in place if `SimpleMem` is disabled, missing, or fails
  - the current semantic recall path still depends on optional `lancedb` / `pyarrow` support in `backend/LightRAG/.venv`
- `Phase 6` remains pending in the current WSL rebuild

## Planning Principles
- build one stable vertical slice before broad coverage
- keep retrieval as a support tool, not the lesson controller
- rebuild PepTutor logic as thin, well-bounded modules around the upstream repos
- prefer adapters and additive modules over deep upstream rewrites
- validate every backend slice with the narrowest useful test first

## Current Repository Reality
- the previous Windows-specific PepTutor custom code is not present in the current WSL copy
- `backend/LightRAG/` is currently a generic upstream base
- `backend/SimpleMem/` is currently an upstream memory base with cross-session support
- `frontend/airi/` does not yet contain lesson-mode integration
- `app/knowledge/structured/` already contains a usable pilot starting point for `G5 S1 U3`

## Target MVP
Deliver a text-first lesson loop that can:
- stay on the current page and block
- evaluate learner answers locally before retrieval
- use `none / block / page / unit / branch` retrieval modes
- follow the approved difficulty escalation ladder
- support short branch conversations and natural return-to-main behavior
- write back learner memory with priority `mistakes > preferences > mastery`

## Build Strategy
Use six phases. Each phase should be shippable and reviewable on its own.

## Phase 0: Environment and Contract Freeze
Goal: make the workspace runnable in WSL and freeze the V1 contracts before code changes.

Scope:
- create project-local Python environments for `backend/LightRAG` and `backend/SimpleMem`
- install `frontend/airi` dependencies
- choose the initial embedding provider abstraction and env keys
- freeze the V1 schemas for `PageLesson`, `TeachingBlock`, planner output, and lesson runtime state
- decide the exact Qdrant collection naming and workspace strategy

Deliverables:
- reproducible local setup notes for WSL
- env template for Qdrant and embedding provider selection
- schema note or typed contract stub for planner output and runtime state

Validation:
- `backend/LightRAG`: import test or smoke test inside `.venv`
- `backend/SimpleMem`: import test or smoke test inside `.venv`
- `frontend/airi`: `pnpm install` completes and `pnpm dev` boots

## Phase 1: Pilot Data Normalization
Goal: turn the existing pilot assets into the first source of truth for runtime and retrieval.

Scope:
- treat `app/knowledge/structured/g5s1u3-*.json` as the initial canonical pilot
- audit the raw-to-structured gaps for the pilot unit only
- backfill missing V1 fields such as `branchable_topics` and `return_anchors`
- define a normalization path for future raw assets:
  - textbook pages -> `PageLesson` and `TeachingBlock`
  - word lists and useful expressions -> `LexiconEntry`
  - pronunciation assets -> `PronunciationRule`

Deliverables:
- one frozen pilot manifest for `G5 S1 U3`
- updated pilot JSON records with branch-aware fields
- a normalization script or loader for pilot ingestion

Validation:
- schema-level tests for required fields and stable IDs
- fixture tests that confirm block, page, and unit scope can be derived from pilot data

## Phase 2: Lesson Runtime Skeleton in LightRAG
Goal: create the smallest text-only lesson controller before adding rich retrieval or memory.

Recommended new modules in `backend/LightRAG/lightrag/`:
- `orchestrator/lesson_state.py`
- `orchestrator/lesson_runtime.py`
- `pedagogy/types.py`
- `pedagogy/evaluation.py`
- `api/routers/lesson_routes.py`

Scope:
- define lesson runtime state
- define planner output contract
- implement turn entry for the core routes:
  - `answer_question`
  - `ask_knowledge`
  - `ask_help`
  - `navigation`
  - `social`
- implement local answer evaluation against `allowed_answer_scope`
- block retrieval when the runtime is actively waiting for an answer unless local context is insufficient

Deliverables:
- lesson runtime state schema
- lesson API endpoint for text-first pilot interaction
- local answer evaluator with explicit result labels

Validation:
- `backend/LightRAG/.venv/bin/pytest tests` with new lesson-runtime tests
- `backend/LightRAG/.venv/bin/ruff check .`
- focused tests for:
  - answer evaluation priority
  - route classification
  - retrieval blocking while `awaiting_answer = true`

## Phase 3: Scoped Retrieval and Branch Control
Goal: make Qdrant retrieval obey the lesson controller instead of overriding it.

Scope:
- add pilot ingestion into Qdrant using `TeachingBlock`
- build retrieval helpers for:
  - `none`
  - `block`
  - `page`
  - `unit`
  - `branch`
- ensure `PageLesson` stays as runtime metadata rather than the primary vector unit
- implement branch budget, `return_anchor`, and `return_target`
- keep branch retrieval short and scoped

Deliverables:
- Qdrant ingestion pipeline for pilot `TeachingBlock` records
- scoped retrieval adapter with metadata filters
- branch controller with return-to-main support

Validation:
- tests for block, page, unit, and branch scope filtering
- tests that prevent direct escalation from local evaluation to broad retrieval
- Qdrant-backed smoke test for one pilot lesson query path

## Phase 4: Pedagogy Engine and Prompt Wiring
Goal: make the system behave like the approved lively guided teacher.

Recommended new modules in `backend/LightRAG/lightrag/`:
- `pedagogy/planner.py`
- `pedagogy/responder.py`
- `pedagogy/branching.py`
- `pedagogy/escalation.py`

Scope:
- split prompt flow into `Planner Prompt` and `Responder Prompt`
- implement the approved teaching actions
- implement the difficulty escalation ladder:
  - light hint
  - stronger half-hint
  - model sentence
  - repeat and drill
  - independent retry
- support `repair_mode` values such as `word_drill`, `sentence_drill`, `slow_read`, and `asr_clarify`
- attach lightweight AIRI-facing response cues in the backend payload

Deliverables:
- planner and responder prompt templates
- pedagogy action selection layer
- difficulty-escalation module

Validation:
- tests for escalation transitions
- tests for branch-open and branch-close conditions
- golden-response or structured-output tests for planner payload shape

## Phase 5: SimpleMem Integration
Goal: add learner personalization without mixing runtime state and long-term memory.

Scope:
- define the PepTutor memory write-back contract
- convert lesson traces into memory candidates
- write back in this priority order:
  - common mistakes
  - learning preferences
  - mastery progress
- inject compact learner-memory summaries into planner or responder inputs when useful
- keep `SimpleMem` changes minimal and integration-oriented

Current WSL rebuild status:
- first read-only slice is implemented:
  - a thin `LightRAG` adapter reads learner-scoped `session_summaries` and `observations` from `SimpleMem-Cross` SQLite
  - open-turn live prompts receive:
    - `common_mistakes`
    - `preferences`
    - `mastery_signals`
    - compact `summary_text`
  - lesson runtime falls back cleanly when prompt injection is disabled or lookup fails
- second writeback slice is also implemented:
  - each page lesson start creates or binds one `SimpleMem-Cross session`
  - each lesson turn appends a `session_event`
  - deterministic distillation writes `mistake / preference / mastery` observations
  - page close or page switch writes a compact `session_summary`
  - prompt injection excludes the current active `memory_session_id` so same-session traces do not immediately feed back as long-term memory
- third semantic-recall slice is now implemented:
  - lesson observations can be upserted into the `SimpleMem-Cross` LanceDB table as `lesson_trace` vector memories
  - open-turn prompt injection can recall compact semantic hints from LanceDB
  - the active `memory_session_id` is excluded to prevent same-session echo
- still pending:
  - deeper reuse of upstream `SimpleMem` vector entries beyond lesson-trace memories
  - broader AIRI-facing use of long-term memory cues

Recommended integration pattern:
- keep most PepTutor-specific orchestration in `LightRAG`
- add a thin adapter around `backend/SimpleMem/cross/`
- avoid invasive changes to upstream `SimpleMem` internals unless tests prove they are necessary

Deliverables:
- memory adapter
- trace-to-memory distillation step
- learner-memory summary injector
- lesson-trace writeback adapter
- semantic recall adapter

Validation:
- `cd backend/SimpleMem && python -m pytest tests cross/tests`
- adapter tests for write-back priority and recall summarization
- end-to-end test showing memory affects a later lesson turn
- current SQLite + LanceDB read/write slice validation in `backend/LightRAG`:
  - `tests/test_simplemem_prompt_memory.py`
  - `tests/test_simplemem_semantic_memory.py`
  - `tests/test_simplemem_writeback.py`
  - `tests/test_lesson_runtime.py`
  - `tests/test_lesson_runtime_factory.py`
  - result: `33 passed`
  - targeted regression including retrieval/raw/support paths: `53 passed`
  - real semantic-memory smoke: passed after installing `lancedb==0.25.3` and `pyarrow==22.0.0` into `backend/LightRAG/.venv`

## Phase 6: AIRI Integration and End-to-End Flow
Goal: expose the lesson runtime inside AIRI with a clear teaching-mode UI.

Recommended new frontend area:
- `frontend/airi/apps/stage-web/src/features/lesson/`

Scope:
- add a lesson API client
- add lesson-mode state and view model
- show current page, current teaching target, drill state, and short teacher feedback
- support text-first interaction first, then layer voice and avatar cues after the text loop is stable
- map backend pedagogy cues to AIRI visual or motion cues

Deliverables:
- stage-web lesson-mode entry
- lesson API client
- minimal teaching UI for pilot pages

Validation:
- `cd frontend/airi && pnpm test:run`
- `cd frontend/airi && pnpm lint && pnpm typecheck`
- local end-to-end smoke using the pilot unit

## Recommended Slice Order
Implement in this exact order:

1. freeze pilot data and schema
2. build text-only lesson runtime
3. add scoped Qdrant retrieval
4. wire pedagogy planner and responder
5. add SimpleMem write-back and recall
6. add AIRI lesson-mode UI

## Non-Goals for the First Pass
- whole-book ingestion before the pilot loop is stable
- free-form global retrieval during answer evaluation
- deep rewrites of upstream AIRI, LightRAG, or SimpleMem internals
- voice-first behavior before the text loop works
- full curriculum expansion before `G5 S1 U3` is stable

## Immediate Next Slice
The current best next implementation slice is:

1. keep the current runtime state and retrieval contract stable
2. keep the current `SimpleMem` SQLite + LanceDB adapters behind the same lesson payload contract
3. move to `AIRI` lesson-mode integration or broader pilot coverage
4. preserve deterministic fallback while deeper memory integration is still being tuned

This keeps the build moving from backend memory completion into end-to-end teaching product integration without reopening already-stable lesson-runtime or retrieval slices.
