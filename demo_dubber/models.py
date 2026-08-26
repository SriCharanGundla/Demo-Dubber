from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class MediaAsset(BaseModel):
    source_video: Path
    extracted_audio: Path | None = None
    compressed_audio: Path | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None


class Cue(BaseModel):
    index: int = Field(ge=0)
    start_seconds: float = Field(ge=0, allow_inf_nan=False)
    end_seconds: float = Field(gt=0, allow_inf_nan=False)
    text: str
    original_text: str
    speaker: str | None = None
    word_count: int = 0
    char_limit: int = 0
    over_limit: bool = False

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_seconds - self.start_seconds)


class Transcript(BaseModel):
    cues: list[Cue] = Field(default_factory=list)
    raw_response: dict = Field(default_factory=dict)


class SynthesisResult(BaseModel):
    cue_index: int
    audio_path: Path
    duration_seconds: float
    fitted: bool
    applied_speed: float
    time_compression_ratio: float = 1.0


class RenderArtifacts(BaseModel):
    narration_wav: Path | None = None
    subtitled_srt: Path | None = None
    transcript_txt: Path | None = None
    muxed_video: Path | None = None


class AppState(BaseModel):
    stage: str = "upload"
    error: str | None = None
