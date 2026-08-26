from __future__ import annotations

import os
import time

from faster_whisper.utils import download_model


def main() -> None:
    model = os.getenv("DEMO_DUBBER_LOCAL_WHISPER_MODEL", "medium.en")
    token = os.getenv("HF_TOKEN") or None
    last_error: Exception | None = None

    for attempt in range(1, 6):
        try:
            model_path = download_model(model, use_auth_token=token)
            print(f"Whisper model cached at {model_path}", flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"Whisper prewarm attempt {attempt}/5 failed: {exc}", flush=True)
            if attempt < 5:
                time.sleep(10 * attempt)

    raise RuntimeError("Whisper model prewarm failed after 5 attempts") from last_error


if __name__ == "__main__":
    main()
