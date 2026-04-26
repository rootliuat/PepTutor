import { describe, expect, it } from 'vitest'

import { applyLessonMouthIntensity, calculateAnalyserMouthOpen, computeLive2dSpeechMouthState, resolveLessonSpeechStyleRuntimeOptions, shouldRunLive2dLipSyncLoop } from './runtime'

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
