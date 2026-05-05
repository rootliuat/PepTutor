# Curriculum Evidence Index Schema v1

The curriculum evidence index merges canonical structured curriculum graph nodes with supporting evidence from audits, candidate plans, raw docs, and optional RAGFlow chunks.

## Boundary

```text
canonical_source = app/knowledge/structured
ragflow_overrides_structured = false
```

RAGFlow evidence can support human review. It must not override structured curriculum data or live classroom control.

## Top-level Shape

```json
{
  "schema_version": "curriculum_evidence_index_v1",
  "generated_at": "2026-05-05T00:00:00",
  "canonical_source": "app/knowledge/structured",
  "ragflow_overrides_structured": false,
  "summary": {
    "entry_count": 0,
    "entry_counts_by_source": {}
  },
  "entries": []
}
```

## Entry Shape

```json
{
  "evidence_id": "structured:Block-TB-G6S1U1-P4-D2",
  "source": "structured",
  "source_ref": "Block:TB-G6S1U1-P4-D2",
  "page_uid": "TB-G6S1U1-P4",
  "block_uid": "TB-G6S1U1-P4-D2",
  "evidence_type": "Block",
  "text": "Where is the museum shop?",
  "canonical_priority": "canonical"
}
```

## Source Labels

| Source | Meaning |
|---|---|
| `structured` | Canonical structured curriculum graph evidence. |
| `ragflow` | External RAGFlow parser/chunk evidence. Supporting only. |
| `audit` | Curriculum graph audit findings. |
| `candidate` | Review-only data-tightening candidates. |
| `raw` | Local summary/raw documentation snippets. |

## Canonical Priority

| Value | Meaning |
|---|---|
| `canonical` | Source of truth for classroom behavior. |
| `supporting` | Review evidence only. |
| `review_only` | Candidate plan, not a data patch. |
