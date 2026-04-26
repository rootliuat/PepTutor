# Lesson Teacher Mind Task Plan

## Goal
Make PepTutor answer like a prepared G5/G6 English teacher, not a fixed-script page bot or a broad RAG chatbot.

## Task 1: CurriculumMap
Status: done.

Generate a compact four-book curriculum index from existing raw textbook files, word lists, Useful expressions, and `structured/general/*`.

Acceptance:
- covers current catalog scopes
- keeps `source_refs` and `confidence`
- does not hand-write unit goals from memory
- is never injected wholesale into `/lesson/turn`

Implemented:
- builder: `backend/LightRAG/lightrag/orchestrator/curriculum_map_builder.py`
- CLI: `backend/LightRAG/scripts/build_curriculum_map.py`
- output: `app/knowledge/structured/curriculum-map.json`
- tests: `backend/LightRAG/tests/test_curriculum_map_builder.py`
- page-level pilot assets are applied as higher-confidence overlays, so existing manual corrections such as `TB-G5S1U3-P31` being `story` override coarse general drafts

## Task 1.5: Curriculum Overview Export
Status: done.

Export the existing structured curriculum map as a human-readable Chinese overview.
This is an offline review artifact and does not block Task 4.

Acceptance:
- derives from `curriculum-map.json`
- covers all four books and all unit/recycle scopes
- shows Chinese section labels for unit theme, teaching goals, vocabulary, grammar/patterns, page types, source refs, and confidence
- does not replace the structured runtime map

Implemented:
- builder: `backend/LightRAG/lightrag/orchestrator/curriculum_overview_builder.py`
- CLI: `backend/LightRAG/scripts/export_curriculum_overview.py`
- output: `app/knowledge/structured/curriculum-overview.zh.md`
- tests: `backend/LightRAG/tests/test_curriculum_overview_builder.py`

## Task 2: LessonEvidence
Status: done.

Add exact page/block evidence lookup before semantic retrieval.

Acceptance:
- known `page_uid` / `block_uid` uses exact metadata first
- same-page and same-unit support are scoped
- P31 and P49 evidence comes from actual content
- no cross-grade or cross-unit leakage

Implemented:
- lookup/models: `backend/LightRAG/lightrag/orchestrator/lesson_evidence.py`
- runtime wiring: `LessonRuntime` passes compact `lesson_evidence` into `LessonResponder`
- tests: `backend/LightRAG/tests/test_lesson_evidence.py`
- `TB-G5S1U3-P31` uses the page-level pilot story overlay when the runtime catalog is loaded from the general manifest
- `TB-G6S2Recycle2-P49` exact evidence stays on the party-list / phonics page and same-unit support is bounded to `G6 S2 Recycle2`

## Task 3: LessonBriefBuilder
Status: done.

Build a compact private brief for the active page/block.

Acceptance:
- brief includes teaching focus, materials, answer scope, support vocabulary, likely mistakes, and progression
- brief is preparation only, not teacher wording
- live prompt receives only the compact brief slice needed for one turn

Implemented:
- builder: `backend/LightRAG/lightrag/orchestrator/lesson_brief_builder.py`
- prompt model: `backend/LightRAG/lightrag/pedagogy/lesson_brief.py`
- runtime wiring: `LessonRuntime` builds the brief from `LessonEvidence` before calling `LessonResponder`
- tests: `backend/LightRAG/tests/test_lesson_brief_builder.py`
- `TB-G5S1U3-P31` brief uses the story overlay content as teacher preparation material
- `TB-G6S2Recycle2-P49-D4` brief turns the task instruction into a concrete answer scope, rejects task echo, and pulls party-list vocabulary from same-page support

## Task 4: TeachingMovePlanner
Status: done.

Select reusable teaching moves from learner signal plus brief.

Acceptance:
- handles refusal, task echo, incomplete answer, small error, help request, knowledge question, off-topic turn, and good answer
- outputs detected signal, move, rationale, evidence fields used, and expected next learner action
- does not create page-specific templates

Implemented:
- model: `backend/LightRAG/lightrag/pedagogy/teaching_move.py`
- planner: `backend/LightRAG/lightrag/orchestrator/teaching_move_planner.py`
- runtime wiring: `LessonRuntime` builds `teaching_move` from `LessonBrief` before calling `LessonResponder`
- prompt contract: `LessonResponder` receives `teaching_move` as private move selection, not copyable wording
- tests: `backend/LightRAG/tests/test_teaching_move_planner.py`
- required learner signals are covered as reusable moves: refusal, task echo, incomplete answer, small error, help request, knowledge question, off-topic turn, and good answer

## Task 5: Natural LLM Response
Status: done.

Feed `LessonBrief + teaching_move + memory + teacher_soul` into `LessonResponder`.

Acceptance:
- answer is natural and teacher-like
- no fixed catchphrase requirement
- no curriculum metadata leakage
- persona and memory shape tone only, not facts or correctness

Implemented:
- `LessonResponder` prompt now carries a `natural_response_contract` for one fresh child-facing teacher reply
- `LessonResponder` receives `LessonBrief`, `teaching_move`, learner memory, persona context, and system-level Teacher Soul together
- Teacher Soul catchphrases are explicitly optional flavor, not required sign-offs
- responder normalization rejects internal field/metadata leakage across all turns, including `lesson_brief`, `teaching_move`, `lesson_evidence`, private rationale fields, source refs, UIDs, persona, and memory internals
- persona and memory boundaries are repeated in prompt contract and guarded by fallback when a live response tries to override target answers or lesson facts
- tests extend runtime/responder coverage for natural response contract, private-field leakage, catchphrase optionality, and memory/persona boundary

## Task 6: Quality Evals
Status: done.

Update evals around the new pipeline.

Acceptance:
- tests check source grounding, brief quality, move rationale, state progression, naturalness, persona boundary, and memory boundary
- P49 and P31 are sample eval pages, not templates
- route smoke still passes `/lesson/turn` and `/lesson/turn/stream`

Implemented:
- `backend/LightRAG/lightrag/orchestrator/lesson_dialogue_quality_eval.py` now captures the real `LessonResponder` prompt while returning the deterministic safety fallback, so offline evals inspect the actual `lesson_evidence`, `lesson_brief`, `teaching_move`, persona/memory boundary, and natural response contract seen by the responder
- the dialogue quality report now scores retrieval, source grounding, lesson brief, teaching move, state progression, prompt contract, response quality, persona, and memory as separate strict-pass dimensions
- `app/knowledge/evals/lesson-dialogue-quality-gold.json` now includes 12 deterministic samples, including `TB-G5S1U3-P31` story-overlay grounding and the `TB-G6S2Recycle2-P49` task/refusal/error/redirect/advance cases
- `backend/LightRAG/tests/test_lesson_dialogue_quality_eval.py` locks the expanded metrics plus P31/P49 sample behavior
- route smoke was re-run through `scripts/smoke_lesson_turn.py`, covering `/lesson/turn` and P49 `/lesson/turn/stream`

## Task 7: AIRI Visible Closure
After backend turn intent is reliable, verify AIRI presentation matches the turn.

Acceptance:
- listening, learner speaking, thinking, teacher speaking, correction, encouragement, and interruption states are visible
- voice pacing, mouth intensity, expression, motion, and interruption policy match backend intent
- Playwright screenshots show no overlap, layout break, or theme mixing after UI changes

Status: done

Implemented:
- `frontend/airi/packages/stage-layouts/src/components/Widgets/LessonSidebar.vue` now renders a visible AIRI closure strip with classroom state, teaching stance, speech pacing, mouth intensity, motion, expression, and interruption policy
- `frontend/airi/apps/stage-web/src/pages/lesson/index.browser.test.ts` locks listening, learner speaking, thinking, teacher speaking, correction, encouragement, interruption, and performance-intent visibility through the lesson AIRI runtime store
- `frontend/airi/packages/ui/src/components/form/select-tab/select-tab.vue` and `frontend/airi/packages/stage-layouts/src/components/Widgets/LessonPanel.vue` keep lesson selector tabs from forcing clipped mobile/desktop controls during the visual pass
- final screenshots were captured for desktop and mobile after the visible closure changes
