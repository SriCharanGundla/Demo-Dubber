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

    def test_project_paths_are_rebased_after_outputs_directory_moves(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "mounted-outputs"
            project_dir = root / "demo-project"
            project_dir.mkdir(parents=True)
            previous_dir = Path("/host/outputs/demo-project")
            payload = {
                "project_id": "demo-project",
                "title": "Demo",
                "output_dir": str(previous_dir),
                "source_video": str(previous_dir / "demo.mp4"),
                "media_asset": {
                    "extracted_audio": str(previous_dir / "audio" / "source.wav")
                },
                "artifacts": {"muxed_video": str(previous_dir / "dubbed.mp4")},
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
            (project_dir / "project_state.json").write_text(json.dumps(payload))

            projects, errors = scan_saved_projects(root)

            mounted_project_dir = project_dir.resolve()
            self.assertEqual(errors, [])
            self.assertEqual(projects[0].output_dir, mounted_project_dir)
            self.assertEqual(
                projects[0].source_video, mounted_project_dir / "demo.mp4"
            )
            self.assertEqual(
                projects[0].media_asset["extracted_audio"],
                str(mounted_project_dir / "audio" / "source.wav"),
            )
            self.assertEqual(
                projects[0].artifacts["muxed_video"],
                str(mounted_project_dir / "dubbed.mp4"),
            )


if __name__ == "__main__":
    unittest.main()
