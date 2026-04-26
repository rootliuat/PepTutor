# AIRI-Standard Lesson Realtime Voice Runtime

Date: 2026-04-24

## Implementation Status

Implemented and validated on 2026-04-24:

- `POST /lesson/turn/stream` exists and emits `meta`, `action`, `text_delta`, `done`, and `error` SSE events.
- `/lesson` chat now consumes backend stream events directly and commits the final `LessonTurnResult` from `done`.
- Backend teacher responses now stream from the lesson responder call site through a request-local sink. Streaming-capable live responders emit `text_delta` as model chunks arrive; deterministic fallback responses emit immediate deltas on the same path.
- Barge-in stops AIRI playback, cancels the active chat speech intent, aborts the active lesson stream, stops store-owned lesson speech playback, and ignores stale turn ids.
- ACT payload parsing now carries `emotion`, `motion`, `expression`, `duration_ms`, `teaching_action`, `evaluation`, and `turn_label`.
- AIRI stage uses explicit classroom states for listening, learner speaking, thinking, teacher speaking, and interrupted.
- Backend fallback `text_delta` chunking preserves English sentence spacing when frontend chat replays the SSE stream.
- Backend AIRI action profiles now cover every current lesson teaching action and answer evaluation.
- Classroom-state reactions now drive both Live2D motion and VRM expression, including a louder learner-speech reaction.
- Teacher mouth movement remains driven by existing AIRI playback/lip-sync; this change did not add student mouth animation.
- Temporary TTS path remains Edge Xiaoxiao (`peptutor-edge-tts` / `zh-CN-XiaoxiaoNeural`); Doubao TTS remains retained for later paid use.

Validation evidence is recorded in `docs/lesson-testing-status.md`.

## Goal

Make `/lesson` feel like AIRI is teaching live, not like a lesson page that plays audio. AIRI stage/runtime remains the user-facing core. PepTutor lesson backend remains the source of truth for textbook page state, evaluation, retrieval, and memory.

## Non-Goals

- Do not import the full general AIRI companion runtime into `/lesson`.
- Do not change lesson pedagogy, retrieval, memory writeback, or catalog semantics.
- Do not implement student mouth animation; mouth sync is for teacher speech playback.
- Do not require Doubao TTS. Edge Xiaoxiao remains the default temporary TTS voice.

## Architecture

`/lesson` uses a narrow adapter between AIRI and PepTutor:

- Student voice input stays in the existing AIRI hearing/transcription path.
- Finished student speech is submitted as a lesson answer.
- Lesson backend returns/streams teacher text plus lesson metadata.
- Frontend converts lesson metadata into AIRI speech, expression, motion, and interruption signals.
- AIRI stage owns playback, lip sync, Live2D/VRM rendering, and visible character state.

## Required Runtime Behavior

- Student stop-to-submit target: about `900ms`.
- Student barge-in-to-teacher-stop target: under `300-500ms`.
- Teacher text-to-first-audio target: under `1.5s` when the first stream segment is available.
- Teacher playback must drive Live2D/VRM mouth movement.
- Teacher playback must stop mouth movement immediately when interrupted.
- Lesson state must not be overwritten by stale responses after interruption.

## Backend Changes

Add a streaming lesson turn contract without changing core lesson logic:

- Keep `POST /lesson/turn` as the stable JSON route.
- Add `POST /lesson/turn/stream` using server-sent events.
- Emit structured events:
  - `event: meta` for request and turn ids.
  - `event: action` for `teaching_action`, `evaluation`, and computed AIRI action metadata.
  - `event: text_delta` for live responder chunks or deterministic fallback response chunks.
  - `event: done` for the final `LessonTurnResult`.
  - `event: error` for validation/runtime failures.
- Wrap async `stream=True` LLM output in `LLMCallLoopRunner.stream_text(...)` and pass it into `LessonResponder`.
- Use a request-local runtime stream sink so `action` metadata and teacher text can leave the backend before the final result object is returned.
- Add a client-provided `turn_client_id`.
- Let frontend abort the HTTP request; server should stop streaming and avoid extra work where possible.
- Frontend must ignore any response whose `turn_client_id` is no longer current.

## Frontend Changes

Use AIRI runtime as the primary experience:

- `LessonRuntimeChatPanel` continues to use the lesson chat provider.
- `lesson-chat-provider` calls the streaming route when available and only falls back to JSON when needed.
- The chat stream emits real `text_delta` from the backend, not fabricated chunks after a full JSON response.
- `ChatArea` barge-in stops AIRI playback and aborts the active lesson stream; store-level active-turn abort also stops lesson speech playback.
- `useLessonAiriRuntimeStore` gains explicit classroom states: `idle`, `listening`, `learner_speaking`, `thinking`, `teacher_speaking`, `interrupted`.
- `Stage.vue` maps those states into AIRI motion/expression while preserving existing speech and lip-sync behavior.

## AIRI Action Mapping

Extend the existing ACT payload from basic emotion to action metadata:

- `emotion`: normalized AIRI emotion name and intensity.
- `motion`: preferred motion group.
- `expression`: preferred VRM expression or Live2D-compatible emotion.
- `duration_ms`: suggested display duration.
- `teaching_action`: lesson teaching action.
- `evaluation`: lesson answer evaluation.
- `reason`: `lesson_turn`, `learner_speaking`, `thinking`, `interrupted`, or `teacher_speaking`.

Fallback rules:

- Missing model motion falls back to `Think` or `Idle`.
- Missing VRM expression falls back to `neutral` or `think`.
- Runtime state-driven actions can temporarily override turn emotion while the student is speaking or teacher is interrupted.

## Testing And Acceptance

Automated checks:

- Backend tests for `POST /lesson/turn/stream` success, validation errors, and SSE event order.
- Backend tests for live responder chunk pass-through and async model stream wrapping.
- Frontend tests for streaming parser, stale turn ignore, cancel/abort behavior, and action mapping.
- Browser smoke for speech chain: listen -> transcript -> auto-send -> backend stream -> AIRI speech -> interrupt.
- Existing lint/typecheck for touched packages.

Visual/device checks:

- After layout-affecting changes, capture Playwright desktop and mobile screenshots and visually inspect overlap, clipping, offscreen elements, abnormal sizing, and mouth/status HUD placement.
- Run real-device checklist with headset/mic before claiming full acceptance.

## Completion Criteria

This work is complete only when:

- Teacher response is driven by backend stream events from the runtime responder path, not local fake splitting after full JSON.
- Barge-in cancels audible teacher playback and prevents stale lesson result application.
- AIRI visibly changes between listening, learner speaking, thinking, teacher speaking, and interrupted states.
- Teacher TTS continues to drive mouth sync on Live2D and VRM.
- Tests, typecheck, lint, browser smoke, screenshots, and manual review results are recorded.
