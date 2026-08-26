from __future__ import annotations

import unittest

from demo_dubber.models import Cue
from demo_dubber.services.cue_preview import available_tts_seconds


class CuePreviewTests(unittest.TestCase):
    def test_available_time_uses_next_cue_and_guard_gap(self) -> None:
        cues = [
            Cue(
                index=0,
                start_seconds=1,
                end_seconds=2,
                text="One",
                original_text="One",
            ),
            Cue(
                index=1,
                start_seconds=4,
                end_seconds=5,
                text="Two",
                original_text="Two",
            ),
            Cue(
                index=2,
                start_seconds=8,
                end_seconds=9,
                text="Three",
                original_text="Three",
            ),
        ]

        available = available_tts_seconds(
            cues,
            0,
            media_duration_seconds=10,
            guard_gap_ms=120,
        )

        self.assertAlmostEqual(available, 2.88)

    def test_final_cue_can_use_remaining_video_time(self) -> None:
        cues = [
            Cue(
                index=0,
                start_seconds=1,
                end_seconds=2,
                text="One",
                original_text="One",
            )
        ]

        available = available_tts_seconds(
            cues,
            0,
            media_duration_seconds=6,
            guard_gap_ms=100,
        )

        self.assertAlmostEqual(available, 5.9)


if __name__ == "__main__":
    unittest.main()
