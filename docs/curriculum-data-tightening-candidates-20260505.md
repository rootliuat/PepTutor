# Curriculum Data Tightening Candidates

Generated from: `temp/lesson-smoke-artifacts/curriculum_graph_audit_20260505_132456.json`
Graph context: `temp/lesson-smoke-artifacts/curriculum_graph_20260505_132456.json`
Generated candidate JSON: `temp/lesson-smoke-artifacts/curriculum_data_tightening_candidates_20260505_150353.json`

This is a read-only candidate plan. It does not edit structured curriculum data.

## Summary

- finding_count: 988
- candidate_count: 988
- P13 candidate classes: answer_scope_tightening_candidate
- P13 return-anchor/module-choice candidate: False
- P6 candidate classes: phonics_graph_inheritance_candidate, return_anchor_wrapper_candidate
- P6 has phonics_without_exemplar: False

## Candidate Counts By Class

| Class | Count |
|---|---:|
| `answer_scope_tightening_candidate` | 3 |
| `defer_low_priority_candidate` | 765 |
| `false_positive_rule_refinement_candidate` | 105 |
| `phonics_graph_inheritance_candidate` | 60 |
| `return_anchor_wrapper_candidate` | 55 |

## Candidate Counts By Priority

| Priority | Count |
|---|---:|
| `P0` | 3 |
| `P1` | 72 |
| `P2` | 155 |
| `P3` | 758 |

## Recommended Next Slices

1. P8.3a: answer-scope data tightening review. Human approval is still required before data edits.
2. P8.3b: phonics graph inheritance / rule refinement.

## Top Review Candidates

| ID | Priority | Class | Page | Block | Rule | Suggested action |
|---|---|---|---|---|---|---|
| `CDT-0871` | `P0` | `answer_scope_tightening_candidate` | `TB-G6S2U1-P4` | `TB-G6S2U1-P4-D4` | `answer_scope_ambiguous` | Review the block's allowed_answer_scope and replace generic labels with structured acceptable-answer intent, expected frame, and return-anchor boundaries; do not mutate data without human review. |
| `CDT-0894` | `P0` | `answer_scope_tightening_candidate` | `TB-G6S2U2-P13` | `TB-G6S2U2-P13-D1` | `answer_scope_ambiguous` | Review the block's allowed_answer_scope and replace generic labels with structured acceptable-answer intent, expected frame, and return-anchor boundaries; do not mutate data without human review. |
| `CDT-0913` | `P0` | `answer_scope_tightening_candidate` | `TB-G6S2U2-P17` | `TB-G6S2U2-P17-D1` | `answer_scope_ambiguous` | Review the block's allowed_answer_scope and replace generic labels with structured acceptable-answer intent, expected frame, and return-anchor boundaries; do not mutate data without human review. |
| `CDT-0001` | `P1` | `phonics_graph_inheritance_candidate` | `TB-G5S1U1-P6` | `TB-G5S1U1-P6-D1` | `phonics_without_pattern` | Model page-level phonics pattern/exemplar inheritance so practice blocks can inherit the pattern instead of requiring every block to repeat it. |
| `CDT-0002` | `P1` | `phonics_graph_inheritance_candidate` | `TB-G5S1U1-P6` | `TB-G5S1U1-P6-D2` | `phonics_without_pattern` | Model page-level phonics pattern/exemplar inheritance so practice blocks can inherit the pattern instead of requiring every block to repeat it. |
| `CDT-0003` | `P1` | `phonics_graph_inheritance_candidate` | `TB-G5S1U1-P6` | `TB-G5S1U1-P6-D3` | `phonics_without_pattern` | Model page-level phonics pattern/exemplar inheritance so practice blocks can inherit the pattern instead of requiring every block to repeat it. |
| `CDT-0004` | `P1` | `phonics_graph_inheritance_candidate` | `TB-G5S1U1-P6` | `TB-G5S1U1-P6-D4` | `phonics_without_pattern` | Model page-level phonics pattern/exemplar inheritance so practice blocks can inherit the pattern instead of requiring every block to repeat it. |
| `CDT-0005` | `P1` | `phonics_graph_inheritance_candidate` | `TB-G5S1U2-P16` | `TB-G5S1U2-P16-D1` | `phonics_without_pattern` | Model page-level phonics pattern/exemplar inheritance so practice blocks can inherit the pattern instead of requiring every block to repeat it. |
| `CDT-0006` | `P1` | `phonics_graph_inheritance_candidate` | `TB-G5S1U2-P16` | `TB-G5S1U2-P16-D2` | `phonics_without_pattern` | Model page-level phonics pattern/exemplar inheritance so practice blocks can inherit the pattern instead of requiring every block to repeat it. |
| `CDT-0007` | `P1` | `phonics_graph_inheritance_candidate` | `TB-G5S1U2-P16` | `TB-G5S1U2-P16-D3` | `phonics_without_pattern` | Model page-level phonics pattern/exemplar inheritance so practice blocks can inherit the pattern instead of requiring every block to repeat it. |
| `CDT-0008` | `P1` | `phonics_graph_inheritance_candidate` | `TB-G5S1U2-P16` | `TB-G5S1U2-P16-D4` | `phonics_without_pattern` | Model page-level phonics pattern/exemplar inheritance so practice blocks can inherit the pattern instead of requiring every block to repeat it. |
| `CDT-0179` | `P1` | `defer_low_priority_candidate` | `TB-G5S1U3-P22` | `TB-G5S1U3-P22-D1` | `bare_noun_redirect_risk` | Keep as target-priority risk evidence; do not promote to immediate source edit without runtime evidence. |

## Guardrails

- `should_mutate_data_now` is `false` for every candidate.
- P13 is not classified as return-anchor or module-choice risk unless the audit finding explicitly says so.
- P6 is not classified as `phonics_without_exemplar` because the P8.1 audit emitted no such P6 finding.
- Low-priority target-selection risks remain documented but are not promoted into immediate data edits.
