# Ada — Multi-Agent Mental Health AI System

A multi-agent AI system that provides conversational therapy, mental/emotional/physical assessment, crisis detection, and caregiver coordination.
Part of the CerebrumCraft ecosystem.

## Prerequisites

- **Python ≥ 3.11** — [uv](https://docs.astral.sh/uv/) can install the right version automatically
- **uv** — fast Python package manager; see [installation instructions](https://docs.astral.sh/uv/getting-started/installation/)
- **Node.js LTS + npm** — any current LTS release (20 or 22)
- **Git**
- **Optional: local LLM server** on `http://localhost:8080/v1` (Ollama, LM Studio, llama.cpp) for offline or dual mode. Without it, set `ANTHROPIC_API_KEY` and use Claude mode.

## Install

```bash
uv pip install -e ".[stt,tts,dev]"
cd web && npm install && cd ..
```

The `[stt,tts,dev]` extras pull in `kokoro-onnx`, `onnxruntime`, `piper-tts`,
`faster-whisper`, and dev tooling (pytest, ruff, etc.).

## Configure Secrets

```bash
cp .env.example .env
```

Open `.env` and set the values you need:

```bash
# Required for Claude mode
ANTHROPIC_API_KEY=sk-ant-...

# Required — falls back to an insecure dev default if unset (do not ship that)
ADA_JWT_SECRET=...

# Only if pointing openai_compat at a paid endpoint
OPENAI_API_KEY=...

# Only if testing push notifications
ADA_VAPID_PRIVATE_KEY=...
ADA_VAPID_PUBLIC_KEY=...
```

Generate a JWT secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`.env` is gitignored. Never commit secrets.

> **Note:** `.env` is loaded automatically on startup (added in PR #79). If you
> are running a version of Ada before that merge, `export` the variables in your
> shell before running `make dev`.

## Model Assets

**Auto-downloaded on first use — nothing to do:**

- **Kokoro TTS** — downloads `kokoro-v1.0.onnx` + `voices-v1.0.bin` (~350 MB) to
  `~/.cache/ada/kokoro/` on the first TTS call. Override the path with
  `ADA_TTS__KOKORO_CACHE_DIR`.
- **faster-whisper turbo** — downloads from Hugging Face on the first
  transcription call.

**Manual download (optional, Piper fallback only):**

Piper TTS fires only if Kokoro fails. Skip unless you want belt-and-suspenders
TTS coverage:

- `data/voices/piper/en_US-lessac-medium.onnx`
- `data/voices/piper/en_US-lessac-medium.onnx.json`

Both files are at
[rhasspy/piper-voices — en/en_US/lessac/medium](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/lessac/medium)
on Hugging Face.

## Run

```bash
make dev
```

Backend on `http://localhost:8000`, frontend on `http://localhost:5173`. `Ctrl+C` stops both.

## LAN / Mobile Testing

```bash
./scripts/lan-dev.sh                      # auto-detect LAN IP
LAN_HTTP_ONLY=1 ./scripts/lan-dev.sh      # skip mkcert (Tailscale path)
LAN_IP=100.x.x.x ./scripts/lan-dev.sh    # explicit IP
```

**Need real-cert HTTPS on iOS/Android without mkcert?** Use Tailscale Serve instead:

```bash
./scripts/tailscale-serve.sh
```

This exposes Ada at `https://<machine>.<tailnet>.ts.net` with a real Let's Encrypt cert
trusted by iOS and Android by default — no profile install or trust toggle required.
Every test device must have Tailscale connected. First-time setup: `sudo tailscale cert <hostname>`.

## Tests

```bash
uv run pytest tests/ -q
cd web && npm run lint
```

## Choosing an LLM Mode

After login, open **Settings** and pick a mode:

| Mode | Requires | Notes |
|------|----------|-------|
| **Claude** | `ANTHROPIC_API_KEY` | Anthropic API only |
| **Offline** | Local LLM on port 8080 | No external API calls |
| **Dual** | Both of the above | Per-agent routing via `config/default.toml → [model_routing.agent_mapping]` |

## Troubleshooting

**"I'm having a moment — could you try saying that again?"**
`ANTHROPIC_API_KEY` is not set in the environment that started the server. Add it
to `.env` and restart (`make dev`).

**`Invalid token: Signature verification failed` after rotating `ADA_JWT_SECRET`**
Expected — existing JWTs were signed with the old secret. Log out, log back in.

**TTS goes silent after switching LLM modes**
The per-session voice toggle is not preserved across mode switches. Re-enable it
in the session controls.
