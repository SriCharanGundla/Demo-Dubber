from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    kokoro_voice: str = Field(default="af_heart", alias="KOKORO_VOICE")
    kokoro_speed: float = Field(default=1.0, gt=0, alias="KOKORO_SPEED")
    max_kokoro_speed: float = Field(
        default=1.25, gt=0, alias="DEMO_DUBBER_MAX_KOKORO_SPEED"
    )
    kokoro_lang_code: str = Field(default="a", alias="KOKORO_LANG_CODE")
    kokoro_repo_id: str = Field(default="hexgrad/Kokoro-82M", alias="KOKORO_REPO_ID")
    workspace_dir: Path = Field(
        default=Path("workspace"), alias="DEMO_DUBBER_WORKSPACE"
    )
    outputs_dir: Path = Field(default=Path("outputs"), alias="DEMO_DUBBER_OUTPUTS")
    guard_gap_ms: int = Field(default=120, alias="DEMO_DUBBER_GUARD_GAP_MS")
    chars_per_second: float = Field(default=14.0, alias="DEMO_DUBBER_CHARS_PER_SECOND")
    char_limit_margin: int = Field(default=10, alias="DEMO_DUBBER_CHAR_LIMIT_MARGIN")
    max_tempo_compression_ratio: float = Field(
        default=1.08,
        ge=1.0,
        alias="DEMO_DUBBER_MAX_TEMPO_COMPRESSION_RATIO",
    )
    max_cue_shift_seconds: float = Field(
        default=0.75, ge=0, alias="DEMO_DUBBER_MAX_CUE_SHIFT_SECONDS"
    )
    transcription_model: str = Field(
        default="whisper-1", alias="DEMO_DUBBER_TRANSCRIPTION_MODEL"
    )
    transcription_provider: str = Field(
        default="openai", alias="DEMO_DUBBER_TRANSCRIPTION_PROVIDER"
    )
    local_whisper_model: str = Field(
        default="medium.en", alias="DEMO_DUBBER_LOCAL_WHISPER_MODEL"
    )
    local_whisper_device: str = Field(
        default="auto", alias="DEMO_DUBBER_LOCAL_WHISPER_DEVICE"
    )
    local_whisper_compute_type: str = Field(
        default="int8", alias="DEMO_DUBBER_LOCAL_WHISPER_COMPUTE_TYPE"
    )
    local_whisper_auto_compute_type: str = Field(
        default="auto",
        alias="DEMO_DUBBER_LOCAL_WHISPER_AUTO_COMPUTE_TYPE",
    )
    local_whisper_beam_size: int = Field(
        default=5, alias="DEMO_DUBBER_LOCAL_WHISPER_BEAM_SIZE"
    )
    mlx_whisper_model: str = Field(
        default="mlx-community/whisper-medium.en-mlx",
        alias="DEMO_DUBBER_MLX_WHISPER_MODEL",
    )
    transcription_chunk_seconds: int = Field(
        default=600,
        ge=60,
        alias="DEMO_DUBBER_TRANSCRIPTION_CHUNK_SECONDS",
    )
    transcription_chunk_overlap_seconds: float = Field(
        default=1.0,
        ge=0,
        le=10,
        alias="DEMO_DUBBER_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS",
    )
    cleanup_provider: str = Field(
        default="openai", alias="DEMO_DUBBER_CLEANUP_PROVIDER"
    )
    cleanup_model: str = Field(
        default="gpt-5.6-luna", alias="DEMO_DUBBER_CLEANUP_MODEL"
    )
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        alias="GEMINI_OPENAI_BASE_URL",
    )
    gemini_model: str = Field(default="gemini-3.7-flash", alias="GEMINI_MODEL")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
    )
    openrouter_model: str = Field(
        default="google/gemini-3.7-flash",
        alias="OPENROUTER_MODEL",
    )
    openrouter_site_url: str | None = Field(default=None, alias="OPENROUTER_SITE_URL")
    openrouter_app_name: str = Field(default="Demo Dubber", alias="OPENROUTER_APP_NAME")
    sample_rate: int = 24_000

    @model_validator(mode="after")
    def validate_quality_limits(self) -> Settings:
        if self.max_kokoro_speed < self.kokoro_speed:
            raise ValueError(
                "DEMO_DUBBER_MAX_KOKORO_SPEED must be at least KOKORO_SPEED"
            )
        if self.local_whisper_device.lower() not in {
            "auto",
            "cpu",
            "cuda",
            "mps",
            "metal",
        }:
            raise ValueError(
                "DEMO_DUBBER_LOCAL_WHISPER_DEVICE must be one of: "
                "auto, cpu, cuda, mps, metal"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
