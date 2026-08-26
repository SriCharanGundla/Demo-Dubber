from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

JobStatus = Literal["queued", "running", "succeeded", "failed"]
ACTIVE_STATUSES = {"queued", "running"}


class ActiveJobError(RuntimeError):
    """Raised when a project already has unfinished work."""


@dataclass
class Job:
    id: str
    project_id: str
    kind: str
    status: JobStatus = "queued"
    message: str = "Queued"
    completed: int | None = None
    total: int | None = None
    error: str | None = None
    failed_at: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "kind": self.kind,
            "status": self.status,
            "message": self.message,
            "completed": self.completed,
            "total": self.total,
            "error": self.error,
            "failed_at": self.failed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class InMemoryJobStore:
    """Thread-safe local job state; replace with a durable queue for multi-worker use."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, project_id: str, kind: str) -> Job:
        with self._lock:
            active = next(
                (
                    job
                    for job in self._jobs.values()
                    if job.project_id == project_id and job.status in ACTIVE_STATUSES
                ),
                None,
            )
            if active is not None:
                raise ActiveJobError(
                    f"A {active.kind} job is already active for this project"
                )
            job = Job(id=uuid.uuid4().hex, project_id=project_id, kind=kind)
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def active_for_project(self, project_id: str) -> Job | None:
        with self._lock:
            return next(
                (
                    job
                    for job in self._jobs.values()
                    if job.project_id == project_id and job.status in ACTIVE_STATUSES
                ),
                None,
            )

    def latest_for_project(self, project_id: str) -> Job | None:
        with self._lock:
            matching = [
                job for job in self._jobs.values() if job.project_id == project_id
            ]
            return max(matching, key=lambda job: job.updated_at) if matching else None

    def update(self, job_id: str, **changes: object) -> Job:
        with self._lock:
            job = self._jobs[job_id]
            for name, value in changes.items():
                setattr(job, name, value)
            job.updated_at = datetime.now(UTC)
            return job
