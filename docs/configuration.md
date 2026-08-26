# Configuration

Copy `.env.example` to `.env`, then change only the providers and limits you
need. `.env.example` remains the authoritative list of supported variables.

## Transcription

Set `DEMO_DUBBER_TRANSCRIPTION_PROVIDER` to `openai` or `local`.

- OpenAI supports hosted and speaker-aware transcription.
- `auto`, `cpu`, and `cuda` use faster-whisper with CTranslate2.
- `mps` or `metal` uses MLX Whisper on Apple Silicon hosts.
- Docker always uses CPU faster-whisper because Linux containers cannot access
  macOS Metal or MLX.

The main local settings are:

```env
DEMO_DUBBER_TRANSCRIPTION_PROVIDER=local
DEMO_DUBBER_LOCAL_WHISPER_DEVICE=auto
DEMO_DUBBER_LOCAL_WHISPER_MODEL=medium.en
DEMO_DUBBER_LOCAL_WHISPER_COMPUTE_TYPE=int8
DEMO_DUBBER_MLX_WHISPER_MODEL=mlx-community/whisper-medium.en-mlx
```

## Transcript cleanup

Set `DEMO_DUBBER_CLEANUP_PROVIDER` to `openai`, `gemini`, or `openrouter`, then
provide the matching API key. Cleanup responses are validated locally so the
provider cannot change trusted timestamps, cue order, or speaker boundaries.

```env
OPENAI_API_KEY=
GEMINI_API_KEY=
OPENROUTER_API_KEY=
```

Hosted calls may incur provider charges. Gemini AI Studio and OpenRouter use
their OpenAI-compatible endpoints.

## Narration

The app includes 28 American and British English Kokoro voices. Voice samples
are rendered once during the Docker build and served as static audio.

Narration is fitted to cue timing within the configured speed, tempo, silence,
and shift limits. Edit cues that exceed their timing-derived character budgets
before export.

## Storage and background jobs

Projects and artifacts are stored under `outputs/`; temporary processing data
is stored under `workspace/`. Both locations can be changed in `.env`.

Transcription and rendering continue after the browser tab closes while the API
process remains running. Completed job results persist across restarts. A job
interrupted by an API restart is marked as failed at its last recorded phase,
but completed project data and render checkpoints remain on disk.

Remove generated previews, render segments, and transcription chunks after a
retention period with:

```bash
uv run python scripts/cleanup_generated.py --older-than-days 30
uv run python scripts/cleanup_generated.py --older-than-days 30 --apply
```

## Docker

`deploy.sh` builds the FastAPI API and compiled React client into one image. It
binds to `127.0.0.1` by default and mounts the repository's `outputs/` and
`workspace/` directories.

The image preloads the configured faster-whisper model, Kokoro model, English
voice packs, and voice samples. Docker caches these immutable layers between
builds. `Dockerfile.streamlit` remains available for compatibility builds.

## Limits

Uploads are checked for file size, playable duration, video dimensions, and
FFmpeg execution time. Defaults allow files up to 2 GiB, four hours, and 8K.
Adjust the corresponding `DEMO_DUBBER_MAX_*` variables in `.env` when needed.
