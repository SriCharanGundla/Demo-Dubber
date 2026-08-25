# Demo Dubber

Streamlit app for turning narrated demo videos into cleaned, re-voiced MP4s.

It does four things:
- extracts audio from an uploaded demo video with `ffmpeg`
- transcribes the narration with an OpenAI speech-to-text model using timestamps
- cleans and merges awkward transcript chunks with the configured cleanup model
- generates replacement narration locally with Kokoro and muxes it back into the video

## Workflow

The app uses a staged flow:

1. Upload a demo video and preview it in the UI.
2. Extract audio and transcribe it with timestamped OpenAI segments.
3. Run a cleanup pass with the configured model to fix grammar, remove stutters, and merge adjacent split sentence fragments while preserving timestamp coverage.
4. Show timestamped transcript rows with:
   - original text on the left
   - editable text on the right
   - an optional per-cue source preview in audio or video mode
   - unrestricted editable text with a non-blocking timing estimate
   - natural and quality-capped local TTS previews for each cue
   - autosaved progress so draft edits survive refreshes and crashes
5. Generate Kokoro TTS per cue.
6. Plan the narration globally by keeping natural speech where possible, borrowing nearby silence within a bounded timestamp shift, selectively accelerating conflicting cues, and using tightly capped `ffmpeg atempo` only as a last resort.
7. Reject impossible timelines with an actionable cue message instead of silently producing heavily compressed or clipped speech.
8. Assemble a narration WAV timeline.
9. Mux the narration back into the original video.
10. Preview the dubbed MP4 and download:
   - MP4
   - SRT
   - TXT
   - narration WAV
11. Reopen saved uploads from the history list on the upload screen.

## Requirements

- Python `3.12+`
- `uv`
- `ffmpeg`
- `ffprobe`

## Environment

Copy the template and fill in the API key:

```bash
cp .env.example .env
```

Current environment variables:

```env
OPENAI_API_KEY=
KOKORO_VOICE=af_heart
KOKORO_SPEED=1.0
DEMO_DUBBER_MAX_KOKORO_SPEED=1.25
KOKORO_LANG_CODE=a
KOKORO_REPO_ID=hexgrad/Kokoro-82M
DEMO_DUBBER_WORKSPACE=workspace
DEMO_DUBBER_OUTPUTS=outputs
DEMO_DUBBER_GUARD_GAP_MS=120
DEMO_DUBBER_CHARS_PER_SECOND=14.0
DEMO_DUBBER_CHAR_LIMIT_MARGIN=10
DEMO_DUBBER_MAX_TEMPO_COMPRESSION_RATIO=1.08
DEMO_DUBBER_MAX_CUE_SHIFT_SECONDS=0.75
DEMO_DUBBER_TRANSCRIPTION_MODEL=whisper-1
DEMO_DUBBER_TRANSCRIPTION_PROVIDER=openai
DEMO_DUBBER_LOCAL_WHISPER_MODEL=medium.en
DEMO_DUBBER_LOCAL_WHISPER_DEVICE=cpu
DEMO_DUBBER_LOCAL_WHISPER_COMPUTE_TYPE=int8
DEMO_DUBBER_LOCAL_WHISPER_BEAM_SIZE=5
DEMO_DUBBER_TRANSCRIPTION_CHUNK_SECONDS=600
DEMO_DUBBER_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS=1.0
DEMO_DUBBER_CLEANUP_PROVIDER=openai
DEMO_DUBBER_CLEANUP_MODEL=gpt-5.6-luna
```

Notes:
- `OPENAI_API_KEY` is required for transcription and transcript cleanup.
- `DEMO_DUBBER_TRANSCRIPTION_MODEL` sets the default upload-screen transcription mode. You can still switch between `Standard` and `Speaker-aware` per run in the UI.
- `DEMO_DUBBER_TRANSCRIPTION_PROVIDER=local` defaults the upload screen to local `faster-whisper`; the UI still lets you switch back to OpenAI per run.
- Local transcription uses `DEMO_DUBBER_LOCAL_WHISPER_MODEL`, `DEMO_DUBBER_LOCAL_WHISPER_DEVICE`, `DEMO_DUBBER_LOCAL_WHISPER_COMPUTE_TYPE`, and `DEMO_DUBBER_LOCAL_WHISPER_BEAM_SIZE`. The default is `medium.en` on CPU with int8 quantization.
- Recordings longer than `DEMO_DUBBER_TRANSCRIPTION_CHUNK_SECONDS` are transcribed in overlapping chunks. `DEMO_DUBBER_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS` controls boundary context while midpoint ownership removes duplicate cues.
- `DEMO_DUBBER_CLEANUP_PROVIDER=openai` uses OpenAI Responses for transcript cleanup.
- Docker deploy mounts `.docker-data/huggingface` to `/opt/huggingface`, so local Whisper models download on first use and are reused across container rebuilds. Override with `HOST_HF_CACHE_DIR=/path/to/cache ./deploy.sh`.
- `DEMO_DUBBER_CHAR_LIMIT_MARGIN` only controls the timing estimate shown beside editable text; it is not a hard input limit.
- `DEMO_DUBBER_MAX_KOKORO_SPEED` caps generated speech acceleration so fitting cannot silently produce extreme delivery.
- `DEMO_DUBBER_MAX_TEMPO_COMPRESSION_RATIO` caps the last-resort `ffmpeg atempo` adjustment.
- `DEMO_DUBBER_MAX_CUE_SHIFT_SECONDS` controls how far the global scheduler may move narration around its original timestamp to borrow nearby silence.
- `KOKORO_REPO_ID` is set explicitly to suppress Kokoro’s default repo warning.

## Local Run

Install dependencies:

```bash
uv sync --project . --native-tls
```

Run the app:

```bash
uv run --project . python -m streamlit run app.py
```

The included Streamlit config runs headless by default. Open the app in your browser at:

```text
http://localhost:8501
```

## Deployment

This folder includes a Docker-based deployment path.

Files:
- [Dockerfile](./Dockerfile)
- [deploy.sh](./deploy.sh)
- [teardown.sh](./teardown.sh)

The container:
- binds Streamlit to `0.0.0.0`
- exposes port `6767`
- installs `ffmpeg`
- installs the spaCy English model needed by Kokoro’s English pipeline

Deploy:

```bash
./deploy.sh
```

Tear down:

```bash
./teardown.sh
```

Defaults:
- image name: `demo-dubber`
- container name: `demo-dubber`
- host port: `6767`
- data root for persisted uploads/history: `.docker-data/`
- Kokoro model prewarm during image build: enabled by default

Optional overrides:

```bash
IMAGE_NAME=my-demo-dubber CONTAINER_NAME=my-demo-dubber HOST_PORT=6767 ./deploy.sh
ENV_FILE=/absolute/path/to/.env ./deploy.sh
DATA_ROOT=/absolute/path/to/demo-dubber-data ./deploy.sh
PREWARM_KOKORO=1 ./deploy.sh
PREWARM_KOKORO=0 ./deploy.sh
CA_BUNDLE=/path/to/company-ca-bundle.pem ./deploy.sh
```

`PREWARM_KOKORO=1` downloads the Kokoro model and configured voice during image build so runtime rendering does not need to fetch them again. `deploy.sh` passes `KOKORO_VOICE`, `KOKORO_LANG_CODE`, and `KOKORO_REPO_ID` from `.env` as build args so the prewarmed assets match runtime settings. It also passes `HF_TOKEN` from `.env` to Docker as a BuildKit secret for this download without baking the token into the image. If Docker Hub, PyTorch, GitHub, or Hugging Face reset a connection, the build retries before failing.

The deploy script also imports the host CA bundle (default:
`/etc/ssl/certs/ca-certificates.crt`) into the image. Set `CA_BUNDLE` when the
trusted corporate/proxy CA bundle lives elsewhere. The bundle is passed through
BuildKit rather than copied into the Docker build context.

## Outputs

Generated files go into:

- `workspace/`
  temporary uploaded and extracted source media
- `outputs/`
  per-video project folders containing saved editor state, transcript exports, segment WAVs, and final dubbed MP4

## Current Behavior

- transcript editing is cue-based, not word-based
- cue timestamps are derived from the original ASR cue coverage after transcript cleanup
- the app blocks rendering if a cue still cannot fit safely into its slot
- transcript cleanup is validated so cue coverage and ordering cannot drift away from the original ASR timestamps
- speaker labels are optional and only appear when speaker recognition is enabled for that upload

## Known Constraints

- transcript cleanup uses strict JSON Schema where supported, retries one invalid response, and still validates cue coverage locally
- very long videos require enough temporary disk space for the extracted WAV and chunk files
- `gpt-4o-transcribe` and `gpt-4o-mini-transcribe` are not wired into this app because they do not provide the timestamped segment output this workflow depends on
- `ffmpeg atempo` fallback is intentionally conservative and will not heavily compress speech just to force a fit
- the renderer retries a few faster Kokoro speeds before using the tempo fallback
- uploaded and rendered videos are stored on disk inside this app directory unless you change the env paths
