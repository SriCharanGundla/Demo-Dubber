from __future__ import annotations

import json
import subprocess
from pathlib import Path

from demo_dubber.models import MediaAsset


class FFmpegService:
    def probe_video(self, video_path: Path) -> MediaAsset:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout or "{}")
        duration = float(payload.get("format", {}).get("duration", 0.0))
        return MediaAsset(source_video=video_path, duration_seconds=duration)

    def extract_audio(self, video_path: Path, audio_path: Path) -> Path:
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(audio_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return audio_path

    def probe_video_codec(self, video_path: Path) -> str:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip().lower()

    def extract_audio_clip(
        self,
        audio_path: Path,
        output_path: Path,
        start_seconds: float,
        duration_seconds: float,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        safe_duration = max(0.1, duration_seconds)
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{max(0.0, start_seconds):.3f}",
            "-t",
            f"{safe_duration:.3f}",
            "-i",
            str(audio_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return output_path

    def extract_video_clip(
        self,
        video_path: Path,
        output_path: Path,
        start_seconds: float,
        duration_seconds: float,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        safe_duration = max(0.1, duration_seconds)
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{max(0.0, start_seconds):.3f}",
            "-t",
            f"{safe_duration:.3f}",
            "-i",
            str(video_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return output_path

    def mux_audio(self, video_path: Path, audio_path: Path, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        def command(video_args: list[str]) -> list[str]:
            return [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-map_metadata",
                "0",
                *video_args,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(output_path),
            ]

        try:
            # Preserve the source video bit-for-bit whenever its codec can be
            # carried by the MP4 output container.
            subprocess.run(
                command(["-c:v", "copy"]),
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError:
            # Use a visually lossless fallback only for incompatible codecs.
            subprocess.run(
                command(
                    [
                        "-c:v",
                        "libx264",
                        "-preset",
                        "slow",
                        "-crf",
                        "17",
                        "-pix_fmt",
                        "yuv420p",
                    ]
                ),
                check=True,
                capture_output=True,
                text=True,
            )
        return output_path
