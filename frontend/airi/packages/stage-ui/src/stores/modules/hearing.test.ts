import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useProvidersStore } from '../providers'
import { useHearingSpeechInputPipeline, useHearingStore } from './hearing'

const transcriptionMocks = vi.hoisted(() => ({
  streamDoubaoRealtimeTranscription: vi.fn(),
}))

vi.mock('../providers/volcengine/stream-transcription', () => ({
  streamDoubaoRealtimeTranscription: transcriptionMocks.streamDoubaoRealtimeTranscription,
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
  }),
}))

class FakeSpeechRecognition {
  static lastInstance: FakeSpeechRecognition | undefined
  static completeOnStop = true

  continuous = true
  interimResults = true
  maxAlternatives = 1
  lang = 'en-US'
  onresult: ((event: unknown) => void) | undefined
  onend: (() => void) | undefined
  onstart: (() => void) | undefined
  onaudiostart: (() => void) | undefined
  onsoundstart: (() => void) | undefined
  onspeechstart: (() => void) | undefined
  onspeechend: (() => void) | undefined
  onsoundend: (() => void) | undefined
  onaudioend: (() => void) | undefined
  onnomatch: (() => void) | undefined
  onerror: ((event: unknown) => void) | undefined
  start = vi.fn(() => {
    this.onstart?.()
  })

  stop = vi.fn(() => {
    if (FakeSpeechRecognition.completeOnStop)
      this.onend?.()
  })

  constructor() {
    FakeSpeechRecognition.lastInstance = this
  }

  emitFinalTranscript(text: string) {
    const result = {
      0: { transcript: text },
      isFinal: true,
    }
    this.onresult?.({
      resultIndex: 0,
      results: [result],
    })
  }
}

describe('hearing speech input pipeline', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('window', {
      webkitSpeechRecognition: FakeSpeechRecognition,
    })
    FakeSpeechRecognition.lastInstance = undefined
    FakeSpeechRecognition.completeOnStop = true
    transcriptionMocks.streamDoubaoRealtimeTranscription.mockReset()
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('gracefully stops browser Web Speech push-to-talk and returns final text', async () => {
    const hearingStore = useHearingStore()
    hearingStore.activeTranscriptionProvider = 'browser-web-speech-api'

    const pipeline = useHearingSpeechInputPipeline()
    const finalDeltas: string[] = []

    await pipeline.transcribeForMediaStream({ id: 'test-stream' } as MediaStream, {
      onSentenceEnd: delta => finalDeltas.push(delta),
    })

    const recognition = FakeSpeechRecognition.lastInstance
    expect(recognition).toBeDefined()

    recognition!.emitFinalTranscript('salad')
    const stoppedText = await pipeline.stopStreamingTranscription(false)

    expect(finalDeltas).toEqual(['salad'])
    expect(stoppedText?.trim()).toBe('salad')
    expect(recognition!.continuous).toBe(false)
    expect(recognition!.stop).toHaveBeenCalledTimes(1)
  })

  it('does not hang when browser Web Speech stop does not emit an end event', async () => {
    vi.useFakeTimers()
    FakeSpeechRecognition.completeOnStop = false
    const hearingStore = useHearingStore()
    hearingStore.activeTranscriptionProvider = 'browser-web-speech-api'

    const pipeline = useHearingSpeechInputPipeline()
    await pipeline.transcribeForMediaStream({ id: 'test-stream' } as MediaStream)

    const stoppedText = pipeline.stopStreamingTranscription(false)
    await vi.advanceTimersByTimeAsync(1600)

    await expect(stoppedText).resolves.toBeUndefined()
    expect(FakeSpeechRecognition.lastInstance!.continuous).toBe(false)
    expect(FakeSpeechRecognition.lastInstance!.stop).toHaveBeenCalledTimes(1)
  })

  it('closes realtime provider audio on graceful stop without aborting final transcript', async () => {
    class FakeAudioContext {
      state = 'running'
      destination = {}
      audioWorklet = {
        addModule: vi.fn(async () => {}),
      }

      createMediaStreamSource = vi.fn(() => ({
        connect: vi.fn(),
        disconnect: vi.fn(),
      }))

      createGain = vi.fn(() => ({
        gain: { value: 0 },
        connect: vi.fn(),
      }))

      close = vi.fn(async () => {})
      resume = vi.fn(async () => {})
    }

    class FakeAudioWorkletNode {
      port: { onmessage: ((event: MessageEvent<{ buffer?: Float32Array }>) => void) | null } = {
        onmessage: null,
      }

      connect = vi.fn()
      disconnect = vi.fn()
    }

    vi.stubGlobal('AudioContext', FakeAudioContext)
    vi.stubGlobal('AudioWorkletNode', FakeAudioWorkletNode)

    const hearingStore = useHearingStore()
    hearingStore.activeTranscriptionProvider = 'volcengine-realtime-transcription'
    hearingStore.activeTranscriptionModel = 'fake-realtime-model'

    const providersStore = useProvidersStore()
    vi.spyOn(providersStore, 'getProviderInstance').mockResolvedValue({
      transcription: (_model: string, extraOptions?: Record<string, unknown>) => ({
        baseURL: 'ws://example.test/asr',
        model: 'fake-realtime-model',
        ...extraOptions,
      }),
    } as any)

    let abortSignal: AbortSignal | undefined
    transcriptionMocks.streamDoubaoRealtimeTranscription.mockImplementation((options: {
      abortSignal?: AbortSignal
      inputAudioStream: ReadableStream<ArrayBuffer>
    }) => {
      abortSignal = options.abortSignal
      const text = (async () => {
        const reader = options.inputAudioStream.getReader()
        while (true) {
          const { done } = await reader.read()
          if (done)
            return 'salad'
        }
      })()
      return {
        mode: 'stream',
        text,
        textStream: new ReadableStream<string>({
          start(controller) {
            controller.close()
          },
        }),
      }
    })

    const pipeline = useHearingSpeechInputPipeline()
    await pipeline.transcribeForMediaStream({ id: 'test-stream' } as MediaStream)
    const stoppedText = await pipeline.stopStreamingTranscription(false)

    expect(stoppedText).toBe('salad')
    expect(abortSignal?.aborted).toBe(false)
  })
})
