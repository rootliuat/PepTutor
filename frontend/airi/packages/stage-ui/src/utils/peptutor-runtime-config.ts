export const pepTutorRuntimeConfigKeys = [
  'VITE_PEPTUTOR_LESSON_API_URL',
  'VITE_PEPTUTOR_LESSON_API_KEY',
  'VITE_PEPTUTOR_LESSON_BEARER_TOKEN',
  'VITE_PEPTUTOR_LESSON_ACCESS_TOKEN',
  'VITE_PEPTUTOR_LESSON_AUTH_USERNAME',
  'VITE_PEPTUTOR_LESSON_AUTH_PASSWORD',
  'VITE_PEPTUTOR_TTS_PROVIDER',
  'VITE_PEPTUTOR_TTS_MODEL',
  'VITE_PEPTUTOR_TTS_VOICE',
  'VITE_PEPTUTOR_TTS_CLUSTER',
  'VITE_PEPTUTOR_TTS_PROXY_URL',
  'VITE_PEPTUTOR_ASR_PROVIDER',
  'VITE_PEPTUTOR_ASR_MODEL',
  'VITE_PEPTUTOR_ASR_PROXY_URL',
  'VITE_PEPTUTOR_ASR_RESOURCE_ID',
  'VITE_PEPTUTOR_ASR_APP_KEY',
  'VITE_PEPTUTOR_ENABLE_KOKORO_FALLBACK',
] as const

export type PepTutorRuntimeConfigKey = typeof pepTutorRuntimeConfigKeys[number]
export type PepTutorRuntimeConfig = Partial<Record<PepTutorRuntimeConfigKey, string>>

declare global {
  // eslint-disable-next-line vars-on-top
  var __PEPTUTOR_RUNTIME_CONFIG__: PepTutorRuntimeConfig | undefined
}

function normalizeString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

export function readPepTutorRuntimeConfig(): PepTutorRuntimeConfig {
  const runtimeConfig = globalThis.__PEPTUTOR_RUNTIME_CONFIG__
  if (!runtimeConfig || typeof runtimeConfig !== 'object') {
    return {}
  }

  const resolvedConfig: PepTutorRuntimeConfig = {}
  for (const key of pepTutorRuntimeConfigKeys) {
    const value = normalizeString(runtimeConfig[key])
    if (value) {
      resolvedConfig[key] = value
    }
  }

  return resolvedConfig
}

export function resolvePepTutorRuntimeEnv(
  env: ImportMetaEnv = import.meta.env,
): ImportMetaEnv {
  const runtimeConfig = readPepTutorRuntimeConfig()
  if (Object.keys(runtimeConfig).length === 0) {
    return env
  }

  return {
    ...env,
    ...runtimeConfig,
  } as ImportMetaEnv
}
