from __future__ import annotations

from pathlib import Path
from typing import Any

from openai import OpenAI

from demo_dubber.models import Cue, Transcript
from demo_dubber.services.transcript_validation import validate_transcript_timeline

DIARIZATION_MODEL = "gpt-4o-transcribe-diarize"


class OpenAITranscriptionService:
    def __init__(self, api_key: str | None, model: str = "whisper-1") -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key) if api_key else None

    def transcribe_with_timestamps(self, audio_path: Path) -> Transcript:
        if self._client is None:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        with audio_path.open("rb") as audio_file:
            response = self._create_transcription(audio_file)

        raw = response.model_dump()
        segments = self._extract_segments(response, raw)
        cues: list[Cue] = []
        for segment in segments:
            if segment is None:
                continue
            text = (segment.get("text") or "").strip()
            if not text:
                continue
            cues.append(
                Cue(
                    index=len(cues),
                    start_seconds=float(segment.get("start", 0.0)),
                    end_seconds=float(segment.get("end", 0.0)),
                    text=text,
                    original_text=text,
                    speaker=self._normalize_speaker(segment.get("speaker")),
                    word_count=len(text.split()),
                )
            )

        if not cues:
            raise RuntimeError(
                "OpenAI returned no timestamped segments for this transcript."
            )
        return validate_transcript_timeline(Transcript(cues=cues, raw_response=raw))

    def _create_transcription(self, audio_file):
        if self._model == "whisper-1":
            return self._client.audio.transcriptions.create(
                file=audio_file,
                model=self._model,
                response_format="verbose_json",
                timestamp_granularities=["segment", "word"],
            )

        if self._model == DIARIZATION_MODEL:
            return self._client.audio.transcriptions.create(
                file=audio_file,
                model=self._model,
                response_format="diarized_json",
                chunking_strategy="auto",
            )

        raise RuntimeError(
            f"Transcription model '{self._model}' is not supported by this app. "
            "Use 'whisper-1' or 'gpt-4o-transcribe-diarize'."
        )

    def _extract_segments(
        self, response: Any, raw: dict[str, Any]
    ) -> list[dict[str, Any]]:
        raw_segments = raw.get("segments")
        if raw_segments:
            return [segment for segment in raw_segments if segment]

        response_segments = getattr(response, "segments", None)
        if response_segments:
            normalized = []
            for segment in response_segments:
                if segment is None:
                    continue
                if hasattr(segment, "model_dump"):
                    normalized.append(segment.model_dump())
                elif isinstance(segment, dict):
                    normalized.append(segment)
            if normalized:
                return normalized

        words = raw.get("words") or []
        if words:
            text = " ".join((word.get("word") or "").strip() for word in words).strip()
            if text:
                return [
                    {
                        "start": float(words[0].get("start", 0.0)),
                        "end": float(words[-1].get("end", 0.0)),
                        "text": text,
                    }
                ]

        return []

    def _normalize_speaker(self, speaker: Any) -> str | None:
        if speaker in (None, ""):
            return None
        return str(speaker).strip() or None
