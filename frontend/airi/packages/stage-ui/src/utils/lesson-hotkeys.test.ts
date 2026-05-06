import { describe, expect, it } from 'vitest'

import {
  isLessonPushToTalkCombo,
  updateLessonPushToTalkModifierState,
} from './lesson-hotkeys'

describe('lesson push-to-talk hotkey', () => {
  it('uses ctrl+shift as the lesson ASR push-to-talk combo', () => {
    expect(isLessonPushToTalkCombo({ ctrlKey: true, shiftKey: true }, { ctrlDown: false, shiftDown: false })).toBe(true)
    expect(isLessonPushToTalkCombo({ ctrlKey: true }, { ctrlDown: false, shiftDown: false })).toBe(false)
    expect(isLessonPushToTalkCombo({ shiftKey: true }, { ctrlDown: false, shiftDown: false })).toBe(false)
  })

  it('tracks split modifier keydown events before both flags appear on the browser event', () => {
    const state = { ctrlDown: false, shiftDown: false }

    updateLessonPushToTalkModifierState(state, { key: 'Control', code: 'ControlLeft' }, true)
    expect(isLessonPushToTalkCombo({}, state)).toBe(false)

    updateLessonPushToTalkModifierState(state, { key: 'Shift', code: 'ShiftLeft' }, true)
    expect(isLessonPushToTalkCombo({}, state)).toBe(true)

    updateLessonPushToTalkModifierState(state, { key: 'Shift', code: 'ShiftLeft' }, false)
    expect(isLessonPushToTalkCombo({}, state)).toBe(false)
  })
})
