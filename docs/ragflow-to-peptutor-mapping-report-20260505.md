# RAGFlow To PepTutor Mapping Report

Date: 2026-05-05

Scope: mapping design/report for the offline RAGFlow evidence adapter. No live RAGFlow export is required for this repository state, and no RAGFlow evidence is tracked in Git.

## Current Mapping Summary

No real RAGFlow chunk export is committed in this goal. The scripts and tests validate the mapping behavior using fake chunks.

| Metric | Count |
|---|---:|
| mapped_exact_count | 0 |
| mapped_page_only_count | 0 |
| unknown_count | 0 |

## Six Anchor Mapping Summary

| Page | Current tracked RAGFlow evidence chunks |
|---|---:|
| `TB-G5S1U3-P22` | 0 |
| `TB-G6S1U1-P4` | 0 |
| `TB-G6S2U1-P4` | 0 |
| `TB-G5S1U3-P31` | 0 |
| `TB-G5S2U1-P6` | 0 |
| `TB-G6S2U2-P13` | 0 |

## Adapter Behavior

`scripts/import_ragflow_chunks.py` maps RAGFlow chunks into:

```text
chunk_id
source=ragflow
book_id
unit_id
page_uid
block_uid
chunk_type
text
keywords
source_file
ragflow_document_id
ragflow_chunk_id
mapping_confidence
```

Mapping confidence values:

- `exact`: block UID detected
- `page_only`: page UID detected
- `book_unit_only`: book/unit hint detected
- `unknown`: no stable curriculum identifier detected

## Known Limitations

- RAGFlow chunk text may not include PepTutor page/block UIDs unless uploaded source material contains them.
- OCR or PDF parser output can split page references away from the relevant text.
- A chunk with `unknown` confidence is supporting evidence only; it must not mutate structured curriculum data.
- RAGFlow evidence does not override canonical structured curriculum data.

## Next Step

After May 8, run a real disabled-by-default RAGFlow evidence pass only if a RAGFlow service is available:

```bash
PEPTUTOR_RAGFLOW_ENABLED=1 \
RAGFLOW_BASE_URL=http://127.0.0.1:9380 \
RAGFLOW_API_KEY=... \
RAGFLOW_DATASET_ID=... \
python scripts/check_ragflow_service.py
```

Then use the export, clean, import, and evidence-index scripts to create local generated artifacts for human review.
