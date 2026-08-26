from __future__ import annotations

import json
import logging
import shutil
from collections.abc import MutableMapping
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from demo_dubber.utils.files import (
    atomic_write_text,
    ensure_directories,
    ensure_path_within,
    slugify_stem,
)

PROJECT_STATE_FILENAME = "project_state.json"
logger = logging.getLogger(__name__)
_TRANSCRIPT_WIDGET_PREFIXES = (
    "cue_original_",
    "cue_text_",
    "cue_preview_mode_",
)
_TRANSCRIPT_WIDGET_KEYS = (
    "global_cue_preview_mode",
    "global_cue_preview_mode_last_applied",
)


class SavedProjectState(BaseModel):
    project_id: str
    title: str
    stage: str = "upload"
    transcription_mode: str | None = None
    transcription_provider: str | None = None
    cleanup_provider: str | None = None
    tts_voice: str | None = None
    tts_language: str | None = None
    speaker_recognition_enabled: bool | None = None
    uploaded_filename: str | None = None
    output_dir: Path
    source_video: Path | None = None
    media_asset: dict = Field(default_factory=dict)
    transcript: dict = Field(default_factory=dict)
    transcript_cues: list[dict] = Field(default_factory=list)
    transcript_has_errors: bool = False
    artifacts: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


def create_project_output_dir(outputs_root: Path, filename: str) -> Path:
    ensure_directories(outputs_root)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    base_name = f"{slugify_stem(filename)}-{timestamp}"
    candidate = outputs_root / base_name
    suffix = 1
    while candidate.exists():
        candidate = outputs_root / f"{base_name}-{suffix}"
        suffix += 1
    ensure_directories(candidate)
    return candidate


def list_saved_projects(outputs_root: Path) -> list[SavedProjectState]:
    projects, _errors = scan_saved_projects(outputs_root)
    return projects


def scan_saved_projects(
    outputs_root: Path,
) -> tuple[list[SavedProjectState], list[str]]:
    if not outputs_root.exists():
        return [], []

    projects: list[SavedProjectState] = []
    errors: list[str] = []
    for child in outputs_root.iterdir():
        if not child.is_dir():
            continue
        project = load_project_state(child)
        if project is not None:
            # The directory being enumerated is authoritative. Never trust a
            # serialized deletion target from project_state.json.
            projects.append(_rebase_project_paths(project, child.resolve()))
        elif (child / PROJECT_STATE_FILENAME).exists():
            errors.append(child.name)

    return sorted(
        projects, key=lambda project: project.updated_at, reverse=True
    ), sorted(errors)


def load_project_state(output_dir: Path) -> SavedProjectState | None:
    state_path = output_dir / PROJECT_STATE_FILENAME
    if not state_path.exists():
        return None

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        return SavedProjectState(**payload)
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Could not load project state from %s: %s", state_path, exc)
        return None


def _rebase_project_paths(
    project: SavedProjectState, output_dir: Path
) -> SavedProjectState:
    """Make paths portable when an outputs directory moves or is mounted."""
    previous_output_dir = project.output_dir
    updates: dict[str, object] = {"output_dir": output_dir}
    if previous_output_dir == output_dir or previous_output_dir.name != output_dir.name:
        return project.model_copy(update=updates)

    def rebase(value: object) -> object:
        if isinstance(value, dict):
            return {key: rebase(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rebase(item) for item in value]
        if not isinstance(value, (str, Path)):
            return value

        path = Path(value)
        try:
            relative = path.relative_to(previous_output_dir)
        except ValueError:
            return value
        rebased = output_dir / relative
        return rebased if isinstance(value, Path) else str(rebased)

    updates.update(
        source_video=rebase(project.source_video),
        media_asset=rebase(project.media_asset),
        artifacts=rebase(project.artifacts),
    )
    return project.model_copy(update=updates)


def save_project_state(project: SavedProjectState) -> SavedProjectState:
    """Persist a framework-independent project snapshot atomically."""
    ensure_directories(project.output_dir)
    atomic_write_text(
        project.output_dir / PROJECT_STATE_FILENAME,
        project.model_dump_json(indent=2),
    )
    return project


def delete_project(project: SavedProjectState, outputs_root: Path) -> None:
    project_dir = ensure_path_within(outputs_root, project.output_dir)
    if project_dir == outputs_root.resolve():
        raise ValueError("Refusing to delete the outputs root directory.")
    if project_dir.exists():
        shutil.rmtree(project_dir)


def save_session_project(
    session_state: MutableMapping[str, object],
    outputs_root: Path,
    stage: str | None = None,
) -> SavedProjectState | None:
    output_dir_value = session_state.get("output_dir")
    if not output_dir_value:
        return None

    output_dir = ensure_path_within(outputs_root, Path(str(output_dir_value)))
    ensure_directories(output_dir)
    current = load_project_state(output_dir)
    now = datetime.now(UTC)
    source_video = _path_or_none(session_state.get("source_video"))
    uploaded_filename = _string_or_none(session_state.get("uploaded_filename"))
    title = uploaded_filename or (
        source_video.name if source_video is not None else output_dir.name
    )

    project = SavedProjectState(
        project_id=current.project_id if current is not None else output_dir.name,
        title=title,
        stage=_resumable_stage(
            stage or _string_or_none(session_state.get("stage")) or "upload",
            session_state,
        ),
        transcription_mode=_string_or_none(session_state.get("transcription_mode"))
        or "Standard",
        transcription_provider=_string_or_none(
            session_state.get("transcription_provider")
        ),
        cleanup_provider=_string_or_none(session_state.get("cleanup_provider")),
        tts_voice=_string_or_none(session_state.get("tts_voice"))
        or (current.tts_voice if current is not None else None),
        tts_language=_string_or_none(session_state.get("tts_language"))
        or (current.tts_language if current is not None else None),
        uploaded_filename=uploaded_filename,
        output_dir=output_dir,
        source_video=source_video,
        media_asset=dict(session_state.get("media_asset") or {}),
        transcript=dict(session_state.get("transcript") or {}),
        transcript_cues=[
            dict(cue) for cue in (session_state.get("transcript_cues") or [])
        ],
        transcript_has_errors=bool(session_state.get("transcript_has_errors", False)),
        artifacts=dict(session_state.get("artifacts") or {}),
        created_at=current.created_at if current is not None else now,
        updated_at=now,
    )

    return save_project_state(project)


def restore_project_session(
    project: SavedProjectState, session_state: MutableMapping[str, object]
) -> None:
    clear_transcript_widget_state(session_state)
    session_state["source_video"] = (
        str(project.source_video) if project.source_video is not None else None
    )
    session_state["uploaded_filename"] = project.uploaded_filename
    session_state["output_dir"] = str(project.output_dir)
    session_state["transcription_mode"] = _restored_transcription_mode(project)
    session_state["transcription_provider"] = (
        project.transcription_provider or "OpenAI Whisper"
    )
    session_state["cleanup_provider"] = project.cleanup_provider or "OpenAI"
    session_state["tts_voice"] = project.tts_voice
    session_state["tts_language"] = project.tts_language
    session_state["media_asset"] = dict(project.media_asset)
    session_state["transcript"] = dict(project.transcript)
    session_state["transcript_cues"] = [dict(cue) for cue in project.transcript_cues]
    session_state["transcript_has_errors"] = project.transcript_has_errors
    session_state["artifacts"] = dict(project.artifacts)
    session_state["error"] = None
    session_state["stage"] = _restored_stage(project)
    session_state["current_project_id"] = project.project_id
    for cue in project.transcript_cues:
        cue_index = cue.get("index")
        if cue_index is None:
            continue
        session_state[f"cue_text_{cue_index}"] = cue.get("text", "")
        session_state[f"cue_original_{cue_index}"] = cue.get("original_text", "")


def clear_transcript_widget_state(session_state: MutableMapping[str, object]) -> None:
    for key in list(session_state.keys()):
        if key in _TRANSCRIPT_WIDGET_KEYS:
            session_state.pop(key, None)
            continue
        if any(key.startswith(prefix) for prefix in _TRANSCRIPT_WIDGET_PREFIXES):
            session_state.pop(key, None)


def _restored_stage(project: SavedProjectState) -> str:
    if _artifact_exists(project.artifacts.get("muxed_video")):
        return "result"
    if project.transcript_cues:
        return "edit"
    return "upload"


def _resumable_stage(stage: str, session_state: MutableMapping[str, object]) -> str:
    if _artifact_exists((session_state.get("artifacts") or {}).get("muxed_video")):
        return "result"
    if stage in {"edit", "processing_render"} and session_state.get("transcript_cues"):
        return "edit"
    return "upload"


def _artifact_exists(path_value: object) -> bool:
    path = _path_or_none(path_value)
    return path is not None and path.exists()


def _path_or_none(value: object) -> Path | None:
    if value in (None, ""):
        return None
    return Path(str(value))


def _string_or_none(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _restored_transcription_mode(project: SavedProjectState) -> str:
    if project.transcription_mode:
        return project.transcription_mode
    if project.speaker_recognition_enabled:
        return "Speaker-aware"
    return "Standard"
