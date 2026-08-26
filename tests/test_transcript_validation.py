from __future__ import annotations

import unittest

from pydantic import ValidationError

from demo_dubber.models import Cue, Transcript
from demo_dubber.services.transcript_validation import validate_transcript_timeline


def cue(index: int, start: float, end: float) -> Cue:
    return Cue(
        index=index,
        start_seconds=start,
        end_seconds=end,
        text="Words",
        original_text="Words",
    )


class TranscriptValidationTests(unittest.TestCase):
    def test_rejects_overlapping_cues(self) -> None:
        transcript = Transcript(cues=[cue(0, 0, 2), cue(1, 1, 3)])

        with self.assertRaisesRegex(ValueError, "overlaps"):
            validate_transcript_timeline(transcript)

    def test_allows_small_timestamp_rounding_tolerance(self) -> None:
        transcript = Transcript(cues=[cue(0, 0, 2), cue(1, 1.96, 3)])
        self.assertIs(validate_transcript_timeline(transcript), transcript)

    def test_rejects_non_finite_timestamps(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                cue(0, value, 1)


if __name__ == "__main__":
    unittest.main()
