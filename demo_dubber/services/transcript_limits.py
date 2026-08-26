from __future__ import annotations

from demo_dubber.models import Cue, Transcript


def apply_char_limits(
    transcript: Transcript,
    margin: int,
    media_duration_seconds: float | None = None,
    chars_per_second: float | None = None,
    guard_gap_ms: int = 0,
) -> Transcript:
    updated = []
    for index, cue in enumerate(transcript.cues):
        next_cue = (
            transcript.cues[index + 1] if index + 1 < len(transcript.cues) else None
        )
        slot_end = (
            next_cue.start_seconds
            if next_cue is not None
            else media_duration_seconds or cue.end_seconds
        )
        if chars_per_second is None:
            original_text = cue.original_text or cue.text
            char_limit = max(1, len(original_text) + margin)
        else:
            usable_seconds = max(
                0.0, slot_end - cue.start_seconds - guard_gap_ms / 1000
            )
            char_limit = max(1, int(usable_seconds * chars_per_second) + margin)
        updated.append(
            cue.model_copy(
                update={
                    "char_limit": char_limit,
                    "over_limit": len(cue.text) > char_limit,
                }
            )
        )
    return transcript.model_copy(update={"cues": updated})


def expanded_final_char_limit(
    cues: list[Cue],
    media_duration_seconds: float | None,
    chars_per_second: float | None,
    margin: int,
    guard_gap_ms: int,
) -> int | None:
    if not cues or media_duration_seconds is None or chars_per_second is None:
        return None
    final_cue = cues[-1]
    guard_gap_seconds = guard_gap_ms / 1000
    start_seconds = (
        0.0
        if len(cues) == 1
        else min(final_cue.start_seconds, cues[-2].end_seconds + guard_gap_seconds)
    )
    end_seconds = max(final_cue.end_seconds, media_duration_seconds)
    usable_seconds = max(0.0, end_seconds - start_seconds - guard_gap_seconds)
    return max(1, int(usable_seconds * chars_per_second) + margin)
