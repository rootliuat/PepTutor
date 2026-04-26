# Debug Signals Observability Postmortem

Date: 2026-04-12

## Current State

When `PEPTUTOR_DEBUG_SIGNALS=1` is enabled on the LightRAG lesson backend,
every `/lesson/turn` response now carries a full `debug_signals` payload.

That payload is no longer only a backend-side debugging aid.
The `/lesson` page renders it directly through the "本轮能力" card, and the
card now follows the latest real backend turn instead of a static fixture.

The important property here is dynamic alignment:

- backend returns the actual per-turn capability state
- frontend renders that exact payload
- browser smoke asserts the rendered card against the latest captured real
  `/lesson/turn` response

This closes the gap between:

- `FeatureStatus` at backend startup
- `debug_signals` on the runtime turn result
- frontend observability for the active lesson turn

## Validation Path

The acceptance path is not limited to the first teacher turn anymore.

Real browser smoke now verifies two things:

1. the first real `/lesson/turn` response exposes `debug_signals`
2. after learner input triggers a second real `/lesson/turn`, the card still
   matches the newest backend payload

This is exercised through:

```bash
cd frontend/airi && pnpm -F @proj-airi/stage-web test:run:browser:real
```

That command:

- waits for the real lesson backend to become ready
- runs browser smoke with `VITE_PEPTUTOR_LESSON_EXPECT_DEBUG_SIGNALS=1`
- asserts dynamic consistency, not just initial render

The key property is that the assertion compares rendered frontend state against
the captured real response body from `/lesson/turn`.
It does not rely on fixture defaults.

## What Is Verified

Current real-browser assertions cover at least:

- `live_prompts.enabled`
- `prompt_memory.enabled`
- the corresponding human-readable detail text for both fields

The test also proves that the card continues to track the latest turn after the
learner sends input, so stale first-turn values cannot silently persist on the
page.

## Risk Reminder

`injected_buckets` and `recalled_memories` being empty is currently normal for a
new learner with no useful prior memory.

That means:

- empty arrays are not evidence of a regression
- browser smoke must not hard-code those fields to stay empty forever

As real learner history accumulates, these fields are expected to become
non-empty:

- `prompt_memory.injected_buckets`
- `semantic_recall.recalled_memories`

Future smoke coverage should keep asserting frontend/backed consistency, but it
must not encode "empty means correct" as a permanent invariant.

## Validation

Commands used for this observability pass:

```bash
cd frontend/airi && pnpm -F @proj-airi/stage-web typecheck
cd frontend/airi && pnpm -F @proj-airi/stage-web test:run:browser:real
```

Result:

- `typecheck` passed
- real browser smoke passed with dynamic debug-signal consistency coverage
