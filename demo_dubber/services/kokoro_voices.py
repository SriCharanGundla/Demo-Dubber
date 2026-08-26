from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=4)
def load_voice_catalog(catalog_path: Path) -> dict[str, object]:
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def voice_language_code(voice_id: str) -> str:
    return voice_id[0] if voice_id else ""


def voice_options(catalog_path: Path, samples_dir: Path) -> list[dict[str, object]]:
    catalog = load_voice_catalog(catalog_path)
    languages = dict(catalog["languages"])
    phrases = dict(catalog["sample_phrases"])
    options = []
    for voice_id in catalog["voices"]:
        language_code = voice_language_code(voice_id)
        gender = "Female" if voice_id[1:2] == "f" else "Male"
        name = voice_id.split("_", maxsplit=1)[-1].replace("_", " ").title()
        options.append(
            {
                "id": voice_id,
                "name": name,
                "gender": gender,
                "language": languages[language_code],
                "language_code": language_code,
                "sample_phrase": phrases[language_code],
                "sample_available": (samples_dir / f"{voice_id}.wav").is_file(),
            }
        )
    return options


def validate_voice(catalog_path: Path, voice_id: str, language_code: str) -> bool:
    catalog = load_voice_catalog(catalog_path)
    return (
        voice_id in catalog["voices"]
        and voice_language_code(voice_id) == language_code
    )
