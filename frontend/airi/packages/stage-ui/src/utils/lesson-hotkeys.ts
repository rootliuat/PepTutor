export interface LessonKeyboardEventLike {
  key?: string
  code?: string
  ctrlKey?: boolean
  shiftKey?: boolean
}

export interface LessonPushToTalkModifierState {
  ctrlDown: boolean
  shiftDown: boolean
}

export function isLessonControlKey(event: LessonKeyboardEventLike) {
  return event.key === 'Control' || event.code === 'ControlLeft' || event.code === 'ControlRight'
}

export function isLessonShiftKey(event: LessonKeyboardEventLike) {
  return event.key === 'Shift' || event.code === 'ShiftLeft' || event.code === 'ShiftRight'
}

export function updateLessonPushToTalkModifierState(
  state: LessonPushToTalkModifierState,
  event: LessonKeyboardEventLike,
  pressed: boolean,
) {
  if (isLessonControlKey(event))
    state.ctrlDown = pressed
  if (isLessonShiftKey(event))
    state.shiftDown = pressed
}

export function isLessonPushToTalkCombo(
  event: LessonKeyboardEventLike,
  state: LessonPushToTalkModifierState,
) {
  return Boolean((event.ctrlKey || state.ctrlDown) && (event.shiftKey || state.shiftDown))
}
