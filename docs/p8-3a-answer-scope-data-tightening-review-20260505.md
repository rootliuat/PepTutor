# P8.3a Answer-Scope Data Tightening Review

Date: 2026-05-05

Scope: review-only. This document does not edit `app/knowledge/structured`, runtime, planner, redirect policy, prompts, RAG, S4, P13 data, persona, or smoke matrix.

Source evidence:

- `docs/curriculum-data-tightening-candidates-20260505.md`
- local generated candidate JSON: `temp/lesson-smoke-artifacts/curriculum_data_tightening_candidates_20260505_150353.json`
- local generated audit JSON: `temp/lesson-smoke-artifacts/curriculum_graph_audit_20260505_132456.json`

## Review Summary

The three P8.3a candidates are real review targets, but none should be edited before the May 8 delivery. They are source-data tightening candidates, not emergency runtime fixes. The current demo path is better protected by the existing TeachingMove/action-contract work and P5/P7/P13 runtime boundary fixes than by last-minute curriculum data mutation.

Recommendation:

```text
Defer data mutation until after May 8.
Keep the candidates documented for human review.
Do not invent P13 return_anchor or module_choice findings.
Do not classify P6 as phonics_without_exemplar; P6 is outside this P8.3a scope.
```

## Candidate 1: G6S2 U1 P4 D4

| Field | Value |
|---|---|
| page_uid | `TB-G6S2U1-P4` |
| block_uid | `TB-G6S2U1-P4-D4` |
| source file | `app/knowledge/structured/general/g6s2u1-general.json` |
| current issue class | `answer_scope_tightening_candidate` |
| current issue rule | `answer_scope_ambiguous` |
| current allowed_answer_scope | `["Personalized answer"]` |
| current question targets | `How old are you?`; `How tall are you?`; `Who is older than you?`; `Who is taller than you?` |
| current answer frames | `I'm ... metres tall.`; `... is ...`; `Personalized answer` |
| current return anchors | `How old are you?`; `How tall are you?`; `Who is taller than you?` |

Why selected:

`Personalized answer` is too broad for answer-scope validation. It does not distinguish personal-height answers, age answers, and comparison answers.

Proposed data-tightening action:

Split the generic scope into structured accepted answer families, for example:

- personal age answer for `How old are you?`
- personal height answer for `How tall are you?`
- comparison answer for `Who is older/taller than you?`

Risk if changed:

Over-tightening could reject valid personalized answers or force a rigid answer style on an open pair-work page.

Risk if not changed:

The graph will keep reporting ambiguous answer scope, and future runtime answer-scope logic may need to stay conservative.

Demo impact:

Low for the May 8 demo unless this exact personal-height block is shown. The known `How tall is it?` dinosaur block is already handled separately in the TeachingMove/action contract path.

May 8 recommendation:

```text
defer
```

This needs human curriculum review after delivery.

## Candidate 2: G6S2 U2 P13 D1

| Field | Value |
|---|---|
| page_uid | `TB-G6S2U2-P13` |
| block_uid | `TB-G6S2U2-P13-D1` |
| source file | `app/knowledge/structured/general/g6s2u2-general.json` |
| current issue class | `answer_scope_tightening_candidate` |
| current issue rule | `answer_scope_ambiguous` |
| current allowed_answer_scope | `["Last weekend"]` |
| current question targets | not detected by candidate planner |
| current answer frames | `Last weekend` |
| current return anchors | `Last weekend` |

Why selected:

`Last weekend` is a topic label, not an answer-scope contract. It does not express whether the learner is answering a weekend question, explaining vocabulary, returning from a vocab answer, or choosing a module.

Important boundary:

The P8.1/P8.2 graph audit does **not** show a P13 `return_anchor` finding and does **not** show a P13 `module_choice_leak_risk` finding. P13 must not be reclassified as a return-anchor or module-choice graph issue based on this audit alone.

Proposed data-tightening action:

After May 8, review the source block and decide whether to express separate structures for:

- weekend-topic expected answer scope
- vocabulary answer return behavior
- durable question/answer frame if present in the textbook source

Risk if changed:

This page has a known runtime history. A rushed source edit could reopen the answer-scope/module-choice boundary that has already been stabilized elsewhere.

Risk if not changed:

The audit will keep flagging `Last weekend` as ambiguous, and future graph-derived answer-scope logic will have to treat this block conservatively.

Demo impact:

Medium if P13 is shown, but current runtime behavior is already more stable than the source graph contract. Do not mutate source data immediately before submission.

May 8 recommendation:

```text
needs human review; defer data edit
```

## Candidate 3: G6S2 U2 P17 D1

| Field | Value |
|---|---|
| page_uid | `TB-G6S2U2-P17` |
| block_uid | `TB-G6S2U2-P17-D1` |
| source file | `app/knowledge/structured/general/g6s2u2-general.json` |
| current issue class | `answer_scope_tightening_candidate` |
| current issue rule | `answer_scope_ambiguous` |
| current allowed_answer_scope | `read a book`; `saw a film`; `had a cold`; `slept`; `last weekend`; `last night` |
| current question targets | `Did you like it?`; `What did you do last weekend?` |
| current answer frames | `I ...`; `I saw a film.`; `Yes, I did. / No, I didn't.`; `Yes, I did. It was great.`; `read a book`; `saw a film`; `had a cold`; `slept`; `last weekend`; `last night` |
| current return anchors | `Did you like it?`; `I saw a film.`; `What did you do last weekend?` |

Why selected:

The scope mixes answer phrases (`read a book`, `saw a film`, `had a cold`, `slept`) with time expressions (`last weekend`, `last night`). The action contract would be clearer if temporal context and answer actions were separated.

Proposed data-tightening action:

After May 8, split answer scope into:

- action/vocab answer set
- time-expression context
- yes/no answer for `Did you like it?`
- open answer frame for `What did you do last weekend?`

Risk if changed:

The page likely supports flexible personalized answers. Over-structuring may make the tutor sound too narrow.

Risk if not changed:

The graph keeps reporting an ambiguous scope, but the current demo does not depend on this block.

Demo impact:

Low for May 8 unless this page is selected deliberately.

May 8 recommendation:

```text
defer
```

## Final P8.3a Recommendation

No P8.3a data edits before May 8.

Use this document as a human-review checklist after submission. The first post-delivery implementation slice should be:

```text
P8.3a-answer-scope-data-tightening-source-review
```

That slice should edit only reviewed source blocks and should include a before/after graph audit, but it should not mutate runtime or prompts.
