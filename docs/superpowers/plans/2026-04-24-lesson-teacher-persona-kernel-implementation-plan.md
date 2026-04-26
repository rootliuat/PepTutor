# Lesson Teacher Persona Kernel Implementation Plan

Date: 2026-04-24

## Status

This plan implements the design in `docs/superpowers/specs/2026-04-24-lesson-teacher-persona-kernel-design.md` as small reviewable tasks.

The plan intentionally avoids a large "rewrite the whole agent" change. Each task must be independently testable, reviewable, and revertible.

## Current Reality

Already implemented or partially implemented:

- `/lesson` uses `backend/LightRAG` as the route/runtime service.
- `LessonRuntime` controls page state, turn routing, answer evaluation, retrieval mode, and final result shape.
- structured support-asset lookup exists for vocabulary and useful expressions.
- optional Qdrant-backed vector reranking exists behind `PEPTUTOR_LESSON_VECTOR_RETRIEVAL`.
- SimpleMem-compatible prompt recall, semantic recall, and writeback adapters exist.
- `POST /lesson/turn/stream` streams teacher text deltas.
- frontend barge-in cancels active playback/stream and ignores stale turn ids.
- AIRI action payloads already cover baseline emotion, motion, expression, teaching action, and evaluation.

Still missing:

- a versioned teacher persona profile contract
- explicit relationship/affect state assembly before teacher response
- Alma-style memory layering into facts, episodes, and procedures
- persona drift regression tests
- objective persona/debug signals in `/lesson`
- full frontend application of speech style, emotion, motion, mouth intensity, and fallback reporting
- real-device acceptance for persona plus voice behavior

## Execution Rules

- Keep LessonRuntime as the content authority.
- Keep AIRI as the embodied execution layer.
- Do not add an unbounded agent loop to live lesson turns.
- Every backend slice gets focused pytest coverage and ruff.
- Every frontend visual slice gets typecheck plus Playwright screenshot review.
- Every voice/runtime slice gets browser smoke; final voice acceptance still requires a real headset/mic.
- No slice is accepted without a short review note: changed behavior, tests run, residual risk.

## Recommended Task Order

### Task 1: Persona Contract And Fixtures

Status: completed on 2026-04-24.

Goal: define the stable data contract before wiring it into generation.

Scope:

- add a versioned `TeacherPersonaProfile` schema
- add a compact `LessonPersonaContext` schema
- add an `AiriPerformancePlan` schema if the current action payload is not expressive enough
- create one default PepTutor teacher profile
- document fields that are allowed to affect teaching style versus fields that must not affect correctness

Primary areas:

- `backend/LightRAG/lightrag/orchestrator/`
- `backend/LightRAG/tests/`
- optional shared docs under `docs/superpowers/specs/`

Review checklist:

- schema is small enough to fit every turn
- no field can override target answer, page, block, or evaluation
- profile id and version are explicit
- defaults are deterministic

Validation:

- focused pytest for schema validation and default profile loading
- `ruff check` on touched backend files

Acceptance:

- a reviewer can read one JSON/model object and understand the teacher's stable style and allowed influence boundaries

Completion note:

- Added `lesson_persona.py` with versioned `TeacherPersonaProfile`, compact `LessonPersonaContext`, `LearnerRelationshipProfile`, `ClassroomAffectState`, `AiriPerformancePlan`, and deterministic default PepTutor teacher profile.
- Explicit boundaries keep `LessonRuntime` as content authority and AIRI as presentation authority.
- Added focused schema tests in `test_lesson_persona.py`.
- Validation: `.venv/bin/python -m pytest tests/test_lesson_persona.py -q` passed, `.venv/bin/ruff check lightrag/orchestrator/lesson_persona.py tests/test_lesson_persona.py` passed.
- Residual risk: the contract is not wired into runtime generation yet; Task 2 will assemble and expose persona context per turn without changing teacher text first.

### Task 2: Backend Persona Context Assembler

Status: completed on 2026-04-24.

Goal: assemble teacher persona plus learner relationship memory before response generation.

Scope:

- read the default teacher profile
- reuse current SimpleMem prompt recall
- convert recalled mistakes/preferences/mastery signals into `LearnerRelationshipProfile`
- derive a minimal `ClassroomAffectState` from turn label, evaluation, help requests, interruptions, and recent state
- expose persona debug signals without changing final teacher text yet

Primary areas:

- `lesson_runtime.py`
- `lesson_runtime_factory.py`
- `simplemem_prompt_memory.py`
- new persona module if needed

Review checklist:

- no cross-student or cross-project memory leakage
- active session exclusion still works
- affect state is deterministic and explainable
- debug signal shows what influenced the turn

Validation:

- `pytest tests/test_lesson_runtime.py`
- `pytest tests/test_lesson_runtime_factory.py`
- `pytest tests/test_simplemem_prompt_memory.py`
- `ruff check` on touched backend files

Acceptance:

- a route result can show persona profile, relationship signals, and affect state for the turn

Completion note:

- Extended `lesson_persona.py` with deterministic assemblers that convert SimpleMem prompt-memory buckets into `LearnerRelationshipProfile`, derive `ClassroomAffectState`, and map the turn into a presentation-only `AiriPerformancePlan`.
- Extended `LessonRuntime` debug output with a `persona` signal containing profile id/version, Xiaoxiao voice hint, allowed/protected boundaries, relationship signals, relationship memory snippets, affect state, and AIRI performance plan.
- Kept teacher response text unchanged; this slice only makes the persona context visible and testable for Task 3 prompt wiring.
- Validation: `.venv/bin/python -m pytest tests/test_lesson_persona.py -q`, `.venv/bin/python -m pytest tests/test_lesson_runtime.py -q`, `.venv/bin/python -m pytest tests/test_lesson_runtime_factory.py -q`, `.venv/bin/python -m pytest tests/test_simplemem_prompt_memory.py -q`, touched-file `ruff check`, and `NO_PROXY=127.0.0.1,localhost,::1 backend/LightRAG/.venv/bin/python scripts/smoke_lesson_turn.py` all passed.
- Follow-up closed by Task 3: persona context is now injected into `LessonResponder` while preserving lesson correctness authority.

### Task 3: Persona-Aware Responder Prompt

Status: completed on 2026-04-24.

Goal: make teacher text consistently reflect the persona without breaking lesson correctness.

Scope:

- add persona context to `LessonResponder` prompt assembly
- keep lesson objective, target answer, and evaluation higher priority than persona style
- add output constraints for concise classroom speech
- add tests that the same learner situation produces stable style markers
- add tests that persona cannot change correctness judgment or page progression

Primary areas:

- `backend/LightRAG/lightrag/pedagogy/responder.py`
- `backend/LightRAG/lightrag/orchestrator/lesson_runtime.py`
- related tests

Review checklist:

- prompt is not overloaded with raw memory
- persona affects delivery style, not lesson truth
- deterministic fallback path remains acceptable
- streaming path still emits real deltas

Validation:

- focused responder/runtime pytest
- route smoke through `scripts/smoke_lesson_turn.py`
- ruff on touched backend files

Acceptance:

- sampled teacher replies show stable persona and better scaffolding, while evaluation and target answer remain unchanged

Completion note:

- Passed the compact `LessonPersonaContext` into `LessonResponder` for both normal and streaming teacher turns.
- Added prompt boundaries so persona can shape tone, pacing, encouragement, scaffold granularity, classroom habits, speech style, and AIRI presentation intent, but cannot change target answers, correctness, page progression, retrieval scope, current block, or required teaching action.
- Added compact persona payload shaping in `responder.py` so raw memory does not expand beyond the existing prompt-memory payload; relationship signals stay capped by the Task 2 assembler.
- Added hard fallback protection for `confirm` turns that drop required practice phrases, including service-question prompts such as `What would you like to eat?`.
- Added regression coverage that persona context reaches the responder, memory-derived relationship signals shape the prompt, stable catchphrases are available, and persona output cannot change evaluation or page progression.
- Validation: `.venv/bin/python -m pytest tests/test_lesson_runtime.py -q`, `.venv/bin/python -m pytest tests/test_lesson_persona.py -q`, `.venv/bin/python -m pytest tests/test_lesson_runtime_factory.py -q`, `.venv/bin/python -m pytest tests/test_simplemem_prompt_memory.py -q`, touched-file `ruff check`, and `NO_PROXY=127.0.0.1,localhost,::1 .venv/bin/python ../../scripts/smoke_lesson_turn.py` all passed.
- Residual risk: this completes backend prompt wiring only. Full AIRI-wide persona settings, memory layering, and embodied behavior evaluation remain in later tasks.

### Task 4: Alma-Style Memory Layering

Status: completed on 2026-04-24 for the first backend slice.

Goal: improve SimpleMem usefulness by separating facts, episodes, and procedures.

Scope:

- extend distillation/writeback to classify memory candidates as fact, episode, or procedure
- preserve existing common mistake, preference, and mastery buckets
- add relevance ranking so old generic memories do not dominate current page facts
- add duplicate/conflict handling for repeated facts
- keep raw session history out of the hot prompt path

Primary areas:

- `simplemem_writeback.py`
- `simplemem_prompt_memory.py`
- `simplemem_semantic_memory.py`
- tests for SimpleMem adapters

Review checklist:

- procedure memory cannot become a hidden teaching policy override
- episode summaries stay compact
- facts/procedures are project- and learner-scoped
- stale/conflicting memories are filtered or ranked lower

Validation:

- `pytest tests/test_simplemem_writeback.py`
- `pytest tests/test_simplemem_prompt_memory.py`
- `pytest tests/test_simplemem_semantic_memory.py`
- `ruff check` on touched backend files

Acceptance:

- repeated learner behavior creates durable memory that can be recalled in a later session and used as style/scaffold context

Completion note:

- Added prompt-safe `LayeredMemoryItem` output to `LearnerMemorySummary` so recalled memory is explicitly separated into `fact`, `episode`, and `procedure`.
- Added `MemoryConflictResolution` output for stable progress conflicts. When repeated mistake and repeated mastery signals disagree on the same target, prompt memory now records the chosen category and suppressed category instead of silently injecting both.
- Added durable promotion behavior on the read side: repeated supported progress can appear as a stable `fact` even when the legacy common-mistake/mastery buckets stay deduped for backward compatibility.
- Added writeback-side `memory_layer` and `promotion_policy` metadata. Lesson mistakes and mastery are stored as `episode` candidates that can be promoted after repeated support; style preferences are stored as `procedure`.
- Updated `LessonResponder` prompt rules so `learner_memory.memory_layers` are private hints only: facts predict stable needs, episodes describe recent context, and procedures shape style without changing lesson targets.
- Validation: `.venv/bin/python -m pytest tests/test_simplemem_prompt_memory.py -q`, `.venv/bin/python -m pytest tests/test_simplemem_writeback.py -q`, `.venv/bin/python -m pytest tests/test_simplemem_semantic_memory.py -q`, `.venv/bin/python -m pytest tests/test_lesson_runtime.py -q`, `.venv/bin/python -m pytest tests/test_lesson_persona.py -q`, `.venv/bin/python -m pytest tests/test_lesson_runtime_factory.py -q`, touched-file `ruff check`, and `NO_PROXY=127.0.0.1,localhost,::1 .venv/bin/python ../../scripts/smoke_lesson_turn.py` all passed.
- Residual risk: this is not a full Alma-style independent memory lifecycle yet. It establishes the backend layering contract and promotion/conflict rules used by the current lesson prompt path.

### Task 5: AIRI Performance Planner

Status: completed on 2026-04-24 for the backend action-payload slice.

Goal: convert persona, affect, teaching action, and evaluation into embodied behavior.

Scope:

- map `ClassroomAffectState` plus `teaching_action` plus `evaluation` to `AiriPerformancePlan`
- include `emotion`, `expression`, `motion`, `speech_style`, `mouth_intensity`, and `interrupt_policy`
- preserve existing ACT payload compatibility
- make fallbacks explicit when a model cannot perform a requested expression/motion

Primary areas:

- backend lesson action payload generation
- frontend lesson store/action parser
- stage runtime mapping

Review checklist:

- every current `teaching_action` has a mapping
- every current answer evaluation has a mapping
- interruption state wins over normal speaking state
- frontend never rewrites teacher text

Validation:

- backend action payload tests
- frontend parser/store tests
- `pnpm -F @proj-airi/stage-web typecheck`

Acceptance:

- debug signals and frontend state agree on the selected performance plan

Completion note:

- `LessonRuntime` now emits stream `action` metadata after assembling the same per-turn `LessonPersonaContext` used by the responder, so `POST /lesson/turn/stream` no longer relies only on the old static teaching-action/evaluation profile.
- `lesson_routes.py` now prefers `AiriPerformancePlan` when present and maps it into the existing AIRI-compatible ACT fields: `emotion`, `motion`, `expression`, and `duration_ms`.
- The action payload now also carries presentation metadata for the lesson frontend/runtime: `speech_style`, `mouth_intensity`, `interrupt_policy`, `content_source`, `fallback_allowed`, and `performance_source`.
- Legacy static evaluation/action profiles remain as fallback when no persona performance plan is available.
- Added backend regression coverage that proves streamed actions prefer persona performance plans before legacy profiles, while old evaluation/action profile coverage still passes.
- Updated the frontend lesson action payload type and stream-chat test fixture so the new performance metadata is preserved inside ACT tokens.
- Validation: `.venv/bin/python -m pytest tests/test_lesson_runtime.py -q`, `.venv/bin/python -m pytest tests/test_lesson_persona.py tests/test_lesson_runtime_factory.py -q`, touched-file `ruff check`, `NO_PROXY=127.0.0.1,localhost,::1 .venv/bin/python ../../scripts/smoke_lesson_turn.py`, `pnpm -F @proj-airi/stage-ui test:run -- src/stores/lesson-chat-provider.test.ts src/composables/queues.test.ts`, `pnpm -F @proj-airi/stage-ui typecheck`, and touched-file `eslint` all passed.
- Residual risk: this slice completes backend action-payload handoff. Full frontend application of `speech_style` and `mouth_intensity` remains in Task 6, and real headset/mic validation remains in Task 8.

### Task 6: Frontend AIRI Application And Layout Review

Goal: make AIRI visibly perform the backend plan without regressing `/lesson` layout.

Scope:

- consume `AiriPerformancePlan` in the lesson frontend
- apply speech style where the TTS/playback path supports it
- drive Live2D/VRM expression and motion through existing runtime hooks
- show compact debug state for persona/performance decisions
- keep left chat rail and right lesson panel layout clean in light and dark modes

Primary areas:

- `frontend/airi/packages/stage-layouts/src/components/Widgets/`
- `frontend/airi/packages/stage-ui/src/stores/`
- `frontend/airi/apps/stage-web/src/pages/lesson/`

Review checklist:

- no overlapping panels
- no mixed light/dark surface in light mode
- left rail remains chat-only
- mobile still usable
- visible state matches backend debug payload

Validation:

- frontend typecheck
- focused Vitest/browser tests
- Playwright screenshots for light/dark desktop and mobile
- visual inspection of overlap, clipping, abnormal width/height, and control placement

Acceptance:

- screenshots pass visual review and AIRI state visibly changes with lesson turns

### Task 7: Persona Evaluation Harness

Status: completed on 2026-04-24 for the deterministic backend quality-eval slice.

Goal: make "independent personality" measurable.

Scope:

- add scripted multi-turn conversations for help, wrong answer, correct answer, knowledge question, interruption, and returning learner memory
- score retrieval hit, memory hit, persona consistency, lesson correctness, and response quality
- detect persona drift and sycophantic over-agreement
- record outputs under `backend/LightRAG/temp/` or a dedicated eval output directory

Primary areas:

- backend eval scripts
- backend route smoke
- docs/testing status

Review checklist:

- metrics are simple and reproducible
- failures point to concrete debug signals
- eval does not require paid TTS
- real-model and deterministic modes are separated

Validation:

- scripted eval command
- route smoke
- relevant pytest

Acceptance:

- the eval can answer: did retrieval hit, did memory matter, did the teacher stay in character, did the lesson stay correct

Completion note:

- Added `lesson_dialogue_quality_eval.py`, `scripts/eval_lesson_dialogue_quality.py`, and `app/knowledge/evals/lesson-dialogue-quality-gold.json`.
- The deterministic gold set currently covers six fixed classroom samples: current-block expression support, unit lexicon support, branch return anchor, stuck-learner correction, SimpleMem prompt-memory influence, and a G6 unit lexicon query.
- The eval reports separate retrieval, response quality, persona, and memory contract rates instead of one subjective "sounds good" label.
- Tightened deterministic `ask_knowledge` fallback wording so raw curriculum summaries and `Key patterns` no longer leak into teacher speech; query-aligned target phrases are preferred for lexicon-style questions.
- Validation: `.venv/bin/python -m pytest tests/test_lesson_dialogue_quality_eval.py tests/test_lesson_retrieval_eval.py -q`, touched-file `ruff check`, `scripts/eval_lesson_dialogue_quality.py`, `scripts/eval_lesson_retrieval.py`, `tests/test_lesson_runtime.py tests/test_lesson_persona.py tests/test_simplemem_prompt_memory.py -q`, and `scripts/smoke_lesson_turn.py` all passed.
- Follow-up slice completed: added `lesson_transcript_quality_eval.py`, `scripts/eval_lesson_transcript_quality.py`, and `tests/test_lesson_transcript_quality_eval.py`.
- The transcript scorer can run the existing temporary route smoke, capture live-model `/lesson/turn` outputs, write them to JSON, and re-score the saved transcript through `--input`.
- Live transcript scoring reports response naturalness, retrieval grounding, persona/AIRI signal presence, live-prompt signal presence, prompt-memory observation, and latency.
- Validation: `.venv/bin/python -m pytest tests/test_lesson_transcript_quality_eval.py tests/test_lesson_dialogue_quality_eval.py -q`, touched-file `ruff check`, `NO_PROXY=127.0.0.1,localhost,::1 backend/LightRAG/.venv/bin/python scripts/eval_lesson_transcript_quality.py --write-transcript backend/LightRAG/temp/lesson_transcript_quality_latest.json`, and saved transcript re-score all passed. Latest live score: `strict=15/15`, `avg_latency=2306ms`, `max_latency=4773ms`.
- Residual risk: this still uses deterministic heuristics over captured live transcripts, not a separate paid LLM judge. Frontend visible-performance scoring remains for Task 6.

### Task 8: Real-Device Voice And Persona Acceptance

Goal: verify the final user-facing experience on real mic/headphones.

Scope:

- run the real-device voice checklist
- verify auto-send, streaming teacher playback, interruption, mouth sync, expression/motion, and persona continuity
- compare backend debug signals against visible AIRI behavior
- record failures as follow-up bugs, not new features

Primary areas:

- `docs/superpowers/checklists/2026-04-24-real-device-voice-checklist.md`
- `docs/lesson-testing-status.md`
- browser screenshots and smoke logs

Review checklist:

- student stop-to-submit feels natural
- teacher begins speaking from stream without long pause
- interruption stops old voice and mouth movement
- teacher remembers relevant learner facts
- teacher does not drift away from the textbook task

Validation:

- real headset/mic
- HTTPS lesson page if required by browser mic policy
- LightRAG backend with Edge Xiaoxiao TTS and Doubao ASR credentials
- browser screenshots and logs

Acceptance:

- the system can be demonstrated as a real-time embodied AI tutor, not just a text chat with audio

## Slice Review Template

Every task should close with this review note:

- Scope completed:
- Files changed:
- Behavior changed:
- Tests run:
- Screenshots captured, if UI:
- Known residual risk:
- Next task:

## Recommended First Task

Start with **Task 1: Persona Contract And Fixtures**.

Reason:

- it is small and reviewable
- it prevents backend/frontend from inventing separate persona payloads
- it gives later tests a stable target
- it does not risk breaking voice or layout

## Completion Standard

This plan is complete only when the repository can support this statement:

`/lesson` has one deterministic teaching brain, one inspectable teacher persona kernel, one learner-memory authority, and one AIRI embodiment layer; each layer is testable and none silently overrides another.
