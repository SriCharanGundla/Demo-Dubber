import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from demo_dubber.services.ffmpeg import FFmpegService


class FFmpegServiceTests(unittest.TestCase):
    @patch("demo_dubber.services.ffmpeg.subprocess.run")
    def test_mux_copies_source_video_without_shortening_it(self, run: Mock) -> None:
        service = FFmpegService()
        service.mux_audio(
            Path("source.webm"), Path("narration.wav"), Path("dubbed.mp4")
        )
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-c:v") + 1], "copy")
        self.assertNotIn("-shortest", command)
        self.assertIn("-map_metadata", command)
        self.assertIn("+faststart", command)

    @patch("demo_dubber.services.ffmpeg.subprocess.run")
    def test_mux_uses_high_quality_fallback_for_incompatible_codec(
        self, run: Mock
    ) -> None:
        run.side_effect = [
            subprocess.CalledProcessError(1, ["ffmpeg"]),
            Mock(),
        ]
        service = FFmpegService()
        service.mux_audio(Path("source.mp4"), Path("narration.wav"), Path("dubbed.mp4"))
        self.assertEqual(run.call_count, 2)
        fallback = run.call_args.args[0]
        self.assertEqual(fallback[fallback.index("-c:v") + 1], "libx264")
        self.assertEqual(fallback[fallback.index("-crf") + 1], "17")
        self.assertEqual(fallback[fallback.index("-preset") + 1], "slow")


if __name__ == "__main__":
    unittest.main()
