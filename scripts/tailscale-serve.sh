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
# @decision DEC-PWA-010
# @title tailscale-serve.sh refuses root invocation; sudoes only the serve call
# @status accepted
# @rationale Two failure modes hit by founder:
#   1. Running with sudo: uv lives in the user's PATH, not root's — backend
#      never starts ("uv: command not found").
#   2. Running without sudo on a machine where the user lacks Tailscale operator
#      privileges: `tailscale serve` fails with "Access denied".
#   Fix: hard-error on EUID==0 at startup so the user never runs the whole
#   script as root. For the access-denied case, the script retries only the
#   `tailscale serve` call with sudo, printing the operator one-time tip.
#   The cleanup reset mirrors the same try-then-sudo pattern so Ctrl+C
#   cleanup never leaves a stale serve rule.
#   One-time cure for the sudo prompt: sudo tailscale set --operator=$USER
#
# Usage:
#   ./scripts/tailscale-serve.sh          # normal invocation
#
#   DO NOT run with sudo — uv/npx won't be on root's PATH.
#   If 'tailscale serve' needs root on first run, the script will prompt for
#   your password and sudo just that one command.
#
#   Optional one-time setup to skip the sudo prompt entirely:
#     sudo tailscale set --operator=$USER
#
# What it does:
#   1. Preflight checks: tailscale CLI, running daemon, DNS name resolved
#   2. Resolves the Tailscale MagicDNS hostname from `tailscale status --json`
#   3. Sets CORS env vars so the backend accepts requests from that hostname
#   4. Starts Ada backend bound to 0.0.0.0 on port 8000
#   5. Starts Vite frontend bound to 0.0.0.0 on port 5173 (plain HTTP — Tailscale handles TLS)
#   6. Runs `tailscale serve --bg http://localhost:5173` for real-cert HTTPS
#      (falls back to sudo if the user lacks operator privileges)
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
# 0. Root guard — must run as regular user
# ---------------------------------------------------------------------------
# Running with sudo breaks uv and npx: those tools live in the user's PATH,
# not root's. If 'tailscale serve' needs elevated access, this script will
# sudo just that single command (see section 5 below).
if [[ "${EUID:-0}" -eq 0 ]]; then
  echo "" >&2
  echo "ERROR: Don't run this script with sudo." >&2
  echo "  Backend (uv) and Vite (npx) must run as your regular user;" >&2
  echo "  uv typically isn't on root's PATH." >&2
  echo "" >&2
  echo "  If 'tailscale serve' needs root on your system, the script" >&2
  echo "  will sudo just that one command. To skip even that, run once:" >&2
  echo "    sudo tailscale set --operator=\$USER" >&2
  echo "" >&2
  exit 1
fi

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
echo "Starting Tailscale Serve (https://443 -> http://localhost:${FRONTEND_PORT}) ..."
echo ""

# New Tailscale CLI syntax (v1.56+): `tailscale serve --bg <backend-url>`
# HTTPS on port 443 is now the implicit default — the old `https / <url>` form
# is rejected with "the CLI for serve and funnel has changed." Upgrade Tailscale
# if this still fails (tailscale update).
#
# Try without sudo first. If access is denied (user lacks operator privilege),
# fall back to a single sudo invocation and print the one-time cure.
# See DEC-PWA-010 for rationale.

SERVE_ERR_FILE="${REPO_ROOT}/tmp/.tailscale-serve-err"
mkdir -p "${REPO_ROOT}/tmp"

SERVE_CMD=("tailscale" "serve" "--bg" "http://localhost:${FRONTEND_PORT}")

TAILSCALE_SERVE_USED_SUDO=false

if "${SERVE_CMD[@]}" 2>"${SERVE_ERR_FILE}"; then
  : # success without sudo
elif grep -q "Access denied" "${SERVE_ERR_FILE}"; then
  echo "Tailscale serve needs root on this machine — re-trying with sudo." >&2
  echo "Tip: run 'sudo tailscale set --operator=\$USER' once to avoid this prompt next time." >&2
  echo "" >&2
  sudo "${SERVE_CMD[@]}"
  TAILSCALE_SERVE_USED_SUDO=true
else
  # Some other error — surface it and bail out cleanly.
  cat "${SERVE_ERR_FILE}" >&2
  rm -f "${SERVE_ERR_FILE}"
  echo ""
  echo "ERROR: 'tailscale serve' failed. Possible reasons:" >&2
  echo "  - Cert not provisioned: sudo tailscale cert ${TS_DNS_NAME}" >&2
  echo "  - Tailscale version too old: tailscale update" >&2
  echo "  - Port 443 already in use: lsof -i :443" >&2
  echo "" >&2
  kill "${BACKEND_PID}" 2>/dev/null || true
  kill "${FRONTEND_PID}" 2>/dev/null || true
  exit 1
fi

rm -f "${SERVE_ERR_FILE}"
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
  # Mirror the try-then-sudo pattern from startup: if we needed sudo to start, we need
  # it to reset; otherwise try without first.
  if [[ "${TAILSCALE_SERVE_STARTED:-false}" == "true" ]]; then
    echo "  Removing Tailscale Serve rule ..."
    RESET_ERR_FILE="${REPO_ROOT}/tmp/.tailscale-reset-err"
    if [[ "${TAILSCALE_SERVE_USED_SUDO:-false}" == "true" ]]; then
      # We know sudo is required — skip the no-sudo attempt to avoid a pointless failure.
      sudo tailscale serve reset 2>/dev/null || \
        echo "  Warning: could not reset tailscale serve — run 'sudo tailscale serve reset' manually."
    elif tailscale serve reset 2>"${RESET_ERR_FILE}"; then
      : # success without sudo
    elif grep -q "Access denied" "${RESET_ERR_FILE}" 2>/dev/null; then
      sudo tailscale serve reset 2>/dev/null || \
        echo "  Warning: could not reset tailscale serve — run 'sudo tailscale serve reset' manually."
    else
      echo "  Warning: could not reset tailscale serve — you may need to run 'tailscale serve reset' manually."
    fi
    rm -f "${RESET_ERR_FILE:-}"
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
