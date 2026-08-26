from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from apps.api.jobs import ActiveJobError, InMemoryJobStore
from demo_dubber.config import get_settings
from demo_dubber.models import Cue, RenderArtifacts, Transcript
from demo_dubber.services.cue_preview import (
    available_tts_seconds,
    generate_tts_preview,
    load_tts_preview,
)
from demo_dubber.services.export import export_srt, export_text
from demo_dubber.services.ffmpeg import FFmpegService
from demo_dubber.services.kokoro_voices import (
    validate_voice,
    voice_language_code,
    voice_options,
)
from demo_dubber.services.project_store import (
    SavedProjectState,
    create_project_output_dir,
    delete_project,
    save_project_state,
    scan_saved_projects,
)
from demo_dubber.services.provider_factory import (
    build_cleanup_service,
    cleanup_provider_catalog,
)
from demo_dubber.services.render_workflow import RenderWorkflow
from demo_dubber.services.transcript_limits import apply_char_limits
from demo_dubber.services.transcript_validation import validate_transcript_timeline
from demo_dubber.services.transcription_factory import (
    build_transcription_service,
    transcription_provider_catalog,
)
from demo_dubber.services.transcription_workflow import TranscriptionWorkflow
from demo_dubber.ui.render_panel import generate_narration
from demo_dubber.utils.files import safe_filename

logger = logging.getLogger(__name__)
settings = get_settings()
jobs = InMemoryJobStore()

app = FastAPI(
    title="Demo Dubber API",
    version="0.2.0",
    description="Transcribe, edit, synthesize, and render dubbed demo videos.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "DEMO_DUBBER_CORS_ORIGINS", "http://localhost:5173"
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TranscriptionRequest(BaseModel):
    transcription_provider: Literal[
        "openai", "local-auto", "local-cpu", "local-cuda", "local-mps"
    ] = "local-auto"
    cleanup_provider: Literal["openai", "gemini", "openrouter"] = "openai"
    tts_voice: str = Field(default="af_heart", min_length=1, max_length=80)


class TranscriptUpdate(BaseModel):
    cues: list[Cue] = Field(min_length=1)


class ProjectUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class TTSPreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5_000)
    voice: str | None = None
    speed: float | None = Field(default=None, gt=0)


def _project(project_id: str) -> SavedProjectState:
    projects, _errors = scan_saved_projects(settings.outputs_dir)
    project = next((item for item in projects if item.project_id == project_id), None)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _project_payload(project: SavedProjectState) -> dict[str, object]:
    payload = project.model_dump(mode="json")
    active_job = jobs.active_for_project(project.project_id)
    payload["active_job"] = active_job.as_dict() if active_job is not None else None
    return payload


def _require_idle_project(project_id: str) -> None:
    active = jobs.active_for_project(project_id)
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A {active.kind} job is active for this project",
        )


def _project_cues(project: SavedProjectState) -> list[Cue]:
    if not project.transcript_cues:
        raise HTTPException(status_code=409, detail="Transcript is missing")
    return [Cue(**cue) for cue in project.transcript_cues]


def _cue_at(project: SavedProjectState, cue_index: int) -> tuple[list[Cue], int, Cue]:
    cues = _project_cues(project)
    position = next(
        (position for position, cue in enumerate(cues) if cue.index == cue_index), None
    )
    if position is None:
        raise HTTPException(status_code=404, detail="Cue not found")
    return cues, position, cues[position]


def _save_uploaded_file(upload: UploadFile, output_dir: Path) -> Path:
    filename = safe_filename(upload.filename or "video.mp4")
    target = output_dir / filename
    descriptor, temporary_name = tempfile.mkstemp(dir=output_dir, suffix=".upload")
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with temporary_path.open("wb") as destination:
            shutil.copyfileobj(upload.file, destination, length=1024 * 1024)
        os.replace(temporary_path, target)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return target


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/providers")
def providers() -> dict[str, object]:
    return {
        "cleanup": [item.__dict__ for item in cleanup_provider_catalog(settings)],
        "transcription": [
            item.__dict__ for item in transcription_provider_catalog(settings)
        ],
    }


@app.get("/api/voices")
def voices() -> dict[str, object]:
    options = voice_options(
        settings.kokoro_voice_catalog, settings.kokoro_voice_samples_dir
    )
    return {
        "voices": [
            {
                **option,
                "sample_url": f"/api/voices/{option['id']}/sample",
            }
            for option in options
        ],
        "default_voice": settings.kokoro_voice,
    }


@app.get("/api/voices/{voice_id}/sample")
def voice_sample(voice_id: str) -> FileResponse:
    language_code = voice_id[0] if voice_id else ""
    if not validate_voice(
        settings.kokoro_voice_catalog, voice_id, language_code
    ):
        raise HTTPException(status_code=404, detail="Voice not found")
    sample_path = settings.kokoro_voice_samples_dir / f"{voice_id}.wav"
    if not sample_path.is_file():
        raise HTTPException(status_code=404, detail="Voice sample is unavailable")
    return FileResponse(
        sample_path,
        media_type="audio/wav",
        filename=sample_path.name,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.get("/api/projects")
def projects() -> dict[str, object]:
    found, errors = scan_saved_projects(settings.outputs_dir)
    return {
        "projects": [_project_payload(item) for item in found],
        "unreadable_projects": errors,
    }


@app.post("/api/projects", status_code=status.HTTP_201_CREATED)
def create_project(video: Annotated[UploadFile, File()]) -> dict[str, object]:
    allowed_suffixes = {".mp4", ".mov", ".m4v", ".webm"}
    filename = safe_filename(video.filename or "video.mp4")
    if Path(filename).suffix.lower() not in allowed_suffixes:
        raise HTTPException(status_code=415, detail="Unsupported video type")

    output_dir = create_project_output_dir(settings.outputs_dir, filename)
    source_video = _save_uploaded_file(video, output_dir)
    now = datetime.now(UTC)
    project = SavedProjectState(
        project_id=output_dir.name,
        title=filename,
        output_dir=output_dir.resolve(),
        source_video=source_video.resolve(),
        tts_voice=settings.kokoro_voice,
        tts_language=voice_language_code(settings.kokoro_voice),
        uploaded_filename=filename,
        created_at=now,
        updated_at=now,
    )
    save_project_state(project)
    return project.model_dump(mode="json")


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict[str, object]:
    return _project_payload(_project(project_id))


@app.patch("/api/projects/{project_id}")
def update_project(project_id: str, update: ProjectUpdate) -> dict[str, object]:
    project = _project(project_id)
    _require_idle_project(project_id)
    title = " ".join(update.title.split())
    if not title:
        raise HTTPException(status_code=422, detail="Project name cannot be blank")
    saved = project.model_copy(update={"title": title, "updated_at": datetime.now(UTC)})
    save_project_state(saved)
    return saved.model_dump(mode="json")


@app.delete("/api/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project(project_id: str) -> None:
    project = _project(project_id)
    _require_idle_project(project_id)
    delete_project(project, settings.outputs_dir)


@app.post("/api/projects/{project_id}/transcribe", status_code=status.HTTP_202_ACCEPTED)
def transcribe_project(
    project_id: str,
    request: TranscriptionRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, object]:
    project = _project(project_id)
    if not validate_voice(
        settings.kokoro_voice_catalog,
        request.tts_voice,
        request.tts_voice[0],
    ):
        raise HTTPException(status_code=422, detail="Unsupported Kokoro voice")
    if project.source_video is None or not project.source_video.exists():
        raise HTTPException(status_code=409, detail="Source video is missing")
    transcription_provider = next(
        (
            provider
            for provider in transcription_provider_catalog(settings)
            if provider.id == request.transcription_provider
        ),
        None,
    )
    if transcription_provider is None or not transcription_provider.configured:
        raise HTTPException(
            status_code=409,
            detail=f"{request.transcription_provider} transcription is unavailable",
        )
    cleanup_provider = next(
        (
            provider
            for provider in cleanup_provider_catalog(settings)
            if provider.id == request.cleanup_provider
        ),
        None,
    )
    if cleanup_provider is None or not cleanup_provider.configured:
        raise HTTPException(
            status_code=409,
            detail=f"{request.cleanup_provider} cleanup is not configured",
        )
    try:
        job = jobs.create(project_id, "transcription")
    except ActiveJobError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    project = project.model_copy(
        update={
            "tts_voice": request.tts_voice,
            "tts_language": voice_language_code(request.tts_voice),
            "updated_at": datetime.now(UTC),
        }
    )
    save_project_state(project)
    background_tasks.add_task(_run_transcription, job.id, project, request)
    return job.as_dict()


def _run_transcription(
    job_id: str, project: SavedProjectState, request: TranscriptionRequest
) -> None:
    jobs.update(job_id, status="running", message="Extracting and transcribing audio")

    def progress(message: str, completed: int | None, total: int | None) -> None:
        jobs.update(job_id, message=message, completed=completed, total=total)

    try:
        transcriber = build_transcription_service(
            settings, request.transcription_provider
        )
        workflow = TranscriptionWorkflow(
            ffmpeg=FFmpegService(),
            transcriber=transcriber,
            cleaner=build_cleanup_service(settings, request.cleanup_provider),
            chunk_seconds=settings.transcription_chunk_seconds,
            overlap_seconds=settings.transcription_chunk_overlap_seconds,
            progress_callback=progress,
        )
        run = workflow.run(project.source_video, project.output_dir)
        transcript = apply_char_limits(
            run.transcript,
            settings.char_limit_margin,
            run.media_asset.duration_seconds,
            settings.chars_per_second,
            settings.guard_gap_ms,
        )
        save_project_state(
            project.model_copy(
                update={
                    "stage": "edit",
                    "transcription_provider": request.transcription_provider,
                    "cleanup_provider": request.cleanup_provider,
                    "media_asset": run.media_asset.model_copy(
                        update={
                            "extracted_audio": run.extracted_audio,
                            "compressed_audio": run.extracted_audio,
                        }
                    ).model_dump(mode="json"),
                    "transcript": transcript.model_dump(mode="json"),
                    "transcript_cues": [
                        cue.model_dump(mode="json") for cue in transcript.cues
                    ],
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        jobs.update(job_id, status="succeeded", message="Transcript ready")
    except Exception as exc:
        logger.exception("Transcription failed for project %s", project.project_id)
        current = jobs.get(job_id)
        jobs.update(
            job_id,
            status="failed",
            message="Transcription failed",
            error=str(exc),
            failed_at=current.message if current is not None else "Transcribing audio",
        )


@app.get("/api/projects/{project_id}/jobs/active")
def active_job(project_id: str) -> dict[str, object]:
    _project(project_id)
    job = jobs.active_for_project(project_id)
    return {"job": job.as_dict() if job is not None else None}


@app.get("/api/projects/{project_id}/jobs/latest")
def latest_job(project_id: str) -> dict[str, object]:
    _project(project_id)
    job = jobs.latest_for_project(project_id)
    return {"job": job.as_dict() if job is not None else None}


@app.get("/api/projects/{project_id}/jobs/{job_id}")
def get_job(project_id: str, job_id: str) -> dict[str, object]:
    _project(project_id)
    job = jobs.get(job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.as_dict()


@app.get("/api/projects/{project_id}/transcript")
def get_transcript(project_id: str) -> dict[str, object]:
    project = _project(project_id)
    if not project.transcript_cues:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return {"cues": project.transcript_cues}


@app.put("/api/projects/{project_id}/transcript")
def update_transcript(project_id: str, update: TranscriptUpdate) -> dict[str, object]:
    project = _project(project_id)
    _require_idle_project(project_id)
    duration = project.media_asset.get("duration_seconds")
    transcript = validate_transcript_timeline(
        Transcript(
            cues=update.cues, raw_response=project.transcript.get("raw_response", {})
        ),
        total_duration=float(duration) if duration is not None else None,
    )
    transcript = transcript.model_copy(
        update={
            "cues": [
                cue.model_copy(update={"over_limit": len(cue.text) > cue.char_limit})
                for cue in transcript.cues
            ]
        }
    )
    saved = project.model_copy(
        update={
            "stage": "edit",
            "transcript": transcript.model_dump(mode="json"),
            "transcript_cues": [cue.model_dump(mode="json") for cue in transcript.cues],
            "transcript_has_errors": any(cue.over_limit for cue in transcript.cues),
            "artifacts": {},
            "updated_at": datetime.now(UTC),
        }
    )
    save_project_state(saved)
    return {"cues": saved.transcript_cues}


@app.get("/api/projects/{project_id}/exports/{export_format}")
def export_transcript(project_id: str, export_format: str) -> FileResponse:
    project = _project(project_id)
    cues = _project_cues(project)
    exporters = {
        "srt": ("subtitled_srt", export_srt, project.output_dir / "transcript.srt"),
        "txt": ("transcript_txt", export_text, project.output_dir / "transcript.txt"),
    }
    selected = exporters.get(export_format.lower())
    if selected is None:
        raise HTTPException(status_code=404, detail="Export format not found")
    artifact_name, exporter, output_path = selected
    path = exporter(cues, output_path)
    artifacts = {**project.artifacts, artifact_name: path}
    save_project_state(
        project.model_copy(
            update={"artifacts": artifacts, "updated_at": datetime.now(UTC)}
        )
    )
    return FileResponse(path, filename=path.name)


@app.get("/api/projects/{project_id}/previews/original/{kind}/{cue_index}")
def original_cue_preview(project_id: str, kind: str, cue_index: int) -> FileResponse:
    project = _project(project_id)
    _cues, _position, cue = _cue_at(project, cue_index)
    preview_root = project.output_dir / "editor_previews" / kind
    preview_root.mkdir(parents=True, exist_ok=True)
    if kind == "audio":
        source = Path(str(project.media_asset.get("extracted_audio") or ""))
        suffix = ".wav"
    elif kind == "video":
        source = project.source_video
        suffix = ".mp4"
    else:
        raise HTTPException(status_code=404, detail="Preview type not found")
    if source is None or not source.is_file():
        raise HTTPException(status_code=404, detail="Preview source is missing")
    output_path = preview_root / (
        f"cue_{cue.index:04}_{int(cue.start_seconds * 1000):08}_"
        f"{int(cue.end_seconds * 1000):08}{suffix}"
    )
    if not output_path.is_file():
        ffmpeg = FFmpegService()
        if kind == "audio":
            ffmpeg.extract_audio_clip(
                audio_path=source,
                output_path=output_path,
                start_seconds=cue.start_seconds,
                duration_seconds=cue.duration_seconds,
            )
        else:
            ffmpeg.extract_video_clip(
                video_path=source,
                output_path=output_path,
                start_seconds=cue.start_seconds,
                duration_seconds=cue.duration_seconds,
            )
    return FileResponse(output_path, filename=output_path.name)


@app.post("/api/projects/{project_id}/previews/tts/{cue_index}")
def create_tts_preview(
    project_id: str, cue_index: int, request: TTSPreviewRequest
) -> dict[str, object]:
    project = _project(project_id)
    _require_idle_project(project_id)
    cues, position, cue = _cue_at(project, cue_index)
    preview_text = request.text.strip()
    if not preview_text:
        raise HTTPException(status_code=422, detail="Preview text cannot be blank")
    cue = cue.model_copy(update={"text": preview_text})
    media_duration = float(
        project.media_asset.get("duration_seconds") or cue.end_seconds
    )
    available_seconds = available_tts_seconds(
        cues,
        position,
        media_duration_seconds=media_duration,
        guard_gap_ms=settings.guard_gap_ms,
    )
    selected_voice = request.voice or project.tts_voice or settings.kokoro_voice
    selected_language = voice_language_code(selected_voice)
    if not validate_voice(
        settings.kokoro_voice_catalog, selected_voice, selected_language
    ):
        raise HTTPException(status_code=422, detail="Unsupported Kokoro voice")
    preview_settings = settings.model_copy(
        update={"kokoro_lang_code": selected_language}
    )
    preview = generate_tts_preview(
        project_id=project.project_id,
        output_dir=project.output_dir,
        cue=cue,
        available_seconds=available_seconds,
        settings=preview_settings,
        voice=selected_voice,
        speed=request.speed or settings.kokoro_speed,
    )
    payload = preview.model_dump(mode="json", exclude={"audio_path", "natural_audio_path"})
    return {
        **payload,
        "audio_url": (
            f"/api/projects/{project_id}/previews/tts/{cue_index}/"
            f"{preview.signature}/audio"
        ),
        "natural_audio_url": (
            f"/api/projects/{project_id}/previews/tts/{cue_index}/"
            f"{preview.signature}/natural"
        ),
    }


@app.get(
    "/api/projects/{project_id}/previews/tts/{cue_index}/{signature}/{variant}"
)
def download_tts_preview(
    project_id: str, cue_index: int, signature: str, variant: str
) -> FileResponse:
    project = _project(project_id)
    _cues, _position, _cue = _cue_at(project, cue_index)
    preview = load_tts_preview(project.output_dir, cue_index, signature)
    if preview is None:
        raise HTTPException(status_code=404, detail="TTS preview not found")
    paths = {"audio": preview.audio_path, "natural": preview.natural_audio_path}
    path = paths.get(variant)
    if path is None:
        raise HTTPException(status_code=404, detail="TTS preview not found")
    path = path.resolve()
    try:
        path.relative_to(project.output_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid preview path") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="TTS preview not found")
    return FileResponse(path, filename=path.name, media_type="audio/wav")


@app.post("/api/projects/{project_id}/render", status_code=status.HTTP_202_ACCEPTED)
def render_project(
    project_id: str, background_tasks: BackgroundTasks
) -> dict[str, object]:
    project = _project(project_id)
    if not project.transcript_cues:
        raise HTTPException(status_code=409, detail="Transcript is missing")
    try:
        job = jobs.create(project_id, "render")
    except ActiveJobError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(_run_render, job.id, project)
    return job.as_dict()


def _run_render(job_id: str, project: SavedProjectState) -> None:
    jobs.update(job_id, status="running", message="Preparing render")

    def progress(message: str, completed: int | None, total: int | None) -> None:
        jobs.update(job_id, message=message, completed=completed, total=total)

    try:
        project_settings = settings.model_copy(
            update={
                "kokoro_voice": project.tts_voice or settings.kokoro_voice,
                "kokoro_lang_code": project.tts_language
                or voice_language_code(project.tts_voice or settings.kokoro_voice),
            }
        )
        workflow = RenderWorkflow(
            settings=project_settings,
            ffmpeg=FFmpegService(),
            narration_generator=generate_narration,
        )
        artifacts = workflow.run(
            cues=[Cue(**cue) for cue in project.transcript_cues],
            media_asset=project.media_asset,
            output_dir=project.output_dir,
            source_video=project.source_video,
            existing_artifacts=RenderArtifacts(**project.artifacts),
            progress_callback=progress,
        )
        save_project_state(
            project.model_copy(
                update={
                    "stage": "result",
                    "artifacts": artifacts.model_dump(mode="json"),
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        jobs.update(job_id, status="succeeded", message="Render ready")
    except Exception as exc:
        logger.exception("Render failed for project %s", project.project_id)
        current = jobs.get(job_id)
        jobs.update(
            job_id,
            status="failed",
            message="Render failed",
            error=str(exc),
            failed_at=current.message if current is not None else "Rendering dubbed demo",
        )


@app.get("/api/projects/{project_id}/artifacts/{artifact_name}")
def download_artifact(project_id: str, artifact_name: str) -> FileResponse:
    project = _project(project_id)
    allowed = {"narration_wav", "subtitled_srt", "transcript_txt", "muxed_video"}
    if artifact_name not in allowed:
        raise HTTPException(status_code=404, detail="Artifact not found")
    stored = project.artifacts.get(artifact_name)
    if not stored:
        raise HTTPException(status_code=404, detail="Artifact not found")
    path = Path(str(stored)).resolve()
    try:
        path.relative_to(project.output_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact path") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path, filename=path.name)


web_dist = Path(__file__).resolve().parents[1] / "web" / "dist"
if web_dist.is_dir():
    assets_dir = web_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="web-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def web_app(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        requested = (web_dist / full_path).resolve()
        try:
            requested.relative_to(web_dist.resolve())
        except ValueError:
            requested = web_dist / "index.html"
        if not requested.is_file():
            requested = web_dist / "index.html"
        return FileResponse(requested)
