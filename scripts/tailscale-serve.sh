#!/usr/bin/env bash
# tailscale-serve.sh — Start Ada with real-cert HTTPS via Tailscale Serve.
#
# @decision DEC-PWA-008
# @title scripts/tailscale-serve.sh — HTTPS testing via Tailscale Serve, no cert sideload
# @status accepted
# @rationale Founder N=1 testing on iOS: mkcert root sideload doesn't work
#   because the iOS "Enable Full Trust" toggle doesn't appear after profile
#   install (likely cert wasn't wrapped as a root-CA-class .mobileconfig
#   profile). Tailscale Serve provides a real Let's Encrypt cert at the
#   tailnet MagicDNS hostname, trusted by iOS/Android out-of-box. Tradeoff:
#   every test device must have Tailscale connected — acceptable since
#   founder's testing flow already requires it.
#
# Usage:
#   ./scripts/tailscale-serve.sh
#
# What it does:
#   1. Preflight checks: tailscale CLI, running daemon, DNS name resolved
#   2. Resolves the Tailscale MagicDNS hostname from `tailscale status --json`
#   3. Sets CORS env vars so the backend accepts requests from that hostname
#   4. Starts Ada backend bound to 0.0.0.0 on port 8000
#   5. Starts Vite frontend bound to 0.0.0.0 on port 5173 (plain HTTP — Tailscale handles TLS)
#   6. Runs `tailscale serve --bg http://localhost:5173` for real-cert HTTPS
#   7. Prints the access URL and optional QR code
#
# Cleanup:
#   Press Ctrl+C to stop backend, frontend, and remove the Tailscale serve rule.
#
# Requirements:
#   - Tailscale installed and running: https://tailscale.com/download
#   - MagicDNS enabled in your tailnet admin console
#   - sudo tailscale cert <hostname>.<tailnet>.ts.net   (first time only)
#
# See also:
#   scripts/lan-dev.sh — HTTP-LAN flow for Wi-Fi testing without Tailscale

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

FRONTEND_PORT="${VITE_PORT:-5173}"
BACKEND_PORT="${ADA_API_PORT:-8000}"

# ---------------------------------------------------------------------------
# 1. Preflight checks
# ---------------------------------------------------------------------------

echo ""
echo "Ada Tailscale Serve Mode"
echo "========================"
echo ""

preflight_fail() {
  echo ""
  echo "ERROR: $*" >&2
  echo "" >&2
  exit 1
}

# 1a. tailscale CLI in PATH
if ! command -v tailscale &>/dev/null; then
  preflight_fail "tailscale CLI not found in PATH. Install from https://tailscale.com/download"
fi

# 1b. Tailscale daemon running
TS_STATUS_JSON="$(tailscale status --json 2>/dev/null || true)"
if [[ -z "${TS_STATUS_JSON}" ]]; then
  preflight_fail "tailscale status --json returned nothing. Is the Tailscale daemon running?"
fi

TS_BACKEND_STATE="$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('BackendState', 'Unknown'))
" <<< "${TS_STATUS_JSON}")"

if [[ "${TS_BACKEND_STATE}" != "Running" ]]; then
  preflight_fail "Tailscale daemon state is '${TS_BACKEND_STATE}', expected 'Running'. Run: sudo tailscale up"
fi

# 1c. Resolve MagicDNS hostname (Self.DNSName)
TS_DNS_NAME="$(python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
self_node = d.get('Self', {})
dns = self_node.get('DNSName', '')
# Strip trailing dot (Tailscale returns FQDN with trailing dot)
print(dns.rstrip('.'))
" <<< "${TS_STATUS_JSON}")"

if [[ -z "${TS_DNS_NAME}" ]]; then
  preflight_fail "Could not read Self.DNSName from tailscale status. Is MagicDNS enabled in your tailnet admin console?"
fi

echo "Tailscale hostname: ${TS_DNS_NAME}"
echo ""

# 1d. Cert advisory (warn-only — we can't verify cert existence without invoking tailscale cert,
#     which would attempt issuance and require sudo; the serve step will fail clearly if missing)
echo "Note: Tailscale Serve requires a cert to be pre-provisioned for this machine."
echo "If the serve step fails, run:"
echo "  sudo tailscale cert ${TS_DNS_NAME}"
echo ""

# ---------------------------------------------------------------------------
# 2. Build CORS origin list
# ---------------------------------------------------------------------------

TS_ORIGIN="https://${TS_DNS_NAME}"
LOCAL_ORIGIN="http://localhost:${FRONTEND_PORT}"

echo "CORS origins:"
echo "  ${LOCAL_ORIGIN}"
echo "  ${TS_ORIGIN}"
echo ""

# ---------------------------------------------------------------------------
# 3. Start Ada backend
# ---------------------------------------------------------------------------

echo "Starting Ada backend on 0.0.0.0:${BACKEND_PORT} ..."

export ADA_NETWORK__BIND_HOST="0.0.0.0"
export ADA_NETWORK__CORS_ORIGINS="[\"${LOCAL_ORIGIN}\",\"${TS_ORIGIN}\"]"
export ADA_API__HOST="0.0.0.0"
export ADA_API__PORT="${BACKEND_PORT}"

(cd "${REPO_ROOT}" && uv run python -m ada) &
BACKEND_PID=$!

# ---------------------------------------------------------------------------
# 4. Start Vite frontend (plain HTTP — Tailscale Serve handles TLS termination)
# ---------------------------------------------------------------------------

echo "Starting Vite frontend on 0.0.0.0:${FRONTEND_PORT} (HTTP — TLS via Tailscale) ..."

(cd "${REPO_ROOT}/web" && npx vite --host 0.0.0.0 --port "${FRONTEND_PORT}") &
FRONTEND_PID=$!

# ---------------------------------------------------------------------------
# 5. Start Tailscale Serve (real Let's Encrypt cert, port 443)
# ---------------------------------------------------------------------------

echo ""
echo "Starting Tailscale Serve (https://443 → http://localhost:${FRONTEND_PORT}) ..."
echo ""

# New Tailscale CLI syntax (v1.56+): `tailscale serve --bg <backend-url>`
# HTTPS on port 443 is now the implicit default — the old `https / <url>` form
# is rejected with "the CLI for serve and funnel has changed." Upgrade Tailscale
# if this still fails (tailscale update).
if ! tailscale serve --bg "http://localhost:${FRONTEND_PORT}" 2>&1; then
  echo ""
  echo "ERROR: 'tailscale serve' failed. Possible reasons:" >&2
  echo "  • Cert not provisioned: sudo tailscale cert ${TS_DNS_NAME}" >&2
  echo "  • Tailscale version too old: tailscale update" >&2
  echo "  • Port 443 already in use: lsof -i :443" >&2
  echo "" >&2
  kill "${BACKEND_PID}" 2>/dev/null || true
  kill "${FRONTEND_PID}" 2>/dev/null || true
  exit 1
fi

TAILSCALE_SERVE_STARTED=true

# ---------------------------------------------------------------------------
# 6. Print access URL and optional QR code
# ---------------------------------------------------------------------------

echo "Ada is running:"
echo "  Local:     ${LOCAL_ORIGIN}"
echo "  Tailscale: ${TS_ORIGIN}"
echo ""
echo "Open ${TS_ORIGIN} on any Tailscale-connected device."
echo ""

if command -v qrencode &>/dev/null; then
  echo "Scan to open on mobile:"
  qrencode -t UTF8 "${TS_ORIGIN}"
  echo ""
else
  echo "Tip: install qrencode to print a QR code here."
  echo "     URL: ${TS_ORIGIN}"
  echo ""
fi

echo "Press Ctrl+C to stop."
echo ""

# ---------------------------------------------------------------------------
# 7. Cleanup on exit
# ---------------------------------------------------------------------------

cleanup() {
  echo ""
  echo "Stopping Ada Tailscale Serve Mode ..."

  # Remove the Tailscale Serve rule first (reset clears all serve config for this machine).
  # `tailscale serve reset` is the canonical form across all CLI versions that support serve.
  # The old `tailscale serve --bg https=443 off` fallback is omitted — it was rejected by
  # the same CLI change that broke the start command.
  if [[ "${TAILSCALE_SERVE_STARTED:-false}" == "true" ]]; then
    echo "  Removing Tailscale Serve rule ..."
    tailscale serve reset 2>/dev/null || \
      echo "  Warning: could not reset tailscale serve — you may need to run 'tailscale serve reset' manually."
  fi

  kill "${BACKEND_PID}" 2>/dev/null || true
  kill "${FRONTEND_PID}" 2>/dev/null || true
  wait "${BACKEND_PID}" 2>/dev/null || true
  wait "${FRONTEND_PID}" 2>/dev/null || true

  echo "Done."
}

trap cleanup SIGINT SIGTERM EXIT

# Wait for either process to exit (they normally run until Ctrl+C)
wait "${BACKEND_PID}" "${FRONTEND_PID}"
