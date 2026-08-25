import unittest
from pathlib import Path

from demo_dubber.models import Cue, SynthesisResult
from demo_dubber.services.cue_fit import next_quality_adjustment, quality_speed_steps
from demo_dubber.services.timeline import plan_quality_constrained_placements


def cue(index: int, start: float, end: float) -> Cue:
    return Cue(
        index=index,
        start_seconds=start,
        end_seconds=end,
        text="test",
        original_text="test",
    )


def result(index: int, duration: float) -> SynthesisResult:
    return SynthesisResult(
        cue_index=index,
        audio_path=Path(f"cue-{index}.wav"),
        duration_seconds=duration,
        fitted=False,
        applied_speed=1.0,
    )


class QualityTimingTests(unittest.TestCase):
    def test_speed_steps_never_exceed_quality_cap(self) -> None:
        self.assertEqual(quality_speed_steps(1.0, 1.12), [1.0, 1.05, 1.1, 1.12])

    def test_scheduler_borrows_neighboring_slack(self) -> None:
        cues = [cue(0, 1.0, 2.0), cue(1, 3.0, 4.0)]
        placements, conflict = plan_quality_constrained_placements(
            cues,
            [result(0, 2.1), result(1, 0.8)],
            total_duration=5.0,
            guard_gap_seconds=0.1,
            max_shift_seconds=0.6,
        )
        self.assertIsNone(conflict)
        self.assertIsNotNone(placements)
        assert placements is not None
        self.assertGreaterEqual(placements[1] - placements[0], 2.2)

    def test_scheduler_reports_impossible_timeline(self) -> None:
        cues = [cue(0, 1.0, 2.0), cue(1, 2.2, 3.0)]
        placements, conflict = plan_quality_constrained_placements(
            cues,
            [result(0, 3.0), result(1, 2.0)],
            total_duration=4.0,
            guard_gap_seconds=0.1,
            max_shift_seconds=0.25,
        )
        self.assertIsNone(placements)
        self.assertEqual(conflict, 1)

    def test_scheduler_rejects_audio_longer_than_video(self) -> None:
        placements, conflict = plan_quality_constrained_placements(
            [cue(0, 1.0, 1.0)],
            [result(0, 2.0)],
            total_duration=1.0,
            guard_gap_seconds=0.1,
            max_shift_seconds=2.0,
        )
        self.assertIsNone(placements)
        self.assertEqual(conflict, 0)

    def test_optimizer_returns_to_speed_after_compression_reveals_later_conflict(
        self,
    ) -> None:
        speed_positions = {0: 2, 1: 0}
        compressed_positions: set[int] = set()
        first = next_quality_adjustment(
            conflict_position=0,
            cue_indexes=[0, 1],
            durations=[4.0, 3.0],
            speed_positions=speed_positions,
            speed_step_count=3,
            compressed_positions=compressed_positions,
        )
        self.assertEqual(first, ("compress", 0))

        compressed_positions.add(0)
        second = next_quality_adjustment(
            conflict_position=1,
            cue_indexes=[0, 1],
            durations=[3.7, 3.0],
            speed_positions=speed_positions,
            speed_step_count=3,
            compressed_positions=compressed_positions,
        )
        self.assertEqual(second, ("speed", 1))


if __name__ == "__main__":
    unittest.main()
