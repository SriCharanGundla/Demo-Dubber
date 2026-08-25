# Demo Dubber

Demo Dubber turns a narrated demo video into an editable, timestamp-safe transcript and a Kokoro-voiced MP4. The current branch is a pnpm/uv monorepo with a React web client and FastAPI backend. The original Streamlit app remains available and is tagged as `streamlit-v1`.

## Architecture

```text
apps/
  api/          FastAPI HTTP API and local background-job adapter
  web/          Vite + React JavaScript + Tailwind CSS v4 + shadcn-style UI
  streamlit/    compatibility entry point for the original interface
demo_dubber/    shared models, media, transcription, cleanup, and render services
tests/          workflow, safety, provider, and API contract tests
```

The backend exposes project, transcription, transcript editing, rendering, job polling, provider, health, and contained artifact-download endpoints. Interactive API documentation is at `http://localhost:8000/docs`.

## Requirements

- Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 22+, and pnpm 11+
- `ffmpeg` and `ffprobe`
- An OpenAI key for hosted transcription, or local faster-whisper
- A key for the selected transcript-cleanup provider

## Setup and run

```bash
cp .env.example .env
uv sync --all-groups
pnpm install
pnpm dev
```

Open `http://localhost:5173`. Vite proxies `/api` to FastAPI on port 8000.

```bash
pnpm lint       # Ruff + ESLint, with zero warnings allowed
pnpm test       # Python unit and API contract tests
pnpm build      # Vite production build
pnpm dev:api    # FastAPI only
pnpm dev:web    # React only
```

The Streamlit fallback remains available:

```bash
uv run streamlit run app.py
# or: uv run streamlit run apps/streamlit/app.py
```

## Cleanup providers

All cleanup responses are validated locally to preserve cue order, adjacent coverage, speaker boundaries, and trusted timestamps.

- `openai`: OpenAI Responses API with strict JSON Schema.
- `gemini`: Gemini AI Studio's OpenAI-compatible Chat Completions endpoint.
- `openrouter`: OpenRouter's OpenAI-compatible endpoint. The adapter requests providers that support structured parameters, then safely falls back to prompt-constrained JSON if the selected model rejects JSON Schema.

Gemini and OpenRouter compatibility is covered by mocked request/validation contract tests. Live calls require your own keys and incur provider usage; select the configured provider in either UI to perform an end-to-end check.

Key environment variables:

```env
OPENAI_API_KEY=
DEMO_DUBBER_TRANSCRIPTION_PROVIDER=openai
DEMO_DUBBER_CLEANUP_PROVIDER=openai

GEMINI_API_KEY=
GEMINI_OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
GEMINI_MODEL=gemini-3.7-flash

OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=google/gemini-3.7-flash
OPENROUTER_SITE_URL=
OPENROUTER_APP_NAME=Demo Dubber

```

See [.env.example](./.env.example) for transcription, timing, Kokoro, workspace, and CORS settings.

## Processing behavior

1. The source video is saved under a contained per-project output directory.
2. FFmpeg extracts mono audio; long recordings are transcribed in overlapping chunks.
3. Cleanup may correct wording and merge adjacent cues, but cannot alter timeline coverage.
4. Cue edits retain character budgets derived from timing.
5. Kokoro narration is scheduled globally, borrowing bounded silence and applying conservative speed/tempo adjustments.
6. The app exports TXT, SRT, narration WAV, and a codec-aware muxed MP4.

Project state and artifacts live under `outputs/`. Temporary workspace data lives under `workspace/`. Both can be relocated with environment variables.

## Deployment notes

The existing `Dockerfile`, `deploy.sh`, and `teardown.sh` continue to deploy the Streamlit version. The new development monorepo runs with `pnpm dev`; production container separation is the next deployment step.

The in-process API job store is intentionally a local single-process adapter. Before scaling the API to multiple workers or machines, replace it with a durable queue and persist job status externally; the frontend polling contract can stay unchanged.
