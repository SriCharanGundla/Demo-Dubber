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
from pydantic import BaseModel, Field

from apps.api.jobs import InMemoryJobStore
from demo_dubber.config import get_settings
from demo_dubber.models import Cue, RenderArtifacts, Transcript
from demo_dubber.services.ffmpeg import FFmpegService
from demo_dubber.services.local_whisper_transcribe import (
    LocalWhisperTranscriptionService,
)
from demo_dubber.services.openai_transcribe import OpenAITranscriptionService
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
    transcription_provider: Literal["openai", "local"] = "openai"
    cleanup_provider: Literal["openai", "gemini", "openrouter"] = "openai"


class TranscriptUpdate(BaseModel):
    cues: list[Cue] = Field(min_length=1)


def _project(project_id: str) -> SavedProjectState:
    projects, _errors = scan_saved_projects(settings.outputs_dir)
    project = next((item for item in projects if item.project_id == project_id), None)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


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
            {"id": "openai", "label": "OpenAI Whisper"},
            {"id": "local", "label": "Local faster-whisper"},
        ],
    }


@app.get("/api/projects")
def projects() -> dict[str, object]:
    found, errors = scan_saved_projects(settings.outputs_dir)
    return {
        "projects": [item.model_dump(mode="json") for item in found],
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
        uploaded_filename=filename,
        created_at=now,
        updated_at=now,
    )
    save_project_state(project)
    return project.model_dump(mode="json")


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict[str, object]:
    return _project(project_id).model_dump(mode="json")


@app.delete("/api/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project(project_id: str) -> None:
    delete_project(_project(project_id), settings.outputs_dir)


@app.post("/api/projects/{project_id}/transcribe", status_code=status.HTTP_202_ACCEPTED)
def transcribe_project(
    project_id: str,
    request: TranscriptionRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, object]:
    project = _project(project_id)
    if project.source_video is None or not project.source_video.exists():
        raise HTTPException(status_code=409, detail="Source video is missing")
    job = jobs.create(project_id, "transcription")
    background_tasks.add_task(_run_transcription, job.id, project, request)
    return job.as_dict()


def _run_transcription(
    job_id: str, project: SavedProjectState, request: TranscriptionRequest
) -> None:
    jobs.update(job_id, status="running", message="Extracting and transcribing audio")
    try:
        transcriber = (
            LocalWhisperTranscriptionService(
                model=settings.local_whisper_model,
                device=settings.local_whisper_device,
                compute_type=settings.local_whisper_compute_type,
                beam_size=settings.local_whisper_beam_size,
            )
            if request.transcription_provider == "local"
            else OpenAITranscriptionService(
                api_key=settings.openai_api_key,
                model=settings.transcription_model,
            )
        )
        workflow = TranscriptionWorkflow(
            ffmpeg=FFmpegService(),
            transcriber=transcriber,
            cleaner=build_cleanup_service(settings, request.cleanup_provider),
            chunk_seconds=settings.transcription_chunk_seconds,
            overlap_seconds=settings.transcription_chunk_overlap_seconds,
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
        jobs.update(
            job_id, status="failed", message="Transcription failed", error=str(exc)
        )


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


@app.post("/api/projects/{project_id}/render", status_code=status.HTTP_202_ACCEPTED)
def render_project(
    project_id: str, background_tasks: BackgroundTasks
) -> dict[str, object]:
    project = _project(project_id)
    if not project.transcript_cues:
        raise HTTPException(status_code=409, detail="Transcript is missing")
    job = jobs.create(project_id, "render")
    background_tasks.add_task(_run_render, job.id, project)
    return job.as_dict()


def _run_render(job_id: str, project: SavedProjectState) -> None:
    jobs.update(job_id, status="running", message="Preparing render")

    def progress(message: str, completed: int | None, total: int | None) -> None:
        jobs.update(job_id, message=message, completed=completed, total=total)

    try:
        workflow = RenderWorkflow(
            settings=settings,
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
        jobs.update(job_id, status="failed", message="Render failed", error=str(exc))


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
