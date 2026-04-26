# Speech Proxy Deployment

## Scope

This document covers the backend-native PepTutor speech proxy routes served by `backend/LightRAG`:

- `POST /api/peptutor/edge-tts`
- `POST /api/peptutor/doubao-tts`
- `WS /api/peptutor/doubao-realtime-asr`

The deployment target is the existing `LightRAG` FastAPI service. `stage-web` local speech proxies remain development fallbacks and protocol references, not the production target.

## Runtime Assumptions

- frontend `/lesson` traffic and speech proxy traffic should use the same backend origin
- the browser should call `LightRAG` directly for lesson API, TTS, and ASR
- websocket proxying must be enabled in the reverse proxy in front of `LightRAG`
- the current deployment assumption is same-origin for HTTP and websocket traffic

## Environment Variables

Recommended server-side variables:

```env
# Required only when using the paid Doubao TTS route again.
PEPTUTOR_DOUBAO_TTS_APP_ID=...
PEPTUTOR_DOUBAO_TTS_API_KEY=...
PEPTUTOR_DOUBAO_TTS_CLUSTER=volcano_tts

PEPTUTOR_DOUBAO_ASR_APP_ID=...
PEPTUTOR_DOUBAO_ASR_API_KEY=...
PEPTUTOR_DOUBAO_ASR_MODEL=1.2.1.1
PEPTUTOR_DOUBAO_ASR_RESOURCE_ID=volc.speech.dialog
PEPTUTOR_DOUBAO_ASR_APP_KEY=PlgvMymc7f3tQnJ6

PEPTUTOR_LESSON_RATE_LIMIT_REQUESTS=60
PEPTUTOR_LESSON_RATE_LIMIT_WINDOW_SECONDS=60
PEPTUTOR_SPEECH_TTS_RATE_LIMIT_REQUESTS=20
PEPTUTOR_SPEECH_TTS_RATE_LIMIT_WINDOW_SECONDS=60
PEPTUTOR_SPEECH_ASR_CONNECT_RATE_LIMIT_REQUESTS=6
PEPTUTOR_SPEECH_ASR_CONNECT_RATE_LIMIT_WINDOW_SECONDS=60
```

Current fallback order inside `LightRAG` is:

1. process environment
2. `backend/LightRAG/.env`
3. repo root `.env`

For production deployment, prefer explicit process environment or a service-local `backend/LightRAG/.env`. Do not rely on frontend `VITE_*` names as the long-term production contract.

## Authentication

Current backend-native speech routes reuse the existing `LightRAG` API authentication layer:

- if neither JWT auth nor API-key auth is configured, the speech routes remain open for local development
- if `LIGHTRAG_API_KEY` is configured, both speech routes require that same API key
- if `AUTH_ACCOUNTS` JWT auth is configured, both speech routes require a non-guest bearer token from the same `/login` flow used elsewhere in `LightRAG`
- these speech routes use strict auth and do not treat the broader `/api/*` whitelist pattern as a bypass

Credential transport details:

- `POST /api/peptutor/edge-tts` and `POST /api/peptutor/doubao-tts` accept the normal `X-API-Key` header or `Authorization: Bearer ...`
- `WS /api/peptutor/doubao-realtime-asr` accepts the same headers for non-browser clients
- for browser websocket clients that cannot attach custom headers, the current route also accepts `?api_key=...` or `?access_token=...` on the websocket URL

Current frontend lesson mode can bootstrap the same credentials with env:

- `VITE_PEPTUTOR_LESSON_API_KEY=...` for API-key protected deployments
- `VITE_PEPTUTOR_LESSON_BEARER_TOKEN=...` or `VITE_PEPTUTOR_LESSON_ACCESS_TOKEN=...` for JWT-protected deployments
- `VITE_PEPTUTOR_LESSON_AUTH_USERNAME=...` plus `VITE_PEPTUTOR_LESSON_AUTH_PASSWORD=...` to let the browser fetch `/auth-status`, call `/login`, and cache the returned JWT automatically
- if both are set, the frontend currently prefers bearer-token transport

If you turn on auth for `LightRAG`, treat the speech routes and `/lesson` as one protected surface and keep the frontend on that same credential contract.

## Rate Limiting

Current backend-native lesson and speech routes also reuse one process-local fixed-window limiter:

- `/lesson/catalog` and `/lesson/turn` share the `PEPTUTOR_LESSON_RATE_LIMIT_*` limit
- `POST /api/peptutor/edge-tts` and `POST /api/peptutor/doubao-tts` use the `PEPTUTOR_SPEECH_TTS_RATE_LIMIT_*` limit
- websocket connection attempts for `WS /api/peptutor/doubao-realtime-asr` use the `PEPTUTOR_SPEECH_ASR_CONNECT_RATE_LIMIT_*` limit
- setting any request-count or window value to `0` or lower disables that limiter

Current scope and tradeoff:

- the limiter keys by authenticated identity when available, otherwise by API-key fingerprint or client IP
- it is process-local; multiple `gunicorn` workers or multiple hosts do not share counters
- it is intended as the first hardening layer for the PepTutor mainline, not the final distributed quota system

## Frontend Routing

When the frontend sets:

```env
VITE_PEPTUTOR_LESSON_API_URL=https://your-lightrag-host
VITE_PEPTUTOR_TTS_PROVIDER=peptutor-edge-tts
VITE_PEPTUTOR_TTS_VOICE=zh-CN-XiaoxiaoNeural
VITE_PEPTUTOR_ASR_PROVIDER=volcengine-realtime-transcription
# optional for protected deployments:
# VITE_PEPTUTOR_LESSON_API_KEY=...
# VITE_PEPTUTOR_LESSON_BEARER_TOKEN=...
# VITE_PEPTUTOR_LESSON_AUTH_USERNAME=...
# VITE_PEPTUTOR_LESSON_AUTH_PASSWORD=...
```

and does not set explicit `VITE_PEPTUTOR_TTS_PROXY_URL` or `VITE_PEPTUTOR_ASR_PROXY_URL`, the current bootstrap logic derives:

- `https://your-lightrag-host/api/peptutor/edge-tts`
- `wss://your-lightrag-host/api/peptutor/doubao-realtime-asr`

from the lesson backend base automatically.

## Nginx Reverse Proxy

Use websocket upgrade passthrough for `/api/peptutor/doubao-realtime-asr` and ordinary HTTP proxying for `/api/peptutor/edge-tts` and `/api/peptutor/doubao-tts`.

Example:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl http2;
    server_name peptutor.example.com;

    location / {
        proxy_pass http://127.0.0.1:9625;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    location /api/peptutor/doubao-realtime-asr {
        proxy_pass http://127.0.0.1:9625/api/peptutor/doubao-realtime-asr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_buffering off;
    }
}
```

## Idle Timeout Recommendations

Recommended starting values:

- lesson/TTS HTTP routes: `120s`
- Doubao realtime ASR websocket: `300s`

Reasoning:

- TTS is short-lived synchronous HTTP
- lesson ASR is push-to-talk but still benefits from a more forgiving websocket idle window
- `300s` is conservative enough for interactive testing without being unbounded

If upstream infrastructure has stricter defaults, keep the websocket timeout comfortably above your expected lesson turn duration.

## CORS and Origin Assumption

Current backend speech routes do not add a separate websocket-origin policy layer, and frontend defaults now assume the speech proxy lives on the same backend origin as `/lesson`.

Current deployment recommendation:

- keep `/lesson`, `/api/peptutor/edge-tts`, `/api/peptutor/doubao-tts`, and `/api/peptutor/doubao-realtime-asr` on the same public origin
- avoid cross-origin websocket deployment unless you are also prepared to own explicit browser origin policy and proxy behavior

## Local Smoke

The checked-in backend-native smoke command is:

```bash
backend/LightRAG/.venv/bin/python scripts/smoke_speech.py
```

Optional overrides:

```env
PEPTUTOR_SPEECH_SMOKE_BASE_URL=http://127.0.0.1:9625
PEPTUTOR_SPEECH_SMOKE_TTS_PATH=/api/peptutor/edge-tts
PEPTUTOR_SPEECH_SMOKE_TTS_TEXT=PepTutor speech smoke test.
PEPTUTOR_SPEECH_SMOKE_TTS_VOICE=zh-CN-XiaoxiaoNeural
PEPTUTOR_SPEECH_SMOKE_TIMEOUT_SECONDS=30
PEPTUTOR_SPEECH_SMOKE_AUDIO_FILE=/absolute/path/to/audio.raw
PEPTUTOR_SPEECH_SMOKE_ASR_SECONDS=1.0
PEPTUTOR_SPEECH_SMOKE_ASR_CHUNK_MS=200
```

If `PEPTUTOR_SPEECH_SMOKE_AUDIO_FILE` is unset, the script sends generated `16k / mono / s16le` silence to the ASR route. That is intentional: the smoke is for service reachability and protocol correctness, not ASR accuracy benchmarking.

The acceptance bar for this slice is that the script prints explicit `PASS` lines for both TTS and ASR against an already running `LightRAG` instance.

## Operational Logging

Current backend-native speech routes emit request-scoped logs:

- TTS:
  - `Speech proxy TTS start ...`
  - `Speech proxy TTS success ...`
  - `Speech proxy TTS error ...`
- ASR:
  - `Speech proxy ASR connected ...`
  - `Speech proxy ASR start ...`
  - `Speech proxy ASR ready ...`
  - `Speech proxy ASR closed ...`
  - `Speech proxy ASR error ...`

These lines include a proxy request id plus latency-oriented fields such as `duration_ms`, `ready_ms`, and `audio_bytes`. The smoke script is expected to correlate with those logs during local deployment validation.
