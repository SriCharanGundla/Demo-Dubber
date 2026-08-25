import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from demo_dubber.services.project_store import (
    SavedProjectState,
    delete_project,
    save_session_project,
    scan_saved_projects,
)
from demo_dubber.utils.files import atomic_write_json, ensure_path_within, safe_filename


class FileSafetyTests(unittest.TestCase):
    def test_upload_filename_is_reduced_to_basename(self) -> None:
        self.assertEqual(safe_filename("../../videos/demo.mp4"), "demo.mp4")
        self.assertEqual(safe_filename(r"..\videos\demo.mp4"), "demo.mp4")

    def test_path_containment_rejects_escape(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "outputs"
            root.mkdir()
            with self.assertRaisesRegex(ValueError, "outside"):
                ensure_path_within(root, root.parent / "unrelated")

    def test_project_deletion_cannot_escape_outputs_root(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "outputs"
            outside = Path(directory) / "keep-me"
            root.mkdir()
            outside.mkdir()
            project = SavedProjectState(
                project_id="unsafe",
                title="unsafe",
                output_dir=outside,
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            )
            with self.assertRaisesRegex(ValueError, "outside"):
                delete_project(project, root)
            self.assertTrue(outside.exists())

    def test_project_save_cannot_escape_outputs_root(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "outputs"
            outside = Path(directory) / "outside"
            root.mkdir()
            with self.assertRaisesRegex(ValueError, "outside"):
                save_session_project({"output_dir": str(outside)}, root, stage="edit")

    def test_atomic_json_write_produces_valid_file(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            atomic_write_json(path, {"stage": "edit"})
            self.assertEqual(json.loads(path.read_text()), {"stage": "edit"})
            self.assertEqual(list(path.parent.glob(".state.json.*")), [])

    def test_corrupt_project_state_is_reported(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            broken = root / "broken-project"
            broken.mkdir()
            (broken / "project_state.json").write_text("not json")
            projects, errors = scan_saved_projects(root)
            self.assertEqual(projects, [])
            self.assertEqual(errors, ["broken-project"])


if __name__ == "__main__":
    unittest.main()
