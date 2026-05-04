import type { TextSegment, TextToken } from '@proj-airi/pipelines-audio'

import { describe, expect, it } from 'vitest'

import { applyLessonMouthIntensity, calculateAnalyserMouthOpen, computeLive2dSpeechMouthState, createLessonSpeechSegmentStream, isLessonRuntimePerformancePayload, resolveLessonSpeechStyleRuntimeOptions, resolveLive2dPerformanceApplyState, resolveLive2dPerformanceMotion, resolveSpeechVoiceForPlayback, shouldRunLive2dLipSyncLoop } from './runtime'

function createTokenStream(text: string): ReadableStream<TextToken> {
  return new ReadableStream<TextToken>({
    start(controller) {
      controller.enqueue({
        type: 'literal',
        value: text,
        streamId: 'stream-1',
        intentId: 'intent-1',
        sequence: 0,
        createdAt: Date.now(),
      })
      controller.close()
    },
  })
}

async function readSegments(stream: ReadableStream<TextSegment>) {
  const reader = stream.getReader()
  const segments: TextSegment[] = []

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done)
        break
      if (value)
        segments.push(value)
    }
  }
  finally {
    reader.releaseLock()
  }

  return segments
}

describe('shouldRunLive2dLipSyncLoop', () => {
  it('runs only for live2d while not paused', () => {
    expect(shouldRunLive2dLipSyncLoop({ stageModelRenderer: 'live2d', paused: false })).toBe(true)
    expect(shouldRunLive2dLipSyncLoop({ stageModelRenderer: 'live2d', paused: true })).toBe(false)
    expect(shouldRunLive2dLipSyncLoop({ stageModelRenderer: 'vrm', paused: false })).toBe(false)
  })
})

describe('calculateAnalyserMouthOpen', () => {
  it('returns zero for silence', () => {
    expect(calculateAnalyserMouthOpen(new Float32Array([0, 0, 0, 0]))).toBe(0)
  })

  it('returns a normalized mouth-open value for louder peaks', () => {
    const quiet = calculateAnalyserMouthOpen(new Float32Array([0.02, -0.02, 0.01]))
    const loud = calculateAnalyserMouthOpen(new Float32Array([0.35, -0.4, 0.28]))

    expect(quiet).toBeGreaterThanOrEqual(0)
    expect(quiet).toBeLessThan(loud)
    expect(loud).toBeGreaterThan(0)
    expect(loud).toBeLessThanOrEqual(1)
  })
})

describe('computeLive2dSpeechMouthState', () => {
  it('stays closed and neutral for silence', () => {
    expect(computeLive2dSpeechMouthState({
      analyserMouthOpen: 0,
      lipSyncMouthOpen: 0,
      vowelWeights: { A: 0, E: 0, I: 0, O: 0, U: 0 },
    })).toEqual({ mouthOpen: 0, mouthForm: 0 })
  })

  it('keeps mouth motion alive from analyser energy when lip-sync open is weak', () => {
    const result = computeLive2dSpeechMouthState({
      analyserMouthOpen: 0.8,
      lipSyncMouthOpen: 0.1,
      vowelWeights: { A: 0.3, E: 0.1, I: 0.2, O: 0.1, U: 0.1 },
    })

    expect(result.mouthOpen).toBeCloseTo(0.576)
    expect(result.mouthForm).toBeGreaterThan(0)
  })

  it('biases round vowels toward negative mouth form', () => {
    const result = computeLive2dSpeechMouthState({
      analyserMouthOpen: 0.6,
      lipSyncMouthOpen: 0.4,
      vowelWeights: { A: 0.05, E: 0.05, I: 0.05, O: 0.4, U: 0.45 },
    })

    expect(result.mouthOpen).toBeGreaterThan(0)
    expect(result.mouthForm).toBeLessThan(0)
  })

  it('scales mouth motion with the lesson AIRI mouth intensity', () => {
    const result = computeLive2dSpeechMouthState({
      analyserMouthOpen: 0.8,
      lipSyncMouthOpen: 0.5,
      mouthIntensity: 0.4,
      vowelWeights: { A: 0.4, E: 0.2, I: 0.1, O: 0.1, U: 0.1 },
    })

    expect(result.mouthOpen).toBeCloseTo(0.2304)
    expect(result.mouthForm).toBeGreaterThan(0)
  })
})

describe('applyLessonMouthIntensity', () => {
  it('keeps normal speech unchanged and clamps lesson intensity bounds', () => {
    expect(applyLessonMouthIntensity(0.7)).toBeCloseTo(0.7)
    expect(applyLessonMouthIntensity(0.7, 0.5)).toBeCloseTo(0.35)
    expect(applyLessonMouthIntensity(0.7, 2)).toBeCloseTo(0.7)
    expect(applyLessonMouthIntensity(0.7, -1)).toBe(0)
  })
})

describe('resolveLessonSpeechStyleRuntimeOptions', () => {
  it('maps lesson speech styles to concrete TTS pacing options', () => {
    expect(resolveLessonSpeechStyleRuntimeOptions('normal')).toEqual({ edgeRate: '+0%', ssmlSpeed: 1 })
    expect(resolveLessonSpeechStyleRuntimeOptions('short_prompt')).toEqual({ edgeRate: '+0%', ssmlSpeed: 1 })
    expect(resolveLessonSpeechStyleRuntimeOptions('slow_split')).toEqual({ edgeRate: '-12%', ssmlSpeed: 0.88 })
    expect(resolveLessonSpeechStyleRuntimeOptions('gentle_correction')).toEqual({ edgeRate: '-8%', ssmlSpeed: 0.92 })
  })
})

describe('resolveSpeechVoiceForPlayback', () => {
  it('uses the loaded voice object when available', () => {
    const voice = {
      id: 'voice-loaded',
      name: 'Loaded voice',
      provider: 'peptutor-edge-tts',
      languages: [{ code: 'zh-CN', title: 'Chinese (Mainland)' }],
    }

    expect(resolveSpeechVoiceForPlayback('peptutor-edge-tts', voice, 'voice-id')).toBe(voice)
  })

  it('falls back to the selected voice id before async voice metadata has loaded', () => {
    expect(resolveSpeechVoiceForPlayback('peptutor-edge-tts', undefined, 'zh-CN-XiaoxiaoNeural')).toEqual({
      id: 'zh-CN-XiaoxiaoNeural',
      name: 'zh-CN-XiaoxiaoNeural',
      description: 'zh-CN-XiaoxiaoNeural',
      previewURL: '',
      languages: [{ code: 'zh-CN', title: 'Chinese (Mainland)' }],
      provider: 'peptutor-edge-tts',
      gender: 'neutral',
    })
  })

  it('returns undefined when neither loaded voice nor selected voice id exists', () => {
    expect(resolveSpeechVoiceForPlayback('peptutor-edge-tts', undefined, '')).toBeUndefined()
  })
})

describe('isLessonRuntimePerformancePayload', () => {
  it('accepts only lesson-owned performance sources', () => {
    expect(isLessonRuntimePerformancePayload({
      performanceSource: 'frontend_lesson_runtime_profile',
    })).toBe(true)
    expect(isLessonRuntimePerformancePayload({
      performanceSource: 'lesson_persona_context',
    })).toBe(true)
    expect(isLessonRuntimePerformancePayload({
      performanceSource: 'generic_chat_emotion',
    })).toBe(false)
    expect(isLessonRuntimePerformancePayload({
      contentSource: 'lesson_runtime_teacher_response',
    })).toBe(false)
    expect(isLessonRuntimePerformancePayload({})).toBe(false)
  })
})

describe('createLessonSpeechSegmentStream', () => {
  it('keeps punctuation-rich lesson replies in a small number of TTS requests', async () => {
    const text = '你好。先练喝的。你说到 pizza 了。现在口渴了，说：I\'d like some water. 再试一次。'
    const segments = await readSegments(createLessonSpeechSegmentStream(
      createTokenStream(text),
      { streamId: 'stream-1', intentId: 'intent-1' },
    ))

    expect(segments).toHaveLength(1)
    expect(segments[0]?.text).toBe(text)
    expect(segments[0]?.reason).toBe('flush')
  })
})

describe('resolveLive2dPerformanceMotion', () => {
  it('uses an exact runtime motion group when the model exposes it', () => {
    expect(resolveLive2dPerformanceMotion('Think', [
      { motionName: 'Idle', motionIndex: 0, fileName: 'idle.motion3.json' },
      { motionName: 'Think', motionIndex: 1, fileName: 'think.motion3.json' },
    ])).toEqual({
      requestedMotion: 'Think',
      appliedMotion: 'Think',
      motion: { group: 'Think', index: 1 },
      status: 'applied',
      fallbackReason: '',
    })
  })

  it('keeps the requested motion pending until the Live2D motion catalog loads', () => {
    expect(resolveLive2dPerformanceMotion('Question', [])).toEqual({
      requestedMotion: 'Question',
      appliedMotion: 'Question',
      motion: { group: 'Question' },
      status: 'pending',
      fallbackReason: 'live2d_motion_catalog_unavailable',
    })
  })

  it('falls back to a visible model motion when the requested group is missing', () => {
    expect(resolveLive2dPerformanceMotion('Explain', [
      { motionName: 'Idle', motionIndex: 0, fileName: 'idle.motion3.json' },
      { motionName: 'Nod', motionIndex: 1, fileName: 'nod.motion3.json' },
    ])).toEqual({
      requestedMotion: 'Explain',
      appliedMotion: 'Nod',
      motion: { group: 'Nod', index: 1 },
      status: 'fallback',
      fallbackReason: 'live2d_motion_unavailable:Explain',
    })
  })

  it('maps high-level lesson motions to available Live2D runtime groups', () => {
    expect(resolveLive2dPerformanceMotion('Happy', [
      { motionName: 'Idle', motionIndex: 0, fileName: 'idle.motion3.json' },
      { motionName: 'Flick', motionIndex: 0, fileName: 'flick.motion3.json' },
      { motionName: 'Tap', motionIndex: 0, fileName: 'tap.motion3.json' },
    ])).toEqual({
      requestedMotion: 'Happy',
      appliedMotion: 'Tap',
      motion: { group: 'Tap', index: 0 },
      status: 'fallback',
      fallbackReason: 'live2d_motion_alias:Happy->Tap',
    })

    expect(resolveLive2dPerformanceMotion('Question', [
      { motionName: 'Idle', motionIndex: 0, fileName: 'idle.motion3.json' },
      { motionName: 'Flick', motionIndex: 0, fileName: 'flick.motion3.json' },
      { motionName: 'FlickDown', motionIndex: 0, fileName: 'flick-down.motion3.json' },
    ])).toEqual({
      requestedMotion: 'Question',
      appliedMotion: 'FlickDown',
      motion: { group: 'FlickDown', index: 0 },
      status: 'fallback',
      fallbackReason: 'live2d_motion_alias:Question->FlickDown',
    })
  })

  it('skips motion application when no backend motion was requested', () => {
    expect(resolveLive2dPerformanceMotion('', [
      { motionName: 'Idle', motionIndex: 0, fileName: 'idle.motion3.json' },
    ])).toEqual({
      requestedMotion: '',
      appliedMotion: '',
      motion: null,
      status: 'skipped',
      fallbackReason: 'motion_not_requested',
    })
  })
})

describe('resolveLive2dPerformanceApplyState', () => {
  it('reports motion-only fallback when the Live2D model cannot apply expressions', () => {
    expect(resolveLive2dPerformanceApplyState({
      motion: 'Think',
      expression: 'focused',
    }, [
      { motionName: 'Idle', motionIndex: 0, fileName: 'idle.motion3.json' },
      { motionName: 'Think', motionIndex: 1, fileName: 'think.motion3.json' },
    ])).toEqual({
      requestedMotion: 'Think',
      appliedMotion: 'Think',
      requestedExpression: 'focused',
      appliedExpression: 'motion-only',
      motion: { group: 'Think', index: 1 },
      status: 'fallback',
      fallbackReason: 'live2d_expression_unavailable:focused',
    })
  })

  it('keeps plan application pending until the model motion catalog is available', () => {
    expect(resolveLive2dPerformanceApplyState({
      motion: 'Question',
      expression: 'think',
    }, [])).toEqual({
      requestedMotion: 'Question',
      appliedMotion: 'Question',
      requestedExpression: 'think',
      appliedExpression: '',
      motion: { group: 'Question' },
      status: 'pending',
      fallbackReason: 'live2d_motion_catalog_unavailable',
    })
  })

  it('marks empty Live2D performance plans unsupported instead of pretending they applied', () => {
    expect(resolveLive2dPerformanceApplyState({}, [
      { motionName: 'Idle', motionIndex: 0, fileName: 'idle.motion3.json' },
    ])).toEqual({
      requestedMotion: '',
      appliedMotion: '',
      requestedExpression: '',
      appliedExpression: '',
      motion: null,
      status: 'unsupported',
      fallbackReason: 'motion_not_requested',
    })
  })
})
