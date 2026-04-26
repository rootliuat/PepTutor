import type { StageModelRenderer } from '../../stores/settings'

export interface Live2DLipSyncLoopParams {
  paused: boolean
  stageModelRenderer: StageModelRenderer
}

export function shouldRunLive2dLipSyncLoop(params: Live2DLipSyncLoopParams) {
  return params.stageModelRenderer === 'live2d' && !params.paused
}

export function calculateAnalyserMouthOpen(samples: ArrayLike<number>) {
  let peak = 0

  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.abs(Number(samples[i]) || 0)
    if (sample > peak)
      peak = sample
  }

  const normalized = 1 / (1 + Math.exp(-45 * peak + 5))
  return normalized < 0.1 ? 0 : Math.min(1, normalized)
}

export interface Live2DSpeechMouthStateParams {
  analyserMouthOpen: number
  lipSyncMouthOpen: number
  mouthIntensity?: number
  vowelWeights?: Partial<Record<'A' | 'E' | 'I' | 'O' | 'U', number>>
}

export type LessonSpeechStyle = 'normal' | 'slow_split' | 'short_prompt' | 'gentle_correction'

export interface LessonSpeechStyleRuntimeOptions {
  edgeRate: string
  ssmlSpeed: number
}

function clampUnit(value: number | undefined) {
  return Math.max(0, Math.min(1, Number(value) || 0))
}

function clampSignedUnit(value: number | undefined) {
  return Math.max(-1, Math.min(1, Number(value) || 0))
}

export function computeLive2dSpeechMouthState(params: Live2DSpeechMouthStateParams) {
  const lipSyncMouthOpen = clampUnit(params.lipSyncMouthOpen)
  const analyserMouthOpen = clampUnit(params.analyserMouthOpen)
  const mouthOpen = applyLessonMouthIntensity(
    Math.max(lipSyncMouthOpen, analyserMouthOpen * 0.72),
    params.mouthIntensity,
  )

  const A = clampUnit(params.vowelWeights?.A)
  const E = clampUnit(params.vowelWeights?.E)
  const I = clampUnit(params.vowelWeights?.I)
  const O = clampUnit(params.vowelWeights?.O)
  const U = clampUnit(params.vowelWeights?.U)
  const total = A + E + I + O + U

  if (mouthOpen <= 0.02 || total <= 1e-4) {
    return {
      mouthOpen,
      mouthForm: 0,
    }
  }

  // Live2D ParamMouthForm uses positive values for wider/smiling shapes and
  // negative values for rounder shapes.
  const spreadness = I + E * 0.75 + A * 0.2
  const roundness = U + O * 0.75
  const mouthForm = clampSignedUnit(((spreadness - roundness) / total) * 1.35) * Math.min(1, mouthOpen * 1.25)

  return {
    mouthOpen,
    mouthForm,
  }
}

export function applyLessonMouthIntensity(value: number, intensity?: number) {
  const normalizedIntensity = intensity === undefined ? 1 : clampUnit(intensity)
  return clampUnit(clampUnit(value) * normalizedIntensity)
}

export function resolveLessonSpeechStyleRuntimeOptions(style: LessonSpeechStyle | undefined): LessonSpeechStyleRuntimeOptions {
  switch (style) {
    case 'slow_split':
      return {
        edgeRate: '-12%',
        ssmlSpeed: 0.88,
      }
    case 'gentle_correction':
      return {
        edgeRate: '-8%',
        ssmlSpeed: 0.92,
      }
    case 'short_prompt':
      return {
        edgeRate: '+0%',
        ssmlSpeed: 1,
      }
    case 'normal':
    default:
      return {
        edgeRate: '+0%',
        ssmlSpeed: 1,
      }
  }
}
