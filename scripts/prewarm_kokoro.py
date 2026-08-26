from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from huggingface_hub import hf_hub_download
from kokoro import KModel, KPipeline


def main() -> None:
    repo_id = os.getenv("KOKORO_REPO_ID", "hexgrad/Kokoro-82M")
    lang_code = os.getenv("KOKORO_LANG_CODE", "a")
    catalog_path = Path(
        os.getenv("DEMO_DUBBER_VOICE_CATALOG", "assets/kokoro_voices.json")
    )
    samples_dir = Path(
        os.getenv("DEMO_DUBBER_VOICE_SAMPLES", "/opt/kokoro-voice-samples")
    )
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    last_error: Exception | None = None

    for attempt in range(1, 6):
        try:
            samples_dir.mkdir(parents=True, exist_ok=True)
            for voice in catalog["voices"]:
                hf_hub_download(repo_id=repo_id, filename=f"voices/{voice}.pt")

            model = KModel(repo_id=repo_id).to("cpu").eval()
            pipelines: dict[str, KPipeline] = {}
            with torch.inference_mode():
                for position, voice in enumerate(catalog["voices"], start=1):
                    output_path = samples_dir / f"{voice}.wav"
                    if output_path.is_file():
                        continue
                    voice_lang_code = voice[0]
                    pipeline = pipelines.get(voice_lang_code)
                    if pipeline is None:
                        pipeline = KPipeline(
                            lang_code=voice_lang_code or lang_code,
                            repo_id=repo_id,
                            model=model,
                        )
                        pipelines[voice_lang_code] = pipeline
                    phrase = catalog["sample_phrases"][voice_lang_code]
                    segments = list(pipeline(phrase, voice=voice, speed=1.0))
                    audio = np.concatenate(
                        [np.asarray(item[2], dtype=np.float32) for item in segments]
                    )
                    sf.write(output_path, audio, 24_000)
                    print(
                        f"Rendered Kokoro voice {position}/{len(catalog['voices'])}: {voice}",
                        flush=True,
                    )
            print("All Kokoro voices and samples prewarmed successfully", flush=True)
            return
        # Kokoro can surface backend-specific exceptions from Torch,
        # Hugging Face, HTTP clients, and model loaders. This build-time retry
        # boundary must retain all of them for the final chained error.
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"Kokoro prewarm attempt {attempt}/5 failed: {exc}", flush=True)
            if attempt < 5:
                time.sleep(10 * attempt)

    raise RuntimeError("Kokoro model prewarm failed after 5 attempts") from last_error


if __name__ == "__main__":
    main()
