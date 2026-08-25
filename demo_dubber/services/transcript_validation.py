from __future__ import annotations

from collections.abc import Sequence

from demo_dubber.models import Cue, Transcript

TIMESTAMP_TOLERANCE_SECONDS = 0.05


def validate_transcript_timeline(
    transcript: Transcript,
    *,
    total_duration: float | None = None,
) -> Transcript:
    """Validate cue identity and timestamp ordering at an ingestion boundary."""
    expected_indexes = list(range(len(transcript.cues)))
    actual_indexes = [cue.index for cue in transcript.cues]
    if actual_indexes != expected_indexes:
        raise ValueError(
            "Transcript cue indexes must be consecutive and start at zero."
        )

    previous_start = -1.0
    for cue in transcript.cues:
        if cue.start_seconds < 0:
            raise ValueError(
                f"Cue {cue.index + 1} starts before the beginning of the video."
            )
        if cue.end_seconds <= cue.start_seconds:
            raise ValueError(f"Cue {cue.index + 1} must end after it starts.")
        if cue.start_seconds + TIMESTAMP_TOLERANCE_SECONDS < previous_start:
            raise ValueError(f"Cue {cue.index + 1} starts before the previous cue.")
        if (
            total_duration is not None
            and cue.end_seconds > total_duration + TIMESTAMP_TOLERANCE_SECONDS
        ):
            raise ValueError(f"Cue {cue.index + 1} ends after the video duration.")
        previous_start = cue.start_seconds

    return transcript


def renumber_cues(cues: Sequence[Cue]) -> list[Cue]:
    return [cue.model_copy(update={"index": index}) for index, cue in enumerate(cues)]
