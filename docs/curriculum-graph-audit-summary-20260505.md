# Curriculum Graph Audit Summary

Date: 2026-05-05

This is the compact tracked summary for the P8.1/P8.2 curriculum graph work. The full generated JSON artifacts are local build outputs and are intentionally not tracked in Git.

## Local Artifacts

| Artifact | Path |
|---|---|
| Generated graph JSON | `temp/lesson-smoke-artifacts/curriculum_graph_20260505_132456.json` |
| Generated graph audit JSON | `temp/lesson-smoke-artifacts/curriculum_graph_audit_20260505_132456.json` |
| Findings triage document | `docs/curriculum-graph-findings-triage-20260505.md` |

## Corpus Counts

| Metric | Count |
|---|---:|
| books | 4 |
| units | 30 |
| pages | 255 |
| blocks | 581 |
| nodes | 9328 |
| edges | 22475 |
| finding_count | 988 |
| six anchor pages present | 6/6 |

## Triage Counts

| Bucket | Count |
|---|---:|
| true curriculum structure gaps | 695 |
| modeling/rule false-positive class | 60 |
| low-priority risk signals | 233 |

## P13 Summary

`TB-G6S2U2-P13` has one P8.1 graph-audit finding:

```text
answer_scope_ambiguous
```

The audit does not show:

- P13 `return_anchor` finding
- P13 `module_choice_leak_risk` finding

P13 should therefore not be classified as a return-anchor or module-choice graph issue from this audit alone. The safe candidate is answer-scope data tightening review.

## P6 Summary

`TB-G5S2U1-P6` does not have a `phonics_without_exemplar` finding in the P8.1 audit.

The exposed P6 graph-audit issues are:

- `phonics_without_pattern`
- wrapper-style return anchors such as `Learn the consonant blend 'cl' as in 'clean'.`

Recommended later work:

```text
P8.3b phonics page-level inheritance / graph-rule refinement
```

The next repair should make page-level phonics patterns and exemplars available to practice blocks without treating wrapper instructions as durable target phrases.
