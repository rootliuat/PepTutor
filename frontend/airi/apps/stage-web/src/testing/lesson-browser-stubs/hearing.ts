import { computed, ref } from 'vue'

const activeTranscriptionProvider = ref('browser-web-speech-api')
const activeTranscriptionModel = ref('web-speech-api')
const autoSendEnabled = ref(false)
const autoSendDelay = ref(2000)
const configured = computed(() => Boolean(activeTranscriptionProvider.value))

const hearingStore = {
  activeTranscriptionProvider,
  activeTranscriptionModel,
  autoSendEnabled,
  autoSendDelay,
  configured,
}

const hearingPipelineStore = {
  supportsStreamInput: ref(true),
  error: ref(''),
  async transcribeForMediaStream() {},
  async stopStreamingTranscription() {},
}

export function useHearingStore() {
  return hearingStore
}

export function useHearingSpeechInputPipeline() {
  return hearingPipelineStore
}
