# Lesson Memory Boundary Implementation Plan

## Status
This plan translates the approved design in `docs/superpowers/specs/2026-04-23-lesson-memory-boundary-design.md` into a concrete build order for the current repository state.

The purpose of this plan is not to redesign `/lesson`. The design is already fixed. This document defines the implementation sequence that gets the codebase from the current mixed-boundary state to the approved "one personality source, one long-term memory source" state.

## Current Reality
The current repository already contains most of the raw pieces, but the boundary is only partially enforced.

What is already in place:

- AIRI personality ownership already lives in the frontend card/runtime layer.
- lesson runtime already performs backend memory recall and writeback through the `LightRAG -> SimpleMem-compatible` integration.
- prompt-memory SQLite recall already scopes by both `student_id` and `project`.
- `/lesson` already has browser smoke coverage for the main chat and speech loop.

What is still incorrect or incomplete:

- frontend notebook writes still look too much like a memory channel rather than a mirror/debug surface
- session binding in SQLite is not fully isolated because `content_session_id` lookup is too weak
- semantic memory recall and writeback do not carry the same `project` boundary as prompt-memory recall
- the running lesson UI does not expose enough backend memory debug metadata to prove recall/writeback behavior end-to-end
- current tests do not pin all of the boundary regressions called out in the design

## Planning Principles
- fix correctness boundaries before adding broader AIRI-wide memory reuse
- keep the slice reviewable by separating backend isolation, frontend mirror semantics, and debug visibility
- prefer additive contract tightening over broad refactors
- do not let notebook state influence prompt-time learner memory
- validate every boundary change with the narrowest useful tests first, then broader route-level smoke

## Target Result
After this plan is fully implemented, the codebase should satisfy all of the following:

- `/lesson` personality is still owned by AIRI runtime/card prompt composition
- `/lesson` prompt-time learner memory comes only from backend recall
- lesson memory writeback persists under explicit `project` and `student_id` boundaries
- semantic recall cannot cross projects for the same learner identifier
- frontend notebook behaves as a mirror/debug surface only
- the running lesson UI exposes enough memory debug data to verify recall, writeback, and degradation

## Build Strategy
Use four implementation phases. Each phase should be independently reviewable and should leave the repo in a testable state.

## Phase 1: Backend Boundary Hardening
Goal: make backend memory scoping correct before changing frontend semantics.

Scope:

- tighten SQLite session binding so session lookup cannot reuse a `content_session_id` across the wrong `project` or learner
- decide and implement the required session identity rule for `content_session_id`
- make semantic memory writeback carry explicit `project` identity
- make semantic recall filter by the same effective project boundary used by prompt-memory SQLite recall
- ensure lesson runtime and factory wiring pass the right scope information without relying on ambiguous defaults

Primary files:

- `backend/LightRAG/lightrag/orchestrator/lesson_runtime.py`
- `backend/LightRAG/lightrag/orchestrator/lesson_runtime_factory.py`
- `backend/LightRAG/lightrag/orchestrator/simplemem_writeback.py`
- `backend/LightRAG/lightrag/orchestrator/simplemem_prompt_memory.py`
- `backend/LightRAG/lightrag/orchestrator/simplemem_semantic_memory.py`

Deliverables:

- corrected session binding rules
- corrected semantic-memory storage and recall scoping
- explicit project-aware backend contracts where they are currently implicit

Validation:

- targeted `pytest` for `test_simplemem_writeback.py`
- targeted `pytest` for `test_simplemem_prompt_memory.py`
- targeted `pytest` for `test_simplemem_semantic_memory.py`
- targeted `pytest` for `test_lesson_runtime.py` and `test_lesson_runtime_factory.py`
- `ruff check .` in `backend/LightRAG`

## Phase 2: Frontend Memory Ownership Cleanup
Goal: stop the frontend from looking like a second learner-memory authority.

Scope:

- make `lesson-chat-provider.ts` treat backend memory as the only durable memory authority
- keep notebook writes for diary/debug visibility only
- remove any naming, comments, or UI assumptions that imply notebook is a true long-term memory source
- make notebook-clearing semantics safe and explicit

Primary files:

- `frontend/airi/packages/stage-ui/src/stores/lesson-chat-provider.ts`
- `frontend/airi/packages/stage-ui/src/stores/character/notebook.ts`
- any lesson-facing components that currently present notebook content as if it were learner memory truth

Deliverables:

- frontend bridge logic that mirrors backend memory behavior instead of competing with it
- notebook semantics that are clearly cache/debug only

Validation:

- targeted Vitest coverage for lesson store behavior where needed
- `pnpm -F @proj-airi/stage-ui typecheck`
- `pnpm -F @proj-airi/stage-web typecheck`

## Phase 3: Memory Debug Surface
Goal: make backend memory behavior visible during real route testing.

Scope:

- expose memory debug metadata from backend runtime and frontend bridge
- render the required debug fields somewhere stable in the lesson route or an existing developer-facing panel
- distinguish success, skipped, and degraded states for recall and writeback
- make the debug surface usable in browser smoke assertions

Required visible fields:

- active `student_id`
- active `project`
- active backend `memory_session_id`
- last recall status
- last recall summary or hit metadata
- last writeback status
- last writeback summary
- degradation state

Primary files:

- backend lesson runtime result/debug payload types
- frontend lesson provider/store
- lesson page components that can safely surface debug state
- lesson browser smoke tests

Deliverables:

- observable memory debug surface
- route-level assertions that prove memory work happened

Validation:

- targeted frontend browser tests for `/lesson`
- `bash frontend/airi/scripts/smoke_lesson_browser.sh` if the slice touches real route contracts

## Phase 4: Final Boundary Regression Pass
Goal: lock down the boundary so future changes do not silently reintroduce dual authority.

Scope:

- add or tighten tests for project isolation, learner isolation, session reuse, and degradation behavior
- verify prompt-memory, semantic-memory, and writeback paths all agree on the effective boundary
- verify notebook state does not affect prompt-time learner-memory behavior
- verify the debug surface reflects real backend state under success and failure conditions

Deliverables:

- regression tests for the exact failure modes identified in the design
- final verification notes for the slice

Validation:

- focused backend and frontend suites from earlier phases
- broader `pnpm -F @proj-airi/stage-web test:run:browser -- src/pages/lesson/index.browser.test.ts --reporter verbose`
- broader `pnpm -F @proj-airi/stage-web typecheck`

## Recommended Execution Order
The concrete order of work should stay fixed:

1. backend session and semantic isolation
2. frontend notebook ownership cleanup
3. memory debug surface
4. final regression pass

The reason is simple:

- if backend isolation is still wrong, frontend cleanup only hides the problem
- if debug visibility lands before the contracts are corrected, the UI will faithfully show broken boundaries
- if regression coverage lands before the behavior is stable, tests will have to be rewritten immediately

## First Slice To Build Now
The first implementation slice should be `Phase 1: Backend Boundary Hardening`.

That slice directly addresses the highest-risk correctness gaps already confirmed in the code:

- prompt-memory SQLite recall uses `student_id + project`
- session binding does not fully use that same boundary
- semantic memory does not currently carry `project` through storage and recall

Fixing those three mismatches first creates a stable base for the frontend mirror/debug work.

## Completion Standard
This plan is complete only when the repository can support the following statement without qualification:

`/lesson` backend memory boundaries are explicit, project-safe, learner-safe, and observable, and the frontend no longer acts like a second long-term memory authority.`
