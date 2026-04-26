import { describe, expect, it } from 'vitest'

import { normalizeMicrophoneError } from './audio-device'

describe('normalizeMicrophoneError', () => {
  it('maps stream timeout without any detected devices to a missing-device message', () => {
    expect(normalizeMicrophoneError('Timed out waiting for audio input stream.', {
      hasAudioInputs: false,
    })).toBe('没有检测到可用麦克风，请检查耳机或系统输入设备。')
  })

  it('maps stream timeout with detected devices to a connection-timeout message', () => {
    expect(normalizeMicrophoneError('Timed out waiting for audio input stream.', {
      hasAudioInputs: true,
    })).toBe('麦克风接入超时，请检查浏览器输入设备和系统录音权限。')
  })

  it('maps permission errors to a browser-permission message', () => {
    expect(normalizeMicrophoneError('NotAllowedError: Permission denied', {
      hasAudioInputs: true,
    })).toBe('浏览器没有获得麦克风权限，请在地址栏权限设置里允许访问。')
  })

  it('preserves already normalized Chinese messages', () => {
    expect(normalizeMicrophoneError('麦克风需要 localhost、127.0.0.1 或 HTTPS。', {
      hasAudioInputs: true,
    })).toBe('麦克风需要 localhost、127.0.0.1 或 HTTPS。')
  })
})
