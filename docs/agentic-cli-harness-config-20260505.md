# Agentic CLI Harness Config

PepTutor P8.5 adds an offline harness for curriculum evidence review. It is not part of the live lesson runtime.

## Boundary

- Canonical curriculum source: `app/knowledge/structured`.
- Agentic CLI output: supporting evidence for human review only.
- The harness must not edit `app/knowledge/structured`, runtime code, prompts, TeachingMove, redirect policy, S4, persona, or smoke matrix.
- No model training, GRPO, or live lesson integration is included.

## Default Mode

The default provider is `none`.

```bash
python scripts/run_agentic_curriculum_harness.py --provider none
```

`provider=none` builds prompts and local review artifacts only. It does not call an external model or CLI.

## Providers

Supported provider labels:

- `none`
- `kimi`
- `deepagents`
- `bub`
- `generic`

For non-`none` providers, pass a command template:

```bash
python scripts/run_agentic_curriculum_harness.py \
  --provider generic \
  --provider-command 'cat {prompt_file}'
```

The command template may use:

- `{prompt_file}`
- `{query_id}`
- `{provider}`

Provider calls are logged with:

- command
- exit_code
- stdout
- stderr
- duration_seconds

## Query Set

Default query set:

```text
docs/curriculum-agentic-query-set-20260505.json
```

It covers the current anchor evidence questions:

- `Where is the museum shop?`
- `It's near ...`
- `How tall is it?`
- `TB-G6S2U2-P13 answer scope`
- `cl as in clean`
- `What's your favourite food?`
- `story scaffold P31`

## Outputs

Harness output:

```text
temp/lesson-smoke-artifacts/agentic_curriculum_harness_<timestamp>.json
```

Comparison output:

```text
temp/lesson-smoke-artifacts/curriculum_retrieval_comparison_<timestamp>.json
docs/curriculum-retrieval-comparison-report-20260505.md
```

Review queue output:

```text
temp/lesson-smoke-artifacts/curriculum_evidence_review_queue_<timestamp>.json
docs/curriculum-evidence-review-queue-20260505.md
```

Generated JSON artifacts under `temp/lesson-smoke-artifacts` are local evidence artifacts and should not be committed by default.
