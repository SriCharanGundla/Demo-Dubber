from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from apps.api.jobs import ActiveJobError, InMemoryJobStore


class InMemoryJobStoreTests(unittest.TestCase):
    def test_rejects_a_second_active_job_for_the_same_project(self) -> None:
        jobs = InMemoryJobStore()
        first = jobs.create("project-1", "transcription")

        with self.assertRaisesRegex(ActiveJobError, "already active"):
            jobs.create("project-1", "transcription")

        jobs.update(first.id, status="succeeded")
        second = jobs.create("project-1", "render")
        self.assertEqual(second.kind, "render")

    def test_allows_active_jobs_for_different_projects(self) -> None:
        jobs = InMemoryJobStore()

        jobs.create("project-1", "transcription")
        second = jobs.create("project-2", "transcription")

        self.assertEqual(second.project_id, "project-2")

    def test_latest_job_includes_failure_phase(self) -> None:
        jobs = InMemoryJobStore()
        job = jobs.create("project-1", "transcription")
        jobs.update(
            job.id,
            status="failed",
            message="Transcription failed",
            failed_at="Cleaning transcript",
            error="Provider timed out",
        )

        latest = jobs.latest_for_project("project-1")

        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.failed_at, "Cleaning transcript")
        self.assertEqual(latest.as_dict()["error"], "Provider timed out")

    def test_job_outcome_survives_store_restart(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.json"
            first_store = InMemoryJobStore(path)
            job = first_store.create("project-1", "render")
            first_store.update(job.id, status="succeeded", message="Render ready")

            reloaded = InMemoryJobStore(path).latest_for_project("project-1")

            self.assertIsNotNone(reloaded)
            assert reloaded is not None
            self.assertEqual(reloaded.status, "succeeded")
            self.assertEqual(reloaded.message, "Render ready")

    def test_active_job_is_marked_interrupted_after_restart(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.json"
            first_store = InMemoryJobStore(path)
            job = first_store.create("project-1", "transcription")
            first_store.update(job.id, status="running", message="Cleaning transcript")

            reloaded = InMemoryJobStore(path).latest_for_project("project-1")

            self.assertIsNotNone(reloaded)
            assert reloaded is not None
            self.assertEqual(reloaded.status, "failed")
            self.assertEqual(reloaded.failed_at, "Cleaning transcript")


if __name__ == "__main__":
    unittest.main()
