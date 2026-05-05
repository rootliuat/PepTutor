# RAGFlow Parser Config Notes

Date: 2026-05-05

Purpose: define a conservative parser/chunking setup for using RAGFlow as offline curriculum evidence. This does not affect PepTutor live runtime.

## Recommended Dataset

```text
dataset name: peptutor-curriculum-evidence
parser mode: naive / text-oriented
chunk size target: 700-1000 tokens or equivalent text length
overlap: low to moderate
auto keyword/question generation: optional, evidence only
```

The goal is not to generate final curriculum data. The goal is to preserve enough textbook/document context for human review.

## Source Types

Preferred:

- structured audit summaries from `docs/`
- curriculum triage documents
- selected raw textbook markdown/text files
- chapter or page outlines if produced later

Avoid:

- generated smoke JSON
- large raw graph JSON artifacts
- screenshots unless explicitly reviewed
- pytest logs
- token audit dumps

## Chunk Metadata To Preserve

When possible, preserve:

- source document name
- RAGFlow document id
- RAGFlow chunk id
- page-like text such as `TB-G6S1U1-P4`
- block-like text such as `TB-G6S1U1-P4-D2`
- book/unit hints such as `G6S1` and `U1`

## Mapping Confidence

PepTutor import maps chunks to:

- `exact`: block UID was detected
- `page_only`: page UID was detected
- `book_unit_only`: only book/unit hints were detected
- `unknown`: no stable curriculum identifier was detected

Unknown chunks are still useful as supporting evidence, but they must not drive source mutation without human review.

## Boundary

RAGFlow parser output is not canonical. It can suggest where to look, but `app/knowledge/structured` remains the source of truth for classroom behavior.
