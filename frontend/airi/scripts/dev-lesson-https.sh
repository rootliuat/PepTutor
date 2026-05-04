#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
STAGE_WEB_DIR="${REPO_DIR}/apps/stage-web"
NODE_BIN_RESOLVER="${REPO_DIR}/scripts/resolve-node-bin.mjs"
CERT_DIR="${REPO_DIR}/.cache/peptutor-dev-https"
PORT="${PEPTUTOR_STAGE_WEB_HTTPS_PORT:-5174}"
BACKEND_URL="${VITE_PEPTUTOR_DEV_PROXY_TARGET:-http://127.0.0.1:9625}"

mkdir -p "${CERT_DIR}"

KEY_PATH="${CERT_DIR}/localhost-key.pem"
CERT_PATH="${CERT_DIR}/localhost-cert.pem"
OPENSSL_CONFIG="${CERT_DIR}/openssl-san.cnf"

PRIMARY_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
PRIMARY_IP="${PRIMARY_IP:-127.0.0.1}"

cat > "${OPENSSL_CONFIG}" <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
CN = localhost

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
IP.2 = ${PRIMARY_IP}
EOF

if [[ ! -f "${KEY_PATH}" || ! -f "${CERT_PATH}" ]]; then
  openssl req \
    -x509 \
    -newkey rsa:2048 \
    -nodes \
    -sha256 \
    -days 365 \
    -keyout "${KEY_PATH}" \
    -out "${CERT_PATH}" \
    -config "${OPENSSL_CONFIG}" >/dev/null 2>&1
fi

export VITE_PEPTUTOR_DEV_HTTPS_KEY="${KEY_PATH}"
export VITE_PEPTUTOR_DEV_HTTPS_CERT="${CERT_PATH}"
export VITE_PEPTUTOR_DEV_PROXY_TARGET="${BACKEND_URL}"
export VITE_PEPTUTOR_LESSON_API_URL="${VITE_PEPTUTOR_LESSON_API_URL:-/peptutor-api}"
if [[ -z "${VITE_PEPTUTOR_TTS_PROVIDER:-}" && -n "${PEPTUTOR_LESSON_TTS_PROVIDER:-}" ]]; then
  export VITE_PEPTUTOR_TTS_PROVIDER="${PEPTUTOR_LESSON_TTS_PROVIDER}"
fi
if [[ -z "${VITE_PEPTUTOR_TTS_MODEL:-}" && -n "${PEPTUTOR_LESSON_TTS_MODEL:-}" ]]; then
  export VITE_PEPTUTOR_TTS_MODEL="${PEPTUTOR_LESSON_TTS_MODEL}"
fi
if [[ -z "${VITE_PEPTUTOR_TTS_VOICE:-}" && -n "${PEPTUTOR_LESSON_TTS_VOICE:-}" ]]; then
  export VITE_PEPTUTOR_TTS_VOICE="${PEPTUTOR_LESSON_TTS_VOICE}"
fi
export VITE_PEPTUTOR_ENABLE_KOKORO_FALLBACK="${VITE_PEPTUTOR_ENABLE_KOKORO_FALLBACK:-false}"

echo "PepTutor HTTPS lesson dev server"
echo "  Local:   https://127.0.0.1:${PORT}/lesson?page_uid=TB-G5S1U1-P2"
echo "  Remote:  https://${PRIMARY_IP}:${PORT}/lesson?page_uid=TB-G5S1U1-P2"
echo "  Backend: ${BACKEND_URL} via /peptutor-api"
echo "  TTS:     ${VITE_PEPTUTOR_TTS_PROVIDER:-runtime default} / ${VITE_PEPTUTOR_TTS_VOICE:-runtime default}"
echo

VITE_BIN="$(
  node "${NODE_BIN_RESOLVER}" vite bin/vite.js "${STAGE_WEB_DIR}"
)"

cd "${STAGE_WEB_DIR}"
exec node "${VITE_BIN}" --host 0.0.0.0 --port "${PORT}" --strictPort
