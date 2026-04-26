# AIRI Lesson Route and LessonPanel Design

## Scope
- add a dedicated `stage-web` lesson route at `/lesson`
- keep the existing `/` chat page unchanged
- reuse the existing `WidgetStage` on the left
- render a PepTutor-specific `LessonPanel` on the right
- connect the panel directly to `POST /lesson/turn`

## Why This Shape
- the current PepTutor backend already exposes a stable lesson turn contract
- the existing AIRI homepage is a general chat surface and should stay isolated from lesson state for now
- the wireframe already assumes a desktop split view with character stage on the left and teaching control panel on the right

## UI Structure
- desktop:
  - left: `WidgetStage`
  - right: `LessonPanel`
- mobile:
  - top: stage
  - bottom: stacked lesson panel

## LessonPanel Sections
- top status strip:
  - current unit/page
  - current block uid
  - runtime activity badge
- start card:
  - page selector for the active pilot pages
  - page uid input
  - start or restart action
- task card:
  - current teacher question or active task
  - retrieval mode
  - teaching action
  - quick lesson facts such as hint level and branch state
- transcript strip:
  - latest learner partial input or manual draft text
- dialogue thread:
  - teacher and learner bubbles derived from lesson turns
- quick actions:
  - hint
  - repeat prompt locally
  - return to lesson
  - restart page
- lesson rhythm card:
  - current page uid
  - current block uid
  - pedagogy level
  - same-goal attempt count

## Data Model
- frontend keeps a dedicated lesson store with:
  - selected page uid
  - student id
  - last `LessonTurnResult`
  - current backend runtime state
  - transcript entries for teacher and learner messages
  - request status and error state

## API Contract
- start lesson:
  - `POST /lesson/turn` with `page_uid` and `student_id`
- continue lesson:
  - `POST /lesson/turn` with `page_uid`, `student_id`, `state`, and `learner_input`

## Non-Goals
- no automatic chat-to-lesson intent detection
- no lesson takeover of the existing `/` chat page
- no Live2D-specific lesson gestures in this slice
- no TTS playback or speech routing changes in this slice

## Validation
- add a focused `stage-ui` store test for lesson start and follow-up turns
- run typecheck in `@proj-airi/stage-ui`, `@proj-airi/stage-layouts`, and `@proj-airi/stage-web`
