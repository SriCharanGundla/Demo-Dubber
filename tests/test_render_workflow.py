import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from demo_dubber.config import Settings
from demo_dubber.models import Cue, RenderArtifacts
from demo_dubber.services.render_workflow import RenderWorkflow


class _FakeFFmpeg:
    def __init__(self) -> None:
        self.muxed: tuple[Path, Path, Path] | None = None

    def mux_audio(self, video_path: Path, audio_path: Path, output_path: Path) -> Path:
        output_path.write_bytes(b"video")
        self.muxed = (video_path, audio_path, output_path)
        return output_path


class RenderWorkflowTests(unittest.TestCase):
    def test_export_narration_and_mux_are_orchestrated_without_streamlit(self) -> None:
        cue = Cue(
            index=0, start_seconds=0, end_seconds=1, text="Hello", original_text="Hello"
        )
        ffmpeg = _FakeFFmpeg()

        def generate_narration(**kwargs) -> RenderArtifacts:
            narration_path = kwargs["output_dir"] / "narration.wav"
            narration_path.write_bytes(b"audio")
            return kwargs["existing_artifacts"].model_copy(
                update={"narration_wav": narration_path}
            )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = RenderWorkflow(
                settings=Settings(),
                ffmpeg=ffmpeg,
                narration_generator=generate_narration,
            )
            artifacts = workflow.run(
                cues=[cue],
                media_asset={"duration_seconds": 1.0},
                output_dir=root,
                source_video=root / "source.mp4",
                existing_artifacts=RenderArtifacts(),
            )
            self.assertTrue(artifacts.subtitled_srt.exists())
            self.assertTrue(artifacts.transcript_txt.exists())
            self.assertTrue(artifacts.narration_wav.exists())
            self.assertTrue(artifacts.muxed_video.exists())
            self.assertIsNotNone(ffmpeg.muxed)


if __name__ == "__main__":
    unittest.main()
