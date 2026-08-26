from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api import main as api_module
from apps.api.jobs import InMemoryJobStore
from demo_dubber.models import Cue, MediaAsset, RenderArtifacts
from demo_dubber.services.project_store import save_project_state


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_settings = api_module.settings
        self.original_jobs = api_module.jobs
        api_module.jobs = InMemoryJobStore()
        voice_samples = Path(self.temporary_directory.name) / "voice-samples"
        voice_samples.mkdir()
        (voice_samples / "af_heart.wav").write_bytes(b"sample audio")
        api_module.settings = self.original_settings.model_copy(
            update={
                "outputs_dir": Path(self.temporary_directory.name),
                "kokoro_voice_catalog": Path("assets/kokoro_voices.json").resolve(),
                "kokoro_voice_samples_dir": voice_samples,
                "openai_api_key": None,
                "gemini_api_key": None,
                "openrouter_api_key": None,
            }
        )
        self.client = TestClient(api_module.app)

    def tearDown(self) -> None:
        api_module.settings = self.original_settings
        api_module.jobs = self.original_jobs
        self.temporary_directory.cleanup()

    def _upload_project(self) -> dict[str, object]:
        with patch.object(
            api_module.FFmpegService,
            "probe_video",
            return_value=MediaAsset(
                source_video=Path("demo.mp4"),
                duration_seconds=60,
                width=1920,
                height=1080,
            ),
        ):
            response = self.client.post(
                "/api/projects",
                files={"video": ("demo.mp4", b"test video", "video/mp4")},
            )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_health_and_provider_catalog(self) -> None:
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        providers = self.client.get("/api/providers").json()
        self.assertEqual(
            [provider["id"] for provider in providers["cleanup"]],
            ["openai", "gemini", "openrouter"],
        )
        self.assertFalse(
            any(provider["configured"] for provider in providers["cleanup"])
        )
        self.assertEqual(
            [provider["id"] for provider in providers["transcription"]],
            ["openai", "local-auto", "local-cpu", "local-cuda", "local-mps"],
        )
        transcription = {
            provider["id"]: provider for provider in providers["transcription"]
        }
        self.assertFalse(transcription["openai"]["configured"])
        self.assertTrue(transcription["local-auto"]["configured"])
        self.assertTrue(transcription["local-cpu"]["configured"])

    def test_voice_catalog_exposes_only_english_samples(self) -> None:
        response = self.client.get("/api/voices")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["voices"]), 28)
        self.assertEqual(
            {voice["language"] for voice in payload["voices"]},
            {"American English", "British English"},
        )
        self.assertTrue(
            all(voice["sample_url"].endswith("/sample") for voice in payload["voices"])
        )
        heart = next(voice for voice in payload["voices"] if voice["id"] == "af_heart")
        self.assertTrue(heart["sample_available"])
        sample = self.client.get(heart["sample_url"])
        self.assertEqual(sample.status_code, 200)
        self.assertIn("immutable", sample.headers["cache-control"])

    def test_project_upload_list_and_delete(self) -> None:
        project = self._upload_project()
        self.assertNotIn("source_video", project)
        self.assertNotIn("output_dir", project)
        stored = api_module._project(str(project["project_id"]))
        self.assertTrue(stored.source_video and stored.source_video.is_file())
        self.assertEqual(project["tts_voice"], "af_heart")
        self.assertEqual(project["tts_language"], "a")

        listed = self.client.get("/api/projects").json()["projects"]
        self.assertEqual(
            [item["project_id"] for item in listed], [project["project_id"]]
        )

        deleted = self.client.delete(f"/api/projects/{project['project_id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/projects").json()["projects"], [])

    def test_project_rename_preserves_stable_id(self) -> None:
        project = self._upload_project()

        response = self.client.patch(
            f"/api/projects/{project['project_id']}",
            json={"title": "  Launch   walkthrough  "},
        )

        self.assertEqual(response.status_code, 200)
        renamed = response.json()
        self.assertEqual(renamed["project_id"], project["project_id"])
        self.assertEqual(renamed["title"], "Launch walkthrough")
        self.assertEqual(
            self.client.get(f"/api/projects/{project['project_id']}").json()["title"],
            "Launch walkthrough",
        )

    def test_active_job_can_be_reattached_after_browser_refresh(self) -> None:
        project = self._upload_project()
        job = api_module.jobs.create(str(project["project_id"]), "transcription")

        response = self.client.get(f"/api/projects/{project['project_id']}/jobs/active")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job"]["id"], job.id)
        listed = self.client.get("/api/projects").json()["projects"][0]
        loaded = self.client.get(f"/api/projects/{project['project_id']}").json()
        self.assertEqual(listed["active_job"]["id"], job.id)
        self.assertEqual(loaded["active_job"]["kind"], "transcription")

    def test_latest_job_preserves_failed_processing_phase(self) -> None:
        project = self._upload_project()
        job = api_module.jobs.create(str(project["project_id"]), "transcription")
        api_module.jobs.update(
            job.id,
            status="failed",
            message="Transcription failed",
            failed_at="Cleaning transcript",
            error="Cleanup provider timed out",
        )

        response = self.client.get(f"/api/projects/{project['project_id']}/jobs/latest")

        self.assertEqual(response.status_code, 200)
        latest = response.json()["job"]
        self.assertEqual(latest["id"], job.id)
        self.assertEqual(latest["failed_at"], "Cleaning transcript")
        self.assertEqual(latest["error"], "Cleanup provider timed out")

    def test_transcript_exports_work_before_render(self) -> None:
        project_payload = self._upload_project()
        project = api_module._project(str(project_payload["project_id"]))
        cue = Cue(
            index=0,
            start_seconds=0,
            end_seconds=1.5,
            text="Edited words",
            original_text="Original words",
        )
        save_project_state(
            project.model_copy(
                update={"stage": "edit", "transcript_cues": [cue.model_dump()]}
            )
        )

        txt = self.client.get(f"/api/projects/{project.project_id}/exports/txt")
        srt = self.client.get(f"/api/projects/{project.project_id}/exports/srt")

        self.assertEqual(txt.status_code, 200)
        self.assertIn("Edited words", txt.text)
        self.assertEqual(srt.status_code, 200)
        self.assertIn("00:00:00,000 --> 00:00:01,500", srt.text)

    @patch("apps.api.main.RenderWorkflow")
    def test_render_uses_the_project_voice_and_accent(self, workflow: object) -> None:
        project_payload = self._upload_project()
        project = api_module._project(str(project_payload["project_id"]))
        cue = Cue(
            index=0,
            start_seconds=0,
            end_seconds=1,
            text="Hello",
            original_text="Hello",
        )
        project = project.model_copy(
            update={
                "tts_voice": "bf_emma",
                "tts_language": "b",
                "transcript_cues": [cue.model_dump()],
            }
        )
        workflow.return_value.run.return_value = RenderArtifacts()
        job = api_module.jobs.create(project.project_id, "render")

        api_module._run_render(job.id, project)

        render_settings = workflow.call_args.kwargs["settings"]
        self.assertEqual(render_settings.kokoro_voice, "bf_emma")
        self.assertEqual(render_settings.kokoro_lang_code, "b")

    def test_upload_rejects_unsupported_extension(self) -> None:
        response = self.client.post(
            "/api/projects",
            files={"video": ("payload.exe", b"unsafe", "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 415)

    def test_upload_rejects_files_over_configured_limit(self) -> None:
        api_module.settings = api_module.settings.model_copy(
            update={"max_upload_bytes": 3}
        )
        response = self.client.post(
            "/api/projects",
            files={"video": ("large.mp4", b"four", "video/mp4")},
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            [
                path.name
                for path in Path(self.temporary_directory.name).iterdir()
                if path.name != "voice-samples"
            ],
            [],
        )

    def test_transcript_update_rejects_untrusted_cue_metadata(self) -> None:
        project_payload = self._upload_project()
        project = api_module._project(str(project_payload["project_id"]))
        original = Cue(
            index=0,
            start_seconds=1,
            end_seconds=3,
            text="Original words",
            original_text="Original words",
            char_limit=1,
            over_limit=True,
        )
        save_project_state(
            project.model_copy(update={"transcript_cues": [original.model_dump()]})
        )

        response = self.client.put(
            f"/api/projects/{project.project_id}/transcript",
            json={
                "cues": [
                    {
                        **original.model_dump(),
                        "text": "Edited words",
                        "start_seconds": 20,
                        "end_seconds": 30,
                        "original_text": "Tampered",
                        "char_limit": 9999,
                        "over_limit": False,
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 422)

        accepted = self.client.put(
            f"/api/projects/{project.project_id}/transcript",
            json={"cues": [{"index": 0, "text": "Edited words"}]},
        )
        self.assertEqual(accepted.status_code, 200)
        saved = accepted.json()["cues"][0]
        self.assertEqual(saved["start_seconds"], 1)
        self.assertEqual(saved["end_seconds"], 3)
        self.assertEqual(saved["original_text"], "Original words")
        self.assertNotEqual(saved["char_limit"], 9999)

    def test_render_rejects_over_limit_transcript(self) -> None:
        project_payload = self._upload_project()
        project = api_module._project(str(project_payload["project_id"]))
        cue = Cue(
            index=0,
            start_seconds=0,
            end_seconds=1,
            text="x" * 1_000,
            original_text="Short",
        )
        save_project_state(
            project.model_copy(update={"transcript_cues": [cue.model_dump()]})
        )

        response = self.client.post(f"/api/projects/{project.project_id}/render")

        self.assertEqual(response.status_code, 409)
        self.assertIn("over-limit", response.json()["detail"])
