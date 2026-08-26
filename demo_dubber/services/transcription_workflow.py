from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from demo_dubber.models import Cue, MediaAsset, Transcript
from demo_dubber.services.ffmpeg import FFmpegService
from demo_dubber.services.transcript_validation import (
    renumber_cues,
    validate_transcript_timeline,
)


class TimestampTranscriber(Protocol):
    def transcribe_with_timestamps(self, audio_path: Path) -> Transcript: ...


class TranscriptCleaner(Protocol):
    def clean_timestamped_transcript(self, transcript: Transcript) -> Transcript: ...


ProgressCallback = Callable[[str, int | None, int | None], None]


@dataclass(frozen=True)
class TranscriptionRun:
    media_asset: MediaAsset
    extracted_audio: Path
    transcript: Transcript


class TranscriptionWorkflow:
    """Framework-independent video transcription and cleanup orchestration."""

    def __init__(
        self,
        *,
        ffmpeg: FFmpegService,
        transcriber: TimestampTranscriber,
        cleaner: TranscriptCleaner,
        chunk_seconds: int = 600,
        overlap_seconds: float = 1.0,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self._ffmpeg = ffmpeg
        self._transcriber = transcriber
        self._cleaner = cleaner
        self._chunk_seconds = chunk_seconds
        self._overlap_seconds = overlap_seconds
        self._progress_callback = progress_callback

    def run(self, video_path: Path, output_dir: Path) -> TranscriptionRun:
        self._report_progress("Preparing audio", 0, 4)
        media_asset = self._ffmpeg.probe_video(video_path)
        audio_path = output_dir / f"{video_path.stem}.wav"
        self._ffmpeg.extract_audio(video_path, audio_path)
        duration = float(media_asset.duration_seconds or 0.0)

        if duration > self._chunk_seconds:
            self._report_progress("Transcribing and cleaning audio chunks", 1, 4)
            transcript = self._transcribe_chunked(audio_path, output_dir, duration)
        else:
            self._report_progress("Transcribing audio", 1, 4)
            raw_transcript = self._transcriber.transcribe_with_timestamps(audio_path)
            self._report_progress("Cleaning transcript", 2, 4)
            transcript = self._cleaner.clean_timestamped_transcript(raw_transcript)

        self._report_progress("Validating transcript", 3, 4)
        transcript = validate_transcript_timeline(
            transcript, total_duration=duration or None
        )
        self._report_progress("Transcript ready", 4, 4)
        return TranscriptionRun(
            media_asset=media_asset, extracted_audio=audio_path, transcript=transcript
        )

    def _report_progress(
        self, message: str, completed: int | None, total: int | None
    ) -> None:
        if self._progress_callback is not None:
            self._progress_callback(message, completed, total)

    def _transcribe_chunked(
        self, audio_path: Path, output_dir: Path, total_duration: float
    ) -> Transcript:
        chunk_dir = output_dir / "transcription_chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        combined_cues: list[Cue] = []
        raw_chunks: list[dict] = []
        nominal_start = 0.0
        chunk_number = 0

        while nominal_start < total_duration:
            nominal_end = min(total_duration, nominal_start + self._chunk_seconds)
            extraction_start = max(
                0.0, nominal_start - (self._overlap_seconds if chunk_number else 0.0)
            )
            extraction_end = min(
                total_duration,
                nominal_end
                + (self._overlap_seconds if nominal_end < total_duration else 0.0),
            )
            chunk_path = chunk_dir / f"chunk_{chunk_number:04}.wav"
            self._ffmpeg.extract_audio_clip(
                audio_path=audio_path,
                output_path=chunk_path,
                start_seconds=extraction_start,
                duration_seconds=extraction_end - extraction_start,
            )

            try:
                chunk_transcript = self._transcriber.transcribe_with_timestamps(
                    chunk_path
                )
            except RuntimeError as exc:
                if "no timestamped segments" not in str(exc).lower():
                    raise
            else:
                cleaned = self._cleaner.clean_timestamped_transcript(chunk_transcript)
                raw_chunks.append(cleaned.raw_response)
                for cue in cleaned.cues:
                    shifted = cue.model_copy(
                        update={
                            "start_seconds": cue.start_seconds + extraction_start,
                            "end_seconds": cue.end_seconds + extraction_start,
                        }
                    )
                    midpoint = (shifted.start_seconds + shifted.end_seconds) / 2
                    owns_midpoint = midpoint >= nominal_start and (
                        midpoint < nominal_end or nominal_end >= total_duration
                    )
                    if owns_midpoint:
                        combined_cues.append(shifted)

            nominal_start = nominal_end
            chunk_number += 1

        if not combined_cues:
            raise RuntimeError(
                "Transcription returned no timestamped segments across all audio chunks."
            )

        transcript = Transcript(
            cues=renumber_cues(combined_cues),
            raw_response={"provider_chunks": raw_chunks, "chunked": True},
        )
        return validate_transcript_timeline(transcript, total_duration=total_duration)
