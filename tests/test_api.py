from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api import main as api_module


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_settings = api_module.settings
        api_module.settings = self.original_settings.model_copy(
            update={"outputs_dir": Path(self.temporary_directory.name)}
        )
        self.client = TestClient(api_module.app)

    def tearDown(self) -> None:
        api_module.settings = self.original_settings
        self.temporary_directory.cleanup()

    def test_health_and_provider_catalog(self) -> None:
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        providers = self.client.get("/api/providers").json()
        self.assertEqual(
            [provider["id"] for provider in providers["cleanup"]],
            ["openai", "gemini", "openrouter"],
        )

    def test_project_upload_list_and_delete(self) -> None:
        response = self.client.post(
            "/api/projects",
            files={"video": ("demo.mp4", b"test video", "video/mp4")},
        )
        self.assertEqual(response.status_code, 201)
        project = response.json()
        self.assertTrue(Path(project["source_video"]).is_file())

        listed = self.client.get("/api/projects").json()["projects"]
        self.assertEqual(
            [item["project_id"] for item in listed], [project["project_id"]]
        )

        deleted = self.client.delete(f"/api/projects/{project['project_id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/projects").json()["projects"], [])

    def test_upload_rejects_unsupported_extension(self) -> None:
        response = self.client.post(
            "/api/projects",
            files={"video": ("payload.exe", b"unsafe", "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 415)
