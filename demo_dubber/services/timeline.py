from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from demo_dubber.models import Cue, SynthesisResult


class TimelineAssembler:
    def __init__(self, sample_rate: int, guard_gap_ms: int) -> None:
        self._sample_rate = sample_rate
        self._guard_gap_seconds = guard_gap_ms / 1000

    def char_limit_for_cue(
        self, cue: Cue, next_cue: Cue | None, chars_per_second: float
    ) -> int:
        slot_end = next_cue.start_seconds if next_cue else cue.end_seconds
        usable_seconds = max(
            0.0, slot_end - cue.start_seconds - self._guard_gap_seconds
        )
        return max(1, int(usable_seconds * chars_per_second))

    def validate_fit(
        self, cue: Cue, result: SynthesisResult, next_cue: Cue | None
    ) -> bool:
        slot_end = next_cue.start_seconds if next_cue else cue.end_seconds
        usable_seconds = max(
            0.0, slot_end - cue.start_seconds - self._guard_gap_seconds
        )
        return result.duration_seconds <= usable_seconds

    def assemble(
        self,
        cues: list[Cue],
        results: list[SynthesisResult],
        output_path: Path,
        total_duration: float,
        placement_starts: dict[int, float] | None = None,
    ) -> Path:
        frame_count = int(total_duration * self._sample_rate)
        master = np.zeros(frame_count, dtype=np.float32)
        result_map = {result.cue_index: result for result in results}
        placement_starts = placement_starts or {}

        for cue in cues:
            result = result_map.get(cue.index)
            if result is None:
                continue
            audio, _ = sf.read(result.audio_path, dtype="float32")
            start_seconds = placement_starts.get(cue.index, cue.start_seconds)
            start_frame = int(start_seconds * self._sample_rate)
            end_frame = min(frame_count, start_frame + len(audio))
            clip = audio[: max(0, end_frame - start_frame)]
            master[start_frame:end_frame] += clip

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(output_path, master, self._sample_rate)
        return output_path


def plan_quality_constrained_placements(
    cues: list[Cue],
    results: list[SynthesisResult],
    total_duration: float,
    guard_gap_seconds: float,
    max_shift_seconds: float,
) -> tuple[dict[int, float] | None, int | None]:
    """Place narration near original starts while borrowing nearby timeline slack.

    Returns the first conflicting cue when the requested durations cannot be
    scheduled within the configured timestamp drift.
    """
    if not cues:
        return {}, None

    result_map = {result.cue_index: result for result in results}
    earliest: list[float] = []
    upper_bounds: list[float] = []

    for position, cue in enumerate(cues):
        result = result_map.get(cue.index)
        if result is None:
            return None, position

        lower = max(0.0, cue.start_seconds - max_shift_seconds)
        latest_end_aligned_start = total_duration - result.duration_seconds
        if latest_end_aligned_start < -1e-6:
            return None, position
        upper = min(
            cue.start_seconds + max_shift_seconds,
            max(0.0, latest_end_aligned_start),
        )
        if position == 0:
            start = lower
        else:
            previous = result_map[cues[position - 1].index]
            start = max(
                lower, earliest[-1] + previous.duration_seconds + guard_gap_seconds
            )
        if start > upper + 1e-6:
            return None, position
        earliest.append(start)
        upper_bounds.append(upper)

    placements = [0.0] * len(cues)
    for position in range(len(cues) - 1, -1, -1):
        cue = cues[position]
        latest = upper_bounds[position]
        if position + 1 < len(cues):
            result = result_map[cue.index]
            latest = min(
                latest,
                placements[position + 1] - guard_gap_seconds - result.duration_seconds,
            )
        placements[position] = max(earliest[position], min(cue.start_seconds, latest))

    return {cue.index: placements[position] for position, cue in enumerate(cues)}, None
