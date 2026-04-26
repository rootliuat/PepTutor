# Pilot Implementation Log

## Purpose
This document records what was implemented for the first teaching pilot, how it was implemented, how it was validated, and what remains next. It exists so the work does not depend on chat history.

## Pilot Scope
- Textbook scope: `五年级上册 Unit 3, p24-p31`
- Priority scenes:
  - dialogue teaching
  - correction
  - interactive follow-up
- Teaching style:
  - Chinese-led explanation
  - English practice
  - lively teacher persona

## Data Assets
- Pilot plan: [pilot-unit3-slicing-plan.md](/F:/TestCode/github_project/PepTutor/docs/pilot-unit3-slicing-plan.md)
- Teacher persona: [soul.md](/F:/TestCode/github_project/PepTutor/soul.md)
- Structured pilot data:
  - [g5s1u3-p24-p25-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p24-p25-pilot.json)
  - [g5s1u3-p26-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p26-pilot.json)
  - [g5s1u3-p27-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p27-pilot.json)
  - [g5s1u3-p28-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p28-pilot.json)
  - [g5s1u3-p29-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p29-pilot.json)
  - [g5s1u3-p30-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p30-pilot.json)
  - [g5s1u3-p31-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p31-pilot.json)
  - [g5s1u3-pilot-manifest.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-pilot-manifest.json)

## Step 1: Freeze The Pilot Data Model
Goal:
- lock the first set of page-level and block-level teaching structures

What was done:
- finalized the pilot data model around:
  - `PageLesson`
  - `TeachingBlock`
  - `KnowledgeAtom`
  - `LearningTarget`
- aligned docs with:
  - `page_type`
  - page-entry probe
  - `mastered | shaky | not_mastered`
  - `assumed_prior_knowledge`
  - `repair_mode`

Where it lives:
- [project-design-overview.md](/F:/TestCode/github_project/PepTutor/docs/project-design-overview.md)
- [teaching-agent-architecture.md](/F:/TestCode/github_project/PepTutor/docs/teaching-agent-architecture.md)
- [turn-routing-and-pedagogy.md](/F:/TestCode/github_project/PepTutor/docs/turn-routing-and-pedagogy.md)
- [data-schema.md](/F:/TestCode/github_project/PepTutor/docs/data-schema.md)

Validation:
- doc review
- schema consistency check across pilot data files

## Step 2: Build The First Page Entry Loop
Goal:
- support requests such as `学习五年级上册第31页`, `五年级上31页`, and `五年级上第三单元`

What was done:
- created a page/unit request parser
- loaded pilot page metadata from the Unit 3 manifest
- returned:
  - page overview
  - 1 to 2 short probe questions
  - page or unit target info

Where it lives:
- [page_entry.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/page_entry.py)
- [test_pilot_page_entry.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_page_entry.py)

Validation:
- page request test
- unit request test
- probe output test

## Step 3: Add Page-Type Teaching Flow
Goal:
- make teaching follow `page_type` instead of generic chat

What was done:
- created a page flow planner
- mapped page types to page-level teaching actions
- planner output includes:
  - page overview
  - readiness probe
  - block-level actions
  - page wrap-up

Where it lives:
- [page_flow.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/page_flow.py)
- [test_pilot_page_flow.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_page_flow.py)

Validation:
- flow generation per `page_type`
- correct block sequencing
- repair modes preserved in block steps

## Step 4: Add Local Answer Evaluation And Repair Routing
Goal:
- evaluate the learner answer locally before widening retrieval

What was done:
- created a local answer evaluator for the current `TeachingBlock`
- evaluator returns:
  - `verdict`
  - `mastery_level`
  - `recommended_action`
- added handling for:
  - correct answer
  - partial answer
  - wrong answer
  - unclear answer
  - learner repair requests such as "拆开练" or "先练这个词"

Where it lives:
- [answer_evaluation.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/answer_evaluation.py)
- [test_pilot_answer_evaluation.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_answer_evaluation.py)

Validation:
- happy path answer
- partial answer path
- correction path
- repair request path
- ASR clarify path

## Step 5: Add Assumed Prior Knowledge Verification
Goal:
- support "probably learned before" as a hypothesis, not a fact

What was done:
- added `assumed_prior_knowledge` to pilot data
- created prior-knowledge loading and verification logic
- linked probe/evaluation results to:
  - `confirmed`
  - `rejected`
  - `unverified`

Where it lives:
- [prior_knowledge.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/prior_knowledge.py)
- [test_pilot_prior_knowledge.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_prior_knowledge.py)

Validation:
- page hypothesis load test
- verification state transition tests

## Step 6: Tighten Retrieval Scope To `block -> page -> unit`
Goal:
- stop the system from jumping out of the current page too early

What was done:
- built a retrieval-scope selector
- retrieval now widens only when the earlier layer is insufficient:
  - current block
  - current page
  - current unit

Where it lives:
- [retrieval_scope.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/retrieval_scope.py)
- [test_pilot_retrieval_scope.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_retrieval_scope.py)

Validation:
- hit in current block
- widen to page
- widen to unit
- empty result path

## Step 7: Build Memory Writeback Payloads
Goal:
- capture lesson evidence without yet fully wiring to live memory storage

What was done:
- created writeback package builders for:
  - `LessonTraceRecord`
  - `TeachingUnitRecord`
  - `SimpleMemEntryPayload`
- knowledge-point mastery and mistake evidence are turned into stable writeback payloads
- strategy memory is also captured when the learner asks for task shrinking

Where it lives:
- [memory_writeback.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/memory_writeback.py)
- [test_pilot_memory_writeback.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_memory_writeback.py)

Validation:
- mastery payload generation
- mistake payload generation
- strategy payload generation

## Step 8: Build Regression Coverage For End-To-End Pilot Flows
Goal:
- validate the pilot as a teaching chain instead of isolated functions

What was done:
- added regression tests that cover:
  - dialogue progression
  - interaction with task shrinking
  - correction flow

Where it lives:
- [test_pilot_regression_flows.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_regression_flows.py)

Validation:
- story page happy path
- unit entry split-practice path
- vocabulary correction path

## Step 9: Connect The Pilot Chain To LessonState And LangGraph
Goal:
- move from separate utilities to a real lesson orchestration path

What was done:
- created a minimal lesson graph
- added runtime `LessonState`
- connected:
  - page entry
  - page flow
  - answer evaluation
  - prior knowledge verification
  - retrieval scope decision
  - memory writeback
- switched from fallback mode to real `LangGraph StateGraph`

Where it lives:
- [lesson_graph.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/orchestrator/lesson_graph.py)
- [test_pilot_lesson_graph.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_lesson_graph.py)

Validation:
- page-entry-only state update
- happy path graph run
- repair request graph run
- correction graph run

## Step 10: Expose The Pilot Chain Through A Real API Route
Goal:
- make the pilot lesson graph callable through the existing LightRAG FastAPI service

What was done:
- added a dedicated lesson route:
  - `POST /lesson/pilot/invoke`
- wrapped the current pilot `lesson_graph` in an API request/response model
- included the route in the main FastAPI app without changing existing `/query` semantics
- kept authentication behavior aligned with the rest of the API through `X-API-Key`

Where it lives:
- [lesson_routes.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/api/routers/lesson_routes.py)
- [lightrag_server.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/api/lightrag_server.py)
- [test_pilot_lesson_api.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_lesson_api.py)

Validation:
- page-entry API call
- interaction-flow API call
- API key protection test

## Environment Isolation
What was done:
- created a project-local Python environment for LightRAG:
  - [backend/LightRAG/.venv](/F:/TestCode/github_project/PepTutor/backend/LightRAG/.venv)
- updated repo instructions to prefer local virtual environments over global Python

Where it is documented:
- [AGENTS.md](/F:/TestCode/github_project/PepTutor/AGENTS.md)
- [backend/LightRAG/AGENTS.md](/F:/TestCode/github_project/PepTutor/backend/LightRAG/AGENTS.md)

Validation:
- `.venv` install completed
- `pip check` passed inside `.venv`

## Current Validation Snapshot
Commands:
```powershell
cd F:\TestCode\github_project\PepTutor\backend\LightRAG
.\.venv\Scripts\python -m pip check
.\.venv\Scripts\python -m pytest tests\test_pilot_answer_evaluation.py tests\test_pilot_prior_knowledge.py tests\test_pilot_page_entry.py tests\test_pilot_page_flow.py tests\test_pilot_retrieval_scope.py tests\test_pilot_memory_writeback.py tests\test_pilot_regression_flows.py tests\test_pilot_lesson_graph.py
.\.venv\Scripts\python -m ruff check --no-cache lightrag\__init__.py lightrag\pedagogy lightrag\orchestrator tests\test_pilot_answer_evaluation.py tests\test_pilot_prior_knowledge.py tests\test_pilot_page_entry.py tests\test_pilot_page_flow.py tests\test_pilot_retrieval_scope.py tests\test_pilot_memory_writeback.py tests\test_pilot_regression_flows.py tests\test_pilot_lesson_graph.py
```

Results:
- `pip check`: passed
- `pytest`: `39 passed`
- `ruff check`: passed

## Step 11: Wire Local Qdrant Into LightRAG
Goal:
- move textbook vector storage from pilot-only in-memory/static behavior toward a real local vector store

What was done:
- added `QDRANT_PATH` support so `QdrantVectorDBStorage` can run in embedded local mode without `QDRANT_URL`
- expanded environment variables in `QDRANT_PATH`, so values like `%LOCALAPPDATA%\PepTutor\qdrant_local` work
- fixed embedded-Qdrant startup by reusing a shared `QdrantClient` for the same local storage path across `entities`, `relationships`, and `chunks`
- configured local LightRAG env to use embedded Qdrant on the user-local system drive instead of the repo drive

Where it lives:
- [qdrant_impl.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/kg/qdrant_impl.py)
- [utils.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/utils.py)
- [backend/LightRAG/.env](/F:/TestCode/github_project/PepTutor/backend/LightRAG/.env)
- [test_qdrant_env_validation.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_qdrant_env_validation.py)
- [test_qdrant_local_path_config.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_qdrant_local_path_config.py)
- [test_qdrant_migration.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_qdrant_migration.py)
- [test_qdrant_upsert_batching.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_qdrant_upsert_batching.py)

Validation:
- `pytest tests\test_qdrant_env_validation.py tests\test_qdrant_local_path_config.py tests\test_qdrant_migration.py tests\test_qdrant_upsert_batching.py` -> `18 passed`
- `ruff check --no-cache lightrag\kg\qdrant_impl.py tests\test_qdrant_local_path_config.py tests\test_qdrant_migration.py` -> passed
- started LightRAG with `QdrantVectorDBStorage` on `http://127.0.0.1:9624`
- `GET /health` returned healthy
- `POST /lesson/pilot/invoke` returned success while running under the Qdrant-backed startup

## Step 12: Ingest Pilot Teaching Blocks Into Qdrant And Switch Retrieval
Goal:
- stop relying on static keyword-only pilot retrieval and move the pilot lesson graph onto a real vector-backed block index

What was done:
- added a pilot Qdrant retrieval path for `TeachingBlock` data
- ingested all `g5s1u3` pilot blocks into a dedicated `teaching_blocks` Qdrant collection
- used a deterministic local hash embedding for the pilot index so the retrieval path can run without an external embedding API
- kept the lesson graph/test defaults on static retrieval, but switched the real FastAPI server route to request the Qdrant-backed retrieval backend
- preserved the same `block -> page -> unit` widening policy after vector recall

Where it lives:
- [retrieval_scope.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/retrieval_scope.py)
- [lesson_graph.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/orchestrator/lesson_graph.py)
- [lesson_routes.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/api/routers/lesson_routes.py)
- [lightrag_server.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/api/lightrag_server.py)
- [test_pilot_qdrant_retrieval.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_qdrant_retrieval.py)
- [test_pilot_lesson_api.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_lesson_api.py)

Validation:
- `pytest tests\test_pilot_retrieval_scope.py tests\test_pilot_qdrant_retrieval.py tests\test_pilot_lesson_api.py tests\test_pilot_lesson_graph.py tests\test_pilot_regression_flows.py` -> `18 passed`
- `ruff check --no-cache ...` on modified retrieval/orchestrator/api files -> passed
- started LightRAG on `http://127.0.0.1:9625` with a fresh embedded Qdrant path
- `GET /health` returned healthy
- `POST /lesson/pilot/invoke` returned a retrieval payload with `backend = qdrant`
- runtime retrieval for learner text `sweet` widened to the unit and returned `TB-G5S1U3-P28-D1`, `TB-G5S1U3-P28-D3`, and `TB-G5S1U3-P28-D2`

## Current Status
Completed:
- pilot data slicing for Unit 3
- page-entry diagnosis
- page-type teaching flow
- answer evaluation and repair routing
- assumed prior knowledge verification
- retrieval scope control
- memory writeback payload generation
- regression coverage
- LangGraph/LessonState orchestration
- real API route for the pilot lesson graph
- local Python environment isolation for `backend/LightRAG`
- local embedded Qdrant integration and runtime validation
- pilot textbook block ingest into Qdrant
- Qdrant-backed lesson retrieval in the real API server path
- `memory_writeback` to `SimpleMem-Cross` contract and client wiring
- real local `SimpleMem` HTTP service with deterministic local embedding mode
- real `LightRAG -> SimpleMem` end-to-end HTTP lesson writeback validation

Not yet completed:
- AIRI frontend integration
- scaling this flow beyond the pilot unit
- production deployment recipe for Qdrant on the target server
- replacing the pilot hash embedding with a real embedding provider

## Step 13: Finish The Live `LightRAG -> SimpleMem` HTTP Loop
Goal:
- move from contract tests to a real local cross-service writeback loop

What was done:
- created a local `backend/SimpleMem/.venv`
- added env-driven runtime config via:
  - [config.py](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/config.py)
  - [backend/SimpleMem/.env](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/.env)
- added deterministic local embedding mode for SimpleMem so the service can run without downloading a sentence-transformer
- made `cross` ASGI startup load `.env` before heavy module initialization
- changed SimpleMem SQLite and LanceDB paths to support environment-variable expansion and moved runtime storage to `%TEMP%\PepTutor\simplemem_cross`
- fixed `cross.__init__` to lazy-load heavy modules so `uvicorn cross.asgi:app` no longer bypasses `.env`
- tightened the LightRAG SimpleMem HTTP client to use `trust_env=False`
- validated:
  - live SimpleMem `GET /cross/health`
  - live SimpleMem `POST /cross/lesson-writeback`
  - live LightRAG `POST /lesson/pilot/invoke` with `memory_writeback.simplemem_persistence.status = stored`

Where it lives:
- [config.py](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/config.py)
- [cross/asgi.py](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/cross/asgi.py)
- [cross/__init__.py](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/cross/__init__.py)
- [cross/storage_sqlite.py](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/cross/storage_sqlite.py)
- [cross/storage_lancedb.py](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/cross/storage_lancedb.py)
- [cross/tests/test_runtime_embedding.py](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/cross/tests/test_runtime_embedding.py)
- [cross/tests/test_storage_path_config.py](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/cross/tests/test_storage_path_config.py)
- [cross/tests/test_asgi_env_bootstrap.py](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/cross/tests/test_asgi_env_bootstrap.py)
- [simplemem_client.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/simplemem_client.py)
- [test_simplemem_cross_client.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_simplemem_cross_client.py)

Validation:
- `cd backend/SimpleMem && .\.venv\Scripts\python -m pytest -p no:cacheprovider cross\tests\test_lesson_writeback.py cross\tests\test_runtime_embedding.py cross\tests\test_storage_path_config.py cross\tests\test_asgi_env_bootstrap.py` -> `6 passed`
- `cd backend/SimpleMem && .\.venv\Scripts\python -m ruff check --no-cache cross\__init__.py cross\api_http.py cross\asgi.py cross\storage_sqlite.py cross\storage_lancedb.py utils\embedding.py utils\__init__.py config.py cross\tests\test_runtime_embedding.py cross\tests\test_storage_path_config.py cross\tests\test_asgi_env_bootstrap.py` -> passed
- `cd backend/LightRAG && .\.venv\Scripts\python -m pytest tests\test_simplemem_cross_client.py tests\test_pilot_lesson_graph.py -p no:cacheprovider` -> `8 passed`
- `cd backend/LightRAG && .\.venv\Scripts\python -m ruff check --no-cache lightrag\pedagogy\simplemem_client.py tests\test_simplemem_cross_client.py tests\test_pilot_lesson_graph.py` -> passed
- live SimpleMem service:
  - `http://127.0.0.1:8321/cross/health` -> healthy
  - `POST /cross/lesson-writeback` -> `stored`
- live LightRAG service:
  - `http://127.0.0.1:9625/health` -> healthy
  - `POST /lesson/pilot/invoke` -> `memory_writeback.simplemem_persistence.status = stored`

## Recommended Next Steps
1. Start `backend/SimpleMem` with its own local environment and validate `POST /cross/lesson-writeback` from `LightRAG`.
2. Replace the pilot hash embedding with a real embedding provider.
3. Add another pilot unit before scaling to full-grade ingestion.
4. Prepare a server-side Qdrant deployment recipe for cloud rollout.

## Step 13: Connect `memory_writeback` To `backend/SimpleMem`
Goal:
- stop leaving lesson memory as an internal payload and provide a real persistence handoff into `SimpleMem-Cross`

What was done:
- added a dedicated `LessonWritebackStore` in `backend/SimpleMem` that:
  - creates or reuses a cross-session record in SQLite
  - stores the lesson turn as a session event
  - converts teaching-unit writeback into observations
  - converts `SimpleMemEntryPayload` into `CrossMemoryEntry` records
  - writes traceability links from stored vectors back to teaching observations
  - stores a lightweight session summary
- added a new `SimpleMem-Cross` HTTP endpoint:
  - `POST /cross/lesson-writeback`
- added a `LightRAG` HTTP client for this endpoint
- wired the lesson graph memory node so it now returns:
  - the existing writeback package
  - `memory_writeback.simplemem_persistence`
- kept the integration non-blocking:
  - if `SIMPLEMEM_CROSS_URL` is not configured, lesson flow continues and marks persistence as `disabled`
  - if the HTTP call fails, lesson flow continues and marks persistence as `error`

Where it lives:
- [lesson_writeback.py](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/cross/lesson_writeback.py)
- [api_http.py](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/cross/api_http.py)
- [__init__.py](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/cross/__init__.py)
- [test_lesson_writeback.py](/F:/TestCode/github_project/PepTutor/backend/SimpleMem/cross/tests/test_lesson_writeback.py)
- [simplemem_client.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/simplemem_client.py)
- [lesson_graph.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/orchestrator/lesson_graph.py)
- [test_simplemem_cross_client.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_simplemem_cross_client.py)
- [test_pilot_lesson_graph.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_lesson_graph.py)

Validation:
- `cd backend/LightRAG && .\.venv\Scripts\python -m pytest tests\test_pilot_memory_writeback.py tests\test_pilot_regression_flows.py tests\test_simplemem_cross_client.py tests\test_pilot_lesson_graph.py` -> `13 passed`
- `cd backend/LightRAG && .\.venv\Scripts\python -m pytest tests\test_simplemem_cross_client.py tests\test_pilot_lesson_graph.py tests\test_pilot_lesson_api.py` -> `11 passed`
- `cd backend/LightRAG && .\.venv\Scripts\python -m ruff check --no-cache ...` on modified LightRAG files -> passed
- `cd backend/SimpleMem && python -m pytest -p no:cacheprovider cross\tests\test_lesson_writeback.py` -> `2 passed`
- `cd backend/SimpleMem && python -m ruff check --no-cache cross\lesson_writeback.py cross\api_http.py cross\__init__.py cross\tests\test_lesson_writeback.py` -> passed

Notes:
- this step validates the code contract and persistence behavior with a fake vector store in tests
- it does not yet prove a full live HTTP round-trip against a running `backend/SimpleMem` service with LanceDB installed
- to enable runtime persistence from `LightRAG`, set `SIMPLEMEM_CROSS_URL`, for example:
  - `http://127.0.0.1:8000`

## Step 14: Add Minimal TeacherAgent Reasoning And Harden Lesson-Core Tests
Goal:
- move from “workflow plus final reply generation” toward a more teacher-like path where the system reasons before speaking
- raise lesson-core testing quality above the `90` threshold

What was done:
- added a clean teacher reasoning service:
  - [teacher_reasoning_service.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/teacher_reasoning_service.py)
- wired the lesson graph to use teacher reasoning before teacher response generation
- rebuilt the reasoning tests in UTF-8 and removed reliance on garbled string assertions
- rebuilt teacher response prompt tests so they now assert:
  - exact page-request acknowledgement contract
  - Chinese opening overview contract
  - key-pattern mention contract
  - one-small-next-move contract
- documented test samples and score in:
  - [lesson-testing-status.md](/F:/TestCode/github_project/PepTutor/docs/lesson-testing-status.md)
  - [test-data-samples.md](/F:/TestCode/github_project/PepTutor/docs/test-data-samples.md)

Where it lives:
- [teacher_reasoning_service.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/teacher_reasoning_service.py)
- [lesson_graph.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/orchestrator/lesson_graph.py)
- [test_pilot_teacher_reasoning.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_reasoning.py)
- [test_pilot_teacher_response.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_response.py)
- [test_pilot_teacher_response_opening_prompt.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_response_opening_prompt.py)

Validation:
- `pytest tests\test_pilot_teacher_reasoning.py tests\test_pilot_teacher_response.py tests\test_pilot_teacher_response_opening_prompt.py tests\test_pilot_lesson_graph.py tests\test_pilot_lesson_api.py` -> `19 passed`
- `ruff check --no-cache ...` on lesson-core files -> passed

Current testing note:
- lesson-core score is currently assessed at `91/100`
- this score reflects stable regression quality, not just raw pass count
- real LLM calls are still validated separately as smoke checks, not as default pytest cases

## Step 15: Tighten Opening Fallback And Clean Page-31 Intro
Goal:
- make the non-LLM teacher path behave like a real classroom opening instead of a generic fallback
- ensure page 31 starts with exact page acknowledgement, Chinese page intro, key patterns, and one tiny probe

What was done:
- tightened the fallback reply builder in:
  - [teacher_response.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/teacher_response.py)
- added explicit fallback helpers for:
  - exact user-request acknowledgement
  - key-pattern insertion when the intro does not already contain it
  - sentence-drill shrinking to a target expression instead of repeating generic prompts
- refined the page-31 sample intro in:
  - [g5s1u3-p31-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p31-pilot.json)
- expanded teacher response tests so fallback behavior is now asserted, not just prompt construction

Where it lives:
- [teacher_response.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/teacher_response.py)
- [g5s1u3-p31-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p31-pilot.json)
- [test_pilot_teacher_response.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_response.py)

Validation:
- `pytest tests\test_pilot_teacher_response.py tests\test_pilot_teacher_response_opening_prompt.py tests\test_pilot_teacher_reasoning.py tests\test_pilot_lesson_graph.py tests\test_pilot_lesson_api.py` -> `21 passed`
- `pytest tests\test_pilot_teacher_response.py -q` -> `7 passed`
- `ruff check --no-cache lightrag\pedagogy\teacher_response.py tests\test_pilot_teacher_response.py tests\test_pilot_teacher_response_opening_prompt.py` -> passed

Runtime fallback sample:
- `好，我们来学五年级上册第31页。`
- `这一页通过 Zoom 和 Zip 的故事学习做沙拉和表达想吃什么。`
- `这一页先抓两个重点句型：“I'm hungry.”、“Let's make a salad.”。`
- `先来一个很短的小问题：What would Zoom like to eat?`

## Step 16: Add Response Guardrails And Remove Pydantic V2 Warnings
Goal:
- stop real LLM openings from drifting to wrong labels like `第五册第31页`
- align split-practice behavior across evaluation, repair mode, and teacher reasoning
- remove noisy Pydantic v2 deprecation warnings from lesson API tests

What was done:
- tightened opening-turn guardrails in:
  - [teacher_response.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/teacher_response.py)
  - exact page acknowledgement is now code-enforced for opening turns, even if the LLM drifts
- adjusted split-practice evaluation in:
  - [answer_evaluation.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/answer_evaluation.py)
  - `story_block` and `reading_passage` now prefer `word_drill` when the learner asks to split practice
- migrated document API response models in:
  - [document_routes.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/api/routers/document_routes.py)
  - replaced legacy `class Config` usage with `ConfigDict`
- expanded regression tests for:
  - story split-practice alignment
  - opening acknowledgement rewrite when LLM says the wrong page label

Where it lives:
- [answer_evaluation.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/answer_evaluation.py)
- [teacher_response.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/teacher_response.py)
- [document_routes.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/api/routers/document_routes.py)
- [test_pilot_answer_evaluation.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_answer_evaluation.py)
- [test_pilot_teacher_response.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_response.py)
- [test_pilot_lesson_graph.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_lesson_graph.py)
- [test_pilot_lesson_api.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_lesson_api.py)

Validation:
- `pytest tests\test_pilot_answer_evaluation.py tests\test_pilot_teacher_response.py tests\test_pilot_lesson_graph.py tests\test_pilot_lesson_api.py` -> `25 passed`
- `ruff check --no-cache ...` on modified lesson/document files -> passed
- `pytest tests\test_pilot_lesson_api.py -q` -> `4 passed`
- API warning status: cleared for the lesson API regression path

Runtime lesson result:
- opening turn is now pinned to `好，我们来学五年级上册第31页。`
- story-page split practice now aligns to `word_drill` across:
  - `evaluation.recommended_action`
  - `repair_mode`
  - `teacher_reasoning.chosen_skill`

## Step 17: Strengthen Teacher Prompt And Remove Repeated Opening Drift
Goal:
- make teacher reasoning align more tightly with evaluation and chosen skill
- make the response prompt more skill-aware
- prevent non-opening turns from repeating the page-opening scaffold

What was done:
- strengthened [teacher_reasoning_service.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/teacher_reasoning_service.py):
  - added explicit skill-alignment priority rules to the reasoning prompt
  - opening turns now explicitly prefer `page_intro`
  - repair requests now explicitly prefer low-burden drill skills
- strengthened [teacher_response.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/teacher_response.py):
  - added `Chosen skill execution guidance` to the LLM prompt
  - added required opening acknowledgement and required opening pattern hints
  - opening turns now auto-insert key pattern lines if the model omits them
  - non-opening turns now strip repeated opening acknowledgement and repeated pattern lines
- added regression tests for:
  - reasoning prompt skill-alignment rules
  - opening pattern insertion when the model omits them
  - non-opening repeated-opening cleanup

Where it lives:
- [teacher_reasoning_service.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/teacher_reasoning_service.py)
- [teacher_response.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/teacher_response.py)
- [test_pilot_teacher_reasoning_prompt.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_reasoning_prompt.py)
- [test_pilot_teacher_response.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_response.py)

Validation:
- `pytest tests\test_pilot_teacher_response.py tests\test_pilot_teacher_reasoning_prompt.py tests\test_pilot_lesson_graph.py tests\test_pilot_answer_evaluation.py` -> `26 passed`
- `ruff check --no-cache ...` on modified prompt/response files -> passed

Runtime lesson result:
- turn 1 keeps the page-opening scaffold and key patterns
- turn 2 no longer repeats `好，我们来学五年级上册第31页`
- turn 3 no longer repeats the page-opening scaffold before `word_drill`
## Step 18: Add Reusable Live LLM Smoke Validation
Goal:
- stop relying on ad hoc shell snippets for real DeepSeek acceptance
- make live lesson acceptance repeatable before demo, UI regression, or release

What was done:
- added a reusable smoke script:
  - [lesson_live_llm_smoke.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/tools/lesson_live_llm_smoke.py)
- the script now drives the real lesson API through three turns:
  - opening page request
  - partial-answer correction
  - split-practice follow-up
- the script validates:
  - `teacher_reasoning.used_llm = true`
  - `response_generation.used_llm = true`
  - opening-turn page acknowledgement
  - key-pattern mention on opening
  - no opening-ack repetition on non-opening turns
  - `word_drill` alignment on split practice
- added logic-level tests for the smoke helper functions
- documented the run command and pass criteria in:
  - [live-llm-smoke.md](/F:/TestCode/github_project/PepTutor/docs/live-llm-smoke.md)

Where it lives:
- [lesson_live_llm_smoke.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/tools/lesson_live_llm_smoke.py)
- [test_lesson_live_llm_smoke.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_lesson_live_llm_smoke.py)
- [live-llm-smoke.md](/F:/TestCode/github_project/PepTutor/docs/live-llm-smoke.md)

Validation:
- `pytest tests\test_lesson_live_llm_smoke.py tests\test_pilot_teacher_reasoning.py tests\test_pilot_teacher_response.py tests\test_pilot_teacher_response_opening_prompt.py tests\test_pilot_lesson_graph.py tests\test_pilot_lesson_api.py`
- `ruff check --no-cache lightrag\tools\lesson_live_llm_smoke.py tests\test_lesson_live_llm_smoke.py lightrag\pedagogy\teacher_reasoning_service.py lightrag\pedagogy\teacher_response.py lightrag\orchestrator\lesson_graph.py`
