import { useLocalStorageManualReset } from '@proj-airi/stage-shared/composables'
import { defineStore } from 'pinia'
import { onMounted, ref, watch } from 'vue'

import { useAudioDevice } from '../audio'

export type AudioPermissionState = 'unknown' | 'requesting' | 'granted' | 'denied' | 'unavailable'

type MicrophoneErrorContext = {
  hasAudioInputs: boolean
}

export function normalizeMicrophoneError(error: unknown, context: MicrophoneErrorContext): string {
  const rawMessage = typeof error === 'string'
    ? error
    : error instanceof Error
      ? error.message
      : ''
  const normalizedMessage = rawMessage.trim()
  const lowerCaseMessage = normalizedMessage.toLowerCase()

  if (!normalizedMessage) {
    return context.hasAudioInputs
      ? '麦克风初始化失败，请检查浏览器和系统录音设置。'
      : '没有检测到可用麦克风，请检查耳机或系统输入设备。'
  }

  if (
    lowerCaseMessage.includes('timed out waiting for audio input stream')
    || lowerCaseMessage.includes('device timeout')
  ) {
    return context.hasAudioInputs
      ? '麦克风接入超时，请检查浏览器输入设备和系统录音权限。'
      : '没有检测到可用麦克风，请检查耳机或系统输入设备。'
  }

  if (
    lowerCaseMessage.includes('notfound')
    || lowerCaseMessage.includes('requested device not found')
    || lowerCaseMessage.includes('requested device not available')
    || lowerCaseMessage.includes('device not found')
  ) {
    return '没有检测到可用麦克风，请检查耳机或系统输入设备。'
  }

  if (
    lowerCaseMessage.includes('notallowed')
    || lowerCaseMessage.includes('permission denied')
    || lowerCaseMessage.includes('permission dismissed')
    || lowerCaseMessage.includes('permission blocked')
  ) {
    return '浏览器没有获得麦克风权限，请在地址栏权限设置里允许访问。'
  }

  if (
    lowerCaseMessage.includes('notreadable')
    || lowerCaseMessage.includes('could not start audio source')
    || lowerCaseMessage.includes('trackstarterror')
    || lowerCaseMessage.includes('aborterror')
  ) {
    return '浏览器无法打开麦克风，请关闭占用设备的应用后重试。'
  }

  if (
    lowerCaseMessage.includes('overconstrained')
    || lowerCaseMessage.includes('constraint')
  ) {
    return '当前选择的麦克风不可用，请重新选择输入设备。'
  }

  if (lowerCaseMessage.includes('secure') || lowerCaseMessage.includes('https') || lowerCaseMessage.includes('localhost')) {
    return '麦克风需要 localhost、127.0.0.1 或 HTTPS。'
  }

  if (lowerCaseMessage.includes('unavailable in this browser')) {
    return '当前浏览器不支持麦克风输入。'
  }

  return normalizedMessage
}

export const useSettingsAudioDevice = defineStore('settings-audio-devices', () => {
  const { audioInputs, deviceConstraints, selectedAudioInput: selectedAudioInputNonPersist, startStream, stopStream, stream, askPermission } = useAudioDevice()

  const selectedAudioInputPersist = useLocalStorageManualReset<string>('settings/audio/input', selectedAudioInputNonPersist.value)
  const selectedAudioInputEnabledPersist = useLocalStorageManualReset<boolean>('settings/audio/input/enabled', false)
  const permissionState = ref<AudioPermissionState>('unknown')
  const permissionError = ref('')

  watch(selectedAudioInputPersist, (newValue) => {
    selectedAudioInputNonPersist.value = newValue
  })

  watch(selectedAudioInputEnabledPersist, (val) => {
    if (val) {
      startStream()
    }
    else {
      stopStream()
    }
  })

  onMounted(() => {
    const hasSelectedInput = selectedAudioInputPersist.value
      && audioInputs.value.some(device => device.deviceId === selectedAudioInputPersist.value)

    if (selectedAudioInputEnabledPersist.value && hasSelectedInput) {
      startStream()
    }
    if (selectedAudioInputNonPersist.value && !selectedAudioInputEnabledPersist.value) {
      selectedAudioInputPersist.value = selectedAudioInputNonPersist.value
    }
  })

  function resetState() {
    selectedAudioInputPersist.reset()
    selectedAudioInputNonPersist.value = ''
    selectedAudioInputEnabledPersist.reset()
    permissionState.value = 'unknown'
    permissionError.value = ''
    stopStream()
  }

  async function waitForStream(timeoutMs = 4000) {
    const startedAt = Date.now()
    while (!stream.value && Date.now() - startedAt < timeoutMs) {
      await new Promise(resolve => setTimeout(resolve, 50))
    }

    return stream.value
  }

  async function ensureInputReady() {
    permissionError.value = ''

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      permissionState.value = 'unavailable'
      permissionError.value = '当前浏览器不支持麦克风输入。'
      throw new Error(permissionError.value)
    }

    if (typeof window !== 'undefined' && !window.isSecureContext) {
      permissionState.value = 'unavailable'
      permissionError.value = '麦克风需要 localhost、127.0.0.1 或 HTTPS。'
      throw new Error(permissionError.value)
    }

    permissionState.value = 'requesting'

    try {
      await askPermission()

      if (!selectedAudioInputPersist.value && audioInputs.value.length > 0) {
        selectedAudioInputPersist.value = audioInputs.value.find(input => input.deviceId === 'default')?.deviceId || audioInputs.value[0].deviceId
      }

      selectedAudioInputEnabledPersist.value = true
      startStream()

      const nextStream = await waitForStream()
      if (!nextStream) {
        throw new Error('Timed out waiting for audio input stream.')
      }

      permissionState.value = 'granted'
      return nextStream
    }
    catch (error) {
      permissionState.value = 'denied'
      permissionError.value = normalizeMicrophoneError(error, {
        hasAudioInputs: audioInputs.value.length > 0,
      })
      selectedAudioInputEnabledPersist.value = false
      stopStream()
      throw new Error(permissionError.value)
    }
  }

  return {
    audioInputs,
    deviceConstraints,
    selectedAudioInput: selectedAudioInputPersist,
    enabled: selectedAudioInputEnabledPersist,

    stream,

    askPermission,
    ensureInputReady,
    startStream,
    stopStream,
    permissionState,
    permissionError,
    resetState,
  }
})
