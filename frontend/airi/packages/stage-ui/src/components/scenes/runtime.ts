import type { TextSegment, TextToken } from '@proj-airi/pipelines-audio'

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

export interface SpeechVoiceRuntimeOption {
  id: string
  name: string
  description?: string
  previewURL?: string
  languages: Array<{ code: string, title: string }>
  provider: string
  gender?: string
}

export interface Live2DMotionOption {
  motionName: string
  motionIndex?: number
  fileName?: string
}

export type Live2DPerformanceMotionStatus = 'applied' | 'fallback' | 'pending' | 'skipped'
export type Live2DPerformanceApplyStatus = 'applied' | 'fallback' | 'pending' | 'unsupported'

export interface Live2DPerformanceMotionResolution {
  requestedMotion: string
  appliedMotion: string
  motion: { group: string, index?: number } | null
  status: Live2DPerformanceMotionStatus
  fallbackReason: string
}

export interface Live2DPerformanceApplyResolution {
  requestedMotion: string
  appliedMotion: string
  requestedExpression: string
  appliedExpression: string
  motion: { group: string, index?: number } | null
  status: Live2DPerformanceApplyStatus
  fallbackReason: string
}

export interface LessonRuntimePerformancePayload {
  contentSource?: string
  performanceSource?: string
}

const lessonSpeechSegmentMaxChars = 520

const live2dMotionFallbackCandidates: Record<string, string[]> = {
  happy: ['Tap', 'FlickUp', 'Flick', 'Tap@Body', 'Flick@Body'],
  nod: ['Tap', 'FlickUp', 'Flick', 'Tap@Body', 'Flick@Body'],
  encourage: ['Tap', 'FlickUp', 'Flick', 'Tap@Body', 'Flick@Body'],
  curious: ['FlickUp', 'Flick', 'Tap', 'Tap@Body', 'Flick@Body'],
  question: ['FlickDown', 'Flick', 'Tap', 'Flick@Body'],
  think: ['FlickDown', 'Flick', 'Tap', 'Flick@Body'],
  explain: ['FlickDown', 'Flick', 'Tap', 'Flick@Body'],
  listen: ['Flick', 'FlickDown', 'Tap'],
  awkward: ['FlickDown', 'Flick@Body', 'Flick'],
  surprise: ['FlickDown', 'FlickUp', 'Flick', 'Tap'],
  interrupted: ['FlickDown', 'Flick@Body', 'Flick'],
}

function joinFallbackReasons(reasons: string[]) {
  return reasons
    .map(reason => reason.trim())
    .filter(Boolean)
    .join(';')
}

function splitLessonSpeechText(text: string) {
  const normalized = text.trim()
  if (!normalized)
    return []
  if (normalized.length <= lessonSpeechSegmentMaxChars)
    return [normalized]

  const chunks: string[] = []
  let remaining = normalized

  while (remaining.length > lessonSpeechSegmentMaxChars) {
    const windowText = remaining.slice(0, lessonSpeechSegmentMaxChars)
    const punctuationBreak = Math.max(
      windowText.lastIndexOf('。'),
      windowText.lastIndexOf('？'),
      windowText.lastIndexOf('?'),
      windowText.lastIndexOf('！'),
      windowText.lastIndexOf('!'),
    )
    const whitespaceBreak = windowText.lastIndexOf(' ')
    const breakAt = punctuationBreak >= 180
      ? punctuationBreak + 1
      : whitespaceBreak >= 180
        ? whitespaceBreak + 1
        : lessonSpeechSegmentMaxChars

    chunks.push(remaining.slice(0, breakAt).trim())
    remaining = remaining.slice(breakAt).trim()
  }

  if (remaining)
    chunks.push(remaining)

  return chunks
}

export function createLessonSpeechSegmentStream(
  tokens: ReadableStream<TextToken>,
  meta: { streamId: string, intentId: string },
): ReadableStream<TextSegment> {
  let segmentIndex = 0

  return new ReadableStream<TextSegment>({
    async start(controller) {
      const reader = tokens.getReader()
      let pendingText = ''

      const enqueueText = () => {
        for (const text of splitLessonSpeechText(pendingText)) {
          controller.enqueue({
            streamId: meta.streamId,
            intentId: meta.intentId,
            segmentId: `${meta.streamId}:lesson:${segmentIndex++}`,
            text,
            special: null,
            reason: 'flush',
            createdAt: Date.now(),
          })
        }
        pendingText = ''
      }

      try {
        while (true) {
          const { value, done } = await reader.read()
          if (done)
            break
          if (!value)
            continue

          if (value.type === 'literal') {
            pendingText += value.value ?? ''
          }
          else if (value.type === 'special') {
            enqueueText()
            controller.enqueue({
              streamId: meta.streamId,
              intentId: meta.intentId,
              segmentId: `${meta.streamId}:lesson:${segmentIndex++}`,
              text: '',
              special: value.value ?? '',
              reason: 'special',
              createdAt: Date.now(),
            })
          }
        }

        enqueueText()
        controller.close()
      }
      catch (error) {
        controller.error(error)
      }
      finally {
        reader.releaseLock()
      }
    },
  })
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

export function resolveSpeechVoiceForPlayback(
  providerId: string | undefined,
  activeVoice: SpeechVoiceRuntimeOption | undefined,
  activeVoiceId: string | undefined,
): SpeechVoiceRuntimeOption | undefined {
  if (activeVoice?.id?.trim())
    return activeVoice

  const voiceId = activeVoiceId?.trim()
  if (!voiceId)
    return undefined

  const provider = providerId?.trim() || 'unknown'
  return {
    id: voiceId,
    name: voiceId,
    description: voiceId,
    previewURL: '',
    languages: [{ code: 'zh-CN', title: 'Chinese (Mainland)' }],
    provider,
    gender: 'neutral',
  }
}

export function isLessonRuntimePerformancePayload(payload: LessonRuntimePerformancePayload) {
  const performanceSource = payload.performanceSource?.trim()
  return performanceSource === 'frontend_lesson_runtime_profile'
    || performanceSource === 'lesson_persona_context'
}

export function resolveLive2dPerformanceMotion(
  requestedMotion: string | undefined,
  availableMotions: Live2DMotionOption[],
): Live2DPerformanceMotionResolution {
  const normalizedRequest = requestedMotion?.trim() || ''
  if (!normalizedRequest) {
    return {
      requestedMotion: '',
      appliedMotion: '',
      motion: null,
      status: 'skipped',
      fallbackReason: 'motion_not_requested',
    }
  }

  const normalizedMotions = availableMotions
    .filter(motion => motion.motionName?.trim())
    .map(motion => ({
      motionName: motion.motionName.trim(),
      motionIndex: motion.motionIndex,
      fileName: motion.fileName,
    }))

  if (!normalizedMotions.length) {
    return {
      requestedMotion: normalizedRequest,
      appliedMotion: normalizedRequest,
      motion: { group: normalizedRequest },
      status: 'pending',
      fallbackReason: 'live2d_motion_catalog_unavailable',
    }
  }

  const exactMatch = normalizedMotions.find(motion =>
    motion.motionName.toLocaleLowerCase() === normalizedRequest.toLocaleLowerCase(),
  )
  if (exactMatch) {
    return {
      requestedMotion: normalizedRequest,
      appliedMotion: exactMatch.motionName,
      motion: { group: exactMatch.motionName, index: exactMatch.motionIndex },
      status: 'applied',
      fallbackReason: '',
    }
  }

  const candidateNames = live2dMotionFallbackCandidates[normalizedRequest.toLocaleLowerCase()] ?? []
  const semanticFallback = candidateNames
    .map(candidate => normalizedMotions.find(motion =>
      motion.motionName.toLocaleLowerCase() === candidate.toLocaleLowerCase(),
    ))
    .find(Boolean)
  if (semanticFallback) {
    return {
      requestedMotion: normalizedRequest,
      appliedMotion: semanticFallback.motionName,
      motion: { group: semanticFallback.motionName, index: semanticFallback.motionIndex },
      status: 'fallback',
      fallbackReason: `live2d_motion_alias:${normalizedRequest}->${semanticFallback.motionName}`,
    }
  }

  const fallback = normalizedMotions.find(motion =>
    motion.motionName.toLocaleLowerCase() !== 'idle',
  ) || normalizedMotions[0]
  return {
    requestedMotion: normalizedRequest,
    appliedMotion: fallback.motionName,
    motion: { group: fallback.motionName, index: fallback.motionIndex },
    status: 'fallback',
    fallbackReason: `live2d_motion_unavailable:${normalizedRequest}`,
  }
}

export function resolveLive2dPerformanceApplyState(
  profile: { motion?: string, expression?: string },
  availableMotions: Live2DMotionOption[],
): Live2DPerformanceApplyResolution {
  const motionResolution = resolveLive2dPerformanceMotion(profile.motion, availableMotions)
  const requestedExpression = profile.expression?.trim() || ''
  const fallbackReasons = [motionResolution.fallbackReason]

  let status: Live2DPerformanceApplyStatus
  let appliedExpression = ''

  if (motionResolution.status === 'pending') {
    status = 'pending'
  }
  else if (motionResolution.status === 'skipped') {
    status = 'unsupported'
  }
  else if (requestedExpression) {
    status = 'fallback'
    appliedExpression = 'motion-only'
    fallbackReasons.push(`live2d_expression_unavailable:${requestedExpression}`)
  }
  else if (motionResolution.status === 'fallback') {
    status = 'fallback'
  }
  else {
    status = 'applied'
  }

  return {
    requestedMotion: motionResolution.requestedMotion,
    appliedMotion: motionResolution.appliedMotion,
    requestedExpression,
    appliedExpression,
    motion: motionResolution.motion,
    status,
    fallbackReason: joinFallbackReasons(fallbackReasons),
  }
}
