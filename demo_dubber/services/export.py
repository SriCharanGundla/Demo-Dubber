from __future__ import annotations

from pathlib import Path

from demo_dubber.models import Cue
from demo_dubber.utils.srt import format_srt_timestamp


def export_srt(cues: list[Cue], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for cue in cues:
        lines.extend(
            [
                str(cue.index + 1),
                f"{format_srt_timestamp(cue.start_seconds)} --> {format_srt_timestamp(cue.end_seconds)}",
                _export_text(cue),
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def export_text(cues: list[Cue], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(
            f"[{format_srt_timestamp(cue.start_seconds)} --> {format_srt_timestamp(cue.end_seconds)}] {_export_text(cue)}"
            for cue in cues
        ),
        encoding="utf-8",
    )
    return output_path


def _export_text(cue: Cue) -> str:
    speaker = (cue.speaker or "").strip()
    text = " ".join(cue.text.split())
    return f"[{speaker}] {text}" if speaker else text
