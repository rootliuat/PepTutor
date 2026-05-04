import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useHearingStore } from './modules/hearing'
import { useSpeechStore } from './modules/speech'
import { bootstrapPepTutorVoiceEnvDefaults, resolvePepTutorVoiceEnvBootstrapPlan } from './provider-env-bootstrap'
import { useProvidersStore } from './providers'

vi.mock('@xsai/model', () => ({
  listModels: vi.fn(async () => []),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
  }),
}))

describe('provider env bootstrap', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('resolves mixed env names into a bootstrap plan', () => {
    const plan = resolvePepTutorVoiceEnvBootstrapPlan({
      VITE_PEPTUTOR_TTS_API_KEY: 'sk-tts',
      VITE_PEPTUTOR_TTS_BASE_URL: 'https://tts.example.test/v1',
      VITE_PEPTUTOR_TTS_MODEL: 'tts-model',
      VITE_PEPTUTOR_TTS_VOICE: 'alloy',
      ALIYUN_AK_ID: 'aliyun-ak',
      ALIYUN_AK_SECRET: 'aliyun-secret',
      ALIYUN_NLS_APP_KEY: 'aliyun-app',
    } as unknown as ImportMetaEnv)

    expect(plan.speech).toMatchObject({
      providerId: 'openai-compatible-audio-speech',
      config: {
        apiKey: 'sk-tts',
        baseUrl: 'https://tts.example.test/v1/',
        model: 'tts-model',
        voice: 'alloy',
      },
      model: 'tts-model',
      voiceId: 'alloy',
    })

    expect(plan.transcription).toMatchObject({
      providerId: 'aliyun-nls-transcription',
      config: {
        accessKeyId: 'aliyun-ak',
        accessKeySecret: 'aliyun-secret',
        appKey: 'aliyun-app',
        region: 'cn-shanghai',
      },
      model: 'aliyun-nls-v1',
    })
  })

  it('resolves backend-native speech proxy mode from runtime config without frontend secrets', () => {
    vi.stubGlobal('__PEPTUTOR_RUNTIME_CONFIG__', {
      VITE_PEPTUTOR_LESSON_API_URL: '/peptutor-api',
      VITE_PEPTUTOR_TTS_PROVIDER: 'volcengine',
      VITE_PEPTUTOR_TTS_MODEL: 'v1',
      VITE_PEPTUTOR_TTS_VOICE: 'zh_female_vv_uranus_bigtts',
      VITE_PEPTUTOR_ASR_PROVIDER: 'volcengine-realtime-transcription',
      VITE_PEPTUTOR_ASR_MODEL: '1.2.1.1',
    })

    const plan = resolvePepTutorVoiceEnvBootstrapPlan({} as ImportMetaEnv)

    expect(plan.speech).toMatchObject({
      providerId: 'volcengine',
      config: {
        proxyUrl: '/peptutor-api/api/peptutor/doubao-tts',
        model: 'v1',
        app: {
          cluster: 'volcano_tts',
        },
      },
      model: 'v1',
      voiceId: 'zh_female_vv_uranus_bigtts',
    })
    expect(plan.speech?.config).not.toHaveProperty('apiKey')
    expect(plan.speech?.config.app).not.toHaveProperty('appId')

    expect(plan.transcription).toMatchObject({
      providerId: 'volcengine-realtime-transcription',
      config: {
        proxyUrl: '/peptutor-api/api/peptutor/doubao-realtime-asr',
        model: '1.2.1.1',
        resourceId: 'volc.speech.dialog',
        appKey: 'PlgvMymc7f3tQnJ6',
      },
      model: '1.2.1.1',
    })
    expect(plan.transcription?.config).not.toHaveProperty('apiKey')
    expect(plan.transcription?.config.app).not.toHaveProperty('appId')
  })

  it('bootstraps backend-native speech proxy mode from runtime config without frontend secrets', async () => {
    vi.stubGlobal('__PEPTUTOR_RUNTIME_CONFIG__', {
      VITE_PEPTUTOR_LESSON_API_URL: '/peptutor-api',
      VITE_PEPTUTOR_TTS_PROVIDER: 'volcengine',
      VITE_PEPTUTOR_TTS_VOICE: 'zh_female_vv_uranus_bigtts',
      VITE_PEPTUTOR_ASR_PROVIDER: 'volcengine-realtime-transcription',
    })

    await bootstrapPepTutorVoiceEnvDefaults()

    const providersStore = useProvidersStore()
    const speechStore = useSpeechStore()
    const hearingStore = useHearingStore()

    expect(providersStore.getProviderConfig('volcengine')).toMatchObject({
      proxyUrl: '/peptutor-api/api/peptutor/doubao-tts',
      app: {
        cluster: 'volcano_tts',
      },
    })
    expect(providersStore.getProviderConfig('volcengine')).not.toHaveProperty('apiKey')
    expect((providersStore.getProviderConfig('volcengine').app as Record<string, unknown>) || {}).not.toHaveProperty('appId')

    expect(providersStore.getProviderConfig('volcengine-realtime-transcription')).toMatchObject({
      proxyUrl: '/peptutor-api/api/peptutor/doubao-realtime-asr',
      model: '1.2.1.1',
      resourceId: 'volc.speech.dialog',
      appKey: 'PlgvMymc7f3tQnJ6',
    })
    expect(providersStore.getProviderConfig('volcengine-realtime-transcription')).not.toHaveProperty('apiKey')

    expect(speechStore.activeSpeechProvider).toBe('volcengine')
    expect(speechStore.activeSpeechVoiceId).toBe('zh_female_vv_uranus_bigtts')
    expect(hearingStore.activeTranscriptionProvider).toBe('volcengine-realtime-transcription')
  })

  it('resolves Edge Xiaoxiao TTS proxy mode from runtime config', () => {
    vi.stubGlobal('__PEPTUTOR_RUNTIME_CONFIG__', {
      VITE_PEPTUTOR_LESSON_API_URL: '/peptutor-api',
      VITE_PEPTUTOR_TTS_PROVIDER: 'peptutor-edge-tts',
      VITE_PEPTUTOR_TTS_MODEL: 'edge-tts',
      VITE_PEPTUTOR_TTS_VOICE: 'zh-CN-XiaoxiaoNeural',
    })

    const plan = resolvePepTutorVoiceEnvBootstrapPlan({} as ImportMetaEnv)

    expect(plan.speech).toMatchObject({
      providerId: 'peptutor-edge-tts',
      config: {
        proxyUrl: '/peptutor-api/api/peptutor/edge-tts',
        model: 'edge-tts',
      },
      model: 'edge-tts',
      voiceId: 'zh-CN-XiaoxiaoNeural',
      forceSelection: true,
    })
  })

  it('ignores a Doubao proxy URL when Edge Xiaoxiao TTS is selected', () => {
    const plan = resolvePepTutorVoiceEnvBootstrapPlan({
      VITE_PEPTUTOR_LESSON_API_URL: '/peptutor-api',
      VITE_PEPTUTOR_TTS_PROVIDER: 'edge-tts',
      VITE_PEPTUTOR_TTS_PROXY_URL: '/api/peptutor/doubao-tts',
    } as unknown as ImportMetaEnv)

    expect(plan.speech).toMatchObject({
      providerId: 'peptutor-edge-tts',
      config: {
        proxyUrl: '/peptutor-api/api/peptutor/edge-tts',
        model: 'edge-tts',
      },
      voiceId: 'zh-CN-XiaoxiaoNeural',
    })
  })

  it('defaults lesson speech to Edge Xiaoxiao TTS when a lesson API is configured', () => {
    vi.stubGlobal('__PEPTUTOR_RUNTIME_CONFIG__', {
      VITE_PEPTUTOR_LESSON_API_URL: 'http://127.0.0.1:9625',
    })

    const plan = resolvePepTutorVoiceEnvBootstrapPlan({} as ImportMetaEnv)

    expect(plan.speech).toMatchObject({
      providerId: 'peptutor-edge-tts',
      config: {
        proxyUrl: 'http://127.0.0.1:9625/api/peptutor/edge-tts',
        model: 'edge-tts',
      },
      model: 'edge-tts',
      voiceId: 'zh-CN-XiaoxiaoNeural',
    })
    expect(plan.speech?.forceSelection).toBe(true)
  })

  it('uses the dev proxy lesson API for default Edge speech on the lesson route', () => {
    vi.stubGlobal('location', {
      pathname: '/lesson',
    })

    const plan = resolvePepTutorVoiceEnvBootstrapPlan({} as ImportMetaEnv)

    expect(plan.speech).toMatchObject({
      providerId: 'peptutor-edge-tts',
      config: {
        proxyUrl: '/peptutor-api/api/peptutor/edge-tts',
        model: 'edge-tts',
      },
      model: 'edge-tts',
      voiceId: 'zh-CN-XiaoxiaoNeural',
      forceSelection: true,
    })
  })

  it('prefers explicit OpenAI-compatible TTS env over the lesson Edge default', () => {
    const plan = resolvePepTutorVoiceEnvBootstrapPlan({
      VITE_PEPTUTOR_LESSON_API_URL: 'http://127.0.0.1:9625',
      VITE_PEPTUTOR_TTS_API_KEY: 'sk-tts',
      VITE_PEPTUTOR_TTS_BASE_URL: 'https://tts.example.test/v1',
      VITE_PEPTUTOR_TTS_MODEL: 'tts-model',
      VITE_PEPTUTOR_TTS_VOICE: 'nova',
    } as unknown as ImportMetaEnv)

    expect(plan.speech).toMatchObject({
      providerId: 'openai-compatible-audio-speech',
      config: {
        apiKey: 'sk-tts',
        baseUrl: 'https://tts.example.test/v1/',
        model: 'tts-model',
        voice: 'nova',
      },
      model: 'tts-model',
      voiceId: 'nova',
    })
  })

  it('bootstraps explicit Edge Xiaoxiao TTS over a persisted Doubao selection', async () => {
    vi.stubGlobal('__PEPTUTOR_RUNTIME_CONFIG__', {
      VITE_PEPTUTOR_LESSON_API_URL: '/peptutor-api',
      VITE_PEPTUTOR_TTS_PROVIDER: 'edge-tts',
    })

    const speechStore = useSpeechStore()
    speechStore.activeSpeechProvider = 'volcengine'
    speechStore.activeSpeechModel = 'v1'
    speechStore.activeSpeechVoiceId = 'zh_female_vv_uranus_bigtts'

    await bootstrapPepTutorVoiceEnvDefaults()

    const providersStore = useProvidersStore()

    expect(providersStore.getProviderConfig('peptutor-edge-tts')).toMatchObject({
      proxyUrl: '/peptutor-api/api/peptutor/edge-tts',
      model: 'edge-tts',
    })
    expect(speechStore.activeSpeechProvider).toBe('peptutor-edge-tts')
    expect(speechStore.activeSpeechModel).toBe('edge-tts')
    expect(speechStore.activeSpeechVoiceId).toBe('zh-CN-XiaoxiaoNeural')
  })

  it('repairs a stale Edge provider proxy URL that points at Doubao TTS', async () => {
    vi.stubGlobal('__PEPTUTOR_RUNTIME_CONFIG__', {
      VITE_PEPTUTOR_LESSON_API_URL: '/peptutor-api',
      VITE_PEPTUTOR_TTS_PROVIDER: 'edge-tts',
    })

    const providersStore = useProvidersStore()
    const speechStore = useSpeechStore()
    Object.assign(providersStore.getProviderConfig('peptutor-edge-tts')!, {
      proxyUrl: '/api/peptutor/doubao-tts',
      model: 'v1',
    })
    speechStore.activeSpeechProvider = 'peptutor-edge-tts'
    speechStore.activeSpeechModel = 'v1'
    speechStore.activeSpeechVoiceId = 'zh_female_vv_uranus_bigtts'

    await bootstrapPepTutorVoiceEnvDefaults()

    expect(providersStore.getProviderConfig('peptutor-edge-tts')).toMatchObject({
      proxyUrl: '/peptutor-api/api/peptutor/edge-tts',
      model: 'edge-tts',
    })
    expect(speechStore.activeSpeechProvider).toBe('peptutor-edge-tts')
    expect(speechStore.activeSpeechModel).toBe('edge-tts')
    expect(speechStore.activeSpeechVoiceId).toBe('zh-CN-XiaoxiaoNeural')
  })

  it('keeps lesson Doubao TTS on volcengine while preserving Doubao ASR', () => {
    const plan = resolvePepTutorVoiceEnvBootstrapPlan({
      VITE_PEPTUTOR_LESSON_API_URL: 'http://127.0.0.1:9625',
      VITE_DOUBAO_TTS_API_KEY: 'doubao-tts-token',
      VITE_DOUBAO_TTS_APP_ID: 'doubao-tts-app-id',
      VITE_DOUBAO_ASR_API_KEY: 'doubao-asr-token',
      VITE_DOUBAO_ASR_APP_ID: 'doubao-asr-app-id',
    } as unknown as ImportMetaEnv)

    expect(plan.speech).toMatchObject({
      providerId: 'volcengine',
      config: {
        apiKey: 'doubao-tts-token',
        proxyUrl: 'http://127.0.0.1:9625/api/peptutor/doubao-tts',
        model: 'v1',
        app: {
          appId: 'doubao-tts-app-id',
          cluster: 'volcano_tts',
        },
      },
      model: 'v1',
    })

    expect(plan.transcription).toMatchObject({
      providerId: 'volcengine-realtime-transcription',
      config: {
        apiKey: 'doubao-asr-token',
        proxyUrl: 'http://127.0.0.1:9625/api/peptutor/doubao-realtime-asr',
        app: {
          appId: 'doubao-asr-app-id',
        },
      },
    })
  })

  it('resolves doubao-named env keys into the volcengine bootstrap plan', () => {
    const plan = resolvePepTutorVoiceEnvBootstrapPlan({
      VITE_DOUBAO_TTS_API_KEY: 'doubao-token',
      VITE_DOUBAO_TTS_APP_ID: 'doubao-app-id',
      VITE_PEPTUTOR_TTS_VOICE: 'zh_female_vv_uranus_bigtts',
    } as unknown as ImportMetaEnv)

    expect(plan.speech).toMatchObject({
      providerId: 'volcengine',
      config: {
        apiKey: 'doubao-token',
        proxyUrl: '/api/peptutor/doubao-tts',
        model: 'v1',
        app: {
          appId: 'doubao-app-id',
          cluster: 'volcano_tts',
        },
      },
      model: 'v1',
      voiceId: 'zh_female_vv_uranus_bigtts',
    })

    expect(plan.transcription).toMatchObject({
      providerId: 'volcengine-realtime-transcription',
      config: {
        apiKey: 'doubao-token',
        proxyUrl: '/api/peptutor/doubao-realtime-asr',
        model: '1.2.1.1',
        resourceId: 'volc.speech.dialog',
        appKey: 'PlgvMymc7f3tQnJ6',
        app: {
          appId: 'doubao-app-id',
        },
      },
      model: '1.2.1.1',
    })
  })

  it('derives backend-native Doubao proxy URLs from the lesson API base when Doubao TTS is explicitly selected', () => {
    const plan = resolvePepTutorVoiceEnvBootstrapPlan({
      VITE_PEPTUTOR_LESSON_API_URL: 'http://127.0.0.1:9625',
      VITE_PEPTUTOR_TTS_PROVIDER: 'volcengine',
      VITE_DOUBAO_TTS_API_KEY: 'doubao-token',
      VITE_DOUBAO_TTS_APP_ID: 'doubao-app-id',
      VITE_PEPTUTOR_TTS_VOICE: 'zh_female_vv_uranus_bigtts',
    } as unknown as ImportMetaEnv)

    expect(plan.speech).toMatchObject({
      providerId: 'volcengine',
      config: {
        proxyUrl: 'http://127.0.0.1:9625/api/peptutor/doubao-tts',
      },
    })

    expect(plan.transcription).toMatchObject({
      providerId: 'volcengine-realtime-transcription',
      config: {
        proxyUrl: 'http://127.0.0.1:9625/api/peptutor/doubao-realtime-asr',
      },
    })
  })

  it('attaches lesson backend auth to Doubao proxy config when the lesson backend is protected', () => {
    const plan = resolvePepTutorVoiceEnvBootstrapPlan({
      VITE_PEPTUTOR_LESSON_API_URL: 'https://lesson.example.test',
      VITE_PEPTUTOR_LESSON_API_KEY: 'lesson-api-key',
      VITE_PEPTUTOR_LESSON_BEARER_TOKEN: 'lesson-jwt',
      VITE_PEPTUTOR_TTS_PROVIDER: 'volcengine',
      VITE_DOUBAO_TTS_API_KEY: 'doubao-token',
      VITE_DOUBAO_TTS_APP_ID: 'doubao-app-id',
    } as unknown as ImportMetaEnv)

    expect(plan.speech).toMatchObject({
      providerId: 'volcengine',
      config: {
        proxyUrl: 'https://lesson.example.test/api/peptutor/doubao-tts',
        proxyAuth: {
          apiKey: 'lesson-api-key',
          accessToken: 'lesson-jwt',
        },
      },
    })

    expect(plan.transcription).toMatchObject({
      providerId: 'volcengine-realtime-transcription',
      config: {
        proxyUrl: 'https://lesson.example.test/api/peptutor/doubao-realtime-asr',
        proxyAuth: {
          apiKey: 'lesson-api-key',
          accessToken: 'lesson-jwt',
        },
      },
    })
  })

  it('resolves volcengine TTS env into a bootstrap plan', () => {
    const plan = resolvePepTutorVoiceEnvBootstrapPlan({
      VITE_PEPTUTOR_LESSON_API_URL: 'http://127.0.0.1:9625',
      VITE_PEPTUTOR_TTS_PROVIDER: 'volcengine',
      VITE_PEPTUTOR_TTS_API_KEY: 'volc-token',
      VITE_PEPTUTOR_TTS_APP_ID: 'volc-app-id',
      VITE_PEPTUTOR_TTS_PROXY_URL: '/api/custom-doubao-tts',
      VITE_PEPTUTOR_TTS_MODEL: 'v1',
      VITE_PEPTUTOR_TTS_VOICE: 'Vivi 2.0',
      VITE_PEPTUTOR_TTS_CLUSTER: 'volcano_tts',
    } as unknown as ImportMetaEnv)

    expect(plan.speech).toMatchObject({
      providerId: 'volcengine',
      config: {
        apiKey: 'volc-token',
        proxyUrl: '/api/custom-doubao-tts',
        model: 'v1',
        app: {
          appId: 'volc-app-id',
          cluster: 'volcano_tts',
        },
      },
      model: 'v1',
      voiceId: 'Vivi 2.0',
    })
  })

  it('bootstraps OpenAI-compatible speech and transcription into local settings', async () => {
    vi.stubEnv('VITE_PEPTUTOR_TTS_API_KEY', 'sk-tts')
    vi.stubEnv('VITE_PEPTUTOR_TTS_BASE_URL', 'https://tts.example.test/v1')
    vi.stubEnv('VITE_PEPTUTOR_TTS_MODEL', 'gpt-4o-mini-tts')
    vi.stubEnv('VITE_PEPTUTOR_TTS_VOICE', 'nova')
    vi.stubEnv('VITE_PEPTUTOR_ASR_API_KEY', 'sk-asr')
    vi.stubEnv('VITE_PEPTUTOR_ASR_BASE_URL', 'https://asr.example.test/v1')
    vi.stubEnv('VITE_PEPTUTOR_ASR_MODEL', 'gpt-4o-transcribe')

    await bootstrapPepTutorVoiceEnvDefaults()

    const providersStore = useProvidersStore()
    const speechStore = useSpeechStore()
    const hearingStore = useHearingStore()

    expect(providersStore.getProviderConfig('openai-compatible-audio-speech')).toMatchObject({
      apiKey: 'sk-tts',
      baseUrl: 'https://tts.example.test/v1/',
      model: 'gpt-4o-mini-tts',
      voice: 'nova',
    })
    expect(providersStore.getProviderConfig('openai-compatible-audio-transcription')).toMatchObject({
      apiKey: 'sk-asr',
      baseUrl: 'https://asr.example.test/v1/',
      model: 'gpt-4o-transcribe',
    })

    expect(speechStore.activeSpeechProvider).toBe('openai-compatible-audio-speech')
    expect(speechStore.activeSpeechModel).toBe('gpt-4o-mini-tts')
    expect(speechStore.activeSpeechVoiceId).toBe('nova')
    expect(hearingStore.activeTranscriptionProvider).toBe('openai-compatible-audio-transcription')
    expect(hearingStore.activeTranscriptionModel).toBe('gpt-4o-transcribe')
  })

  it('bootstraps volcengine speech into local settings', async () => {
    vi.stubEnv('VITE_PEPTUTOR_TTS_PROVIDER', 'volcengine')
    vi.stubEnv('VITE_PEPTUTOR_TTS_API_KEY', 'volc-token')
    vi.stubEnv('VITE_PEPTUTOR_TTS_APP_ID', 'volc-app-id')
    vi.stubEnv('VITE_PEPTUTOR_TTS_PROXY_URL', '/api/custom-doubao-tts')
    vi.stubEnv('VITE_PEPTUTOR_TTS_MODEL', 'v1')
    vi.stubEnv('VITE_PEPTUTOR_TTS_VOICE', 'Vivi 2.0')
    vi.stubEnv('VITE_PEPTUTOR_TTS_CLUSTER', 'volcano_tts')

    await bootstrapPepTutorVoiceEnvDefaults()

    const providersStore = useProvidersStore()
    const speechStore = useSpeechStore()

    expect(providersStore.getProviderConfig('volcengine')).toMatchObject({
      apiKey: 'volc-token',
      proxyUrl: '/api/custom-doubao-tts',
      model: 'v1',
      app: {
        appId: 'volc-app-id',
        cluster: 'volcano_tts',
      },
    })

    expect(speechStore.activeSpeechProvider).toBe('volcengine')
    expect(speechStore.activeSpeechModel).toBe('v1')
    expect(speechStore.activeSpeechVoiceId).toBe('Vivi 2.0')
  })

  it('bootstraps volcengine speech from doubao env names', async () => {
    vi.stubEnv('VITE_DOUBAO_TTS_API_KEY', 'doubao-token')
    vi.stubEnv('VITE_DOUBAO_TTS_APP_ID', 'doubao-app-id')
    vi.stubEnv('VITE_PEPTUTOR_TTS_VOICE', 'zh_female_vv_uranus_bigtts')

    await bootstrapPepTutorVoiceEnvDefaults()

    const providersStore = useProvidersStore()
    const speechStore = useSpeechStore()
    const hearingStore = useHearingStore()

    expect(providersStore.getProviderConfig('volcengine')).toMatchObject({
      apiKey: 'doubao-token',
      proxyUrl: '/api/peptutor/doubao-tts',
      model: 'v1',
      app: {
        appId: 'doubao-app-id',
        cluster: 'volcano_tts',
      },
    })

    expect(speechStore.activeSpeechProvider).toBe('volcengine')
    expect(speechStore.activeSpeechModel).toBe('v1')
    expect(speechStore.activeSpeechVoiceId).toBe('zh_female_vv_uranus_bigtts')

    expect(providersStore.getProviderConfig('volcengine-realtime-transcription')).toMatchObject({
      apiKey: 'doubao-token',
      proxyUrl: '/api/peptutor/doubao-realtime-asr',
      model: '1.2.1.1',
      resourceId: 'volc.speech.dialog',
      appKey: 'PlgvMymc7f3tQnJ6',
      app: {
        appId: 'doubao-app-id',
      },
    })
    expect(hearingStore.activeTranscriptionProvider).toBe('volcengine-realtime-transcription')
    expect(hearingStore.activeTranscriptionModel).toBe('1.2.1.1')
  })

  it('replaces the local Kokoro fallback when Doubao speech is configured', async () => {
    const speechStore = useSpeechStore()
    speechStore.activeSpeechProvider = 'kokoro-local'
    speechStore.activeSpeechModel = 'q4f16'

    vi.stubEnv('VITE_DOUBAO_TTS_API_KEY', 'doubao-token')
    vi.stubEnv('VITE_DOUBAO_TTS_APP_ID', 'doubao-app-id')
    vi.stubEnv('VITE_PEPTUTOR_TTS_VOICE', 'zh_female_vv_uranus_bigtts')

    await bootstrapPepTutorVoiceEnvDefaults()

    expect(speechStore.activeSpeechProvider).toBe('volcengine')
    expect(speechStore.activeSpeechModel).toBe('v1')
    expect(speechStore.activeSpeechVoiceId).toBe('zh_female_vv_uranus_bigtts')
  })

  it('selects the first local volcengine voice when no explicit voice is configured', async () => {
    vi.stubEnv('VITE_DOUBAO_TTS_API_KEY', 'doubao-token')
    vi.stubEnv('VITE_DOUBAO_TTS_APP_ID', 'doubao-app-id')

    await bootstrapPepTutorVoiceEnvDefaults()

    const providersStore = useProvidersStore()
    const speechStore = useSpeechStore()

    const voices = await providersStore.getProviderMetadata('volcengine').capabilities.listVoices?.(
      providersStore.getProviderConfig('volcengine'),
    )

    expect(voices?.map(voice => voice.id)).toEqual(['zh_female_vv_uranus_bigtts'])
    expect(speechStore.activeSpeechProvider).toBe('volcengine')
    expect(speechStore.activeSpeechVoiceId).toBe('zh_female_vv_uranus_bigtts')
  })

  it('prefers explicit Doubao ASR env over legacy ASR providers', () => {
    const plan = resolvePepTutorVoiceEnvBootstrapPlan({
      VITE_DOUBAO_TTS_API_KEY: 'doubao-token',
      VITE_DOUBAO_TTS_APP_ID: 'doubao-app-id',
      ALIYUN_AK_ID: 'aliyun-ak',
      ALIYUN_AK_SECRET: 'aliyun-secret',
      ALIYUN_NLS_APP_KEY: 'aliyun-app',
    } as unknown as ImportMetaEnv)

    expect(plan.transcription).toMatchObject({
      providerId: 'volcengine-realtime-transcription',
      config: {
        apiKey: 'doubao-token',
        app: {
          appId: 'doubao-app-id',
        },
      },
    })
  })

  it('keeps explicit Doubao ASR provider in proxy mode without borrowing TTS secrets into the browser config', () => {
    const plan = resolvePepTutorVoiceEnvBootstrapPlan({
      VITE_PEPTUTOR_ASR_PROVIDER: 'volcengine-realtime-transcription',
      VITE_PEPTUTOR_ASR_APP_ID: 'asr-app-id',
      VITE_DOUBAO_TTS_API_KEY: 'tts-token',
      VITE_DOUBAO_TTS_APP_ID: 'tts-app-id',
    } as unknown as ImportMetaEnv)

    expect(plan.transcription).toMatchObject({
      providerId: 'volcengine-realtime-transcription',
      config: {
        proxyUrl: '/api/peptutor/doubao-realtime-asr',
        app: {
          appId: 'asr-app-id',
        },
      },
    })
    expect(plan.transcription?.config).not.toHaveProperty('apiKey')
  })

  it('does not override existing provider settings or active selections', async () => {
    const providersStore = useProvidersStore()
    const speechStore = useSpeechStore()
    const hearingStore = useHearingStore()

    Object.assign(providersStore.getProviderConfig('openai-compatible-audio-speech')!, {
      apiKey: 'existing-tts-key',
      baseUrl: 'https://existing-tts.example.test/v1/',
      model: 'existing-tts-model',
      voice: 'existing-tts-voice',
    })
    Object.assign(providersStore.getProviderConfig('openai-compatible-audio-transcription')!, {
      apiKey: 'existing-asr-key',
      baseUrl: 'https://existing-asr.example.test/v1/',
      model: 'existing-asr-model',
    })

    speechStore.activeSpeechProvider = 'openai-compatible-audio-speech'
    speechStore.activeSpeechModel = 'existing-tts-model'
    speechStore.activeSpeechVoiceId = 'existing-tts-voice'
    hearingStore.activeTranscriptionProvider = 'openai-compatible-audio-transcription'
    hearingStore.activeTranscriptionModel = 'existing-asr-model'

    vi.stubEnv('VITE_PEPTUTOR_TTS_API_KEY', 'new-tts-key')
    vi.stubEnv('VITE_PEPTUTOR_TTS_BASE_URL', 'https://new-tts.example.test/v1')
    vi.stubEnv('VITE_PEPTUTOR_TTS_MODEL', 'new-tts-model')
    vi.stubEnv('VITE_PEPTUTOR_TTS_VOICE', 'new-tts-voice')
    vi.stubEnv('VITE_PEPTUTOR_ASR_API_KEY', 'new-asr-key')
    vi.stubEnv('VITE_PEPTUTOR_ASR_BASE_URL', 'https://new-asr.example.test/v1')
    vi.stubEnv('VITE_PEPTUTOR_ASR_MODEL', 'new-asr-model')

    await bootstrapPepTutorVoiceEnvDefaults()

    expect(providersStore.getProviderConfig('openai-compatible-audio-speech')).toMatchObject({
      apiKey: 'existing-tts-key',
      baseUrl: 'https://existing-tts.example.test/v1/',
      model: 'existing-tts-model',
      voice: 'existing-tts-voice',
    })
    expect(providersStore.getProviderConfig('openai-compatible-audio-transcription')).toMatchObject({
      apiKey: 'existing-asr-key',
      baseUrl: 'https://existing-asr.example.test/v1/',
      model: 'existing-asr-model',
    })

    expect(speechStore.activeSpeechProvider).toBe('openai-compatible-audio-speech')
    expect(speechStore.activeSpeechModel).toBe('existing-tts-model')
    expect(speechStore.activeSpeechVoiceId).toBe('existing-tts-voice')
    expect(hearingStore.activeTranscriptionProvider).toBe('openai-compatible-audio-transcription')
    expect(hearingStore.activeTranscriptionModel).toBe('existing-asr-model')
  })
})
