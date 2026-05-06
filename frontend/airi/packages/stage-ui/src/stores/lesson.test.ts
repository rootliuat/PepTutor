import type { LessonTurnResult } from '../types/lesson'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cloneLessonFixture,
  lessonCatalogFixture,
  lessonJsonResponse,
  lessonPersonaDebugSignalFixture,
  lessonTurnP24AnswerFixture,
  lessonTurnP24RestartStartFixture,
  lessonTurnP24StartFixture,
  lessonTurnP25StartFixture,
  lessonTurnP31StartFixture,
} from '../testing/lesson-api-fixtures'
import { useCharacterNotebookStore } from './character'
import { useSharedChatHooks } from './chat/hooks'
import { setLessonApiBaseUrlForTest, useLessonStore } from './lesson'
import { useLessonAiriRuntimeStore } from './lesson-airi-runtime'
import { useSpeechRuntimeStore } from './speech-runtime'

function createLocalStorageMock() {
  const backingStore = new Map<string, string>()

  return {
    getItem(key: string) {
      return backingStore.has(key) ? backingStore.get(key)! : null
    },
    setItem(key: string, value: string) {
      backingStore.set(key, String(value))
    },
    removeItem(key: string) {
      backingStore.delete(key)
    },
    clear() {
      backingStore.clear()
    },
    key(index: number) {
      return [...backingStore.keys()][index] ?? null
    },
    get length() {
      return backingStore.size
    },
  }
}

function mockSpeechRuntimeStore() {
  const speechRuntimeStore = useSpeechRuntimeStore()

  speechRuntimeStore.stopAll = vi.fn()

  return {
    speechRuntimeStore,
  }
}

function mockAiriAssistantOutput() {
  const chatHooks = useSharedChatHooks()
  const literalWrites: string[] = []
  const specialWrites: string[] = []
  const beforeMessageComposed = vi.fn()
  const streamEnd = vi.fn()
  const assistantResponseEnd = vi.fn()

  chatHooks.onBeforeMessageComposed(async (message) => {
    beforeMessageComposed(message)
  })
  chatHooks.onTokenLiteral(async (literal) => {
    literalWrites.push(String(literal ?? ''))
  })
  chatHooks.onTokenSpecial(async (special) => {
    specialWrites.push(String(special ?? ''))
  })
  chatHooks.onStreamEnd(async () => {
    streamEnd()
  })
  chatHooks.onAssistantResponseEnd(async (message) => {
    assistantResponseEnd(message)
  })

  return {
    literalWrites,
    specialWrites,
    beforeMessageComposed,
    streamEnd,
    assistantResponseEnd,
  }
}

function assistantLiteralText(output: { literalWrites: string[] }) {
  return output.literalWrites.join('')
}

function catalogResponse() {
  return lessonJsonResponse(cloneLessonFixture(lessonCatalogFixture))
}

function turnResponse(result: LessonTurnResult) {
  return lessonJsonResponse(cloneLessonFixture(result))
}

function mockLessonTurnFetch(...results: LessonTurnResult[]) {
  const fetchSpy = vi.fn()

  for (const result of results) {
    fetchSpy.mockResolvedValueOnce(turnResponse(result))
  }

  return fetchSpy
}

describe('store lesson', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useSharedChatHooks().clearHooks()
    setLessonApiBaseUrlForTest('http://127.0.0.1:9625')
  })

  afterEach(() => {
    setLessonApiBaseUrlForTest(undefined)
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('falls back to the pilot page list and resets to the first page', () => {
    const store = useLessonStore()

    expect(store.availablePages.map(page => page.value)).toEqual([
      'TB-G5S1U3-P24',
      'TB-G5S1U3-P25',
      'TB-G5S1U3-P26',
      'TB-G5S1U3-P27',
      'TB-G5S1U3-P28',
      'TB-G5S1U3-P29',
      'TB-G5S1U3-P30',
      'TB-G5S1U3-P31',
    ])

    store.setSelectedPageUid('TB-G5S1U3-P31')
    store.resetLessonState()

    expect(store.selectedPageUid).toBe('TB-G5S1U3-P24')
  })

  it('appends streaming learner dictation into the draft input with stable spacing', () => {
    const store = useLessonStore()

    store.setDraftLearnerInput('I think')
    store.appendDraftLearnerInput('  the answer  ')
    store.appendDraftLearnerInput('')
    store.appendDraftLearnerInput('is on page twenty four.')

    expect(store.draftLearnerInput).toBe('I think the answer is on page twenty four.')
  })

  it('loads the lesson catalog from the backend and replaces the fallback page list', async () => {
    const fetchSpy = vi.fn(async () => catalogResponse())

    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    await store.loadCatalog()

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(fetchSpy).toHaveBeenCalledWith('http://127.0.0.1:9625/lesson/catalog', {
      method: 'GET',
      headers: {},
    })
    expect(store.catalogLoaded).toBe(true)
    expect(store.availablePages.map(page => page.value)).toEqual([
      'TB-G5S1U3-P24',
      'TB-G6S1U1-P2',
      'TB-G6S2Recycle2-P49',
      'TB-G6S2Recycle2-P51',
    ])
    expect(store.availablePages[1]).toEqual({
      label: 'G6 S1 U1 · P2',
      value: 'TB-G6S1U1-P2',
      description: 'dialogue · 这一页进入六上第一单元的问路对话。',
    })
    expect(store.availablePages[2]).toEqual({
      label: 'G6 S2 Recycle2 · P49',
      value: 'TB-G6S2Recycle2-P49',
      description: 'phonics · 这一页复习告别派对里的语音分类。',
    })
    expect(store.selectedGrade).toBe('G5')
    expect(store.selectedSemester).toBe('S1')
    expect(store.selectedUnit).toBe('U3')
    expect(store.scopedPages.map(page => page.value)).toEqual(['TB-G5S1U3-P24'])
  })

  it('sends the lesson api key when loading the catalog from a protected backend', async () => {
    vi.stubEnv('VITE_PEPTUTOR_LESSON_API_KEY', 'lesson-api-key')
    const fetchSpy = vi.fn(async () => catalogResponse())

    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    await store.loadCatalog()

    expect(fetchSpy).toHaveBeenCalledWith('http://127.0.0.1:9625/lesson/catalog', {
      method: 'GET',
      headers: {
        'X-API-Key': 'lesson-api-key',
      },
    })
  })

  it('uses the runtime-configured lesson api base when no test override is set', async () => {
    setLessonApiBaseUrlForTest(undefined)
    vi.stubGlobal('__PEPTUTOR_RUNTIME_CONFIG__', {
      VITE_PEPTUTOR_LESSON_API_URL: '/peptutor-api',
    })
    const fetchSpy = vi.fn(async () => catalogResponse())

    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    await store.loadCatalog()

    expect(fetchSpy).toHaveBeenCalledWith('/peptutor-api/lesson/catalog', {
      method: 'GET',
      headers: {},
    })
  })

  it('falls back to the same-origin peptutor proxy when no lesson api base is configured', async () => {
    setLessonApiBaseUrlForTest(undefined)
    vi.stubGlobal('__PEPTUTOR_RUNTIME_CONFIG__', {})
    const fetchSpy = vi.fn(async () => catalogResponse())

    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    await store.loadCatalog()

    expect(fetchSpy).toHaveBeenCalledWith('/peptutor-api/lesson/catalog', {
      method: 'GET',
      headers: {},
    })
  })

  it('switches the active scope and keeps the selected page inside the chosen unit', async () => {
    const fetchSpy = vi.fn(async () => catalogResponse())

    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    await store.loadCatalog()

    await store.selectLessonGrade('G6')

    expect(store.selectedGrade).toBe('G6')
    expect(store.selectedSemester).toBe('S1')
    expect(store.selectedUnit).toBe('U1')
    expect(store.selectedPageUid).toBe('TB-G6S1U1-P2')

    await store.selectLessonSemester('S2')

    expect(store.selectedSemester).toBe('S2')
    expect(store.selectedUnit).toBe('Recycle2')
    expect(store.selectedPageUid).toBe('TB-G6S2Recycle2-P49')
    expect(store.scopedPages.map(page => page.value)).toEqual([
      'TB-G6S2Recycle2-P49',
      'TB-G6S2Recycle2-P51',
    ])

    store.setSelectedPageUid('TB-G6S2Recycle2-P51')

    expect(store.selectedGrade).toBe('G6')
    expect(store.selectedSemester).toBe('S2')
    expect(store.selectedUnit).toBe('Recycle2')
    expect(store.selectedPageUid).toBe('TB-G6S2Recycle2-P51')
  })

  it('restores the last persisted lesson page after loading the backend catalog', async () => {
    const localStorageMock = createLocalStorageMock()
    localStorageMock.setItem('peptutor/lesson/last-page-uid', 'TB-G6S2Recycle2-P51')
    vi.stubGlobal('localStorage', localStorageMock)

    const fetchSpy = vi.fn(async () => catalogResponse())

    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    await store.loadCatalog()

    expect(store.selectedGrade).toBe('G6')
    expect(store.selectedSemester).toBe('S2')
    expect(store.selectedUnit).toBe('Recycle2')
    expect(store.selectedPageUid).toBe('TB-G6S2Recycle2-P51')
  })

  it('keeps the fallback page list when the catalog request fails', async () => {
    const fetchSpy = vi.fn(async () => {
      return new Response(JSON.stringify({
        detail: 'catalog unavailable',
      }), {
        status: 503,
        headers: {
          'Content-Type': 'application/json',
        },
      })
    })

    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    await store.loadCatalog()

    expect(store.catalogLoaded).toBe(false)
    expect(store.availablePages[0]?.value).toBe('TB-G5S1U3-P24')
    expect(store.selectedPageUid).toBe('TB-G5S1U3-P24')
  })

  it('persists the selected lesson page when the user changes scope', async () => {
    const localStorageMock = createLocalStorageMock()
    vi.stubGlobal('localStorage', localStorageMock)

    const fetchSpy = vi.fn(async () => catalogResponse())

    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    await store.loadCatalog()
    await store.selectLessonGrade('G6')
    await store.selectLessonSemester('S2')
    await store.selectLessonPage('TB-G6S2Recycle2-P51')

    expect(localStorageMock.getItem('peptutor/lesson/last-page-uid')).toBe('TB-G6S2Recycle2-P51')
  })

  it('sends the lesson bearer token when starting a lesson against a protected backend', async () => {
    vi.stubEnv('VITE_PEPTUTOR_LESSON_BEARER_TOKEN', 'lesson-jwt')
    const fetchSpy = vi.fn(async () => turnResponse(lessonTurnP24StartFixture))

    vi.stubGlobal('fetch', fetchSpy)
    mockSpeechRuntimeStore()

    const store = useLessonStore()
    await store.startLesson()

    expect(fetchSpy).toHaveBeenCalledWith('http://127.0.0.1:9625/lesson/turn', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer lesson-jwt',
      },
      body: JSON.stringify({
        page_uid: 'TB-G5S1U3-P24',
        student_id: 'demo-student',
      }),
    })
  })

  it('keeps the current valid page when a manual jump requests an unknown page uid', async () => {
    const fetchSpy = vi.fn(async () => catalogResponse())

    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    await store.loadCatalog()
    await store.selectLessonGrade('G6')
    await store.selectLessonSemester('S2')
    await store.selectLessonPage('TB-G6S2Recycle2-P51')
    await store.selectLessonPage('TB-UNKNOWN-P404')

    expect(store.selectedGrade).toBe('G6')
    expect(store.selectedSemester).toBe('S2')
    expect(store.selectedUnit).toBe('Recycle2')
    expect(store.selectedPageUid).toBe('TB-G6S2Recycle2-P51')
  })

  it('starts a lesson session and records the teacher opening', async () => {
    const fetchSpy = mockLessonTurnFetch(lessonTurnP24StartFixture)

    vi.stubGlobal('fetch', fetchSpy)

    const assistantOutput = mockAiriAssistantOutput()
    const store = useLessonStore()
    await store.startLesson('TB-G5S1U3-P24')

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(store.runtimeState?.current_page_uid).toBe('TB-G5S1U3-P24')
    expect(store.transcript).toHaveLength(1)
    expect(store.transcript[0]?.speaker).toBe('teacher')
    expect(store.currentTeacherPrompt).toBe('What would you like to drink?')
    expect(store.activeTurn?.debug_signals).toEqual(lessonTurnP24StartFixture.debug_signals)
    await vi.waitFor(() => {
      expect(assistantLiteralText(assistantOutput)).toBe('这一页练习点餐和饮料表达。Can you say: What would you like to drink?')
    })
    expect(assistantOutput.specialWrites).toHaveLength(1)
    expect(assistantOutput.specialWrites[0]).toContain('<|ACT ')
    expect(assistantOutput.specialWrites[0]).toContain('"teaching_action":"page_intro"')
    expect(assistantOutput.beforeMessageComposed).toHaveBeenCalledWith('lesson-start')
    expect(assistantOutput.streamEnd).toHaveBeenCalledTimes(1)
    expect(assistantOutput.assistantResponseEnd).toHaveBeenCalledWith('这一页练习点餐和饮料表达。Can you say: What would you like to drink?')
  })

  it('replays backend persona performance metadata instead of guessing from the turn label', async () => {
    const startFixture = cloneLessonFixture(lessonTurnP24StartFixture)
    startFixture.debug_signals = {
      ...startFixture.debug_signals!,
      persona: {
        airi_performance: {
          emotion: 'correction',
          motion: 'Explain',
          expression: 'focused',
          speech_style: 'gentle_correction',
          mouth_intensity: 0.7,
          interrupt_policy: 'finish_current_sentence',
          content_source: 'lesson_runtime_teacher_response',
          fallback_allowed: false,
        },
      },
    }

    const fetchSpy = mockLessonTurnFetch(startFixture)
    vi.stubGlobal('fetch', fetchSpy)

    const assistantOutput = mockAiriAssistantOutput()
    const store = useLessonStore()
    const lessonAiriRuntimeStore = useLessonAiriRuntimeStore()
    await store.startLesson('TB-G5S1U3-P24')

    expect(lessonAiriRuntimeStore.currentPerformancePlan).toMatchObject({
      motion: 'Think',
      expression: 'think',
      speechStyle: 'gentle_correction',
      mouthIntensity: 0.7,
      interruptPolicy: 'finish_current_sentence',
      fallbackAllowed: false,
      performanceSource: 'lesson_persona_context',
      turnLabel: 'page_entry',
    })
    await vi.waitFor(() => {
      expect(assistantOutput.specialWrites).toHaveLength(1)
    })
    expect(assistantOutput.specialWrites[0]).toContain('"emotion":{"name":"question","intensity":0.86}')
    expect(assistantOutput.specialWrites[0]).toContain('"motion":"Think"')
    expect(assistantOutput.specialWrites[0]).toContain('"expression":"think"')
    expect(assistantOutput.specialWrites[0]).toContain('"speech_style":"gentle_correction"')
    expect(assistantOutput.specialWrites[0]).toContain('"mouth_intensity":0.7')
    expect(assistantOutput.specialWrites[0]).toContain('"interrupt_policy":"finish_current_sentence"')
    expect(assistantOutput.specialWrites[0]).toContain('"fallback_allowed":false')
    expect(assistantOutput.specialWrites[0]).toContain('"performance_source":"lesson_persona_context"')
  })

  it('restores the active turn persona performance plan from a history snapshot', async () => {
    const startFixture = cloneLessonFixture(lessonTurnP24StartFixture)
    startFixture.debug_signals = {
      ...startFixture.debug_signals!,
      persona: lessonPersonaDebugSignalFixture({
        emotion: 'encouraging',
        motion: 'Encourage',
        expression: 'soft_smile',
        speech_style: 'normal',
        mouth_intensity: 0.75,
        interrupt_policy: 'barge_in_allowed',
        content_source: 'lesson_runtime_teacher_response',
        fallback_allowed: true,
      }),
    }

    const fetchSpy = mockLessonTurnFetch(startFixture)
    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    const lessonAiriRuntimeStore = useLessonAiriRuntimeStore()
    await store.startLesson('TB-G5S1U3-P24', { replayTeacher: false })

    const snapshot = store.exportRuntimeSnapshot()
    lessonAiriRuntimeStore.clearPerformancePlan()
    store.restoreRuntimeSnapshot(snapshot)

    expect(lessonAiriRuntimeStore.currentPerformancePlan).toMatchObject({
      motion: 'Curious',
      expression: 'happy',
      speechStyle: 'normal',
      mouthIntensity: 0.75,
      performanceSource: 'lesson_persona_context',
      turnLabel: 'page_entry',
    })
  })

  it('strips markdown emphasis before replaying teacher speech', async () => {
    const startFixtureWithMarkdown = cloneLessonFixture(lessonTurnP24StartFixture)
    startFixtureWithMarkdown.teacher_response = '先热身：Do you know the word **hungry**?'

    const fetchSpy = mockLessonTurnFetch(startFixtureWithMarkdown)
    vi.stubGlobal('fetch', fetchSpy)

    const assistantOutput = mockAiriAssistantOutput()
    const store = useLessonStore()
    await store.startLesson('TB-G5S1U3-P24')

    await vi.waitFor(() => {
      expect(assistantLiteralText(assistantOutput)).toBe('先热身：Do you know the word hungry?')
    })
  })

  it('uses backend teacher visible segments for transcript display and one-pass replay speech', async () => {
    const startFixtureWithSegments = cloneLessonFixture(lessonTurnP25StartFixture)
    startFixtureWithSegments.teacher_response = '好，那我们开始第一块。\n先看看这个词你认不认识：salad'
    startFixtureWithSegments.teacher_visible_segments = [
      {
        segment_id: 'teacher-visible-1',
        sequence: 0,
        segment_kind: 'ack',
        display_text: '好，那我们开始第一块。',
        tts_text: '好，那我们开始第一块。',
        caption_text: '好，那我们开始第一块。',
        emotion: null,
      },
      {
        segment_id: 'teacher-visible-2',
        sequence: 1,
        segment_kind: 'scaffold',
        display_text: '先看看这个词你认不认识：salad',
        tts_text: '先看看这个词你认不认识：salad',
        caption_text: '先看看这个词你认不认识：salad',
        emotion: null,
      },
    ]

    const fetchSpy = mockLessonTurnFetch(startFixtureWithSegments)
    vi.stubGlobal('fetch', fetchSpy)

    const assistantOutput = mockAiriAssistantOutput()
    const store = useLessonStore()
    await store.startLesson('TB-G5S1U3-P25')

    expect(store.transcript[0]?.segments?.map(segment => segment.display_text)).toEqual([
      '好，那我们开始第一块。',
      '先看看这个词你认不认识：salad',
    ])
    await vi.waitFor(() => {
      expect(assistantLiteralText(assistantOutput)).toBe('好，那我们开始第一块。 先看看这个词你认不认识：salad')
    })
  })

  it('continues a lesson turn and appends learner and teacher transcript entries', async () => {
    const fetchSpy = mockLessonTurnFetch(
      lessonTurnP24StartFixture,
      lessonTurnP24AnswerFixture,
    )

    vi.stubGlobal('fetch', fetchSpy)

    const assistantOutput = mockAiriAssistantOutput()
    const store = useLessonStore()
    await store.startLesson('TB-G5S1U3-P24')
    await store.sendTurn(`I'd like some water.`)

    expect(fetchSpy).toHaveBeenCalledTimes(2)
    expect(store.transcript).toHaveLength(3)
    expect(store.transcript[1]?.speaker).toBe('learner')
    expect(store.transcript[1]?.text).toBe(`I'd like some water.`)
    expect(store.transcript[2]?.speaker).toBe('teacher')
    expect(store.activeTurn?.evaluation).toBe('correct')
    expect(store.runtimeState?.current_block_uid).toBe('TB-G5S1U3-P24-D2')
    expect(store.activeTurn?.debug_signals).toEqual(lessonTurnP24AnswerFixture.debug_signals)
    await vi.waitFor(() => {
      expect(assistantLiteralText(assistantOutput)).toBe('这一页练习点餐和饮料表达。Can you say: What would you like to drink?对了。我们继续：Now say one full drink sentence.')
    })
    expect(assistantOutput.beforeMessageComposed).toHaveBeenNthCalledWith(1, 'lesson-start')
    expect(assistantOutput.beforeMessageComposed).toHaveBeenNthCalledWith(2, 'lesson-turn')
    expect(assistantOutput.specialWrites).toHaveLength(2)
    expect(assistantOutput.specialWrites[1]).toContain('"evaluation":"correct"')
    expect(assistantOutput.streamEnd).toHaveBeenCalledTimes(2)
    expect(assistantOutput.assistantResponseEnd).toHaveBeenCalledTimes(2)
  })

  it('prepares and aborts a streamed lesson turn without using the JSON turn route', async () => {
    const fetchSpy = mockLessonTurnFetch(lessonTurnP24StartFixture)
    vi.stubGlobal('fetch', fetchSpy)

    const { speechRuntimeStore } = mockSpeechRuntimeStore()
    const store = useLessonStore()
    await store.startLesson('TB-G5S1U3-P24', { replayTeacher: false })

    const streamedTurn = store.beginStreamedTurn(`I'd like some water.`)

    expect(streamedTurn.url).toBe('http://127.0.0.1:9625/lesson/turn/stream')
    expect(streamedTurn.payload).toEqual({
      page_uid: 'TB-G5S1U3-P24',
      student_id: 'demo-student',
      learner_input: `I'd like some water.`,
      state: cloneLessonFixture(lessonTurnP24StartFixture.state),
      turn_client_id: streamedTurn.turnClientId,
    })
    expect(store.loading).toBe(true)
    expect(store.activeTurnClientId).toBe(streamedTurn.turnClientId)
    expect(store.transcript.at(-1)).toMatchObject({
      speaker: 'learner',
      text: `I'd like some water.`,
    })

    expect(store.abortActiveTurn('test-abort')).toBe(true)
    expect(streamedTurn.signal.aborted).toBe(true)
    expect(store.loading).toBe(false)
    expect(store.activeTurnClientId).toBeNull()
    expect(speechRuntimeStore.stopAll).toHaveBeenCalledWith('test-abort')
    expect(fetchSpy).toHaveBeenCalledTimes(1)
  })

  it('never sends notebook mirror data back into the lesson turn api contract', async () => {
    const fetchSpy = mockLessonTurnFetch(
      lessonTurnP24StartFixture,
      lessonTurnP24AnswerFixture,
    )

    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    const notebookStore = useCharacterNotebookStore()

    notebookStore.addTranscriptEntry('Poisoned local mirror entry.', {
      metadata: {
        source: 'poisoned-local-notebook',
        memoryAuthority: 'notebook',
        memoryProject: 'poison-project',
        memoryRecallSummary: 'poison recall summary',
        memoryWritebackSummary: 'poison writeback summary',
      },
    })

    await store.startLesson('TB-G5S1U3-P24', { replayTeacher: false })

    notebookStore.addTranscriptEntry('Another poisoned local mirror entry.', {
      metadata: {
        source: 'poisoned-local-notebook-2',
        memoryAuthority: 'notebook',
        memoryProject: 'poison-project-2',
      },
    })

    await store.sendTurn(`I'd like some water.`, { replayTeacher: false })

    const lessonTurnPayload = JSON.parse(String(fetchSpy.mock.calls[1]?.[1]?.body ?? 'null'))

    expect(lessonTurnPayload).toEqual({
      page_uid: 'TB-G5S1U3-P24',
      student_id: 'demo-student',
      learner_input: `I'd like some water.`,
      state: cloneLessonFixture(lessonTurnP24StartFixture.state),
    })
    expect(JSON.stringify(lessonTurnPayload)).not.toContain('poison-project')
    expect(JSON.stringify(lessonTurnPayload)).not.toContain('memoryAuthority')
    expect(store.activeTurn?.debug_signals?.memory_runtime.project).toBe('peptutor-lesson')
    expect(store.activeTurn?.debug_signals?.memory_runtime.last_recall_summary).toBe(
      'Injected buckets: common_mistakes / preferences / stable_preferences. Semantic hits: 1. Prompt summary available.',
    )
  })

  it('starts the final pilot page without changing the request contract', async () => {
    const fetchSpy = mockLessonTurnFetch(lessonTurnP31StartFixture)

    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    await store.startLesson('TB-G5S1U3-P31')

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(fetchSpy.mock.calls[0]?.[1]?.body).toBe(JSON.stringify({
      page_uid: 'TB-G5S1U3-P31',
      student_id: 'demo-student',
    }))
    expect(store.runtimeState?.current_page_uid).toBe('TB-G5S1U3-P31')
    expect(store.currentPageTitle).toBe('G5 S1 U3 · P31')
  })

  it('updates the selected page without requesting a restart before the lesson begins', async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    await store.selectLessonPage('TB-G5S1U3-P25', { restartIfStarted: true })

    expect(fetchSpy).not.toHaveBeenCalled()
    expect(store.selectedPageUid).toBe('TB-G5S1U3-P25')
    expect(store.runtimeState).toBeNull()
  })

  it('restarts the lesson when selecting a different page after the session has started', async () => {
    const fetchSpy = mockLessonTurnFetch(
      lessonTurnP24RestartStartFixture,
      lessonTurnP25StartFixture,
    )

    vi.stubGlobal('fetch', fetchSpy)

    const store = useLessonStore()
    await store.startLesson('TB-G5S1U3-P24')
    await store.selectLessonPage('TB-G5S1U3-P25', { restartIfStarted: true })

    expect(fetchSpy).toHaveBeenCalledTimes(2)
    expect(fetchSpy.mock.calls[1]?.[1]?.body).toBe(JSON.stringify({
      page_uid: 'TB-G5S1U3-P25',
      student_id: 'demo-student',
    }))
    expect(store.selectedPageUid).toBe('TB-G5S1U3-P25')
    expect(store.runtimeState?.current_page_uid).toBe('TB-G5S1U3-P25')
    expect(store.currentPageTitle).toBe('G5 S1 U3 · P25')
    expect(store.transcript).toHaveLength(1)
    expect(store.transcript[0]?.text).toContain('salad')
  })

  it('replays the latest teacher prompt through the AIRI assistant hooks', async () => {
    const assistantOutput = mockAiriAssistantOutput()
    const store = useLessonStore()

    store.repeatTeacherPrompt()
    expect(assistantOutput.beforeMessageComposed).not.toHaveBeenCalled()

    store.transcript.push({
      id: 'teacher-1',
      created_at: Date.now(),
      speaker: 'teacher',
      text: 'Listen again: What would you like to drink?',
      turn_label: 'page_entry',
      teaching_action: 'page_intro',
      retrieval_mode: 'none',
      evaluation: null,
    })

    store.repeatTeacherPrompt()
    await vi.waitFor(() => {
      expect(assistantOutput.streamEnd).toHaveBeenCalledTimes(1)
    })

    expect(store.transcript).toHaveLength(2)
    expect(store.transcript[1]?.local_only).toBe(true)
    expect(store.transcript[1]?.text).toBe('Listen again: What would you like to drink?')
    expect(assistantOutput.beforeMessageComposed).toHaveBeenCalledWith('lesson-repeat')
    expect(assistantLiteralText(assistantOutput)).toBe('Listen again: What would you like to drink?')
    expect(assistantOutput.streamEnd).toHaveBeenCalledTimes(1)
    expect(assistantOutput.assistantResponseEnd).toHaveBeenCalledWith('Listen again: What would you like to drink?')
  })
})
