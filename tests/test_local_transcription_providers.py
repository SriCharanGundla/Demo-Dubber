from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from demo_dubber.config import Settings
from demo_dubber.services.mlx_whisper_transcribe import (
    MLXWhisperTranscriptionService,
)
from demo_dubber.services.transcription_factory import (
    build_transcription_service,
    transcription_provider_catalog,
)


class MLXWhisperTests(unittest.TestCase):
    def test_mlx_response_is_converted_to_timestamped_cues(self) -> None:
        requests = []

        def transcribe(audio, **options):
            requests.append((audio, options))
            return {
                "language": "en",
                "segments": [
                    {
                        "start": 1,
                        "end": 2.5,
                        "text": " Hello from MLX. ",
                        "words": [
                            {
                                "start": 1,
                                "end": 1.4,
                                "word": " Hello",
                                "probability": 0.98,
                            }
                        ],
                    }
                ],
            }

        service = MLXWhisperTranscriptionService(
            model="mlx-community/test-model",
            transcribe=transcribe,
        )
        transcript = service.transcribe_with_timestamps(Path("audio.wav"))

        self.assertEqual(transcript.cues[0].text, "Hello from MLX.")
        self.assertEqual(transcript.cues[0].start_seconds, 1.0)
        self.assertEqual(transcript.raw_response["provider"], "mlx-whisper")
        self.assertTrue(requests[0][1]["word_timestamps"])

    @patch(
        "demo_dubber.services.transcription_factory._mlx_available", return_value=True
    )
    @patch(
        "demo_dubber.services.transcription_factory._cuda_available", return_value=False
    )
    def test_mps_environment_defaults_to_mlx(self, _cuda, _mlx) -> None:
        settings = Settings().model_copy(
            update={
                "transcription_provider": "local",
                "local_whisper_device": "mps",
            }
        )

        catalog = transcription_provider_catalog(settings)
        default = next(provider for provider in catalog if provider.default)
        service = build_transcription_service(settings, "local")

        self.assertEqual(default.id, "local-mps")
        self.assertIsInstance(service, MLXWhisperTranscriptionService)

    @patch(
        "demo_dubber.services.transcription_factory._mlx_available", return_value=False
    )
    @patch(
        "demo_dubber.services.transcription_factory._cuda_available", return_value=True
    )
    def test_cuda_is_exposed_only_when_detected(self, _cuda, _mlx) -> None:
        settings = Settings().model_copy(
            update={
                "transcription_provider": "local",
                "local_whisper_device": "cuda",
            }
        )

        providers = {
            provider.id: provider
            for provider in transcription_provider_catalog(settings)
        }

        self.assertTrue(providers["local-cuda"].configured)
        self.assertTrue(providers["local-cuda"].default)
        self.assertFalse(providers["local-mps"].configured)
