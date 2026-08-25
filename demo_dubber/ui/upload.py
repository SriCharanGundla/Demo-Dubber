from __future__ import annotations

import subprocess
from pathlib import Path

import streamlit as st
from openai import OpenAIError

from demo_dubber.config import Settings
from demo_dubber.models import Cue, Transcript
from demo_dubber.services.ffmpeg import FFmpegService
from demo_dubber.services.local_whisper_transcribe import (
    LocalWhisperTranscriptionService,
)
from demo_dubber.services.openai_cleanup import OpenAICleanupService
from demo_dubber.services.openai_transcribe import (
    DIARIZATION_MODEL,
    OpenAITranscriptionService,
)
from demo_dubber.services.project_store import (
    clear_transcript_widget_state,
    create_project_output_dir,
    delete_project,
    restore_project_session,
    save_session_project,
    scan_saved_projects,
)
from demo_dubber.services.transcript_import import (
    apply_replacement_texts,
    replacement_texts_from_txt,
    transcript_from_srt,
    transcript_from_timestamped_txt,
)
from demo_dubber.services.transcription_workflow import TranscriptionWorkflow
from demo_dubber.utils.files import (
    atomic_write_bytes,
    ensure_directories,
    output_dir_for_upload,
    safe_filename,
)
from demo_dubber.utils.media import render_video_file

TRANSCRIPTION_MODE_KEY = "transcription_mode"
TRANSCRIPTION_PROVIDER_KEY = "transcription_provider"
CLEANUP_PROVIDER_KEY = "cleanup_provider"
STANDARD_TRANSCRIPTION_MODE = "Standard"
SPEAKER_AWARE_TRANSCRIPTION_MODE = "Speaker-aware"
OPENAI_TRANSCRIPTION_PROVIDER = "OpenAI Whisper"
LOCAL_TRANSCRIPTION_PROVIDER = "Local Whisper"
OPENAI_CLEANUP_PROVIDER = "OpenAI"


def render_upload_panel(settings: Settings) -> None:
    _ensure_transcription_defaults(settings)
    st.subheader("1. Upload")
    _render_saved_projects(settings)

    uploaded = st.file_uploader(
        "Upload a demo video", type=["mp4", "mov", "m4v", "webm"]
    )
    if uploaded is not None:
        video_path = _persist_uploaded_video(settings, uploaded)
        st.success(f"Saved video to {video_path}")
        _show_next_steps(settings, video_path)
        return

    current_video = _current_source_video()
    if current_video is not None:
        st.info(f"Loaded project: `{current_video.name}`")
        _show_next_steps(settings, current_video)
        return

    if uploaded is None:
        st.info("Upload a video to start the workflow.")
        return


def _show_next_steps(settings: Settings, video_path: Path) -> None:
    render_video_file(video_path)
    save_session_project(st.session_state, settings.outputs_dir, stage="upload")
    _render_upload_transcript_import(settings, video_path)
    transcription_mode = st.radio(
        "Transcription mode",
        options=[STANDARD_TRANSCRIPTION_MODE, SPEAKER_AWARE_TRANSCRIPTION_MODE],
        key=TRANSCRIPTION_MODE_KEY,
        horizontal=True,
        help=(
            "Standard uses Whisper timestamps. Speaker-aware uses OpenAI diarization "
            "to label multiple speakers for this upload."
        ),
    )
    transcription_provider = st.radio(
        "Transcription provider",
        options=[OPENAI_TRANSCRIPTION_PROVIDER, LOCAL_TRANSCRIPTION_PROVIDER],
        key=TRANSCRIPTION_PROVIDER_KEY,
        horizontal=True,
        disabled=transcription_mode == SPEAKER_AWARE_TRANSCRIPTION_MODE,
        help="Local Whisper runs faster-whisper on this machine. Speaker-aware transcription currently requires OpenAI.",
    )
    if transcription_mode == SPEAKER_AWARE_TRANSCRIPTION_MODE:
        st.caption("Using `gpt-4o-transcribe-diarize` for this run.")
    elif transcription_provider == LOCAL_TRANSCRIPTION_PROVIDER:
        st.caption(
            f"Using local `faster-whisper` model `{settings.local_whisper_model}` "
            f"on `{settings.local_whisper_device}` with `{settings.local_whisper_compute_type}`."
        )
    else:
        st.caption("Using `whisper-1` for this run.")
    st.radio(
        "Transcript cleanup provider",
        options=[OPENAI_CLEANUP_PROVIDER],
        key=CLEANUP_PROVIDER_KEY,
        horizontal=True,
        help="Cleanup fixes grammar, punctuation, and line grouping after transcription.",
    )
    st.caption(f"Using OpenAI cleanup model `{settings.cleanup_model}`.")
    if st.button("Extract Audio and Transcribe", type="primary"):
        save_session_project(st.session_state, settings.outputs_dir, stage="upload")
        st.session_state["stage"] = "processing_transcript"
        st.rerun()

    media_asset = st.session_state.get("media_asset")
    if media_asset:
        st.caption(
            f"Loaded audio: `{media_asset.get('extracted_audio', '')}` | "
            f"Video duration: {media_asset.get('duration_seconds', 0.0):.2f}s"
        )


def _render_upload_transcript_import(settings: Settings, video_path: Path) -> None:
    with st.expander("Use existing transcript file", expanded=False):
        st.caption(
            "Upload an SRT or timestamped TXT exported by this app to skip OpenAI transcription entirely."
        )
        uploaded = st.file_uploader(
            "Transcript file",
            type=["txt", "srt"],
            key="upload_stage_transcript_file",
        )
        if uploaded is None:
            return

        if st.button("Use Transcript File", type="primary"):
            try:
                _apply_upload_stage_transcript(settings, video_path, uploaded)
            except ValueError as exc:
                st.error(str(exc))
                return
            except (
                OSError,
                RuntimeError,
                subprocess.SubprocessError,
                UnicodeError,
            ) as exc:
                st.error(f"Failed to prepare transcript: {exc}")
                return

            st.success("Loaded transcript from uploaded file.")
            st.rerun()


def _apply_upload_stage_transcript(
    settings: Settings, video_path: Path, uploaded
) -> None:
    content = uploaded.getvalue().decode("utf-8-sig")
    suffix = Path(uploaded.name).suffix.lower()
    cues = st.session_state.get("transcript_cues") or []

    if suffix == ".srt":
        transcript = transcript_from_srt(content, settings.char_limit_margin)
        _prepare_media_for_import(settings, video_path)
        transcript = _apply_char_limits(
            transcript,
            settings.char_limit_margin,
            _media_duration_seconds(),
            settings.chars_per_second,
            settings.guard_gap_ms,
        )
        st.session_state["transcript"] = transcript.model_dump(mode="json")
        st.session_state["transcript_cues"] = [
            cue.model_dump(mode="json") for cue in transcript.cues
        ]
    else:
        if not cues:
            transcript = transcript_from_timestamped_txt(
                content, settings.char_limit_margin
            )
            _prepare_media_for_import(settings, video_path)
            transcript = _apply_char_limits(
                transcript,
                settings.char_limit_margin,
                _media_duration_seconds(),
                settings.chars_per_second,
                settings.guard_gap_ms,
            )
            st.session_state["transcript"] = transcript.model_dump(mode="json")
            st.session_state["transcript_cues"] = [
                cue.model_dump(mode="json") for cue in transcript.cues
            ]
            cues = st.session_state["transcript_cues"]
        elif cues:
            replacement_texts = replacement_texts_from_txt(cues, content)
            apply_replacement_texts(cues, replacement_texts, settings.char_limit_margin)
            _apply_final_char_limit_to_cue_dicts(
                cues,
                _media_duration_seconds(),
                settings.chars_per_second,
                settings.char_limit_margin,
                settings.guard_gap_ms,
            )
            st.session_state["transcript_cues"] = cues

        if not cues:
            raise ValueError(
                "TXT files need timestamps to skip OpenAI transcription. Use a TXT exported by this app, or upload SRT."
            )

    clear_transcript_widget_state(st.session_state)
    st.session_state["transcript_has_errors"] = False
    st.session_state["artifacts"] = {}
    st.session_state["stage"] = "edit"
    st.session_state["error"] = None
    save_session_project(st.session_state, settings.outputs_dir, stage="edit")


def _prepare_media_for_import(settings: Settings, video_path: Path) -> None:
    ffmpeg = FFmpegService()
    media_asset = ffmpeg.probe_video(video_path)
    output_dir = _current_output_dir(settings)
    audio_path = output_dir / f"{video_path.stem}.wav"
    if not audio_path.exists():
        ffmpeg.extract_audio(video_path, audio_path)
    st.session_state["media_asset"] = media_asset.model_copy(
        update={"extracted_audio": audio_path, "compressed_audio": audio_path}
    ).model_dump(mode="json")


def process_transcription(settings: Settings) -> None:
    source_video = st.session_state.get("source_video")
    if not source_video:
        st.session_state["stage"] = "upload"
        st.session_state["error"] = "No source video was found."
        st.rerun()
        return

    transcriber = _build_transcription_service(settings)
    cleanup = _build_cleanup_service(settings)
    workflow = TranscriptionWorkflow(
        ffmpeg=FFmpegService(),
        transcriber=transcriber,
        cleaner=cleanup,
        chunk_seconds=settings.transcription_chunk_seconds,
        overlap_seconds=settings.transcription_chunk_overlap_seconds,
    )

    st.subheader("Transcribing")
    st.caption(
        "Extracting audio, generating timestamped transcription, and cleaning the transcript."
    )

    try:
        with st.spinner("Processing video..."):
            video_path = Path(source_video)
            output_dir = _current_output_dir(settings)
            run = workflow.run(video_path, output_dir)
            media_asset = run.media_asset
            audio_path = run.extracted_audio
            transcript = run.transcript
            transcript = _apply_char_limits(
                transcript,
                settings.char_limit_margin,
                media_asset.duration_seconds,
                settings.chars_per_second,
                settings.guard_gap_ms,
            )
    except (
        OSError,
        OpenAIError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        st.session_state["stage"] = "upload"
        st.session_state["error"] = f"Transcription failed: {exc}"
        st.rerun()
        return

    st.session_state["media_asset"] = media_asset.model_copy(
        update={"extracted_audio": audio_path, "compressed_audio": audio_path}
    ).model_dump(mode="json")
    st.session_state["transcript"] = transcript.model_dump(mode="json")
    st.session_state["transcript_cues"] = [
        cue.model_dump(mode="json") for cue in transcript.cues
    ]
    clear_transcript_widget_state(st.session_state)
    st.session_state["stage"] = "edit"
    st.session_state["error"] = None
    save_session_project(st.session_state, settings.outputs_dir, stage="edit")
    st.rerun()


def _current_output_dir(settings: Settings) -> Path:
    output_dir = st.session_state.get("output_dir")
    if output_dir:
        path = Path(output_dir)
        ensure_directories(path)
        return path

    uploaded_filename = st.session_state.get("uploaded_filename")
    if uploaded_filename:
        path = output_dir_for_upload(settings.outputs_dir, uploaded_filename)
        ensure_directories(path)
        st.session_state["output_dir"] = str(path)
        return path

    ensure_directories(settings.outputs_dir)
    return settings.outputs_dir


def _persist_uploaded_video(settings: Settings, uploaded) -> Path:
    uploaded_filename = safe_filename(uploaded.name)
    upload_token = f"{uploaded_filename}:{getattr(uploaded, 'size', 'unknown')}"
    existing_token = st.session_state.get("uploaded_file_token")
    existing_video = _current_source_video()
    if existing_token == upload_token and existing_video is not None:
        return existing_video

    clear_transcript_widget_state(st.session_state)
    st.session_state[TRANSCRIPTION_MODE_KEY] = _default_transcription_mode(settings)
    st.session_state[TRANSCRIPTION_PROVIDER_KEY] = _default_transcription_provider(
        settings
    )
    st.session_state[CLEANUP_PROVIDER_KEY] = _default_cleanup_provider(settings)
    st.session_state.pop("speaker_recognition_enabled", None)
    upload_dir = create_project_output_dir(settings.outputs_dir, uploaded_filename)
    ensure_directories(upload_dir)
    video_path = upload_dir / uploaded_filename
    atomic_write_bytes(video_path, bytes(uploaded.getbuffer()))
    st.session_state["source_video"] = str(video_path)
    st.session_state["uploaded_filename"] = uploaded_filename
    st.session_state["output_dir"] = str(upload_dir)
    st.session_state["uploaded_file_token"] = upload_token
    st.session_state["media_asset"] = {}
    st.session_state["transcript"] = {}
    st.session_state["transcript_cues"] = []
    st.session_state["transcript_has_errors"] = False
    st.session_state["artifacts"] = {}
    st.session_state["error"] = None
    st.session_state["stage"] = "upload"
    save_session_project(st.session_state, settings.outputs_dir, stage="upload")
    return video_path


def _reset_current_session() -> None:
    for key in [
        "current_project_id",
        "source_video",
        "uploaded_filename",
        "uploaded_file_token",
        "transcription_mode",
        "transcription_provider",
        "cleanup_provider",
        "speaker_recognition_enabled",
        "output_dir",
        "media_asset",
        "transcript",
        "transcript_cues",
        "transcript_has_errors",
        "artifacts",
        "error",
    ]:
        st.session_state.pop(key, None)
    clear_transcript_widget_state(st.session_state)
    st.session_state["stage"] = "upload"


def _render_saved_projects(settings: Settings) -> None:
    projects, load_errors = scan_saved_projects(settings.outputs_dir)
    if load_errors:
        st.warning(
            "Some saved projects have unreadable state and were not loaded: "
            + ", ".join(load_errors[:5])
        )
    if not projects:
        return

    with st.expander("Saved Projects", expanded=True):
        for project in projects:
            meta_col, resume_col, edit_col, download_col, delete_col = st.columns(
                [5, 1, 1, 1, 1]
            )
            with meta_col:
                st.markdown(f"**{project.title}**")
                st.caption(
                    f"{_project_status_label(project)} | Updated {_format_saved_at(project.updated_at)} | "
                    f"Folder `{project.output_dir.name}`"
                )
            with resume_col:
                if st.button(
                    "Resume",
                    key=f"resume_project_{project.project_id}",
                    use_container_width=True,
                ):
                    restore_project_session(project, st.session_state)
                    st.rerun()
            with edit_col:
                can_edit = bool(project.transcript_cues)
                if st.button(
                    "Edit",
                    key=f"edit_project_{project.project_id}",
                    use_container_width=True,
                    disabled=not can_edit,
                ):
                    restore_project_session(project, st.session_state)
                    st.session_state["artifacts"] = {}
                    st.session_state["stage"] = "edit"
                    save_session_project(
                        st.session_state, settings.outputs_dir, stage="edit"
                    )
                    st.rerun()
            with download_col:
                transcript_path = _saved_transcript_path(project)
                if transcript_path is not None:
                    with transcript_path.open("rb") as file_handle:
                        st.download_button(
                            "Transcript",
                            data=file_handle.read(),
                            file_name=transcript_path.name,
                            mime="text/plain",
                            key=f"download_transcript_{project.project_id}",
                            use_container_width=True,
                        )
            with delete_col:
                if st.button(
                    "Delete",
                    key=f"delete_project_{project.project_id}",
                    use_container_width=True,
                ):
                    deleting_current_project = (
                        Path(str(st.session_state.get("output_dir", "")))
                        == project.output_dir
                    )
                    delete_project(project, settings.outputs_dir)
                    if deleting_current_project:
                        _reset_current_session()
                    st.rerun()
            st.divider()


def _saved_transcript_path(project) -> Path | None:
    transcript_txt = (project.artifacts or {}).get("transcript_txt")
    if not transcript_txt:
        return None
    path = Path(str(transcript_txt))
    return path if path.exists() else None


def _project_status_label(project) -> str:
    muxed_video = (project.artifacts or {}).get("muxed_video")
    if (
        _saved_transcript_path(project) is not None
        and muxed_video
        and Path(str(muxed_video)).exists()
    ):
        return "Rendered"
    if project.transcript_cues:
        return "Draft transcript"
    if project.source_video is not None:
        return "Uploaded"
    return "Saved"


def _format_saved_at(saved_at) -> str:
    return saved_at.astimezone().strftime("%Y-%m-%d %H:%M")


def _current_source_video() -> Path | None:
    source_video = st.session_state.get("source_video")
    if not source_video:
        return None
    path = Path(str(source_video))
    return path if path.exists() else None


def _apply_char_limits(
    transcript: Transcript,
    margin: int,
    media_duration_seconds: float | None = None,
    chars_per_second: float | None = None,
    guard_gap_ms: int = 0,
) -> Transcript:
    updated_cues = []
    final_char_limit = _expanded_final_char_limit(
        transcript.cues,
        media_duration_seconds,
        chars_per_second,
        margin,
        guard_gap_ms,
    )
    for index, cue in enumerate(transcript.cues):
        original_text = cue.original_text or cue.text
        char_limit = max(1, len(original_text) + margin)
        if final_char_limit is not None and index == len(transcript.cues) - 1:
            char_limit = max(char_limit, final_char_limit)
        updated_cues.append(
            cue.model_copy(
                update={
                    "char_limit": char_limit,
                    "over_limit": False,
                }
            )
        )
    return transcript.model_copy(update={"cues": updated_cues})


def _apply_final_char_limit_to_cue_dicts(
    cues: list[dict],
    media_duration_seconds: float | None,
    chars_per_second: float,
    margin: int,
    guard_gap_ms: int,
) -> None:
    model_cues = [Cue(**cue) for cue in cues]
    final_char_limit = _expanded_final_char_limit(
        model_cues,
        media_duration_seconds,
        chars_per_second,
        margin,
        guard_gap_ms,
    )
    if final_char_limit is None or not cues:
        return
    cues[-1]["char_limit"] = max(int(cues[-1].get("char_limit") or 1), final_char_limit)
    cues[-1]["over_limit"] = (
        len(str(cues[-1].get("text") or "")) > cues[-1]["char_limit"]
    )


def _expanded_final_char_limit(
    cues: list[Cue],
    media_duration_seconds: float | None,
    chars_per_second: float | None,
    margin: int,
    guard_gap_ms: int,
) -> int | None:
    if not cues or media_duration_seconds is None or chars_per_second is None:
        return None
    final_cue = cues[-1]
    guard_gap_seconds = guard_gap_ms / 1000
    if len(cues) == 1:
        start_seconds = 0.0
    else:
        start_seconds = min(
            final_cue.start_seconds, cues[-2].end_seconds + guard_gap_seconds
        )
    end_seconds = max(final_cue.end_seconds, media_duration_seconds)
    usable_seconds = max(0.0, end_seconds - start_seconds - guard_gap_seconds)
    return max(1, int(usable_seconds * chars_per_second) + margin)


def _media_duration_seconds() -> float | None:
    media_asset = st.session_state.get("media_asset") or {}
    duration = media_asset.get("duration_seconds")
    return float(duration) if duration not in (None, "") else None


def _ensure_transcription_defaults(settings: Settings) -> None:
    st.session_state.setdefault(
        TRANSCRIPTION_MODE_KEY,
        _default_transcription_mode(settings),
    )
    st.session_state.setdefault(
        TRANSCRIPTION_PROVIDER_KEY,
        _default_transcription_provider(settings),
    )
    st.session_state.setdefault(
        CLEANUP_PROVIDER_KEY,
        _default_cleanup_provider(settings),
    )


def _build_transcription_service(settings: Settings):
    if _selected_transcription_model(settings) == DIARIZATION_MODEL:
        return OpenAITranscriptionService(
            api_key=settings.openai_api_key,
            model=DIARIZATION_MODEL,
        )

    if st.session_state.get(TRANSCRIPTION_PROVIDER_KEY) == LOCAL_TRANSCRIPTION_PROVIDER:
        return LocalWhisperTranscriptionService(
            model=settings.local_whisper_model,
            device=settings.local_whisper_device,
            compute_type=settings.local_whisper_compute_type,
            beam_size=settings.local_whisper_beam_size,
        )

    return OpenAITranscriptionService(
        api_key=settings.openai_api_key,
        model="whisper-1",
    )


def _build_cleanup_service(settings: Settings):
    return OpenAICleanupService(
        api_key=settings.openai_api_key,
        model=settings.cleanup_model,
    )


def _default_transcription_provider(settings: Settings) -> str:
    if settings.transcription_provider.lower() in {
        "local",
        "local-whisper",
        "local_whisper",
    }:
        return LOCAL_TRANSCRIPTION_PROVIDER
    return OPENAI_TRANSCRIPTION_PROVIDER


def _default_cleanup_provider(settings: Settings) -> str:
    return OPENAI_CLEANUP_PROVIDER


def _selected_transcription_model(settings: Settings) -> str:
    if (
        st.session_state.get(
            TRANSCRIPTION_MODE_KEY,
            _default_transcription_mode(settings),
        )
        == SPEAKER_AWARE_TRANSCRIPTION_MODE
    ):
        return DIARIZATION_MODEL
    return "whisper-1"


def _default_transcription_mode(settings: Settings) -> str:
    if settings.transcription_model == DIARIZATION_MODEL:
        return SPEAKER_AWARE_TRANSCRIPTION_MODE
    return STANDARD_TRANSCRIPTION_MODE
