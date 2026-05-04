# Runtime State Minimal View Default-On

`answer_turn_policy` now uses the minimal runtime state view by default.

The switch is intentionally narrow:

- It only changes the runtime state frame sent to `answer_turn_policy`.
- It keeps the existing output schema and policy rubric.
- It does not change RAG, route selection, page/block progression, P49 classification, P13 answer scope data, S4, persona, or the smoke matrix.

## Rollback

Set this environment variable before starting the backend:

```bash
PEPTUTOR_ANSWER_TURN_MINIMAL_RUNTIME_STATE=0
```

Accepted enabled values are:

```text
1, true, yes, on
```

When the variable is unset, the minimal runtime state view is enabled.
