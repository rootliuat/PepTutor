# P8.2 Curriculum Graph Findings Triage

Generated from: `temp/lesson-smoke-artifacts/curriculum_graph_audit_20260505_132456.json`

Scope followed: read-only graph-audit triage. No runtime, planner, redirect policy, prompt, RAG, S4, P49, P13 data, persona, or smoke matrix changes. No full, browser, or deep smoke was run.

## Executive Summary

P8.1 produced 988 curriculum-graph findings across 255 pages and 581 blocks. The findings are useful, but they are not all runtime defects.

The safest interpretation is:

| Triage bucket | Count | Meaning |
|---|---:|---|
| Real curriculum structure gaps | 695 | Missing or underspecified source-level teaching structure: question targets, answer frames, story questions, answer scopes, or return anchors. |
| Rule/modeling false positives | 60 | The current graph rule expects per-block phonics patterns; many phonics practice blocks should inherit a page-level pattern instead. |
| Low-priority risk signals | 233 | Warnings that identify possible runtime target-selection risk, not confirmed broken data. |
| Next-round fix candidates | subset | Small, reviewable source/schema fixes drawn from the above, not a separate additive count. |

Recommended next slice: **P8.3 Curriculum Graph Source Repair Plan**, starting with graph/source-level fixes only. Do not patch runtime from this audit alone.

## Rule Triage Table

| Rule | Count | Severity | Triage | Read |
|---|---:|---|---|---|
| `question_without_answer_frame` | 576 | warning | Real structure backlog | The largest gap. Many question targets lack explicit answer frames. Some are legitimate read-aloud or dialogue questions, so this needs source/schema triage before bulk fixing. |
| `bare_noun_redirect_risk` | 180 | warning | Low-priority risk signal | Not a source error. It marks places where a vocab item appears inside a question and could be over-selected as a bare target. Useful for target-priority review. |
| `story_without_question` | 65 | warning | Real structure gap with possible false positives | Some story blocks need a question; some are narrative/setup panels. Needs story block role classification. |
| `phonics_without_pattern` | 60 | error | Rule/modeling false positive class | Mostly indicates graph extraction/inheritance is too strict. Practice blocks often need inherited page-level phonics pattern, not duplicated source text. |
| `suspicious_return_anchor` | 53 | warning | Low-priority risk signal / source cleanup candidate | Return anchors like `Listen and tick.` or `Choose and write.` are activity wrappers, not teaching targets. Normalize source anchors before runtime use. |
| `story_without_answer_frame` | 40 | warning | Real structure gap | Story questions need answer frames for stable redirect scaffold. |
| `missing_question_target` | 9 | warning | Real structure gap | Dialogue core blocks with no question target. High leverage because it affects target/action contracts. |
| `answer_scope_ambiguous` | 3 | warning | Real structure gap | Generic scopes like `Last weekend` or `Personalized answer` are not enough to prevent answer-scope drift. |
| `module_choice_leak_risk` | 1 | warning | Real structure gap | One multi-block page lacks a return anchor and can fall back to module-choice wording. |
| `vocab_without_return_anchor` | 1 | warning | Real structure gap | One vocab block has focus vocabulary but no return anchor. |
| `phonics_without_exemplar` | 0 | n/a | Audit blind spot for P8.2 focus | The rule exists but emitted no findings. P6 still shows phonics readiness risk through `phonics_without_pattern` and wrapper anchors. |

## Six Anchor Pages

| Page | Findings | Triage |
|---|---:|---|
| `TB-G5S1U3-P22` | 1 | `bare_noun_redirect_risk` for `favourite food` inside `What's your favourite food?`. This is a known target-priority risk, not a source defect by itself. |
| `TB-G6S1U1-P4` | 4 | Location Q/A structure is represented, but `museum shop` and `post office` are still marked as bare-noun risks. `Listen and tick.` is a wrapper anchor. D3 has a question without answer frame. |
| `TB-G6S2U1-P4` | 5 | `How tall is it?` is present, but D2 lacks an answer frame in the graph audit. D4 has `Personalized answer`, which is too broad. `How tall are you?` page content creates bare-noun/role ambiguity risk. |
| `TB-G5S1U3-P31` | 0 | Story scaffold is clean in this graph audit: question and answer frame are represented. No P8.2 source repair needed for this anchor. |
| `TB-G5S2U1-P6` | 5 | P6 has two `phonics_without_pattern` findings and three wrapper-style return anchors. The audit did not emit `phonics_without_exemplar`, so the P6 issue is currently modeled as phonics inheritance/anchor normalization. |
| `TB-G6S2U2-P13` | 1 | Only `answer_scope_ambiguous` is present: `allowed_answer_scope=["Last weekend"]`. P8.1 does not show a P13 `return_anchor` or `module_choice_leak_risk` finding. |

## Required Focus Areas

### P13 Return Anchor / Module Choice Boundary

P8.1 audit evidence for P13 is narrower than the runtime history:

```text
page_uid=TB-G6S2U2-P13
block_uid=TB-G6S2U2-P13-D1
rule=answer_scope_ambiguous
evidence={"allowed_answer_scope": ["Last weekend"]}
```

There is no P13 `module_choice_leak_risk` or `suspicious_return_anchor` finding in this audit. The source-level fix candidate is therefore not a runtime redirect patch. It is to make P13 answer scope more explicit, e.g. separating weekend-topic scope, vocabulary answer returns, and module-choice boundaries in structured curriculum data.

### P6 Phonics Without Exemplar

The `phonics_without_exemplar` rule emitted zero findings. P6 still has phonics risk:

```text
TB-G5S2U1-P6-D2 phonics_without_pattern
TB-G5S2U1-P6-D3 phonics_without_pattern
TB-G5S2U1-P6-D1 suspicious_return_anchor: Learn the consonant blend 'cl' as in 'clean'.
TB-G5S2U1-P6-D1 suspicious_return_anchor: Learn the consonant blend 'pl' as in 'plate'.
TB-G5S2U1-P6-D3 suspicious_return_anchor: Choose, write and say.
```

This should be triaged as a graph/source modeling issue. Practice blocks should inherit page-level phonics patterns and exemplars where appropriate, instead of requiring each practice block to repeat the pattern. Keep the existing runtime guard that prevents `cl' as in` from leaking to visible replies.

### Story Question / Answer Frame

Story findings are substantial:

```text
story_without_question=65
story_without_answer_frame=40
```

These are likely mixed:

- True structure gaps where story redirect needs `story_question` and `answer_frame`.
- Valid story panels that are narrative, setup, or reading-only blocks with no single expected answer.

Do not bulk-fill story frames from heuristics. First add or use a story block role distinction: `story_setup`, `story_question`, `story_answer`, `story_reading`, `story_wrap`.

### Bare Noun Redirect Risk

`bare_noun_redirect_risk=180` is a warning class, not proof of broken source data. It is valuable because it identifies the same class of risk that previously affected pages like:

- `TB-G5S1U3-P22`: `favourite food`
- `TB-G6S1U1-P4`: `museum shop`, `post office`
- `TB-G6S2U1-P4`: `older` inside personal comparison questions

The safe repair is source-level target priority or graph edge weighting, not page-specific runtime patches.

### Answer Scope Ambiguous

There are three ambiguous answer-scope findings:

| Page | Block | Evidence |
|---|---|---|
| `TB-G6S2U1-P4` | `TB-G6S2U1-P4-D4` | `["Personalized answer"]` |
| `TB-G6S2U2-P13` | `TB-G6S2U2-P13-D1` | `["Last weekend"]` |
| `TB-G6S2U2-P17` | `TB-G6S2U2-P17-D1` | `["last weekend"]` |

These are high-value source/schema cleanup candidates because they affect answer-scope boundaries without requiring prompt or runtime behavior changes.

## Next-Round Minimal Fix Candidates

### P8.3a Answer-Scope Data Tightening

Scope:

- `TB-G6S2U1-P4-D4`
- `TB-G6S2U2-P13-D1`
- `TB-G6S2U2-P17-D1`

Goal: replace broad scopes like `Personalized answer` and `Last weekend` with structured acceptable-answer intent, expected frame, and return anchor fields. This is the smallest high-leverage source repair.

### P8.3b Phonics Graph Inheritance

Scope:

- Graph builder/audit schema, not runtime.
- Start with `phonics_without_pattern=60`, using P6 as the anchor.

Goal: represent page-level phonics pattern/exemplars and allow practice blocks to inherit them. Do not duplicate patterns into every block unless the source truly says so.

### P8.3c Story Role Classification

Scope:

- `story_without_question=65`
- `story_without_answer_frame=40`

Goal: distinguish story setup/reading/question/answer blocks before filling missing frames. Prioritize pages with both story question and answer-frame risk.

### P8.3d Return Anchor Normalization

Scope:

- `suspicious_return_anchor=53`
- `vocab_without_return_anchor=1`
- `module_choice_leak_risk=1`

Goal: stop activity wrappers such as `Listen and tick.`, `Choose and write.`, and `Learn the consonant blend...` from being treated as durable teaching targets in source-derived graph fields.

### P8.3e Question Answer-Frame Backlog Triage

Scope:

- `question_without_answer_frame=576`

Goal: do not bulk-fix all 576. First rank by page risk and block role. Use top pages and anchor-adjacent pages to decide where answer frames are true missing data.

## Not Recommended For Immediate Implementation

- No runtime target-source change from P8.2 alone.
- No redirect policy patch from graph warnings alone.
- No prompt change.
- No page_uid special cases.
- No smoke-input special cases.
- No full smoke validation for this read-only triage.

## Completion Checklist

| Requirement | Evidence |
|---|---|
| Analyze all 988 findings | Rule triage table accounts for all findings by rule and bucket. |
| Classify into real gaps, false positives, low priority, fix candidates | Executive summary and rule table provide these buckets; fix candidates are explicitly listed as a subset. |
| Cover six anchor pages | Anchor page table includes all six named pages. |
| Cover P13 return-anchor/module-choice boundary | P13 section states the audit only shows `answer_scope_ambiguous`, with no P13 return-anchor/module-choice finding in P8.1. |
| Cover P6 phonics issue | P6 section covers zero `phonics_without_exemplar` findings plus actual P6 phonics findings. |
| Cover story missing question/frame | Story section covers counts and triage. |
| Cover bare noun redirect risk | Dedicated section covers count and anchor examples. |
| Cover answer_scope_ambiguous | Dedicated table covers all three findings. |
| Output next minimal repair candidates | P8.3a through P8.3e provide ordered candidates. |
| Avoid forbidden runtime/smoke work | This document is the only output; no full/browser/deep smoke was run. |
