# Factory Silent-Off Postmortem

Date: 2026-04-11

## Problem

The lesson runtime factory used env flags as the primary gate for optional
features.

That created a silent-off failure mode:

- `llm_model_func` could be available, but live prompts stayed off if
  `PEPTUTOR_LESSON_LIVE_PROMPTS` was unset
- `embedding_func` and Qdrant settings could be available, but vector retrieval
  stayed off if `PEPTUTOR_LESSON_VECTOR_RETRIEVAL` was unset
- SimpleMem SQLite or LanceDB could be available, but prompt injection,
  writeback, or semantic recall stayed off if their env flags were unset

In all of those cases, the runtime still booted successfully.
The feature was simply disabled, with no machine-readable explanation for why it
was off.

This made the failure class hard to diagnose:

- capability existed
- feature did not enable
- no clear reason was attached to the assembled runtime

## Trigger

The easiest reproduction path was:

1. Start the lesson server with `llm_model_func` and/or `embedding_func`
   available.
2. Leave lesson feature flags unset.
3. Call `build_lesson_runtime(...)`.

Before the fix, the runtime came up in a reduced mode even though the underlying
capability was present.

## Fix

The factory was changed from flag-driven assembly to capability-driven
assembly.

Key changes:

- `build_lesson_runtime(...)` now auto-detects whether each optional feature can
  actually run.
- The assembled bundle now exposes `feature_statuses` on
  `LessonRuntimeBundle`.
- Each feature is represented by
  `FeatureStatus(enabled, mode, reason)`.
- `mode` distinguishes `auto`, `explicit`, and `disabled`.
- `enabled=False` is no longer allowed to exist without a reason.

The enforcement point is:

- `backend/LightRAG/lightrag/orchestrator/lesson_runtime_factory.py:72`

The guard is implemented in `FeatureStatus.__post_init__`, which raises if the
reason is empty.

## Regression Guard

This is now blocked in two layers.

### 1. Constructor-level invariant

`FeatureStatus` itself rejects empty reasons for disabled states:

- `backend/LightRAG/lightrag/orchestrator/lesson_runtime_factory.py:72`

This means future call sites cannot silently create
`enabled=False, reason=""`.

### 2. Factory regression tests

`backend/LightRAG/tests/test_lesson_runtime_factory.py` now covers both sides:

- positive auto-enable paths when capability exists but no env flag is set
- negative downgrade paths when capability is truly missing

Key guardrail test:

- `backend/LightRAG/tests/test_lesson_runtime_factory.py:875`
  `test_build_lesson_runtime_reports_non_empty_reasons_for_unavailable_auto_features`

That test explicitly checks that unavailable auto-detected features still return
non-empty reasons.

The suite also covers automatic enablement for:

- live prompts
- vector retrieval
- prompt injection
- writeback
- semantic recall

## Validation

Commands used after the change:

```bash
backend/LightRAG/.venv/bin/python -m pytest backend/LightRAG/tests/test_lesson_runtime_factory.py
backend/LightRAG/.venv/bin/python -m pytest backend/LightRAG/tests/test_lesson_runtime.py backend/LightRAG/tests/test_lesson_runtime_factory.py backend/LightRAG/tests/test_simplemem_prompt_memory.py backend/LightRAG/tests/test_simplemem_writeback.py backend/LightRAG/tests/test_simplemem_semantic_memory.py
cd backend/LightRAG && .venv/bin/ruff check .
backend/LightRAG/.venv/bin/python -m pytest backend/LightRAG/tests
```

Result:

- `618 passed, 33 skipped`

## Risk Reminder

Any future optional feature added to the lesson runtime factory must provide a
downgrade reason.

Do not add new statuses that only say `enabled=False`.

Minimum bar for any new feature:

- expose a `FeatureStatus`
- set `mode`
- provide a non-empty `reason`
- add both positive auto-enable coverage and negative downgrade coverage

If a future feature bypasses that contract, silent-off behavior can come back
without breaking runtime startup.
