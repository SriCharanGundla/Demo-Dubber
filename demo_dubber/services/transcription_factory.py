from __future__ import annotations

import importlib.util
import platform
from dataclasses import dataclass

import ctranslate2

from demo_dubber.config import Settings
from demo_dubber.services.local_whisper_transcribe import (
    LocalWhisperTranscriptionService,
)
from demo_dubber.services.mlx_whisper_transcribe import (
    MLXWhisperTranscriptionService,
)
from demo_dubber.services.openai_transcribe import OpenAITranscriptionService


@dataclass(frozen=True)
class TranscriptionProviderInfo:
    id: str
    label: str
    configured: bool
    default: bool = False
    detail: str | None = None


def transcription_provider_catalog(
    settings: Settings,
) -> list[TranscriptionProviderInfo]:
    cuda_available = _cuda_available()
    mlx_available = _mlx_available()
    default_provider = _default_provider_id(settings)
    return [
        TranscriptionProviderInfo(
            "openai",
            "OpenAI Whisper",
            bool(settings.openai_api_key),
            default_provider == "openai",
            "Requires OPENAI_API_KEY",
        ),
        TranscriptionProviderInfo(
            "local-auto",
            "Local Whisper · Auto",
            True,
            default_provider == "local-auto",
            "Lets CTranslate2 choose CPU or NVIDIA CUDA",
        ),
        TranscriptionProviderInfo(
            "local-cpu",
            "Local Whisper · CPU",
            True,
            default_provider == "local-cpu",
            "Portable CPU inference",
        ),
        TranscriptionProviderInfo(
            "local-cuda",
            "Local Whisper · NVIDIA CUDA",
            cuda_available,
            default_provider == "local-cuda",
            "Requires a detected NVIDIA CUDA device",
        ),
        TranscriptionProviderInfo(
            "local-mps",
            "MLX Whisper · Apple Silicon",
            mlx_available,
            default_provider == "local-mps",
            "Uses the Apple GPU through MLX",
        ),
    ]


def build_transcription_service(settings: Settings, provider: str):
    provider_id = _normalize_provider_id(provider, settings.local_whisper_device)
    if provider_id == "openai":
        return OpenAITranscriptionService(
            api_key=settings.openai_api_key,
            model=settings.transcription_model,
        )
    if provider_id == "local-mps":
        if not _mlx_available():
            raise RuntimeError("MLX Whisper requires an Apple Silicon Mac.")
        return MLXWhisperTranscriptionService(model=settings.mlx_whisper_model)

    devices = {
        "local-auto": "auto",
        "local-cpu": "cpu",
        "local-cuda": "cuda",
    }
    device = devices.get(provider_id)
    if device is None:
        raise ValueError(f"Unknown transcription provider: {provider}")
    if device == "cuda" and not _cuda_available():
        raise RuntimeError("No NVIDIA CUDA device was detected by CTranslate2.")
    compute_type = (
        settings.local_whisper_compute_type
        if device != "auto"
        else settings.local_whisper_auto_compute_type
    )
    return LocalWhisperTranscriptionService(
        model=settings.local_whisper_model,
        device=device,
        compute_type=compute_type,
        beam_size=settings.local_whisper_beam_size,
    )


def _default_provider_id(settings: Settings) -> str:
    provider = settings.transcription_provider.strip().lower()
    if provider == "openai":
        return "openai"
    return _normalize_provider_id(provider, settings.local_whisper_device)


def _normalize_provider_id(provider: str, configured_device: str) -> str:
    provider_id = provider.strip().lower()
    if provider_id in {"mlx", "mps", "metal", "local-mps"}:
        return "local-mps"
    if provider_id in {"local", "local-whisper", "local_whisper"}:
        device = configured_device.strip().lower()
        if device in {"mps", "metal"}:
            return "local-mps"
        if device == "cuda":
            return "local-cuda"
        if device == "cpu":
            return "local-cpu"
        return "local-auto"
    if provider_id in {"local-auto", "local-cpu", "local-cuda", "openai"}:
        return provider_id
    return provider_id


def _mlx_available() -> bool:
    return (
        platform.system() == "Darwin"
        and platform.machine() == "arm64"
        and importlib.util.find_spec("mlx_whisper") is not None
    )


def _cuda_available() -> bool:
    try:
        return ctranslate2.get_cuda_device_count() > 0
    except RuntimeError:
        return False
