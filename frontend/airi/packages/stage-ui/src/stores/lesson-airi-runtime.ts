import type { EmotionPayload } from '../constants/emotions'
import type { AudioPermissionState } from './settings/audio-device'

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

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

function clampUnit(value: number | undefined, fallback: number) {
  if (typeof value !== 'number' || Number.isNaN(value))
    return fallback
  return Math.min(1, Math.max(0, value))
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

  function setClassroomState(value: LessonAiriClassroomState) {
    classroomState.value = value
    classroomStateUpdatedAt.value = Date.now()
  }

  function applyPerformancePlan(payload: EmotionPayload) {
    currentPerformancePlan.value = {
      emotionName: payload.name,
      emotionIntensity: clampUnit(payload.intensity, 1),
      motion: payload.motion || '',
      expression: payload.expression || '',
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
  }

  function clearPerformancePlan() {
    currentPerformancePlan.value = null
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
    microphoneStatus,
    microphoneStatusLabel,
    currentSpeechStyle,
    currentMouthIntensity,
    currentInterruptPolicy,
    canBargeInDuringTeacherSpeech,
    updateMicrophoneState,
    updateInputVolume,
    setTeacherSpeaking,
    setClassroomState,
    applyPerformancePlan,
    clearPerformancePlan,
    markInterrupted,
    updateLiveTranscript,
    clearLiveTranscript,
    markMicInteraction,
    markRecognizedText,
    resetRuntimeState,
  }
})
