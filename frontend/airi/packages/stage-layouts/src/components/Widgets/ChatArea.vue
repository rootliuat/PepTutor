<script setup lang="ts">
import type { LessonInterruptEvent } from '@proj-airi/stage-ui/utils/lesson-interrupt-policy'
import type { ChatProvider } from '@xsai-ext/providers/utils'

import { isStageTamagotchi } from '@proj-airi/stage-shared'
import { useAudioAnalyzer } from '@proj-airi/stage-ui/composables'
import { useAudioContext } from '@proj-airi/stage-ui/stores/audio'
import { useChatOrchestratorStore } from '@proj-airi/stage-ui/stores/chat'
import { useChatSessionStore } from '@proj-airi/stage-ui/stores/chat/session-store'
import { useLessonStore } from '@proj-airi/stage-ui/stores/lesson'
import { useLessonAiriRuntimeStore } from '@proj-airi/stage-ui/stores/lesson-airi-runtime'
import { useConsciousnessStore } from '@proj-airi/stage-ui/stores/modules/consciousness'
import { useHearingSpeechInputPipeline, useHearingStore } from '@proj-airi/stage-ui/stores/modules/hearing'
import { useProvidersStore } from '@proj-airi/stage-ui/stores/providers'
import { useSettings, useSettingsAudioDevice } from '@proj-airi/stage-ui/stores/settings'
import { useSpeechRuntimeStore } from '@proj-airi/stage-ui/stores/speech-runtime'
import {
  isLessonControlKey,
  isLessonPushToTalkCombo,
  isLessonShiftKey,
  updateLessonPushToTalkModifierState,
} from '@proj-airi/stage-ui/utils/lesson-hotkeys'
import { resolveLessonInterruptDecision } from '@proj-airi/stage-ui/utils/lesson-interrupt-policy'
import { until } from '@vueuse/core'
import { storeToRefs } from 'pinia'
import { computed, nextTick, onMounted, onUnmounted, ref, unref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import IndicatorMicVolume from './IndicatorMicVolume.vue'

const props = withDefaults(defineProps<{
  chatProviderOverride?: ChatProvider | null
  modelOverride?: string
  providerConfigOverride?: Record<string, unknown> | null
  disabled?: boolean
  placeholder?: string
  autoSendEnabledOverride?: boolean | null
  autoSendDelayOverride?: number | null
  interruptPlaybackOnInput?: boolean
  compactMode?: boolean
  pushToTalkHotkey?: boolean
  beforeSend?: () => Promise<void> | void
}>(), {
  chatProviderOverride: null,
  modelOverride: '',
  providerConfigOverride: null,
  disabled: false,
  placeholder: '',
  autoSendEnabledOverride: null,
  autoSendDelayOverride: null,
  interruptPlaybackOnInput: false,
  compactMode: false,
  pushToTalkHotkey: false,
  beforeSend: undefined,
})

const messageInput = ref('')
const isComposing = ref(false)
const isListening = ref(false) // Transcription listening state (separate from microphone enabled)
const microphoneInitInFlight = ref(false)
const pendingAutoSendText = ref('')
const pushToTalkActive = ref(false)
const inputShellRef = ref<HTMLElement>()
const textareaRef = ref<HTMLTextAreaElement>()
const lastLiveTranscriptPreview = ref('')
const pushToTalkModifierState = {
  ctrlDown: false,
  shiftDown: false,
}
let textareaResizeFrame: number | undefined

const providersStore = useProvidersStore()
const { activeProvider, activeModel } = storeToRefs(useConsciousnessStore())
const { themeColorsHueDynamic } = storeToRefs(useSettings())

const settingsAudioDevice = useSettingsAudioDevice()
const { ensureInputReady, startStream } = settingsAudioDevice
const { enabled, selectedAudioInput, stream, audioInputs, permissionState, permissionError } = storeToRefs(settingsAudioDevice)
const chatOrchestrator = useChatOrchestratorStore()
const { sending } = storeToRefs(chatOrchestrator)
const chatSession = useChatSessionStore()
const speechRuntimeStore = useSpeechRuntimeStore()
const { ingest, onAfterMessageComposed, discoverToolsCompatibility } = chatOrchestrator
const { messages } = storeToRefs(chatSession)
const { resumeAudioContext } = useAudioContext()
const { t } = useI18n()
const { startAnalyzer, stopAnalyzer, volumeLevel } = useAudioAnalyzer()
const normalizedVolume = computed(() => Math.min(1, Math.max(0, (volumeLevel.value ?? 0) / 100)))

// Transcription pipeline
const hearingStore = useHearingStore()
const hearingPipeline = useHearingSpeechInputPipeline()
const lessonAiriRuntime = useLessonAiriRuntimeStore()
const lessonStore = useLessonStore()
const { transcribeForMediaStream, stopStreamingTranscription } = hearingPipeline
const { supportsStreamInput } = storeToRefs(hearingPipeline)
const { configured: hearingConfigured, autoSendEnabled, autoSendDelay } = storeToRefs(hearingStore)
const { loading: lessonLoading, runtimeState } = storeToRefs(lessonStore)
const { teacherSpeaking, lastRecognizedText, liveTranscriptText, currentInterruptPolicy, classroomSimpleStatus } = storeToRefs(lessonAiriRuntime)
const shouldUseStreamInput = computed(() => supportsStreamInput.value && !!stream.value)
const effectiveAutoSendEnabled = computed(() => props.autoSendEnabledOverride ?? autoSendEnabled.value)
const effectiveAutoSendDelay = computed(() => props.autoSendDelayOverride ?? autoSendDelay.value)
const shouldInterruptPlaybackOnInput = computed(() => props.interruptPlaybackOnInput)
const chatInputPlaceholder = computed(() => props.placeholder || t('stage.message'))
const canSendMessage = computed(() =>
  Boolean(messageInput.value.trim())
  && !isComposing.value
  && !props.disabled
  && !lessonLoading.value
  && !sending.value,
)
const activeTranscriptionProviderId = computed(() => {
  const provider = unref(hearingStore.activeTranscriptionProvider)
  return typeof provider === 'string' ? provider : ''
})
const activeTranscriptionModelId = computed(() => {
  const model = unref(hearingStore.activeTranscriptionModel)
  return typeof model === 'string' ? model : ''
})
const usesStreamingTranscriptPreview = computed(() =>
  Boolean(activeTranscriptionProviderId.value)
  && activeTranscriptionProviderId.value !== 'browser-web-speech-api',
)
const microphoneApiSupported = computed(() =>
  typeof navigator !== 'undefined'
  && Boolean(navigator.mediaDevices?.getUserMedia),
)
const microphoneUnavailableReason = computed(() => {
  if (typeof window !== 'undefined' && !window.isSecureContext) {
    return 'Microphone requires localhost, 127.0.0.1, or HTTPS.'
  }

  if (!microphoneApiSupported.value) {
    return 'Microphone input is unavailable in this browser.'
  }

  return ''
})
const microphoneButtonTitle = computed(() => permissionError.value || microphoneUnavailableReason.value || 'Microphone')
const microphoneStatusLabel = computed(() => {
  if (microphoneUnavailableReason.value)
    return microphoneUnavailableReason.value
  if (permissionState.value === 'requesting')
    return '正在请求麦克风权限'
  if (permissionState.value === 'denied' && permissionError.value)
    return permissionError.value
  if (isListening.value && normalizedVolume.value >= 0.08)
    return '学生正在说话'
  if (isListening.value)
    return '正在听，识别后会自动发送'
  if (enabled.value && stream.value)
    return '麦克风已开，等待语音'
  if (enabled.value)
    return '正在请求麦克风'
  return '麦克风关闭'
})
const hearingProviderLabel = computed(() => {
  const provider = activeTranscriptionProviderId.value || '未选择'
  const model = activeTranscriptionModelId.value
  return model ? `${provider} · ${model}` : provider
})
const selectedAudioInputLabel = computed(() => {
  if (!selectedAudioInput.value) {
    return enabled.value ? '正在匹配默认麦克风' : '未选择输入设备'
  }

  return audioInputs.value.find(device => device.deviceId === selectedAudioInput.value)?.label
    || '已连接输入设备'
})
const microphoneContextLabel = computed(() => {
  if (permissionState.value === 'requesting') {
    return selectedAudioInputLabel.value
  }

  if (permissionError.value) {
    return selectedAudioInputLabel.value
  }

  return selectedAudioInputLabel.value
})
const actionButtonSizeClasses = computed(() => props.compactMode ? 'h-10 w-10' : 'h-12 w-12')
const sendButtonClasses = computed(() => props.compactMode
  ? 'h-10 min-w-10 rounded-full px-3.5'
  : 'h-11 min-w-11 rounded-full px-4')
const sendButtonLabelVisible = computed(() => !props.compactMode)
const composerShellClasses = computed(() => props.compactMode
  ? 'min-h-[4.75rem] items-stretch gap-3 rounded-[28px] border border-sky-100/90 bg-white/94 px-3.5 py-2.5 shadow-[0_18px_48px_-38px_rgba(15,23,42,0.55)] dark:border-cyan-300/18 dark:!bg-slate-950/92 dark:shadow-[0_20px_56px_-36px_rgba(8,145,178,0.5)]'
  : 'items-end gap-3 rounded-[28px] border border-sky-100/90 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(240,249,255,0.9))] px-3 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(12,18,28,0.96),rgba(8,12,20,0.92))] dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]')
const textareaClasses = computed(() => props.compactMode
  ? 'max-h-[7.5rem] min-h-[2rem] py-1 text-[15px] leading-6'
  : 'max-h-[18rem] min-h-[3.25rem] py-2 text-base leading-6')
const learnerSpeaking = computed(() => isListening.value && normalizedVolume.value >= 0.08)
const canStopInteraction = computed(() =>
  teacherSpeaking.value
  || enabled.value
  || isListening.value
  || lessonLoading.value
  || sending.value
  || Boolean(pendingAutoSendText.value.trim()),
)
const interactionStatus = computed(() => {
  if (props.disabled) {
    return {
      label: '未开始',
      detail: 'lesson 还没有启动，当前只展示输入框壳。',
      tone: 'slate',
      icon: 'i-solar:playback-speed-bold-duotone',
    }
  }

  if (permissionState.value === 'requesting') {
    return {
      label: '接入中',
      detail: '正在向浏览器请求麦克风，并尝试连接当前输入设备。',
      tone: 'sky',
      icon: 'i-solar:microphone-3-bold-duotone',
    }
  }

  if (permissionError.value) {
    return {
      label: '接入失败',
      detail: permissionError.value,
      tone: 'rose',
      icon: 'i-solar:danger-circle-bold-duotone',
    }
  }

  if (teacherSpeaking.value) {
    return {
      label: '说话中',
      detail: '米粒老师正在播报当前页面内容。',
      tone: 'cyan',
      icon: 'i-solar:chat-round-call-bold-duotone',
    }
  }

  if (lessonLoading.value || sending.value) {
    return {
      label: '思考中',
      detail: '正在等待 lesson backend 返回下一句回复。',
      tone: 'amber',
      icon: 'i-solar:lightbulb-bolt-bold-duotone',
    }
  }

  if (learnerSpeaking.value) {
    return {
      label: '聆听中',
      detail: '正在接收学生语音并实时识别。',
      tone: 'emerald',
      icon: 'i-solar:ear-bold-duotone',
    }
  }

  if (isListening.value) {
    return {
      label: '聆听中',
      detail: '麦克风已开，等待学生说完整一句。',
      tone: 'emerald',
      icon: 'i-solar:ear-bold-duotone',
    }
  }

  if (microphoneUnavailableReason.value) {
    return {
      label: '麦克风不可用',
      detail: microphoneUnavailableReason.value,
      tone: 'rose',
      icon: 'i-solar:danger-circle-bold-duotone',
    }
  }

  if (runtimeState.value?.awaiting_answer) {
    return {
      label: '等待回答',
      detail: '老师正在等你回答，开口后会自动听写。',
      tone: 'violet',
      icon: 'i-solar:case-round-minimalistic-bold-duotone',
    }
  }

  if (enabled.value && stream.value) {
    return {
      label: '待命中',
      detail: '麦克风已接通，随时可以开始说话。',
      tone: 'sky',
      icon: 'i-solar:microphone-3-bold-duotone',
    }
  }

  return {
    label: '待命中',
    detail: '可以直接输入，也可以打开麦克风开始对话。',
    tone: 'slate',
    icon: 'i-solar:chat-round-bold-duotone',
  }
})
const statusBadgeClasses = computed(() => {
  switch (interactionStatus.value.tone) {
    case 'cyan':
      return 'bg-cyan-100 text-cyan-700 ring-cyan-200 dark:bg-cyan-400/14 dark:text-cyan-100 dark:ring-cyan-300/18'
    case 'emerald':
      return 'bg-emerald-100 text-emerald-700 ring-emerald-200 dark:bg-emerald-400/14 dark:text-emerald-100 dark:ring-emerald-300/18'
    case 'amber':
      return 'bg-amber-100 text-amber-700 ring-amber-200 dark:bg-amber-400/14 dark:text-amber-100 dark:ring-amber-300/18'
    case 'violet':
      return 'bg-violet-100 text-violet-700 ring-violet-200 dark:bg-violet-400/14 dark:text-violet-100 dark:ring-violet-300/18'
    case 'rose':
      return 'bg-rose-100 text-rose-700 ring-rose-200 dark:bg-rose-400/14 dark:text-rose-100 dark:ring-rose-300/18'
    case 'sky':
      return 'bg-sky-100 text-sky-700 ring-sky-200 dark:bg-sky-400/14 dark:text-sky-100 dark:ring-sky-300/18'
    case 'slate':
    default:
      return 'bg-slate-100 text-slate-600 ring-slate-200 dark:bg-white/10 dark:text-neutral-100 dark:ring-white/10'
  }
})

const statusPanelClasses = computed(() => {
  switch (interactionStatus.value.tone) {
    case 'cyan':
      return 'border-cyan-100/90 bg-[linear-gradient(180deg,rgba(236,254,255,0.96),rgba(255,255,255,0.9))] dark:border-cyan-400/18 dark:bg-[linear-gradient(180deg,rgba(6,22,34,0.96),rgba(7,16,28,0.92))]'
    case 'emerald':
      return 'border-emerald-100/90 bg-[linear-gradient(180deg,rgba(236,253,245,0.96),rgba(255,255,255,0.9))] dark:border-emerald-400/18 dark:bg-[linear-gradient(180deg,rgba(5,26,24,0.96),rgba(6,15,18,0.92))]'
    case 'amber':
      return 'border-amber-100/90 bg-[linear-gradient(180deg,rgba(255,251,235,0.96),rgba(255,255,255,0.9))] dark:border-amber-400/18 dark:bg-[linear-gradient(180deg,rgba(32,20,8,0.96),rgba(16,12,8,0.92))]'
    case 'violet':
      return 'border-violet-100/90 bg-[linear-gradient(180deg,rgba(245,243,255,0.96),rgba(255,255,255,0.9))] dark:border-violet-400/18 dark:bg-[linear-gradient(180deg,rgba(22,16,38,0.96),rgba(11,10,24,0.92))]'
    case 'rose':
      return 'border-rose-100/90 bg-[linear-gradient(180deg,rgba(255,241,242,0.96),rgba(255,255,255,0.9))] dark:border-rose-400/18 dark:bg-[linear-gradient(180deg,rgba(36,14,20,0.96),rgba(15,9,14,0.92))]'
    case 'sky':
      return 'border-sky-100/90 bg-[linear-gradient(180deg,rgba(240,249,255,0.96),rgba(255,255,255,0.9))] dark:border-sky-400/18 dark:bg-[linear-gradient(180deg,rgba(12,20,34,0.96),rgba(8,12,20,0.92))]'
    case 'slate':
    default:
      return 'border-slate-200/90 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(248,250,252,0.9))] dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(16,21,31,0.96),rgba(9,13,22,0.92))]'
  }
})
const statusPanelShellClasses = computed(() => props.compactMode
  ? 'w-max max-w-[18rem] rounded-full px-2.5 py-1.5 shadow-[0_14px_36px_-28px_rgba(2,12,27,0.9)]'
  : 'max-w-[24rem] rounded-[18px] px-3.5 py-2.5 shadow-[0_18px_55px_-35px_rgba(2,12,27,0.9)]')
const compactClassroomStatusLabel = computed(() => {
  if (microphoneUnavailableReason.value || permissionError.value)
    return '未连接'
  if (props.disabled)
    return '不可用'
  if (lessonLoading.value || sending.value || teacherSpeaking.value)
    return '思考/说话中'
  return classroomSimpleStatus.value === '思考/说话中' ? '思考/说话中' : '等待'
})
const compactClassroomStatusClasses = computed(() =>
  compactClassroomStatusLabel.value === '思考/说话中'
    ? 'bg-violet-500 text-white shadow-[0_14px_30px_-18px_rgba(124,58,237,0.88)] dark:bg-violet-400 dark:text-violet-950 dark:shadow-[0_12px_32px_-16px_rgba(167,139,250,0.95)]'
    : compactClassroomStatusLabel.value === '等待'
      ? 'bg-emerald-100 text-emerald-700 ring-1 ring-inset ring-emerald-200/90 dark:bg-emerald-300 dark:text-emerald-950 dark:ring-emerald-200/80 dark:shadow-[0_12px_30px_-18px_rgba(110,231,183,0.9)]'
      : 'bg-slate-100 text-slate-500 ring-1 ring-inset ring-slate-200 dark:bg-slate-200 dark:text-slate-950 dark:ring-white/40',
)

async function resolveSendOptions() {
  const overrideProvider = props.chatProviderOverride
  const overrideModel = props.modelOverride.trim()

  if (overrideProvider && overrideModel) {
    return {
      chatProvider: overrideProvider,
      model: overrideModel,
      providerConfig: props.providerConfigOverride ?? {},
    }
  }

  const providerConfig = providersStore.getProviderConfig(activeProvider.value)
  const provider = await providersStore.getProviderInstance(activeProvider.value) as ChatProvider

  if (!provider || !activeModel.value) {
    throw new Error('No active chat provider or model configured')
  }

  return {
    chatProvider: provider,
    model: activeModel.value,
    providerConfig,
  }
}

async function sendTextToChat(text: string, interruptEvent: Extract<LessonInterruptEvent, 'manual_send' | 'auto_send'> = 'manual_send') {
  await props.beforeSend?.()
  if (shouldInterruptPlaybackOnInput.value) {
    interruptLessonPlayback(interruptEvent)
  }
  lessonAiriRuntime.setClassroomState('thinking')
  await ingest(text, await resolveSendOptions())
  lessonAiriRuntime.clearLiveTranscript()
}

// Auto-send logic
let autoSendTimeout: ReturnType<typeof setTimeout> | undefined

function clearAutoSendTimeout() {
  if (autoSendTimeout) {
    clearTimeout(autoSendTimeout)
    autoSendTimeout = undefined
  }
}

function clearPendingAutoSend() {
  clearAutoSendTimeout()
  pendingAutoSendText.value = ''
}

function takePendingAutoSendText() {
  clearAutoSendTimeout()
  const text = pendingAutoSendText.value.trim()
  pendingAutoSendText.value = ''
  return text
}

function withoutTrailingPreview(value: string, preview: string) {
  const normalizedValue = value.trim()
  const normalizedPreview = preview.trim()
  if (!normalizedValue || !normalizedPreview) {
    return normalizedValue
  }

  if (normalizedValue === normalizedPreview) {
    return ''
  }

  const previewWithSeparator = ` ${normalizedPreview}`
  if (normalizedValue.endsWith(previewWithSeparator)) {
    return normalizedValue.slice(0, -previewWithSeparator.length).trim()
  }

  if (normalizedValue.endsWith(normalizedPreview)) {
    return normalizedValue.slice(0, -normalizedPreview.length).trim()
  }

  return normalizedValue
}

function appendInputSegment(currentText: string, segment: string) {
  const normalizedCurrentText = currentText.trim()
  const normalizedSegment = segment.trim()
  return [normalizedCurrentText, normalizedSegment].filter(Boolean).join(' ')
}

function applyLiveTranscriptPreview(text: string) {
  const preview = text.trim()
  const baseText = withoutTrailingPreview(messageInput.value, lastLiveTranscriptPreview.value)
  lastLiveTranscriptPreview.value = preview
  messageInput.value = appendInputSegment(baseText, preview)
}

function commitLiveTranscriptDelta(delta: string) {
  if (usesStreamingTranscriptPreview.value) {
    const finalText = lastLiveTranscriptPreview.value.trim() || delta.trim()
    if (!finalText) {
      return ''
    }

    const baseText = withoutTrailingPreview(messageInput.value, lastLiveTranscriptPreview.value)
    lastLiveTranscriptPreview.value = finalText
    messageInput.value = appendInputSegment(baseText, finalText)
    return finalText
  }

  const baseText = withoutTrailingPreview(messageInput.value, lastLiveTranscriptPreview.value)
  lastLiveTranscriptPreview.value = ''
  messageInput.value = appendInputSegment(baseText, delta)
  return delta.trim()
}

function interruptLessonPlayback(event: LessonInterruptEvent) {
  if (shouldInterruptPlaybackOnInput.value) {
    const decision = resolveLessonInterruptDecision({
      event,
      policy: currentInterruptPolicy.value,
    })
    if (!decision.shouldStopPlayback)
      return

    speechRuntimeStore.stopAll(decision.rawStopReason)
    if (decision.shouldAbortActiveTurn)
      lessonStore.abortActiveTurn(decision.rawStopReason)
    if (decision.shouldMarkInterrupted)
      lessonAiriRuntime.markInterrupted()
  }
}

async function debouncedAutoSend(text: string, options: { replace?: boolean } = {}) {
  // Double-check auto-send is enabled before proceeding
  if (!effectiveAutoSendEnabled.value || props.disabled) {
    clearPendingAutoSend()
    return
  }

  const normalizedText = text.trim()
  if (!normalizedText) {
    clearPendingAutoSend()
    return
  }

  // Add text to pending buffer
  pendingAutoSendText.value = options.replace
    ? normalizedText
    : pendingAutoSendText.value ? `${pendingAutoSendText.value} ${normalizedText}` : normalizedText

  // Clear existing timeout
  clearAutoSendTimeout()

  // Set new timeout
  autoSendTimeout = setTimeout(async () => {
    // Final check before sending - auto-send might have been disabled while waiting
    if (!effectiveAutoSendEnabled.value || props.disabled) {
      clearPendingAutoSend()
      return
    }

    autoSendTimeout = undefined
    const textToSend = takePendingAutoSendText()
    if (textToSend && effectiveAutoSendEnabled.value) {
      try {
        await sendTextToChat(textToSend, 'auto_send')
        lessonAiriRuntime.markRecognizedText(textToSend)
        // Clear the message input after sending
        messageInput.value = ''
        lastLiveTranscriptPreview.value = ''
      }
      catch (err) {
        console.error('[ChatArea] Auto-send error:', err)
      }
    }
  }, effectiveAutoSendDelay.value)
}

async function handleSend() {
  if (!canSendMessage.value) {
    return
  }

  const textToSend = messageInput.value
  messageInput.value = ''
  lastLiveTranscriptPreview.value = ''

  try {
    await sendTextToChat(textToSend)
  }
  catch (error) {
    messageInput.value = textToSend
    messages.value.pop()
    messages.value.push({
      role: 'error',
      content: (error as Error).message,
    })
  }
}

function scheduleTextareaResize() {
  if (typeof window === 'undefined') {
    return
  }

  if (textareaResizeFrame !== undefined) {
    window.cancelAnimationFrame(textareaResizeFrame)
  }

  textareaResizeFrame = window.requestAnimationFrame(() => {
    textareaResizeFrame = undefined
    const textarea = textareaRef.value
    if (!textarea) {
      return
    }

    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, props.compactMode ? 144 : 288)}px`
  })
}

function handleTextareaInput() {
  scheduleTextareaResize()
}

function handleTextareaKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || isComposing.value) {
    return
  }

  event.preventDefault()
  void handleSend()
}

function handleCompositionEnd() {
  isComposing.value = false
  scheduleTextareaResize()
}

async function handleMicrophoneTriggerClick() {
  if (props.disabled || microphoneUnavailableReason.value)
    return

  lessonAiriRuntime.markMicInteraction()
  microphoneInitInFlight.value = true
  try {
    await ensureInputReady()
  }
  catch (error) {
    console.error('[ChatArea] Failed to enable microphone:', error)
  }
  finally {
    microphoneInitInFlight.value = false
  }
}

async function handleMicrophoneButtonClick() {
  if (enabled.value || isListening.value) {
    pushToTalkActive.value = false
    enabled.value = false
    await stopListening({ flushPending: false })
    return
  }

  await handleMicrophoneTriggerClick()
}

async function handleStopInteraction() {
  pushToTalkActive.value = false
  interruptLessonPlayback('stop_button')

  if (isListening.value) {
    await stopListening({ flushPending: true })
  }
  else {
    clearPendingAutoSend()
  }

  if (enabled.value) {
    enabled.value = false
  }
}

function updatePushToTalkModifierState(event: KeyboardEvent, pressed: boolean) {
  updateLessonPushToTalkModifierState(pushToTalkModifierState, event, pressed)
}

function isPushToTalkCombo(event: KeyboardEvent) {
  return isLessonPushToTalkCombo(event, pushToTalkModifierState)
}

async function beginPushToTalk() {
  if (pushToTalkActive.value || props.disabled || microphoneUnavailableReason.value) {
    return
  }

  pushToTalkActive.value = true
  await handleMicrophoneTriggerClick()
}

async function endPushToTalk() {
  if (!pushToTalkActive.value) {
    return
  }

  pushToTalkActive.value = false
  if (isListening.value) {
    await stopListening({ flushPending: true })
  }
  else {
    clearPendingAutoSend()
  }

  if (enabled.value) {
    enabled.value = false
  }
}

function handlePushToTalkKeydown(event: KeyboardEvent) {
  updatePushToTalkModifierState(event, true)

  if (!isPushToTalkCombo(event)) {
    return
  }

  event.preventDefault()
  if (event.repeat && pushToTalkActive.value) {
    return
  }

  void beginPushToTalk()
}

function handlePushToTalkKeyup(event: KeyboardEvent) {
  const wasPushToTalkActive = pushToTalkActive.value
  const releasedPushToTalkModifier = isLessonControlKey(event) || isLessonShiftKey(event)
  updatePushToTalkModifierState(event, false)

  if (!wasPushToTalkActive || !releasedPushToTalkModifier) {
    return
  }

  event.preventDefault()
  void endPushToTalk()
}

function handlePushToTalkBlur() {
  pushToTalkModifierState.ctrlDown = false
  pushToTalkModifierState.shiftDown = false
  void endPushToTalk()
}

function focusMessageInputFromContainer(event: PointerEvent) {
  const target = event.target
  if (target instanceof HTMLElement && target.closest('button')) {
    return
  }

  inputShellRef.value?.querySelector('textarea')?.focus()
}

watch([activeProvider, activeModel], async () => {
  if (props.chatProviderOverride) {
    return
  }

  if (activeProvider.value && activeModel.value) {
    await discoverToolsCompatibility(activeModel.value, await providersStore.getProviderInstance<ChatProvider>(activeProvider.value), [])
  }
})

onAfterMessageComposed(async () => {
})

let analyzerSource: MediaStreamAudioSourceNode | undefined

function teardownAnalyzer() {
  try {
    analyzerSource?.disconnect()
  }
  catch {}
  analyzerSource = undefined
  stopAnalyzer()
}

async function setupAnalyzer() {
  teardownAnalyzer()
  if (!enabled.value || !stream.value)
    return
  if (typeof MediaStream !== 'undefined' && !(stream.value instanceof MediaStream))
    return
  try {
    const audioContext = await resumeAudioContext()
    const analyser = startAnalyzer(audioContext)
    if (!analyser)
      return
    analyzerSource = audioContext.createMediaStreamSource(stream.value)
    analyzerSource.connect(analyser)
  }
  catch (error) {
    console.warn('[ChatArea] Failed to initialize microphone analyzer:', error)
    teardownAnalyzer()
  }
}

watch([enabled, stream], () => {
  setupAnalyzer()
}, { immediate: true })

watch(
  [
    enabled,
    stream,
    isListening,
    hearingConfigured,
    supportsStreamInput,
    effectiveAutoSendEnabled,
    effectiveAutoSendDelay,
    microphoneUnavailableReason,
    permissionState,
    permissionError,
  ],
  () => {
    lessonAiriRuntime.updateMicrophoneState({
      enabled: enabled.value,
      ready: Boolean(stream.value),
      inputDeviceLabel: selectedAudioInputLabel.value,
      unavailableReason: microphoneUnavailableReason.value,
      permissionState: permissionState.value,
      permissionError: permissionError.value,
      configured: hearingConfigured.value,
      streamInput: supportsStreamInput.value,
      listening: isListening.value,
      autoSend: effectiveAutoSendEnabled.value,
      autoSendDelayMs: effectiveAutoSendDelay.value,
    })
  },
  { immediate: true },
)

watch(normalizedVolume, (volume) => {
  lessonAiriRuntime.updateInputVolume(volume * 100)
}, { immediate: true })

watch(
  [
    teacherSpeaking,
    learnerSpeaking,
    isListening,
    lessonLoading,
    sending,
    enabled,
  ],
  ([isTeacherSpeaking, isLearnerSpeaking, isHearing, isLessonLoading, isSending, isMicrophoneEnabled]) => {
    if (props.disabled) {
      lessonAiriRuntime.setClassroomState('idle')
      return
    }

    if (isTeacherSpeaking) {
      lessonAiriRuntime.setClassroomState('teacher_speaking')
    }
    else if (isLearnerSpeaking) {
      lessonAiriRuntime.setClassroomState('learner_speaking')
    }
    else if (isLessonLoading || isSending) {
      lessonAiriRuntime.setClassroomState('thinking')
    }
    else if (isHearing || isMicrophoneEnabled) {
      lessonAiriRuntime.setClassroomState('listening')
    }
    else {
      lessonAiriRuntime.setClassroomState('idle')
    }
  },
  { immediate: true },
)

onMounted(() => {
  if (!props.pushToTalkHotkey) {
    return
  }

  window.addEventListener('keydown', handlePushToTalkKeydown, { capture: true })
  window.addEventListener('keyup', handlePushToTalkKeyup, { capture: true })
  window.addEventListener('blur', handlePushToTalkBlur)
})

onUnmounted(() => {
  if (props.pushToTalkHotkey) {
    window.removeEventListener('keydown', handlePushToTalkKeydown, { capture: true })
    window.removeEventListener('keyup', handlePushToTalkKeyup, { capture: true })
    window.removeEventListener('blur', handlePushToTalkBlur)
  }
  pushToTalkModifierState.ctrlDown = false
  pushToTalkModifierState.shiftDown = false
  teardownAnalyzer()
  void stopListening({ flushPending: false })
  lessonAiriRuntime.resetRuntimeState()
  clearPendingAutoSend()
  if (textareaResizeFrame !== undefined) {
    window.cancelAnimationFrame(textareaResizeFrame)
    textareaResizeFrame = undefined
  }
})

watch(messageInput, () => {
  scheduleTextareaResize()
}, { flush: 'post' })

// Transcription listening functions
let startListeningInFlight = false
let stopListeningPromise: Promise<void> | null = null

async function startListening() {
  if (startListeningInFlight || isListening.value) {
    return
  }

  if (props.disabled || microphoneUnavailableReason.value) {
    console.warn('[ChatArea] Microphone unavailable:', microphoneUnavailableReason.value || 'chat disabled')
    isListening.value = false
    return
  }

  startListeningInFlight = true
  try {
    console.info('[ChatArea] Starting listening...', {
      enabled: enabled.value,
      hasStream: !!stream.value,
      supportsStreamInput: supportsStreamInput.value,
      hearingConfigured: hearingConfigured.value,
    })

    // Auto-configure Web Speech API as default if no provider is configured
    if (!hearingConfigured.value) {
      // Check if Web Speech API is available in the browser
      // Web Speech API is NOT available in Electron (stage-tamagotchi) - it requires Google's embedded API keys
      // which are not available in Electron, causing it to fail at runtime
      const isWebSpeechAvailable = typeof window !== 'undefined'
        && !isStageTamagotchi() // Explicitly exclude Electron
        && ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)

      if (isWebSpeechAvailable) {
        console.info('[ChatArea] No transcription provider configured. Auto-configuring Web Speech API as default...')

        // Initialize the provider in the providers store first
        try {
          providersStore.initializeProvider('browser-web-speech-api')
        }
        catch (err) {
          console.warn('[ChatArea] Error initializing Web Speech API provider:', err)
        }

        // Set as active provider
        hearingStore.activeTranscriptionProvider = 'browser-web-speech-api'

        // Wait for reactivity to update
        await nextTick()

        // Verify the provider was set correctly
        if (hearingStore.activeTranscriptionProvider === 'browser-web-speech-api') {
          console.info('[ChatArea] Web Speech API configured as default provider')
          // Continue with transcription - Web Speech API is ready
        }
        else {
          console.error('[ChatArea] Failed to set Web Speech API as default provider')
          isListening.value = false
          return
        }
      }
      else {
        console.error('[ChatArea] Web Speech API not available. No transcription provider configured and Web Speech API is not available in this browser. Please go to Settings > Modules > Hearing to configure a transcription provider. Browser support:', {
          hasWindow: typeof window !== 'undefined',
          hasWebkitSpeechRecognition: typeof window !== 'undefined' && 'webkitSpeechRecognition' in window,
          hasSpeechRecognition: typeof window !== 'undefined' && 'SpeechRecognition' in window,
        })
        isListening.value = false
        return
      }
    }

    // Request microphone permission if needed (microphone should already be enabled by the user)
    if (!stream.value) {
      console.info('[ChatArea] Requesting microphone permission...')
      await ensureInputReady()

      // If still no stream, try starting it manually
      if (!stream.value && enabled.value) {
        console.info('[ChatArea] Attempting to start stream manually...')
        startStream()
        // Wait for the stream to become available with a timeout.
        try {
          await until(stream).toBeTruthy({ timeout: 3000, throwOnTimeout: true })
        }
        catch {
          console.error('[ChatArea] Timed out waiting for audio stream.')
          isListening.value = false
          return
        }
      }
    }

    if (!stream.value) {
      const errorMsg = 'Failed to get audio stream for transcription. Please check microphone permissions and ensure a device is selected.'
      console.error('[ChatArea]', errorMsg)
      isListening.value = false
      return
    }

    // Check if streaming input is supported
    if (!shouldUseStreamInput.value) {
      const errorMsg = 'Streaming input not supported by the selected transcription provider. Please select a provider that supports streaming (e.g., Web Speech API).'
      console.warn('[ChatArea]', errorMsg)
      // Clean up any existing sessions from other pages (e.g., test page) that might interfere
      await stopStreamingTranscription(true)
      isListening.value = false
      return
    }

    console.info('[ChatArea] Starting streaming transcription with stream:', stream.value.id)

    // Call transcribeForMediaStream - it's async so we await it
    try {
      isListening.value = true
      await transcribeForMediaStream(stream.value, {
        onTranscriptUpdate: (text) => {
          if (text.trim()) {
            applyLiveTranscriptPreview(text)
          }
          lessonAiriRuntime.updateLiveTranscript(text)
        },
        onSentenceEnd: (delta) => {
          if (delta && delta.trim()) {
            interruptLessonPlayback('final_transcript')
            const committedText = commitLiveTranscriptDelta(delta)
            lessonAiriRuntime.markRecognizedText(committedText || delta)
            lessonAiriRuntime.updateLiveTranscript(messageInput.value)
            console.info('[ChatArea] Received transcription delta:', delta)

            // Auto-send if enabled - check the current value (not captured in closure)
            // This ensures we always respect the current setting, even if callbacks are reused
            if (effectiveAutoSendEnabled.value) {
              debouncedAutoSend(committedText || delta, {
                replace: usesStreamingTranscriptPreview.value,
              })
            }
            else {
              // If auto-send is disabled, clear any pending auto-send text to prevent accidental sends
              clearPendingAutoSend()
            }
          }
        },
        // Omit onSpeechEnd to avoid re-adding user-deleted text; use sentence deltas only.
      })

      console.info('[ChatArea] Streaming transcription initiated successfully')
    }
    catch (err) {
      console.error('[ChatArea] Transcription error:', err)
      isListening.value = false
      throw err // Re-throw to be caught by outer catch
    }
  }
  catch (err) {
    console.error('[ChatArea] Failed to start transcription:', err)
    isListening.value = false
  }
  finally {
    startListeningInFlight = false
  }
}

async function stopListening(options: { flushPending?: boolean } = {}) {
  const shouldFlushPending = options.flushPending !== false
  if (stopListeningPromise) {
    await stopListeningPromise
    return
  }

  if (!isListening.value)
    return

  stopListeningPromise = (async () => {
    try {
      console.info('[ChatArea] Stopping transcription...')

      // Send any pending text immediately if auto-send is enabled
      const textToSend = takePendingAutoSendText()
      if (shouldFlushPending && effectiveAutoSendEnabled.value && textToSend && !props.disabled) {
        try {
          await sendTextToChat(textToSend, 'auto_send')
          lessonAiriRuntime.markRecognizedText(textToSend)
          messageInput.value = ''
          lastLiveTranscriptPreview.value = ''
        }
        catch (err) {
          console.error('[ChatArea] Auto-send error on stop:', err)
        }
      }
      else {
        clearPendingAutoSend()
      }

      await stopStreamingTranscription(true)
      isListening.value = false
      lastLiveTranscriptPreview.value = ''
      lessonAiriRuntime.clearLiveTranscript()
      console.info('[ChatArea] Transcription stopped')
    }
    catch (err) {
      console.error('[ChatArea] Error stopping transcription:', err)
      isListening.value = false
    }
    finally {
      stopListeningPromise = null
    }
  })()

  await stopListeningPromise
}

// Start listening when microphone is enabled and stream is available
watch(enabled, async (val) => {
  if (val && stream.value) {
    // Microphone was just enabled and we have a stream, start transcription
    await startListening()
  }
  else if (!val && isListening.value) {
    // Microphone was disabled, stop transcription
    await stopListening()
  }
})

// Start listening when stream becomes available (if microphone is enabled)
watch(stream, async (val) => {
  if (val && enabled.value && !isListening.value) {
    // Stream became available and microphone is enabled, start transcription
    await startListening()
  }
  else if (!val && isListening.value) {
    // Stream was lost, stop transcription
    await stopListening()
  }
})

// Watch for auto-send setting changes and clear pending sends if disabled
watch(effectiveAutoSendEnabled, (enabled) => {
  if (!enabled) {
    // Auto-send was disabled - clear any pending auto-send
    clearPendingAutoSend()
    console.info('[ChatArea] Auto-send disabled, cleared pending text')
  }
})
</script>

<template>
  <div h="<md:full" flex gap-2 class="ph-no-capture">
    <div class="w-full flex flex-col gap-3">
      <div
        v-if="props.compactMode"
        class="sr-only"
        aria-live="polite"
      >
        <span data-testid="lesson-chat-status-label">{{ compactClassroomStatusLabel }}</span>
        <span data-testid="lesson-chat-status-detail">{{ compactClassroomStatusLabel }}</span>
        <span
          v-if="liveTranscriptText || lastRecognizedText"
          data-testid="lesson-chat-live-transcript"
        >
          实时转写：{{ liveTranscriptText || lastRecognizedText }}
        </span>
      </div>

      <div
        v-else
        :class="[
          statusPanelClasses,
          statusPanelShellClasses,
          'border backdrop-blur-xl',
        ]"
      >
        <div :class="['flex gap-2', props.compactMode ? 'items-center' : 'items-start']">
          <div
            :class="[
              'flex shrink-0 items-center justify-center rounded-full bg-sky-100/80 text-sky-700 dark:bg-white/8 dark:text-neutral-100',
              props.compactMode ? 'h-6 w-6' : 'mt-0.5 h-8 w-8',
            ]"
          >
            <div :class="[interactionStatus.icon, props.compactMode ? 'h-4 w-4' : 'h-4.5 w-4.5']" />
          </div>

          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <span
                data-testid="lesson-chat-status-label"
                :class="[
                  statusBadgeClasses,
                  'rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ring-inset',
                ]"
              >
                {{ interactionStatus.label }}
              </span>
              <span
                data-testid="lesson-chat-status-meta"
                class="min-w-0 truncate text-[11px] text-slate-500 dark:text-neutral-300/88"
              >
                {{ microphoneContextLabel }}
              </span>
            </div>

            <div
              data-testid="lesson-chat-status-detail"
              :class="[
                props.compactMode
                  ? 'sr-only'
                  : 'mt-1.5 text-xs leading-5 text-slate-600 dark:text-neutral-200/84',
              ]"
            >
              {{ interactionStatus.detail }}
            </div>

            <div
              v-if="!props.compactMode"
              class="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500 dark:text-neutral-400/92"
            >
              <span class="rounded-full bg-sky-100/70 px-2.5 py-1 dark:bg-white/6">
                {{ hearingProviderLabel }}
              </span>
              <span
                v-if="effectiveAutoSendEnabled"
                class="rounded-full bg-sky-100/70 px-2.5 py-1 dark:bg-white/6"
              >
                自动发送 {{ effectiveAutoSendDelay }}ms
              </span>
              <span
                v-if="liveTranscriptText || lastRecognizedText"
                data-testid="lesson-chat-live-transcript"
                class="max-w-full truncate rounded-full bg-emerald-100/80 px-2.5 py-1 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-100/90"
              >
                实时转写：{{ liveTranscriptText || lastRecognizedText }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div
        ref="inputShellRef"
        data-testid="lesson-chat-input-shell"
        :class="[
          composerShellClasses,
          'relative flex w-full cursor-text',
        ]"
        @pointerdown="focusMessageInputFromContainer"
      >
        <div
          :class="[
            props.compactMode
              ? 'flex w-[6.25rem] shrink-0 flex-col items-center justify-center gap-1.5 self-stretch rounded-[22px] bg-sky-50/70 p-1.5 ring-1 ring-inset ring-sky-100/90 dark:bg-slate-950/58 dark:ring-cyan-200/16'
              : 'flex shrink-0 items-end gap-2',
          ]"
        >
          <div
            v-if="props.compactMode"
            data-testid="lesson-chat-compact-status-label"
            :class="[
              compactClassroomStatusClasses,
              'w-full rounded-full px-2.5 py-1.5 text-center text-[12px] font-semibold leading-4',
            ]"
          >
            {{ compactClassroomStatusLabel }}
          </div>

          <div :class="[props.compactMode ? 'flex items-center gap-2' : 'flex items-end gap-2']">
            <button
              type="button"
              :class="[
                actionButtonSizeClasses,
                'flex items-center justify-center rounded-full border border-sky-100/90 bg-sky-50/95 text-slate-700 shadow-[0_10px_24px_-20px_rgba(15,23,42,0.42)] outline-none transition-colors duration-150 hover:bg-sky-100 dark:border-cyan-200/24 dark:bg-cyan-300/18 dark:text-cyan-50 dark:shadow-[0_12px_26px_-18px_rgba(103,232,249,0.86)] dark:hover:bg-cyan-300/28',
                { 'cursor-not-allowed opacity-45 active:scale-100': props.disabled || microphoneUnavailableReason },
              ]"
              :disabled="props.disabled || Boolean(microphoneUnavailableReason)"
              aria-label="麦克风"
              :title="microphoneButtonTitle"
              @click="void handleMicrophoneButtonClick()"
            >
              <Transition name="fade" mode="out-in">
                <IndicatorMicVolume v-if="enabled" class="h-6 w-6" />
                <div v-else class="i-ph:microphone h-6 w-6" />
              </Transition>
            </button>

            <button
              type="button"
              :class="[
                actionButtonSizeClasses,
                'flex items-center justify-center rounded-full border border-sky-100/90 bg-slate-100/92 text-slate-600 shadow-[0_10px_24px_-20px_rgba(15,23,42,0.38)] outline-none transition-colors duration-150 hover:bg-slate-200 dark:border-slate-200/18 dark:bg-slate-700/80 dark:text-slate-100 dark:shadow-[0_12px_26px_-18px_rgba(148,163,184,0.74)] dark:hover:bg-slate-600/90',
                { 'cursor-not-allowed opacity-40 active:scale-100': !canStopInteraction },
              ]"
              :disabled="!canStopInteraction"
              aria-label="停止听写"
              title="停止"
              @click="void handleStopInteraction()"
            >
              <div class="i-ph:hand-palm h-5.5 w-5.5" />
            </button>
          </div>
        </div>

        <div class="min-w-0 flex-1 self-center">
          <textarea
            id="lesson-chat-input"
            ref="textareaRef"
            v-model="messageInput"
            name="lesson-chat-input"
            :placeholder="chatInputPlaceholder"
            :disabled="props.disabled"
            rows="1"
            :class="[
              textareaClasses,
              'block w-full cursor-text resize-none overflow-y-auto bg-transparent px-0 font-medium text-slate-800 outline-none placeholder:text-slate-500 scrollbar-none dark:text-neutral-50 dark:placeholder:text-neutral-400',
              {
                'transition-colors-none placeholder:transition-colors-none': themeColorsHueDynamic,
              },
            ]"
            @input="handleTextareaInput"
            @keydown="handleTextareaKeydown"
            @compositionstart="isComposing = true"
            @compositionend="handleCompositionEnd"
          />

          <div v-if="!props.compactMode" class="mt-1 min-w-0">
            <div class="truncate text-xs text-slate-800 font-medium dark:text-neutral-100">
              {{ microphoneStatusLabel }}
            </div>
            <div class="mt-0.5 truncate text-[11px] text-slate-500 dark:text-neutral-400">
              {{ microphoneContextLabel }}
            </div>
          </div>
        </div>

        <button
          type="button"
          :class="[
            sendButtonClasses,
            'shrink-0 flex items-center justify-center gap-2 font-medium outline-none transition-colors duration-150',
            canSendMessage
              ? 'bg-primary-500 text-white shadow-sm hover:bg-primary-600'
              : 'cursor-not-allowed bg-slate-100 text-slate-400 dark:bg-white/8 dark:text-neutral-500',
          ]"
          :disabled="!canSendMessage"
          aria-label="发送"
          title="Send"
          @click="handleSend"
        >
          <div class="i-solar:arrow-up-bold h-4 w-4" />
          <span v-if="sendButtonLabelVisible" class="text-sm">发送</span>
        </button>
      </div>
    </div>
  </div>
</template>
