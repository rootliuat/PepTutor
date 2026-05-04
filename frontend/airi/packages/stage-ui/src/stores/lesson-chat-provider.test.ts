import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cloneLessonFixture,
  lessonJsonResponse,
  lessonPersonaDebugSignalFixture,
  lessonTurnP24AnswerFixture,
  lessonTurnP24StartFixture,
} from '../testing/lesson-api-fixtures'
import { setLessonApiBaseUrlForTest, useLessonStore } from './lesson'
import { useLessonAiriRuntimeStore } from './lesson-airi-runtime'
import { createPepTutorLessonChatProvider } from './lesson-chat-provider'

function lessonStreamResponse(turnClientId: string, events: string[]) {
  return new Response(events.join(''), {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
    },
  })
}

function sseEvent(event: string, payload: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`
}

function parseChatSseText(text: string) {
  return text
    .trim()
    .split('\n\n')
    .map(block => block.split('\n').find(line => line.startsWith('data: '))?.slice('data: '.length) || '')
    .filter(data => data && data !== '[DONE]')
    .map(data => JSON.parse(data) as { choices: Array<{ delta?: { content?: string }, finish_reason?: string | null }> })
}

function createStreamFetchSpy() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)

    if (url.endsWith('/lesson/turn')) {
      return lessonJsonResponse(cloneLessonFixture(lessonTurnP24StartFixture))
    }

    if (url.endsWith('/lesson/turn/stream')) {
      const body = JSON.parse(String(init?.body ?? '{}')) as { turn_client_id?: string }
      const turnClientId = body.turn_client_id || 'missing-turn-client-id'
      const doneResult = cloneLessonFixture(lessonTurnP24AnswerFixture)
      doneResult.debug_signals = {
        ...doneResult.debug_signals!,
        persona: lessonPersonaDebugSignalFixture({
          emotion: 'joy',
          motion: 'Nod',
          expression: 'soft_smile',
          speech_style: 'normal',
          mouth_intensity: 0.8,
          interrupt_policy: 'barge_in_allowed',
          content_source: 'lesson_runtime_teacher_response',
          fallback_allowed: true,
        }),
      }

      return lessonStreamResponse(turnClientId, [
        sseEvent('meta', {
          turn_client_id: turnClientId,
          page_uid: 'TB-G5S1U3-P24',
        }),
        sseEvent('action', {
          turn_client_id: turnClientId,
          emotion: { name: 'happy', intensity: 0.92 },
          motion: 'Happy',
          expression: 'happy',
          duration_ms: 2800,
          teaching_action: 'confirm',
          evaluation: 'correct',
          reason: 'lesson_turn',
          turn_label: 'answer_question',
          speech_style: 'normal',
          mouth_intensity: 0.8,
          interrupt_policy: 'barge_in_allowed',
          content_source: 'lesson_runtime_teacher_response',
          fallback_allowed: true,
          performance_source: 'lesson_persona_context',
        }),
        sseEvent('text_delta', {
          turn_client_id: turnClientId,
          index: 0,
          text: '对了。',
        }),
        sseEvent('text_delta', {
          turn_client_id: turnClientId,
          index: 1,
          text: '我们继续：Now say one full drink sentence.',
        }),
        sseEvent('done', {
          turn_client_id: turnClientId,
          result: doneResult,
        }),
      ])
    }

    throw new Error(`Unexpected fetch URL: ${url}`)
  })
}

describe('lesson chat provider', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLessonApiBaseUrlForTest('http://127.0.0.1:9625')
  })

  afterEach(() => {
    setLessonApiBaseUrlForTest(undefined)
    vi.unstubAllGlobals()
  })

  it('streams backend lesson SSE into chat chunks and commits the final turn result', async () => {
    const fetchSpy = createStreamFetchSpy()
    vi.stubGlobal('fetch', fetchSpy)

    const lessonStore = useLessonStore()
    await lessonStore.startLesson('TB-G5S1U3-P24', { replayTeacher: false })
    const lessonAiriRuntime = useLessonAiriRuntimeStore()

    const provider = createPepTutorLessonChatProvider().chat('peptutor-lesson-turn')
    const response = await provider.fetch!(new URL('https://peptutor.lesson.local/v1/chat/completions'), {
      method: 'POST',
      body: JSON.stringify({
        messages: [
          {
            role: 'user',
            content: `I'd like some water.`,
          },
        ],
      }),
    })

    const chatChunks = parseChatSseText(await response.text())
    const streamedContent = chatChunks
      .map(chunk => chunk.choices[0]?.delta?.content || '')
      .join('')

    expect(fetchSpy).toHaveBeenCalledTimes(2)
    expect(String(fetchSpy.mock.calls[1]?.[0])).toBe('http://127.0.0.1:9625/lesson/turn/stream')

    const streamPayload = JSON.parse(String(fetchSpy.mock.calls[1]?.[1]?.body ?? '{}'))
    expect(streamPayload.turn_client_id).toMatch(/^lesson-turn-/)
    expect(streamPayload.learner_input).toBe(`I'd like some water.`)
    expect(streamPayload.state).toEqual(cloneLessonFixture(lessonTurnP24StartFixture.state))

    expect(streamedContent).toContain('<|ACT ')
    expect(streamedContent).toContain('"motion":"Happy"')
    expect(streamedContent).toContain('"speech_style":"normal"')
    expect(streamedContent).toContain('"mouth_intensity":0.8')
    expect(streamedContent).toContain('"performance_source":"lesson_persona_context"')
    expect(streamedContent).toContain('对了。我们继续：Now say one full drink sentence.')
    expect(chatChunks.at(-1)?.choices[0]?.finish_reason).toBe('stop')

    expect(lessonStore.activeTurn?.turn_label).toBe('answer_question')
    expect(lessonAiriRuntime.currentPerformancePlan).toMatchObject({
      motion: 'Happy',
      expression: 'happy',
      durationMs: 2800,
      performanceSource: 'lesson_persona_context',
      turnLabel: 'answer_question',
    })
    expect(lessonStore.loading).toBe(false)
    expect(lessonStore.transcript.map(entry => entry.speaker)).toEqual(['teacher', 'learner', 'teacher'])
  })

  it('surfaces backend lesson stream error events in the lesson store', async () => {
    const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/lesson/turn')) {
        return lessonJsonResponse(cloneLessonFixture(lessonTurnP24StartFixture))
      }

      if (url.endsWith('/lesson/turn/stream')) {
        const body = JSON.parse(String(init?.body ?? '{}')) as { turn_client_id?: string }
        const turnClientId = body.turn_client_id || 'missing-turn-client-id'
        return lessonStreamResponse(turnClientId, [
          sseEvent('meta', {
            turn_client_id: turnClientId,
            page_uid: 'TB-G5S1U3-P24',
          }),
          sseEvent('error', {
            turn_client_id: turnClientId,
            status_code: 400,
            detail: 'learner_input is required when state is provided',
          }),
        ])
      }

      throw new Error(`Unexpected fetch URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchSpy)

    const lessonStore = useLessonStore()
    await lessonStore.startLesson('TB-G5S1U3-P24', { replayTeacher: false })

    const provider = createPepTutorLessonChatProvider().chat('peptutor-lesson-turn')
    const response = await provider.fetch!(new URL('https://peptutor.lesson.local/v1/chat/completions'), {
      method: 'POST',
      body: JSON.stringify({
        messages: [
          {
            role: 'user',
            content: `I'd like some water.`,
          },
        ],
      }),
    })

    await expect(response.text()).rejects.toThrow('learner_input is required when state is provided')
    expect(lessonStore.error).toBe('learner_input is required when state is provided')
    expect(lessonStore.loading).toBe(false)
    expect(lessonStore.transcript.at(-1)).toMatchObject({
      speaker: 'system',
      text: 'learner_input is required when state is provided',
    })
  })
})
