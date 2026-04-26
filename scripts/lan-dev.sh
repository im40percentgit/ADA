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
#   detection prefers Tailscale (100.x.x.x) when up, then 192.168.x.x
#   physical-LAN; override with LAN_IP env var. mkcert is optional — the
#   script works over HTTP if not installed. qrencode is optional — the
#   LAN URL is printed regardless.
#
# @decision DEC-PWA-006
# @title LAN_HTTP_ONLY env-var override forces HTTP regardless of mkcert
# @status accepted
# @rationale iOS mkcert root-cert trust is multi-step (transfer pem, install
#   profile, toggle in Certificate Trust Settings — see reference_lan_dev.md
#   memory). Tailscale-based testing for browsing/auth/visual doesn't need
#   HTTPS. Opt-out env var lets the user skip cert hassle on iOS without
#   uninstalling mkcert globally. HTTPS is only required for PWA install,
#   push notifications, and microphone access.
#
# @decision DEC-PWA-007
# @title detect_lan_ip prefers Tailscale interface when up
# @status accepted
# @rationale Founder N=1 testing flow: phones reach the dev box via Tailscale
#   (100.x.x.x), not home Wi-Fi (192.168.x.x). The previous auto-detect picked
#   Wi-Fi first, requiring LAN_IP override on every invocation. Tailscale-first
#   when Tailscale is connected matches actual usage; Wi-Fi-first when Tailscale
#   isn't up preserves previous behavior for non-Tailscale users. We use
#   `tailscale ip -4` (the official command) rather than grepping hostname -I
#   for 100.x.x.x patterns — more correct, handles multiple Tailscale interfaces.
#   `tailscale status --json | grep BackendState` gates the query so a merely
#   installed-but-not-connected tailscale CLI is silently skipped.
#
# Usage:
#   ./scripts/lan-dev.sh
#   LAN_IP=192.168.1.74 ./scripts/lan-dev.sh   # override auto-detection
#   LAN_IP=100.92.157.18 ./scripts/lan-dev.sh  # pin to a specific Tailscale IP
#   LAN_HTTP_ONLY=1 ./scripts/lan-dev.sh       # force HTTP even when mkcert is installed
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
  # Precedence (DEC-PWA-007):
  #   1. Tailscale IPv4 — when `tailscale` CLI exists AND BackendState==Running
  #   2. 192.168.x.x   — typical home Wi-Fi / physical LAN
  #   3. Default-route source IP (ip route get 1.1.1.1)
  #   4. hostname -I first entry
  #   5. 127.0.0.1 last-resort fallback
  local ip

  # 1. Tailscale: probe only when CLI is installed and the daemon is running.
  if command -v tailscale &>/dev/null; then
    local ts_state
    ts_state=$(tailscale status --json 2>/dev/null | grep -o '"BackendState": *"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"')
    if [[ "$ts_state" == "Running" ]]; then
      ip=$(tailscale ip -4 2>/dev/null | head -1)
      if [[ -n "$ip" ]]; then
        echo "$ip"
        return
      fi
    fi
  fi

  # 2. 192.168.x.x physical-LAN preference.
  for ip in $(hostname -I 2>/dev/null || true); do
    if [[ "$ip" =~ ^192\.168\. ]]; then
      echo "$ip"
      return
    fi
  done

  # 3. Default-route source IP.
  ip=$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}')
  if [[ -n "$ip" ]]; then
    echo "$ip"
    return
  fi

  # 4. hostname -I first entry.
  ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  if [[ -n "$ip" ]]; then
    echo "$ip"
    return
  fi

  # 5. ifconfig fallback (macOS / older Linux without `ip`).
  ip=$(ifconfig 2>/dev/null | awk '/inet /{print $2}' | grep -v '127.0.0.1' | head -1)
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

# LAN_HTTP_ONLY=1 forces plain HTTP even when mkcert is available.
# Useful for Tailscale-based testing on iOS where mkcert root-cert trust is
# multi-step and not needed for browsing/auth/visual testing
# (HTTPS is only required for PWA install / push / mic).
if [[ "${LAN_HTTP_ONLY:-0}" == "1" ]]; then
  echo "LAN_HTTP_ONLY=1 — skipping mkcert; serving plain HTTP."
  echo ""
elif command -v mkcert &>/dev/null; then
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
