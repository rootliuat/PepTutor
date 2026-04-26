import { afterEach, describe, expect, it, vi } from 'vitest'

import { createPepTutorEdgeSpeechProvider } from './audio-speech'

describe('peptutor edge speech provider', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts Xiaoxiao TTS requests to the PepTutor backend proxy with lesson audit headers', async () => {
    const fetchSpy = vi.fn(async () => new Response(new ArrayBuffer(0), {
      status: 200,
      headers: {
        'Content-Type': 'audio/mpeg',
      },
    }))
    vi.stubGlobal('fetch', fetchSpy)
    vi.stubGlobal('location', new URL('https://lesson.example.test/lesson?page_uid=TB-G5S1U3-P24'))

    const provider = createPepTutorEdgeSpeechProvider({
      proxyUrl: 'https://lesson.example.test/api/peptutor/edge-tts',
      proxyAuth: {
        accessToken: 'lesson-jwt',
      },
    })

    const request = provider.speech('edge-tts')
    await request.fetch!(new URL('https://ignored.example.test'), {
      body: JSON.stringify({
        input: 'Hello',
        voice: 'zh-CN-XiaoxiaoNeural',
      }),
    })

    expect(fetchSpy).toHaveBeenCalledWith('https://lesson.example.test/api/peptutor/edge-tts', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer lesson-jwt',
        'X-PepTutor-Source-Path': '/lesson',
        'X-PepTutor-Source-Page-Uid': 'TB-G5S1U3-P24',
        'X-PepTutor-Source-Tag': 'lesson-runtime',
      },
      body: JSON.stringify({
        input: 'Hello',
        voice: 'zh-CN-XiaoxiaoNeural',
        model: 'edge-tts',
        rate: '+0%',
        volume: '+0%',
        pitch: '+0Hz',
      }),
    })
  })
})
