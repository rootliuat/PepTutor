import type { SpeechProviderWithExtraOptions } from '@xsai-ext/providers/utils'

import type { PepTutorBackendAuthConfig } from '../../../utils/peptutor-backend-auth'

import { resolvePepTutorBackendAuth } from '../../../utils/peptutor-backend-auth'
import { fetchPepTutorBackend } from '../../peptutor-backend-auth'

export const EDGE_TTS_DEFAULT_MODEL = 'edge-tts'
export const EDGE_TTS_DEFAULT_VOICE = 'zh-CN-XiaoxiaoNeural'
const DEFAULT_EDGE_TTS_PROXY_PATH = '/api/peptutor/edge-tts'

interface PepTutorEdgeSpeechExtraOptions {
  proxyUrl?: string
  proxyAuth?: PepTutorBackendAuthConfig
  rate?: string
  volume?: string
  pitch?: string
}

interface OpenAISpeechRequestLike {
  input?: string
  voice?: string
  model?: string
}

function resolveBaseOrigin(): string {
  if (typeof globalThis.location?.origin === 'string' && globalThis.location.origin) {
    return globalThis.location.origin
  }

  return 'http://localhost'
}

function resolveProxyUrl(proxyUrl: string | undefined) {
  const raw = proxyUrl?.trim() || DEFAULT_EDGE_TTS_PROXY_PATH
  return new URL(raw, resolveBaseOrigin()).toString()
}

function resolvePepTutorTtsAuditHeaders(): Record<string, string> {
  if (typeof globalThis.location?.href !== 'string' || !globalThis.location.href) {
    return {}
  }

  try {
    const currentUrl = new URL(globalThis.location.href)
    const sourcePath = currentUrl.pathname.trim()
    const sourcePageUid = currentUrl.searchParams.get('page_uid')?.trim() || ''

    return {
      ...(sourcePath ? { 'X-PepTutor-Source-Path': sourcePath } : {}),
      ...(sourcePageUid ? { 'X-PepTutor-Source-Page-Uid': sourcePageUid } : {}),
      'X-PepTutor-Source-Tag': sourcePath.startsWith('/lesson') ? 'lesson-runtime' : 'browser-runtime',
    }
  }
  catch {
    return {}
  }
}

export function createPepTutorEdgeSpeechProvider(
  config: Record<string, unknown>,
): SpeechProviderWithExtraOptions<string, PepTutorEdgeSpeechExtraOptions> {
  return {
    speech: (model, options) => ({
      baseURL: 'http://peptutor-edge-tts.local/v1/',
      model,
      fetch: async (_input: RequestInfo | URL, init?: RequestInit) => {
        if (!init?.body || typeof init.body !== 'string') {
          throw new Error('Invalid Edge TTS request body.')
        }

        const body = JSON.parse(init.body) as OpenAISpeechRequestLike
        const proxyUrl = resolveProxyUrl(
          (options?.proxyUrl || config.proxyUrl) as string | undefined,
        )
        const proxyAuth = (
          options?.proxyAuth
          || resolvePepTutorBackendAuth()
          || config.proxyAuth
        ) as PepTutorBackendAuthConfig | undefined
        const response = await fetchPepTutorBackend(proxyUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...resolvePepTutorTtsAuditHeaders(),
          },
          body: JSON.stringify({
            input: body.input,
            voice: body.voice || EDGE_TTS_DEFAULT_VOICE,
            model: body.model || model || EDGE_TTS_DEFAULT_MODEL,
            rate: options?.rate || (config.rate as string | undefined) || '+0%',
            volume: options?.volume || (config.volume as string | undefined) || '+0%',
            pitch: options?.pitch || (config.pitch as string | undefined) || '+0Hz',
          }),
        }, {
          auth: proxyAuth,
        })

        if (!response.ok) {
          const errorText = await response.text()
          throw new Error(errorText || `Edge TTS proxy failed with HTTP ${response.status}`)
        }

        return response
      },
    }),
  }
}
