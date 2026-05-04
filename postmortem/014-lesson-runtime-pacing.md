# Lesson Runtime Pacing Postmortem

Date: 2026-05-02

## Summary

Recent S3 issues had the same shape: the runtime could keep the request alive,
but the boundary between lesson structure, page navigation, short answers, and
teacher phrasing was not explicit enough. The fix pattern is to make the
classroom task contract observable before asking the LLM to phrase a reply.

## Incidents

### P24 Food/Drink Wrong Boundary

- Root cause pattern: same-page food and drink blocks shared vocabulary and
  examples, so a valid drink answer could be pulled back to the previous food
  step.
- Prevention rule: answer-turn policy must evaluate whether the learner input
  matches the current block, next block, or same-page support before forcing a
  pullback.
- Regression test: P24 `I'd like some water.` must route to the drink block
  without resetting to the first block.
- Smoke detector: state block drift and reply evidence that mentions the wrong
  same-page target.
- Owner file: `backend/LightRAG/lightrag/orchestrator/lesson_runtime.py`.

### P13 Vocabulary Return Repeats Module Choice

- Root cause pattern: vocabulary interruption explained the word but lost the
  active prompt, so the recovery reply reopened module choice.
- Prevention rule: lexicon turns inside an active task must carry a return
  anchor and may not reopen page overview unless the active prompt really is a
  module-choice prompt.
- Regression test: P13 `What does stayed at home mean?` returns to the current
  dialogue task without appending "你想先学哪一块".
- Smoke detector: vocabulary turns followed by repeated module-choice language.
- Owner file: `backend/LightRAG/lightrag/orchestrator/lesson_runtime.py` and
  `backend/LightRAG/lightrag/pedagogy/responder.py`.

### G6 Off-Topic Mis-Cuts Block

- Root cause pattern: off-topic learner text was treated like navigation or
  same-page intent because module choice and content matching were too loose.
- Prevention rule: only explicit module-navigation intent may switch block;
  off-topic social text should redirect to the active page prompt.
- Regression test: G6 off-topic inputs keep `current_block_uid` stable unless
  the learner says a real module selector such as "第二块".
- Smoke detector: block changes on off-topic turns without a module-choice
  input.
- Owner file: `backend/LightRAG/lightrag/orchestrator/module_choice_skill.py`.

### P49 Short-Answer Object Praise

- Root cause pattern: page-entry module choice used `llm_only`, and a short
  answer such as `pizza` reached the responder before the runtime grounded it
  against the party-picture classification task. The LLM filled the gap with
  object appraisal: "很好吃".
- Prevention rule: classify/list/find-word tasks must run a deterministic
  short-answer policy before free teacher phrasing. The policy must decide
  exact page item, alias item, related category term, wrong category, off-topic,
  or unknown from block metadata only.
- Regression test: P49 `pizza`, `water`, `news`, `我不知道`, and `我想学第二块`.
- Smoke detector: `generic_praise_for_short_answer` when short answers get
  object praise without category grounding, current-task pullback, or next step.
- Owner file:
  `backend/LightRAG/lightrag/pedagogy/classification_task_policy.py`.

## Prevention Rules

- Runtime owns task state and correctness boundaries.
- Responder owns voice only; it must not invent task classification.
- Structured lesson metadata should carry task type and answer categories when
  a task depends on classification.
- Any deterministic repair must be visible in `response_audit.repair_reason`.
- Smoke detectors should target failure shape, not a single phrase.

## Regression Surface

- `backend/LightRAG/tests/test_lesson_runtime.py`
- `backend/LightRAG/tests/test_lesson_smoke_scripts.py`
- `scripts/smoke_lesson_matrix.py`
- `temp/lesson_deep_smoke.py`
