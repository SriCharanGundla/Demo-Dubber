from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedSrtCue:
    start_seconds: float
    end_seconds: float
    text: str


def format_srt_timestamp(total_seconds: float) -> str:
    total_milliseconds = max(0, round(total_seconds * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def parse_srt(content: str) -> list[ParsedSrtCue]:
    blocks = [
        block.strip()
        for block in content.replace("\r\n", "\n").replace("\r", "\n").split("\n\n")
    ]
    cues: list[ParsedSrtCue] = []

    for block in blocks:
        if not block:
            continue

        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        timing_index = 1 if lines[0].isdigit() and len(lines) > 1 else 0
        if timing_index >= len(lines) or "-->" not in lines[timing_index]:
            raise ValueError("SRT cue is missing a timestamp line.")

        start_raw, end_raw = [
            part.strip() for part in lines[timing_index].split("-->", 1)
        ]
        cues.append(
            ParsedSrtCue(
                start_seconds=parse_srt_timestamp(start_raw),
                end_seconds=parse_srt_timestamp(end_raw),
                text="\n".join(lines[timing_index + 1 :]).strip(),
            )
        )

    if not cues:
        raise ValueError("No SRT cues were found.")
    return cues


def parse_srt_timestamp(value: str) -> float:
    timestamp = value.split()[0].replace(",", ".")
    hours_raw, minutes_raw, seconds_raw = timestamp.split(":", 2)
    seconds, _, milliseconds = seconds_raw.partition(".")
    return (
        int(hours_raw) * 3600
        + int(minutes_raw) * 60
        + int(seconds)
        + int((milliseconds + "000")[:3]) / 1000
    )
