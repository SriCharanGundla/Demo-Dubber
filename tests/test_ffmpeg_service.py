import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from demo_dubber.services.ffmpeg import FFmpegService


class FFmpegServiceTests(unittest.TestCase):
    @patch("demo_dubber.services.ffmpeg.subprocess.run")
    def test_mux_transcodes_non_h264_video(self, run: Mock) -> None:
        service = FFmpegService()
        service.probe_video_codec = Mock(return_value="vp9")
        service.mux_audio(
            Path("source.webm"), Path("narration.wav"), Path("dubbed.mp4")
        )
        command = run.call_args.args[0]
        self.assertIn("libx264", command)
        self.assertIn("+faststart", command)

    @patch("demo_dubber.services.ffmpeg.subprocess.run")
    def test_mux_copies_h264_video(self, run: Mock) -> None:
        service = FFmpegService()
        service.probe_video_codec = Mock(return_value="h264")
        service.mux_audio(Path("source.mp4"), Path("narration.wav"), Path("dubbed.mp4"))
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-c:v") + 1], "copy")


if __name__ == "__main__":
    unittest.main()
