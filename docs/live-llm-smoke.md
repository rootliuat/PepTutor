# Live LLM Smoke Validation

## Purpose
This document defines the current real-model acceptance path for the lesson runtime. It replaces older notes that referenced `lesson_graph`, `teacher_reasoning`, `teacher_response`, or `POST /lesson/pilot/invoke`.

Use it when you need to confirm:
- the current `build_lesson_runtime()` path really reaches a live DeepSeek-compatible model
- `soul.md` is actually wired into the live teacher path
- the current `POST /lesson/turn` contract still works end to end
- the active `P24 -> P25 -> P26` lesson behavior still matches the current demo expectations

## Current Smoke Entry Points
Use one or both of these paths:

- one-command route smoke:
  - run `cd /root/my-project/PepTutor && backend/LightRAG/.venv/bin/python scripts/smoke_lesson_turn.py`
  - the script starts a temporary `LightRAG` backend, enables lesson live prompts plus debug signals, and validates the current `POST /lesson/turn` contract across a continuous `P24 -> P25 -> P26` route
  - default mode is route-focused: it disables vector retrieval and SimpleMem add-ons so `/lesson/turn` can be smoke-tested without unrelated cold-start noise
  - current default coverage includes same-student page switches, `P25` in-page progression, the `P26` `What does snow mean?` interruption while the listening prompt is active, and a `G6S2U2 P13` unit-retrieval sanity slice for `stayed at home` / `had a cold`
  - current default coverage does not require the later `P25` breakfast branch to open as a real `branch`; keep that check in the full current-env route smoke or the direct runtime-factory path
  - set `PEPTUTOR_LESSON_SMOKE_FULL_STACK=1` if you want to keep the current vector/SimpleMem settings during the smoke
- one-command browser smoke:
  - run `cd /root/my-project/PepTutor && bash scripts/smoke_lesson_browser.sh`
  - the helper starts a temporary route-focused `lightrag-server` on `127.0.0.1:9625`, waits for `/lesson/catalog`, runs the checked-in Chromium `/lesson` real-browser suite, and shuts the backend down automatically
  - set `PEPTUTOR_LESSON_SMOKE_FULL_STACK=1` if you want to keep the current vector/SimpleMem settings during the browser smoke
  - set `PEPTUTOR_LESSON_SMOKE_KEEP_SERVER=1` only when you intentionally want the backend to stay up after the browser suite for manual debugging
  - checked-in offline regression now covers loopback proxy-bypass variants (`127.0.0.1`, `localhost`, `[::1]`), the default route-focused env, the `PEPTUTOR_LESSON_SMOKE_FULL_STACK=1` / `PEPTUTOR_LESSON_SMOKE_KEEP_SERVER=1` branch, preflight fail-fast checks for missing helper dependencies, and the wait-failure / browser-failure cleanup paths that must print the backend log tail via `backend/LightRAG/tests/test_lesson_smoke_scripts.py`
  - the frontend repo now also owns a standalone GitHub Actions workflow at `frontend/airi/.github/workflows/lesson-browser-smoke.yml`; it runs the same checked-in browser suite on narrow `push` to `main`, `workflow_dispatch`, and nightly `schedule`, using required secret `PEPTUTOR_LESSON_REAL_BACKEND_URL` plus optional auth secrets `PEPTUTOR_LESSON_API_KEY`, `PEPTUTOR_LESSON_BEARER_TOKEN`, `PEPTUTOR_LESSON_AUTH_USERNAME`, and `PEPTUTOR_LESSON_AUTH_PASSWORD`
  - because GitHub only indexes dispatchable workflows from the default branch, pre-merge external verification now uses a temporary fork-only bootstrap workflow on `rootliuat/airi:main` that checks out the PR branch; that path passed on `2026-04-19` with `1 file passed`, `8 passed | 6 skipped (14)` in `https://github.com/rootliuat/airi/actions/runs/24617715847` while the upstream PR stayed `MERGEABLE`, `BLOCKED`, not draft at `https://github.com/moeru-ai/airi/pull/1683`
  - the same PR then received a review-cleanup follow-up on `2026-04-19` at `https://github.com/moeru-ai/airi/pull/1683#issuecomment-4274929739`, touching `apps/stage-web/vite.config.ts`, `apps/stage-web/src/peptutor-voice-env-defines.ts`, `apps/stage-web/src/server/doubao-tts-proxy.ts`, `apps/stage-web/src/server/doubao-realtime-asr-proxy.ts`, `apps/stage-web/src/server/doubao-realtime-protocol.ts`, and their matching tests; that cleanup tightened client env exposure to `VITE_` keys only and hardened the local Doubao proxy helpers against malformed control frames and truncated upstream payloads
  - the same PR then received a typecheck-cleanup follow-up on `2026-04-19` at `https://github.com/moeru-ai/airi/pull/1683#issuecomment-4274969438`, touching `apps/stage-web/tsconfig.json`, `apps/stage-web/src/unplugin-vue-router-vite.d.ts`, `packages/stage-shared/tsconfig.json`, `packages/stage-shared/src/electron-screen-capture.d.ts`, `packages/stage-shared/src/electron-screen-capture-renderer.d.ts`, `packages/stage-shared/src/beat-sync/detector.ts`, and `packages/stage-ui/src/stores/providers.ts`; that follow-up cleared the previous `stage-web` `vue-tsc` blockers and the grouped-selector Chromium slice still passed on the new head
- direct runtime-factory smoke:
  - instantiate `build_lesson_runtime(...)`
  - drive `runtime.start_page()` and `runtime.handle_turn()` directly
- browser route smoke:
  - prefer `bash scripts/smoke_lesson_browser.sh` for the checked-in suite
  - if you need an interactive backend that stays up after the suite, start a dedicated long-lived shell with:
    - `cd /root/my-project/PepTutor/backend/LightRAG`
    - `PEPTUTOR_LESSON_LIVE_PROMPTS=1 PEPTUTOR_DEBUG_SIGNALS=1 PEPTUTOR_LESSON_VECTOR_RETRIEVAL=0 PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION=0 PEPTUTOR_SIMPLEMEM_WRITEBACK=0 PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL=0 ./.venv/bin/lightrag-server --host 127.0.0.1 --port 9625`
  - start `frontend/airi/apps/stage-web`
  - validate the current `P24 -> P25 -> P26` browser route path ending with the `P26` `snow` interruption, plus the checked-in `TB-G6S2U2-P13` unit-vocabulary interruption slice and the checked-in `TB-G6S2Recycle2-P49 -> P51` route-recovery slice
  - keep the separate committed mock-browser grouped-selector regression in mind as a UI-only guard: `TB-G6S2Recycle2-P49 -> TB-G6S1U1-P2`
  - a matching real-browser case is checked in under `frontend/airi/apps/stage-web/src/pages/lesson/index.browser.test.ts`
  - `scripts/wait-for-lesson-backend.sh` now bypasses proxies automatically for `127.0.0.1`, `localhost`, and `::1`, so the checked-in browser smoke no longer needs explicit `NO_PROXY` wrappers
  - `scripts/smoke_lesson_turn.py` remains the one-command direct route smoke, but `scripts/smoke_lesson_browser.sh` is now the default browser-smoke entry point

The route path now has a committed one-command direct smoke helper plus a committed one-command browser smoke helper. Browser acceptance now also has checked-in real-browser cases for `P24 -> P25 -> P26`, `TB-G6S2U2-P13`, and `TB-G6S2Recycle2-P49 -> P51`, plus a checked-in mock-browser grouped-selector cross-scope guard for `TB-G6S2Recycle2-P49 -> TB-G6S1U1-P2`; the committed `test:run:browser:real` suite was re-run locally on `2026-04-18` and passed in Chromium with `8 passed | 6 skipped (14)`, and it now also has a standalone frontend-owned workflow instead of relying only on local manual runs. That workflow path was then revalidated through a fork GitHub Actions run on `2026-04-19`; upstream still needs the PR merged plus `PEPTUTOR_LESSON_REAL_BACKEND_URL` and any required auth secrets before the scheduled job can run inside `moeru-ai/airi`.

The browser helper itself also has checked-in offline regression coverage now, including the failure paths that must print the backend log tail before exiting. Its cleanup path tracks the real `lightrag-server` PID, so the default one-command smoke actually releases `:9625` after the suite while `PEPTUTOR_LESSON_SMOKE_KEEP_SERVER=1` intentionally leaves the backend up for follow-up debugging. The frontend-owned browser launcher now lives at `frontend/airi/scripts/run-lesson-browser-real-smoke.sh`, with `frontend/airi/scripts/wait-for-lesson-backend.sh` as its local wait helper, so `frontend/airi` can execute the real-browser suite without depending on PepTutor root scripts.

## Prerequisites
- the repository root `.env` contains a usable `DEEPSEEK_API_KEY`
- optional overrides such as `DEEPSEEK_MODEL` or `DEEPSEEK_BASE_URL` are configured if needed
- `backend/LightRAG/.venv` is installed and usable
- for browser smoke, `frontend/airi` dependencies are installed

Recommended frontend env for lesson-only smoke:

```env
VITE_PEPTUTOR_LESSON_API_URL=http://127.0.0.1:9625
# if the backend is protected, add one of:
# VITE_PEPTUTOR_LESSON_API_KEY=...
# VITE_PEPTUTOR_LESSON_BEARER_TOKEN=...
# or let the browser auto-login:
# VITE_PEPTUTOR_LESSON_AUTH_USERNAME=...
# VITE_PEPTUTOR_LESSON_AUTH_PASSWORD=...
VITE_PEPTUTOR_SKIP_REMOTE_ASSET_DOWNLOADS=1
```

## Current Acceptance Cases
The current live smoke should cover these cases in `TB-G5S1U3-P24`:

1. page entry
   - the opening response is localized Chinese teacher wording
   - the opening response comes from the live teacher responder, not only from deterministic fallback text
   - the page starts on the expected `P24` teaching block
   - the first warm-up on `P24` uses a child-facing scene frame such as `假设你饿了...` instead of a worksheet-style task stem
2. in-lesson knowledge interruption
   - learner input: `What does salad mean?`
   - expected result:
     - `turn_label = ask_knowledge`
     - `retrieval_mode = unit`
     - the reply explains `salad`
     - the lesson returns to the active answer prompt
     - if the active prompt is still `I am hungry.`, the reply returns to that exact warm-up target instead of drifting into the later `eat` prompt
3. answer-style help
   - learner flow: first answer `I am hungry.`, then ask for `help`
   - expected result:
     - the reply gives concrete answer choices
     - the reply does not regress to `I'd like ...`
4. drink-to-food progression
   - learner flow: first answer `I am hungry.`, then answer `I'd like some tea.`
   - expected result:
     - `evaluation = correct`
     - the next active block becomes `TB-G5S1U3-P24-D4`
     - the reply moves to `What would you like to eat?`
5. wrong-domain answer rejection
   - learner flow: first answer `I am hungry.`, then answer `I'd like chicken and bread.`
   - expected result:
     - `evaluation = incorrect`
     - `teaching_action = hint`
     - `state.current_block_uid` stays on `TB-G5S1U3-P24-D3`
     - the reply offers drink answers such as `I'd like some tea.` or `I'd like water.`
6. single-word answer stays in sentence practice
   - learner flow: first answer `I am hungry.`, then answer `water`
   - expected result:
     - `evaluation = partially_correct`
     - `state.current_block_uid` stays on `TB-G5S1U3-P24-D3`
     - `awaiting_answer = true`
     - the reply asks for a full sentence instead of treating the one-word answer as complete
7. no repeated scene setup on the next correction turn
   - learner flow: first answer `I am hungry.`, then answer `water`
   - expected result:
     - the first teacher turn may introduce the scene frame such as `现在你口渴了...`
     - the next correction turn should focus on completing the sentence
     - the next correction turn should not simply repeat the same scene frame again
8. teacher-live coverage
   - run one longer conversation across `P24 -> P25 -> P26`
   - expected result:
     - every turn records at least one live `teacher` responder call
     - `page_entry`, `answer_question`, `ask_help`, and `ask_knowledge` all produce teacher replies through the live responder
     - the conversation can finish 20+ turns without silently dropping back to deterministic teacher text
9. short branch open and close
   - learner flow: on `TB-G5S1U3-P25-D3`, ask `Can I eat noodles for breakfast?`, then answer `okay`
   - expected result:
     - the first turn returns `turn_label = ask_knowledge`
     - `retrieval_mode = branch`
     - `retrieved_block_uids = [TB-G5S1U3-P27-D4]`
     - the branch turn sets `branch_active = true` and `awaiting_answer = false`
     - the follow-up turn closes the branch with `turn_label = social`
     - the role-play answer state is restored with `awaiting_answer = true`

## Recommended Direct Smoke Commands
The fastest checked-in route smoke is:

```bash
cd /root/my-project/PepTutor
backend/LightRAG/.venv/bin/python scripts/smoke_lesson_turn.py
```

That command now covers:
- localized `P24` entry plus in-page interruption and correction checks
- a same-student `P24 -> P25` page switch
- `P25` progression from `tea` into the service-question block and then into the role-play block
- a same-student `P25 -> P26` page switch
- the `P26` `snow` interruption while still awaiting the listening answer
- a separate `G6 P13` live route slice where `What does stayed at home mean?` and `What does had a cold mean?` both stay on `TB-G6S2U2-P13-D2` and hit the expected unit-level vocabulary page at top-1

For the slower current-env variant that keeps vector retrieval and SimpleMem enabled:

```bash
cd /root/my-project/PepTutor
PEPTUTOR_LESSON_SMOKE_FULL_STACK=1 backend/LightRAG/.venv/bin/python scripts/smoke_lesson_turn.py
```

Then, if you need deeper runtime-factory coverage, run:

From `backend/LightRAG`:

```bash
./.venv/bin/python -m pytest tests/test_lesson_runtime.py -q
./.venv/bin/python -m pytest tests/test_lesson_runtime_factory.py -q
```

Then run a real-model check through `build_lesson_runtime()` and verify the fields listed in the acceptance cases above.

For the current acceptance bar, include one real long-conversation run and record:
- total turns
- how many turns contained a live `teacher` responder call
- whether all teacher turns hit the live responder

## Recommended Browser Smoke Flow
1. Prefer the one-command browser helper:

```bash
cd /root/my-project/PepTutor
bash scripts/smoke_lesson_browser.sh
```

   That helper starts the route-focused backend, waits for readiness, runs the checked-in browser suite, and cleans up automatically.

   If you need a backend that stays alive for extra manual checks, start a temporary lesson backend on `127.0.0.1:9625` using `build_lesson_runtime()` and `create_lesson_routes()` in a dedicated shell. For the checked-in browser suite, use:

```bash
cd /root/my-project/PepTutor/backend/LightRAG
PEPTUTOR_LESSON_LIVE_PROMPTS=1 \
PEPTUTOR_DEBUG_SIGNALS=1 \
PEPTUTOR_LESSON_VECTOR_RETRIEVAL=0 \
PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION=0 \
PEPTUTOR_SIMPLEMEM_WRITEBACK=0 \
PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL=0 \
./.venv/bin/lightrag-server --host 127.0.0.1 --port 9625
```

   `scripts/smoke_lesson_turn.py` is still the right direct route smoke, while `scripts/smoke_lesson_browser.sh` is the default browser-smoke entry point.
2. Start `frontend/airi/apps/stage-web` with:

```bash
cd /root/my-project/PepTutor/frontend/airi/apps/stage-web
VITE_PEPTUTOR_LESSON_API_URL=http://127.0.0.1:9625 \
VITE_PEPTUTOR_SKIP_REMOTE_ASSET_DOWNLOADS=1 \
pnpm dev
```

3. Open:

```text
http://127.0.0.1:5173/lesson?page_uid=TB-G5S1U3-P24
```

4. Verify:
   - page entry loads automatically
   - the bundled character is visible on the left stage area, even if prior global Live2D position or scale settings were bad
   - the page does not trigger a direct `hiyori_free_zh.zip` or `hiyori_pro_zh.zip` browser download prompt while loading the preset model
   - `What does salad mean?` explains the word and returns to the lesson
   - the first `I am hungry.` warm-up is framed through a concrete scene, not as a worksheet instruction
   - `给提示` after `I am hungry.` gives two concrete drink answers
   - a one-word drink answer such as `water` does not advance the block and the next teacher turn asks for a full sentence
   - a correct drink answer advances to the food prompt
   - `I'd like chicken and bread.` does not advance to the next block
   - an in-app page-selector click from `P25` to `P26` reloads the listening opening turn on `TB-G5S1U3-P26-D2`
   - `What does snow mean?` routes to `ask_knowledge`, keeps `state.current_block_uid = TB-G5S1U3-P26-D2`, and preserves `awaiting_answer = true`
5. Then open:

```text
http://127.0.0.1:5173/lesson?page_uid=TB-G6S2U2-P13
```

6. Verify:
   - page entry loads automatically on `TB-G6S2U2-P13-D2`
   - `What does stayed at home mean?` routes to `ask_knowledge`
   - `retrieval_mode = unit`
   - `state.current_block_uid` stays on `TB-G6S2U2-P13-D2`
   - `awaiting_answer = true` is preserved
   - `retrieved_block_uids[0] = TB-G6S2U2-P15-D1`
   - `What does had a cold mean?` keeps the same current block and hits `TB-G6S2U2-P17-D1` at top-1

## Pass Criteria
The smoke passes only when all of the following are true:
- the live model path responds without falling back silently because of transport or parameter-shape issues
- the root `soul.md` persona is present in the live teacher prompt path
- `ask_knowledge` interruptions stay lesson-aware
- scene-based warm-up phrasing is present where expected
- answer-style help and hint responses stay concrete
- one-word sentence fragments do not pass as completed full answers
- correction turns do not keep repeating the same scene setup once that scene has already been introduced
- correct drink answers advance into the follow-up food prompt
- wrong-domain food answers are rejected on the `drink` prompt
- `page_entry` and answer-evaluation replies also hit the live teacher responder when `live_prompts_enabled = true`
- the browser `/lesson` route shows the same behavior as the direct backend check
- the browser `/lesson` route still renders the bundled Live2D character without relying on a clean global stage configuration
- the preset bundled model path does not regress to a raw `.zip` URL that browsers or extensions may treat as a direct download

## Failure Reading Guide
Typical failure buckets:

- the live runtime falls back to deterministic behavior unexpectedly
  - provider config is incomplete
  - the live prompt path was not enabled
  - the model client rejected the request shape
- `ask_knowledge` does not return to the active answer prompt
  - open-turn interruption routing regressed
- answer-style help regresses to `I'd like ...`
  - concrete scaffold ranking or responder constraints regressed
- the teacher keeps repeating `现在你口渴了` or the same scene frame on consecutive correction turns
  - live responder prompt constraints or fallback phrasing regressed
- `I'd like some tea.` does not advance into `TB-G5S1U3-P24-D4`
  - the approved `P24` block split or success-transition path regressed
- `water` is accepted as if it were a full sentence answer
  - sentence-level evaluation or active-block correction flow regressed
- `I'd like chicken and bread.` is accepted on the `drink` prompt
  - prompt-aware answer filtering regressed
- browser route behavior differs from direct runtime behavior
  - frontend lesson store or route isolation regressed
- the stage is blank or the browser starts downloading `hiyori_free_zh.zip`
  - lesson-stage model recovery regressed
  - route-local Live2D framing regressed
  - preset-model asset routing regressed back to a raw `.zip` path

## Relationship To Pytest
The default regression suite remains:
- deterministic where possible
- local and repeatable
- suitable for normal development

The live smoke remains:
- network-dependent
- API-key-dependent
- model-dependent
- intended for acceptance before demo or release
