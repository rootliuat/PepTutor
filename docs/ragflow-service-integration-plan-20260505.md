# RAGFlow Service Integration Plan

Date: 2026-05-05

Scope: offline curriculum evidence only.

RAGFlow is not part of the live PepTutor lesson runtime in this integration. It is a supporting parser/chunk/retrieval evidence source for curriculum graph audit, answer-scope review, phonics review, and future human-approved data tightening.

## Canonical Source Boundary

```text
app/knowledge/structured remains canonical.
RAGFlow output is supporting evidence only.
TeachingMove remains the classroom control layer.
```

RAGFlow evidence must not override:

- lesson route
- page/block progression
- TeachingMove action contract
- redirect policy
- live classroom prompt
- P13 answer-scope data
- persona behavior

## Configuration

Environment fields:

```text
PEPTUTOR_RAGFLOW_ENABLED=0
RAGFLOW_BASE_URL=http://127.0.0.1:9380
RAGFLOW_API_KEY=
RAGFLOW_DATASET_ID=
RAGFLOW_TIMEOUT_SECONDS=10
```

Default is disabled. If disabled or unavailable, RAGFlow scripts should warn and exit gracefully rather than failing project startup.

## Scripts

| Script | Role |
|---|---|
| `scripts/check_ragflow_service.py` | Optional service and dataset health check. |
| `scripts/ragflow_upload_curriculum_sources.py` | Dry-run or committed upload plan for selected docs/raw text. |
| `scripts/ragflow_export_chunks.py` | Export RAGFlow chunks to a local generated artifact. |
| `scripts/clean_ragflow_chunks.py` | Drop empty, duplicate, and short noise chunks. |
| `scripts/import_ragflow_chunks.py` | Convert RAGFlow chunks to PepTutor evidence chunk schema. |
| `scripts/build_curriculum_evidence_index.py` | Merge structured/audit/candidate/RAGFlow evidence into a review index. |

## Upload Policy

Allowed upload candidates:

- `docs/curriculum-graph-audit-summary-20260505.md`
- `docs/curriculum-graph-findings-triage-20260505.md`
- `docs/curriculum-data-tightening-candidates-20260505.md`
- selected `app/knowledge/raw` markdown/text files

Excluded:

- `temp/lesson-smoke-artifacts/*.json`
- smoke artifacts
- large audit artifacts with raw payloads
- pytest logs
- credentials

## RAGFlow API Surface

The offline client wraps these operations:

- `health_check`
- `list_datasets`
- `list_documents`
- `upload_document`
- `export_chunks`
- `retrieve`

The implementation uses timeout support, graceful failure, and fake transport support for tests. Tests do not require a real RAGFlow server or network.

## Delivery Boundary

This goal does not introduce:

- GRPO
- model training
- LLM extraction
- live runtime RAGFlow retrieval
- RAGFlow requirement for startup

RAGFlow is a future-facing evidence tool for human review and source-data hardening.
