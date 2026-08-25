from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

import streamlit as st

from demo_dubber.config import Settings
from demo_dubber.models import Cue, RenderArtifacts, SynthesisResult
from demo_dubber.services.cue_fit import next_quality_adjustment, quality_speed_steps
from demo_dubber.services.ffmpeg import FFmpegService
from demo_dubber.services.kokoro_synthesize import KokoroSynthesisService
from demo_dubber.services.project_store import (
    clear_transcript_widget_state,
    save_session_project,
)
from demo_dubber.services.render_workflow import RenderWorkflow
from demo_dubber.services.timeline import (
    TimelineAssembler,
    plan_quality_constrained_placements,
)
from demo_dubber.utils.files import (
    atomic_write_json,
    ensure_directories,
    output_dir_for_upload,
)
from demo_dubber.utils.media import render_video_file

logger = logging.getLogger(__name__)


def process_render(settings: Settings) -> None:
    st.subheader("Rendering")
    st.caption(
        "Generating Kokoro narration, exporting subtitles, and muxing the final MP4."
    )

    cues = _load_cues()
    media_asset = st.session_state.get("media_asset")
    if not cues or not media_asset:
        st.session_state["stage"] = "edit"
        st.session_state["error"] = "Transcript data is missing."
        st.rerun()

    progress_bar = st.progress(0, text="Preparing render...")
    status_text = st.empty()
    started_at = time.perf_counter()
    output_dir = _current_output_dir(settings)

    def report(
        message: str, completed: int | None = None, total: int | None = None
    ) -> None:
        status_text.caption(message)
        logger.info(message)
        if completed is not None and total:
            percent = min(100, int((completed / total) * 100))
            progress_bar.progress(percent, text=message)

    try:
        workflow = RenderWorkflow(
            settings=settings,
            ffmpeg=FFmpegService(),
            narration_generator=generate_narration,
        )
        artifacts = workflow.run(
            cues=cues,
            media_asset=media_asset,
            output_dir=output_dir,
            source_video=Path(st.session_state["source_video"]),
            existing_artifacts=RenderArtifacts(**st.session_state.get("artifacts", {})),
            progress_callback=report,
        )
        elapsed = time.perf_counter() - started_at
        report(
            f"Render completed in {elapsed:.1f}s.",
            completed=len(cues) + 3,
            total=len(cues) + 3,
        )
    except Exception as exc:
        logger.exception("Render failed")
        st.session_state["stage"] = "edit"
        st.session_state["error"] = f"Render failed: {exc}"
        st.rerun()
        return

    _save_artifacts(artifacts)
    st.session_state["stage"] = "result"
    st.session_state["error"] = None
    save_session_project(st.session_state, settings.outputs_dir, stage="result")
    st.rerun()


def render_result_panel(settings: Settings) -> None:
    st.subheader("3. Dubbed Video")
    st.caption(
        "Review the final MP4, download the generated assets, or go back and edit the transcript."
    )

    artifacts = RenderArtifacts(**st.session_state.get("artifacts", {}))
    if artifacts.muxed_video is None or not artifacts.muxed_video.exists():
        st.warning("No rendered video is available yet.")
        return

    save_session_project(st.session_state, settings.outputs_dir, stage="result")
    render_video_file(artifacts.muxed_video)
    _render_downloads(artifacts)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Edit Transcript"):
            _clear_render_artifacts()
            st.session_state["stage"] = "edit"
            save_session_project(st.session_state, settings.outputs_dir, stage="edit")
            st.rerun()
    with col2:
        if st.button("Start New Video"):
            _reset_workflow()
            st.rerun()


def _load_cues() -> list[Cue]:
    cue_dicts = st.session_state.get("transcript_cues", [])
    return [Cue(**cue) for cue in cue_dicts]


def generate_narration(
    cues: list[Cue],
    media_asset: dict,
    settings: Settings,
    output_dir: Path,
    voice: str,
    base_speed: float,
    guard_gap_ms: int,
    existing_artifacts: RenderArtifacts,
    progress_callback: Callable[[str, int | None, int | None], None] | None = None,
) -> RenderArtifacts:
    synth = KokoroSynthesisService(
        voice=voice,
        lang_code=settings.kokoro_lang_code,
        repo_id=settings.kokoro_repo_id,
        base_speed=base_speed,
        sample_rate=settings.sample_rate,
    )
    assembler = TimelineAssembler(
        sample_rate=settings.sample_rate,
        guard_gap_ms=guard_gap_ms,
    )

    segment_dir = output_dir / "segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / "render_progress.json"
    progress_payload = _load_progress(progress_path)
    results = []
    speed_steps = quality_speed_steps(base_speed, settings.max_kokoro_speed)
    total_steps = len(cues) + 3
    total_duration = float(
        media_asset.get("duration_seconds") or max(cue.end_seconds for cue in cues)
    )
    speed_positions: dict[int, int] = {cue.index: 0 for cue in cues}
    cue_signatures: dict[int, str] = {}
    timeline_signature = _timeline_signature(cues, total_duration, settings)

    for index, cue in enumerate(cues):
        previous_cue = cues[index - 1] if index > 0 else None
        next_cue = cues[index + 1] if index + 1 < len(cues) else None
        window_start, window_end = _render_window_for_cue(
            cue=cue,
            previous_cue=previous_cue,
            next_cue=next_cue,
            total_duration=total_duration,
            guard_gap_ms=guard_gap_ms,
            next_is_final=index + 2 == len(cues),
        )
        cue_signature = _cue_signature(
            cue,
            voice,
            settings.kokoro_lang_code,
            settings.kokoro_repo_id,
            window_start,
            window_end,
            base_speed,
            settings.max_kokoro_speed,
            settings.max_tempo_compression_ratio,
            settings.max_cue_shift_seconds,
            timeline_signature,
        )
        cue_signatures[cue.index] = cue_signature
        if progress_callback is not None:
            progress_callback(
                f"Rendering cue {index + 1}/{len(cues)}...",
                completed=index + 1,
                total=total_steps,
            )

        cached_result = _load_cached_result(
            cue=cue,
            cue_signature=cue_signature,
            progress_payload=progress_payload,
        )
        if cached_result is not None:
            logger.info("Reusing rendered cue %s from checkpoint", cue.index + 1)
            results.append(cached_result)
            speed_positions[cue.index] = min(
                range(len(speed_steps)),
                key=lambda position: abs(
                    speed_steps[position] - cached_result.applied_speed
                ),
            )
            continue

        result = synth.synthesize_cue(
            cue=cue,
            output_path=segment_dir / f"cue_{cue.index:04}.wav",
            speed=base_speed,
        )
        results.append(result)
        _save_cached_result(
            progress_path=progress_path,
            progress_payload=progress_payload,
            cue=cue,
            cue_signature=cue_signature,
            result=result,
        )

    placement_starts, conflict_position = plan_quality_constrained_placements(
        cues,
        results,
        total_duration=total_duration,
        guard_gap_seconds=guard_gap_ms / 1000,
        max_shift_seconds=settings.max_cue_shift_seconds,
    )

    compressed_positions = {
        position
        for position, result in enumerate(results)
        if result.time_compression_ratio > 1.0 + 1e-6
    }
    while placement_starts is None and conflict_position is not None:
        adjustment = next_quality_adjustment(
            conflict_position=conflict_position,
            cue_indexes=[cue.index for cue in cues],
            durations=[result.duration_seconds for result in results],
            speed_positions=speed_positions,
            speed_step_count=len(speed_steps),
            compressed_positions=compressed_positions,
        )
        if adjustment is None:
            break
        adjustment_type, position = adjustment
        cue = cues[position]
        if adjustment_type == "speed":
            # Regeneration replaces any previously tempo-compressed file, so
            # this cue may use its one bounded compression pass again.
            compressed_positions.discard(position)
            speed_positions[cue.index] += 1
            speed = speed_steps[speed_positions[cue.index]]
            if progress_callback is not None:
                progress_callback(
                    f"Resolving timing conflict near cue {conflict_position + 1}: testing cue {cue.index + 1} "
                    f"at {speed:.2f}×..."
                )
            results[position] = synth.synthesize_cue(
                cue=cue,
                output_path=segment_dir / f"cue_{cue.index:04}.wav",
                speed=speed,
            )
        else:
            compressed_positions.add(position)
            result = results[position]
            if progress_callback is not None:
                progress_callback(
                    f"Applying limited tempo adjustment to cue {cue.index + 1}..."
                )
            compressed = synth.compress_to_duration(
                result=result,
                target_duration_seconds=result.duration_seconds
                / settings.max_tempo_compression_ratio,
                max_compression_ratio=settings.max_tempo_compression_ratio,
            )
            if compressed is not None:
                results[position] = compressed
        _save_cached_result(
            progress_path=progress_path,
            progress_payload=progress_payload,
            cue=cue,
            cue_signature=cue_signatures[cue.index],
            result=results[position],
        )
        placement_starts, conflict_position = plan_quality_constrained_placements(
            cues,
            results,
            total_duration=total_duration,
            guard_gap_seconds=guard_gap_ms / 1000,
            max_shift_seconds=settings.max_cue_shift_seconds,
        )

    if placement_starts is None:
        failed_position = conflict_position or 0
        failed_cue = cues[failed_position]
        raise RuntimeError(
            _build_quality_failure_message(
                cue=failed_cue,
                result=results[failed_position],
                max_speed=settings.max_kokoro_speed,
                max_compression=settings.max_tempo_compression_ratio,
                max_shift=settings.max_cue_shift_seconds,
            )
        )

    for position, (cue, result) in enumerate(zip(cues, results, strict=True)):
        window_start, window_end = _render_window_for_cue(
            cue=cue,
            previous_cue=cues[position - 1] if position > 0 else None,
            next_cue=cues[position + 1] if position + 1 < len(cues) else None,
            total_duration=total_duration,
            guard_gap_ms=guard_gap_ms,
            next_is_final=position + 2 == len(cues),
        )
        _save_cached_result(
            progress_path=progress_path,
            progress_payload=progress_payload,
            cue=cue,
            cue_signature=_cue_signature(
                cue,
                voice,
                settings.kokoro_lang_code,
                settings.kokoro_repo_id,
                window_start,
                window_end,
                base_speed,
                settings.max_kokoro_speed,
                settings.max_tempo_compression_ratio,
                settings.max_cue_shift_seconds,
                timeline_signature,
            ),
            result=result.model_copy(update={"fitted": True}),
        )

    narration_path = output_dir / "narration.wav"
    if progress_callback is not None:
        progress_callback(
            "Assembling narration timeline...",
            completed=len(cues) + 1,
            total=total_steps,
        )
    assembler.assemble(
        cues,
        results,
        narration_path,
        total_duration=total_duration,
        placement_starts=placement_starts,
    )

    return existing_artifacts.model_copy(update={"narration_wav": narration_path})


def _render_downloads(artifacts: RenderArtifacts) -> None:
    st.markdown("**Downloads**")

    download_items = [
        ("Download SRT", artifacts.subtitled_srt),
        ("Download TXT", artifacts.transcript_txt),
        ("Download Narration WAV", artifacts.narration_wav),
        ("Download MP4", artifacts.muxed_video),
    ]
    available_items = [
        (label, path)
        for label, path in download_items
        if path is not None and path.exists()
    ]
    if not available_items:
        return

    columns = st.columns(len(available_items))
    for column, (label, path) in zip(columns, available_items, strict=False):
        if path is None or not path.exists():
            continue
        mime = _mime_type_for_path(path)
        with column, path.open("rb") as file_handle:
            st.download_button(
                label=label,
                data=file_handle,
                file_name=path.name,
                mime=mime,
                use_container_width=True,
            )


def _mime_type_for_path(path: Path) -> str:
    if path.suffix == ".srt":
        return "application/x-subrip"
    if path.suffix == ".txt":
        return "text/plain"
    if path.suffix == ".wav":
        return "audio/wav"
    if path.suffix == ".mp4":
        return "video/mp4"
    return "application/octet-stream"


def _save_artifacts(artifacts: RenderArtifacts) -> None:
    st.session_state["artifacts"] = artifacts.model_dump(mode="json")


def _clear_render_artifacts() -> None:
    st.session_state["artifacts"] = {}


def _reset_workflow() -> None:
    for key in [
        "current_project_id",
        "source_video",
        "uploaded_filename",
        "uploaded_file_token",
        "transcription_mode",
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


def _render_window_for_cue(
    cue: Cue,
    previous_cue: Cue | None,
    next_cue: Cue | None,
    total_duration: float,
    guard_gap_ms: int,
    next_is_final: bool = False,
) -> tuple[float, float]:
    if next_cue is not None:
        if next_is_final:
            return cue.start_seconds, _final_cue_window_start(
                next_cue, cue, guard_gap_ms
            )
        return cue.start_seconds, next_cue.start_seconds

    if previous_cue is None:
        start_seconds = 0.0
    else:
        start_seconds = _final_cue_window_start(cue, previous_cue, guard_gap_ms)
    end_seconds = max(cue.end_seconds, total_duration)
    return max(0.0, start_seconds), end_seconds


def _final_cue_window_start(cue: Cue, previous_cue: Cue, guard_gap_ms: int) -> float:
    earliest_after_previous = previous_cue.end_seconds + (guard_gap_ms / 1000)
    return max(0.0, min(cue.start_seconds, earliest_after_previous))


def _timeline_signature(
    cues: list[Cue], total_duration: float, settings: Settings
) -> str:
    payload = {
        "algorithm": "quality-constrained-v2",
        "cues": [
            {
                "index": cue.index,
                "text": cue.text,
                "start_seconds": cue.start_seconds,
                "end_seconds": cue.end_seconds,
            }
            for cue in cues
        ],
        "total_duration": total_duration,
        "base_speed": settings.kokoro_speed,
        "max_speed": settings.max_kokoro_speed,
        "max_compression": settings.max_tempo_compression_ratio,
        "max_shift": settings.max_cue_shift_seconds,
        "guard_gap_ms": settings.guard_gap_ms,
    }
    serialized = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _cue_signature(
    cue: Cue,
    voice: str,
    lang_code: str,
    repo_id: str,
    window_start: float,
    window_end: float,
    base_speed: float,
    max_speed: float,
    max_compression: float,
    max_shift: float,
    timeline_signature: str,
) -> str:
    payload = json.dumps(
        {
            "index": cue.index,
            "text": cue.text,
            "start_seconds": cue.start_seconds,
            "end_seconds": cue.end_seconds,
            "render_window_start": window_start,
            "render_window_end": window_end,
            "voice": voice,
            "lang_code": lang_code,
            "repo_id": repo_id,
            "base_speed": base_speed,
            "max_speed": max_speed,
            "max_compression": max_compression,
            "max_shift": max_shift,
            "timeline_signature": timeline_signature,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_progress(progress_path: Path) -> dict:
    if not progress_path.exists():
        return {"cues": {}}

    try:
        return json.loads(progress_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Ignoring unreadable render progress file at %s", progress_path)
        return {"cues": {}}


def _load_cached_result(
    cue: Cue,
    cue_signature: str,
    progress_payload: dict,
) -> SynthesisResult | None:
    cue_payload = progress_payload.get("cues", {}).get(str(cue.index))
    if not cue_payload:
        return None
    if cue_payload.get("signature") != cue_signature:
        return None

    audio_path = Path(cue_payload.get("audio_path", ""))
    if not audio_path.exists():
        return None

    cached_result = {
        "cue_index": cue.index,
        "audio_path": audio_path,
        "duration_seconds": float(cue_payload.get("duration_seconds", 0.0)),
        "fitted": bool(cue_payload.get("fitted", False)),
        "applied_speed": float(cue_payload.get("applied_speed", 1.0)),
        "time_compression_ratio": float(cue_payload.get("time_compression_ratio", 1.0)),
    }
    return SynthesisResult(**cached_result)


def _save_cached_result(
    progress_path: Path,
    progress_payload: dict,
    cue: Cue,
    cue_signature: str,
    result: SynthesisResult,
) -> None:
    cues_payload = progress_payload.setdefault("cues", {})
    cues_payload[str(cue.index)] = {
        "signature": cue_signature,
        "audio_path": str(result.audio_path),
        "duration_seconds": result.duration_seconds,
        "fitted": result.fitted,
        "applied_speed": result.applied_speed,
        "time_compression_ratio": result.time_compression_ratio,
    }
    atomic_write_json(progress_path, progress_payload)


def _build_quality_failure_message(
    cue: Cue,
    result: SynthesisResult,
    max_speed: float,
    max_compression: float,
    max_shift: float,
) -> str:
    return (
        f"Cue {cue.index + 1} cannot fit naturally near its timestamp. Its best quality-constrained audio is "
        f"{result.duration_seconds:.2f}s at {result.applied_speed:.2f}× Kokoro speed and "
        f"{result.time_compression_ratio:.2f}× tempo compression. The renderer capped Kokoro at {max_speed:.2f}×, "
        f"tempo compression at {max_compression:.2f}×, and timestamp movement at ±{max_shift:.2f}s to prevent "
        "robotic speech. Shorten or redistribute this cue, test it again, and rerender."
    )
