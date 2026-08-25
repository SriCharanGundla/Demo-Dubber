from __future__ import annotations

import re
from difflib import SequenceMatcher

from demo_dubber.models import Cue, Transcript
from demo_dubber.services.transcript_validation import validate_transcript_timeline
from demo_dubber.utils.srt import parse_srt, parse_srt_timestamp

TIMESTAMPED_TXT_PATTERN = re.compile(
    r"^\[(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})\]\s*(?P<text>.*)$"
)
SPEAKER_PREFIX_PATTERN = re.compile(r"^\[(?P<speaker>[^\]]+)\]\s*(?P<text>.*)$")


def transcript_from_srt(content: str, char_limit_margin: int) -> Transcript:
    imported_cues = parse_srt(content)
    cues = [
        _build_cue(
            index=index,
            start_seconds=cue.start_seconds,
            end_seconds=cue.end_seconds,
            text=cue.text,
            char_limit_margin=char_limit_margin,
        )
        for index, cue in enumerate(imported_cues)
    ]
    return validate_transcript_timeline(
        Transcript(cues=cues, raw_response={"source": "uploaded_srt"})
    )


def transcript_from_timestamped_txt(content: str, char_limit_margin: int) -> Transcript:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    timestamped_lines = _parse_timestamped_txt_lines(lines)
    if timestamped_lines is None:
        raise ValueError(
            "TXT files need timestamps to skip OpenAI transcription. Use a TXT exported by this app, or upload SRT."
        )

    cues = [
        _build_cue(
            index=index,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            text=text,
            char_limit_margin=char_limit_margin,
        )
        for index, (start_seconds, end_seconds, text) in enumerate(timestamped_lines)
    ]
    return validate_transcript_timeline(
        Transcript(cues=cues, raw_response={"source": "uploaded_timestamped_txt"})
    )


def replacement_texts_from_srt(cues: list[dict], content: str) -> list[str]:
    imported_cues = parse_srt(content)
    if len(imported_cues) != len(cues):
        raise ValueError(
            f"SRT cue count ({len(imported_cues)}) does not match current transcript ({len(cues)})."
        )

    mismatches: list[str] = []
    for index, (cue, imported_cue) in enumerate(
        zip(cues, imported_cues, strict=True), start=1
    ):
        if not _timestamps_match(
            cue, imported_cue.start_seconds, imported_cue.end_seconds
        ):
            mismatches.append(
                f"cue {index}: expected {_format_mmss(cue['start_seconds'])}-{_format_mmss(cue['end_seconds'])}, "
                f"got {_format_mmss(imported_cue.start_seconds)}-{_format_mmss(imported_cue.end_seconds)}"
            )

    if mismatches:
        raise ValueError(
            "SRT timestamps do not match the generated transcript: "
            + "; ".join(mismatches[:5])
        )
    return [_split_speaker_prefix(cue.text)[1] for cue in imported_cues]


def replacement_texts_from_txt(cues: list[dict], content: str) -> list[str]:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    timestamped_lines = _parse_timestamped_txt_lines(lines)
    if timestamped_lines is not None:
        return _texts_from_matching_timestamped_txt(cues, timestamped_lines)

    if len(lines) == len(cues):
        return lines
    if len(lines) > len(cues):
        return _group_extra_lines_to_cues(cues, lines)
    raise ValueError(
        f"TXT line count ({len(lines)}) is less than current transcript cue count ({len(cues)})."
    )


def _parse_timestamped_txt_lines(
    lines: list[str],
) -> list[tuple[float, float, str]] | None:
    parsed: list[tuple[float, float, str]] = []
    for line in lines:
        match = TIMESTAMPED_TXT_PATTERN.match(line)
        if match is None:
            return None
        parsed.append(
            (
                parse_srt_timestamp(match.group("start")),
                parse_srt_timestamp(match.group("end")),
                match.group("text").strip(),
            )
        )
    return parsed


def _texts_from_matching_timestamped_txt(
    cues: list[dict], lines: list[tuple[float, float, str]]
) -> list[str]:
    if len(lines) != len(cues):
        raise ValueError(
            f"Timestamped TXT cue count ({len(lines)}) does not match current transcript ({len(cues)})."
        )

    mismatches: list[str] = []
    for index, (cue, (start_seconds, end_seconds, _text)) in enumerate(
        zip(cues, lines, strict=True), start=1
    ):
        if not _timestamps_match(cue, start_seconds, end_seconds):
            mismatches.append(
                f"cue {index}: expected {_format_mmss(cue['start_seconds'])}-{_format_mmss(cue['end_seconds'])}, "
                f"got {_format_mmss(start_seconds)}-{_format_mmss(end_seconds)}"
            )

    if mismatches:
        raise ValueError(
            "TXT timestamps do not match the generated transcript: "
            + "; ".join(mismatches[:5])
        )
    return [
        _split_speaker_prefix(text)[1] for _start_seconds, _end_seconds, text in lines
    ]


def apply_replacement_texts(
    cues: list[dict], replacement_texts: list[str], char_limit_margin: int
) -> None:
    if len(replacement_texts) != len(cues):
        raise ValueError(
            f"Imported text count ({len(replacement_texts)}) does not match current transcript ({len(cues)})."
        )

    for cue, replacement_text in zip(cues, replacement_texts, strict=True):
        text = replacement_text.strip()
        cue["text"] = text
        cue["original_text"] = text
        cue["word_count"] = len(text.split())
        cue["char_limit"] = max(1, len(text) + char_limit_margin)
        cue["over_limit"] = False


def _group_extra_lines_to_cues(cues: list[dict], lines: list[str]) -> list[str]:
    grouped: list[str] = []
    line_index = 0

    for cue_index, cue in enumerate(cues):
        remaining_cues = len(cues) - cue_index - 1
        max_group_size = len(lines) - line_index - remaining_cues
        if remaining_cues == 0:
            grouped.append(" ".join(lines[line_index:]))
            break

        expected = _normalize_text(
            str(cue.get("original_text") or cue.get("text") or "")
        )
        best_size = 1
        best_score = -1.0

        for group_size in range(1, max_group_size + 1):
            candidate = " ".join(lines[line_index : line_index + group_size])
            score = SequenceMatcher(None, expected, _normalize_text(candidate)).ratio()
            if score > best_score:
                best_score = score
                best_size = group_size

        grouped.append(" ".join(lines[line_index : line_index + best_size]))
        line_index += best_size

    return grouped


def _build_cue(
    index: int,
    start_seconds: float,
    end_seconds: float,
    text: str,
    char_limit_margin: int,
) -> Cue:
    speaker, normalized_text = _split_speaker_prefix(text)
    return Cue(
        index=index,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        text=normalized_text,
        original_text=normalized_text,
        speaker=speaker,
        word_count=len(normalized_text.split()),
        char_limit=max(1, len(normalized_text) + char_limit_margin),
    )


def _split_speaker_prefix(text: str) -> tuple[str | None, str]:
    normalized_text = " ".join(text.split())
    match = SPEAKER_PREFIX_PATTERN.match(normalized_text)
    if match is None:
        return None, normalized_text

    speaker = match.group("speaker").strip()
    cue_text = match.group("text").strip()
    return speaker or None, cue_text


def _timestamps_match(cue: dict, start_seconds: float, end_seconds: float) -> bool:
    tolerance_seconds = 0.05
    return (
        abs(float(cue["start_seconds"]) - start_seconds) <= tolerance_seconds
        and abs(float(cue["end_seconds"]) - end_seconds) <= tolerance_seconds
    )


def _format_mmss(total_seconds: float) -> str:
    whole_seconds = max(0, int(total_seconds))
    minutes, seconds = divmod(whole_seconds, 60)
    return f"{minutes:02}:{seconds:02}"


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())
