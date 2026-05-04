import type { EmotionPayload } from '../constants/emotions'

import { createQueue } from '@proj-airi/stream-kit'
import { describe, expect, it, vi } from 'vitest'

import { Emotion } from '../constants/emotions'
import { useEmotionsMessageQueue } from './queues'

describe('useEmotionsMessageQueue', () => {
  it('parses AIRI lesson ACT payloads with emotion, motion, expression, and duration', async () => {
    const received: EmotionPayload[] = []
    const emotionsQueue = createQueue<EmotionPayload>({
      handlers: [
        async (ctx) => {
          received.push(ctx.data)
        },
      ],
    })
    const specialQueue = useEmotionsMessageQueue(emotionsQueue)

    specialQueue.enqueue(`<|ACT ${JSON.stringify({
      emotion: { name: 'happy', intensity: 0.92 },
      motion: 'Happy',
      expression: 'happy',
      duration_ms: 3000,
      reason: 'lesson_turn',
      teaching_action: 'confirm',
      evaluation: 'correct',
      turn_label: 'answer_question',
      speech_style: 'normal',
      mouth_intensity: 0.8,
      interrupt_policy: 'barge_in_allowed',
      content_source: 'lesson_runtime_teacher_response',
      fallback_allowed: true,
      performance_source: 'lesson_persona_context',
      target_role: 'question',
      expected_student_action: 'answer',
      speech_style_tag: 'short_scaffold',
    })}|>`)

    await vi.waitFor(() => {
      expect(received).toHaveLength(1)
    })
    expect(received[0]).toEqual({
      name: Emotion.Happy,
      intensity: 0.92,
      motion: 'Happy',
      expression: 'happy',
      durationMs: 3000,
      reason: 'lesson_turn',
      teachingAction: 'confirm',
      evaluation: 'correct',
      turnLabel: 'answer_question',
      speechStyle: 'normal',
      mouthIntensity: 0.8,
      interruptPolicy: 'barge_in_allowed',
      contentSource: 'lesson_runtime_teacher_response',
      fallbackAllowed: true,
      performanceSource: 'lesson_persona_context',
      targetRole: 'question',
      expectedStudentAction: 'answer',
      speechStyleTag: 'short_scaffold',
    })
  })
})
