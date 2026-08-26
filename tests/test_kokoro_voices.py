import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from demo_dubber.services.kokoro_voices import validate_voice, voice_options


class KokoroVoiceCatalogTests(unittest.TestCase):
    catalog_path = Path("assets/kokoro_voices.json")

    def test_catalog_contains_every_english_voice(self) -> None:
        with TemporaryDirectory() as directory:
            options = voice_options(self.catalog_path, Path(directory))

        self.assertEqual(len(options), 28)
        self.assertEqual(
            {option["language"] for option in options},
            {"American English", "British English"},
        )
        self.assertEqual(
            {option["gender"] for option in options}, {"Female", "Male"}
        )

    def test_voice_and_language_must_match_catalog(self) -> None:
        self.assertTrue(validate_voice(self.catalog_path, "af_heart", "a"))
        self.assertTrue(validate_voice(self.catalog_path, "bf_emma", "b"))
        self.assertFalse(validate_voice(self.catalog_path, "bf_emma", "a"))
        self.assertFalse(validate_voice(self.catalog_path, "zf_xiaoyi", "z"))

    def test_sample_availability_reflects_pre_rendered_file(self) -> None:
        with TemporaryDirectory() as directory:
            samples_dir = Path(directory)
            (samples_dir / "af_heart.wav").write_bytes(b"sample")

            options = voice_options(self.catalog_path, samples_dir)

        heart = next(option for option in options if option["id"] == "af_heart")
        alloy = next(option for option in options if option["id"] == "af_alloy")
        self.assertTrue(heart["sample_available"])
        self.assertFalse(alloy["sample_available"])


if __name__ == "__main__":
    unittest.main()
