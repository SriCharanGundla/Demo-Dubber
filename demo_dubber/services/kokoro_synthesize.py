from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from kokoro import KPipeline

from demo_dubber.models import Cue, SynthesisResult

logger = logging.getLogger(__name__)


class KokoroSynthesisService:
    def __init__(
        self,
        voice: str,
        lang_code: str,
        repo_id: str,
        base_speed: float,
        sample_rate: int,
    ) -> None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._pipeline = _get_pipeline(
            lang_code=lang_code, repo_id=repo_id, device=device
        )
        self._voice = voice
        self._base_speed = base_speed
        self._sample_rate = sample_rate

    def synthesize_cue(
        self, cue: Cue, output_path: Path, speed: float | None = None
    ) -> SynthesisResult:
        applied_speed = speed if speed is not None else self._base_speed
        if not cue.text.strip():
            return self._render_silent_cue(cue, output_path, applied_speed)

        segments = list(
            self._pipeline(cue.text, voice=self._voice, speed=applied_speed)
        )
        if not segments:
            raise RuntimeError(f"Kokoro returned no audio for cue {cue.index}")

        audio_parts = [np.asarray(audio, dtype=np.float32) for _, _, audio in segments]
        full_audio = np.concatenate(audio_parts)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_wav_atomic(output_path, full_audio, self._sample_rate)

        duration = len(full_audio) / self._sample_rate
        return SynthesisResult(
            cue_index=cue.index,
            audio_path=output_path,
            duration_seconds=duration,
            fitted=duration <= cue.duration_seconds,
            applied_speed=applied_speed,
        )

    def _render_silent_cue(
        self, cue: Cue, output_path: Path, applied_speed: float
    ) -> SynthesisResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # One silent frame keeps the WAV valid while preserving an effectively empty cue.
        _write_wav_atomic(output_path, np.zeros(1, dtype=np.float32), self._sample_rate)
        return SynthesisResult(
            cue_index=cue.index,
            audio_path=output_path,
            duration_seconds=1 / self._sample_rate,
            fitted=True,
            applied_speed=applied_speed,
        )

    def compress_to_duration(
        self,
        result: SynthesisResult,
        target_duration_seconds: float,
        max_compression_ratio: float = 1.2,
    ) -> SynthesisResult | None:
        if target_duration_seconds <= 0:
            return None
        if result.duration_seconds <= target_duration_seconds:
            return result.model_copy(update={"fitted": True})

        required_ratio = result.duration_seconds / target_duration_seconds
        if required_ratio > max_compression_ratio:
            return None

        output_path = result.audio_path.with_name(f"{result.audio_path.stem}_tempo.wav")
        filter_chain = self._build_atempo_filter(required_ratio)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(result.audio_path),
            "-filter:a",
            filter_chain,
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        audio, sample_rate = sf.read(output_path, dtype="float32")
        actual_duration = len(audio) / sample_rate
        output_path.replace(result.audio_path)

        return result.model_copy(
            update={
                "duration_seconds": actual_duration,
                "fitted": actual_duration <= target_duration_seconds,
                "time_compression_ratio": required_ratio,
            }
        )

    def _build_atempo_filter(self, ratio: float) -> str:
        factors: list[float] = []
        remaining = ratio

        while remaining > 2.0:
            factors.append(2.0)
            remaining /= 2.0

        while remaining < 0.5:
            factors.append(0.5)
            remaining /= 0.5

        factors.append(remaining)
        return ",".join(f"atempo={factor:.5f}" for factor in factors)


@lru_cache(maxsize=4)
def _get_pipeline(lang_code: str, repo_id: str, device: str) -> KPipeline:
    logger.info("Initializing Kokoro pipeline on %s from %s", device, repo_id)
    return KPipeline(lang_code=lang_code, repo_id=repo_id, device=device)


def _write_wav_atomic(output_path: Path, audio: np.ndarray, sample_rate: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(suffix=".wav", dir=output_path.parent)
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        sf.write(temporary_path, audio, sample_rate)
        os.replace(temporary_path, output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
