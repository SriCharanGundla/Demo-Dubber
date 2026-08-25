from __future__ import annotations

import platform
from collections.abc import Callable
from pathlib import Path
from typing import Any

from demo_dubber.models import Cue, Transcript
from demo_dubber.services.transcript_validation import validate_transcript_timeline

MLXTranscribe = Callable[..., dict[str, Any]]


class MLXWhisperTranscriptionService:
    """Whisper transcription accelerated by MLX on Apple Silicon."""

    def __init__(
        self,
        model: str = "mlx-community/whisper-medium.en-mlx",
        transcribe: MLXTranscribe | None = None,
    ) -> None:
        self._model_name = model
        self._transcribe = transcribe

    def transcribe_with_timestamps(self, audio_path: Path) -> Transcript:
        transcribe = self._transcribe or self._load_transcriber()
        result = transcribe(
            str(audio_path),
            path_or_hf_repo=self._model_name,
            word_timestamps=True,
            language="en" if ".en" in self._model_name else None,
        )
        raw_segments = result.get("segments") or []
        cues: list[Cue] = []
        normalized_segments: list[dict[str, Any]] = []
        for segment in raw_segments:
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            words = [
                {
                    "start": float(word.get("start", 0.0)),
                    "end": float(word.get("end", 0.0)),
                    "word": str(word.get("word") or ""),
                    **(
                        {"probability": float(word["probability"])}
                        if word.get("probability") is not None
                        else {}
                    ),
                }
                for word in (segment.get("words") or [])
            ]
            normalized = {
                "start": float(segment.get("start", 0.0)),
                "end": float(segment.get("end", 0.0)),
                "text": text,
                "words": words,
            }
            normalized_segments.append(normalized)
            cues.append(
                Cue(
                    index=len(cues),
                    start_seconds=normalized["start"],
                    end_seconds=normalized["end"],
                    text=text,
                    original_text=text,
                    word_count=len(text.split()),
                )
            )

        if not cues:
            raise RuntimeError(
                "MLX Whisper returned no timestamped segments for this transcript."
            )

        return validate_transcript_timeline(
            Transcript(
                cues=cues,
                raw_response={
                    "provider": "mlx-whisper",
                    "model": self._model_name,
                    "device": "mps",
                    "language": result.get("language"),
                    "segments": normalized_segments,
                },
            )
        )

    def _load_transcriber(self) -> MLXTranscribe:
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise RuntimeError("MLX Whisper requires an Apple Silicon Mac.")
        try:
            import mlx_whisper
        except ImportError as exc:
            raise RuntimeError(
                "MLX Whisper is not installed. Run `uv sync` on Apple Silicon."
            ) from exc
        return mlx_whisper.transcribe
