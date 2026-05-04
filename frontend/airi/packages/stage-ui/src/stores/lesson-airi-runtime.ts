import type { EmotionPayload } from '../constants/emotions'
import type { AudioPermissionState } from './settings/audio-device'

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { normalizeLessonPlaybackStopReason } from '../utils/lesson-interrupt-policy'

export type LessonAiriMicrophoneStatus
  = | 'unavailable'
    | 'requesting'
    | 'denied'
    | 'off'
    | 'ready'
    | 'listening'
    | 'speaking'

export type LessonAiriClassroomState
  = | 'idle'
    | 'listening'
    | 'learner_speaking'
    | 'thinking'
    | 'teacher_speaking'
    | 'interrupted'

export type LessonAiriSpeechStyle = NonNullable<EmotionPayload['speechStyle']>
export type LessonAiriInterruptPolicy = NonNullable<EmotionPayload['interruptPolicy']>
export type LessonAiriSpeechPlaybackStatus
  = | 'idle'
    | 'synthesizing'
    | 'decoded'
    | 'playing'
    | 'ended'
    | 'interrupted'
    | 'error'

export type LessonAiriTtsSynthesisState
  = | 'idle'
    | 'requesting'
    | 'http_ok'
    | 'http_error'
    | 'empty_audio'
    | 'unsupported_provider'

export type LessonAiriTtsPlaybackState
  = | 'idle'
    | 'play_requested'
    | 'playing'
    | 'play_resolved'
    | 'play_rejected'
    | 'autoplay_blocked'
    | 'audio_context_suspended'
    | 'ended'
    | 'interrupted'
    | 'skipped'

export type LessonAiriSpeechFailureStage
  = | 'configuration'
    | 'missing_audio'
    | 'audio_context'
    | 'synthesis'
    | 'empty_audio'
    | 'decode'
    | 'playback'

export type LessonAiriPerformanceApplyStatus
  = | 'idle'
    | 'pending'
    | 'applied'
    | 'fallback'
    | 'unsupported'
    | 'error'

export type LessonAiriPerformanceFallbackKind
  = | ''
    | 'known_capability_gap'
    | 'motion_alias'
    | 'motion_unavailable'
    | 'runtime_unsupported'
    | 'runtime_error'
    | 'unknown'

export interface LessonAiriPerformancePlanState {
  emotionName: string
  emotionIntensity: number
  motion: string
  expression: string
  durationMs: number | null
  reason: string
  teachingAction: string
  evaluation: string | null
  turnLabel: string
  speechStyle: LessonAiriSpeechStyle
  mouthIntensity: number
  interruptPolicy: LessonAiriInterruptPolicy
  contentSource: string
  fallbackAllowed: boolean | null
  performanceSource: string
  updatedAt: number
}

type LessonAiriPerformancePlanFingerprint = Omit<LessonAiriPerformancePlanState, 'updatedAt'>

function clampUnit(value: number | undefined, fallback: number) {
  if (typeof value !== 'number' || Number.isNaN(value))
    return fallback
  return Math.min(1, Math.max(0, value))
}

function formatDurationMs(value: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value))
    return ''
  return `${Math.max(0, Math.round(value))}ms`
}

function formatByteLength(value: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value))
    return ''
  if (value < 1024)
    return `${Math.max(0, Math.round(value))}B`
  return `${(value / 1024).toFixed(1)}KB`
}

function classifyPerformanceFallback(reason: string): LessonAiriPerformanceFallbackKind {
  const normalized = reason.trim()
  if (!normalized)
    return ''
  if (normalized.includes('live2d_expression_unavailable'))
    return 'known_capability_gap'
  if (normalized.includes('live2d_motion_alias'))
    return 'motion_alias'
  if (normalized.includes('live2d_motion_unavailable'))
    return 'motion_unavailable'
  if (normalized.includes('runtime_error'))
    return 'runtime_error'
  if (normalized.includes('unsupported'))
    return 'runtime_unsupported'
  return 'unknown'
}

function isActivePlaybackState(state: LessonAiriTtsPlaybackState) {
  return state === 'play_requested' || state === 'playing'
}

function fingerprintPerformancePlan(plan: LessonAiriPerformancePlanState): string {
  const stablePlan: LessonAiriPerformancePlanFingerprint = {
    emotionName: plan.emotionName,
    emotionIntensity: plan.emotionIntensity,
    motion: plan.motion,
    expression: plan.expression,
    durationMs: plan.durationMs,
    reason: plan.reason,
    teachingAction: plan.teachingAction,
    evaluation: plan.evaluation,
    turnLabel: plan.turnLabel,
    speechStyle: plan.speechStyle,
    mouthIntensity: plan.mouthIntensity,
    interruptPolicy: plan.interruptPolicy,
    contentSource: plan.contentSource,
    fallbackAllowed: plan.fallbackAllowed,
    performanceSource: plan.performanceSource,
  }

  return JSON.stringify(stablePlan)
}

export const useLessonAiriRuntimeStore = defineStore('lesson-airi-runtime', () => {
  const microphoneEnabled = ref(false)
  const microphoneReady = ref(false)
  const microphoneInputDeviceLabel = ref('')
  const microphoneUnavailableReason = ref('')
  const microphonePermissionState = ref<AudioPermissionState>('unknown')
  const microphonePermissionError = ref('')
  const hearingListening = ref(false)
  const teacherSpeaking = ref(false)
  const hearingConfigured = ref(false)
  const supportsStreamInput = ref(false)
  const autoSendEnabled = ref(false)
  const autoSendDelay = ref(0)
  const inputVolumeLevel = ref(0)
  const liveTranscriptText = ref('')
  const liveTranscriptUpdatedAt = ref(0)
  const lastRecognizedText = ref('')
  const lastRecognizedAt = ref(0)
  const lastMicInteractionAt = ref(0)
  const classroomState = ref<LessonAiriClassroomState>('idle')
  const classroomStateUpdatedAt = ref(0)
  const currentPerformancePlan = ref<LessonAiriPerformancePlanState | null>(null)
  const performanceApplyStatus = ref<LessonAiriPerformanceApplyStatus>('idle')
  const requestedMotion = ref('')
  const appliedMotion = ref('')
  const requestedExpression = ref('')
  const appliedExpression = ref('')
  const performanceFallbackReason = ref('')
  const performanceFallbackKind = ref<LessonAiriPerformanceFallbackKind>('')
  const performanceApplyUpdatedAt = ref(0)
  const speechPlaybackStatus = ref<LessonAiriSpeechPlaybackStatus>('idle')
  const ttsSynthesisState = ref<LessonAiriTtsSynthesisState>('idle')
  const ttsPlaybackState = ref<LessonAiriTtsPlaybackState>('idle')
  const ttsPlaybackReason = ref('')
  const ttsPlaybackId = ref('')
  const activeReplyId = ref('')
  const ttsPlaybackStopReason = ref('')
  const ttsPlaybackNormalizedStopReason = ref('')
  const ttsPlaybackOverlapDetected = ref(false)
  const ttsPlaybackOverlapCount = ref(0)
  const speechPlaybackError = ref('')
  const speechPlaybackProvider = ref('')
  const speechPlaybackModel = ref('')
  const speechPlaybackVoice = ref('')
  const speechPlaybackText = ref('')
  const speechPlaybackUpdatedAt = ref(0)
  const speechPlaybackFailureStage = ref<LessonAiriSpeechFailureStage | ''>('')
  const speechPlaybackAudioContextState = ref('')
  const speechSynthesisHttpStatus = ref<number | null>(null)
  const speechSynthesisHttpStatusText = ref('')
  const speechAudioByteLength = ref<number | null>(null)
  const speechAudioDurationMs = ref<number | null>(null)
  const speechSynthesisStartedAt = ref(0)
  const speechSynthesisReadyAt = ref(0)
  const speechPlaybackStartedAt = ref(0)
  const speechPlaybackEndedAt = ref(0)
  const speechSynthesisLatencyMs = ref<number | null>(null)
  const speechPlaybackStartupLatencyMs = ref<number | null>(null)
  const speechPlaybackDurationMs = ref<number | null>(null)

  const microphoneStatus = computed<LessonAiriMicrophoneStatus>(() => {
    if (microphoneUnavailableReason.value)
      return 'unavailable'
    if (microphonePermissionState.value === 'requesting')
      return 'requesting'
    if (microphonePermissionState.value === 'denied')
      return 'denied'
    if (hearingListening.value && inputVolumeLevel.value >= 8)
      return 'speaking'
    if (hearingListening.value)
      return 'listening'
    if (microphoneEnabled.value && microphoneReady.value)
      return 'ready'
    return 'off'
  })

  const microphoneStatusLabel = computed(() => {
    switch (microphoneStatus.value) {
      case 'unavailable':
        return microphoneUnavailableReason.value || 'Microphone unavailable'
      case 'requesting':
        return '正在请求麦克风权限'
      case 'denied':
        return microphonePermissionError.value || '麦克风权限被拒绝'
      case 'speaking':
        return '学生正在说话'
      case 'listening':
        return '正在听'
      case 'ready':
        return '麦克风已开'
      case 'off':
      default:
        return '麦克风关闭'
    }
  })

  const currentSpeechStyle = computed<LessonAiriSpeechStyle>(() =>
    currentPerformancePlan.value?.speechStyle || 'normal',
  )
  const currentMouthIntensity = computed(() =>
    currentPerformancePlan.value?.mouthIntensity ?? 1,
  )
  const currentInterruptPolicy = computed<LessonAiriInterruptPolicy>(() =>
    currentPerformancePlan.value?.interruptPolicy || 'barge_in_allowed',
  )
  const canBargeInDuringTeacherSpeech = computed(() =>
    currentInterruptPolicy.value === 'barge_in_allowed',
  )
  const canDriveMouthOpen = computed(() =>
    ttsPlaybackState.value === 'playing',
  )
  const ttsSynthesisStateLabel = computed(() => {
    switch (ttsSynthesisState.value) {
      case 'requesting':
        return 'requesting'
      case 'http_ok':
        return 'http_ok'
      case 'http_error':
        return 'http_error'
      case 'empty_audio':
        return 'empty_audio'
      case 'unsupported_provider':
        return 'unsupported_provider'
      case 'idle':
      default:
        return 'idle'
    }
  })
  const ttsPlaybackStateLabel = computed(() => {
    switch (ttsPlaybackState.value) {
      case 'play_requested':
        return 'play_requested'
      case 'playing':
        return 'playing'
      case 'play_resolved':
        return 'play_resolved'
      case 'play_rejected':
        return 'play_rejected'
      case 'autoplay_blocked':
        return 'autoplay_blocked'
      case 'audio_context_suspended':
        return 'audio_context_suspended'
      case 'ended':
        return 'ended'
      case 'interrupted':
        return 'interrupted'
      case 'skipped':
        return 'skipped'
      case 'idle':
      default:
        return 'idle'
    }
  })
  const speechPlaybackStatusLabel = computed(() => {
    switch (speechPlaybackStatus.value) {
      case 'synthesizing':
        return 'TTS 合成中'
      case 'decoded':
        return 'TTS 已生成'
      case 'playing':
        return '正在播放'
      case 'ended':
        return '播放结束'
      case 'interrupted':
        return '已打断'
      case 'error':
        return speechPlaybackError.value || 'TTS 播放失败'
      case 'idle':
      default:
        return '待命'
    }
  })
  const speechPlaybackDebugLabel = computed(() => {
    const parts = [speechPlaybackStatusLabel.value]
    const providerLabel = [speechPlaybackProvider.value, speechPlaybackVoice.value]
      .map(value => value.trim())
      .filter(Boolean)
      .join('/')
    const synthesisLatencyLabel = formatDurationMs(speechSynthesisLatencyMs.value)
    const startupLatencyLabel = formatDurationMs(speechPlaybackStartupLatencyMs.value)
    const playbackDurationLabel = formatDurationMs(speechPlaybackDurationMs.value)
    const audioBytesLabel = formatByteLength(speechAudioByteLength.value)

    if (providerLabel)
      parts.push(providerLabel)
    if (typeof speechSynthesisHttpStatus.value === 'number')
      parts.push(`HTTP ${speechSynthesisHttpStatus.value}${speechSynthesisHttpStatusText.value ? ` ${speechSynthesisHttpStatusText.value}` : ''}`)
    if (speechPlaybackFailureStage.value)
      parts.push(`stage=${speechPlaybackFailureStage.value}`)
    if (ttsSynthesisState.value !== 'idle' || ttsPlaybackState.value !== 'idle') {
      parts.push(`synthesis=${ttsSynthesisState.value}`)
      parts.push(`playback=${ttsPlaybackState.value}`)
      if (ttsPlaybackId.value)
        parts.push(`playback_id=${ttsPlaybackId.value}`)
      if (activeReplyId.value)
        parts.push(`reply=${activeReplyId.value}`)
      if (ttsPlaybackReason.value)
        parts.push(`reason=${ttsPlaybackReason.value}`)
      if (ttsPlaybackStopReason.value)
        parts.push(`stop=${ttsPlaybackStopReason.value}`)
      if (ttsPlaybackNormalizedStopReason.value)
        parts.push(`stop_type=${ttsPlaybackNormalizedStopReason.value}`)
      if (ttsPlaybackOverlapDetected.value)
        parts.push(`overlap=true/${ttsPlaybackOverlapCount.value}`)
    }
    if (audioBytesLabel)
      parts.push(audioBytesLabel)
    if (speechAudioDurationMs.value !== null) {
      const audioDurationLabel = formatDurationMs(speechAudioDurationMs.value)
      if (audioDurationLabel)
        parts.push(`audio=${audioDurationLabel}`)
    }
    if (synthesisLatencyLabel)
      parts.push(`tts=${synthesisLatencyLabel}`)
    if (startupLatencyLabel)
      parts.push(`start=${startupLatencyLabel}`)
    if (playbackDurationLabel)
      parts.push(`play=${playbackDurationLabel}`)
    if (speechPlaybackAudioContextState.value)
      parts.push(`ctx=${speechPlaybackAudioContextState.value}`)

    return parts.join(' · ')
  })
  const performanceApplyStatusLabel = computed(() => {
    switch (performanceApplyStatus.value) {
      case 'pending':
        return '等待应用'
      case 'applied':
        return '已应用'
      case 'fallback':
        return '已降级'
      case 'unsupported':
        return '不支持'
      case 'error':
        return performanceFallbackReason.value || '表现层错误'
      case 'idle':
      default:
        return '待命'
    }
  })

  function updateMicrophoneState(next: {
    enabled: boolean
    ready: boolean
    inputDeviceLabel?: string
    unavailableReason?: string
    permissionState: AudioPermissionState
    permissionError?: string
    configured: boolean
    streamInput: boolean
    listening: boolean
    autoSend: boolean
    autoSendDelayMs: number
  }) {
    microphoneEnabled.value = next.enabled
    microphoneReady.value = next.ready
    microphoneInputDeviceLabel.value = next.inputDeviceLabel || ''
    microphoneUnavailableReason.value = next.unavailableReason || ''
    microphonePermissionState.value = next.permissionState
    microphonePermissionError.value = next.permissionError || ''
    hearingConfigured.value = next.configured
    supportsStreamInput.value = next.streamInput
    hearingListening.value = next.listening
    autoSendEnabled.value = next.autoSend
    autoSendDelay.value = next.autoSendDelayMs
  }

  function updateInputVolume(level: number) {
    inputVolumeLevel.value = Math.min(100, Math.max(0, Number.isFinite(level) ? level : 0))
  }

  function setTeacherSpeaking(value: boolean) {
    teacherSpeaking.value = value
    if (value)
      setClassroomState('teacher_speaking')
  }

  function markSpeechSynthesisStart(next: {
    provider: string
    model: string
    voice: string
    text: string
    replyId?: string
  }) {
    const now = Date.now()
    const playbackActive = isActivePlaybackState(ttsPlaybackState.value)
    if (!playbackActive)
      speechPlaybackStatus.value = 'synthesizing'
    ttsSynthesisState.value = 'requesting'
    if (!playbackActive) {
      ttsPlaybackState.value = 'idle'
      ttsPlaybackReason.value = ''
      ttsPlaybackNormalizedStopReason.value = ''
      speechPlaybackAudioContextState.value = ''
      speechPlaybackStartedAt.value = 0
      speechPlaybackEndedAt.value = 0
      speechPlaybackStartupLatencyMs.value = null
      speechPlaybackDurationMs.value = null
    }
    speechPlaybackError.value = ''
    speechPlaybackProvider.value = next.provider
    speechPlaybackModel.value = next.model
    speechPlaybackVoice.value = next.voice
    speechPlaybackText.value = next.text
    if (!isActivePlaybackState(ttsPlaybackState.value) && next.replyId?.trim())
      activeReplyId.value = next.replyId.trim()
    speechPlaybackUpdatedAt.value = now
    speechPlaybackFailureStage.value = ''
    speechSynthesisHttpStatus.value = null
    speechSynthesisHttpStatusText.value = ''
    speechAudioByteLength.value = null
    speechAudioDurationMs.value = null
    speechSynthesisStartedAt.value = now
    speechSynthesisReadyAt.value = 0
    speechSynthesisLatencyMs.value = null
  }

  function markSpeechSynthesisHttpResult(next: {
    status: number
    statusText?: string
  }) {
    if (!Number.isFinite(next.status))
      return
    const status = Math.trunc(next.status)
    speechSynthesisHttpStatus.value = status
    speechSynthesisHttpStatusText.value = next.statusText?.trim() || ''
    ttsSynthesisState.value = status >= 200 && status < 300 ? 'http_ok' : 'http_error'
  }

  function markSpeechSynthesisReady(next: {
    audioByteLength?: number
    audioDurationMs?: number
  } = {}) {
    const now = Date.now()
    if (speechSynthesisHttpStatus.value === null)
      ttsSynthesisState.value = 'http_ok'
    if (!isActivePlaybackState(ttsPlaybackState.value))
      speechPlaybackStatus.value = 'decoded'
    speechPlaybackError.value = ''
    speechPlaybackUpdatedAt.value = now
    speechSynthesisReadyAt.value = now
    speechSynthesisLatencyMs.value = speechSynthesisStartedAt.value > 0
      ? now - speechSynthesisStartedAt.value
      : null
    if (typeof next.audioByteLength === 'number' && Number.isFinite(next.audioByteLength))
      speechAudioByteLength.value = Math.max(0, Math.trunc(next.audioByteLength))
    if (typeof next.audioDurationMs === 'number' && Number.isFinite(next.audioDurationMs))
      speechAudioDurationMs.value = Math.max(0, Math.round(next.audioDurationMs))
  }

  function markSpeechPlaybackRequested(next: {
    playbackId?: string
    replyId?: string
    audioContextState?: string
    reason?: string
  } = {}) {
    const nextPlaybackId = next.playbackId?.trim() || ttsPlaybackId.value
    const nextReplyId = next.replyId?.trim() || activeReplyId.value
    if (isActivePlaybackState(ttsPlaybackState.value) && ttsPlaybackId.value && nextPlaybackId && ttsPlaybackId.value !== nextPlaybackId) {
      ttsPlaybackOverlapDetected.value = true
      ttsPlaybackOverlapCount.value += 1
    }
    ttsPlaybackId.value = nextPlaybackId
    activeReplyId.value = nextReplyId
    ttsPlaybackState.value = 'play_requested'
    ttsPlaybackReason.value = next.reason?.trim() || ''
    ttsPlaybackStopReason.value = ''
    ttsPlaybackNormalizedStopReason.value = ''
    speechPlaybackAudioContextState.value = next.audioContextState?.trim() || ''
    speechPlaybackUpdatedAt.value = Date.now()
    setTeacherSpeaking(false)
  }

  function markSpeechPlaybackStart(next: {
    playbackId?: string
    replyId?: string
    audioContextState?: string
  } = {}) {
    const now = Date.now()
    const nextPlaybackId = next.playbackId?.trim() || ttsPlaybackId.value
    const nextReplyId = next.replyId?.trim() || activeReplyId.value
    if (isActivePlaybackState(ttsPlaybackState.value) && ttsPlaybackId.value && nextPlaybackId && ttsPlaybackId.value !== nextPlaybackId) {
      ttsPlaybackOverlapDetected.value = true
      ttsPlaybackOverlapCount.value += 1
    }
    ttsPlaybackId.value = nextPlaybackId
    activeReplyId.value = nextReplyId
    speechPlaybackStatus.value = 'playing'
    ttsPlaybackState.value = 'playing'
    ttsPlaybackReason.value = ''
    ttsPlaybackStopReason.value = ''
    ttsPlaybackNormalizedStopReason.value = ''
    speechPlaybackError.value = ''
    speechPlaybackUpdatedAt.value = now
    speechPlaybackStartedAt.value = now
    speechPlaybackAudioContextState.value = next.audioContextState?.trim() || ''
    speechPlaybackStartupLatencyMs.value = speechSynthesisReadyAt.value > 0
      ? now - speechSynthesisReadyAt.value
      : null
    setTeacherSpeaking(true)
  }

  function isCurrentPlaybackEvent(playbackId?: string) {
    const normalizedPlaybackId = playbackId?.trim() || ''
    return !normalizedPlaybackId || !ttsPlaybackId.value || normalizedPlaybackId === ttsPlaybackId.value
  }

  function markSpeechPlaybackEnd(status: Extract<LessonAiriSpeechPlaybackStatus, 'ended' | 'interrupted'> = 'ended', next: {
    playbackId?: string
    replyId?: string
    stopReason?: string
  } = {}) {
    if (!isCurrentPlaybackEvent(next.playbackId))
      return

    const now = Date.now()
    if (next.playbackId?.trim())
      ttsPlaybackId.value = next.playbackId.trim()
    if (next.replyId?.trim())
      activeReplyId.value = next.replyId.trim()
    speechPlaybackStatus.value = status
    ttsPlaybackState.value = status === 'ended' ? 'ended' : 'interrupted'
    ttsPlaybackStopReason.value = next.stopReason?.trim() || status
    ttsPlaybackNormalizedStopReason.value = normalizeLessonPlaybackStopReason(ttsPlaybackStopReason.value)
    ttsPlaybackReason.value = ttsPlaybackStopReason.value
    speechPlaybackUpdatedAt.value = now
    speechPlaybackEndedAt.value = now
    speechPlaybackDurationMs.value = speechPlaybackStartedAt.value > 0
      ? now - speechPlaybackStartedAt.value
      : null
    setTeacherSpeaking(false)
  }

  function markSpeechPlaybackError(message: string, next: {
    playbackId?: string
    replyId?: string
    stage?: LessonAiriSpeechFailureStage
    httpStatus?: number | null
    httpStatusText?: string
    playbackState?: Extract<LessonAiriTtsPlaybackState, 'play_rejected' | 'autoplay_blocked' | 'audio_context_suspended' | 'skipped'>
    reason?: string
  } = {}) {
    if (!isCurrentPlaybackEvent(next.playbackId))
      return

    const stage = next.stage || ''
    if (next.playbackId?.trim())
      ttsPlaybackId.value = next.playbackId.trim()
    if (next.replyId?.trim())
      activeReplyId.value = next.replyId.trim()
    speechPlaybackStatus.value = 'error'
    speechPlaybackError.value = message.trim() || 'TTS 播放失败'
    speechPlaybackFailureStage.value = stage
    ttsPlaybackState.value = next.playbackState
      || (stage === 'audio_context'
        ? 'audio_context_suspended'
        : stage === 'playback'
          ? 'play_rejected'
          : 'skipped')
    ttsPlaybackReason.value = next.reason?.trim() || speechPlaybackError.value
    ttsPlaybackStopReason.value = next.reason?.trim() || ''
    ttsPlaybackNormalizedStopReason.value = normalizeLessonPlaybackStopReason(
      ttsPlaybackStopReason.value || ttsPlaybackState.value,
    )
    if (stage === 'configuration')
      ttsSynthesisState.value = 'unsupported_provider'
    else if (stage === 'empty_audio')
      ttsSynthesisState.value = 'empty_audio'
    else if (stage === 'synthesis')
      ttsSynthesisState.value = 'http_error'
    if (typeof next.httpStatus === 'number' && Number.isFinite(next.httpStatus)) {
      speechSynthesisHttpStatus.value = Math.trunc(next.httpStatus)
      speechSynthesisHttpStatusText.value = next.httpStatusText?.trim() || speechSynthesisHttpStatusText.value
      ttsSynthesisState.value = speechSynthesisHttpStatus.value >= 200 && speechSynthesisHttpStatus.value < 300 ? ttsSynthesisState.value : 'http_error'
    }
    speechPlaybackUpdatedAt.value = Date.now()
    setTeacherSpeaking(false)
  }

  function setClassroomState(value: LessonAiriClassroomState) {
    classroomState.value = value
    classroomStateUpdatedAt.value = Date.now()
  }

  function applyPerformancePlan(payload: EmotionPayload) {
    const nextMotion = payload.motion || ''
    const nextExpression = payload.expression || ''
    const nextPlan: LessonAiriPerformancePlanState = {
      emotionName: payload.name,
      emotionIntensity: clampUnit(payload.intensity, 1),
      motion: nextMotion,
      expression: nextExpression,
      durationMs: typeof payload.durationMs === 'number' && Number.isFinite(payload.durationMs)
        ? payload.durationMs
        : null,
      reason: payload.reason || '',
      teachingAction: payload.teachingAction || '',
      evaluation: payload.evaluation ?? null,
      turnLabel: payload.turnLabel || '',
      speechStyle: payload.speechStyle || 'normal',
      mouthIntensity: clampUnit(payload.mouthIntensity, 1),
      interruptPolicy: payload.interruptPolicy || 'barge_in_allowed',
      contentSource: payload.contentSource || '',
      fallbackAllowed: typeof payload.fallbackAllowed === 'boolean' ? payload.fallbackAllowed : null,
      performanceSource: payload.performanceSource || '',
      updatedAt: Date.now(),
    }

    if (
      currentPerformancePlan.value
      && fingerprintPerformancePlan(currentPerformancePlan.value) === fingerprintPerformancePlan(nextPlan)
    ) {
      currentPerformancePlan.value = nextPlan
      return
    }

    currentPerformancePlan.value = nextPlan
    performanceApplyStatus.value = 'pending'
    requestedMotion.value = nextMotion
    appliedMotion.value = ''
    requestedExpression.value = nextExpression
    appliedExpression.value = ''
    performanceFallbackReason.value = ''
    performanceFallbackKind.value = ''
    performanceApplyUpdatedAt.value = Date.now()
  }

  function clearPerformancePlan() {
    currentPerformancePlan.value = null
    clearPerformanceApplyState()
  }

  function markPerformanceApplied(next: {
    status: LessonAiriPerformanceApplyStatus
    requestedMotion?: string
    appliedMotion?: string
    requestedExpression?: string
    appliedExpression?: string
    fallbackReason?: string
  }) {
    performanceApplyStatus.value = next.status
    requestedMotion.value = next.requestedMotion?.trim() ?? requestedMotion.value
    appliedMotion.value = next.appliedMotion?.trim() ?? appliedMotion.value
    requestedExpression.value = next.requestedExpression?.trim() ?? requestedExpression.value
    appliedExpression.value = next.appliedExpression?.trim() ?? appliedExpression.value
    performanceFallbackReason.value = next.fallbackReason?.trim() ?? ''
    performanceFallbackKind.value = classifyPerformanceFallback(performanceFallbackReason.value)
    performanceApplyUpdatedAt.value = Date.now()
  }

  function clearPerformanceApplyState() {
    performanceApplyStatus.value = 'idle'
    requestedMotion.value = ''
    appliedMotion.value = ''
    requestedExpression.value = ''
    appliedExpression.value = ''
    performanceFallbackReason.value = ''
    performanceFallbackKind.value = ''
    performanceApplyUpdatedAt.value = 0
  }

  function markInterrupted() {
    setClassroomState('interrupted')
  }

  function updateLiveTranscript(text: string) {
    liveTranscriptText.value = text.trim()
    liveTranscriptUpdatedAt.value = Date.now()
  }

  function clearLiveTranscript() {
    liveTranscriptText.value = ''
    liveTranscriptUpdatedAt.value = 0
  }

  function markMicInteraction() {
    lastMicInteractionAt.value = Date.now()
  }

  function markRecognizedText(text: string) {
    const normalizedText = text.trim()
    if (!normalizedText)
      return
    lastRecognizedText.value = normalizedText
    lastRecognizedAt.value = Date.now()
  }

  function resetRuntimeState() {
    microphoneEnabled.value = false
    microphoneReady.value = false
    microphoneInputDeviceLabel.value = ''
    microphoneUnavailableReason.value = ''
    microphonePermissionState.value = 'unknown'
    microphonePermissionError.value = ''
    hearingListening.value = false
    teacherSpeaking.value = false
    inputVolumeLevel.value = 0
    liveTranscriptText.value = ''
    liveTranscriptUpdatedAt.value = 0
    lastRecognizedText.value = ''
    lastRecognizedAt.value = 0
    classroomState.value = 'idle'
    classroomStateUpdatedAt.value = 0
    currentPerformancePlan.value = null
    clearPerformanceApplyState()
    speechPlaybackStatus.value = 'idle'
    ttsSynthesisState.value = 'idle'
    ttsPlaybackState.value = 'idle'
    ttsPlaybackReason.value = ''
    ttsPlaybackId.value = ''
    activeReplyId.value = ''
    ttsPlaybackStopReason.value = ''
    ttsPlaybackNormalizedStopReason.value = ''
    ttsPlaybackOverlapDetected.value = false
    ttsPlaybackOverlapCount.value = 0
    speechPlaybackError.value = ''
    speechPlaybackProvider.value = ''
    speechPlaybackModel.value = ''
    speechPlaybackVoice.value = ''
    speechPlaybackText.value = ''
    speechPlaybackUpdatedAt.value = 0
    speechPlaybackFailureStage.value = ''
    speechPlaybackAudioContextState.value = ''
    speechSynthesisHttpStatus.value = null
    speechSynthesisHttpStatusText.value = ''
    speechAudioByteLength.value = null
    speechAudioDurationMs.value = null
    speechSynthesisStartedAt.value = 0
    speechSynthesisReadyAt.value = 0
    speechPlaybackStartedAt.value = 0
    speechPlaybackEndedAt.value = 0
    speechSynthesisLatencyMs.value = null
    speechPlaybackStartupLatencyMs.value = null
    speechPlaybackDurationMs.value = null
  }

  return {
    microphoneEnabled,
    microphoneReady,
    microphoneInputDeviceLabel,
    microphoneUnavailableReason,
    microphonePermissionState,
    microphonePermissionError,
    hearingListening,
    teacherSpeaking,
    hearingConfigured,
    supportsStreamInput,
    autoSendEnabled,
    autoSendDelay,
    inputVolumeLevel,
    liveTranscriptText,
    liveTranscriptUpdatedAt,
    lastRecognizedText,
    lastRecognizedAt,
    lastMicInteractionAt,
    classroomState,
    classroomStateUpdatedAt,
    currentPerformancePlan,
    performanceApplyStatus,
    performanceApplyStatusLabel,
    requestedMotion,
    appliedMotion,
    requestedExpression,
    appliedExpression,
    performanceFallbackReason,
    performanceFallbackKind,
    performanceApplyUpdatedAt,
    speechPlaybackStatus,
    ttsSynthesisState,
    ttsSynthesisStateLabel,
    ttsPlaybackState,
    ttsPlaybackStateLabel,
    ttsPlaybackReason,
    ttsPlaybackId,
    activeReplyId,
    ttsPlaybackStopReason,
    ttsPlaybackNormalizedStopReason,
    ttsPlaybackOverlapDetected,
    ttsPlaybackOverlapCount,
    speechPlaybackStatusLabel,
    speechPlaybackDebugLabel,
    speechPlaybackError,
    speechPlaybackProvider,
    speechPlaybackModel,
    speechPlaybackVoice,
    speechPlaybackText,
    speechPlaybackUpdatedAt,
    speechPlaybackFailureStage,
    speechPlaybackAudioContextState,
    speechSynthesisHttpStatus,
    speechSynthesisHttpStatusText,
    speechAudioByteLength,
    speechAudioDurationMs,
    speechSynthesisStartedAt,
    speechSynthesisReadyAt,
    speechPlaybackStartedAt,
    speechPlaybackEndedAt,
    speechSynthesisLatencyMs,
    speechPlaybackStartupLatencyMs,
    speechPlaybackDurationMs,
    microphoneStatus,
    microphoneStatusLabel,
    currentSpeechStyle,
    currentMouthIntensity,
    currentInterruptPolicy,
    canBargeInDuringTeacherSpeech,
    canDriveMouthOpen,
    updateMicrophoneState,
    updateInputVolume,
    setTeacherSpeaking,
    markSpeechSynthesisStart,
    markSpeechSynthesisHttpResult,
    markSpeechSynthesisReady,
    markSpeechPlaybackRequested,
    markSpeechPlaybackStart,
    markSpeechPlaybackEnd,
    markSpeechPlaybackError,
    setClassroomState,
    applyPerformancePlan,
    clearPerformancePlan,
    markPerformanceApplied,
    clearPerformanceApplyState,
    markInterrupted,
    updateLiveTranscript,
    clearLiveTranscript,
    markMicInteraction,
    markRecognizedText,
    resetRuntimeState,
  }
})
