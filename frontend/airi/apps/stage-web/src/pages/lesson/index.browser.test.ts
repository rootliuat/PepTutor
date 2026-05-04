import type { LessonTurnDebugSignals, LessonTurnResult } from '@proj-airi/stage-ui/types/lesson'

import html2canvas from 'html2canvas'

import { Emotion } from '@proj-airi/stage-ui/constants/emotions'
import { useChatSessionStore } from '@proj-airi/stage-ui/stores/chat/session-store'
import { setLessonApiBaseUrlForTest, useLessonStore } from '@proj-airi/stage-ui/stores/lesson'
import { useLessonAiriRuntimeStore } from '@proj-airi/stage-ui/stores/lesson-airi-runtime'
import { useLessonChatHistoryStore } from '@proj-airi/stage-ui/stores/lesson-chat-history'
import {
  cloneLessonFixture,
  lessonCatalogSmokeFixture,
  lessonJsonResponse,
  lessonPersonaDebugSignalFixture,
  lessonTurnP24AnswerFixture,
  lessonTurnP24StartFixture,
  lessonTurnP25StartFixture,
} from '@proj-airi/stage-ui/testing/lesson-api-fixtures'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, createApp, h, nextTick, ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'

const mockSettingsStore = {
  stageModelRenderer: ref('mock-renderer'),
  themeColorsHueDynamic: ref(false),
  stageModelSelected: 'mock-model',
  stageModelSelectedUrl: ref('/mock-model.vrm'),
  updateStageModel: vi.fn(async () => {}),
}

const mockAudioDeviceStore = {
  enabled: ref(false),
  selectedAudioInput: ref('mock-mic'),
  stream: ref<MediaStream | null>(null),
  audioInputs: ref([
    {
      label: 'Mock Mic',
      deviceId: 'mock-mic',
    },
  ]),
  askPermission: vi.fn(async () => {}),
  permissionState: ref<'unknown' | 'requesting' | 'granted' | 'denied' | 'unavailable'>('unknown'),
  permissionError: ref(''),
  ensureInputReady: vi.fn(async () => {
    mockAudioDeviceStore.permissionError.value = ''
    mockAudioDeviceStore.permissionState.value = 'requesting'
    await mockAudioDeviceStore.askPermission()
    mockAudioDeviceStore.enabled.value = true
    mockAudioDeviceStore.startStream()
    mockAudioDeviceStore.permissionState.value = 'granted'
    return mockAudioDeviceStore.stream.value
  }),
  startStream: vi.fn(() => {
    mockAudioDeviceStore.stream.value = { id: 'mock-stream' } as MediaStream
  }),
  stopStream: vi.fn(() => {
    mockAudioDeviceStore.enabled.value = false
    mockAudioDeviceStore.stream.value = null
  }),
}

let lastSentenceEndHandler: ((delta: string) => void) | null = null
let lastTranscriptUpdateHandler: ((text: string) => void) | null = null

const mockActiveTranscriptionProvider = ref('browser-web-speech-api')
const mockActiveTranscriptionModel = ref('web-speech-api')
const mockAutoSendEnabled = ref(false)
const mockAutoSendDelay = ref(2000)
const mockHearingConfigured = computed(() => Boolean(mockActiveTranscriptionProvider.value))

const mockHearingStore = {
  activeTranscriptionProvider: mockActiveTranscriptionProvider,
  activeTranscriptionModel: mockActiveTranscriptionModel,
  autoSendEnabled: mockAutoSendEnabled,
  autoSendDelay: mockAutoSendDelay,
  configured: mockHearingConfigured,
}

const mockHearingPipeline = {
  supportsStreamInput: ref(true),
  error: ref(''),
  transcribeForMediaStream: vi.fn(async (_stream: MediaStream, options?: { onTranscriptUpdate?: (text: string) => void, onSentenceEnd?: (delta: string) => void }) => {
    lastTranscriptUpdateHandler = options?.onTranscriptUpdate ?? null
    lastSentenceEndHandler = options?.onSentenceEnd ?? null
  }),
  stopStreamingTranscription: vi.fn(async () => {}),
}

const mockSpeechStore = {
  activeSpeechProvider: ref('browser-speech-api'),
  activeSpeechModel: ref('browser-speech-api'),
  activeSpeechVoiceId: ref('lesson-voice'),
}

function resetLessonBrowserMockStores() {
  mockSettingsStore.stageModelRenderer.value = 'mock-renderer'
  mockSettingsStore.themeColorsHueDynamic.value = false
  mockSettingsStore.stageModelSelected = 'mock-model'
  mockSettingsStore.stageModelSelectedUrl.value = '/mock-model.vrm'
  mockSettingsStore.updateStageModel.mockClear()

  mockAudioDeviceStore.enabled.value = false
  mockAudioDeviceStore.selectedAudioInput.value = 'mock-mic'
  mockAudioDeviceStore.stream.value = null
  mockAudioDeviceStore.askPermission.mockClear()
  mockAudioDeviceStore.permissionState.value = 'unknown'
  mockAudioDeviceStore.permissionError.value = ''
  mockAudioDeviceStore.ensureInputReady.mockClear()
  mockAudioDeviceStore.startStream.mockClear()
  mockAudioDeviceStore.stopStream.mockClear()

  lastSentenceEndHandler = null
  lastTranscriptUpdateHandler = null
  mockHearingStore.activeTranscriptionProvider.value = 'browser-web-speech-api'
  mockHearingStore.activeTranscriptionModel.value = 'web-speech-api'
  mockHearingStore.autoSendEnabled.value = false
  mockHearingStore.autoSendDelay.value = 2000
  mockHearingPipeline.supportsStreamInput.value = true
  mockHearingPipeline.error.value = ''
  mockHearingPipeline.transcribeForMediaStream.mockClear()
  mockHearingPipeline.stopStreamingTranscription.mockClear()

  mockSpeechStore.activeSpeechProvider.value = 'browser-speech-api'
  mockSpeechStore.activeSpeechModel.value = 'browser-speech-api'
  mockSpeechStore.activeSpeechVoiceId.value = 'lesson-voice'
}

function emitMockTranscriptionSentence(delta: string) {
  if (!lastSentenceEndHandler) {
    throw new Error('Expected a lesson hearing sentence handler to be registered')
  }

  lastSentenceEndHandler(delta)
}

function emitMockTranscriptionInterim(text: string) {
  if (!lastTranscriptUpdateHandler) {
    throw new Error('Expected a lesson hearing transcript update handler to be registered')
  }

  lastTranscriptUpdateHandler(text)
}

vi.mock('@proj-airi/stage-layouts/components/Layouts/Header.vue', async () => {
  const { h } = await import('vue')

  return {
    default: {
      name: 'LessonHeaderStub',
      setup: () => () => h('div', { 'data-testid': 'lesson-header-stub' }),
    },
  }
})

vi.mock('@proj-airi/stage-layouts/components/Layouts/MobileHeader.vue', async () => {
  const { h } = await import('vue')

  return {
    default: {
      name: 'LessonMobileHeaderStub',
      setup: () => () => h('div', { 'data-testid': 'lesson-mobile-header-stub' }),
    },
  }
})

vi.mock('@proj-airi/stage-layouts/components/Backgrounds', async () => {
  const { h } = await import('vue')

  return {
    BackgroundProvider: {
      name: 'LessonBackgroundProviderStub',
      setup: (_props: unknown, { slots }: { slots: { default?: () => unknown[] } }) => () =>
        h('div', { 'data-testid': 'lesson-background-provider-stub' }, slots.default?.() as any),
    },
  }
})

vi.mock('@proj-airi/stage-layouts/composables/theme-color', () => ({
  useBackgroundThemeColor: () => ({
    syncBackgroundTheme: vi.fn(),
  }),
}))

vi.mock('@proj-airi/stage-layouts/stores/background', async () => {
  const { ref } = await import('vue')

  const backgroundStore = {
    selectedOption: ref({ id: 'colorful-wave' }),
    sampledColor: ref('#ffffff'),
  }

  return {
    useBackgroundStore: () => backgroundStore,
  }
})

vi.mock('@proj-airi/stage-ui/components/scenes', async () => {
  const { h, onUnmounted, watch } = await import('vue')
  const { useSharedChatHooks } = await import('@proj-airi/stage-ui/stores/chat/hooks')
  const { useLessonAiriRuntimeStore } = await import('@proj-airi/stage-ui/stores/lesson-airi-runtime')
  const { useSpeechRuntimeStore } = await import('@proj-airi/stage-ui/stores/speech-runtime')

  return {
    WidgetStage: {
      name: 'LessonWidgetStageStub',
      setup: () => {
        const chatHooks = useSharedChatHooks()
        const lessonAiriRuntimeStore = useLessonAiriRuntimeStore()
        const speechRuntimeStore = useSpeechRuntimeStore()
        let currentIntent: ReturnType<typeof speechRuntimeStore.openIntent> | null = null
        const cleanups = [
          watch(() => lessonAiriRuntimeStore.currentPerformancePlan?.updatedAt ?? 0, () => {
            const plan = lessonAiriRuntimeStore.currentPerformancePlan
            if (!plan) {
              return
            }

            lessonAiriRuntimeStore.markPerformanceApplied({
              status: plan.expression ? 'fallback' : 'applied',
              requestedMotion: plan.motion,
              appliedMotion: plan.motion,
              requestedExpression: plan.expression,
              appliedExpression: plan.expression ? 'motion-only' : '',
              fallbackReason: plan.expression ? `live2d_expression_unavailable:${plan.expression}` : '',
            })
          }, { immediate: true }),
          chatHooks.onBeforeMessageComposed(async () => {
            currentIntent?.cancel('new-message')
            currentIntent = speechRuntimeStore.openIntent({
              ownerId: 'lesson',
              priority: 'normal',
              behavior: 'interrupt',
            })
          }),
          chatHooks.onTokenLiteral(async (literal) => {
            currentIntent?.writeLiteral(literal)
          }),
          chatHooks.onTokenSpecial(async (special) => {
            currentIntent?.writeSpecial(special)
          }),
          chatHooks.onStreamEnd(async () => {
            currentIntent?.writeFlush()
          }),
          chatHooks.onAssistantResponseEnd(async () => {
            currentIntent?.end()
            currentIntent = null
          }),
        ]

        onUnmounted(() => {
          cleanups.forEach(cleanup => cleanup())
          currentIntent?.cancel('stage-unmount')
          currentIntent = null
        })

        return () => h('div', { 'data-testid': 'lesson-widget-stage-stub' })
      },
    },
  }
})

vi.mock('@proj-airi/stage-layouts/components/Widgets/IndicatorMicVolume.vue', async () => {
  const { h } = await import('vue')

  return {
    default: {
      name: 'LessonIndicatorMicVolumeStub',
      setup: () => () => h('div', { 'data-testid': 'lesson-indicator-mic-volume-stub' }),
    },
  }
})

vi.mock('@proj-airi/stage-ui/stores/provider-env-bootstrap', () => ({
  bootstrapPepTutorVoiceEnvDefaults: vi.fn(async () => {}),
}))

vi.mock('@proj-airi/stage-ui/stores/peptutor-backend-auth', () => ({
  bootstrapPepTutorBackendAuth: vi.fn(async () => undefined),
  fetchPepTutorBackend: vi.fn(async (input: string | URL, init?: RequestInit) => fetch(input, init)),
}))

vi.mock('@proj-airi/stage-ui/stores/lesson-voice-hearing-fallback', () => ({
  ensureLessonHearingFallbackProvider: vi.fn(async () => true),
  isLessonHearingFallbackSupported: vi.fn(() => true),
}))

vi.mock('@proj-airi/stage-ui/stores/lesson-voice-speech-fallback', () => ({
  ensureLessonSpeechFallbackProvider: vi.fn(async () => true),
}))

vi.mock('@proj-airi/stage-ui/stores/settings', async () => {
  return {
    useSettings: () => mockSettingsStore,
    useSettingsAudioDevice: () => mockAudioDeviceStore,
  }
})

vi.mock('@proj-airi/stage-ui/stores/modules/hearing', async () => {
  return {
    useHearingStore: () => mockHearingStore,
    useHearingSpeechInputPipeline: () => mockHearingPipeline,
  }
})

vi.mock('@proj-airi/stage-ui/stores/modules/speech', async () => {
  return {
    useSpeechStore: () => mockSpeechStore,
  }
})

async function flushUi(cycles: number = 4) {
  for (let index = 0; index < cycles; index += 1) {
    await Promise.resolve()
    await nextTick()
  }
}

const useRealLessonBackend = import.meta.env.VITE_PEPTUTOR_LESSON_REAL_BACKEND_SMOKE === '1'
const expectRealLessonDebugSignals = import.meta.env.VITE_PEPTUTOR_LESSON_EXPECT_DEBUG_SIGNALS === '1'
const lessonApiBaseUrl = import.meta.env.VITE_PEPTUTOR_LESSON_REAL_BACKEND_URL || 'http://127.0.0.1:9625'
const describeMockSmoke = useRealLessonBackend ? describe.skip : describe
const describeRealSmoke = useRealLessonBackend ? describe : describe.skip
const itRealDebugSmoke = expectRealLessonDebugSignals ? it : it.skip

function positiveIntegerEnv(raw: string | undefined, fallback: number): number {
  const value = Number.parseInt(raw || '', 10)
  return Number.isFinite(value) && value > 0 ? value : fallback
}

const smokeWaitTimeoutMs = useRealLessonBackend
  ? positiveIntegerEnv(import.meta.env.VITE_PEPTUTOR_LESSON_SMOKE_WAIT_TIMEOUT_MS, 30_000)
  : 5_000
const smokeTestTimeoutMs = useRealLessonBackend
  ? positiveIntegerEnv(import.meta.env.VITE_PEPTUTOR_LESSON_SMOKE_TEST_TIMEOUT_MS, 90_000)
  : 10_000

function lastTeacherTranscriptText(lessonStore: ReturnType<typeof useLessonStore>) {
  return [...lessonStore.transcript]
    .reverse()
    .find(entry => entry.speaker === 'teacher')
    ?.text
    ?.trim() || ''
}

function expectRealTeacherResponse(teacherResponse: string) {
  expect(teacherResponse.length).toBeGreaterThanOrEqual(8)
  expect(/[A-Z\u4E00-\u9FFF]/i.test(teacherResponse)).toBe(true)
}

function logRealSmokeObservation(testName: string, startedAtMs: number, teacherResponse: string) {
  console.info(`[lesson-real-smoke] ${JSON.stringify({
    test: testName,
    duration_ms: Date.now() - startedAtMs,
    teacher_response: teacherResponse,
  })}`)
}

function logRealDebugSignalsObservation(testName: string, debugSignals: LessonTurnDebugSignals) {
  console.info(`[lesson-real-debug-signals] ${JSON.stringify({
    test: testName,
    debug_signals: debugSignals,
  })}`)
}

async function captureArtifactScreenshot(): Promise<{ data_url?: string, error?: string }> {
  try {
    const canvas = await html2canvas(document.body, {
      backgroundColor: '#ffffff',
      logging: false,
      scale: 0.5,
      useCORS: true,
    })
    return { data_url: canvas.toDataURL('image/png') }
  }
  catch (error) {
    return { error: error instanceof Error ? error.message : String(error) }
  }
}

async function logRealArtifactSnapshot(testName: string, pinia: ReturnType<typeof createPinia>) {
  const lessonChatHistoryStore = useLessonChatHistoryStore(pinia)
  const chatSessionStore = useChatSessionStore(pinia)
  const screenshot = await captureArtifactScreenshot()
  const networkEntries = performance.getEntriesByType('resource')
    .slice(-40)
    .map((entry) => {
      const resource = entry as PerformanceResourceTiming
      return {
        name: resource.name,
        initiator_type: resource.initiatorType || '',
        duration_ms: Math.round(resource.duration),
        transfer_size: resource.transferSize || 0,
      }
    })
  console.info(`[lesson-real-artifacts] ${JSON.stringify({
    test: testName,
    network_entries: networkEntries,
    history_debug: {
      active_session_id: chatSessionStore.activeSessionId || '',
      active_lesson_tab_writable: lessonChatHistoryStore.activeLessonTabWritable,
      active_history_read_only: lessonChatHistoryStore.activeHistoryReadOnly,
      history_safety_session_count: Object.keys(lessonChatHistoryStore.historySafetyBySessionId).length,
    },
    dom_snapshot: {
      text_chars: textContent().length,
      has_lesson_sidebar: textContent().includes('重新开始'),
    },
    screenshot: {
      format: 'png',
      data_url: screenshot.data_url || '',
      error: screenshot.error || '',
    },
  })}`)
}

function textContent() {
  return document.body.textContent || ''
}

function queryRequiredElement<T extends Element>(selector: string): T {
  const element = document.querySelector(selector)
  if (!element) {
    throw new Error(`Expected element for selector "${selector}"`)
  }

  return element as T
}

function queryPageUidInput(): HTMLInputElement {
  const input = [...document.querySelectorAll('input')]
    .find((candidate): candidate is HTMLInputElement => {
      if (!(candidate instanceof HTMLInputElement)) {
        return false
      }

      const value = candidate.value.trim()
      const placeholder = candidate.getAttribute('placeholder')?.trim() || ''
      return value.startsWith('TB-') || placeholder.startsWith('TB-')
    })

  if (!input) {
    throw new Error('Expected Page UID input')
  }

  return input
}

function queryButton(label: string): HTMLButtonElement {
  const button = [...document.querySelectorAll('button')]
    .find((candidate): candidate is HTMLButtonElement => {
      if (!(candidate instanceof HTMLButtonElement)) {
        return false
      }

      const text = candidate.textContent?.trim() || ''
      const ariaLabel = candidate.getAttribute('aria-label')?.trim() || ''
      const title = candidate.getAttribute('title')?.trim() || ''
      return text === label || ariaLabel === label || title === label
    })

  if (!button) {
    throw new Error(`Expected button "${label}"`)
  }

  return button
}

function clickButton(label: string) {
  queryButton(label).click()
}

async function openLessonMicrophone() {
  clickButton('麦克风')
  await flushUi()
}

async function stopLessonMicrophone() {
  clickButton('停止听写')
  await flushUi()
}

function clickRadioTab(label: string) {
  const radio = [...document.querySelectorAll('[role="radio"]')]
    .find((candidate): candidate is HTMLElement =>
      candidate instanceof HTMLElement && candidate.getAttribute('aria-label')?.trim() === label,
    )

  if (!radio) {
    throw new Error(`Expected radio tab "${label}"`)
  }

  radio.click()
}

function queryDebugSignalStatus(key: string): string {
  return queryRequiredElement<HTMLElement>(`[data-testid="lesson-debug-signal-status-${key}"]`).textContent?.trim() || ''
}

function queryDebugSignalDetail(key: string): string {
  return queryRequiredElement<HTMLElement>(`[data-testid="lesson-debug-signal-detail-${key}"]`).textContent?.trim() || ''
}

function queryMemoryDebugValue(key: string): string {
  return queryRequiredElement<HTMLElement>(`[data-testid="lesson-memory-debug-value-${key}"]`).textContent?.trim() || ''
}

function queryMemoryDebugStatus(key: string): string {
  return queryRequiredElement<HTMLElement>(`[data-testid="lesson-memory-debug-status-${key}"]`).textContent?.trim() || ''
}

function queryMemoryDebugDetail(key: string): string {
  return queryRequiredElement<HTMLElement>(`[data-testid="lesson-memory-debug-detail-${key}"]`).textContent?.trim() || ''
}

function queryRuntimeFact(key: string): string {
  return queryRequiredElement<HTMLElement>(`[data-testid="lesson-runtime-fact-${key}"]`).textContent?.trim() || ''
}

function queryAiriVisibleState(): string {
  return queryRequiredElement<HTMLElement>('[data-testid="lesson-airi-visible-state"]').textContent?.trim() || ''
}

function queryAiriTeachingStance(): string {
  return queryRequiredElement<HTMLElement>('[data-testid="lesson-airi-teaching-stance"]').textContent?.trim() || ''
}

function queryAiriVisibleFact(key: string): string {
  return queryRequiredElement<HTMLElement>(`[data-testid="lesson-airi-visible-fact-${key}"]`).textContent?.trim() || ''
}

function queryRuntimeStatusLabel(): string {
  return queryRequiredElement<HTMLElement>('[data-testid="lesson-runtime-status-label"]').textContent?.trim() || ''
}

function queryRuntimeStatusDetail(): string {
  return queryRequiredElement<HTMLElement>('[data-testid="lesson-runtime-status-detail"]').textContent?.trim() || ''
}

function queryRuntimeCurrentDevice(): string {
  return queryRequiredElement<HTMLElement>('[data-testid="lesson-runtime-current-device"]').textContent?.trim() || ''
}

function queryRuntimeLiveTranscript(): string {
  return queryRequiredElement<HTMLElement>('[data-testid="lesson-runtime-live-transcript"]').textContent?.trim() || ''
}

function queryChatStatusLabel(): string {
  return queryRequiredElement<HTMLElement>('[data-testid="lesson-chat-status-label"]').textContent?.trim() || ''
}

function queryChatStatusDetail(): string {
  return queryRequiredElement<HTMLElement>('[data-testid="lesson-chat-status-detail"]').textContent?.trim() || ''
}

function queryOptionalElement<T extends Element>(selector: string): T | null {
  const element = document.querySelector(selector)
  return element instanceof Element ? element as T : null
}

function setControlValue(element: HTMLInputElement | HTMLTextAreaElement, value: string) {
  element.value = value
  element.dispatchEvent(new Event('input', { bubbles: true }))
  element.dispatchEvent(new Event('change', { bubbles: true }))
}

function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })

  return {
    promise,
    resolve,
    reject,
  }
}

function spyOnLessonSpeechRuntime(speechRuntimeStore: {
  stopByOwner: (ownerId: string, reason?: string) => void
  openIntent: (options?: { ownerId?: string, priority?: string | number, behavior?: string }) => {
    writeLiteral: (text: string) => void
    writeFlush: () => void
    end: () => void
  }
}) {
  const originalStopByOwner = speechRuntimeStore.stopByOwner.bind(speechRuntimeStore)
  const originalOpenIntent = speechRuntimeStore.openIntent.bind(speechRuntimeStore)
  const literalWrites: string[] = []
  let flushCount = 0
  let endCount = 0

  const stopByOwnerSpy = vi.fn((ownerId: string, reason?: string) => {
    originalStopByOwner(ownerId, reason)
  })
  const openIntentSpy = vi.fn((options?: { ownerId?: string, priority?: string | number, behavior?: string }) => {
    const intent = originalOpenIntent(options)
    const originalWriteLiteral = intent.writeLiteral.bind(intent)
    const originalWriteFlush = intent.writeFlush.bind(intent)
    const originalEnd = intent.end.bind(intent)

    intent.writeLiteral = ((text: string) => {
      literalWrites.push(String(text ?? ''))
      originalWriteLiteral(text)
    }) as typeof intent.writeLiteral
    intent.writeFlush = (() => {
      flushCount += 1
      originalWriteFlush()
    }) as typeof intent.writeFlush
    intent.end = (() => {
      endCount += 1
      originalEnd()
    }) as typeof intent.end

    return intent
  })

  speechRuntimeStore.stopByOwner = stopByOwnerSpy
  speechRuntimeStore.openIntent = openIntentSpy

  return {
    stopByOwnerSpy,
    openIntentSpy,
    literalWrites,
    get flushCount() {
      return flushCount
    },
    get endCount() {
      return endCount
    },
  }
}

function attachLessonPlaybackControllerSpy(speechRuntimeStore: {
  registerPlaybackController: (controller: { stopAll?: (reason: string) => void, stopByOwner?: (ownerId: string, reason: string) => void }) => void
}, options: {
  onStopAll?: (reason: string) => void
  onStopByOwner?: (ownerId: string, reason: string) => void
} = {}) {
  const stopAllSpy = vi.fn()
  const stopByOwnerSpy = vi.fn()

  speechRuntimeStore.registerPlaybackController({
    stopAll: (reason: string) => {
      stopAllSpy(reason)
      options.onStopAll?.(reason)
    },
    stopByOwner: (ownerId: string, reason: string) => {
      stopByOwnerSpy(ownerId, reason)
      options.onStopByOwner?.(ownerId, reason)
    },
  })

  return {
    stopAllSpy,
    stopByOwnerSpy,
  }
}

function installLessonApiMock(turnResults: Array<typeof lessonTurnP24StartFixture>) {
  const queuedTurnResults = turnResults.map(result => cloneLessonFixture(result))
  const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)

    if (url.endsWith('/lesson/catalog')) {
      return lessonJsonResponse(cloneLessonFixture(lessonCatalogSmokeFixture))
    }

    if (url.endsWith('/lesson/turn')) {
      const nextResult = queuedTurnResults.shift()
      if (!nextResult) {
        throw new Error(`Unexpected extra lesson turn request: ${JSON.stringify(init?.body || null)}`)
      }

      return lessonJsonResponse(nextResult)
    }

    if (url.endsWith('/lesson/turn/stream')) {
      const nextResult = queuedTurnResults.shift()
      if (!nextResult) {
        throw new Error(`Unexpected extra lesson stream turn request: ${JSON.stringify(init?.body || null)}`)
      }

      const requestPayload = JSON.parse(String(init?.body || '{}')) as { turn_client_id?: string }
      return lessonTurnStreamResponse(nextResult, requestPayload.turn_client_id || 'browser-test-turn')
    }

    throw new Error(`Unexpected fetch request: ${url}`)
  })

  vi.stubGlobal('fetch', fetchSpy)
  return fetchSpy
}

function lessonTurnStreamResponse(result: LessonTurnResult, turnClientId: string) {
  const event = (name: string, payload: unknown) => `event: ${name}\ndata: ${JSON.stringify(payload)}\n\n`
  const action = {
    emotion: result.evaluation === 'correct'
      ? { name: 'happy', intensity: 0.92 }
      : { name: 'curious', intensity: 0.76 },
    motion: result.evaluation === 'correct' ? 'Happy' : 'Curious',
    expression: result.evaluation === 'correct' ? 'happy' : 'think',
    duration_ms: 3000,
    teaching_action: result.teaching_action,
    evaluation: result.evaluation,
    reason: 'lesson_turn',
    turn_label: result.turn_label,
  }

  return new Response([
    event('meta', {
      turn_client_id: turnClientId,
      page_uid: result.page_uid,
    }),
    event('action', {
      turn_client_id: turnClientId,
      ...action,
    }),
    event('text_delta', {
      turn_client_id: turnClientId,
      index: 0,
      text: result.teacher_response,
    }),
    event('done', {
      turn_client_id: turnClientId,
      result,
    }),
  ].join(''), {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
    },
  })
}

function parseLessonTurnStreamDoneResult(text: string): LessonTurnResult | null {
  for (const block of text.trim().split(/\n{2,}/)) {
    let eventName = 'message'
    const dataLines: string[] = []

    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) {
        eventName = line.slice('event:'.length).trim()
      }
      else if (line.startsWith('data:')) {
        dataLines.push(line.slice('data:'.length).trimStart())
      }
    }

    if (eventName !== 'done' || !dataLines.length) {
      continue
    }

    const payload = JSON.parse(dataLines.join('\n')) as { result?: LessonTurnResult }
    return payload.result || null
  }

  return null
}

function installRealLessonApiCapture() {
  const originalFetch = globalThis.fetch.bind(globalThis)
  const capturedTurnResults: LessonTurnResult[] = []
  const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await originalFetch(input, init)
    const url = String(input)

    if (url.endsWith('/lesson/turn')) {
      const payload = await response.clone().json() as LessonTurnResult
      capturedTurnResults.push(payload)
    }
    else if (url.endsWith('/lesson/turn/stream')) {
      void response.clone().text().then((text) => {
        const payload = parseLessonTurnStreamDoneResult(text)
        if (payload) {
          capturedTurnResults.push(payload)
        }
      })
    }

    return response
  })

  vi.stubGlobal('fetch', fetchSpy as typeof fetch)

  return {
    fetchSpy,
    capturedTurnResults,
  }
}

function buildPageEntryFixture(overrides: {
  pageUid: string
  blockUid: string
  grade: string
  semester: string
  unit: string
  page: number
  pageType: string
  teacherResponse: string
  lastTeacherQuestion: string
}): LessonTurnResult {
  const fixture = cloneLessonFixture(lessonTurnP24StartFixture)
  fixture.page_uid = overrides.pageUid
  fixture.block_uid = overrides.blockUid
  fixture.teacher_response = overrides.teacherResponse
  fixture.state.current_grade = overrides.grade
  fixture.state.current_semester = overrides.semester
  fixture.state.current_unit = overrides.unit
  fixture.state.current_page = overrides.page
  fixture.state.current_page_uid = overrides.pageUid
  fixture.state.current_page_type = overrides.pageType
  fixture.state.current_block_uid = overrides.blockUid
  fixture.state.last_teacher_question = overrides.lastTeacherQuestion
  fixture.retrieved_block_uids = []
  return fixture
}

const lessonTurnG6S2Recycle2P49StartFixture = buildPageEntryFixture({
  pageUid: 'TB-G6S2Recycle2-P49',
  blockUid: 'TB-G6S2Recycle2-P49-D1',
  grade: 'G6',
  semester: 'S2',
  unit: 'Recycle2',
  page: 49,
  pageType: 'phonics',
  teacherResponse: '这一页复习告别派对里的语音分类。Let us sort the sounds together.',
  lastTeacherQuestion: 'Can you sort the sounds?',
})

const lessonTurnG6S1U1P2StartFixture = buildPageEntryFixture({
  pageUid: 'TB-G6S1U1-P2',
  blockUid: 'TB-G6S1U1-P2-D1',
  grade: 'G6',
  semester: 'S1',
  unit: 'U1',
  page: 2,
  pageType: 'dialogue',
  teacherResponse: '这一页进入六上第一单元的问路对话。Can you ask: Where is the museum?',
  lastTeacherQuestion: 'Where is the museum?',
})

const lessonTurnP24AnswerMemoryDegradedFixture = (() => {
  const fixture = cloneLessonFixture(lessonTurnP24AnswerFixture)
  if (!fixture.debug_signals) {
    throw new Error('Expected lessonTurnP24AnswerFixture to include debug_signals')
  }

  fixture.debug_signals.memory_runtime = {
    student_id: 'demo-student',
    project: 'peptutor-lesson',
    memory_session_id: 'memory-session-p24',
    last_recall_status: 'degraded',
    last_recall_summary: 'Learner-memory recall failed; continuing without backend injection.',
    last_writeback_status: 'degraded',
    last_writeback_summary: 'Backend learner-memory writeback failed for this turn.',
    degradation_state: 'recall_and_writeback_degraded',
  }

  return fixture
})()

function livePromptsDetail(debugSignals: LessonTurnDebugSignals): string {
  return debugSignals.live_prompts.enabled
    ? '本轮 teacher 响应走了 live planner / responder。'
    : '本轮没有走 live prompts。'
}

function promptMemoryDetail(debugSignals: LessonTurnDebugSignals): string {
  return debugSignals.prompt_memory.injected_buckets.length > 0
    ? `注入：${debugSignals.prompt_memory.injected_buckets.join(' / ')}`
    : '当前没有注入 memory bucket。'
}

function memoryStatusLabel(status: 'success' | 'skipped' | 'degraded'): string {
  switch (status) {
    case 'success':
      return '成功'
    case 'degraded':
      return '降级'
    case 'skipped':
    default:
      return '跳过'
  }
}

function memoryDegradationLabel(
  state: LessonTurnDebugSignals['memory_runtime']['degradation_state'],
): string {
  switch (state) {
    case 'healthy':
      return '正常'
    case 'idle':
      return '待机'
    case 'memory_disabled':
      return '已关闭'
    case 'session_degraded':
      return '会话异常'
    case 'recall_degraded':
      return '召回降级'
    case 'writeback_degraded':
      return '写回降级'
    case 'recall_and_writeback_degraded':
      return '召回/写回降级'
    default:
      return state
  }
}

function expectRenderedMemoryDebug(debugSignals: LessonTurnDebugSignals) {
  expect(queryMemoryDebugValue('student_id')).toBe(debugSignals.memory_runtime.student_id)
  expect(queryMemoryDebugValue('project')).toBe(debugSignals.memory_runtime.project)
  expect(queryMemoryDebugValue('memory_session_id')).toBe(debugSignals.memory_runtime.memory_session_id || '未建立')
  expect(queryMemoryDebugValue('degradation_state')).toBe(memoryDegradationLabel(debugSignals.memory_runtime.degradation_state))
  expect(queryMemoryDebugStatus('recall')).toBe(memoryStatusLabel(debugSignals.memory_runtime.last_recall_status))
  expect(queryMemoryDebugDetail('recall')).toBe(debugSignals.memory_runtime.last_recall_summary)
  expect(queryMemoryDebugStatus('writeback')).toBe(memoryStatusLabel(debugSignals.memory_runtime.last_writeback_status))
  expect(queryMemoryDebugDetail('writeback')).toBe(debugSignals.memory_runtime.last_writeback_summary)
}

function expectRenderedDebugSignals(debugSignals: LessonTurnDebugSignals) {
  expect(queryDebugSignalStatus('live_prompts')).toBe(debugSignals.live_prompts.enabled ? '开启' : '关闭')
  expect(queryDebugSignalDetail('live_prompts')).toBe(livePromptsDetail(debugSignals))
  expect(queryDebugSignalStatus('prompt_memory')).toBe(debugSignals.prompt_memory.enabled ? '开启' : '关闭')
  expect(queryDebugSignalDetail('prompt_memory')).toBe(promptMemoryDetail(debugSignals))
  expectRenderedMemoryDebug(debugSignals)
  expectRenderedReplyPath(debugSignals)
}

function expectedReplyPathLabel(debugSignals: LessonTurnDebugSignals): string | null {
  const audit = debugSignals.response_audit
  if (!audit) {
    return null
  }

  const latencyLabel = Number.isFinite(audit.latency_ms)
    ? ` · ${audit.latency_ms}ms`
    : ''
  const routeLabel = audit.route ? ` · ${audit.route}` : ''
  const auditFacts = `llm=${audit.llm_called ? 'true' : 'false'} · fallback=${audit.fallback_used ? 'true' : 'false'}${latencyLabel}${routeLabel}`
  const repairLabel = audit.repair_reason && audit.repair_reason !== 'none'
    ? ` · repair=${audit.repair_reason}`
    : ''

  if (audit.fallback_used || audit.source === 'fallback') {
    return `fallback · ${auditFacts} · ${audit.fallback_reason || 'unknown'}`
  }
  if (audit.source === 'policy_repaired') {
    return `policy_repaired · ${auditFacts}${repairLabel}`
  }
  if (audit.source === 'policy') {
    return `policy · ${auditFacts}`
  }
  if (audit.source === 'llm_repaired') {
    return `llm_repaired · ${auditFacts}${repairLabel}`
  }
  if (audit.source === 'llm') {
    return `llm · ${auditFacts}`
  }
  if (audit.source === 'deterministic') {
    return `deterministic · ${auditFacts}`
  }

  return null
}

function expectRenderedReplyPath(debugSignals: LessonTurnDebugSignals) {
  const expected = expectedReplyPathLabel(debugSignals)
  if (!expected) {
    return
  }

  expect(queryAiriVisibleFact('reply_path')).toBe(expected)
}

async function mountLessonPage(
  initialPath: string = '/lesson?page_uid=TB-G5S1U3-P24',
  options: {
    beforeMount?: (deps: {
      pinia: ReturnType<typeof createPinia>
      speechRuntimeStore: any
    }) => void
  } = {},
) {
  const { default: LessonScenePage } = await import('../../testing/LessonScenePageHarness.vue')
  const { useSpeechRuntimeStore: useSharedSpeechRuntimeStore } = await import('@proj-airi/stage-ui/stores/speech-runtime')
  const pinia = createPinia()
  const speechRuntimeStore = useSharedSpeechRuntimeStore(pinia)

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/',
        redirect: '/lesson',
      },
      {
        path: '/lesson',
        component: LessonScenePage,
      },
    ],
  })

  const app = createApp({
    render: () => h(RouterView),
  })
  const i18n = createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: {
      en: {},
    },
  })

  app.use(pinia)
  app.use(i18n)
  app.use(router)
  app.directive('auto-animate', {})

  const host = document.createElement('div')
  document.body.innerHTML = ''
  document.body.appendChild(host)

  await router.push(initialPath)
  options.beforeMount?.({ pinia, speechRuntimeStore })
  app.mount(host)
  await router.isReady()
  await flushUi()

  return {
    app,
    lessonStore: useLessonStore(pinia),
    speechRuntimeStore,
    pinia,
    router,
  }
}

describeMockSmoke('/lesson browser smoke', () => {
  let mountedApp: ReturnType<typeof createApp> | null = null

  beforeEach(() => {
    resetLessonBrowserMockStores()
    setLessonApiBaseUrlForTest(lessonApiBaseUrl)
    vi.clearAllMocks()
    localStorage.clear()
    document.body.innerHTML = ''
  })

  afterEach(() => {
    mountedApp?.unmount()
    mountedApp = null
    setLessonApiBaseUrlForTest(undefined)
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('loads the catalog, resolves the route page, and auto-starts the first teacher turn against the real backend', async () => {
    const fetchSpy = installLessonApiMock([lessonTurnP24StartFixture])
    const { app } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
    })

    const catalogCalls = fetchSpy.mock.calls.filter(([input]) => String(input).endsWith('/lesson/catalog'))
    const turnCalls = fetchSpy.mock.calls.filter(([input]) => String(input).endsWith('/lesson/turn'))

    expect(catalogCalls.length).toBeGreaterThanOrEqual(1)
    expect(turnCalls).toHaveLength(1)
    expect(catalogCalls[0]).toEqual(['http://127.0.0.1:9625/lesson/catalog', { method: 'GET' }])
    expect(turnCalls[0]?.[1]).toMatchObject({
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        page_uid: 'TB-G5S1U3-P24',
        student_id: 'demo-student',
      }),
    })
    expect(textContent()).toContain('G5 S1 U3 · P24')
    expect(textContent()).toContain('重新开始')
    expect(textContent()).toContain('本轮能力')
    expect(textContent()).toContain('Live prompts')
    expect(textContent()).toContain('向量检索')
    expect(textContent()).toContain('命中：unit')
    expect(textContent()).toContain('注入：common_mistakes / stable_preferences')
    expectRenderedDebugSignals(lessonTurnP24StartFixture.debug_signals!)
    expect(queryRuntimeFact('secure_context')).toBe('安全上下文')
    expect(queryRuntimeFact('permission')).toBe('未授权')
    expect(queryRuntimeFact('stream_input')).toBe('支持')
    expect(queryRuntimeFact('auto_send')).toBe('900ms')
    expect(queryRuntimeFact('asr')).toBe('browser-web-speech-api')
    expect(queryRuntimeFact('tts')).toBe('browser-speech-api')
    expect(queryRuntimeFact('tts_synthesis_state')).toBe('idle')
    expect(queryRuntimeFact('tts_playback_state')).toBe('idle')
    expect(queryRuntimeFact('mouth_open')).toBe('0.00')
    mountedApp = null
    app.unmount()
  })

  it('renders AIRI classroom state and backend performance intent as visible lesson closure signals', async () => {
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

    installLessonApiMock([startFixture])
    const { app, pinia } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(startFixture.teacher_response)
    })

    const lessonAiriRuntime = useLessonAiriRuntimeStore(pinia)
    expect(queryAiriVisibleFact('performance_source')).toBe('backend persona')
    expect(queryAiriVisibleFact('content_source')).toBe('lesson_runtime_teacher_response')
    expect(queryAiriVisibleFact('voice_pacing')).toBe('normal')
    expect(queryAiriVisibleFact('mouth_intensity')).toBe('0.75')
    expect(queryAiriVisibleFact('mouth_open')).toBe('0.00')
    expect(queryAiriVisibleFact('tts_synthesis_state')).toBe('idle')
    expect(queryAiriVisibleFact('tts_playback_state')).toBe('idle')

    lessonAiriRuntime.setClassroomState('listening')
    await flushUi()
    expect(queryAiriVisibleState()).toBe('聆听中')

    lessonAiriRuntime.updateInputVolume(22)
    lessonAiriRuntime.setClassroomState('learner_speaking')
    await flushUi()
    expect(queryAiriVisibleState()).toBe('学生说话')

    lessonAiriRuntime.setClassroomState('thinking')
    await flushUi()
    expect(queryAiriVisibleState()).toBe('思考中')

    lessonAiriRuntime.setTeacherSpeaking(true)
    await flushUi()
    expect(queryAiriVisibleState()).toBe('老师说话')

    lessonAiriRuntime.setTeacherSpeaking(false)
    lessonAiriRuntime.applyPerformancePlan({
      name: Emotion.Question,
      intensity: 0.8,
      motion: 'Explain',
      expression: 'focused',
      durationMs: 3000,
      reason: 'incorrect_answer',
      teachingAction: 'hint',
      evaluation: 'incorrect',
      turnLabel: 'answer_question',
      speechStyle: 'gentle_correction',
      mouthIntensity: 0.7,
      interruptPolicy: 'finish_current_sentence',
      contentSource: 'lesson_persona_context',
      fallbackAllowed: false,
      performanceSource: 'lesson_persona_context',
    })
    await flushUi()

    expect(queryAiriTeachingStance()).toBe('纠错中')
    expect(queryAiriVisibleFact('voice_pacing')).toBe('gentle_correction')
    expect(queryAiriVisibleFact('mouth_intensity')).toBe('0.70')
    expect(queryAiriVisibleFact('motion')).toBe('Explain')
    expect(queryAiriVisibleFact('expression')).toBe('focused')
    expect(queryAiriVisibleFact('performance_apply')).toBe('live2d_expression_unavailable:focused')
    expect(queryAiriVisibleFact('performance_fallback_kind')).toBe('known_capability_gap')
    expect(queryAiriVisibleFact('applied_motion')).toBe('Explain')
    expect(queryAiriVisibleFact('applied_expression')).toBe('motion-only')
    expect(queryAiriVisibleFact('interrupt_policy')).toBe('finish_current_sentence')

    lessonAiriRuntime.applyPerformancePlan({
      name: Emotion.Happy,
      intensity: 0.92,
      motion: 'Nod',
      expression: 'soft_smile',
      durationMs: 3000,
      reason: 'correct_answer',
      teachingAction: 'confirm',
      evaluation: 'correct',
      turnLabel: 'answer_question',
      speechStyle: 'normal',
      mouthIntensity: 0.8,
      interruptPolicy: 'barge_in_allowed',
      contentSource: 'lesson_persona_context',
      fallbackAllowed: false,
      performanceSource: 'lesson_persona_context',
    })
    await flushUi()

    await vi.waitFor(() => {
      expect(queryAiriTeachingStance()).toBe('鼓励推进')
      expect(queryAiriVisibleFact('voice_pacing')).toBe('normal')
      expect(queryAiriVisibleFact('mouth_intensity')).toBe('0.80')
      expect(queryAiriVisibleFact('motion')).toBe('Nod')
      expect(queryAiriVisibleFact('expression')).toBe('soft_smile')
      expect(queryAiriVisibleFact('performance_apply')).toBe('live2d_expression_unavailable:soft_smile')
      expect(queryAiriVisibleFact('performance_fallback_kind')).toBe('known_capability_gap')
      expect(queryAiriVisibleFact('applied_motion')).toBe('Nod')
      expect(queryAiriVisibleFact('applied_expression')).toBe('motion-only')
      expect(queryAiriVisibleFact('interrupt_policy')).toBe('barge_in_allowed')
    })

    lessonAiriRuntime.markSpeechSynthesisStart({
      provider: 'peptutor-edge-tts',
      model: 'edge-tts',
      voice: 'zh-CN-XiaoxiaoNeural',
      text: 'Great, say it again.',
      replyId: 'reply-visible-1',
    })
    lessonAiriRuntime.markSpeechSynthesisHttpResult({
      status: 200,
      statusText: 'OK',
    })
    lessonAiriRuntime.markSpeechSynthesisReady({
      audioByteLength: 4096,
      audioDurationMs: 1280,
    })
    lessonAiriRuntime.markSpeechPlaybackRequested({
      playbackId: 'playback-visible-1',
      replyId: 'reply-visible-1',
      audioContextState: 'running',
      reason: 'web_audio_buffer_source_start',
    })
    await flushUi()

    expect(queryAiriVisibleFact('tts_synthesis_state')).toBe('http_ok')
    expect(queryAiriVisibleFact('tts_playback_state')).toContain('play_requested')
    expect(queryAiriVisibleFact('tts_playback_id')).toBe('playback-visible-1')
    expect(queryAiriVisibleFact('active_reply_id')).toBe('reply-visible-1')
    expect(queryAiriVisibleFact('tts_stop_reason')).toBe('none')
    expect(queryAiriVisibleFact('tts_overlap_detected')).toBe('false')
    expect(queryAiriVisibleFact('mouth_open')).toBe('0.00')

    lessonAiriRuntime.markSpeechPlaybackStart({
      playbackId: 'playback-visible-1',
      replyId: 'reply-visible-1',
      audioContextState: 'running',
    })
    await flushUi()

    expect(queryAiriVisibleFact('tts')).toContain('正在播放')
    expect(queryAiriVisibleFact('tts')).toContain('HTTP 200 OK')
    expect(queryAiriVisibleFact('tts')).toContain('ctx=running')
    expect(queryAiriVisibleFact('tts_synthesis_state')).toBe('http_ok')
    expect(queryAiriVisibleFact('tts_playback_state')).toBe('playing')

    lessonAiriRuntime.markSpeechPlaybackEnd('ended', {
      playbackId: 'playback-visible-1',
      replyId: 'reply-visible-1',
      stopReason: 'ended',
    })
    await flushUi()
    expect(queryAiriVisibleFact('tts')).toContain('播放结束')
    expect(queryAiriVisibleFact('tts_playback_state')).toContain('ended')
    expect(queryAiriVisibleFact('tts_stop_reason')).toBe('ended')
    expect(queryAiriVisibleFact('tts_stop_type')).toBe('playback_ended')

    lessonAiriRuntime.markInterrupted()
    await flushUi()
    expect(queryAiriVisibleState()).toBe('被打断')

    mountedApp = null
    app.unmount()
  })

  it('does not call backend lesson turns a rules fallback when debug signals are absent', async () => {
    const startFixture = cloneLessonFixture(lessonTurnP24StartFixture)
    delete startFixture.debug_signals
    installLessonApiMock([startFixture])
    const { app } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(startFixture.teacher_response)
    })

    expect(queryAiriVisibleFact('reply_path')).toBe('后端课堂回复')
    expect(textContent()).not.toContain('规则兜底')
    mountedApp = null
    app.unmount()
  })

  it('renders teacher response audit source when the backend provides it', async () => {
    const startFixture = cloneLessonFixture(lessonTurnP24StartFixture)
    startFixture.debug_signals = {
      ...startFixture.debug_signals!,
      response_audit: {
        source: 'policy',
        llm_called: true,
        llm_provider: 'test-llm',
        latency_ms: 1234,
        fallback_used: false,
        fallback_reason: 'none',
        route: 'answer_turn_policy',
      },
    }
    installLessonApiMock([startFixture])
    const { app } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(startFixture.teacher_response)
    })

    expect(queryAiriVisibleFact('reply_path')).toBe('policy · llm=true · fallback=false · 1234ms · answer_turn_policy')
    expect(textContent()).not.toContain('规则兜底')
    mountedApp = null
    app.unmount()
  })

  it('sends learner text and appends the next teacher turn', async () => {
    const fetchSpy = installLessonApiMock([
      lessonTurnP24StartFixture,
      lessonTurnP24AnswerFixture,
    ])
    const { app } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain('What would you like to drink?')
    })

    const draftInput = queryRequiredElement<HTMLTextAreaElement>('textarea')
    setControlValue(draftInput, `I'd like some water.`)
    await flushUi()
    clickButton('发送')

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24AnswerFixture.teacher_response)
    })

    expect(fetchSpy).toHaveBeenCalledTimes(3)
    expect(textContent()).toContain(`I'd like some water.`)
    expect(textContent()).toContain('命中：branch')
    expect(textContent()).toContain('注入：common_mistakes / preferences / stable_preferences')
    expect(textContent()).toContain('召回：Learner gets shy when asked to answer aloud.')
    expectRenderedDebugSignals(lessonTurnP24AnswerFixture.debug_signals!)
    expect(fetchSpy.mock.calls[2]?.[1]).toMatchObject({
      method: 'POST',
    })
    expect(JSON.parse(String(fetchSpy.mock.calls[2]?.[1]?.body))).toMatchObject({
      page_uid: 'TB-G5S1U3-P24',
      student_id: 'demo-student',
      learner_input: `I'd like some water.`,
      state: cloneLessonFixture(lessonTurnP24StartFixture.state),
      turn_client_id: expect.stringMatching(/^lesson-turn-/),
    })
    mountedApp = null
    app.unmount()
  })

  it('renders degraded backend memory debug state from the latest api turn', async () => {
    installLessonApiMock([
      lessonTurnP24StartFixture,
      lessonTurnP24AnswerMemoryDegradedFixture,
    ])
    const { app } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain('What would you like to drink?')
    })

    const draftInput = queryRequiredElement<HTMLTextAreaElement>('textarea')
    setControlValue(draftInput, `I'd like some water.`)
    await flushUi()
    clickButton('发送')

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24AnswerMemoryDegradedFixture.teacher_response)
      expect(textContent()).toContain('召回/写回降级')
    })

    expectRenderedDebugSignals(lessonTurnP24AnswerMemoryDegradedFixture.debug_signals!)
    mountedApp = null
    app.unmount()
  })

  it('jumps to another page and restarts the lesson on the new page', async () => {
    const fetchSpy = installLessonApiMock([
      lessonTurnP24StartFixture,
      lessonTurnP25StartFixture,
    ])
    const { app, router } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
    })

    const pageUidInput = queryPageUidInput()
    setControlValue(pageUidInput, 'TB-G5S1U3-P25')
    await flushUi()
    clickButton('跳转')

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP25StartFixture.teacher_response)
    })

    expect(fetchSpy).toHaveBeenCalledTimes(3)
    expect(router.currentRoute.value.query.page_uid).toBe('TB-G5S1U3-P25')
    expect(fetchSpy.mock.calls[2]?.[1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({
        page_uid: 'TB-G5S1U3-P25',
        student_id: 'demo-student',
      }),
    })
    expect(textContent()).toContain('G5 S1 U3 · P25')
    mountedApp = null
    app.unmount()
  })

  it('switches scope through the grouped selector and restarts the lesson on the new cross-scope page', async () => {
    const fetchSpy = installLessonApiMock([
      lessonTurnG6S2Recycle2P49StartFixture,
      lessonTurnG6S1U1P2StartFixture,
    ])
    const { app, lessonStore, router } = await mountLessonPage('/lesson?page_uid=TB-G6S2Recycle2-P49')
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnG6S2Recycle2P49StartFixture.teacher_response)
      expect(textContent()).toContain('G6 S2 Recycle2 · P49')
      expect(queryPageUidInput().value).toBe('TB-G6S2Recycle2-P49')
    })

    clickRadioTab('S1')
    await flushUi()

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnG6S1U1P2StartFixture.teacher_response)
      expect(textContent()).toContain('G6 S1 U1 · P2')
      expect(queryPageUidInput().value).toBe('TB-G6S1U1-P2')
      expect(router.currentRoute.value.query.page_uid).toBe('TB-G6S1U1-P2')
      expect(lessonStore.selectedGrade).toBe('G6')
      expect(lessonStore.selectedSemester).toBe('S1')
      expect(lessonStore.selectedUnit).toBe('U1')
      expect(lessonStore.selectedPageUid).toBe('TB-G6S1U1-P2')
      expect(localStorage.getItem('peptutor/lesson/last-page-uid')).toBe('TB-G6S1U1-P2')
    })

    expect(fetchSpy).toHaveBeenCalledTimes(3)
    expect(fetchSpy.mock.calls[1]?.[1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({
        page_uid: 'TB-G6S2Recycle2-P49',
        student_id: 'demo-student',
      }),
    })
    expect(fetchSpy.mock.calls[2]?.[1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({
        page_uid: 'TB-G6S1U1-P2',
        student_id: 'demo-student',
      }),
    })
    mountedApp = null
    app.unmount()
  })

  it('replays teacher prompts through AIRI assistant hooks on start and repeat', async () => {
    installLessonApiMock([lessonTurnP24StartFixture])
    let runtimeSpy!: ReturnType<typeof spyOnLessonSpeechRuntime>
    const { app } = await mountLessonPage('/lesson?page_uid=TB-G5S1U3-P24', {
      beforeMount: ({ speechRuntimeStore }) => {
        runtimeSpy = spyOnLessonSpeechRuntime(speechRuntimeStore)
      },
    })
    mountedApp = app

    await vi.waitFor(() => {
      expect(runtimeSpy.openIntentSpy).toHaveBeenCalledTimes(1)
    })

    expect(runtimeSpy.openIntentSpy).toHaveBeenNthCalledWith(1, {
      ownerId: 'lesson',
      priority: 'normal',
      behavior: 'interrupt',
    })
    expect(runtimeSpy.literalWrites.join('')).toBe(lessonTurnP24StartFixture.teacher_response)
    expect(runtimeSpy.flushCount).toBe(1)
    expect(runtimeSpy.endCount).toBe(1)

    clickButton('再听一遍')
    await flushUi()

    await vi.waitFor(() => {
      expect(runtimeSpy.openIntentSpy).toHaveBeenCalledTimes(2)
    })

    expect(runtimeSpy.openIntentSpy).toHaveBeenNthCalledWith(2, {
      ownerId: 'lesson',
      priority: 'normal',
      behavior: 'interrupt',
    })
    await vi.waitFor(() => {
      expect(runtimeSpy.literalWrites.join('')).toBe(
        `${lessonTurnP24StartFixture.teacher_response}${lessonTurnP24StartFixture.teacher_response}`,
      )
      expect(runtimeSpy.flushCount).toBe(2)
      expect(runtimeSpy.endCount).toBe(2)
    })
    mountedApp = null
    app.unmount()
  })

  it('opens the lesson microphone, starts streaming transcription, and backfills the learner draft', async () => {
    installLessonApiMock([
      lessonTurnP24StartFixture,
      lessonTurnP24AnswerFixture,
    ])
    const { app } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
    })

    await openLessonMicrophone()

    await vi.waitFor(() => {
      expect(mockAudioDeviceStore.askPermission).toHaveBeenCalledTimes(1)
      expect(mockAudioDeviceStore.startStream).toHaveBeenCalledTimes(1)
      expect(mockHearingPipeline.transcribeForMediaStream).toHaveBeenCalledTimes(1)
    })

    expect(queryButton('停止听写')).toBeTruthy()
    emitMockTranscriptionInterim(`I'd like...`)
    await flushUi()

    await vi.waitFor(() => {
      expect(textContent()).toContain('实时转写')
      expect(textContent()).toContain(`I'd like...`)
      expect(textContent()).toContain('Mock Mic')
      expect(queryRequiredElement<HTMLTextAreaElement>('textarea').value).toContain(`I'd like...`)
    })

    emitMockTranscriptionSentence(`I'd like some water.`)
    await flushUi()

    const draftInput = queryRequiredElement<HTMLTextAreaElement>('textarea')
    expect(draftInput.value).toContain(`I'd like some water.`)

    await stopLessonMicrophone()

    await vi.waitFor(() => {
      expect(mockHearingPipeline.stopStreamingTranscription).toHaveBeenCalled()
    })

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24AnswerFixture.teacher_response)
    })

    expect(queryButton('麦克风')).toBeTruthy()
    mountedApp = null
    app.unmount()
  })

  it('renders streaming ASR interim text in the lesson textarea without duplicating deltas', async () => {
    installLessonApiMock([
      lessonTurnP24StartFixture,
    ])
    mockHearingStore.activeTranscriptionProvider.value = 'volcengine-realtime-transcription'
    mockHearingStore.activeTranscriptionModel.value = '1.2.1.1'
    const { app } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
    })

    await openLessonMicrophone()

    await vi.waitFor(() => {
      expect(mockHearingPipeline.transcribeForMediaStream).toHaveBeenCalledTimes(1)
    })

    const draftInput = queryRequiredElement<HTMLTextAreaElement>('textarea')
    emitMockTranscriptionInterim('你')
    await flushUi()
    expect(draftInput.value).toBe('你')

    emitMockTranscriptionSentence('你')
    await flushUi()
    expect(draftInput.value).toBe('你')

    emitMockTranscriptionInterim('你好')
    await flushUi()
    expect(draftInput.value).toBe('你好')

    emitMockTranscriptionSentence('好')
    await flushUi()
    expect(draftInput.value).toBe('你好')

    mountedApp = null
    app.unmount()
  })

  it('focuses the lesson textarea when the input shell is clicked', async () => {
    installLessonApiMock([
      lessonTurnP24StartFixture,
    ])
    const { app } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
    })

    const inputShell = queryRequiredElement<HTMLElement>('[data-testid="lesson-chat-input-shell"]')
    expect(inputShell.className).toContain('cursor-text')
    inputShell.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }))
    await flushUi()

    expect(document.activeElement).toBe(queryRequiredElement<HTMLTextAreaElement>('textarea'))
    mountedApp = null
    app.unmount()
  })

  it('uses Ctrl+Meta as hold-to-talk and flushes the pending transcript on release', async () => {
    const fetchSpy = installLessonApiMock([
      lessonTurnP24StartFixture,
      lessonTurnP24AnswerFixture,
    ])
    const { app } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
    })

    window.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Control',
      code: 'ControlLeft',
      ctrlKey: true,
      bubbles: true,
    }))
    window.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Meta',
      code: 'MetaLeft',
      ctrlKey: true,
      metaKey: true,
      bubbles: true,
    }))
    await flushUi()

    await vi.waitFor(() => {
      expect(mockAudioDeviceStore.ensureInputReady).toHaveBeenCalledTimes(1)
      expect(mockHearingPipeline.transcribeForMediaStream).toHaveBeenCalledTimes(1)
    })

    emitMockTranscriptionSentence(`I'd like some water.`)
    await flushUi()

    window.dispatchEvent(new KeyboardEvent('keyup', {
      key: 'Meta',
      code: 'MetaLeft',
      ctrlKey: true,
      metaKey: false,
      bubbles: true,
    }))
    await flushUi()

    await vi.waitFor(() => {
      expect(mockHearingPipeline.stopStreamingTranscription).toHaveBeenCalled()
      expect(textContent()).toContain(lessonTurnP24AnswerFixture.teacher_response)
    })

    expect(fetchSpy).toHaveBeenCalledTimes(3)
    expect(textContent()).toContain(`I'd like some water.`)
    mountedApp = null
    app.unmount()
  })

  it('keeps the lesson text input enabled while a streamed teacher turn is pending', async () => {
    const learnerReplyResponse = createDeferred<Response>()
    let pendingStreamTurnClientId = 'browser-test-turn'
    const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)

      if (url.endsWith('/lesson/catalog')) {
        return lessonJsonResponse(cloneLessonFixture(lessonCatalogSmokeFixture))
      }

      if (url.endsWith('/lesson/turn')) {
        return lessonJsonResponse(cloneLessonFixture(lessonTurnP24StartFixture))
      }

      if (url.endsWith('/lesson/turn/stream')) {
        const body = typeof init?.body === 'string' ? JSON.parse(init.body) : null
        pendingStreamTurnClientId = body?.turn_client_id || pendingStreamTurnClientId
        return learnerReplyResponse.promise
      }

      throw new Error(`Unexpected fetch request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchSpy)

    const { app, lessonStore } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
    })

    const draftInput = queryRequiredElement<HTMLTextAreaElement>('textarea')
    setControlValue(draftInput, `I'd like some water.`)
    await flushUi()
    clickButton('发送')
    await flushUi()

    await vi.waitFor(() => {
      expect(lessonStore.loading).toBe(true)
      expect(fetchSpy).toHaveBeenCalledTimes(3)
    })

    expect(queryRequiredElement<HTMLTextAreaElement>('textarea').disabled).toBe(false)

    learnerReplyResponse.resolve(lessonTurnStreamResponse(
      cloneLessonFixture(lessonTurnP24AnswerFixture),
      pendingStreamTurnClientId,
    ))
    await flushUi()

    mountedApp = null
    app.unmount()
  })

  it('keeps the live lesson input enabled while history session repair is pending', async () => {
    installLessonApiMock([
      lessonTurnP24StartFixture,
    ])
    const { app, pinia } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
    })

    const chatSessionStore = useChatSessionStore(pinia)
    const lessonChatHistoryStore = useLessonChatHistoryStore(pinia)
    const activeSessionId = chatSessionStore.activeSessionId
    lessonChatHistoryStore.historySafetyBySessionId[activeSessionId] = {
      sessionId: activeSessionId,
      access: 'read_only',
      label: '只读',
      detail: '旧历史或混页历史，只读查看',
      canRestore: false,
      historyFormat: 'peptutor-chat-history:v2',
      auditStatus: 'legacy_readonly',
      restoreSafety: 'none',
      messagePageOwnership: 'mixed',
      safeToMigrate: false,
      warnings: [],
    }
    await flushUi()

    const draftInput = queryRequiredElement<HTMLTextAreaElement>('textarea')
    setControlValue(draftInput, `I'd like some water.`)
    await flushUi()

    expect(lessonChatHistoryStore.activeHistoryReadOnly).toBe(true)
    expect(draftInput.disabled).toBe(false)
    expect(queryButton('发送').disabled).toBe(false)

    mountedApp = null
    app.unmount()
  })

  it('renders a localized microphone failure state when the input stream cannot be opened', async () => {
    installLessonApiMock([
      lessonTurnP24StartFixture,
    ])
    mockAudioDeviceStore.ensureInputReady.mockImplementationOnce(async () => {
      mockAudioDeviceStore.permissionState.value = 'denied'
      mockAudioDeviceStore.permissionError.value = '麦克风接入超时，请检查浏览器输入设备和系统录音权限。'
      throw new Error(mockAudioDeviceStore.permissionError.value)
    })

    const { app } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
    })

    clickButton('麦克风')
    await flushUi()

    await vi.waitFor(() => {
      expect(textContent()).toContain('接入失败')
      expect(textContent()).toContain('麦克风接入超时，请检查浏览器输入设备和系统录音权限。')
    })

    mountedApp = null
    app.unmount()
  })

  it('auto-sends transcribed learner speech after the lesson delay', async () => {
    const fetchSpy = installLessonApiMock([
      lessonTurnP24StartFixture,
      lessonTurnP24AnswerFixture,
    ])
    const { app } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
    })

    await openLessonMicrophone()

    await vi.waitFor(() => {
      expect(mockHearingPipeline.transcribeForMediaStream).toHaveBeenCalledTimes(1)
    })

    emitMockTranscriptionSentence(`I'd like some water.`)
    await flushUi()
    await new Promise(resolve => setTimeout(resolve, 950))
    await flushUi()

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24AnswerFixture.teacher_response)
    })

    expect(fetchSpy).toHaveBeenCalledTimes(3)
    expect(textContent()).toContain('学生')
    expect(textContent()).toContain(`I'd like some water.`)
    mountedApp = null
    app.unmount()
  })

  it('keeps the browser speech chain and latest debug_signals aligned across request, listen, transcript, auto-send, and reply', async () => {
    const microphoneReady = createDeferred<void>()
    const learnerReplyResponse = createDeferred<Response>()
    let pendingStreamTurnClientId = 'browser-test-turn'
    const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)

      if (url.endsWith('/lesson/catalog')) {
        return lessonJsonResponse(cloneLessonFixture(lessonCatalogSmokeFixture))
      }

      if (url.endsWith('/lesson/turn')) {
        return lessonJsonResponse(cloneLessonFixture(lessonTurnP24StartFixture))
      }

      if (url.endsWith('/lesson/turn/stream')) {
        const body = typeof init?.body === 'string' ? JSON.parse(init.body) : null
        pendingStreamTurnClientId = body?.turn_client_id || pendingStreamTurnClientId
        return learnerReplyResponse.promise
      }

      throw new Error(`Unexpected fetch request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchSpy)
    mockAudioDeviceStore.ensureInputReady.mockImplementationOnce(async () => {
      mockAudioDeviceStore.permissionError.value = ''
      mockAudioDeviceStore.permissionState.value = 'requesting'
      await microphoneReady.promise
      mockAudioDeviceStore.enabled.value = true
      mockAudioDeviceStore.startStream()
      mockAudioDeviceStore.permissionState.value = 'granted'
      return mockAudioDeviceStore.stream.value
    })

    const { app } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
      expectRenderedDebugSignals(lessonTurnP24StartFixture.debug_signals!)
      expect(queryRuntimeFact('permission')).toBe('未授权')
    })

    clickButton('麦克风')
    await flushUi()

    await vi.waitFor(() => {
      expect(queryRuntimeStatusLabel()).toBe('接入中')
      expect(queryRuntimeStatusDetail()).toContain('正在向浏览器请求麦克风')
      expect(queryChatStatusLabel()).toBe('接入中')
      expect(queryChatStatusDetail()).toContain('正在向浏览器请求麦克风')
      expect(queryRuntimeFact('permission')).toBe('请求中')
    })

    microphoneReady.resolve()
    await flushUi()

    await vi.waitFor(() => {
      expect(mockHearingPipeline.transcribeForMediaStream).toHaveBeenCalledTimes(1)
      expect(queryRuntimeStatusLabel()).toBe('聆听中')
      expect(queryRuntimeFact('permission')).toBe('已授权')
      expect(queryRuntimeCurrentDevice()).toContain('Mock Mic')
    })

    emitMockTranscriptionInterim(`I'd like...`)
    await flushUi()

    await vi.waitFor(() => {
      expect(queryRuntimeLiveTranscript()).toContain(`I'd like...`)
      const chatTranscript = queryOptionalElement<HTMLElement>('[data-testid="lesson-chat-live-transcript"]')
      if (chatTranscript) {
        expect(chatTranscript.textContent?.trim()).toContain(`I'd like...`)
      }
    })

    emitMockTranscriptionSentence(`I'd like some water.`)
    await flushUi()

    await vi.waitFor(() => {
      expect(queryRuntimeLiveTranscript()).toContain(`I'd like some water.`)
      const chatTranscript = queryOptionalElement<HTMLElement>('[data-testid="lesson-chat-live-transcript"]')
      if (chatTranscript) {
        expect(chatTranscript.textContent?.trim()).toContain(`I'd like some water.`)
      }
    })

    await new Promise(resolve => setTimeout(resolve, 950))
    await flushUi()

    await vi.waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(3)
      expect(queryRuntimeStatusLabel()).toBe('思考中')
      expect(queryRuntimeStatusDetail()).toContain('等待 lesson backend 返回下一句')
    })

    learnerReplyResponse.resolve(lessonTurnStreamResponse(
      cloneLessonFixture(lessonTurnP24AnswerFixture),
      pendingStreamTurnClientId,
    ))
    await flushUi()

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24AnswerFixture.teacher_response)
      expectRenderedDebugSignals(lessonTurnP24AnswerFixture.debug_signals!)
      expect(queryRuntimeStatusLabel()).toBe('聆听中')
      expect(queryRuntimeFact('permission')).toBe('已授权')
      expect(textContent()).toContain(`I'd like some water.`)
    })

    await vi.waitFor(() => {
      expect(queryOptionalElement('[data-testid="lesson-runtime-live-transcript"]')).toBeNull()
    })

    mountedApp = null
    app.unmount()
  })

  it('flushes pending auto-send text when lesson listening stops before the delay elapses', async () => {
    const fetchSpy = installLessonApiMock([
      lessonTurnP24StartFixture,
      lessonTurnP24AnswerFixture,
    ])
    const { app } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
    })

    await openLessonMicrophone()

    await vi.waitFor(() => {
      expect(mockHearingPipeline.transcribeForMediaStream).toHaveBeenCalledTimes(1)
    })

    emitMockTranscriptionSentence(`I'd like some water.`)
    await flushUi()
    await stopLessonMicrophone()

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24AnswerFixture.teacher_response)
    })

    await vi.waitFor(() => {
      expect(mockHearingPipeline.stopStreamingTranscription).toHaveBeenCalled()
    })

    expect(fetchSpy).toHaveBeenCalledTimes(3)
    expect(textContent()).toContain(`I'd like some water.`)
    mountedApp = null
    app.unmount()
  })

  it('interrupts lesson playback as soon as learner speech is recognized', async () => {
    installLessonApiMock([lessonTurnP24StartFixture])
    let playbackControllerSpy!: ReturnType<typeof attachLessonPlaybackControllerSpy>
    const { app } = await mountLessonPage('/lesson?page_uid=TB-G5S1U3-P24', {
      beforeMount: ({ speechRuntimeStore }) => {
        playbackControllerSpy = attachLessonPlaybackControllerSpy(speechRuntimeStore)
      },
    })
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
    })

    await openLessonMicrophone()

    await vi.waitFor(() => {
      expect(mockHearingPipeline.transcribeForMediaStream).toHaveBeenCalledTimes(1)
    })

    emitMockTranscriptionSentence(`I'd like some water.`)
    await flushUi()

    expect(playbackControllerSpy.stopAllSpy).toHaveBeenCalledWith('lesson-learner-transcription')
    mountedApp = null
    app.unmount()
  })

  it('does not stop lesson playback on recognized speech when the backend asks to finish the current sentence', async () => {
    installLessonApiMock([lessonTurnP24StartFixture])
    let playbackControllerSpy!: ReturnType<typeof attachLessonPlaybackControllerSpy>
    const { app, pinia } = await mountLessonPage('/lesson?page_uid=TB-G5S1U3-P24', {
      beforeMount: ({ speechRuntimeStore }) => {
        playbackControllerSpy = attachLessonPlaybackControllerSpy(speechRuntimeStore)
      },
    })
    mountedApp = app

    await vi.waitFor(() => {
      expect(textContent()).toContain(lessonTurnP24StartFixture.teacher_response)
    })

    const lessonAiriRuntime = useLessonAiriRuntimeStore(pinia)
    lessonAiriRuntime.applyPerformancePlan({
      name: Emotion.Question,
      intensity: 0.78,
      motion: 'Explain',
      expression: 'focused',
      durationMs: 3000,
      reason: 'lesson_turn',
      teachingAction: 'hint',
      evaluation: 'unclear',
      turnLabel: 'answer_question',
      speechStyle: 'gentle_correction',
      mouthIntensity: 0.7,
      interruptPolicy: 'finish_current_sentence',
      contentSource: 'lesson_persona_context',
      fallbackAllowed: false,
      performanceSource: 'lesson_persona_context',
    })
    await flushUi()

    await openLessonMicrophone()

    await vi.waitFor(() => {
      expect(mockHearingPipeline.transcribeForMediaStream).toHaveBeenCalledTimes(1)
    })

    emitMockTranscriptionSentence(`I'd like some water.`)
    await flushUi()

    expect(playbackControllerSpy.stopAllSpy).not.toHaveBeenCalledWith('lesson-learner-transcription')
    expect(lessonAiriRuntime.classroomState).not.toBe('interrupted')
    expect(queryRequiredElement<HTMLTextAreaElement>('textarea').value).toContain(`I'd like some water.`)
    mountedApp = null
    app.unmount()
  })
})

describeRealSmoke('/lesson browser smoke (real backend)', () => {
  let mountedApp: ReturnType<typeof createApp> | null = null

  beforeEach(() => {
    resetLessonBrowserMockStores()
    setLessonApiBaseUrlForTest(lessonApiBaseUrl)
    vi.clearAllMocks()
    localStorage.clear()
    document.body.innerHTML = ''
  })

  afterEach(() => {
    mountedApp?.unmount()
    mountedApp = null
    setLessonApiBaseUrlForTest(undefined)
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('loads the catalog, resolves the route page, and auto-starts the first teacher turn', async () => {
    const startedAtMs = Date.now()
    const { app, lessonStore, pinia } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(lessonStore.transcript).toHaveLength(1)
      expect(lessonStore.runtimeState?.current_page_uid).toBe('TB-G5S1U3-P24')
      expect(lessonStore.activeTurn?.turn_label).toBe('page_entry')
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe('')
    }, { timeout: smokeWaitTimeoutMs })

    const teacherResponse = lastTeacherTranscriptText(lessonStore)
    expectRealTeacherResponse(teacherResponse)
    expect(textContent()).toContain('G5 S1 U3 · P24')
    expect(textContent()).toContain('重新开始')
    logRealSmokeObservation('loads the catalog, resolves the route page, and auto-starts the first teacher turn against the real backend', startedAtMs, teacherResponse)
    await logRealArtifactSnapshot('loads the catalog, resolves the route page, and auto-starts the first teacher turn against the real backend', pinia)
    mountedApp = null
    app.unmount()
  }, smokeTestTimeoutMs)

  it('observes S4.1 barge-in stop reason while using the real backend lesson turn', async () => {
    const startedAtMs = Date.now()
    let playbackControllerSpy!: ReturnType<typeof attachLessonPlaybackControllerSpy>
    let lessonAiriRuntime!: ReturnType<typeof useLessonAiriRuntimeStore>
    const playbackId = 's4-barge-in-playback'
    const replyId = 's4-barge-in-reply'
    const { app, lessonStore, pinia } = await mountLessonPage('/lesson?page_uid=TB-G5S1U3-P24', {
      beforeMount: ({ speechRuntimeStore, pinia: mountPinia }) => {
        lessonAiriRuntime = useLessonAiriRuntimeStore(mountPinia)
        playbackControllerSpy = attachLessonPlaybackControllerSpy(speechRuntimeStore, {
          onStopAll: (reason) => {
            lessonAiriRuntime.markSpeechPlaybackEnd('interrupted', {
              playbackId,
              replyId,
              stopReason: reason,
            })
          },
        })
      },
    })
    mountedApp = app

    await vi.waitFor(() => {
      expect(lessonStore.transcript).toHaveLength(1)
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe('')
    }, { timeout: smokeWaitTimeoutMs })

    lessonAiriRuntime = lessonAiriRuntime || useLessonAiriRuntimeStore(pinia)
    lessonAiriRuntime.applyPerformancePlan({
      name: Emotion.Happy,
      intensity: 0.86,
      motion: 'Nod',
      expression: 'soft_smile',
      durationMs: 3000,
      reason: 'lesson_turn',
      teachingAction: 'confirm',
      evaluation: 'correct',
      turnLabel: 'answer_question',
      speechStyle: 'normal',
      mouthIntensity: 0.8,
      interruptPolicy: 'barge_in_allowed',
      contentSource: 'lesson_persona_context',
      fallbackAllowed: false,
      performanceSource: 'lesson_persona_context',
    })
    lessonAiriRuntime.markSpeechSynthesisStart({
      provider: 'peptutor-edge-tts',
      model: 'edge-tts',
      voice: 'zh-CN-XiaoxiaoNeural',
      text: lastTeacherTranscriptText(lessonStore),
      replyId,
    })
    lessonAiriRuntime.markSpeechSynthesisHttpResult({
      status: 200,
      statusText: 'OK',
    })
    lessonAiriRuntime.markSpeechSynthesisReady({
      audioByteLength: 4096,
      audioDurationMs: 1800,
    })
    lessonAiriRuntime.markSpeechPlaybackRequested({
      playbackId,
      replyId,
      audioContextState: 'running',
      reason: 's4_evidence_playback_start',
    })
    lessonAiriRuntime.markSpeechPlaybackStart({
      playbackId,
      replyId,
      audioContextState: 'running',
    })
    await flushUi()

    expect(queryAiriVisibleFact('interrupt_policy')).toBe('barge_in_allowed')
    expect(queryAiriVisibleFact('tts_playback_state')).toBe('playing')

    await openLessonMicrophone()
    await vi.waitFor(() => {
      expect(mockHearingPipeline.transcribeForMediaStream).toHaveBeenCalledTimes(1)
    }, { timeout: smokeWaitTimeoutMs })

    emitMockTranscriptionSentence(`I'd like some water.`)
    await flushUi()

    expect(playbackControllerSpy.stopAllSpy).toHaveBeenCalledWith('lesson-learner-transcription')
    expect(lessonAiriRuntime.ttsPlaybackStopReason).toBe('lesson-learner-transcription')
    expect(lessonAiriRuntime.ttsPlaybackNormalizedStopReason).toBe('final_transcript_interrupt')
    expect(queryAiriVisibleFact('tts_stop_reason')).toBe('lesson-learner-transcription')
    expect(queryAiriVisibleFact('tts_stop_type')).toBe('final_transcript_interrupt')
    expect(queryAiriVisibleFact('tts_overlap_detected')).toBe('false')

    console.info(`[lesson-s4-interrupt-evidence] ${JSON.stringify({
      test: 'barge_in_allowed',
      duration_ms: Date.now() - startedAtMs,
      interrupt_policy: lessonAiriRuntime.currentInterruptPolicy,
      tts_playback_stop_reason: lessonAiriRuntime.ttsPlaybackStopReason,
      tts_playback_stop_reason_normalized: lessonAiriRuntime.ttsPlaybackNormalizedStopReason,
      sidebar_tts_stop_type: queryAiriVisibleFact('tts_stop_type'),
      playback_overlap: lessonAiriRuntime.ttsPlaybackOverlapDetected,
    })}`)

    mountedApp = null
    app.unmount()
  }, smokeTestTimeoutMs)

  it('observes S4.1 finish-current-sentence deferral while using the real backend lesson turn', async () => {
    const startedAtMs = Date.now()
    let playbackControllerSpy!: ReturnType<typeof attachLessonPlaybackControllerSpy>
    const playbackId = 's4-finish-current-sentence-playback'
    const replyId = 's4-finish-current-sentence-reply'
    const { app, lessonStore, pinia } = await mountLessonPage('/lesson?page_uid=TB-G5S1U3-P24', {
      beforeMount: ({ speechRuntimeStore }) => {
        playbackControllerSpy = attachLessonPlaybackControllerSpy(speechRuntimeStore)
      },
    })
    mountedApp = app

    await vi.waitFor(() => {
      expect(lessonStore.transcript).toHaveLength(1)
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe('')
    }, { timeout: smokeWaitTimeoutMs })

    const lessonAiriRuntime = useLessonAiriRuntimeStore(pinia)
    lessonAiriRuntime.applyPerformancePlan({
      name: Emotion.Question,
      intensity: 0.78,
      motion: 'Explain',
      expression: 'focused',
      durationMs: 3000,
      reason: 'lesson_turn',
      teachingAction: 'hint',
      evaluation: 'unclear',
      turnLabel: 'answer_question',
      speechStyle: 'gentle_correction',
      mouthIntensity: 0.7,
      interruptPolicy: 'finish_current_sentence',
      contentSource: 'lesson_persona_context',
      fallbackAllowed: false,
      performanceSource: 'lesson_persona_context',
    })
    lessonAiriRuntime.markSpeechSynthesisStart({
      provider: 'peptutor-edge-tts',
      model: 'edge-tts',
      voice: 'zh-CN-XiaoxiaoNeural',
      text: lastTeacherTranscriptText(lessonStore),
      replyId,
    })
    lessonAiriRuntime.markSpeechSynthesisHttpResult({
      status: 200,
      statusText: 'OK',
    })
    lessonAiriRuntime.markSpeechSynthesisReady({
      audioByteLength: 4096,
      audioDurationMs: 1800,
    })
    lessonAiriRuntime.markSpeechPlaybackRequested({
      playbackId,
      replyId,
      audioContextState: 'running',
      reason: 's4_evidence_playback_start',
    })
    lessonAiriRuntime.markSpeechPlaybackStart({
      playbackId,
      replyId,
      audioContextState: 'running',
    })
    await flushUi()

    expect(queryAiriVisibleFact('interrupt_policy')).toBe('finish_current_sentence')
    expect(queryAiriVisibleFact('tts_playback_state')).toBe('playing')

    await openLessonMicrophone()
    await vi.waitFor(() => {
      expect(mockHearingPipeline.transcribeForMediaStream).toHaveBeenCalledTimes(1)
    }, { timeout: smokeWaitTimeoutMs })

    emitMockTranscriptionSentence(`I'd like some water.`)
    await flushUi()

    expect(playbackControllerSpy.stopAllSpy).not.toHaveBeenCalledWith('lesson-learner-transcription')
    expect(lessonAiriRuntime.ttsPlaybackState).toBe('playing')
    expect(lessonAiriRuntime.ttsPlaybackStopReason).toBe('')
    expect(lessonAiriRuntime.ttsPlaybackNormalizedStopReason).toBe('')
    expect(queryAiriVisibleFact('tts_stop_reason')).toBe('none')
    expect(queryAiriVisibleFact('tts_stop_type')).toBe('none')
    expect(queryAiriVisibleFact('tts_overlap_detected')).toBe('false')
    expect(queryRequiredElement<HTMLTextAreaElement>('textarea').value).toContain(`I'd like some water.`)

    console.info(`[lesson-s4-interrupt-evidence] ${JSON.stringify({
      test: 'finish_current_sentence',
      duration_ms: Date.now() - startedAtMs,
      interrupt_policy: lessonAiriRuntime.currentInterruptPolicy,
      immediate_stop: playbackControllerSpy.stopAllSpy.mock.calls.some(([reason]) => reason === 'lesson-learner-transcription'),
      deferred_transcript_in_textarea: queryRequiredElement<HTMLTextAreaElement>('textarea').value.includes(`I'd like some water.`),
      tts_playback_stop_reason: lessonAiriRuntime.ttsPlaybackStopReason || 'none',
      tts_playback_stop_reason_normalized: lessonAiriRuntime.ttsPlaybackNormalizedStopReason || 'none',
      sidebar_tts_stop_type: queryAiriVisibleFact('tts_stop_type'),
      playback_overlap: lessonAiriRuntime.ttsPlaybackOverlapDetected,
    })}`)

    mountedApp = null
    app.unmount()
  }, smokeTestTimeoutMs)

  it('sends learner text and appends the next teacher turn against the real backend', async () => {
    const startedAtMs = Date.now()
    const { app, lessonStore } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe('')
      expect(lessonStore.transcript).toHaveLength(1)
    }, { timeout: smokeWaitTimeoutMs })

    const initialTeacherResponse = lastTeacherTranscriptText(lessonStore)
    const draftInput = queryRequiredElement<HTMLTextAreaElement>('textarea')
    setControlValue(draftInput, `I'd like some water.`)
    await flushUi()
    clickButton('发送')

    await vi.waitFor(() => {
      expect(lessonStore.transcript).toHaveLength(3)
      expect(lessonStore.transcript[1]?.speaker).toBe('learner')
      expect(lessonStore.transcript[1]?.text).toBe(`I'd like some water.`)
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe(initialTeacherResponse)
    }, { timeout: smokeWaitTimeoutMs })

    const teacherResponse = lastTeacherTranscriptText(lessonStore)
    expectRealTeacherResponse(teacherResponse)
    expect(textContent()).toContain(`I'd like some water.`)
    logRealSmokeObservation('sends learner text and appends the next teacher turn against the real backend', startedAtMs, teacherResponse)
    mountedApp = null
    app.unmount()
  }, smokeTestTimeoutMs)

  it('jumps to another page and restarts the lesson on the new page against the real backend', async () => {
    const startedAtMs = Date.now()
    const { app, lessonStore, router } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe('')
      expect(lessonStore.runtimeState?.current_page_uid).toBe('TB-G5S1U3-P24')
    }, { timeout: smokeWaitTimeoutMs })

    const initialTeacherResponse = lastTeacherTranscriptText(lessonStore)
    const pageUidInput = queryPageUidInput()
    setControlValue(pageUidInput, 'TB-G5S1U3-P25')
    await flushUi()
    clickButton('跳转')

    await vi.waitFor(() => {
      expect(router.currentRoute.value.query.page_uid).toBe('TB-G5S1U3-P25')
      expect(lessonStore.runtimeState?.current_page_uid).toBe('TB-G5S1U3-P25')
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe('')
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe(initialTeacherResponse)
    }, { timeout: smokeWaitTimeoutMs })

    const teacherResponse = lastTeacherTranscriptText(lessonStore)
    expectRealTeacherResponse(teacherResponse)
    expect(textContent()).toContain('G5 S1 U3 · P25')
    logRealSmokeObservation('jumps to another page and restarts the lesson on the new page against the real backend', startedAtMs, teacherResponse)
    mountedApp = null
    app.unmount()
  }, smokeTestTimeoutMs)

  it('keeps browser lesson routing stable across P24 -> P25 -> P26 and preserves the P26 in-context snow question', async () => {
    const startedAtMs = Date.now()
    const { capturedTurnResults } = installRealLessonApiCapture()
    const { app, lessonStore, router } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(capturedTurnResults.length).toBeGreaterThanOrEqual(1)
      expect(lessonStore.runtimeState?.current_page_uid).toBe('TB-G5S1U3-P24')
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe('')
    }, { timeout: smokeWaitTimeoutMs })

    const p24TeacherResponse = lastTeacherTranscriptText(lessonStore)
    setControlValue(queryPageUidInput(), 'TB-G5S1U3-P25')
    await flushUi()
    clickButton('跳转')

    await vi.waitFor(() => {
      expect(router.currentRoute.value.query.page_uid).toBe('TB-G5S1U3-P25')
      expect(lessonStore.runtimeState?.current_page_uid).toBe('TB-G5S1U3-P25')
      expect(lessonStore.activeTurn?.turn_label).toBe('page_entry')
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe('')
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe(p24TeacherResponse)
    }, { timeout: smokeWaitTimeoutMs })

    const p25TeacherResponse = lastTeacherTranscriptText(lessonStore)
    setControlValue(queryPageUidInput(), 'TB-G5S1U3-P26')
    await flushUi()
    clickButton('跳转')

    await vi.waitFor(() => {
      expect(router.currentRoute.value.query.page_uid).toBe('TB-G5S1U3-P26')
      expect(lessonStore.runtimeState?.current_page_uid).toBe('TB-G5S1U3-P26')
      expect(lessonStore.runtimeState?.current_block_uid).toBe('TB-G5S1U3-P26-D1')
      expect(lessonStore.activeTurn?.turn_label).toBe('page_entry')
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe('')
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe(p25TeacherResponse)
    }, { timeout: smokeWaitTimeoutMs })

    const p26TeacherResponse = lastTeacherTranscriptText(lessonStore)
    expectRealTeacherResponse(p26TeacherResponse)
    expect(textContent()).toContain('G5 S1 U3 · P26')

    const draftInput = queryRequiredElement<HTMLTextAreaElement>('textarea')
    setControlValue(draftInput, '第一块')
    await flushUi()
    await vi.waitFor(() => {
      expect(queryRequiredElement<HTMLTextAreaElement>('textarea').disabled).toBe(false)
      expect(queryButton('发送').disabled).toBe(false)
    }, { timeout: smokeWaitTimeoutMs })
    clickButton('发送')

    await vi.waitFor(() => {
      const latestTurn = capturedTurnResults.at(-1)
      expect(lessonStore.activeTurn?.turn_label).toBe('navigation')
      expect(lessonStore.runtimeState?.current_block_uid).toBe('TB-G5S1U3-P26-D1')
      expect(lessonStore.runtimeState?.awaiting_answer).toBe(true)
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe(p26TeacherResponse)
      expect(latestTurn?.turn_label).toBe('navigation')
      expect(latestTurn?.state.current_block_uid).toBe('TB-G5S1U3-P26-D1')
      expect(latestTurn?.state.awaiting_answer).toBe(true)
    }, { timeout: smokeWaitTimeoutMs })

    const p26ModuleResponse = lastTeacherTranscriptText(lessonStore)
    setControlValue(draftInput, 'What does snow mean?')
    await flushUi()
    await vi.waitFor(() => {
      expect(queryRequiredElement<HTMLTextAreaElement>('textarea').disabled).toBe(false)
      expect(queryButton('发送').disabled).toBe(false)
    }, { timeout: smokeWaitTimeoutMs })
    clickButton('发送')

    await vi.waitFor(() => {
      const latestTurn = capturedTurnResults.at(-1)
      expect(lessonStore.activeTurn?.turn_label).toBe('ask_knowledge')
      expect(lessonStore.runtimeState?.current_block_uid).toBe('TB-G5S1U3-P26-D1')
      expect(lessonStore.runtimeState?.awaiting_answer).toBe(true)
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe(p26ModuleResponse)
      expect(latestTurn?.turn_label).toBe('ask_knowledge')
      expect(['block', 'page', 'unit']).toContain(latestTurn?.retrieval_mode)
      expect(latestTurn?.state.current_block_uid).toBe('TB-G5S1U3-P26-D1')
      expect(latestTurn?.state.awaiting_answer).toBe(true)
      expect(latestTurn?.support_entry_uids).toContain('KA-G5S1U3-word-snow')
      expect(latestTurn?.teacher_response).toMatch(/snow|雪/i)
    }, { timeout: smokeWaitTimeoutMs })

    const latestTurn = capturedTurnResults.at(-1)
    if (!latestTurn) {
      throw new Error('Expected to capture the real backend P26 in-context snow question turn.')
    }

    expectRealTeacherResponse(latestTurn.teacher_response)
    expect(latestTurn.teacher_response).toMatch(/snow|雪/i)

    if (expectRealLessonDebugSignals) {
      if (!latestTurn.debug_signals) {
        throw new Error('Expected the real backend P26 in-context question turn to include debug_signals. Start LightRAG with PEPTUTOR_DEBUG_SIGNALS=1.')
      }

      expect(latestTurn.debug_signals.live_prompts.enabled).toBe(true)
      expectRenderedDebugSignals(latestTurn.debug_signals)
    }

    logRealSmokeObservation(
      'keeps browser lesson routing stable across P24 -> P25 -> P26 and preserves the P26 in-context snow question',
      startedAtMs,
      latestTurn.teacher_response,
    )

    mountedApp = null
    app.unmount()
  }, smokeTestTimeoutMs)

  it('keeps browser lesson routing stable on G6 P13 while in-context vocabulary questions stay on the dialogue block', async () => {
    const startedAtMs = Date.now()
    const { capturedTurnResults } = installRealLessonApiCapture()
    const { app, lessonStore, router } = await mountLessonPage('/lesson?page_uid=TB-G6S2U2-P13')
    mountedApp = app

    await vi.waitFor(() => {
      const latestTurn = capturedTurnResults.at(-1)
      expect(router.currentRoute.value.query.page_uid).toBe('TB-G6S2U2-P13')
      expect(capturedTurnResults.length).toBeGreaterThanOrEqual(1)
      expect(lessonStore.runtimeState?.current_page_uid).toBe('TB-G6S2U2-P13')
      expect(lessonStore.runtimeState?.current_block_uid).toBe('TB-G6S2U2-P13-D2')
      expect(lessonStore.runtimeState?.awaiting_answer).toBe(true)
      expect(lessonStore.activeTurn?.turn_label).toBe('page_entry')
      expect(latestTurn?.turn_label).toBe('page_entry')
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe('')
    }, { timeout: smokeWaitTimeoutMs })

    const pageEntryTurn = capturedTurnResults.at(-1)
    if (!pageEntryTurn) {
      throw new Error('Expected to capture the real backend G6 page-entry turn.')
    }

    expectRealTeacherResponse(pageEntryTurn.teacher_response)
    expect(/[\u4E00-\u9FFF]/.test(pageEntryTurn.teacher_response)).toBe(true)
    expect(textContent()).toContain('G6 S2 U2 · P13')

    const draftInput = queryRequiredElement<HTMLTextAreaElement>('textarea')
    setControlValue(draftInput, 'What does stayed at home mean?')
    await flushUi()
    clickButton('发送')

    await vi.waitFor(() => {
      const latestTurn = capturedTurnResults.at(-1)
      expect(lessonStore.activeTurn?.turn_label).toBe('ask_knowledge')
      expect(lessonStore.runtimeState?.current_block_uid).toBe('TB-G6S2U2-P13-D2')
      expect(lessonStore.runtimeState?.awaiting_answer).toBe(true)
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe(pageEntryTurn.teacher_response)
      expect(latestTurn?.turn_label).toBe('ask_knowledge')
      expect(latestTurn?.retrieval_mode).toBe('unit')
      expect(latestTurn?.state.current_block_uid).toBe('TB-G6S2U2-P13-D2')
      expect(latestTurn?.state.awaiting_answer).toBe(true)
      expect(latestTurn?.teacher_response).toMatch(/stayed at home|待在家|在家/i)
    }, { timeout: smokeWaitTimeoutMs })

    const stayedHomeTurn = capturedTurnResults.at(-1)
    if (!stayedHomeTurn) {
      throw new Error('Expected to capture the real backend stayed-at-home in-context question turn.')
    }

    expectRealTeacherResponse(stayedHomeTurn.teacher_response)
    expect(/[\u4E00-\u9FFF]/.test(stayedHomeTurn.teacher_response)).toBe(true)
    expect(stayedHomeTurn.teacher_response).toMatch(/stayed at home|待在家|在家/i)

    if (expectRealLessonDebugSignals) {
      if (!stayedHomeTurn.debug_signals) {
        throw new Error('Expected the real backend stayed-at-home in-context question turn to include debug_signals. Start LightRAG with PEPTUTOR_DEBUG_SIGNALS=1.')
      }

      expect(stayedHomeTurn.debug_signals.live_prompts.enabled).toBe(true)
      expectRenderedDebugSignals(stayedHomeTurn.debug_signals)
    }

    setControlValue(draftInput, 'What does had a cold mean?')
    await flushUi()
    clickButton('发送')

    await vi.waitFor(() => {
      const latestTurn = capturedTurnResults.at(-1)
      expect(lessonStore.activeTurn?.turn_label).toBe('ask_knowledge')
      expect(lessonStore.runtimeState?.current_block_uid).toBe('TB-G6S2U2-P13-D2')
      expect(lessonStore.runtimeState?.awaiting_answer).toBe(true)
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe(stayedHomeTurn.teacher_response)
      expect(latestTurn?.turn_label).toBe('ask_knowledge')
      expect(latestTurn?.retrieval_mode).toBe('unit')
      expect(latestTurn?.state.current_block_uid).toBe('TB-G6S2U2-P13-D2')
      expect(latestTurn?.state.awaiting_answer).toBe(true)
      expect(latestTurn?.teacher_response).toMatch(/had a cold|have a cold|感冒/i)
    }, { timeout: smokeWaitTimeoutMs })

    const hadColdTurn = capturedTurnResults.at(-1)
    if (!hadColdTurn) {
      throw new Error('Expected to capture the real backend had-a-cold in-context question turn.')
    }

    expectRealTeacherResponse(hadColdTurn.teacher_response)
    expect(/[\u4E00-\u9FFF]/.test(hadColdTurn.teacher_response)).toBe(true)
    expect(hadColdTurn.teacher_response).toMatch(/had a cold|have a cold|感冒/i)

    if (expectRealLessonDebugSignals) {
      if (!hadColdTurn.debug_signals) {
        throw new Error('Expected the real backend had-a-cold in-context question turn to include debug_signals. Start LightRAG with PEPTUTOR_DEBUG_SIGNALS=1.')
      }

      expect(hadColdTurn.debug_signals.live_prompts.enabled).toBe(true)
      expectRenderedDebugSignals(hadColdTurn.debug_signals)
    }

    logRealSmokeObservation(
      'keeps browser lesson routing stable on G6 P13 while in-context vocabulary questions stay on the dialogue block',
      startedAtMs,
      hadColdTurn.teacher_response,
    )

    mountedApp = null
    app.unmount()
  }, smokeTestTimeoutMs)

  it('keeps non-pilot browser routing stable across G6 Recycle2 page changes and route recovery', async () => {
    const startedAtMs = Date.now()
    const { capturedTurnResults } = installRealLessonApiCapture()
    const { app, lessonStore, router } = await mountLessonPage('/lesson?page_uid=TB-G6S2Recycle2-P49')
    mountedApp = app

    await vi.waitFor(() => {
      const latestTurn = capturedTurnResults.at(-1)
      expect(router.currentRoute.value.query.page_uid).toBe('TB-G6S2Recycle2-P49')
      expect(capturedTurnResults.length).toBeGreaterThanOrEqual(1)
      expect(lessonStore.runtimeState?.current_page_uid).toBe('TB-G6S2Recycle2-P49')
      expect(lessonStore.activeTurn?.turn_label).toBe('page_entry')
      expect(latestTurn?.turn_label).toBe('page_entry')
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe('')
    }, { timeout: smokeWaitTimeoutMs })

    const p49Turn = capturedTurnResults.at(-1)
    if (!p49Turn) {
      throw new Error('Expected to capture the real backend G6 Recycle2 P49 page-entry turn.')
    }

    expectRealTeacherResponse(p49Turn.teacher_response)
    expect(/[\u4E00-\u9FFF]/.test(p49Turn.teacher_response)).toBe(true)

    if (expectRealLessonDebugSignals) {
      if (!p49Turn.debug_signals) {
        throw new Error('Expected the real backend G6 Recycle2 P49 page-entry turn to include debug_signals. Start LightRAG with PEPTUTOR_DEBUG_SIGNALS=1.')
      }

      expect(p49Turn.debug_signals.live_prompts.enabled).toBe(true)
      expectRenderedDebugSignals(p49Turn.debug_signals)
    }

    const p49TeacherResponse = lastTeacherTranscriptText(lessonStore)
    setControlValue(queryPageUidInput(), 'TB-G6S2Recycle2-P51')
    await flushUi()
    clickButton('跳转')

    await vi.waitFor(() => {
      const latestTurn = capturedTurnResults.at(-1)
      expect(router.currentRoute.value.query.page_uid).toBe('TB-G6S2Recycle2-P51')
      expect(queryPageUidInput().value).toBe('TB-G6S2Recycle2-P51')
      expect(lessonStore.runtimeState?.current_page_uid).toBe('TB-G6S2Recycle2-P51')
      expect(lessonStore.activeTurn?.turn_label).toBe('page_entry')
      expect(latestTurn?.turn_label).toBe('page_entry')
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe('')
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe(p49TeacherResponse)
      expect(localStorage.getItem('peptutor/lesson/last-page-uid')).toBe('TB-G6S2Recycle2-P51')
    }, { timeout: smokeWaitTimeoutMs })

    const p51Turn = capturedTurnResults.at(-1)
    if (!p51Turn) {
      throw new Error('Expected to capture the real backend G6 Recycle2 P51 page-entry turn.')
    }

    expectRealTeacherResponse(p51Turn.teacher_response)
    expect(/[\u4E00-\u9FFF]/.test(p51Turn.teacher_response)).toBe(true)

    if (expectRealLessonDebugSignals) {
      if (!p51Turn.debug_signals) {
        throw new Error('Expected the real backend G6 Recycle2 P51 page-entry turn to include debug_signals. Start LightRAG with PEPTUTOR_DEBUG_SIGNALS=1.')
      }

      expect(p51Turn.debug_signals.live_prompts.enabled).toBe(true)
      expectRenderedDebugSignals(p51Turn.debug_signals)
    }

    await router.push('/lesson')
    await flushUi()

    await vi.waitFor(() => {
      expect(router.currentRoute.value.query.page_uid).toBe('TB-G6S2Recycle2-P51')
      expect(queryPageUidInput().value).toBe('TB-G6S2Recycle2-P51')
      expect(lessonStore.runtimeState?.current_page_uid).toBe('TB-G6S2Recycle2-P51')
      expect(lessonStore.selectedPageUid).toBe('TB-G6S2Recycle2-P51')
    }, { timeout: smokeWaitTimeoutMs })

    await router.push('/lesson?page_uid=TB-UNKNOWN-P404')
    await flushUi()

    await vi.waitFor(() => {
      expect(router.currentRoute.value.query.page_uid).toBe('TB-G6S2Recycle2-P51')
      expect(queryPageUidInput().value).toBe('TB-G6S2Recycle2-P51')
      expect(lessonStore.runtimeState?.current_page_uid).toBe('TB-G6S2Recycle2-P51')
      expect(lessonStore.selectedPageUid).toBe('TB-G6S2Recycle2-P51')
    }, { timeout: smokeWaitTimeoutMs })

    const stableTeacherResponse = lastTeacherTranscriptText(lessonStore)
    setControlValue(queryPageUidInput(), 'TB-UNKNOWN-P404')
    await flushUi()
    clickButton('跳转')

    await vi.waitFor(() => {
      expect(router.currentRoute.value.query.page_uid).toBe('TB-G6S2Recycle2-P51')
      expect(queryPageUidInput().value).toBe('TB-G6S2Recycle2-P51')
      expect(lessonStore.runtimeState?.current_page_uid).toBe('TB-G6S2Recycle2-P51')
      expect(lessonStore.selectedPageUid).toBe('TB-G6S2Recycle2-P51')
      expect(lastTeacherTranscriptText(lessonStore)).toBe(stableTeacherResponse)
    }, { timeout: smokeWaitTimeoutMs })

    logRealSmokeObservation(
      'keeps non-pilot browser routing stable across G6 Recycle2 page changes and route recovery',
      startedAtMs,
      p51Turn.teacher_response,
    )

    mountedApp = null
    app.unmount()
  }, smokeTestTimeoutMs)

  itRealDebugSmoke('renders debug_signals from the real backend turn instead of fixture defaults', async () => {
    const { capturedTurnResults } = installRealLessonApiCapture()
    const { app, lessonStore } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(lessonStore.transcript).toHaveLength(1)
      expect(capturedTurnResults.length).toBeGreaterThanOrEqual(1)
      expect(capturedTurnResults.at(-1)?.debug_signals).toBeTruthy()
      expect(textContent()).toContain('本轮能力')
    }, { timeout: smokeWaitTimeoutMs })

    const debugSignals = capturedTurnResults.at(-1)?.debug_signals
    if (!debugSignals) {
      throw new Error('Expected real backend /lesson/turn response to include debug_signals. Start LightRAG with PEPTUTOR_DEBUG_SIGNALS=1.')
    }

    expectRenderedDebugSignals(debugSignals)

    logRealDebugSignalsObservation(
      'renders debug_signals from the real backend turn instead of fixture defaults',
      debugSignals,
    )

    mountedApp = null
    app.unmount()
  }, smokeTestTimeoutMs)

  itRealDebugSmoke('keeps the debug_signals card aligned with the latest real backend turn after learner input', async () => {
    const { capturedTurnResults } = installRealLessonApiCapture()
    const { app, lessonStore } = await mountLessonPage()
    mountedApp = app

    await vi.waitFor(() => {
      expect(capturedTurnResults.length).toBeGreaterThanOrEqual(1)
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe('')
    }, { timeout: smokeWaitTimeoutMs })

    const initialTeacherResponse = lastTeacherTranscriptText(lessonStore)
    const draftInput = queryRequiredElement<HTMLTextAreaElement>('textarea')
    setControlValue(draftInput, `I'd like some water.`)
    await flushUi()
    clickButton('发送')

    await vi.waitFor(() => {
      expect(capturedTurnResults.length).toBeGreaterThanOrEqual(2)
      expect(lessonStore.transcript).toHaveLength(3)
      expect(lastTeacherTranscriptText(lessonStore)).not.toBe(initialTeacherResponse)
    }, { timeout: smokeWaitTimeoutMs })

    const latestTurn = capturedTurnResults.at(-1)
    if (!latestTurn?.debug_signals) {
      throw new Error('Expected latest real backend /lesson/turn response to include debug_signals after learner input.')
    }

    expect(lessonStore.activeTurn?.teacher_response).toBe(latestTurn.teacher_response)
    expectRenderedDebugSignals(latestTurn.debug_signals)

    logRealDebugSignalsObservation(
      'keeps the debug_signals card aligned with the latest real backend turn after learner input',
      latestTurn.debug_signals,
    )

    mountedApp = null
    app.unmount()
  }, smokeTestTimeoutMs)
})
