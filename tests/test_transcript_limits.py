from __future__ import annotations

import unittest

from demo_dubber.models import Cue, Transcript
from demo_dubber.services.transcript_limits import apply_char_limits


class TranscriptLimitTests(unittest.TestCase):
    def test_every_cue_limit_uses_available_timeline(self) -> None:
        transcript = Transcript(
            cues=[
                Cue(
                    index=0,
                    start_seconds=0,
                    end_seconds=1,
                    text="First",
                    original_text="First",
                ),
                Cue(
                    index=1,
                    start_seconds=2,
                    end_seconds=4,
                    text="Second",
                    original_text="Second",
                ),
            ]
        )

        limited = apply_char_limits(
            transcript,
            margin=0,
            media_duration_seconds=5,
            chars_per_second=10,
            guard_gap_ms=100,
        )

        self.assertEqual([cue.char_limit for cue in limited.cues], [19, 29])


if __name__ == "__main__":
    unittest.main()
