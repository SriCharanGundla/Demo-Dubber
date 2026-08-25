from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

JobStatus = Literal["queued", "running", "succeeded", "failed"]


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
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class InMemoryJobStore:
    """Thread-safe local job state; replace with a durable queue for multi-worker use."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, project_id: str, kind: str) -> Job:
        job = Job(id=uuid.uuid4().hex, project_id=project_id, kind=kind)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **changes: object) -> Job:
        with self._lock:
            job = self._jobs[job_id]
            for name, value in changes.items():
                setattr(job, name, value)
            job.updated_at = datetime.now(UTC)
            return job
