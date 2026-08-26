from __future__ import annotations


def duration_matched_speed(
    base_speed: float,
    min_speed: float,
    natural_duration_seconds: float,
    target_duration_seconds: float,
    tolerance: float = 0.05,
) -> float:
    """Choose a bounded Kokoro speed that fills a short original cue."""
    if target_duration_seconds <= 0 or natural_duration_seconds <= 0:
        return base_speed
    if natural_duration_seconds >= target_duration_seconds * (1 - tolerance):
        return base_speed
    estimated_speed = base_speed * (
        natural_duration_seconds / target_duration_seconds
    )
    return round(max(min_speed, min(base_speed, estimated_speed)), 4)


def quality_speed_steps(
    base_speed: float, max_speed: float, step: float = 0.05
) -> list[float]:
    safe_base = max(0.1, base_speed)
    safe_max = max(safe_base, max_speed)
    steps = [safe_base]
    candidate = safe_base + step
    while candidate < safe_max:
        steps.append(round(candidate, 4))
        candidate += step
    if safe_max > safe_base:
        steps.append(safe_max)
    return sorted(set(steps))


def next_quality_adjustment(
    conflict_position: int,
    cue_indexes: list[int],
    durations: list[float],
    speed_positions: dict[int, int],
    speed_step_count: int,
    compressed_positions: set[int],
) -> tuple[str, int] | None:
    relevant_positions = range(conflict_position + 1)
    speed_candidates = [
        position
        for position in relevant_positions
        if speed_positions[cue_indexes[position]] + 1 < speed_step_count
    ]
    if speed_candidates:
        return "speed", max(speed_candidates, key=durations.__getitem__)

    compression_candidates = [
        position
        for position in relevant_positions
        if position not in compressed_positions and durations[position] > 0.05
    ]
    if compression_candidates:
        return "compress", max(compression_candidates, key=durations.__getitem__)
    return None
