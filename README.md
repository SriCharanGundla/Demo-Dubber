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

The React app uses a resumable four-stage flow:

1. `/projects` — upload, rename, delete, and resume projects.
2. `/projects/:id/transcribe` — choose providers and monitor transcription phases.
3. `/projects/:id/transcript` — edit cues, compare original media with fitted TTS, and download SRT/TXT.
4. `/projects/:id/export` — render, preview, and download the dubbed video and supporting files.

Renaming changes only the displayed title. The project ID and URLs stay stable.

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

### Local transcription devices

Both UIs detect the transcription backends available on the current machine.
The environment setting controls the default selection:

```env
# auto | cpu | cuda | mps
DEMO_DUBBER_TRANSCRIPTION_PROVIDER=local
DEMO_DUBBER_LOCAL_WHISPER_DEVICE=auto

# faster-whisper settings for auto, cpu, and cuda
DEMO_DUBBER_LOCAL_WHISPER_MODEL=medium.en
DEMO_DUBBER_LOCAL_WHISPER_COMPUTE_TYPE=int8
DEMO_DUBBER_LOCAL_WHISPER_AUTO_COMPUTE_TYPE=auto

# MLX model used when device=mps on Apple Silicon
DEMO_DUBBER_MLX_WHISPER_MODEL=mlx-community/whisper-medium.en-mlx
```

- `cpu` uses faster-whisper with CTranslate2.
- `cuda` uses faster-whisper on a detected NVIDIA GPU.
- `mps` or `metal` routes to MLX Whisper on Apple Silicon.
- `auto` lets CTranslate2 choose its faster-whisper device. Set `mps` when MLX
  should be the default on a Mac.

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
5. The selected American or British Kokoro voice is retained per project; narration duration-matches short cues within a quality floor, then schedules all cues globally with bounded silence, speed, and tempo adjustments.
6. The app exports TXT, SRT, narration WAV, and a muxed MP4 that stream-copies compatible source video or uses a high-quality fallback.

Project state and artifacts live under `outputs/`. Temporary workspace data lives under `workspace/`. Both can be relocated with environment variables.

## Docker deployments

The supported deployment is the FastAPI + compiled React image:

```bash
./deploy.sh
# open http://localhost:8000
```

The build downloads the configured faster-whisper model, Kokoro model, and all
28 Kokoro English voice packs into the image. It also renders each voice's
picker sample once at build time. Docker reuses those immutable model and audio
layers on later builds, so playing a sample never invokes TTS at runtime.
Project outputs and workspace data remain in the repo's existing `outputs/`
and `workspace/` directories; the baked model cache is intentionally not hidden
by a runtime volume.

Docker Desktop and OrbStack run Linux containers, so macOS Metal and MLX Whisper
are unavailable inside Docker—even on Apple Silicon. The deployment forces
CPU `faster-whisper` with `int8`. `Dockerfile.streamlit` remains available for
manual compatibility builds, but `deploy.sh` runs only the React web app.

## Deployment notes

Rendering and transcription continue when the browser tab is closed, as long as
the Docker container remains running. Reopening a project reconnects the UI to
an active job, and completed artifacts remain resumable from disk.

The in-process API job store is intentionally a local single-process adapter.
Restarting the container interrupts an active job, though completed project data
and render checkpoints remain on disk. Before scaling the API to multiple
workers or machines, replace it with a durable queue and persist job status
externally; the frontend polling contract can stay unchanged.
