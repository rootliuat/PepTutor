# Prompt Memory Silent Regression Postmortem

Date: 2026-04-11

## Summary

The lesson prompt-memory stack has a high rate of silent regressions.
Most failures in this area do not crash tests or throw runtime errors.
They show up as:

- duplicated facts across prompt buckets
- contradictory learner state on the same target sentence
- scoped preferences leaking into long-term profile
- legacy free-text memories being misclassified
- semantic recall adding noise instead of signal
- structured writeback degrading into text-only heuristics
- runtime prompt payloads drifting away from provider expectations

This postmortem records the seven fragile details, the existing coverage, and
the gaps that needed explicit regression tests.

## Seven Fragile Details

### 1. Cross-bucket dedupe

Risk:
- The same teaching fact can appear in `current`, `stable`, and `semantic`
  buckets under different phrasing.

Existing coverage:
- `backend/LightRAG/tests/test_simplemem_prompt_memory.py`
  - `test_simplemem_prompt_memory_provider_dedupes_semantic_memories_against_current_buckets`
  - `test_simplemem_prompt_memory_provider_avoids_duplicate_global_preference_when_block_matches`
  - `test_simplemem_prompt_memory_provider_collapses_same_target_progress_variants`

Silent regression:
- Yes. Prompt gets larger and noisier, but nothing crashes.

Gap closed in this pass:
- Added one three-way regression so the same fact cannot survive in
  `current + stable + semantic` simultaneously.

### 2. Opposite progress states on the same target

Risk:
- `mistake` and `mastery` can both be injected for the same target sentence.

Existing coverage:
- `backend/LightRAG/tests/test_simplemem_prompt_memory.py`
  - `test_simplemem_prompt_memory_provider_stable_profile_prefers_latest_supported_progress`
  - `test_simplemem_prompt_memory_provider_filters_conflicting_semantic_progress`

Silent regression:
- Yes. The model gets contradictory memory and starts making confused teaching
  decisions.

### 3. Preference scope separation

Risk:
- Block-local repair tactics can leak into page or global learner profile.

Existing coverage:
- `backend/LightRAG/tests/test_simplemem_prompt_memory.py`
  - `test_simplemem_prompt_memory_provider_stable_preferences_respect_page_scope`
  - `test_simplemem_prompt_memory_provider_avoids_duplicate_global_preference_when_block_matches`
  - `test_simplemem_prompt_memory_provider_stable_preferences_prioritize_global_traits`

Silent regression:
- Yes. The system still runs, but learner profile quality degrades.

### 4. Conservative legacy-memory compatibility

Risk:
- Old free-text memories without `facts_json` can be reclassified incorrectly
  by heuristic changes.

Existing coverage:
- `backend/LightRAG/tests/test_simplemem_prompt_memory.py`
  - `test_simplemem_prompt_memory_provider_merges_legacy_summary_with_canonical_target`
  - `test_simplemem_prompt_memory_provider_uses_session_metadata_to_merge_legacy_variants`
  - `test_simplemem_prompt_memory_provider_infers_stable_preference_from_legacy_phrase_variants`
  - `test_simplemem_prompt_memory_provider_collapses_same_target_progress_variants`

Silent regression:
- Yes, and this is the most fragile class. A small hint-word change can send
  old memories into the wrong bucket without breaking execution.

Gap closed in this pass:
- Added one regression for a legacy mastery phrasing variant with no
  structured facts.

### 5. Semantic recall specificity and noise filtering

Risk:
- Semantic recall can bring back generic lesson-process noise such as
  "needs more guided help here".

Existing coverage:
- `backend/LightRAG/tests/test_simplemem_prompt_memory.py`
  - `test_simplemem_prompt_memory_provider_includes_semantic_memories`
  - `test_simplemem_prompt_memory_provider_dedupes_semantic_memories_against_current_buckets`
  - `test_simplemem_prompt_memory_provider_skips_generic_semantic_progress_noise`
  - `test_simplemem_prompt_memory_provider_filters_conflicting_semantic_progress`

Silent regression:
- Yes. Prompt quality slowly decays while all code paths still succeed.

### 6. Structured writeback must stay structured

Risk:
- If writeback stops emitting `candidate_kind`, `model_answer`,
  `mistake_focus`, or `preference_key`, prompt memory falls back to brittle
  text inference.

Existing coverage before this pass:
- `backend/LightRAG/tests/test_simplemem_writeback.py`
  - `test_simplemem_writeback_records_observations_and_summary`

Silent regression:
- Yes. Provider still returns something, but less precise and less stable.

Gap closed in this pass:
- Added one round-trip integration test where the writer writes SQLite data and
  the prompt-memory provider reads it back successfully.

### 7. Runtime integration, not just provider correctness

Risk:
- Provider tests can stay green while planner/responder prompt payloads drift.

Existing coverage:
- `backend/LightRAG/tests/test_lesson_runtime.py`
  - `test_live_prompts_receive_learner_memory_payload`
- `backend/LightRAG/tests/test_lesson_runtime_factory.py`
  - `test_build_lesson_runtime_can_inject_semantic_recall`

Silent regression:
- Yes. The runtime still executes, but learner memory stops influencing the
  actual lesson turn.

## Most Fragile Detail

The easiest detail to break in future edits is item 4: conservative
legacy-memory compatibility.

Why:
- it relies on heuristic text interpretation
- many old records have no structured facts
- tiny wording changes in canonicalization or hint dictionaries can silently
  re-route old memories into the wrong category

The second most fragile area is item 1, because every new bucket, filter, or
selector path can re-introduce duplicate facts under a different phrasing.

## New Regression Tests Added In This Pass

1. `backend/LightRAG/tests/test_simplemem_prompt_memory.py`
   `test_simplemem_prompt_memory_provider_dedupes_same_fact_across_all_memory_buckets`
   Verifies that one fact cannot survive simultaneously in current, stable, and
   semantic buckets.

2. `backend/LightRAG/tests/test_simplemem_prompt_memory.py`
   `test_simplemem_prompt_memory_provider_reads_legacy_mastery_variant_without_facts`
   Verifies that a legacy mastery phrasing variant with no `facts_json` still
   lands in `mastery_signals`.

3. `backend/LightRAG/tests/test_simplemem_writeback.py`
   `test_simplemem_writeback_round_trip_into_prompt_memory_provider`
   Verifies writer -> SQLite -> provider round-trip, including both structured
   raw fields and prompt-memory output.

## Validation

Commands used after the additions:

```bash
backend/LightRAG/.venv/bin/python -m pytest backend/LightRAG/tests/test_simplemem_prompt_memory.py backend/LightRAG/tests/test_simplemem_writeback.py
backend/LightRAG/.venv/bin/python -m pytest backend/LightRAG/tests/test_simplemem_prompt_memory.py backend/LightRAG/tests/test_lesson_runtime.py backend/LightRAG/tests/test_lesson_runtime_factory.py backend/LightRAG/tests/test_simplemem_writeback.py backend/LightRAG/tests/test_simplemem_semantic_memory.py
cd backend/LightRAG && .venv/bin/ruff check .
backend/LightRAG/.venv/bin/python -m pytest backend/LightRAG/tests
```

Result:

- `610 passed, 33 skipped`
