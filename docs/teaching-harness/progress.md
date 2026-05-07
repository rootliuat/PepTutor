# Teaching Harness Progress

Date: 2026-05-06

## Current State

P7.1 now adds a minimal runtime demo slice for two reviewed strategies:

- `TB-G5S1U3-P26` Let’s spell ow phonics.
- `TB-G5S1U3-P24` Let’s try + Let’s talk food/drink.

This is not full 255-page strategy coverage. It is a two-page runtime proof that reviewed strategy data can control the demo classroom path while RAG remains evidence only.
The hook is protected by `PEPTUTOR_TEACHING_STRATEGY_RUNTIME`; targeted tests enable it explicitly.

## Completed In This Slice

- Added reviewed JSON strategies under `app/knowledge/teaching_strategies/`.
- Added a typed page-strategy loader and strategy lock validation.
- Added a deterministic teacher strategy renderer for the two demo pages.
- Added a small Lesson Runtime hook that initializes and updates `strategy_state` when reviewed strategy data exists.
- Kept the runtime hook env-gated so existing page behavior is not changed outside the demo slice.

## Runtime Status

- Backend runtime changed: yes, only for reviewed strategy data selection and strategy-state debug.
- Frontend changed: no.
- RAG changed: no.
- Structured curriculum changed: no.
- GRPO/model training introduced: no.
- Smoke run: no.
- full/browser/deep smoke counts: 0/0/0.

## Next Increment

P7.2 should be runtime hardening before expansion:

1. Add a strategy replay fixture for manual P26/P24 transcripts.
2. Add an audit that checks strategy-state transitions against `allowed_actions`.
3. Keep page strategy data reviewed before runtime use.
4. Avoid expanding beyond two pages until P26/P24 behavior is manually accepted.
5. Add tests before any new page strategy is accepted.

## Harness Engineering Notes

- Repo is now the system of record for strategy shape and samples.
- `strategy-feature-list.json` is the feature inventory.
- This file is the progress log.
- Later implementation must stay incremental and test-gated.
