from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path

import streamlit as st

from demo_dubber.config import Settings
from demo_dubber.models import Cue, SynthesisResult
from demo_dubber.services.cue_fit import quality_speed_steps
from demo_dubber.services.ffmpeg import FFmpegService
from demo_dubber.services.kokoro_synthesize import KokoroSynthesisService
from demo_dubber.services.project_store import save_session_project
from demo_dubber.services.transcript_import import (
    apply_replacement_texts,
    replacement_texts_from_srt,
    replacement_texts_from_txt,
)
from demo_dubber.utils.files import ensure_directories, output_dir_for_upload
from demo_dubber.utils.media import render_video_file

logger = logging.getLogger(__name__)
PREVIEW_OPTIONS = ["Off", "Audio", "Video"]


def render_transcript_editor(settings: Settings) -> None:
    st.subheader("2. Transcript Editor")
    st.caption(
        "Edit the timestamped transcript, then test each cue's fitted TTS before rendering the full video."
    )

    if "transcript_cues" not in st.session_state:
        st.warning("No transcript loaded yet.")
        return

    source_video = _source_video_path()
    source_audio = _source_audio_path()
    ffmpeg = FFmpegService()

    if source_video is not None:
        with st.expander("Original video", expanded=False):
            render_video_file(source_video)

    cues = st.session_state["transcript_cues"]
    _render_transcript_file_import(cues, settings)
    _sync_preview_modes(cues)
    st.radio(
        "Preview all cues",
        options=PREVIEW_OPTIONS,
        horizontal=True,
        key="global_cue_preview_mode",
        help="Changing this updates every cue preview. You can still override any cue below.",
    )
    for cue_position, cue in enumerate(cues):
        start_label = _format_mmss(cue["start_seconds"])
        end_label = _format_mmss(cue["end_seconds"])
        char_limit = cue.get("char_limit", 0)

        st.markdown(f"**Cue {cue['index'] + 1}**")
        info_col, preview_col = st.columns([1, 2])
        with info_col:
            st.caption(f"{start_label} - {end_label}")
            speaker = (cue.get("speaker") or "").strip()
            if speaker:
                st.caption(f"Speaker: {speaker}")
        with preview_col:
            preview_mode = st.radio(
                "Cue preview",
                options=PREVIEW_OPTIONS,
                horizontal=True,
                key=f"cue_preview_mode_{cue['index']}",
                label_visibility="collapsed",
            )

        if preview_mode == "Audio":
            audio_bytes = _load_audio_preview_bytes(settings, ffmpeg, cue, source_audio)
            if audio_bytes is not None:
                st.audio(audio_bytes, format="audio/wav")
            else:
                st.caption("Original audio preview unavailable for this cue.")
        elif preview_mode == "Video":
            video_preview = _ensure_video_preview(settings, ffmpeg, cue, source_video)
            if video_preview is not None:
                render_video_file(video_preview)
            else:
                st.caption("Original video preview unavailable for this cue.")

        col1, col2 = st.columns(2)
        with col1:
            st.text_area(
                "Original",
                value=cue["original_text"],
                height=120,
                disabled=True,
                key=f"cue_original_{cue['index']}",
            )
        with col2:
            edited_text = st.text_area(
                "Editable",
                key=f"cue_text_{cue['index']}",
                value=cue["text"],
                height=120,
            ).strip()
            st.markdown(
                "<div style='text-align: right; color: #6b7280; font-size: 0.9rem;'>"
                f"{len(edited_text)} characters · timing estimate: {char_limit}"
                "</div>",
                unsafe_allow_html=True,
            )
        cue["text"] = edited_text

        available_seconds = _available_tts_seconds(cues, cue_position, settings)
        _render_tts_test(settings, cue, available_seconds)

        char_count = len(edited_text)
        cue["over_limit"] = char_count > char_limit
        st.divider()

    st.session_state["transcript_cues"] = cues
    st.session_state["transcript_has_errors"] = False
    save_session_project(st.session_state, settings.outputs_dir, stage="edit")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Back to Upload"):
            st.session_state["stage"] = "upload"
            st.rerun()
    with col2:
        if st.button("Finalize Transcript", type="primary"):
            st.session_state["stage"] = "processing_render"
            st.session_state["artifacts"] = {}
            st.rerun()


def _format_mmss(total_seconds: float) -> str:
    whole_seconds = max(0, int(total_seconds))
    minutes, seconds = divmod(whole_seconds, 60)
    return f"{minutes:02}:{seconds:02}"


def _render_transcript_file_import(cues: list[dict], settings: Settings) -> None:
    with st.expander("Import transcript from TXT or SRT", expanded=False):
        st.caption(
            "Upload an SRT with matching cue timestamps, or a TXT file exported from this app."
        )
        uploaded = st.file_uploader(
            "Transcript file",
            type=["txt", "srt"],
            key="transcript_file_upload",
        )
        if uploaded is None:
            return

        if st.button("Use Uploaded Transcript", type="primary"):
            try:
                _apply_uploaded_transcript(cues, uploaded, settings)
            except ValueError as exc:
                st.error(str(exc))
                return

            st.session_state["transcript_cues"] = cues
            st.session_state["transcript_has_errors"] = False
            save_session_project(st.session_state, settings.outputs_dir, stage="edit")
            st.success("Imported transcript text from uploaded file.")
            st.rerun()


def _apply_uploaded_transcript(cues: list[dict], uploaded, settings: Settings) -> None:
    content = uploaded.getvalue().decode("utf-8-sig")
    suffix = Path(uploaded.name).suffix.lower()
    if suffix == ".srt":
        replacement_texts = replacement_texts_from_srt(cues, content)
    else:
        replacement_texts = replacement_texts_from_txt(cues, content)

    apply_replacement_texts(cues, replacement_texts, settings.char_limit_margin)
    _apply_expanded_final_char_limit(cues, settings)
    for cue in cues:
        st.session_state[f"cue_text_{cue['index']}"] = cue["text"]
        st.session_state[f"cue_original_{cue['index']}"] = cue["original_text"]


def _apply_expanded_final_char_limit(cues: list[dict], settings: Settings) -> None:
    if not cues:
        return
    media_asset = st.session_state.get("media_asset") or {}
    duration = media_asset.get("duration_seconds")
    if duration in (None, ""):
        return

    final_cue = cues[-1]
    guard_gap_seconds = settings.guard_gap_ms / 1000
    if len(cues) == 1:
        start_seconds = 0.0
    else:
        previous_end = float(cues[-2]["end_seconds"])
        start_seconds = min(
            float(final_cue["start_seconds"]), previous_end + guard_gap_seconds
        )
    end_seconds = max(float(final_cue["end_seconds"]), float(duration))
    usable_seconds = max(0.0, end_seconds - start_seconds - guard_gap_seconds)
    char_limit = max(
        1, int(usable_seconds * settings.chars_per_second) + settings.char_limit_margin
    )
    final_cue["char_limit"] = max(int(final_cue.get("char_limit") or 1), char_limit)
    final_cue["over_limit"] = (
        len(str(final_cue.get("text") or "")) > final_cue["char_limit"]
    )


def _sync_preview_modes(cues: list[dict]) -> None:
    global_key = "global_cue_preview_mode"
    applied_key = "global_cue_preview_mode_last_applied"

    st.session_state.setdefault(global_key, "Off")
    global_mode = st.session_state[global_key]
    last_applied = st.session_state.get(applied_key)

    if last_applied is None or global_mode != last_applied:
        for cue in cues:
            st.session_state[f"cue_preview_mode_{cue['index']}"] = global_mode
        st.session_state[applied_key] = global_mode
        return

    for cue in cues:
        st.session_state.setdefault(f"cue_preview_mode_{cue['index']}", global_mode)


def _source_video_path() -> Path | None:
    source_video = st.session_state.get("source_video")
    if not source_video:
        return None
    path = Path(source_video)
    return path if path.exists() else None


def _source_audio_path() -> Path | None:
    media_asset = st.session_state.get("media_asset") or {}
    extracted_audio = media_asset.get("extracted_audio")
    if not extracted_audio:
        return None
    path = Path(extracted_audio)
    return path if path.exists() else None


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


def _load_audio_preview_bytes(
    settings: Settings,
    ffmpeg: FFmpegService,
    cue: dict,
    source_audio: Path | None,
) -> bytes | None:
    if source_audio is None:
        return None

    preview_path = _preview_path(settings, cue, suffix=".wav", preview_type="audio")
    if preview_path is None:
        return None

    try:
        if not preview_path.exists():
            ffmpeg.extract_audio_clip(
                audio_path=source_audio,
                output_path=preview_path,
                start_seconds=float(cue["start_seconds"]),
                duration_seconds=_cue_duration_seconds(cue),
            )
        return preview_path.read_bytes()
    except Exception:
        logger.exception("Failed to build audio preview for cue %s", cue["index"] + 1)
        return None


def _ensure_video_preview(
    settings: Settings,
    ffmpeg: FFmpegService,
    cue: dict,
    source_video: Path | None,
) -> Path | None:
    if source_video is None:
        return None

    preview_path = _preview_path(settings, cue, suffix=".mp4", preview_type="video")
    if preview_path is None:
        return None

    try:
        if not preview_path.exists():
            ffmpeg.extract_video_clip(
                video_path=source_video,
                output_path=preview_path,
                start_seconds=float(cue["start_seconds"]),
                duration_seconds=_cue_duration_seconds(cue),
            )
        return preview_path
    except Exception:
        logger.exception("Failed to build video preview for cue %s", cue["index"] + 1)
        return None


def _preview_path(
    settings: Settings, cue: dict, suffix: str, preview_type: str
) -> Path:
    preview_root = _current_output_dir(settings) / "editor_previews" / preview_type
    ensure_directories(preview_root)
    cue_index = int(cue["index"])
    start_ms = round(float(cue["start_seconds"]) * 1000)
    end_ms = round(float(cue["end_seconds"]) * 1000)
    return preview_root / f"cue_{cue_index:04}_{start_ms:08}_{end_ms:08}{suffix}"


def _cue_duration_seconds(cue: dict) -> float:
    return max(0.1, float(cue["end_seconds"]) - float(cue["start_seconds"]))


def _available_tts_seconds(
    cues: list[dict], position: int, settings: Settings
) -> float:
    cue = cues[position]
    gap_seconds = settings.guard_gap_ms / 1000
    start_seconds = float(cue["start_seconds"])
    if position + 1 < len(cues):
        next_cue = cues[position + 1]
        if position + 2 == len(cues):
            end_seconds = _final_cue_window_start(next_cue, cue, gap_seconds)
        else:
            end_seconds = float(next_cue["start_seconds"])
    else:
        media_asset = st.session_state.get("media_asset") or {}
        if position > 0:
            start_seconds = _final_cue_window_start(
                cue, cues[position - 1], gap_seconds
            )
        else:
            start_seconds = 0.0
        end_seconds = max(
            float(cue["end_seconds"]),
            float(media_asset.get("duration_seconds") or cue["end_seconds"]),
        )
    return max(0.0, end_seconds - start_seconds - gap_seconds)


def _final_cue_window_start(cue: dict, previous_cue: dict, gap_seconds: float) -> float:
    earliest_after_previous = float(previous_cue["end_seconds"]) + gap_seconds
    return max(0.0, min(float(cue["start_seconds"]), earliest_after_previous))


def _render_tts_test(
    settings: Settings, cue_payload: dict, available_seconds: float
) -> None:
    cue = Cue(**cue_payload)
    project_token = _tts_preview_project_token()
    signature = _tts_preview_signature(cue, available_seconds, settings, project_token)
    state_key = f"cue_tts_preview_{project_token}_{cue.index}"

    action_col, timing_col = st.columns([1, 2])
    with action_col:
        test_clicked = st.button(
            "Test fitted TTS",
            key=f"test_cue_tts_{project_token}_{cue.index}",
            disabled=not cue.text.strip(),
            use_container_width=True,
        )
    with timing_col:
        st.caption(f"Available speaking time: {available_seconds:.2f}s")

    if test_clicked:
        try:
            with st.spinner(f"Generating fitted TTS for cue {cue.index + 1}..."):
                natural_result, result = _generate_fitted_tts_preview(
                    cue, available_seconds, settings, signature
                )
            st.session_state[state_key] = {
                "signature": signature,
                "natural_audio_path": str(natural_result.audio_path),
                "natural_duration_seconds": natural_result.duration_seconds,
                "audio_path": str(result.audio_path),
                "duration_seconds": result.duration_seconds,
                "fitted": result.fitted,
                "applied_speed": result.applied_speed,
                "time_compression_ratio": result.time_compression_ratio,
            }
        except Exception as exc:
            logger.exception("Failed to generate TTS preview for cue %s", cue.index + 1)
            st.error(f"TTS test failed: {exc}")
            return

    preview = st.session_state.get(state_key)
    if not preview or preview.get("signature") != signature:
        return

    audio_path = Path(preview["audio_path"])
    if not audio_path.exists():
        return

    natural_path = Path(preview.get("natural_audio_path", ""))
    if natural_path.exists():
        st.caption(
            f"Natural delivery · {float(preview['natural_duration_seconds']):.2f}s"
        )
        st.audio(natural_path.read_bytes(), format="audio/wav")

    speed = float(preview["applied_speed"])
    compression = float(preview["time_compression_ratio"])
    duration = float(preview["duration_seconds"])
    effective_speed = speed * compression
    details = (
        f"Generated duration: {duration:.2f}s · Kokoro speed: {speed:.2f}× · "
        f"tempo compression: {compression:.2f}× · effective speed: {effective_speed:.2f}×"
    )
    st.caption("Local quality-capped fit estimate")
    st.audio(audio_path.read_bytes(), format="audio/wav")
    if preview["fitted"]:
        st.success(f"Fits the cue. {details}")
    else:
        st.warning(
            f"Does not fit this cue's local window yet. {details}. The full renderer may borrow nearby slack; "
            "otherwise shorten or redistribute the wording."
        )


def _generate_fitted_tts_preview(
    cue: Cue,
    available_seconds: float,
    settings: Settings,
    signature: str,
) -> tuple[SynthesisResult, SynthesisResult]:
    synth = KokoroSynthesisService(
        voice=settings.kokoro_voice,
        lang_code=settings.kokoro_lang_code,
        repo_id=settings.kokoro_repo_id,
        base_speed=settings.kokoro_speed,
        sample_rate=settings.sample_rate,
    )
    preview_root = _current_output_dir(settings) / "editor_previews" / "tts"
    ensure_directories(preview_root)
    natural_path = preview_root / f"cue_{cue.index:04}_{signature[:16]}_natural.wav"
    output_path = preview_root / f"cue_{cue.index:04}_{signature[:16]}.wav"
    speed_steps = quality_speed_steps(settings.kokoro_speed, settings.max_kokoro_speed)

    natural_result = synth.synthesize_cue(
        cue=cue, output_path=natural_path, speed=settings.kokoro_speed
    )
    shutil.copyfile(natural_path, output_path)
    result: SynthesisResult | None = natural_result.model_copy(
        update={"audio_path": output_path}
    )
    for speed in speed_steps:
        if abs(speed - settings.kokoro_speed) <= 1e-6:
            candidate = result
        else:
            candidate = synth.synthesize_cue(
                cue=cue, output_path=output_path, speed=speed
            )
        result = candidate.model_copy(
            update={"fitted": candidate.duration_seconds <= available_seconds}
        )
        if result.fitted:
            return natural_result, result

    if result is None:
        raise RuntimeError("Kokoro returned no preview audio.")

    compressed = synth.compress_to_duration(
        result=result,
        target_duration_seconds=available_seconds,
        max_compression_ratio=settings.max_tempo_compression_ratio,
    )
    return natural_result, compressed if compressed is not None else result


def _tts_preview_project_token() -> str:
    identity = (
        st.session_state.get("current_project_id")
        or st.session_state.get("output_dir")
        or st.session_state.get("source_video")
        or "current"
    )
    return hashlib.sha256(str(identity).encode("utf-8")).hexdigest()[:12]


def _tts_preview_signature(
    cue: Cue,
    available_seconds: float,
    settings: Settings,
    project_token: str,
) -> str:
    payload = json.dumps(
        {
            "project_token": project_token,
            "text": cue.text,
            "available_seconds": available_seconds,
            "voice": settings.kokoro_voice,
            "speed": settings.kokoro_speed,
            "max_speed": settings.max_kokoro_speed,
            "lang_code": settings.kokoro_lang_code,
            "repo_id": settings.kokoro_repo_id,
            "max_compression_ratio": settings.max_tempo_compression_ratio,
            "max_cue_shift_seconds": settings.max_cue_shift_seconds,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
