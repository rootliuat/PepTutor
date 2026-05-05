# Curriculum Graph Schema v1

PepTutor curriculum graph extraction is an offline, read-only audit layer. It makes textbook structure explicit so target, answer-frame, story, phonics, answer-scope, and return-anchor problems can be found as curriculum-quality risks instead of being repeatedly patched inside lesson runtime code.

This work is inspired by graph extraction plus deterministic quality-audit methodology. It does not introduce GRPO training, model fine-tuning, live lesson routing, prompt changes, RAG changes, or runtime behavior changes.

## Inputs

The graph builder reads the current structured curriculum corpus:

- `app/knowledge/structured/curriculum-map.json`
- `app/knowledge/structured/general/general-manifest.json`
- `app/knowledge/structured/general/*.json`
- `app/knowledge/structured/*pilot*.json`
- `app/knowledge/raw/*` as provenance metadata only

The builder does not mutate source curriculum files and does not call an LLM.

## Output Files

Graph output:

```text
temp/lesson-smoke-artifacts/curriculum_graph_<timestamp>.json
```

Audit output:

```text
temp/lesson-smoke-artifacts/curriculum_graph_audit_<timestamp>.json
```

## Graph JSON Shape

```json
{
  "schema_version": "curriculum_graph_v1",
  "generated_at": "2026-05-05T12:00:00",
  "source": {
    "structured_dir": "app/knowledge/structured",
    "raw_dir": "app/knowledge/raw",
    "structured_files": [],
    "raw_files": []
  },
  "metadata": {
    "book_count": 0,
    "unit_count": 0,
    "page_count": 0,
    "block_count": 0,
    "node_count": 0,
    "edge_count": 0,
    "node_type_counts": {},
    "edge_type_counts": {},
    "pages_by_book": {},
    "blocks_by_book": {},
    "anchor_pages": {
      "requested": [],
      "present": [],
      "missing": []
    },
    "methodology_note": ""
  },
  "node_types": [],
  "edge_types": [],
  "nodes": [],
  "edges": []
}
```

## Node Shape

Each node has:

```json
{
  "id": "Block:TB-G6S1U1-P4-D2",
  "type": "Block",
  "label": "TB-G6S1U1-P4-D2",
  "book_id": "G6S1",
  "unit_id": "U1",
  "page_uid": "TB-G6S1U1-P4",
  "block_uid": "TB-G6S1U1-P4-D2",
  "source_files": ["app/knowledge/structured/general/g6s1u1-general.json"],
  "properties": {}
}
```

## Node Types

| type | meaning |
| --- | --- |
| `Book` | Textbook book scope, such as `G5S1`. |
| `Unit` | Unit scope inside a book. |
| `Page` | Textbook page-level lesson entry. |
| `Block` | A teachable block inside a page. |
| `TeachingTarget` | General target from learning targets or core patterns. |
| `QuestionTarget` | A question-form target such as `Where is the museum shop?`. |
| `AnswerTarget` | A concrete answer sentence or accepted answer. |
| `AnswerFrame` | A reusable answer frame such as `It's near ...`. |
| `VocabItem` | Vocabulary item from focus vocabulary or wordlist data. |
| `PhonicsPattern` | Phonics pattern such as `cl`. |
| `PhonicsExemplar` | Exemplar word for a phonics pattern, such as `clean`. |
| `StoryQuestion` | Question target in a story/reading page. |
| `StoryCharacter` | Story character such as Zoom or Zip. |
| `RolePlayPair` | A linked question/answer or role-play pair. |
| `AnswerScope` | Allowed answer scope attached to a block. |
| `ReturnAnchor` | Return anchor used after vocab/support detours. |
| `SourceFile` | Source file provenance node. |

## Edge Shape

Each edge has:

```json
{
  "id": "page_contains_block:Page:TB-G6S1U1-P4->Block:TB-G6S1U1-P4-D2",
  "type": "page_contains_block",
  "source": "Page:TB-G6S1U1-P4",
  "target": "Block:TB-G6S1U1-P4-D2",
  "page_uid": "TB-G6S1U1-P4",
  "block_uid": "TB-G6S1U1-P4-D2",
  "properties": {}
}
```

## Edge Types

| type | meaning |
| --- | --- |
| `book_contains_unit` | Book contains a unit. |
| `unit_contains_page` | Unit contains a page. |
| `page_contains_block` | Page contains a block. |
| `block_has_target` | Block has a general teaching, vocab, or phonics target. |
| `block_has_question_target` | Block has a question target. |
| `block_has_answer_target` | Block has an answer target or answer frame. |
| `question_expects_answer_frame` | Question target expects an answer frame. |
| `block_has_answer_scope` | Block has an allowed answer scope. |
| `block_has_vocab` | Block has a vocabulary item. |
| `vocab_returns_to_anchor` | Block vocabulary/support detour should return to an anchor. |
| `phonics_uses_pattern` | Phonics block uses a phonics pattern. |
| `phonics_uses_exemplar` | Phonics pattern uses an exemplar word. |
| `story_has_question` | Story block has a story question. |
| `story_has_character` | Story block includes a character. |
| `roleplay_has_pair` | Block has a role-play pair. |
| `node_from_source_file` | Curriculum node was extracted from a source file. |

## Audit JSON Shape

```json
{
  "schema_version": "curriculum_graph_audit_v1",
  "generated_at": "2026-05-05T12:00:00",
  "graph_schema_version": "curriculum_graph_v1",
  "rules": [],
  "summary": {
    "book_count": 0,
    "unit_count": 0,
    "page_count": 0,
    "block_count": 0,
    "node_count": 0,
    "edge_count": 0,
    "pages_by_book": {},
    "blocks_by_book": {},
    "pages_with_issues": [],
    "blocks_with_issues": [],
    "issue_counts_by_rule": {},
    "issue_counts_by_severity": {},
    "top_issue_pages": [],
    "six_anchor_pages_present": {},
    "six_anchor_pages_issue_summary": {}
  },
  "findings": []
}
```

Each finding has:

```json
{
  "rule": "question_without_answer_frame",
  "severity": "warning",
  "page_uid": "TB-G6S2U1-P4",
  "block_uid": "TB-G6S2U1-P4-D2",
  "node_id": "QuestionTarget:...",
  "node_type": "QuestionTarget",
  "source_files": [],
  "message": "",
  "evidence": {}
}
```

Severity values are `info`, `warning`, and `error`. Full-curriculum warnings are expected audit output, not PR failures.

## Audit Rules

| rule | intent |
| --- | --- |
| `missing_page_uid` | Node that needs page scope lacks `page_uid`. |
| `missing_block_uid` | Block node lacks a durable `block_uid`. |
| `missing_block_target` | Block lacks a usable target or teaching goal. |
| `missing_question_target` | Dialogue core block lacks a question target. |
| `question_without_answer_frame` | Question target has no linked answer frame. |
| `answer_frame_without_question` | Answer frame is not linked from a question. |
| `phonics_without_pattern` | Phonics block lacks a phonics pattern edge. |
| `phonics_without_exemplar` | Phonics pattern lacks an exemplar edge. |
| `story_without_question` | Story block lacks a story question. |
| `story_without_answer_frame` | Story question lacks a reusable answer frame. |
| `vocab_without_return_anchor` | Vocabulary-bearing block lacks a return anchor. |
| `suspicious_return_anchor` | Return anchor looks like an instruction wrapper or incomplete target. |
| `answer_scope_missing` | Block lacks answer-scope data where it is needed. |
| `answer_scope_ambiguous` | Allowed answer scope is too generic or ambiguous. |
| `multi_target_block_without_priority` | Multi-target block is not represented in page priority. |
| `target_role_unknown` | Block target role cannot be inferred. |
| `bare_noun_redirect_risk` | Focus vocabulary could be over-selected instead of the full question/answer target. |
| `module_choice_leak_risk` | Multi-block page has weak return anchors, increasing module-choice fallback risk. |
| `source_file_missing_or_unknown` | Node lacks source-file provenance. |

## Six Anchor Pages

The graph metadata and audit summary track these regression anchors while still covering the full corpus:

- `TB-G5S1U3-P22`
- `TB-G6S1U1-P4`
- `TB-G6S2U1-P4`
- `TB-G5S1U3-P31`
- `TB-G5S2U1-P6`
- `TB-G6S2U2-P13`

Each anchor summary includes page existence, block count, detected teaching targets, question targets, answer frames, answer-scope nodes, detected issues, bare-noun redirect risk, module-choice leak risk, and missing-answer-frame risk.

## Runtime Boundary

The graph and audit are offline artifacts only. They do not feed lesson runtime, TeachingMove planning, redirect reply policy, RAG, prompts, S4, TTS, browser smoke, persona, or classroom-visible replies. Findings are evidence for future data/schema repair slices; they are not runtime instructions.
