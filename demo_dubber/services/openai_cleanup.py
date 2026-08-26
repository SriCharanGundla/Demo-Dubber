from __future__ import annotations

import json
from typing import Any

from openai import OpenAI, OpenAIError

from demo_dubber.models import Cue, Transcript

CLEANUP_PROMPT = """
You are cleaning a transcript that already has trusted timestamp boundaries from an ASR system.

Your job:
1. Fix obvious grammar, punctuation, capitalization, and minor English issues.
2. Improve awkward, poorly worded, or structurally broken sentences when the intended meaning is clear.
3. Remove clear stutters, repeated filler fragments, and ASR artifacts when they do not carry meaning.
4. Merge adjacent chunks only when they are clearly one sentence split across multiple ASR cues.
5. Preserve the spoken meaning. Do not add facts, examples, claims, or explanations.
6. Preserve cue order.
7. Do not hallucinate, summarize, or rewrite into a different style than the speaker likely intended.
8. Every output cue must map to one or more adjacent input cue indexes.
9. The output cue start_seconds must equal the first mapped cue's start_seconds.
10. The output cue end_seconds must equal the last mapped cue's end_seconds.
11. Use all input cues exactly once, in order, with no gaps and no overlaps.
12. If a phrase is understandable but clumsy, prefer a cleaner natural-English version that keeps the same meaning and timing scope.
13. If speaker labels are present, do not merge across a speaker change.

Return JSON only with this shape:
{
  "cues": [
    {
      "source_indexes": [0, 1],
      "start_seconds": 12.34,
      "end_seconds": 15.67,
      "text": "Corrected sentence here."
    }
  ]
}
"""

CLEANUP_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "cues": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "source_indexes": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "integer"},
                    },
                    "start_seconds": {"type": "number"},
                    "end_seconds": {"type": "number"},
                    "text": {"type": "string"},
                },
                "required": ["source_indexes", "start_seconds", "end_seconds", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cues"],
    "additionalProperties": False,
}


class TranscriptCleanupValidator:
    def _parse_response_text(self, output_text: str) -> dict[str, Any]:
        text = (output_text or "").strip()
        if not text:
            raise RuntimeError("Transcript cleanup returned empty output.")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Transcript cleanup returned invalid JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise TypeError("Transcript cleanup returned JSON that is not an object.")
        return payload

    def _build_payload(self, transcript: Transcript) -> dict[str, Any]:
        return {
            "cues": [
                {
                    "index": cue.index,
                    "start_seconds": cue.start_seconds,
                    "end_seconds": cue.end_seconds,
                    "speaker": cue.speaker,
                    "text": cue.text,
                }
                for cue in transcript.cues
            ]
        }

    def _validate_and_build(
        self, cleaned: dict[str, Any], original: Transcript
    ) -> Transcript:
        raw_cues = cleaned.get("cues")
        if not isinstance(raw_cues, list) or not raw_cues:
            raise RuntimeError("Transcript cleanup returned no cues.")

        expected_indexes = [cue.index for cue in original.cues]
        consumed_indexes: list[int] = []
        rebuilt: list[Cue] = []
        cues_by_index = {cue.index: cue for cue in original.cues}

        for new_index, raw_cue in enumerate(raw_cues):
            source_indexes = raw_cue.get("source_indexes")
            if not isinstance(source_indexes, list) or not source_indexes:
                raise RuntimeError(
                    "Transcript cleanup returned a cue without source_indexes."
                )

            if not all(isinstance(index, int) for index in source_indexes):
                raise RuntimeError(
                    "Transcript cleanup returned non-integer source_indexes."
                )

            try:
                source_cues = [cues_by_index[index] for index in source_indexes]
            except KeyError as exc:
                raise RuntimeError(
                    "Transcript cleanup referenced an unknown cue index."
                ) from exc

            text = (raw_cue.get("text") or "").strip()
            if not text:
                text = " ".join(
                    cue.text.strip() for cue in source_cues if cue.text.strip()
                ).strip()
            if not text:
                raise RuntimeError("Transcript cleanup returned an empty cue text.")

            if source_indexes != list(range(source_indexes[0], source_indexes[-1] + 1)):
                raise RuntimeError(
                    "Transcript cleanup returned non-adjacent source_indexes."
                )

            start_seconds = source_cues[0].start_seconds
            end_seconds = source_cues[-1].end_seconds
            speakers = {cue.speaker for cue in source_cues}
            if len(speakers) > 1:
                raise RuntimeError(
                    "Transcript cleanup merged cues across speaker boundaries."
                )
            speaker = speakers.pop() if len(speakers) == 1 else None

            consumed_indexes.extend(source_indexes)
            rebuilt.append(
                Cue(
                    index=new_index,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    text=text,
                    original_text=text,
                    speaker=speaker,
                    word_count=len(text.split()),
                )
            )

        if consumed_indexes != expected_indexes:
            raise RuntimeError(
                "Transcript cleanup returned invalid cue ordering or coverage."
            )

        return Transcript(cues=rebuilt, raw_response=original.raw_response)


class OpenAICleanupService(TranscriptCleanupValidator):
    def __init__(self, api_key: str | None, model: str = "gpt-5.6-luna") -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key) if api_key else None

    def clean_timestamped_transcript(self, transcript: Transcript) -> Transcript:
        if self._client is None:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        payload = self._build_payload(transcript)

        last_error: RuntimeError | TypeError | None = None
        for _attempt in range(2):
            response = self._client.responses.create(
                model=self._model,
                instructions=CLEANUP_PROMPT,
                input=json.dumps(payload, ensure_ascii=True),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "cleaned_transcript",
                        "strict": True,
                        "schema": CLEANUP_RESPONSE_SCHEMA,
                    }
                },
            )
            try:
                cleaned = self._parse_response_text(response.output_text)
                return self._validate_and_build(cleaned, transcript)
            except (RuntimeError, TypeError) as exc:
                last_error = exc
        raise RuntimeError(
            "Transcript cleanup failed validation after 2 attempts."
        ) from last_error


class OpenAICompatibleChatCleanupService(TranscriptCleanupValidator):
    def __init__(
        self,
        base_url: str,
        token: str | None,
        model: str = "giga-brain",
        provider_name: str = "OpenAI-compatible provider",
        default_headers: dict[str, str] | None = None,
        require_structured_parameters: bool = False,
    ) -> None:
        self._model = model
        self._provider_name = provider_name
        self._require_structured_parameters = require_structured_parameters
        self._client = (
            OpenAI(
                api_key=token,
                base_url=f"{base_url.rstrip('/')}/",
                default_headers=default_headers,
            )
            if token
            else None
        )

    def clean_timestamped_transcript(self, transcript: Transcript) -> Transcript:
        if self._client is None:
            raise RuntimeError(f"{self._provider_name} API key is not configured")

        messages = [
            {"role": "system", "content": CLEANUP_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    self._build_payload(transcript), ensure_ascii=True
                ),
            },
        ]
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "cleaned_transcript",
                "strict": True,
                "schema": CLEANUP_RESPONSE_SCHEMA,
            },
        }

        try:
            return self._request_and_validate(
                transcript,
                messages,
                response_format=response_format,
                require_structured_parameters=self._require_structured_parameters,
            )
        except OpenAIError:
            # Some OpenAI-compatible models do not implement json_schema. The
            # prompt still requires JSON, and local validation remains mandatory.
            return self._request_and_validate(transcript, messages)

    def _request_and_validate(
        self,
        transcript: Transcript,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
        require_structured_parameters: bool = False,
    ) -> Transcript:
        if self._client is None:  # Guarded by the public method.
            raise RuntimeError(f"{self._provider_name} API key is not configured")

        request: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if response_format is not None:
            request["response_format"] = response_format
        if require_structured_parameters:
            request["extra_body"] = {"provider": {"require_parameters": True}}

        last_error: RuntimeError | TypeError | None = None
        for _attempt in range(2):
            response = self._client.chat.completions.create(**request)
            try:
                output_text = response.choices[0].message.content or ""
                cleaned = self._parse_response_text(output_text)
                return self._validate_and_build(cleaned, transcript)
            except (IndexError, RuntimeError, TypeError) as exc:
                last_error = (
                    RuntimeError("Transcript cleanup returned no completion choices.")
                    if isinstance(exc, IndexError)
                    else exc
                )

        raise RuntimeError(
            f"{self._provider_name} transcript cleanup failed validation "
            "after 2 attempts."
        ) from last_error
