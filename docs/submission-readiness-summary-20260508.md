# May 8 Submission Readiness Summary

Date: 2026-05-05

## Latest Main Commit

Engineering baseline after PR #15 merge:

```text
4a79d4eab034637866e96ba7b564d925b418e7bd
```

The final delivery-document commit is recorded in the handoff report after this document is pushed.

## Relevant Merged PRs

| PR | Title | Merge commit | Delivery relevance |
|---|---|---|---|
| [#8](https://github.com/rootliuat/PepTutor/pull/8) | fix: prepare Mili visible tone manual testing | `963252585b8a951db269a68f1cf8e616d4abdd6a` | Prepared S3 Mili visible tone/manual test path. |
| [#9](https://github.com/rootliuat/PepTutor/pull/9) | fix: resolve lesson browser tool binaries directly | `7d6c98c60cb416a78483a684b1b796dfaae3306b` | Closed brittle Vite/Vitest bin path startup failure. |
| [#11](https://github.com/rootliuat/PepTutor/pull/11) | fix: check lesson browser backend before budget | `7014b1e2f75c37f9c140badd44b947eae126da51` | Made browser smoke preflight fail before budget accounting when backend binaries are missing. |
| [#13](https://github.com/rootliuat/PepTutor/pull/13) | test: add P5 location QA preservation handoff | `a1b7cb7b76397c56be3510e55e670ec52046bd28` | Preserved location Q/A target behavior for the May 8 demo path. |
| [#15](https://github.com/rootliuat/PepTutor/pull/15) | feat: add curriculum graph extraction audit | `4a79d4eab034637866e96ba7b564d925b418e7bd` | Added full structured curriculum graph audit, triage, and candidate planner. |

## Key Docs

| Document | Purpose |
|---|---|
| `docs/submission-project-book-outline-20260508.md` | Project-book scaffold for May 8 submission. |
| `docs/submission-video-script-20260508.md` | 6-8 minute explanation video script. |
| `docs/p8-3a-answer-scope-data-tightening-review-20260505.md` | Review-only answer-scope candidate plan; no data mutation. |
| `docs/curriculum-graph-schema-v1.md` | Curriculum graph schema. |
| `docs/curriculum-graph-audit-summary-20260505.md` | Compact audit summary; full JSON artifacts are local generated outputs. |
| `docs/curriculum-graph-findings-triage-20260505.md` | P8.2 findings triage. |
| `docs/curriculum-data-tightening-candidates-20260505.md` | P8.3a/P8.3b candidate summary. |
| `docs/demo-handoff-p0-p5-20260505.md` | Demo handoff for P0-P5. |
| `docs/manual-test-record-s3-mili-tts-human-av-20260505.md` | Human AV boundary record. |
| `docs/test-budget-guard.md` | Test budget policy. |

## Demo Route

Startup:

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

Open:

```text
http://127.0.0.1:5173/lesson
```

Suggested demo pages:

- `TB-G6S1U1-P4`: location Q/A preservation, `Where is the museum shop?` plus `It's near ...`
- `TB-G5S2U1-P6`: phonics scaffold and `cl' as in` non-regression
- `TB-G5S1U3-P31`: story scaffold

Show:

- student input
- teacher reply
- Sidebar route / TeachingMove / persona / TTS fields
- TTS playback state and Live2D observation fields where visible

## Known Blockers / Honest Limits

- True TTS naturalness still requires a human listener.
- True mouthOpen synchronization naturalness still requires a human viewer.
- Mili persona wiring is clean, but fully human-like visible personality is not complete.
- P8.3a is review-only; answer-scope source data was not changed before May 8.
- RAGFlow is not integrated.
- GRPO is not implemented.
- No model training was introduced.
- Full autonomous teacher behavior is not claimed.

## Smoke Counts For This Delivery-Freeze Goal

```text
full 20-page smoke=0
browser smoke=0
deep smoke=0
```

PR #15 validation reused the already completed targeted checks:

```text
pytest backend/LightRAG/tests/test_curriculum_graph_audit.py backend/LightRAG/tests/test_curriculum_data_tightening_plan.py -q -> 9 passed
ruff check scripts/build_curriculum_graph.py scripts/audit_curriculum_graph.py scripts/plan_curriculum_data_tightening.py backend/LightRAG/tests/test_curriculum_graph_audit.py backend/LightRAG/tests/test_curriculum_data_tightening_plan.py -> All checks passed
```

## Do Not Change Before Submission

- Do not change runtime.
- Do not change planner.
- Do not change redirect policy.
- Do not change prompts.
- Do not change RAG.
- Do not change S4.
- Do not change P13 data.
- Do not change persona/soul.
- Do not change smoke matrix.
- Do not edit `app/knowledge/structured`.
- Do not start GRPO, model training, or RAGFlow integration.
- Do not run full/browser/deep smoke unless explicitly requested for a final acceptance pass.

## May 6 Exact Next Action

Use the project-book outline and video script to prepare the actual submission assets:

```text
May 6: convert docs/submission-project-book-outline-20260508.md into the final formatted project book, then record a rehearsal against docs/submission-video-script-20260508.md.
```
