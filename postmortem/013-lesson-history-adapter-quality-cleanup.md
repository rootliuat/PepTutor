# 013 Lesson History, Adapter, And Reply Quality Cleanup

Date: 2026-04-29

## Scope

This pass deliberately skipped Live2D expression files because the current model asset does not provide an expression layer. The work focused on four remaining lesson stability issues:

- legacy history visibility and restore labels
- AIRI mods WebSocket noise on the lesson route
- answer-turn reply self-review context
- stale tab / stale page session state making the input read-only

## What Changed

### History Labels

The backend audit already classifies sessions as:

- `continue`: v3, clean, block-restorable
- `read_only`: legacy or mixed-page history that should not restore state
- `view_only`: readable chat history without safe runtime recovery

The frontend now labels `view_only` as `不可恢复`, with detail text saying it can be viewed but cannot restore classroom state. This is intentionally not a migration. Old polluted JSON files stay untouched.

### Lesson Mods Server Connection

The lesson route does not require the AIRI mods server at `ws://localhost:6121/ws`. Connecting by default produced console noise like adapter / WebSocket failures and made validation harder.

The channel store now skips the default connection on `/lesson` unless a real WebSocket URL was explicitly configured through `VITE_AIRI_WS_URL` or a non-default local setting. This keeps normal AIRI pages free to use the mods server while keeping lesson mode quiet.

### Reply Quality Review

The answer-turn quality revision loop was kept as an LLM self-review, not a program rewrite. The change was only to pass more classroom facts into the revision frame:

- current block
- next block
- same-page blocks

This gives the rewriter enough context to avoid phrases like treating same-page movement as a page change. It does not add answer labels, fixed replies, or word lists.

### Stale Page Session Lock

The browser smoke exposed a real history lifecycle bug:

1. The user jumped P24 -> P25 -> P26.
2. The selected page changed while the lesson store was loading.
3. The history store saw loading and skipped `ensureCurrentLessonHistorySession()`.
4. After the lesson finished loading, nothing retried the history rebinding.
5. The active chat session still belonged to the previous page, so the current page looked read-only and the textarea stayed disabled.

Fix: when lesson loading transitions back to false, the history store retries `ensureCurrentLessonHistorySession()`. This does not restart the lesson; it only binds the active chat session to the now-current page/student identity.

### Smoke Script Race

The backend full-suite caught a shell race in `scripts/smoke_lesson_browser.sh`. In keep-server mode the script disowned the backend immediately after starting it. The test stub could finish before writing its env log.

Fix: keep the process in the shell job table until cleanup. Cleanup is still responsible for disowning when `PEPTUTOR_LESSON_SMOKE_KEEP_SERVER=1`.

## Still Not Solved

Teacher replies can still contain generic praise such as `很好` or `完全正确`. I did not add a forbidden-phrase list for this pass. That would make the quality layer look clean while quietly turning into another hidden rule layer.

Better next step: collect real teacher replies from browser smoke and judge them with a small dialogue-quality eval. If a pattern is stable, improve the LLM self-review instruction around "specific confirmation" without injecting replacement wording.

## Follow-up: Answer-Turn Quality Cut

The next pass focused on the answer-turn policy still moving too fast after a low-mastery student gave a hesitant or partial answer.

What changed:

- Added classroom-level policy instructions for question-mark answers, task-title echoes, new-block micro-steps, and role clarity.
- Kept those instructions semantic. No food/drink word lists, no page-specific replies, and no replacement templates were added.
- Added a reply boundary so self-review output that says things like "I rewrote the teacher reply" is rejected instead of spoken to the student.
- Cleaned the policy textbook frame for `extension_task`: task instructions are no longer sent as `examples`, because P49 showed that `Create a personal party shopping list.` is an instruction, not proof that the learner completed the shopping-list activity.
- Updated `scripts/smoke_lesson_turn.py` to follow the current page-overview flow: choose the drink module before testing drink answers, and choose the P49 party-list module before running the stream gold set.

What the tests showed:

- Route smoke now passes with the multi-module entry flow.
- P49 task echo now stays on the party-list task as a repair turn instead of being treated as successful completion.
- Dynamic 10-turn low-mastery student eval improved on "hear child before teaching", but still fails some "one small step" turns. The latest run was 6/10 pass. The remaining issue is not a broken route; it is classroom strategy: after the student finally says a sentence correctly, the policy still sometimes moves into the next task with too much new material in one reply.

Decision:

Do not keep piling on prompt lines for this in the same cut. The next real improvement should be either:

- a stronger dialogue-quality eval that checks "new block first turn must be a micro-step", or
- a smaller policy output contract that separates `statepatch` from `nextteacherquestion` and `entrymicrostep`, so the LLM can advance state without cramming the next lesson into one spoken sentence.

## Validation

- `pytest backend/LightRAG/tests/test_lesson_runtime.py::test_answer_turn_policy_contextual_reply_review_keeps_llm_as_rewriter backend/LightRAG/tests/test_lesson_chat_history_routes.py backend/LightRAG/tests/test_lesson_chat_history_audit.py -q`
- `vitest run packages/stage-ui/src/stores/lesson-chat-history.test.ts`
- `eslint` on touched frontend files
- `ruff check` on touched backend files
- `pnpm -C frontend/airi -F @proj-airi/stage-web typecheck`
- `NO_PROXY=127.0.0.1,localhost,::1 bash scripts/smoke_lesson_browser.sh`
- `pytest backend/LightRAG/tests -q`
- `NO_PROXY=127.0.0.1,localhost,::1 backend/LightRAG/.venv/bin/python scripts/smoke_lesson_turn.py`
- `NO_PROXY=127.0.0.1,localhost,::1 backend/LightRAG/.venv/bin/python scripts/eval_lesson_mili_principles.py --turns 10 --write-report backend/LightRAG/temp/lesson_mili_principles_next_cut_after_smoke_fix.json`

Final state: browser smoke passed; backend full suite passed.
