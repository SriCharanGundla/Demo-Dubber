import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  Navigate,
  Outlet,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import { Film, Plus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { api } from "@/lib/api";
import { AppContext, projectRoute, showError, useApp } from "@/lib/app-context";
import { ExportScreen } from "@/screens/export";
import { ProjectsScreen } from "@/screens/projects";
import { TranscriptScreen } from "@/screens/transcript";
import { TranscribeScreen } from "@/screens/transcribe";

const emptyProviders = { cleanup: [], transcription: [] };
const emptyVoiceCatalog = { voices: [], default_voice: "af_heart" };

export default function App() {
  const [projects, setProjects] = useState([]);
  const [providers, setProviders] = useState(emptyProviders);
  const [voiceCatalog, setVoiceCatalog] = useState(emptyVoiceCatalog);
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const refreshProjects = useCallback(async () => {
    const result = await api.projects();
    setProjects(result.projects);
    return result.projects;
  }, []);

  const loadProject = useCallback(async (projectId) => {
    const [project, latestResult] = await Promise.all([
      api.project(projectId),
      api.latestJob(projectId),
    ]);
    setJob(latestResult.job);
    setProjects((current) => {
      const exists = current.some((item) => item.project_id === projectId);
      return exists
        ? current.map((item) =>
            item.project_id === projectId ? project : item,
          )
        : [project, ...current];
    });
    return project;
  }, []);

  useEffect(() => {
    Promise.all([refreshProjects(), api.providers(), api.voices()])
      .then(([, providerResult, voiceResult]) => {
        setProviders(providerResult);
        setVoiceCatalog(voiceResult);
      })
      .catch((reason) => showError(reason, "load-app"));
  }, [refreshProjects]);

  useEffect(() => {
    if (!job || ["succeeded", "failed"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.job(job.project_id, job.id);
        setJob(next);
        if (next.status === "succeeded") {
          toast.success(next.message || "Job complete", {
            id: `job-${next.id}`,
          });
          const project = await loadProject(next.project_id);
          navigate(projectRoute(project));
        } else if (next.status === "failed") {
          toast.error(next.error || next.message, { id: `job-${next.id}` });
        }
      } catch (reason) {
        if (reason.status === 404) {
          setJob(null);
          toast.warning("The active job ended when the backend restarted.", {
            id: `job-${job.id}`,
          });
        } else {
          showError(reason, `job-${job.id}`);
        }
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [job, loadProject, navigate]);

  const jobActive = Boolean(
    job && !["succeeded", "failed"].includes(job.status),
  );
  const value = useMemo(
    () => ({
      projects,
      providers,
      voiceCatalog,
      job,
      setJob,
      jobActive,
      busy,
      setBusy,
      refreshProjects,
      loadProject,
    }),
    [
      projects,
      providers,
      voiceCatalog,
      job,
      jobActive,
      busy,
      refreshProjects,
      loadProject,
    ],
  );

  return (
    <AppContext.Provider value={value}>
      <Toaster />
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/projects" replace />} />
          <Route path="projects" element={<ProjectsScreen />} />
          <Route
            path="projects/:projectId/transcribe"
            element={<TranscribeScreen />}
          />
          <Route
            path="projects/:projectId/transcript"
            element={<TranscriptScreen />}
          />
          <Route
            path="projects/:projectId/export"
            element={<ExportScreen />}
          />
          <Route path="*" element={<Navigate to="/projects" replace />} />
        </Route>
      </Routes>
    </AppContext.Provider>
  );
}

function AppShell() {
  const { busy, setBusy, jobActive, refreshProjects } = useApp();
  const navigate = useNavigate();

  async function uploadVideo(event) {
    const file = event.target.files?.[0];
    if (!file || busy || jobActive) return;
    setBusy(true);
    toast.info("Uploading video…", { id: "upload-video" });
    try {
      const project = await api.createProject(file);
      await refreshProjects();
      toast.success("Video uploaded", { id: "upload-video" });
      navigate(`/projects/${project.project_id}/transcribe`);
    } catch (reason) {
      showError(reason, "upload-video");
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  return (
    <main className="relative mx-auto min-h-screen max-w-[1500px] p-4 sm:p-7 lg:p-10">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-5 border-b border-border pb-6">
        <Button
          variant="ghost"
          className="h-auto p-0 text-xl hover:bg-transparent"
          onClick={() => navigate("/projects")}
        >
          <Film className="text-primary" size={25} /> Demo Dubber
        </Button>
        <Button asChild size="lg">
          <label
            className={
              busy || jobActive ? "pointer-events-none opacity-45" : undefined
            }
          >
            <input
              className="sr-only"
              type="file"
              accept="video/mp4,video/quicktime,video/webm"
              onChange={uploadVideo}
              disabled={busy || jobActive}
            />
            <Plus size={18} /> New video
          </label>
        </Button>
      </header>
      <Outlet />
    </main>
  );
}
