from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from openai import OpenAIError

from demo_dubber.models import Cue, Transcript
from demo_dubber.services.openai_cleanup import (
    OpenAICompatibleChatCleanupService,
)


class FakeCompletions:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.requests: list[dict] = []

    def create(self, **request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=response))]
        )


def transcript() -> Transcript:
    return Transcript(
        cues=[
            Cue(
                index=0,
                start_seconds=0.0,
                end_seconds=1.0,
                text="hello world",
                original_text="hello world",
            )
        ]
    )


def valid_response() -> str:
    return json.dumps(
        {
            "cues": [
                {
                    "source_indexes": [0],
                    "start_seconds": 0.0,
                    "end_seconds": 1.0,
                    "text": "Hello world.",
                }
            ]
        }
    )


class CompatibleCleanupTests(unittest.TestCase):
    def test_openrouter_requires_structured_parameter_support(self) -> None:
        service = OpenAICompatibleChatCleanupService(
            base_url="https://openrouter.ai/api/v1",
            token="test",
            model="test/model",
            provider_name="OpenRouter",
            require_structured_parameters=True,
        )
        completions = FakeCompletions([valid_response()])
        service._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        cleaned = service.clean_timestamped_transcript(transcript())

        self.assertEqual(cleaned.cues[0].text, "Hello world.")
        self.assertEqual(
            completions.requests[0]["extra_body"],
            {"provider": {"require_parameters": True}},
        )
        self.assertEqual(
            completions.requests[0]["response_format"]["type"], "json_schema"
        )

    def test_unsupported_schema_falls_back_to_locally_validated_json(self) -> None:
        service = OpenAICompatibleChatCleanupService(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            token="test",
            model="gemini-test",
            provider_name="Gemini AI Studio",
        )
        completions = FakeCompletions(
            [OpenAIError("response_format is unsupported"), valid_response()]
        )
        service._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        cleaned = service.clean_timestamped_transcript(transcript())

        self.assertEqual(cleaned.cues[0].text, "Hello world.")
        self.assertIn("response_format", completions.requests[0])
        self.assertNotIn("response_format", completions.requests[1])

    def test_authentication_failure_is_not_retried(self) -> None:
        service = OpenAICompatibleChatCleanupService(
            base_url="https://example.test/v1",
            token="test",
            model="test-model",
            provider_name="Test provider",
        )
        completions = FakeCompletions([OpenAIError("invalid API key")])
        service._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with self.assertRaisesRegex(OpenAIError, "invalid API key"):
            service.clean_timestamped_transcript(transcript())

        self.assertEqual(len(completions.requests), 1)
