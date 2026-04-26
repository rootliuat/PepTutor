import { ref } from 'vue'

const settingsStore = {
  stageModelRenderer: ref('mock-renderer'),
  stageModelSelected: ref('mock-model'),
  stageModelSelectedUrl: ref('/mock-model.vrm'),
  themeColorsHueDynamic: ref(false),
  async updateStageModel() {},
}

const audioDeviceStore = {
  enabled: ref(false),
  selectedAudioInput: ref('mock-mic'),
  stream: ref<MediaStream | null>(null),
  audioInputs: ref([
    {
      label: 'Mock Mic',
      deviceId: 'mock-mic',
    },
  ]),
  permissionState: ref<'unknown' | 'requesting' | 'granted' | 'denied' | 'unavailable'>('unknown'),
  permissionError: ref(''),
  async askPermission() {},
  async ensureInputReady() {
    audioDeviceStore.permissionError.value = ''
    audioDeviceStore.permissionState.value = 'requesting'
    await audioDeviceStore.askPermission()
    audioDeviceStore.enabled.value = true
    audioDeviceStore.startStream()
    audioDeviceStore.permissionState.value = 'granted'
    return audioDeviceStore.stream.value
  },
  startStream() {
    audioDeviceStore.stream.value = { id: 'mock-stream' } as MediaStream
  },
  stopStream() {
    audioDeviceStore.enabled.value = false
    audioDeviceStore.stream.value = null
  },
}

export function useSettings() {
  return settingsStore
}

export function useSettingsAudioDevice() {
  return audioDeviceStore
}
