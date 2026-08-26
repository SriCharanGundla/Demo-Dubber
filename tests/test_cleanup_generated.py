from __future__ import annotations

import os
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from demo_dubber.services.project_store import SavedProjectState, save_project_state
from scripts.cleanup_generated import cleanup_generated


class GeneratedCleanupTests(unittest.TestCase):
    def test_dry_run_and_apply_only_target_old_transient_paths(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project_dir = root / "project-1"
            project_dir.mkdir()
            now = datetime.now(UTC)
            save_project_state(
                SavedProjectState(
                    project_id="project-1",
                    title="Project",
                    output_dir=project_dir,
                    created_at=now,
                    updated_at=now,
                )
            )
            old_preview = project_dir / "editor_previews"
            old_preview.mkdir()
            (old_preview / "preview.wav").write_bytes(b"preview")
            source = project_dir / "source.mp4"
            source.write_bytes(b"source")
            old_timestamp = time.time() - 40 * 86_400
            os.utime(old_preview, (old_timestamp, old_timestamp))

            candidates = cleanup_generated(root, older_than_days=30, apply=False)
            self.assertEqual(
                [path.resolve() for path in candidates], [old_preview.resolve()]
            )
            self.assertTrue(old_preview.exists())

            cleanup_generated(root, older_than_days=30, apply=True)
            self.assertFalse(old_preview.exists())
            self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
