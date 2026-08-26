from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
