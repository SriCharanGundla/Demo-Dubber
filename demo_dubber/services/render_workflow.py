from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from demo_dubber.config import Settings
from demo_dubber.models import Cue, RenderArtifacts
from demo_dubber.services.export import export_srt, export_text
from demo_dubber.services.ffmpeg import FFmpegService

ProgressCallback = Callable[[str, int | None, int | None], None]
NarrationGenerator = Callable[..., RenderArtifacts]


class RenderWorkflow:
    """Framework-independent export, narration, and mux orchestration."""

    def __init__(
        self,
        *,
        settings: Settings,
        ffmpeg: FFmpegService,
        narration_generator: NarrationGenerator,
    ) -> None:
        self._settings = settings
        self._ffmpeg = ffmpeg
        self._narration_generator = narration_generator

    def run(
        self,
        *,
        cues: list[Cue],
        media_asset: dict,
        output_dir: Path,
        source_video: Path,
        existing_artifacts: RenderArtifacts,
        progress_callback: ProgressCallback | None = None,
    ) -> RenderArtifacts:
        total_steps = max(1, len(cues) + 3)
        if progress_callback is not None:
            progress_callback("Exporting transcript assets...", 0, total_steps)

        artifacts = existing_artifacts.model_copy(
            update={
                "subtitled_srt": export_srt(cues, output_dir / "transcript.srt"),
                "transcript_txt": export_text(cues, output_dir / "transcript.txt"),
            }
        )
        artifacts = self._narration_generator(
            cues=cues,
            media_asset=media_asset,
            settings=self._settings,
            output_dir=output_dir,
            voice=self._settings.kokoro_voice,
            base_speed=self._settings.kokoro_speed,
            guard_gap_ms=self._settings.guard_gap_ms,
            existing_artifacts=artifacts,
            progress_callback=progress_callback,
        )
        if artifacts.narration_wav is None:
            raise RuntimeError("Narration generation did not produce a WAV file.")

        muxed_path = output_dir / f"{source_video.stem}-dubbed.mp4"
        if progress_callback is not None:
            progress_callback(
                f"Muxing final video into {muxed_path.name}...",
                len(cues) + 2,
                total_steps,
            )
        self._ffmpeg.mux_audio(source_video, artifacts.narration_wav, muxed_path)
        return artifacts.model_copy(update={"muxed_video": muxed_path})
