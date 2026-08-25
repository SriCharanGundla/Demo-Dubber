from __future__ import annotations

from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel

from demo_dubber.models import Cue, Transcript
from demo_dubber.services.transcript_validation import validate_transcript_timeline


class LocalWhisperTranscriptionService:
    def __init__(
        self,
        model: str = "medium.en",
        device: str = "cpu",
        compute_type: str = "int8",
        beam_size: int = 5,
    ) -> None:
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._beam_size = beam_size
        self._model: WhisperModel | None = None

    def transcribe_with_timestamps(self, audio_path: Path) -> Transcript:
        model = self._get_model()
        segments, info = model.transcribe(
            str(audio_path),
            beam_size=self._beam_size,
            word_timestamps=True,
            language="en" if self._model_name.endswith(".en") else None,
        )

        raw_segments: list[dict[str, Any]] = []
        cues: list[Cue] = []
        for index, segment in enumerate(segments):
            text = (segment.text or "").strip()
            if not text:
                continue
            words = [
                {
                    "start": word.start,
                    "end": word.end,
                    "word": word.word,
                }
                for word in (segment.words or [])
            ]
            raw_segment = {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": text,
                "words": words,
            }
            raw_segments.append(raw_segment)
            cues.append(
                Cue(
                    index=len(cues),
                    start_seconds=raw_segment["start"],
                    end_seconds=raw_segment["end"],
                    text=text,
                    original_text=text,
                    word_count=len(text.split()),
                )
            )

        if not cues:
            raise RuntimeError(
                "Local Whisper returned no timestamped segments for this transcript."
            )

        raw_response = {
            "provider": "local-whisper",
            "model": self._model_name,
            "device": self._device,
            "compute_type": self._compute_type,
            "beam_size": self._beam_size,
            "language": getattr(info, "language", None),
            "language_probability": getattr(info, "language_probability", None),
            "duration": getattr(info, "duration", None),
            "segments": raw_segments,
        }
        return validate_transcript_timeline(
            Transcript(cues=cues, raw_response=raw_response)
        )

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )
        return self._model
