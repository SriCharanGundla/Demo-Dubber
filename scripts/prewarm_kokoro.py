from __future__ import annotations

import os
import time

from kokoro import KPipeline


def main() -> None:
    lang_code = os.getenv("KOKORO_LANG_CODE", "a")
    repo_id = os.getenv("KOKORO_REPO_ID", "hexgrad/Kokoro-82M")
    voice = os.getenv("KOKORO_VOICE", "af_heart")
    last_error: Exception | None = None

    for attempt in range(1, 6):
        try:
            pipeline = KPipeline(lang_code=lang_code, repo_id=repo_id, device="cpu")
            list(pipeline("Kokoro build prewarm.", voice=voice, speed=1.0))
            print("Kokoro model prewarmed successfully", flush=True)
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
