from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from pydantic import BaseModel

from demo_dubber.config import Settings
from demo_dubber.models import Cue, SynthesisResult
from demo_dubber.services.cue_fit import duration_matched_speed, quality_speed_steps
from demo_dubber.services.kokoro_synthesize import KokoroSynthesisService
from demo_dubber.utils.files import atomic_write_json, ensure_directories


class CueTTSPreview(BaseModel):
    signature: str
    audio_path: Path
    natural_audio_path: Path
    duration_seconds: float
    natural_duration_seconds: float
    available_seconds: float
    fitted: bool
    applied_speed: float
    time_compression_ratio: float
    voice: str


def available_tts_seconds(
    cues: list[Cue],
    position: int,
    *,
    media_duration_seconds: float,
    guard_gap_ms: int,
) -> float:
    cue = cues[position]
    gap_seconds = guard_gap_ms / 1000
    start_seconds = cue.start_seconds
    if position + 1 < len(cues):
        next_cue = cues[position + 1]
        if position + 2 == len(cues):
            end_seconds = _final_cue_window_start(next_cue, cue, gap_seconds)
        else:
            end_seconds = next_cue.start_seconds
    else:
        if position > 0:
            start_seconds = _final_cue_window_start(
                cue, cues[position - 1], gap_seconds
            )
        else:
            start_seconds = 0.0
        end_seconds = max(cue.end_seconds, media_duration_seconds)
    return max(0.0, end_seconds - start_seconds - gap_seconds)


def generate_tts_preview(
    *,
    project_id: str,
    output_dir: Path,
    cue: Cue,
    available_seconds: float,
    settings: Settings,
    voice: str,
    speed: float,
) -> CueTTSPreview:
    signature = _tts_signature(
        project_id=project_id,
        cue=cue,
        available_seconds=available_seconds,
        settings=settings,
        voice=voice,
        speed=speed,
    )
    preview_root = output_dir / "editor_previews" / "tts"
    ensure_directories(preview_root)
    stem = f"cue_{cue.index:04}_{signature[:24]}"
    natural_path = preview_root / f"{stem}_natural.wav"
    output_path = preview_root / f"{stem}.wav"
    metadata_path = preview_root / f"{stem}.json"

    cached = _load_cached_preview(metadata_path)
    if (
        cached is not None
        and cached.signature == signature
        and cached.audio_path.is_file()
        and cached.natural_audio_path.is_file()
    ):
        return cached

    synth = KokoroSynthesisService(
        voice=voice,
        lang_code=settings.kokoro_lang_code,
        repo_id=settings.kokoro_repo_id,
        base_speed=speed,
        sample_rate=settings.sample_rate,
    )
    natural_result = synth.synthesize_cue(
        cue=cue, output_path=natural_path, speed=speed
    )
    shutil.copyfile(natural_path, output_path)
    result: SynthesisResult = natural_result.model_copy(
        update={"audio_path": output_path}
    )
    matched_speed = duration_matched_speed(
        speed,
        settings.min_kokoro_speed,
        natural_result.duration_seconds,
        min(cue.duration_seconds, available_seconds),
    )
    if matched_speed < speed - 1e-6:
        result = synth.synthesize_cue(
            cue=cue, output_path=output_path, speed=matched_speed
        )
    for candidate_speed in quality_speed_steps(
        result.applied_speed, settings.max_kokoro_speed
    ):
        if abs(candidate_speed - result.applied_speed) > 1e-6:
            result = synth.synthesize_cue(
                cue=cue, output_path=output_path, speed=candidate_speed
            )
        result = result.model_copy(
            update={"fitted": result.duration_seconds <= available_seconds}
        )
        if result.fitted:
            break

    if not result.fitted:
        compressed = synth.compress_to_duration(
            result=result,
            target_duration_seconds=available_seconds,
            max_compression_ratio=settings.max_tempo_compression_ratio,
        )
        if compressed is not None:
            result = compressed

    preview = CueTTSPreview(
        signature=signature,
        audio_path=result.audio_path,
        natural_audio_path=natural_result.audio_path,
        duration_seconds=result.duration_seconds,
        natural_duration_seconds=natural_result.duration_seconds,
        available_seconds=available_seconds,
        fitted=result.fitted,
        applied_speed=result.applied_speed,
        time_compression_ratio=result.time_compression_ratio,
        voice=voice,
    )
    atomic_write_json(metadata_path, preview.model_dump(mode="json"))
    return preview


def load_tts_preview(
    output_dir: Path, cue_index: int, signature: str
) -> CueTTSPreview | None:
    if len(signature) != 64 or any(
        char not in "0123456789abcdef" for char in signature
    ):
        return None
    stem = f"cue_{cue_index:04}_{signature[:24]}"
    return _load_cached_preview(output_dir / "editor_previews" / "tts" / f"{stem}.json")


def _load_cached_preview(metadata_path: Path) -> CueTTSPreview | None:
    if not metadata_path.is_file():
        return None
    try:
        return CueTTSPreview.model_validate_json(metadata_path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _final_cue_window_start(cue: Cue, previous_cue: Cue, gap_seconds: float) -> float:
    earliest_after_previous = previous_cue.end_seconds + gap_seconds
    return max(0.0, min(cue.start_seconds, earliest_after_previous))


def _tts_signature(
    *,
    project_id: str,
    cue: Cue,
    available_seconds: float,
    settings: Settings,
    voice: str,
    speed: float,
) -> str:
    payload = json.dumps(
        {
            "project_id": project_id,
            "cue_index": cue.index,
            "text": cue.text,
            "available_seconds": available_seconds,
            "voice": voice,
            "speed": speed,
            "max_speed": settings.max_kokoro_speed,
            "min_speed": settings.min_kokoro_speed,
            "lang_code": settings.kokoro_lang_code,
            "repo_id": settings.kokoro_repo_id,
            "max_compression_ratio": settings.max_tempo_compression_ratio,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
