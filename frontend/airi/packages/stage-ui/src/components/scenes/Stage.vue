<script setup lang="ts">
import type { DuckDBWasmDrizzleDatabase } from '@proj-airi/drizzle-duckdb-wasm'
import type { Live2DLipSync, Live2DLipSyncOptions } from '@proj-airi/model-driver-lipsync'
import type { Profile } from '@proj-airi/model-driver-lipsync/shared/wlipsync'
import type { SpeechProviderWithExtraOptions } from '@xsai-ext/providers/utils'
import type { UnElevenLabsOptions } from 'unspeech'

import type { EmotionPayload } from '../../constants/emotions'

import { createPlaybackManager, createSpeechPipeline } from '@proj-airi/pipelines-audio'
import { Live2DScene } from '@proj-airi/stage-ui-live2d/components/scenes'
import { useLive2d } from '@proj-airi/stage-ui-live2d/stores/live2d'
import { createQueue } from '@proj-airi/stream-kit'
import { useBroadcastChannel } from '@vueuse/core'
// import { createTransformers } from '@xsai-transformers/embed'
// import embedWorkerURL from '@xsai-transformers/embed/worker?worker&url'
// import { embed } from '@xsai/embed'
import { generateSpeech } from '@xsai/generate-speech'
import { storeToRefs } from 'pinia'
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'

import { useDelayMessageQueue, useEmotionsMessageQueue } from '../../composables/queues'
import { llmInferenceEndToken } from '../../constants'
import { EMOTION_EmotionMotionName_value, EMOTION_VRMExpressionName_value, EmotionThinkMotionName } from '../../constants/emotions'
import { useAudioContext, useSpeakingStore } from '../../stores/audio'
import { useChatOrchestratorStore } from '../../stores/chat'
import { useLessonAiriRuntimeStore } from '../../stores/lesson-airi-runtime'
import { useAiriCardStore } from '../../stores/modules'
import { useSpeechStore } from '../../stores/modules/speech'
import { useProvidersStore } from '../../stores/providers'
import { useSettings } from '../../stores/settings'
import { useSpeechRuntimeStore } from '../../stores/speech-runtime'
import { resolveLessonInterruptDecision } from '../../utils/lesson-interrupt-policy'
import { applyLessonMouthIntensity, calculateAnalyserMouthOpen, computeLive2dSpeechMouthState, createLessonSpeechSegmentStream, isLessonRuntimePerformancePayload, resolveLessonSpeechStyleRuntimeOptions, resolveLive2dPerformanceApplyState, resolveSpeechVoiceForPlayback, shouldRunLive2dLipSyncLoop } from './runtime'

const props = withDefaults(defineProps<{
  paused?: boolean
  focusAt: { x: number, y: number }
  xOffset?: number | string
  yOffset?: number | string
  scale?: number
  lessonSafe?: boolean
  lessonSpeech?: boolean
  lessonChatRuntime?: boolean
}>(), { paused: false, scale: 1, lessonSafe: false, lessonSpeech: false, lessonChatRuntime: false })

const componentState = defineModel<'pending' | 'loading' | 'mounted'>('state', { default: 'pending' })

const db = ref<DuckDBWasmDrizzleDatabase>()
// const transformersProvider = createTransformers({ embedWorkerURL })

interface VrmSceneExpose {
  setExpression?: (expression: string, intensity?: number) => void
  canvasElement?: () => HTMLCanvasElement | undefined
  readRenderTargetRegionAtClientPoint?: (clientX: number, clientY: number, radius: number) => unknown
}

const ThreeScene = defineAsyncComponent(() => import('@proj-airi/stage-ui-three').then(module => module.ThreeScene))

const vrmViewerRef = ref<VrmSceneExpose>()
const live2dSceneRef = ref<InstanceType<typeof Live2DScene>>()
const vrmIdleAnimation = ref('')
let vrmAssetsLoaded = false

const settingsStore = useSettings()
const {
  stageModelRenderer,
  stageViewControlsEnabled,
  live2dDisableFocus,
  stageModelSelectedUrl,
  stageModelSelected,
  themeColorsHue,
  themeColorsHueDynamic,
  live2dIdleAnimationEnabled,
  live2dAutoBlinkEnabled,
  live2dForceAutoBlinkEnabled,
  live2dShadowEnabled,
  live2dMaxFps,
} = storeToRefs(settingsStore)
const { mouthOpenSize, nowSpeaking: characterNowSpeaking } = storeToRefs(useSpeakingStore())
const mouthFormValue = ref(0)
const audioContextStore = useAudioContext()
const currentAudioSource = ref<AudioBufferSourceNode>()

const chatHookCleanups: Array<() => void> = []
// WORKAROUND: clear previous handlers on unmount to avoid duplicate calls when this component remounts.
//             We keep per-hook disposers instead of wiping the global chat hooks to play nicely with
//             cross-window broadcast wiring.

const chatRuntimeEnabled = !props.lessonSafe || props.lessonChatRuntime
const speechRuntimeEnabled = !props.lessonSafe || props.lessonSpeech
const chatOrchestratorStore = chatRuntimeEnabled ? useChatOrchestratorStore() : null
const providersStore = speechRuntimeEnabled ? useProvidersStore() : null
const live2dStore = useLive2d()
const showStage = ref(true)
const stageModelRecoveryInFlight = ref(false)
const viewUpdateCleanups: Array<() => void> = []

// Caption + Presentation broadcast channels
type CaptionChannelEvent
  = | { type: 'caption-speaker', text: string }
    | { type: 'caption-assistant', text: string }
const { post: postCaption } = useBroadcastChannel<CaptionChannelEvent, CaptionChannelEvent>({ name: 'airi-caption-overlay' })
const assistantCaption = ref('')

type PresentEvent
  = | { type: 'assistant-reset' }
    | { type: 'assistant-append', text: string }
const { post: postPresent } = useBroadcastChannel<PresentEvent, PresentEvent>({ name: 'airi-chat-present' })

viewUpdateCleanups.push(live2dStore.onShouldUpdateView(async () => {
  showStage.value = false
  await settingsStore.updateStageModel()
  setTimeout(() => {
    showStage.value = true
  }, 100)
}))

const audioAnalyser = ref<AnalyserNode>()
const nowSpeaking = ref(false)
const lipSyncStarted = ref(false)
const lipSyncFallbackEnabled = ref(false)
const lipSyncLoopId = ref<number>()
const lipSyncTimeDomainBuffer = ref<Float32Array<ArrayBuffer>>()
const live2dLipSync = ref<Live2DLipSync>()
const live2dLipSyncOptions: Live2DLipSyncOptions = {
  cap: 1,
  volumeScale: 1,
  mouthUpdateIntervalMs: 50,
  mouthLerpWindowMs: 50,
}

function ensureStageAudioContext() {
  return audioContextStore.ensureAudioContext()
}

const speechStore = speechRuntimeEnabled ? useSpeechStore() : null
const activeCardId = computed(() => props.lessonSafe ? 'lesson' : useAiriCardStore().activeCard?.name ?? 'default')
const speechRuntimeStore = speechRuntimeEnabled ? useSpeechRuntimeStore() : null
const ssmlEnabled = computed(() => speechStore?.ssmlEnabled ?? false)
const activeSpeechProvider = computed(() => speechStore?.activeSpeechProvider ?? 'speech-noop')
const activeSpeechModel = computed(() => speechStore?.activeSpeechModel ?? '')
const activeSpeechVoice = computed(() => speechStore?.activeSpeechVoice)
const activeSpeechVoiceId = computed(() => speechStore?.activeSpeechVoiceId ?? '')
const pitch = computed(() => speechStore?.pitch ?? 0)
const lessonAiriRuntimeStore = props.lessonSafe ? useLessonAiriRuntimeStore() : null
const lessonAiriRuntimeRefs = lessonAiriRuntimeStore ? storeToRefs(lessonAiriRuntimeStore) : null
const lessonSpeechStyle = computed(() => lessonAiriRuntimeRefs?.currentSpeechStyle.value ?? 'normal')
const lessonMouthIntensity = computed(() => lessonAiriRuntimeRefs?.currentMouthIntensity.value ?? 1)
const lessonInterruptPolicy = computed(() => lessonAiriRuntimeRefs?.currentInterruptPolicy.value ?? 'barge_in_allowed')
const canDriveLessonMouthOpen = computed(() => !props.lessonSafe || (lessonAiriRuntimeRefs?.canDriveMouthOpen.value ?? false))
const lessonPerformancePlan = computed(() => lessonAiriRuntimeRefs?.currentPerformancePlan.value ?? null)

const { currentMotion, availableMotions } = storeToRefs(live2dStore)

function hasReadableSpeechText(text: string) {
  return /[\p{L}\p{N}]/u.test(text)
}

function resolveSpeechHttpFailure(error: unknown) {
  const candidates = [error]
  if (typeof error === 'object' && error !== null && 'cause' in error)
    candidates.push((error as { cause?: unknown }).cause)

  for (const candidate of candidates) {
    if (typeof candidate !== 'object' || candidate === null)
      continue
    const status = (candidate as { status?: unknown, statusCode?: unknown }).status
      ?? (candidate as { status?: unknown, statusCode?: unknown }).statusCode
    if (typeof status === 'number' && Number.isFinite(status)) {
      const statusText = (candidate as { statusText?: unknown }).statusText
      return {
        status,
        statusText: typeof statusText === 'string' ? statusText : '',
      }
    }
  }

  const message = error instanceof Error ? error.message : String(error ?? '')
  const match = /\bHTTP\s+(\d{3})\b/i.exec(message)
  if (match) {
    return {
      status: Number(match[1]),
      statusText: '',
    }
  }

  return {
    status: null,
    statusText: '',
  }
}

const emotionsQueue = createQueue<EmotionPayload>({
  handlers: [
    async (ctx) => {
      if (props.lessonSafe) {
        if (!isLessonRuntimePerformancePayload(ctx.data))
          return

        lessonAiriRuntimeStore?.applyPerformancePlan(ctx.data)
        return
      }

      const requestedMotion = ctx.data.motion || EMOTION_EmotionMotionName_value[ctx.data.name] || ''
      const requestedExpression = ctx.data.expression || EMOTION_VRMExpressionName_value[ctx.data.name] || ''

      if (stageModelRenderer.value === 'vrm') {
        // console.debug('VRM emotion anime: ', ctx.data)
        const value = requestedExpression
        if (!value) {
          lessonAiriRuntimeStore?.markPerformanceApplied({
            status: 'unsupported',
            requestedMotion,
            requestedExpression,
            fallbackReason: 'vrm_expression_unavailable',
          })
          return
        }

        if (!vrmViewerRef.value?.setExpression) {
          lessonAiriRuntimeStore?.markPerformanceApplied({
            status: 'unsupported',
            requestedMotion,
            requestedExpression: value,
            fallbackReason: 'vrm_expression_runtime_unavailable',
          })
          return
        }

        await vrmViewerRef.value.setExpression(value, ctx.data.intensity)
        lessonAiriRuntimeStore?.markPerformanceApplied({
          status: 'applied',
          requestedMotion,
          appliedMotion: requestedMotion,
          requestedExpression: value,
          appliedExpression: value,
        })
      }
      else if (stageModelRenderer.value === 'live2d') {
        applyLive2dPerformanceMotion({
          motion: requestedMotion,
          expression: requestedExpression,
        })
      }
    },
  ],
})

const emotionMessageContentQueue = useEmotionsMessageQueue(emotionsQueue)
emotionMessageContentQueue.onHandlerEvent('emotion', (emotion) => {
  // eslint-disable-next-line no-console
  console.debug('emotion detected', emotion)
})

const delaysQueue = useDelayMessageQueue()
delaysQueue.onHandlerEvent('delay', (delay) => {
  // eslint-disable-next-line no-console
  console.debug('delay detected', delay)
})

// Play special token: delay or emotion
function playSpecialToken(special: string) {
  delaysQueue.enqueue(special)
  emotionMessageContentQueue.enqueue(special)
}
const lipSyncNode = ref<AudioNode>()

declare global {
  interface Window {
    __PEPTUTOR_LIPSYNC_DEBUG__?: {
      state: () => Record<string, unknown>
    }
  }
}

async function ensureVrmAssetsLoaded() {
  if (vrmAssetsLoaded)
    return

  const { animations } = await import('@proj-airi/stage-ui-three/assets/vrm')
  vrmIdleAnimation.value = animations.idleLoop.toString()
  vrmAssetsLoaded = true
}

async function playFunction(item: Parameters<Parameters<typeof createPlaybackManager<AudioBuffer>>[0]['play']>[0], signal: AbortSignal): Promise<void> {
  if (!item.audio) {
    lessonAiriRuntimeStore?.markSpeechPlaybackError('没有可播放的 TTS 音频。', {
      playbackId: item.id,
      replyId: item.intentId,
      stage: 'missing_audio',
      playbackState: 'skipped',
      reason: 'audio_element_missing',
    })
    return
  }

  const audioContext = ensureStageAudioContext()

  // Teacher speech reaches this point after AIRI chat hooks emit assistant tokens.
  // Prepare analyser/lip-sync at playback time so Live2D can react to teacher audio.
  setupAnalyser()
  await setupLipSync()

  // Ensure audio context is resumed (browsers suspend it by default until user interaction)
  if (audioContext.state === 'suspended') {
    try {
      await audioContext.resume()
    }
    catch (error) {
      lessonAiriRuntimeStore?.markSpeechPlaybackError(error instanceof Error ? error.message : '浏览器拒绝启动音频上下文。', {
        playbackId: item.id,
        replyId: item.intentId,
        stage: 'audio_context',
        playbackState: error instanceof DOMException && error.name === 'NotAllowedError'
          ? 'autoplay_blocked'
          : 'audio_context_suspended',
        reason: error instanceof DOMException && error.name === 'NotAllowedError'
          ? 'autoplay_blocked'
          : 'audio_context_suspended',
      })
      return
    }

    if (audioContext.state === 'suspended') {
      lessonAiriRuntimeStore?.markSpeechPlaybackError('AudioContext remained suspended after resume().', {
        playbackId: item.id,
        replyId: item.intentId,
        stage: 'audio_context',
        playbackState: 'audio_context_suspended',
        reason: 'audio_context_suspended',
      })
      return
    }
  }

  const source = audioContext.createBufferSource()
  currentAudioSource.value = source
  source.buffer = item.audio

  source.connect(audioContext.destination)
  if (audioAnalyser.value)
    source.connect(audioAnalyser.value)
  if (lipSyncNode.value)
    source.connect(lipSyncNode.value)

  return new Promise<void>((resolve, reject) => {
    let settled = false
    const settlePlayback = (error?: unknown) => {
      if (settled)
        return
      settled = true
      if (currentAudioSource.value === source)
        currentAudioSource.value = undefined
      nowSpeaking.value = false
      characterNowSpeaking.value = false
      mouthOpenSize.value = 0
      mouthFormValue.value = 0
      if (error) {
        lessonAiriRuntimeStore?.markSpeechPlaybackError(error instanceof Error ? error.message : 'TTS 播放失败。', {
          playbackId: item.id,
          replyId: item.intentId,
          stage: 'playback',
          playbackState: 'play_rejected',
          reason: 'source_start_rejected',
        })
        reject(error)
        return
      }
      resolve()
    }

    const stopPlayback = (status: 'ended' | 'interrupted', stopReason: string = status) => {
      if (settled)
        return
      try {
        source.stop()
        source.disconnect()
      }
      catch {}
      lessonAiriRuntimeStore?.markSpeechPlaybackEnd(status, {
        playbackId: item.id,
        replyId: item.intentId,
        stopReason,
      })
      settlePlayback()
    }

    if (signal.aborted) {
      stopPlayback('interrupted', String(signal.reason || 'interrupted'))
      return
    }

    const abortPlayback = () => stopPlayback('interrupted', String(signal.reason || 'interrupted'))
    signal.addEventListener('abort', abortPlayback, { once: true })
    source.onended = () => {
      signal.removeEventListener('abort', abortPlayback)
      stopPlayback('ended')
    }

    try {
      lessonAiriRuntimeStore?.markSpeechPlaybackRequested({
        playbackId: item.id,
        replyId: item.intentId,
        audioContextState: audioContext.state,
        reason: 'web_audio_buffer_source_start',
      })
      source.start(0)
      nowSpeaking.value = true
      characterNowSpeaking.value = true
      lessonAiriRuntimeStore?.markSpeechPlaybackStart({
        playbackId: item.id,
        replyId: item.intentId,
        audioContextState: audioContext.state,
      })
    }
    catch (error) {
      signal.removeEventListener('abort', abortPlayback)
      settlePlayback(error)
    }
  })
}

const playbackManager = !speechRuntimeEnabled
  ? null
  : createPlaybackManager<AudioBuffer>({
      play: playFunction,
      maxVoices: 1,
      overflowPolicy: 'queue',
    })

const speechPipeline = !speechRuntimeEnabled || !playbackManager
  ? null
  : createSpeechPipeline<AudioBuffer>({
      tts: async (request, signal) => {
        if (signal.aborted || !providersStore || !speechStore)
          return null

        if (!request.text && !request.special)
          return null

        if (request.text && !hasReadableSpeechText(request.text))
          return null

        if (activeSpeechProvider.value === 'speech-noop' || !activeSpeechProvider.value) {
          lessonAiriRuntimeStore?.markSpeechPlaybackError('TTS provider is not configured.', {
            replyId: request.intentId,
            stage: 'configuration',
          })
          return null
        }

        const provider = await providersStore.getProviderInstance(activeSpeechProvider.value) as SpeechProviderWithExtraOptions<string, UnElevenLabsOptions>
        if (!provider) {
          console.error('Failed to initialize speech provider')
          lessonAiriRuntimeStore?.markSpeechPlaybackError(`Failed to initialize TTS provider: ${activeSpeechProvider.value}.`, {
            replyId: request.intentId,
            stage: 'configuration',
          })
          return null
        }

        const providerConfig = {
          ...providersStore.getProviderConfig(activeSpeechProvider.value),
        }
        const lessonSpeechOptions = resolveLessonSpeechStyleRuntimeOptions(lessonSpeechStyle.value)
        if (props.lessonSafe && activeSpeechProvider.value === 'peptutor-edge-tts' && lessonSpeechOptions.edgeRate !== '+0%') {
          providerConfig.rate = lessonSpeechOptions.edgeRate
        }
        if (props.lessonSafe && ssmlEnabled.value && lessonSpeechOptions.ssmlSpeed !== 1) {
          providerConfig.speed = lessonSpeechOptions.ssmlSpeed
        }

        // For OpenAI Compatible providers, always use provider config for model and voice
        // since these are manually configured in provider settings
        let model = activeSpeechModel.value || (typeof providerConfig.model === 'string' ? providerConfig.model.trim() : '')
        let voice = resolveSpeechVoiceForPlayback(
          activeSpeechProvider.value,
          activeSpeechVoice.value,
          activeSpeechVoiceId.value
          || (typeof providerConfig.voiceId === 'string' ? providerConfig.voiceId : '')
          || (typeof providerConfig.voice === 'string' ? providerConfig.voice : ''),
        )

        if (activeSpeechProvider.value === 'openai-compatible-audio-speech') {
          if (providerConfig?.model) {
            model = providerConfig.model as string
          }
          else {
            model = 'tts-1'
            console.warn('[Speech Pipeline] OpenAI Compatible: No model in provider config, using default', { providerConfig })
          }

          if (providerConfig?.voice) {
            voice = {
              id: providerConfig.voice as string,
              name: providerConfig.voice as string,
              description: providerConfig.voice as string,
              previewURL: '',
              languages: [{ code: 'en', title: 'English' }],
              provider: activeSpeechProvider.value,
              gender: 'neutral',
            }
          }
          else {
            voice = {
              id: 'alloy',
              name: 'alloy',
              description: 'alloy',
              previewURL: '',
              languages: [{ code: 'en', title: 'English' }],
              provider: activeSpeechProvider.value,
              gender: 'neutral',
            }
            console.warn('[Speech Pipeline] OpenAI Compatible: No voice in provider config, using default', { providerConfig })
          }
        }

        if (!model || !voice) {
          lessonAiriRuntimeStore?.markSpeechPlaybackError(
            !model
              ? `TTS model is not configured for ${activeSpeechProvider.value}.`
              : `TTS voice is not configured for ${activeSpeechProvider.value}.`,
            {
              replyId: request.intentId,
              stage: 'configuration',
            },
          )
          return null
        }

        const input = ssmlEnabled.value
          ? speechStore.generateSSML(request.text, voice, { ...providerConfig, pitch: pitch.value })
          : request.text

        lessonAiriRuntimeStore?.markSpeechSynthesisStart({
          provider: activeSpeechProvider.value,
          model,
          voice: voice.id,
          text: request.text,
          replyId: request.intentId,
        })

        let res: ArrayBuffer
        try {
          const speechRequest = provider.speech(model, providerConfig)
          const speechFetch = speechRequest.fetch
          if (speechFetch) {
            speechRequest.fetch = (async (fetchInput: URL, fetchInit?: RequestInit) => {
              const response = await speechFetch(fetchInput, fetchInit ?? {})
              lessonAiriRuntimeStore?.markSpeechSynthesisHttpResult({
                status: response.status,
                statusText: response.statusText,
              })
              return response
            }) as typeof speechFetch
          }

          res = await generateSpeech({
            ...speechRequest,
            input,
            voice: voice.id,
          })
        }
        catch (error) {
          const httpFailure = resolveSpeechHttpFailure(error)
          lessonAiriRuntimeStore?.markSpeechPlaybackError(error instanceof Error ? error.message : 'TTS 合成失败。', {
            replyId: request.intentId,
            stage: 'synthesis',
            httpStatus: httpFailure.status,
            httpStatusText: httpFailure.statusText,
          })
          return null
        }

        if (signal.aborted)
          return null
        if (!res || res.byteLength === 0) {
          lessonAiriRuntimeStore?.markSpeechPlaybackError('TTS 返回了空音频。', {
            replyId: request.intentId,
            stage: 'empty_audio',
          })
          return null
        }

        try {
          const audioByteLength = res.byteLength
          const audioContext = ensureStageAudioContext()
          const audioBuffer = await audioContext.decodeAudioData(res)
          lessonAiriRuntimeStore?.markSpeechSynthesisReady({
            audioByteLength,
            audioDurationMs: audioBuffer.duration * 1000,
          })
          return audioBuffer
        }
        catch (error) {
          lessonAiriRuntimeStore?.markSpeechPlaybackError(error instanceof Error ? error.message : 'TTS 解码失败。', {
            replyId: request.intentId,
            stage: 'decode',
          })
          return null
        }
      },
      playback: playbackManager,
      segmenter: props.lessonSafe ? createLessonSpeechSegmentStream : undefined,
    })

if (speechRuntimeStore && playbackManager && speechPipeline) {
  void speechRuntimeStore.registerHost(speechPipeline)
  speechRuntimeStore.registerPlaybackController({
    stopByOwner: playbackManager.stopByOwner,
    stopAll: playbackManager.stopAll,
  })

  speechPipeline.on('onSpecial', (segment) => {
    if (segment.special)
      playSpecialToken(segment.special)
  })

  playbackManager.onEnd(({ item }) => {
    if (item.special)
      playSpecialToken(item.special)

    nowSpeaking.value = false
    characterNowSpeaking.value = false
    lessonAiriRuntimeStore?.setTeacherSpeaking(false)
    mouthOpenSize.value = 0
    mouthFormValue.value = 0
  })

  playbackManager.onStart(({ item }) => {
    assistantCaption.value += ` ${item.text}`
    try {
      postCaption({ type: 'caption-assistant', text: assistantCaption.value })
    }
    catch {
    }
    try {
      postPresent({ type: 'assistant-append', text: item.text })
    }
    catch {
    }
  })
}

function startLipSyncLoop() {
  if (lipSyncLoopId.value)
    return

  const tick = () => {
    const analyserMouthOpen = readAnalyserMouthOpen()

    if (!nowSpeaking.value || !canDriveLessonMouthOpen.value || !live2dLipSync.value) {
      if (!nowSpeaking.value || !canDriveLessonMouthOpen.value) {
        mouthOpenSize.value = 0
        mouthFormValue.value = 0
      }
      else if (lipSyncFallbackEnabled.value) {
        mouthOpenSize.value = applyLessonMouthIntensity(analyserMouthOpen, lessonMouthIntensity.value)
        mouthFormValue.value = 0
      }
      else {
        mouthOpenSize.value = 0
        mouthFormValue.value = 0
      }
    }
    else {
      const mouthState = computeLive2dSpeechMouthState({
        analyserMouthOpen,
        lipSyncMouthOpen: live2dLipSync.value.getMouthOpen(),
        mouthIntensity: lessonMouthIntensity.value,
        vowelWeights: live2dLipSync.value.getVowelWeights(),
      })
      mouthOpenSize.value = mouthState.mouthOpen
      mouthFormValue.value = mouthState.mouthForm
    }
    lipSyncLoopId.value = requestAnimationFrame(tick)
  }

  lipSyncLoopId.value = requestAnimationFrame(tick)
}

function stopLipSyncLoop() {
  if (lipSyncLoopId.value) {
    cancelAnimationFrame(lipSyncLoopId.value)
    lipSyncLoopId.value = undefined
  }

  mouthOpenSize.value = 0
  mouthFormValue.value = 0
}

function resetLive2dLipSync() {
  stopLipSyncLoop()

  try {
    lipSyncNode.value?.disconnect()
  }
  catch {

  }

  lipSyncNode.value = undefined
  lipSyncFallbackEnabled.value = false
  lipSyncTimeDomainBuffer.value = undefined
  live2dLipSync.value = undefined
  lipSyncStarted.value = false
}

function syncLipSyncLoop() {
  if (shouldRunLive2dLipSyncLoop({
    stageModelRenderer: stageModelRenderer.value,
    paused: Boolean(props.paused),
  }) && (lipSyncStarted.value || lipSyncFallbackEnabled.value)) {
    startLipSyncLoop()
    return
  }

  stopLipSyncLoop()
}

function readAnalyserMouthOpen() {
  if (!audioAnalyser.value)
    return 0

  if (!lipSyncTimeDomainBuffer.value || lipSyncTimeDomainBuffer.value.length !== audioAnalyser.value.fftSize) {
    lipSyncTimeDomainBuffer.value = new Float32Array(audioAnalyser.value.fftSize) as Float32Array<ArrayBuffer>
  }

  audioAnalyser.value.getFloatTimeDomainData(lipSyncTimeDomainBuffer.value)
  return calculateAnalyserMouthOpen(lipSyncTimeDomainBuffer.value)
}

function registerLipSyncDebugHandle() {
  if (!import.meta.env.DEV || typeof window === 'undefined')
    return

  window.__PEPTUTOR_LIPSYNC_DEBUG__ = {
    state: () => ({
      nowSpeaking: nowSpeaking.value,
      mouthOpenSize: mouthOpenSize.value,
      mouthFormValue: mouthFormValue.value,
      lipSyncStarted: lipSyncStarted.value,
      lipSyncFallbackEnabled: lipSyncFallbackEnabled.value,
      analyserMouthOpen: readAnalyserMouthOpen(),
      audioWorkletAvailable: Boolean(audioContextStore.audioContext?.audioWorklet?.addModule),
      live2dLipSyncMouthOpen: live2dLipSync.value?.getMouthOpen() ?? null,
      live2dLipSyncVolume: live2dLipSync.value?.node.volume ?? null,
      live2dLipSyncWeights: live2dLipSync.value?.node.weights ?? null,
      currentAudioSourceConnected: Boolean(currentAudioSource.value),
      lessonSpeechStyle: lessonSpeechStyle.value,
      lessonMouthIntensity: lessonMouthIntensity.value,
      lessonInterruptPolicy: lessonInterruptPolicy.value,
      lessonPerformanceSource: lessonAiriRuntimeStore?.currentPerformancePlan?.performanceSource ?? null,
      lessonPerformanceApplyStatus: lessonAiriRuntimeStore?.performanceApplyStatus ?? null,
      lessonPerformanceAppliedMotion: lessonAiriRuntimeStore?.appliedMotion ?? null,
      lessonPerformanceAppliedExpression: lessonAiriRuntimeStore?.appliedExpression ?? null,
      lessonPerformanceFallbackReason: lessonAiriRuntimeStore?.performanceFallbackReason ?? null,
    }),
  }
}

function clearLipSyncDebugHandle() {
  if (!import.meta.env.DEV || typeof window === 'undefined')
    return

  delete window.__PEPTUTOR_LIPSYNC_DEBUG__
}

async function setupLipSync() {
  if (stageModelRenderer.value !== 'live2d') {
    resetLive2dLipSync()
    return
  }

  if (lipSyncStarted.value || lipSyncFallbackEnabled.value)
    return

  const audioContext = ensureStageAudioContext()

  if (!audioContext.audioWorklet?.addModule) {
    lipSyncFallbackEnabled.value = true
    syncLipSyncLoop()
    console.warn('[Stage] AudioWorklet unavailable, using analyser fallback for Live2D lip sync')
    return
  }

  try {
    const [
      { createLive2DLipSync },
      { wlipsyncProfile },
    ] = await Promise.all([
      import('@proj-airi/model-driver-lipsync'),
      import('@proj-airi/model-driver-lipsync/shared/wlipsync'),
    ])
    const lipSync = await createLive2DLipSync(audioContext, wlipsyncProfile as Profile, live2dLipSyncOptions)
    live2dLipSync.value = lipSync
    lipSyncNode.value = lipSync.node
    await audioContext.resume()
    lipSyncStarted.value = true
    lipSyncFallbackEnabled.value = false
    syncLipSyncLoop()
  }
  catch (error) {
    lipSyncNode.value = undefined
    live2dLipSync.value = undefined
    lipSyncStarted.value = false
    lipSyncFallbackEnabled.value = true
    syncLipSyncLoop()
    console.warn('[Stage] Falling back to analyser-driven Live2D lip sync', error)
  }
}

function setupAnalyser() {
  if (!audioAnalyser.value) {
    const audioContext = ensureStageAudioContext()
    audioAnalyser.value = audioContext.createAnalyser()
  }
}

function applyLive2dPerformanceMotion(profile: {
  motion: string
  expression: string
}, options: {
  recordPerformanceState?: boolean
} = {}) {
  const recordPerformanceState = options.recordPerformanceState ?? true
  const resolution = resolveLive2dPerformanceApplyState(profile, availableMotions.value)
  if (resolution.motion) {
    currentMotion.value = resolution.motion
  }

  if (!recordPerformanceState)
    return

  lessonAiriRuntimeStore?.markPerformanceApplied({
    status: resolution.status,
    requestedMotion: resolution.requestedMotion,
    appliedMotion: resolution.appliedMotion,
    requestedExpression: resolution.requestedExpression,
    appliedExpression: resolution.appliedExpression,
    fallbackReason: resolution.fallbackReason,
  })
}

function live2dMotionCatalogKey() {
  return availableMotions.value
    .map(motion => `${motion.motionName}:${motion.motionIndex ?? ''}:${motion.fileName ?? ''}`)
    .join('|')
}

let lastLessonPerformanceApplyKey = ''

async function applyCurrentLessonPerformancePlan() {
  if (!props.lessonSafe || !lessonAiriRuntimeStore)
    return

  const plan = lessonPerformancePlan.value
  if (!plan) {
    lastLessonPerformanceApplyKey = ''
    return
  }

  const applyKey = [
    plan.updatedAt,
    stageModelRenderer.value,
    stageModelRenderer.value === 'live2d' ? live2dMotionCatalogKey() : '',
  ].join(':')
  if (applyKey === lastLessonPerformanceApplyKey)
    return
  lastLessonPerformanceApplyKey = applyKey

  if (stageModelRenderer.value === 'live2d') {
    applyLive2dPerformanceMotion({
      motion: plan.motion,
      expression: plan.expression,
    })
    return
  }

  if (stageModelRenderer.value === 'vrm') {
    if (!plan.expression) {
      lessonAiriRuntimeStore.markPerformanceApplied({
        status: 'unsupported',
        requestedMotion: plan.motion,
        requestedExpression: plan.expression,
        fallbackReason: 'vrm_expression_not_requested',
      })
      return
    }

    if (!vrmViewerRef.value?.setExpression) {
      lessonAiriRuntimeStore.markPerformanceApplied({
        status: 'unsupported',
        requestedMotion: plan.motion,
        requestedExpression: plan.expression,
        fallbackReason: 'vrm_expression_runtime_unavailable',
      })
      return
    }

    await vrmViewerRef.value.setExpression(plan.expression, plan.emotionIntensity)
    lessonAiriRuntimeStore.markPerformanceApplied({
      status: 'applied',
      requestedMotion: plan.motion,
      appliedMotion: plan.motion,
      requestedExpression: plan.expression,
      appliedExpression: plan.expression,
    })
    return
  }

  lessonAiriRuntimeStore.markPerformanceApplied({
    status: 'unsupported',
    requestedMotion: plan.motion,
    requestedExpression: plan.expression,
    fallbackReason: `stage_renderer_unsupported:${stageModelRenderer.value}`,
  })
}

function applyLessonClassroomAction(profile: {
  motion: string
  expression: string
  intensity: number
}) {
  if (stageModelRenderer.value === 'vrm') {
    void vrmViewerRef.value?.setExpression?.(profile.expression, profile.intensity)
    return
  }

  if (stageModelRenderer.value === 'live2d') {
    applyLive2dPerformanceMotion(profile, { recordPerformanceState: false })
  }
}

let currentChatIntent: ReturnType<ReturnType<typeof useSpeechRuntimeStore>['openIntent']> | null = null
let lessonBargeInActive = false

if (chatOrchestratorStore && speechRuntimeStore && playbackManager) {
  chatHookCleanups.push(chatOrchestratorStore.onBeforeMessageComposed(async () => {
    const interruptDecision = props.lessonSafe
      ? resolveLessonInterruptDecision({
          event: 'new_teacher_turn',
          policy: lessonInterruptPolicy.value,
        })
      : null
    const stopReason = interruptDecision?.rawStopReason || 'new-message'
    if (!props.lessonSafe || interruptDecision?.shouldStopPlayback)
      playbackManager.stopAll(stopReason)

    if (!props.lessonSafe) {
      setupAnalyser()
      await setupLipSync()
    }
    assistantCaption.value = ''
    try {
      postCaption({ type: 'caption-assistant', text: '' })
    }
    catch (error) {
      console.warn('[Stage] Failed to post caption reset (channel may be closed)', { error })
    }
    try {
      postPresent({ type: 'assistant-reset' })
    }
    catch (error) {
      console.warn('[Stage] Failed to post present reset (channel may be closed)', { error })
    }

    if (currentChatIntent) {
      if (!props.lessonSafe || interruptDecision?.shouldStopPlayback)
        currentChatIntent.cancel(stopReason)
      else
        currentChatIntent.end()
      currentChatIntent = null
    }

    currentChatIntent = speechRuntimeStore.openIntent({
      ownerId: activeCardId.value,
      priority: 'normal',
      behavior: interruptDecision?.speechIntentBehavior || 'interrupt',
    })
  }))

  chatHookCleanups.push(chatOrchestratorStore.onBeforeSend(async () => {
    if (props.lessonSafe)
      return

    currentMotion.value = { group: EmotionThinkMotionName }
  }))

  chatHookCleanups.push(chatOrchestratorStore.onTokenLiteral(async (literal) => {
    currentChatIntent?.writeLiteral(literal)
  }))

  chatHookCleanups.push(chatOrchestratorStore.onTokenSpecial(async (special) => {
    currentChatIntent?.writeSpecial(special)
  }))

  chatHookCleanups.push(chatOrchestratorStore.onStreamEnd(async () => {
    delaysQueue.enqueue(llmInferenceEndToken)
    currentChatIntent?.writeFlush()
  }))

  chatHookCleanups.push(chatOrchestratorStore.onAssistantResponseEnd(async (_message) => {
    currentChatIntent?.end()
    currentChatIntent = null
    // const res = await embed({
    //   ...transformersProvider.embed('Xenova/nomic-embed-text-v1'),
    //   input: message,
    // })

    // await db.value?.execute(`INSERT INTO memory_test (vec) VALUES (${JSON.stringify(res.embedding)});`)
  }))
}

if (lessonAiriRuntimeStore) {
  const { hearingListening, microphoneEnabled, inputVolumeLevel, classroomState } = storeToRefs(lessonAiriRuntimeStore)

  watch([
    () => lessonPerformancePlan.value?.updatedAt ?? 0,
    stageModelRenderer,
    () => live2dMotionCatalogKey(),
  ], () => {
    void applyCurrentLessonPerformancePlan()
  }, { immediate: true })

  watch([hearingListening, microphoneEnabled, inputVolumeLevel, nowSpeaking, classroomState, lessonInterruptPolicy], ([listening, enabled, volume, speaking, classroom, interruptPolicy]) => {
    if (!props.lessonSafe)
      return

    const learnerSpeaking = listening && volume >= 12
    const interruptDecision = resolveLessonInterruptDecision({
      event: 'volume_barge_in',
      policy: interruptPolicy,
    })
    if (learnerSpeaking && speaking && interruptDecision.shouldStopPlayback && !lessonBargeInActive) {
      speechRuntimeStore?.stopAll(interruptDecision.rawStopReason)
      currentChatIntent?.cancel(interruptDecision.rawStopReason)
      currentChatIntent = null
      lessonBargeInActive = true
    }
    else if (!learnerSpeaking) {
      lessonBargeInActive = false
    }

    if (speaking)
      return

    if (learnerSpeaking && volume >= 55) {
      applyLessonClassroomAction({
        motion: 'Surprise',
        expression: 'surprised',
        intensity: 0.7,
      })
      return
    }

    if (classroom === 'interrupted') {
      applyLessonClassroomAction({
        motion: EMOTION_EmotionMotionName_value.question,
        expression: 'think',
        intensity: 0.86,
      })
      return
    }

    if (classroom === 'learner_speaking') {
      applyLessonClassroomAction({
        motion: EMOTION_EmotionMotionName_value.curious,
        expression: 'think',
        intensity: 0.72,
      })
      return
    }

    if (classroom === 'thinking') {
      applyLessonClassroomAction({
        motion: EmotionThinkMotionName,
        expression: 'think',
        intensity: 0.74,
      })
      return
    }

    if (learnerSpeaking) {
      applyLessonClassroomAction({
        motion: EMOTION_EmotionMotionName_value.curious,
        expression: 'think',
        intensity: 0.72,
      })
      return
    }

    if (listening || enabled) {
      applyLessonClassroomAction({
        motion: EmotionThinkMotionName,
        expression: 'neutral',
        intensity: 0.58,
      })
    }
  }, { immediate: true })
}

// Resume audio context on first user interaction (browser requirement)
let audioContextResumed = false
function resumeAudioContextOnInteraction() {
  if (audioContextResumed)
    return
  audioContextResumed = true
  audioContextStore.resumeAudioContext().catch(() => {
    // Ignore errors - audio context will be resumed when needed
  })
}

// Add event listeners for user interaction
if (typeof window !== 'undefined') {
  const events = ['click', 'touchstart', 'keydown']
  events.forEach((event) => {
    window.addEventListener(event, resumeAudioContextOnInteraction, { once: true, passive: true })
  })
}

onMounted(async () => {
  if (props.lessonSafe) {
    return
  }

  const [
    { drizzle },
    { getImportUrlBundles },
  ] = await Promise.all([
    import('@proj-airi/drizzle-duckdb-wasm'),
    import('@proj-airi/drizzle-duckdb-wasm/bundles/import-url-browser'),
  ])

  db.value = drizzle({ connection: { bundles: getImportUrlBundles() } })
  await db.value.execute(`CREATE TABLE memory_test (vec FLOAT[768]);`)
})

watch([stageModelRenderer, () => props.paused], ([renderer]) => {
  if (renderer === 'vrm') {
    void ensureVrmAssetsLoaded()
  }

  if (renderer !== 'live2d') {
    resetLive2dLipSync()
    return
  }

  syncLipSyncLoop()
}, { immediate: true })

async function handleStageModelError(error: unknown) {
  console.error('[Stage] Failed to load stage model:', error)

  if (stageModelRecoveryInFlight.value) {
    return
  }

  stageModelRecoveryInFlight.value = true

  try {
    await settingsStore.fallbackStageModel(stageModelSelected.value)
  }
  catch (fallbackError) {
    console.error('[Stage] Failed to recover stage model:', fallbackError)
  }
  finally {
    stageModelRecoveryInFlight.value = false
  }
}

function canvasElement() {
  if (stageModelRenderer.value === 'live2d')
    return live2dSceneRef.value?.canvasElement()

  else if (stageModelRenderer.value === 'vrm')
    return vrmViewerRef.value?.canvasElement?.()
}

function readRenderTargetRegionAtClientPoint(clientX: number, clientY: number, radius: number) {
  if (stageModelRenderer.value !== 'vrm')
    return null

  return vrmViewerRef.value?.readRenderTargetRegionAtClientPoint?.(clientX, clientY, radius) ?? null
}

onUnmounted(() => {
  currentChatIntent?.cancel('stage-unmount')
  currentChatIntent = null
  speechPipeline?.stopAll('stage-unmount')
  lessonAiriRuntimeStore?.setTeacherSpeaking(false)
  characterNowSpeaking.value = false
  resetLive2dLipSync()
  chatHookCleanups.forEach(dispose => dispose?.())
  viewUpdateCleanups.forEach(dispose => dispose?.())
  speechRuntimeStore?.clearPlaybackController()
  void speechRuntimeStore?.dispose()
  clearLipSyncDebugHandle()
})

registerLipSyncDebugHandle()

defineExpose({
  canvasElement,
  readRenderTargetRegionAtClientPoint,
})
</script>

<template>
  <div relative h-full w-full>
    <div h-full w-full>
      <Live2DScene
        v-if="stageModelRenderer === 'live2d' && showStage"
        ref="live2dSceneRef"
        v-model:state="componentState"
        min-w="50% <lg:full" min-h="100 sm:100"
        h-full w-full flex-1
        :model-src="stageModelSelectedUrl"
        :model-id="stageModelSelected"
        :focus-at="focusAt"
        :mouth-open-size="mouthOpenSize"
        :mouth-form-value="mouthFormValue"
        :paused="paused"
        :x-offset="xOffset"
        :y-offset="yOffset"
        :scale="scale"
        :disable-focus-at="live2dDisableFocus"
        :theme-colors-hue="themeColorsHue"
        :theme-colors-hue-dynamic="themeColorsHueDynamic"
        :live2d-idle-animation-enabled="live2dIdleAnimationEnabled"
        :live2d-auto-blink-enabled="live2dAutoBlinkEnabled"
        :live2d-force-auto-blink-enabled="live2dForceAutoBlinkEnabled"
        :live2d-shadow-enabled="live2dShadowEnabled"
        :live2d-max-fps="live2dMaxFps"
        @error="handleStageModelError"
      />
      <ThreeScene
        v-if="stageModelRenderer === 'vrm' && showStage"
        ref="vrmViewerRef"
        v-model:state="componentState"
        min-w="50% <lg:full" min-h="100 sm:100" h-full w-full flex-1
        :model-src="stageModelSelectedUrl"
        :idle-animation="vrmIdleAnimation"
        :paused="paused"
        :show-axes="stageViewControlsEnabled"
        :current-audio-source="currentAudioSource"
        @error="handleStageModelError"
      />
    </div>
  </div>
</template>
