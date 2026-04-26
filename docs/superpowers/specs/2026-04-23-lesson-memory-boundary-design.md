# Lesson Memory Boundary Design

## Status
This document records the approved boundary for `/lesson` personality and long-term memory. It narrows the next implementation slice to one reviewable unit: keep AIRI personality ownership where it already lives, and converge lesson learner memory onto the backend as the only source of truth.

This is not the global "all AIRI memory everywhere" design. It is the boundary-setting spec for the `/lesson` route first.

## Goal
Make `/lesson` behave like one coherent runtime instead of two overlapping systems.

The concrete target is:

- one authoritative personality source
- one authoritative long-term memory source
- no hidden second channel that can silently influence prompts
- explicit isolation between projects, students, and sessions
- observable recall and writeback behavior during browser and backend validation

When this slice is complete, it should be accurate to say:

`/lesson` uses AIRI personality as its runtime character source and backend memory as its persistent learner-memory source.

It should still not be claimed that:

- all AIRI routes share one unified long-term memory system
- the backend owns character personality
- notebook history is a real memory authority

## Scope
This design applies to the `/lesson` runtime only.

Included:

- lesson memory ownership
- lesson personality ownership
- lesson recall and writeback flow
- lesson storage scoping and isolation
- lesson-side debug visibility
- lesson acceptance criteria

Excluded from this slice:

- global AIRI chat and `/` route memory unification
- backend-driven character personality authoring
- a new long-term memory product abstraction for every route
- rewriting the lesson pedagogy engine
- changing the lesson knowledge retrieval design
- replacing the existing AIRI card system

## Design Baseline
The current codebase already points toward the right boundary, but it is not fully enforced.

What is already true:

- AIRI personality comes from the character card and runtime prompt assembly in the frontend.
- lesson runtime already performs backend learner-memory recall and writeback through the `LightRAG -> SimpleMem-compatible` path.
- lesson UI also writes turn summaries into the frontend notebook store.

What is not yet clean:

- the frontend notebook still looks like a second memory channel even though it is local-only
- backend storage defaults are still implicit enough to risk cross-project mixing
- semantic-memory scoping is weaker than prompt-memory scoping
- `/lesson` lacks a first-class debug surface that shows whether recall and writeback actually happened

The working baseline for this spec is:

1. personality remains frontend-owned
2. long-term learner memory becomes backend-owned
3. notebook becomes a mirror, not a source
4. storage boundaries become explicit and testable

## Architecture Boundaries

### Personality Boundary
Personality stays in the AIRI runtime layer.

The authoritative personality inputs remain:

- character card `systemPrompt`
- character card `description`
- character card `personality`
- any existing orchestrator/runtime prompt composition already used by AIRI

The backend may consume personality-derived prompt context if the frontend passes it through existing runtime plumbing, but the backend must not become a second personality author. It must not generate an alternative canonical persona profile, and it must not overwrite card-owned identity.

This means:

- no backend personality profile table for `/lesson`
- no backend writeback into character-card personality fields
- no "memory learned a new personality" path
- no second prompt template that overrides the card's teacher voice as the canonical source

The backend is allowed to store learner-facing facts such as preferences or recurring mistakes, but those facts are not character personality. They are learner memory and must stay in that category.

### Long-Term Memory Boundary
Persistent learner memory belongs to the backend only.

The backend memory authority covers:

- recurring mistakes
- learner preferences
- mastery progress
- durable lesson history features that should influence future turns

The frontend may cache or display memory-derived information, but it does not get to decide what the durable learner profile is.

This means:

- lesson prompt-time learner memory comes from backend recall only
- lesson writeback goes to backend memory only
- frontend notebook entries cannot be read back as memory truth for future planning or prompting
- if notebook and backend disagree, backend wins by definition

### Notebook Boundary
The notebook remains useful, but only as a presentation and debugging surface.

It is explicitly allowed to serve as:

- a readable diary of turns
- a developer-facing transcript/mirror
- a local history surface for inspection

It is explicitly not allowed to serve as:

- the prompt-time learner memory source
- a fallback that silently substitutes for backend recall
- an authority that can change planning or response behavior by itself

### Route Boundary
This slice is route-scoped to `/lesson`.

The lesson runtime should become internally coherent without requiring that the main AIRI chat route already shares the same backend learner-memory authority. That broader unification is a later slice.

### Storage Boundary
Project, tenant, student, and session scoping must be explicit.

The design requires distinct handling for:

- `project`
- `student_id`
- backend `memory_session_id`
- frontend-visible `content_session_id`

No storage layer should rely on "the current default folder" or "the current default project string" as the only isolation mechanism.

## Component Breakdown

### `backend/LightRAG/lightrag/orchestrator/lesson_runtime.py`
This remains the single runtime entry point for lesson memory behavior.

Responsibilities in this design:

- derive or recover the effective backend memory session for the current learner and lesson context
- perform recall before planning/responding
- inject a compact learner-memory summary into the lesson turn pipeline
- perform writeback after the turn completes
- emit structured debug metadata for the frontend or logs

It should not:

- invent a second personality source
- depend on frontend notebook state
- silently switch to local frontend history when backend memory fails

### `backend/LightRAG/lightrag/orchestrator/lesson_runtime_factory.py`
This remains the composition point for memory providers and storage configuration.

Responsibilities in this design:

- make `project`, storage path, and provider configuration explicit
- build the prompt-memory provider and writeback provider under the same isolation policy
- avoid accidental mixing caused by implicit defaults

This file is where boundary mistakes become operational bugs. If the system still defaults to a shared global DB path or vague project label, isolation remains accidental rather than guaranteed.

### `backend/LightRAG/lightrag/orchestrator/simplemem_prompt_memory.py`
This remains the prompt-time recall layer.

Responsibilities in this design:

- recall only the learner memory that belongs to the active `student_id` and `project`
- exclude the active session when the design requires cross-session recall
- return compact, prompt-safe summaries rather than raw storage payloads

The prompt-memory layer already scopes more safely than the semantic layer. This spec keeps that direction and treats it as the minimum acceptable isolation standard.

### `backend/LightRAG/lightrag/orchestrator/simplemem_writeback.py`
This remains the durable writeback layer.

Responsibilities in this design:

- persist turn-derived learner memory under the same `project` and `student_id` boundary used by recall
- guarantee session creation and session lookup do not collide across projects or retries
- emit enough structured metadata to support debugging and tests

This layer must stop relying on assumptions that only hold when one project uses the database.

### `backend/LightRAG/lightrag/orchestrator/simplemem_semantic_memory.py`
This is the highest-risk boundary component in the current design.

Responsibilities in this design:

- apply the same effective isolation semantics as prompt-memory recall
- prevent semantic recall from crossing project boundaries when the same `student_id` appears in more than one project
- make filtering behavior inspectable in tests

If the semantic layer cannot yet persist `project` natively, this slice must still impose an equivalent isolation strategy before it can be treated as safe enough to power prompt-time recall.

### `frontend/airi/packages/stage-ui/src/stores/lesson-chat-provider.ts`
This remains the lesson-to-AIRI bridge on the frontend side.

Responsibilities in this design:

- continue sending lesson turns into AIRI chat/runtime surfaces
- continue reflecting teacher and learner turns into UI-visible history
- stop implying that notebook writes are durable memory writes
- surface backend memory debug metadata to the lesson UI when available

This bridge should be the place where the UI learns what the backend recalled or wrote. It should not become a second place that decides learner memory content.

### `frontend/airi/packages/stage-ui/src/stores/character/notebook.ts`
This store survives, but its meaning changes.

Responsibilities in this design:

- store diary/debug history for UI inspection
- remain safe to clear without changing backend learner memory
- behave like a mirror or cache

It should not:

- claim authority over learner memory state
- be read by the planner or lesson responder as if it were durable truth
- silently backfill missing backend memory behavior

### Lesson Memory Debug Surface
This slice requires a first-class debug surface, either in the lesson page or in an existing developer-facing panel.

It should display at least:

- active `student_id`
- active `project`
- current backend memory session id
- last recall status
- last recall summary or hit metadata
- last writeback status
- last writeback summary
- degradation state when backend memory failed or was skipped

This is not cosmetic. It is needed so browser smoke can validate real memory behavior rather than only visual chat bubbles.

## Data Flow

### 1. Lesson Start
When a lesson page is started or resumed:

- the frontend provides a stable `student_id`
- the backend resolves the active `project`
- the backend creates or restores the backend memory session for that learner and lesson context
- the runtime exposes the resolved memory identity through debug metadata

The effective identity for memory work must be deterministic. Re-entering the same lesson should not accidentally create an unrelated learner-memory universe because a local session id changed.

### 2. Turn Preparation
Before a learner turn is planned or answered:

- the lesson runtime performs backend recall
- recall uses the learner identity and project boundary
- recall returns a compact summary of relevant durable learner state
- that summary is injected into the lesson turn pipeline

The planner and responder may use learner-memory context, but they must consume the backend result only. The frontend notebook is not part of this path.

### 3. Prompt Assembly
During prompt assembly:

- personality context still comes from AIRI runtime/card composition
- learner-memory context comes from backend recall
- lesson state and pedagogy state come from the lesson runtime

This split is the core design rule:

- character identity and voice from AIRI
- learner history from backend memory
- current teaching state from lesson runtime

No one layer should impersonate another.

### 4. Turn Completion
After the turn result is available:

- the runtime derives writeback candidates such as mistakes, preferences, and mastery signals
- backend writeback persists the durable learner-memory update
- writeback emits debug metadata
- frontend notebook receives a mirrored diary/debug entry

The notebook write is downstream of the real memory write. It is not the real memory write.

### 5. Degraded Operation
If backend memory recall or writeback fails:

- the lesson turn is still allowed to complete
- the runtime marks the turn as degraded
- the frontend debug surface shows the degraded state
- the notebook may still receive the visible diary entry
- the degraded path must not pretend the learner memory was updated successfully

The important rule is honesty. A successful chat bubble is not evidence of successful memory behavior.

## Fault Isolation and Failure Handling

### No Dual Authority
The system must not operate in a mode where backend memory and notebook memory both appear authoritative.

Required rule:

- backend memory influences prompt behavior
- notebook does not

This removes a whole class of debugging failures where the visible UI history and the actual memory authority drift apart.

### No Silent Fallback to Notebook Memory
If backend recall fails, the system may continue the lesson without memory, but it must not silently read notebook entries and pretend recall succeeded.

Silent fallback would produce the worst possible operational shape:

- developers think backend memory works
- the user sees plausible behavior
- the prompt is actually driven by local, non-durable, route-scoped history

This design explicitly forbids that.

### Project Isolation
Prompt memory and semantic memory must not cross project boundaries.

If the current semantic store does not persist `project`, this slice must add an equivalent isolation rule before semantic recall is trusted as part of the durable learner profile. An incomplete isolation model is not a documentation issue; it is a correctness bug.

### Session Identity Safety
`content_session_id` and backend session identity must not collide across:

- different projects
- retries
- repeated lesson starts
- resumed sessions

If a global uniqueness constraint is kept at the storage layer, the identity generation policy must respect it. If the current identity shape is too weak, this slice must strengthen it rather than assuming collisions are rare.

### Explicit Degradation
Backend memory failures must be visible and inspectable.

Required outputs:

- structured log or debug metadata for recall failure
- structured log or debug metadata for writeback failure
- UI-visible degraded status in the debug surface

This keeps the system debuggable under real browser smoke and local development instead of only under ideal-path unit tests.

## Acceptance and Validation

### Behavioral Acceptance
The slice is complete only if all of the following statements are true:

- `/lesson` uses AIRI card/runtime prompt composition as the only personality authority
- `/lesson` uses backend memory recall as the only prompt-time learner-memory authority
- frontend notebook data does not change prompt behavior
- one completed learner turn results in observable backend recall/writeback metadata
- backend memory failures degrade honestly without pretending success

### Backend Validation
Add or update targeted backend tests for:

- recall scoping by `student_id`
- recall isolation by `project`
- semantic recall isolation under the same effective project boundary
- writeback scoping by `student_id` and `project`
- session identity uniqueness or collision avoidance
- degraded behavior when memory recall fails
- degraded behavior when memory writeback fails

The goal is not broad test volume. The goal is to pin the exact failure modes that would reintroduce dual authority or cross-project memory mixing.

### Frontend Validation
Add or update frontend tests and browser smoke so that they verify memory behavior directly rather than inferring it from chat UI.

At minimum:

- `/lesson` browser smoke should assert the presence of backend memory debug metadata after a turn
- notebook UI state should still update for visibility
- the smoke should distinguish "chat worked" from "memory worked"

If the debug surface reports degraded operation, browser validation should treat that as an explicit state, not as silent success.

### Operational Validation
A manual developer run should be able to answer these questions without code inspection:

- which learner identity was used
- which project boundary was used
- which backend memory session was active
- whether recall ran
- whether writeback ran
- whether the turn degraded

If these answers are not available from the running system, the slice is not operationally finished even if unit tests pass.

## Non-Goals for This Slice
This design does not attempt to solve:

- full AIRI-wide memory unification across all routes
- backend-authored personality systems
- a complete long-term memory product model for every future agent
- notebook removal
- lesson pedagogy redesign
- speech pipeline redesign

These may come later, but they should not be mixed into the current slice. The purpose here is boundary correctness first.

## Completion Standard
This design should be considered implemented only when the system behavior matches the following concise statement:

`/lesson` has one personality source and one long-term memory source, and both are observable, isolated, and testable.`
