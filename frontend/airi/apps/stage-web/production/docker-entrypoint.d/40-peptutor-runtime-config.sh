#!/bin/sh
set -eu

output_path="/usr/share/nginx/html/runtime-config.js"

json_escape() {
  printf '%s' "${1:-}" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\r/\\r/g; s/\n/\\n/g'
}

write_runtime_pair() {
  key="$1"
  value="$2"
  printf "  %s: \"%s\",\n" "$key" "$(json_escape "$value")"
}

{
  printf 'window.__PEPTUTOR_RUNTIME_CONFIG__ = {\n'
  write_runtime_pair 'VITE_PEPTUTOR_LESSON_API_URL' "${PEPTUTOR_RUNTIME_LESSON_API_URL:-/peptutor-api}"
  write_runtime_pair 'VITE_PEPTUTOR_LESSON_API_KEY' "${PEPTUTOR_RUNTIME_LESSON_API_KEY:-}"
  write_runtime_pair 'VITE_PEPTUTOR_LESSON_BEARER_TOKEN' "${PEPTUTOR_RUNTIME_LESSON_BEARER_TOKEN:-}"
  write_runtime_pair 'VITE_PEPTUTOR_LESSON_ACCESS_TOKEN' "${PEPTUTOR_RUNTIME_LESSON_ACCESS_TOKEN:-}"
  write_runtime_pair 'VITE_PEPTUTOR_LESSON_AUTH_USERNAME' "${PEPTUTOR_RUNTIME_LESSON_AUTH_USERNAME:-}"
  write_runtime_pair 'VITE_PEPTUTOR_LESSON_AUTH_PASSWORD' "${PEPTUTOR_RUNTIME_LESSON_AUTH_PASSWORD:-}"
  write_runtime_pair 'VITE_PEPTUTOR_TTS_PROVIDER' "${PEPTUTOR_RUNTIME_TTS_PROVIDER:-}"
  write_runtime_pair 'VITE_PEPTUTOR_TTS_MODEL' "${PEPTUTOR_RUNTIME_TTS_MODEL:-}"
  write_runtime_pair 'VITE_PEPTUTOR_TTS_VOICE' "${PEPTUTOR_RUNTIME_TTS_VOICE:-}"
  write_runtime_pair 'VITE_PEPTUTOR_TTS_CLUSTER' "${PEPTUTOR_RUNTIME_TTS_CLUSTER:-}"
  write_runtime_pair 'VITE_PEPTUTOR_TTS_PROXY_URL' "${PEPTUTOR_RUNTIME_TTS_PROXY_URL:-}"
  write_runtime_pair 'VITE_PEPTUTOR_ASR_PROVIDER' "${PEPTUTOR_RUNTIME_ASR_PROVIDER:-}"
  write_runtime_pair 'VITE_PEPTUTOR_ASR_MODEL' "${PEPTUTOR_RUNTIME_ASR_MODEL:-}"
  write_runtime_pair 'VITE_PEPTUTOR_ASR_PROXY_URL' "${PEPTUTOR_RUNTIME_ASR_PROXY_URL:-}"
  write_runtime_pair 'VITE_PEPTUTOR_ASR_RESOURCE_ID' "${PEPTUTOR_RUNTIME_ASR_RESOURCE_ID:-}"
  write_runtime_pair 'VITE_PEPTUTOR_ASR_APP_KEY' "${PEPTUTOR_RUNTIME_ASR_APP_KEY:-}"
  write_runtime_pair 'VITE_PEPTUTOR_ENABLE_KOKORO_FALLBACK' "${PEPTUTOR_RUNTIME_ENABLE_KOKORO_FALLBACK:-false}"
  printf '}\n'
} > "${output_path}"
