# Lesson Production Deployment

## Goal

This deployment path is for the current PepTutor `/lesson` mainline:

- one public origin for frontend, `/lesson`, TTS, and realtime ASR
- backend-only Doubao credentials
- runtime-configurable frontend lesson API without rebuilding the static bundle
- direct refresh on `/lesson` and other SPA routes must not 404

## Checked-in Deployment Shape

The checked-in production skeleton now lives in:

- `deploy/lesson/docker-compose.yml`
- `deploy/lesson/backend.env.example`
- `deploy/lesson/frontend.env.example`

and uses:

- `backend/LightRAG/Dockerfile`
- `frontend/airi/apps/stage-web/Dockerfile`

The `stage-web` container now does three jobs:

1. serves the built Vue app
2. injects runtime `lesson` config into `/runtime-config.js` on container start
3. reverse-proxies same-origin `/peptutor-api/*` traffic to the internal `LightRAG` container

That keeps browser lesson traffic same-origin and avoids rebuilding the frontend when the backend hostname or lesson speech settings change.

## Bring-Up

```bash
python3 scripts/prepare_lesson_deploy_env.py
cd deploy/lesson
docker compose up --build -d
```

If you want to start from the checked-in examples instead of the current local `.env`, copy them manually:

```bash
cd deploy/lesson
cp backend.env.example backend.env
cp frontend.env.example frontend.env
```

Default public entry:

- `http://<host>:8080/lesson`

Default same-origin lesson API entry from the browser:

- `http://<host>:8080/peptutor-api/lesson/catalog`
- `http://<host>:8080/peptutor-api/lesson/turn`
- `ws://<host>:8080/peptutor-api/api/peptutor/doubao-realtime-asr`

## Required Backend Configuration

Fill these in `deploy/lesson/backend.env`:

- `PEPTUTOR_REQUIRE_REMOTE_MODELS=1`
- `LLM_BINDING`
- `LLM_BINDING_HOST`
- `LLM_BINDING_API_KEY`
- `LLM_MODEL`
- `EMBEDDING_BINDING`
- `EMBEDDING_BINDING_HOST`
- `EMBEDDING_BINDING_API_KEY`
- `EMBEDDING_MODEL`
- `PEPTUTOR_DOUBAO_ASR_APP_ID`
- `PEPTUTOR_DOUBAO_ASR_API_KEY`

Leave those on the backend only. Do not mirror them into frontend runtime config.

Doubao TTS keys are optional while the runtime TTS provider is `peptutor-edge-tts`. Add `PEPTUTOR_DOUBAO_TTS_APP_ID` and `PEPTUTOR_DOUBAO_TTS_API_KEY` only when switching TTS back to paid Doubao.

`PEPTUTOR_REQUIRE_REMOTE_MODELS=1` is the production guardrail. With it enabled, `lightrag-server` will refuse to boot if:

- `LLM_BINDING` or `EMBEDDING_BINDING` still points at a local-model backend such as `ollama`
- `LLM_BINDING_HOST` or `EMBEDDING_BINDING_HOST` points at `localhost`, `127.0.0.1`, or another obvious same-node endpoint
- the remote API credential variables are missing
- `LLM_MODEL` is still the local default `mistral-nemo:latest`

That is intentional. Competition deployment on a weak rented server should fail fast instead of silently depending on a local model process.

For the competition deployment baseline, the example keeps lesson vector retrieval off and only enables the memory path that is already local to the backend:

- `PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION=1`
- `PEPTUTOR_SIMPLEMEM_WRITEBACK=1`
- `PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL=1`

The vector and memory stores can stay local to the backend container. The hard requirement here is only that inference and embedding generation come from hosted APIs rather than models running on the rented box.

`Qdrant Cloud` is optional. It is only needed if you explicitly want the extra `lesson vector retrieval` layer. Without it:

- `/lesson` still runs
- prompt injection / writeback / semantic recall still run
- you remove one external dependency and one more failure mode from the competition deployment

Only turn `PEPTUTOR_LESSON_VECTOR_RETRIEVAL=1` back on after you also provide:

- `PEPTUTOR_LESSON_QDRANT_URL`
- `PEPTUTOR_LESSON_QDRANT_API_KEY`
- `PEPTUTOR_LESSON_QDRANT_COLLECTION` if you do not want the default collection name

## Frontend Runtime Configuration

The frontend container writes `/runtime-config.js` at startup from `frontend.env`.

The practical production keys are:

- `PEPTUTOR_RUNTIME_LESSON_API_URL=/peptutor-api`
- `PEPTUTOR_RUNTIME_TTS_PROVIDER=peptutor-edge-tts`
- `PEPTUTOR_RUNTIME_TTS_MODEL=edge-tts`
- `PEPTUTOR_RUNTIME_TTS_VOICE=zh-CN-XiaoxiaoNeural`
- `PEPTUTOR_RUNTIME_ASR_PROVIDER=volcengine-realtime-transcription`
- `PEPTUTOR_RUNTIME_ASR_MODEL=1.2.1.1`

The frontend no longer needs Doubao app credentials to bootstrap backend-native speech proxy mode. Proxy-only `peptutor-edge-tts` / `volcengine-realtime-transcription` is now accepted as the temporary local runtime path while Doubao TTS balance is unavailable. Switch TTS back to `volcengine`, `v1`, and `zh_female_vv_uranus_bigtts` for paid competition or production use.

## Auth Boundary

For public competition deployment, the safest current recommendation is:

- keep frontend runtime auth vars empty
- keep backend secrets server-side only
- if access control is needed, prefer ingress or network-layer protection in front of the public site

The current frontend still supports shipping shared lesson auth through runtime config, but that exposes the same shared credential to every browser. Treat that as a temporary staging tool, not the preferred public deployment model.

## Validation

After `docker compose up --build -d`:

```bash
curl http://127.0.0.1:8080/peptutor-api/lesson/catalog
```

Then open:

- `http://127.0.0.1:8080/lesson`

For backend-only route validation:

```bash
backend/LightRAG/.venv/bin/python scripts/smoke_lesson_turn.py
```

For browser validation against the deployed origin, point the real-browser smoke at the public frontend and same-origin lesson API path.

## Current Tradeoff

This skeleton is the direct deployment mainline for the current project. It does not add distributed rate limiting, orchestration, or secret managers. It does solve the current blockers:

- no more static build-time lock on lesson API URL
- no more frontend exposure of Doubao credentials for backend-native proxy mode
- no more SPA refresh 404 on `/lesson`
- same-origin browser routing for `/lesson`, TTS, and realtime ASR
