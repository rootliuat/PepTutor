# 009 - Lesson Dev Startup and Console Noise Notes

Date: 2026-04-29

## Problem

`scripts/start_lesson_dev.sh` announced the requested frontend URL, but Vite could silently move to another port when 5173 was occupied. In one reproduced run, the script was configured for 5181 but Vite started on 5176.

That made browser validation unreliable: a tester could open the announced URL, an old tab, or the auto-shifted Vite URL and think the current code was broken.

A separate console warning printed the AIRI/Neko Ayaka default persona prompt through vue-i18n HTML-message warnings. This did not mean PepTutor Teacher Kernel was using AIRI's default chat prompt, but it polluted console output and made the teacher-persona boundary harder to audit.

Chrome also reported unnamed form fields in the lesson page. The main student textarea, unit combobox, Page UID input, and Student ID input were functional, but missing `id`/`name` kept the console noisy and weakened accessibility diagnostics.

## Fix

- `start_lesson_dev.sh` now launches stage-web with `pnpm -F @proj-airi/stage-web exec vite --host ... --port ... --strictPort`.
- `start_lesson_dev.bat` uses the same direct Vite invocation and strict port behavior.
- `apps/stage-web/src/modules/i18n.ts` sets `warnHtmlMessage: false`, matching the existing Electron-side i18n posture and stopping the default AIRI persona from being dumped into the browser console.
- The lesson textarea, unit combobox, Page UID input, and Student ID input now expose stable `id`/`name` attributes.

## Validation

- Reproduced the old bug: requested `PEPTUTOR_LESSON_FRONTEND_PORT=5181`, Vite started on 5176.
- Verified the fix: the same command now starts exactly on `http://127.0.0.1:5181/`.
- Browser-tested `/lesson?page_uid=TB-G5S1U3-P24&student_id=codex-start-script-fix-2`.
- Sent `第二块` through the real textarea and received an LLM-backed teacher turn on D3.
- Rechecked browser console: the AIRI default persona warning no longer appears, and the unnamed-form-field issue is gone on the new page.
- `backend/LightRAG/.venv/bin/python -m pytest backend/LightRAG/tests/test_lesson_smoke_scripts.py -q`
- `backend/LightRAG/.venv/bin/ruff check backend/LightRAG/tests/test_lesson_smoke_scripts.py`
- `pnpm -C frontend/airi exec eslint apps/stage-web/src/modules/i18n.ts`
- `pnpm -C frontend/airi -F @proj-airi/stage-web typecheck`
- `NO_PROXY=127.0.0.1,localhost,::1 bash scripts/smoke_lesson_browser.sh`

## Better Long-Term Shape

The startup script should remain strict by default. Auto-shifting ports is convenient for generic Vite apps, but harmful for this project because lesson backend URL, browser tabs, history lease, and remote testing URL all depend on a stable port.

If multiple lesson tabs are open, the UI should keep showing lease/read-only state, but startup should not hide port conflicts. A failed startup is cheaper than debugging the wrong page.
