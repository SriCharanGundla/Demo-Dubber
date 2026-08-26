# Demo Dubber

Demo Dubber turns narrated demo videos into editable transcripts and
Kokoro-voiced MP4s while preserving cue timing and video quality.

## Features

- Resume projects across upload, transcription, editing, and export stages.
- Transcribe with OpenAI or local Whisper on CPU, NVIDIA CUDA, or Apple Silicon.
- Clean transcripts with OpenAI, Gemini AI Studio, or OpenRouter.
- Preview and select from 28 English Kokoro voices.
- Edit timestamped cues and export MP4, SRT, TXT, and narration WAV files.

## Quick start

Requirements: Docker Desktop or OrbStack, plus API keys for any hosted providers
you select.

```bash
cp .env.example .env
./deploy.sh
```

Open `http://localhost:8000`. The first build downloads the Whisper and Kokoro
models; Docker caches them for later builds.

## Configuration

Choose providers in `.env` or from the app:

| Task | Options |
| --- | --- |
| Transcription | OpenAI, local faster-whisper, MLX Whisper |
| Transcript cleanup | OpenAI, Gemini AI Studio, OpenRouter |
| Narration | 28 American and British English Kokoro voices |

Add keys only for the hosted providers you use. See
[`.env.example`](./.env.example) for every setting and
[`docs/configuration.md`](./docs/configuration.md) for device, provider, Docker,
and runtime details.

## Development

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 22+,
pnpm 11+, `ffmpeg`, and `ffprobe`.

```bash
cp .env.example .env
uv sync --all-groups
pnpm install
pnpm dev
```

Open `http://localhost:5173`. Useful commands:

```bash
pnpm lint
pnpm test
pnpm build
pnpm dev:api
pnpm dev:web
```

Interactive API documentation is available at `http://localhost:8000/docs`.
The original Streamlit interface remains under the `streamlit-v1` tag.

## How it works

1. FFmpeg extracts audio from the uploaded video.
2. The selected provider transcribes and safely cleans timestamped cues.
3. Cue edits retain timing-derived character budgets and fitted TTS previews.
4. Kokoro narration is duration-matched and muxed with the source video.

Compatible source video is stream-copied during export. Other formats use a
high-quality fallback. Project state and completed artifacts remain resumable
from disk.

## Architecture

Demo Dubber is a pnpm/uv monorepo with a Vite React client, FastAPI backend,
shared Python media services, and a compatibility Streamlit entry point.

## License

Demo Dubber is available under the [MIT License](./LICENSE).
