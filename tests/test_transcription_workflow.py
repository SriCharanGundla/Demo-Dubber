import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from demo_dubber.models import Cue, MediaAsset, Transcript
from demo_dubber.services.transcription_workflow import TranscriptionWorkflow


class _FakeFFmpeg:
    def probe_video(self, video_path: Path) -> MediaAsset:
        return MediaAsset(source_video=video_path, duration_seconds=12.0)

    def extract_audio(self, video_path: Path, audio_path: Path) -> Path:
        audio_path.write_bytes(b"audio")
        return audio_path

    def extract_audio_clip(
        self,
        audio_path: Path,
        output_path: Path,
        start_seconds: float,
        duration_seconds: float,
    ) -> Path:
        output_path.write_text(f"{start_seconds}:{duration_seconds}")
        return output_path


class _FakeTranscriber:
    def transcribe_with_timestamps(self, audio_path: Path) -> Transcript:
        return Transcript(
            cues=[
                Cue(
                    index=0,
                    start_seconds=1,
                    end_seconds=2,
                    text=audio_path.stem,
                    original_text=audio_path.stem,
                )
            ]
        )


class _IdentityCleaner:
    def clean_timestamped_transcript(self, transcript: Transcript) -> Transcript:
        return transcript


class TranscriptionWorkflowTests(unittest.TestCase):
    def test_short_audio_reports_distinct_processing_phases(self) -> None:
        updates: list[tuple[str, int | None, int | None]] = []
        workflow = TranscriptionWorkflow(
            ffmpeg=_FakeFFmpeg(),
            transcriber=_FakeTranscriber(),
            cleaner=_IdentityCleaner(),
            progress_callback=lambda message, completed, total: updates.append(
                (message, completed, total)
            ),
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            workflow.run(root / "video.mp4", root)

        self.assertEqual(
            updates,
            [
                ("Preparing audio", 0, 4),
                ("Transcribing audio", 1, 4),
                ("Cleaning transcript", 2, 4),
                ("Validating transcript", 3, 4),
                ("Transcript ready", 4, 4),
            ],
        )

    def test_long_audio_is_chunked_offset_and_renumbered(self) -> None:
        workflow = TranscriptionWorkflow(
            ffmpeg=_FakeFFmpeg(),
            transcriber=_FakeTranscriber(),
            cleaner=_IdentityCleaner(),
            chunk_seconds=5,
            overlap_seconds=1,
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result = workflow.run(root / "video.mp4", root)
        self.assertEqual([cue.index for cue in result.transcript.cues], [0, 1, 2])
        self.assertEqual(
            [cue.start_seconds for cue in result.transcript.cues], [1.0, 5.0, 10.0]
        )
        self.assertTrue(result.transcript.raw_response["chunked"])


if __name__ == "__main__":
    unittest.main()
