import type { ChatProvider } from '@xsai-ext/providers/utils'
import type { Message } from '@xsai/shared-chat'

import type { LessonAiriActionPayload, LessonTurnResult } from '../types/lesson'

import { useCharacterNotebookStore } from './character'
import { useLessonStore } from './lesson'
import { fetchPepTutorBackend } from './peptutor-backend-auth'

const LESSON_CHAT_BASE_URL = 'https://peptutor.lesson.local/v1/'
const LESSON_CHAT_MODEL = 'peptutor-lesson-turn'

function extractContentText(content: Message['content']): string {
  if (typeof content === 'string') {
    return content
  }

  if (!Array.isArray(content)) {
    return ''
  }

  return content
    .map((part) => {
      if (!part || typeof part !== 'object') {
        return ''
      }

      if ('text' in part && typeof part.text === 'string') {
        return part.text
      }

      return ''
    })
    .join('')
}

function extractLatestUserText(messages: Message[]): string {
  for (let index = messages.length - 1; index >= 0; index--) {
    const message = messages[index]
    if (message?.role !== 'user') {
      continue
    }

    const text = extractContentText(message.content).trim()
    if (text) {
      return text
    }
  }

  return ''
}

async function parseChatMessages(body: BodyInit | null | undefined): Promise<Message[]> {
  if (typeof body !== 'string') {
    return []
  }

  const payload = JSON.parse(body) as { messages?: Message[] }
  return Array.isArray(payload.messages) ? payload.messages : []
}

function createSseChunk(text: string, model: string) {
  return {
    id: `peptutor-lesson-${Date.now()}`,
    object: 'chat.completion.chunk',
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [{
      index: 0,
      delta: { content: text },
      finish_reason: null,
    }],
  }
}

function createSseFinish(model: string) {
  return {
    id: `peptutor-lesson-${Date.now()}`,
    object: 'chat.completion.chunk',
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [{
      index: 0,
      delta: {},
      finish_reason: 'stop',
    }],
  }
}

function mirrorLessonTurnToNotebookTranscript(
  result: LessonTurnResult,
  learnerInput: string,
) {
  const notebookMirrorStore = useCharacterNotebookStore()

  // This is a local transcript/debug mirror of the backend result. It is never read back into
  // lesson prompting or backend memory decisions.
  notebookMirrorStore.addTranscriptEntry(
    [
      `PepTutor lesson ${result.state.current_grade} ${result.state.current_semester} ${result.state.current_unit} P${result.state.current_page}.`,
      `Learner: ${learnerInput}`,
      `Teacher: ${result.teacher_response}`,
      result.evaluation ? `Evaluation: ${result.evaluation}.` : '',
      `Action: ${result.teaching_action}.`,
    ].filter(Boolean).join('\n'),
    {
      tags: ['peptutor', 'lesson', result.state.current_page_uid],
      metadata: {
        source: 'lesson-backend-transcript-mirror',
        memoryAuthority: 'backend',
        pageUid: result.state.current_page_uid,
        blockUid: result.state.current_block_uid,
        turnLabel: result.turn_label,
        teachingAction: result.teaching_action,
        evaluation: result.evaluation,
        retrievalMode: result.retrieval_mode,
        simplememContentSessionId: result.state.simplemem_content_session_id,
        simplememMemorySessionId: result.state.simplemem_memory_session_id,
        memoryProject: result.debug_signals?.memory_runtime.project,
        memoryRecallStatus: result.debug_signals?.memory_runtime.last_recall_status,
        memoryRecallSummary: result.debug_signals?.memory_runtime.last_recall_summary,
        memoryWritebackStatus: result.debug_signals?.memory_runtime.last_writeback_status,
        memoryWritebackSummary: result.debug_signals?.memory_runtime.last_writeback_summary,
        memoryDegradationState: result.debug_signals?.memory_runtime.degradation_state,
      },
    },
  )
}

interface LessonBackendSseEvent {
  event: string
  payload: Record<string, unknown>
}

function createActToken(payload: LessonAiriActionPayload): string {
  return `<|ACT ${JSON.stringify(payload)}|>`
}

function enqueueChatChunk(
  controller: ReadableStreamDefaultController<Uint8Array>,
  encoder: TextEncoder,
  text: string,
  model: string,
) {
  controller.enqueue(encoder.encode(`data: ${JSON.stringify(createSseChunk(text, model))}\n\n`))
}

function enqueueChatFinish(
  controller: ReadableStreamDefaultController<Uint8Array>,
  encoder: TextEncoder,
  model: string,
) {
  controller.enqueue(encoder.encode(`data: ${JSON.stringify(createSseFinish(model))}\n\n`))
  controller.enqueue(encoder.encode('data: [DONE]\n\n'))
}

function parseBackendSseBlock(block: string): LessonBackendSseEvent | null {
  let event = 'message'
  const dataLines: string[] = []

  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    }
    else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart())
    }
  }

  if (!dataLines.length) {
    return null
  }

  const data = dataLines.join('\n')
  if (data === '[DONE]') {
    return null
  }

  return {
    event,
    payload: JSON.parse(data) as Record<string, unknown>,
  }
}

async function readBackendSseStream(
  body: ReadableStream<Uint8Array>,
  signal: AbortSignal,
  onEvent: (event: LessonBackendSseEvent) => Promise<void> | void,
) {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n')

      let separatorIndex = buffer.indexOf('\n\n')
      while (separatorIndex >= 0) {
        const block = buffer.slice(0, separatorIndex)
        buffer = buffer.slice(separatorIndex + 2)
        const parsed = parseBackendSseBlock(block)
        if (parsed) {
          await onEvent(parsed)
        }
        separatorIndex = buffer.indexOf('\n\n')
      }
    }

    if (!signal.aborted) {
      buffer += decoder.decode()
      buffer = buffer.replace(/\r\n/g, '\n')
      const parsed = parseBackendSseBlock(buffer.trim())
      if (parsed) {
        await onEvent(parsed)
      }
    }
  }
  finally {
    reader.releaseLock()
  }
}

async function parseLessonStreamError(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { detail?: string, message?: string }
    if (typeof payload.detail === 'string' && payload.detail.trim()) {
      return payload.detail.trim()
    }
    if (typeof payload.message === 'string' && payload.message.trim()) {
      return payload.message.trim()
    }
  }
  catch {
  }

  try {
    const text = await response.text()
    if (text.trim()) {
      return text.trim()
    }
  }
  catch {
  }

  return `Lesson stream request failed (${response.status})`
}

function linkClientAbort(
  clientSignal: AbortSignal | null | undefined,
  onAbort: () => void,
) {
  if (!clientSignal) {
    return () => {}
  }

  if (clientSignal.aborted) {
    onAbort()
    return () => {}
  }

  clientSignal.addEventListener('abort', onAbort, { once: true })
  return () => clientSignal.removeEventListener('abort', onAbort)
}

function eventTurnClientId(payload: Record<string, unknown>): string {
  return typeof payload.turn_client_id === 'string' ? payload.turn_client_id : ''
}

function streamErrorMessage(payload: Record<string, unknown>): string {
  if (typeof payload.detail === 'string' && payload.detail.trim()) {
    return payload.detail.trim()
  }
  if (typeof payload.message === 'string' && payload.message.trim()) {
    return payload.message.trim()
  }
  if (typeof payload.status_code === 'number') {
    return `Lesson stream failed (${payload.status_code})`
  }
  return 'Lesson stream failed'
}

async function ensureLessonStarted(lessonStore: ReturnType<typeof useLessonStore>) {
  if (!lessonStore.hasStarted) {
    await lessonStore.startLesson(lessonStore.selectedPageUid, { replayTeacher: false })
  }
}

function createStreamingLessonChatResponse(
  messages: Message[],
  model: string,
  clientSignal?: AbortSignal | null,
): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const lessonStore = useLessonStore()
      const learnerInput = extractLatestUserText(messages)

      if (!learnerInput) {
        controller.error(new Error('Lesson chat message is empty'))
        return
      }

      let turnClientId = ''
      let cleanupClientAbort = () => {}
      let finished = false

      try {
        await ensureLessonStarted(lessonStore)

        const streamedTurn = lessonStore.beginStreamedTurn(learnerInput)
        turnClientId = streamedTurn.turnClientId
        cleanupClientAbort = linkClientAbort(clientSignal, () => {
          lessonStore.abortActiveTurn('lesson-chat-client-abort')
        })

        if (clientSignal?.aborted || streamedTurn.signal.aborted) {
          controller.close()
          return
        }

        const response = await fetchPepTutorBackend(streamedTurn.url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(streamedTurn.payload),
          signal: streamedTurn.signal,
        })

        if (!response.ok) {
          throw new Error(await parseLessonStreamError(response))
        }

        if (!response.body) {
          throw new Error('Lesson stream response has no body')
        }

        await readBackendSseStream(response.body, streamedTurn.signal, async ({ event, payload }) => {
          const payloadTurnClientId = eventTurnClientId(payload)
          if (payloadTurnClientId && payloadTurnClientId !== turnClientId) {
            return
          }
          if (!lessonStore.isActiveLessonTurn(turnClientId)) {
            return
          }

          if (event === 'action') {
            const { turn_client_id: _turnClientId, ...actionPayload } = payload
            enqueueChatChunk(controller, encoder, createActToken(actionPayload as unknown as LessonAiriActionPayload), model)
            return
          }

          if (event === 'text_delta') {
            if (typeof payload.text === 'string') {
              enqueueChatChunk(controller, encoder, payload.text, model)
            }
            return
          }

          if (event === 'done') {
            const result = payload.result as LessonTurnResult | undefined
            if (!result) {
              throw new Error('Lesson stream done event did not include a result')
            }

            if (lessonStore.applyStreamedTurnResult(turnClientId, result)) {
              mirrorLessonTurnToNotebookTranscript(result, streamedTurn.learnerInput)
            }
            enqueueChatFinish(controller, encoder, model)
            finished = true
            return
          }

          if (event === 'error') {
            throw new Error(streamErrorMessage(payload))
          }
        })

        if (!finished && lessonStore.isActiveLessonTurn(turnClientId)) {
          lessonStore.completeStreamedTurn(turnClientId)
          enqueueChatFinish(controller, encoder, model)
        }

        controller.close()
      }
      catch (error) {
        if (clientSignal?.aborted || (turnClientId && !lessonStore.isActiveLessonTurn(turnClientId))) {
          controller.close()
          return
        }

        const message = error instanceof Error ? error.message : 'Lesson stream failed'
        if (turnClientId) {
          lessonStore.failStreamedTurn(turnClientId, message)
        }
        controller.error(error)
      }
      finally {
        cleanupClientAbort()
      }
    },
  })

  return new Response(stream, {
    status: 200,
    headers: {
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Content-Type': 'text/event-stream; charset=utf-8',
    },
  })
}

export function createPepTutorLessonChatProvider(): ChatProvider {
  return {
    chat(model) {
      return {
        baseURL: LESSON_CHAT_BASE_URL,
        model: model || LESSON_CHAT_MODEL,
        fetch: async (_input: URL, init: RequestInit) => {
          const messages = await parseChatMessages(init.body)
          return createStreamingLessonChatResponse(messages, model || LESSON_CHAT_MODEL, init.signal)
        },
      }
    },
  }
}

export { LESSON_CHAT_MODEL }
