import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from demo_dubber.models import Cue, Transcript
from demo_dubber.services.openai_cleanup import OpenAICleanupService
from demo_dubber.services.openai_transcribe import OpenAITranscriptionService
from demo_dubber.services.transcript_import import transcript_from_srt
from demo_dubber.services.transcript_validation import validate_transcript_timeline


class _Response:
    def __init__(self, payload: dict | None = None, output_text: str = "") -> None:
        self._payload = payload or {}
        self.output_text = output_text

    def model_dump(self) -> dict:
        return self._payload


class TranscriptIntegrityTests(unittest.TestCase):
    def test_openai_transcription_renumbers_after_blank_segments(self) -> None:
        service = OpenAITranscriptionService(api_key=None)
        service._client = object()
        service._create_transcription = Mock(
            return_value=_Response(
                {
                    "segments": [
                        {"start": 0.0, "end": 1.0, "text": "First"},
                        {"start": 1.0, "end": 1.5, "text": "   "},
                        {"start": 1.5, "end": 2.0, "text": "Second"},
                    ]
                }
            )
        )
        with TemporaryDirectory() as directory:
            audio_path = Path(directory) / "audio.wav"
            audio_path.write_bytes(b"test")
            transcript = service.transcribe_with_timestamps(audio_path)
        self.assertEqual([cue.index for cue in transcript.cues], [0, 1])

    def test_cleanup_uses_strict_schema_and_retries_invalid_output(self) -> None:
        transcript = Transcript(
            cues=[
                Cue(
                    index=0,
                    start_seconds=0,
                    end_seconds=1,
                    text="Hi",
                    original_text="Hi",
                )
            ]
        )
        create = Mock(
            side_effect=[
                _Response(output_text="not json"),
                _Response(
                    output_text=(
                        '{"cues":[{"source_indexes":[0],"start_seconds":0,'
                        '"end_seconds":1,"text":"Hi."}]}'
                    )
                ),
            ]
        )
        service = OpenAICleanupService(api_key=None)
        service._client = Mock(responses=Mock(create=create))
        cleaned = service.clean_timestamped_transcript(transcript)
        self.assertEqual(cleaned.cues[0].text, "Hi.")
        self.assertEqual(create.call_count, 2)
        self.assertEqual(
            create.call_args.kwargs["text"]["format"]["type"], "json_schema"
        )
        self.assertTrue(create.call_args.kwargs["text"]["format"]["strict"])

    def test_invalid_timeline_is_rejected(self) -> None:
        transcript = Transcript(
            cues=[
                Cue(
                    index=0,
                    start_seconds=2,
                    end_seconds=1,
                    text="Bad",
                    original_text="Bad",
                )
            ]
        )
        with self.assertRaisesRegex(ValueError, "must end after"):
            validate_transcript_timeline(transcript)

    def test_invalid_srt_timeline_is_rejected_at_import(self) -> None:
        content = "1\n00:00:02,000 --> 00:00:01,000\nBad cue\n"
        with self.assertRaisesRegex(ValueError, "must end after"):
            transcript_from_srt(content, char_limit_margin=10)


if __name__ == "__main__":
    unittest.main()
