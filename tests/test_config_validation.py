from __future__ import annotations

import unittest

from pydantic import ValidationError

from demo_dubber.config import Settings


class ConfigurationValidationTests(unittest.TestCase):
    def test_rejects_unsafe_timing_and_audio_values(self) -> None:
        invalid_updates = {
            "guard_gap_ms": -1,
            "chars_per_second": 0,
            "char_limit_margin": -1,
            "sample_rate": 0,
            "ffmpeg_timeout_seconds": 0,
        }
        for field, value in invalid_updates.items():
            with self.subTest(field=field), self.assertRaises(ValidationError):
                Settings(**{field: value})


if __name__ == "__main__":
    unittest.main()
