import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { Emotion } from '../constants/emotions'
import { useLessonAiriRuntimeStore } from './lesson-airi-runtime'

describe('lesson AIRI runtime store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('keeps the latest backend performance plan available to the stage runtime', () => {
    const store = useLessonAiriRuntimeStore()

    store.applyPerformancePlan({
      name: Emotion.Question,
      intensity: 0.78,
      motion: 'Think',
      expression: 'think',
      durationMs: 3600,
      reason: 'lesson_turn',
      teachingAction: 'hint',
      evaluation: 'unclear',
      turnLabel: 'answer_question',
      speechStyle: 'gentle_correction',
      mouthIntensity: 0.65,
      interruptPolicy: 'finish_current_sentence',
      contentSource: 'lesson_runtime_teacher_response',
      fallbackAllowed: false,
      performanceSource: 'lesson_persona_context',
    })

    expect(store.currentPerformancePlan).toMatchObject({
      emotionName: Emotion.Question,
      emotionIntensity: 0.78,
      motion: 'Think',
      expression: 'think',
      durationMs: 3600,
      reason: 'lesson_turn',
      teachingAction: 'hint',
      evaluation: 'unclear',
      turnLabel: 'answer_question',
      speechStyle: 'gentle_correction',
      mouthIntensity: 0.65,
      interruptPolicy: 'finish_current_sentence',
      contentSource: 'lesson_runtime_teacher_response',
      fallbackAllowed: false,
      performanceSource: 'lesson_persona_context',
    })
    expect(store.currentPerformancePlan?.updatedAt).toBeGreaterThan(0)
    expect(store.currentSpeechStyle).toBe('gentle_correction')
    expect(store.currentMouthIntensity).toBe(0.65)
    expect(store.currentInterruptPolicy).toBe('finish_current_sentence')
    expect(store.canBargeInDuringTeacherSpeech).toBe(false)
  })

  it('defaults to barge-in allowed and clears stale performance on runtime reset', () => {
    const store = useLessonAiriRuntimeStore()

    expect(store.currentSpeechStyle).toBe('normal')
    expect(store.currentMouthIntensity).toBe(1)
    expect(store.currentInterruptPolicy).toBe('barge_in_allowed')
    expect(store.canBargeInDuringTeacherSpeech).toBe(true)

    store.applyPerformancePlan({
      name: Emotion.Happy,
      intensity: 0.92,
      interruptPolicy: 'no_interrupt',
      speechStyle: 'slow_split',
      mouthIntensity: 0.7,
    })
    store.resetRuntimeState()

    expect(store.currentPerformancePlan).toBeNull()
    expect(store.currentSpeechStyle).toBe('normal')
    expect(store.currentMouthIntensity).toBe(1)
    expect(store.currentInterruptPolicy).toBe('barge_in_allowed')
    expect(store.canBargeInDuringTeacherSpeech).toBe(true)
  })
})
