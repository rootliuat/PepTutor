import { resolvePepTutorRuntimeEnv } from '../utils/peptutor-runtime-config'
import { useSpeechStore } from './modules/speech'
import { useProvidersStore } from './providers'

export const LESSON_FALLBACK_SPEECH_PROVIDER_ID = 'kokoro-local'

function normalizeString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function kokoroFallbackEnabled() {
  return normalizeString(resolvePepTutorRuntimeEnv().VITE_PEPTUTOR_ENABLE_KOKORO_FALLBACK).toLowerCase() === 'true'
}

export async function ensureLessonSpeechFallbackProvider(): Promise<boolean> {
  const speechStore = useSpeechStore()
  const providersStore = useProvidersStore()
  const activeProviderId = normalizeString(speechStore.activeSpeechProvider)

  if (activeProviderId && activeProviderId !== 'speech-noop') {
    return providersStore.providerRuntimeState[activeProviderId]?.isConfigured !== false
  }

  if (!kokoroFallbackEnabled()) {
    return false
  }

  providersStore.initializeProvider(LESSON_FALLBACK_SPEECH_PROVIDER_ID)

  const config = providersStore.getProviderConfig(LESSON_FALLBACK_SPEECH_PROVIDER_ID)
  const providerModel = normalizeString(config?.model)
  const configured = await providersStore.validateProvider(LESSON_FALLBACK_SPEECH_PROVIDER_ID, { force: true })
  if (!configured) {
    return false
  }

  speechStore.activeSpeechProvider = LESSON_FALLBACK_SPEECH_PROVIDER_ID
  if (!normalizeString(speechStore.activeSpeechModel) && providerModel) {
    speechStore.activeSpeechModel = providerModel
  }

  const configuredVoiceId = normalizeString(config?.voiceId)
  if (!normalizeString(speechStore.activeSpeechVoiceId) && configuredVoiceId) {
    speechStore.activeSpeechVoiceId = configuredVoiceId
  }

  if (!normalizeString(speechStore.activeSpeechVoiceId)) {
    const voices = await speechStore.loadVoicesForProvider(LESSON_FALLBACK_SPEECH_PROVIDER_ID)
    if (voices[0]?.id) {
      speechStore.activeSpeechVoiceId = voices[0].id
    }
  }

  return Boolean(normalizeString(speechStore.activeSpeechVoiceId))
}
