#!/usr/bin/env bash
# lan-dev.sh — Start Ada in LAN-accessible mode for multi-device testing.
#
# @decision DEC-PWA-004
# @title lan-dev.sh binds both backend and frontend to 0.0.0.0 via env vars
# @status accepted
# @rationale The backend uses ADA_NETWORK__BIND_HOST and ADA_API__HOST env
#   var overrides rather than editing config files, so the default config
#   stays localhost-only and LAN mode is an opt-in runtime flag. Vite's
#   --host 0.0.0.0 is the standard way to expose the dev server on all
#   interfaces. HTTPS certs are passed to Vite via VITE_HTTPS_CERT and
#   VITE_HTTPS_KEY env vars (read by web/vite.config.ts) because Vite 6
#   removed the --https CLI flag. Backend is launched via `uv run python`
#   to match the Makefile and ensure the project venv is used. LAN IP
#   detection prefers 192.168.x.x physical-LAN addresses over VPN/tunnel
#   interfaces; override with LAN_IP env var. mkcert is optional — the
#   script works over HTTP if not installed. qrencode is optional — the
#   LAN URL is printed regardless.
#
# Usage:
#   ./scripts/lan-dev.sh
#   LAN_IP=192.168.1.74 ./scripts/lan-dev.sh   # override auto-detection
#
# What it does:
#   1. Detects the local LAN IP address (or accepts LAN_IP override)
#   2. Optionally generates mkcert TLS certs if mkcert is available
#   3. Starts the Ada backend bound to 0.0.0.0 with LAN CORS origins
#   4. Starts Vite with --host 0.0.0.0 (HTTPS via env vars if certs exist)
#   5. Prints the LAN access URL (and QR code if qrencode is available)
#
# Cleanup:
#   Press Ctrl+C to stop both backend and frontend processes.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERTS_DIR="${REPO_ROOT}/tmp/lan-certs"

# ---------------------------------------------------------------------------
# 1. Detect local IP address
# ---------------------------------------------------------------------------

detect_lan_ip() {
  # Prefer 192.168.x.x (typical home Wi-Fi) to avoid VPN/tunnel interfaces
  # like Tailscale (100.64-127.x), wireguard (10.x.x.x), etc. Fall back to
  # the default-route source IP, then hostname -I / ifconfig.
  local ip
  for ip in $(hostname -I 2>/dev/null || true); do
    if [[ "$ip" =~ ^192\.168\. ]]; then
      echo "$ip"
      return
    fi
  done
  ip=$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}')
  if [[ -z "$ip" ]]; then
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  fi
  if [[ -z "$ip" ]]; then
    ip=$(ifconfig 2>/dev/null | awk '/inet /{print $2}' | grep -v '127.0.0.1' | head -1)
  fi
  echo "${ip:-127.0.0.1}"
}

# LAN_IP env var overrides auto-detection.
LAN_IP="${LAN_IP:-$(detect_lan_ip)}"
FRONTEND_PORT="${VITE_PORT:-5173}"
BACKEND_PORT="${ADA_API_PORT:-8000}"

echo ""
echo "Ada LAN Dev Mode"
echo "================"
echo "LAN IP: ${LAN_IP}"
echo ""

# ---------------------------------------------------------------------------
# 2. Optionally generate mkcert certs
# ---------------------------------------------------------------------------

USE_HTTPS=false
CERT_FILE=""
KEY_FILE=""

if command -v mkcert &>/dev/null; then
  echo "mkcert detected — generating TLS certificates for ${LAN_IP} ..."
  mkdir -p "${CERTS_DIR}"
  mkcert -cert-file "${CERTS_DIR}/cert.pem" \
         -key-file  "${CERTS_DIR}/key.pem" \
         localhost 127.0.0.1 "${LAN_IP}" 2>/dev/null
  CERT_FILE="${CERTS_DIR}/cert.pem"
  KEY_FILE="${CERTS_DIR}/key.pem"
  USE_HTTPS=true
  echo "  Certificates written to ${CERTS_DIR}"
  echo ""
else
  echo "mkcert not found — running without TLS (HTTP only)."
  echo "  Install mkcert for HTTPS: https://github.com/FiloSottile/mkcert"
  echo ""
fi

# ---------------------------------------------------------------------------
# 3. Build LAN origin list for CORS
# ---------------------------------------------------------------------------

if [[ "$USE_HTTPS" == "true" ]]; then
  SCHEME="https"
else
  SCHEME="http"
fi

LAN_ORIGIN="${SCHEME}://${LAN_IP}:${FRONTEND_PORT}"

# ---------------------------------------------------------------------------
# 4. Start backend
# ---------------------------------------------------------------------------

echo "Starting Ada backend on 0.0.0.0:${BACKEND_PORT} ..."

export ADA_NETWORK__BIND_HOST="0.0.0.0"
export ADA_NETWORK__CORS_ORIGINS="[\"http://localhost:${FRONTEND_PORT}\",\"${LAN_ORIGIN}\"]"
export ADA_API__HOST="0.0.0.0"
export ADA_API__PORT="${BACKEND_PORT}"

# Use `uv run python` to match the Makefile and ensure the project venv is used.
# Plain `python` is not always on PATH (the user may only have `python3` or `uv`).
(cd "${REPO_ROOT}" && uv run python -m ada) &
BACKEND_PID=$!

# ---------------------------------------------------------------------------
# 5. Start Vite frontend
# ---------------------------------------------------------------------------

echo "Starting Vite frontend on 0.0.0.0:${FRONTEND_PORT} ..."

# Vite 6 removed the --https CLI flag. We hand cert/key paths to vite.config.ts
# via env vars, which reads them and populates server.https. Unset env vars
# mean plain HTTP (default dev flow unaffected).
if [[ "$USE_HTTPS" == "true" ]]; then
  export VITE_HTTPS_CERT="${CERT_FILE}"
  export VITE_HTTPS_KEY="${KEY_FILE}"
fi

(cd "${REPO_ROOT}/web" && npx vite --host 0.0.0.0 --port "${FRONTEND_PORT}") &
FRONTEND_PID=$!

# ---------------------------------------------------------------------------
# 6. Print access URL and optional QR code
# ---------------------------------------------------------------------------

LAN_URL="${LAN_ORIGIN}"

echo ""
echo "Ada is running:"
echo "  Local:   http://localhost:${FRONTEND_PORT}"
echo "  Network: ${LAN_URL}"
echo ""

if command -v qrencode &>/dev/null; then
  echo "Scan to open on mobile:"
  qrencode -t UTF8 "${LAN_URL}"
  echo ""
else
  echo "Tip: install qrencode to print a QR code here."
  echo ""
fi

echo "Press Ctrl+C to stop."
echo ""

# ---------------------------------------------------------------------------
# 7. Wait and clean up on exit
# ---------------------------------------------------------------------------

cleanup() {
  echo ""
  echo "Stopping Ada LAN Dev Mode ..."
  kill "${BACKEND_PID}" 2>/dev/null || true
  kill "${FRONTEND_PID}" 2>/dev/null || true
  wait "${BACKEND_PID}" 2>/dev/null || true
  wait "${FRONTEND_PID}" 2>/dev/null || true
  echo "Done."
}

trap cleanup SIGINT SIGTERM

wait "${BACKEND_PID}" "${FRONTEND_PID}"
