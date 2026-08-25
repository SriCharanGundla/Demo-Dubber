import { useCallback, useEffect, useState } from "react";
import {
  Download,
  Film,
  LoaderCircle,
  Mic2,
  Plus,
  Save,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";

const emptyProviders = { cleanup: [], transcription: [] };

export default function App() {
  const [projects, setProjects] = useState([]);
  const [current, setCurrent] = useState(null);
  const [providers, setProviders] = useState(emptyProviders);
  const [transcriptionProvider, setTranscriptionProvider] = useState("openai");
  const [cleanupProvider, setCleanupProvider] = useState("openai");
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(
    async (projectId) => {
      const result = await api.projects();
      setProjects(result.projects);
      const selectedId = projectId || current?.project_id;
      if (selectedId)
        setCurrent(
          result.projects.find((item) => item.project_id === selectedId) ||
            null,
        );
    },
    [current?.project_id],
  );

  useEffect(() => {
    Promise.all([api.projects(), api.providers()])
      .then(([projectResult, providerResult]) => {
        setProjects(projectResult.projects);
        setProviders(providerResult);
      })
      .catch((reason) => setError(reason.message));
  }, []);

  useEffect(() => {
    if (!job || ["succeeded", "failed"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.job(job.project_id, job.id);
        setJob(next);
        if (next.status === "succeeded") await refresh(next.project_id);
        if (next.status === "failed") setError(next.error || next.message);
      } catch (reason) {
        setError(reason.message);
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [job, refresh]);

  async function uploadVideo(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const project = await api.createProject(file);
      setCurrent(project);
      await refresh(project.project_id);
    } catch (reason) {
      setError(reason.message);
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  async function startTranscription() {
    setError("");
    try {
      setJob(
        await api.transcribe(current.project_id, {
          transcription_provider: transcriptionProvider,
          cleanup_provider: cleanupProvider,
        }),
      );
    } catch (reason) {
      setError(reason.message);
    }
  }

  async function saveTranscript() {
    setBusy(true);
    setError("");
    try {
      const result = await api.saveTranscript(
        current.project_id,
        current.transcript_cues,
      );
      setCurrent({ ...current, transcript_cues: result.cues });
      await refresh(current.project_id);
    } catch (reason) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function render() {
    setError("");
    try {
      setJob(await api.render(current.project_id));
    } catch (reason) {
      setError(reason.message);
    }
  }

  async function remove(project) {
    if (!window.confirm(`Delete ${project.title}? This cannot be undone.`))
      return;
    try {
      await api.deleteProject(project.project_id);
      if (current?.project_id === project.project_id) setCurrent(null);
      await refresh();
    } catch (reason) {
      setError(reason.message);
    }
  }

  const progress = job?.total
    ? Math.round(((job.completed || 0) / job.total) * 100)
    : job?.status === "succeeded"
      ? 100
      : 18;

  return (
    <main className="relative mx-auto min-h-screen max-w-[1500px] p-4 sm:p-7 lg:p-10">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-5 border-b border-border pb-7">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-bold uppercase tracking-[.22em] text-primary">
            <Mic2 size={18} /> Demo Dubber
          </div>
          <h1 className="max-w-3xl font-display text-4xl font-bold leading-[.95] tracking-tight sm:text-6xl">
            Turn a rough demo into a polished voiceover.
          </h1>
        </div>
        <label className="cursor-pointer">
          <input
            className="sr-only"
            type="file"
            accept="video/mp4,video/quicktime,video/webm"
            onChange={uploadVideo}
            disabled={busy}
          />
          <span className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-3 text-sm font-bold text-primary-foreground">
            <Plus size={18} /> New video
          </span>
        </label>
      </header>

      {error && (
        <div
          role="alert"
          className="mb-5 rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"
        >
          {error}
        </div>
      )}
      {job && (
        <Card className="mb-5">
          <div className="mb-3 flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 font-semibold">
              {job.status === "running" && (
                <LoaderCircle className="animate-spin" size={17} />
              )}
              {job.message}
            </span>
            <Badge>{job.status}</Badge>
          </div>
          <Progress value={progress} />
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-[290px_minmax(0,1fr)]">
        <aside>
          <Card className="sticky top-6">
            <h2 className="mb-1 font-display text-lg font-bold">Projects</h2>
            <p className="mb-4 text-sm text-muted-foreground">
              Resume anything saved locally.
            </p>
            <div className="grid gap-2">
              {projects.map((project) => (
                <div
                  key={project.project_id}
                  className={`group flex items-center gap-2 rounded-xl border p-2 ${current?.project_id === project.project_id ? "border-primary bg-primary/5" : "border-transparent hover:bg-muted/60"}`}
                >
                  <button
                    className="min-w-0 flex-1 cursor-pointer text-left"
                    onClick={() => setCurrent(project)}
                  >
                    <span className="block truncate text-sm font-semibold">
                      {project.title}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {project.stage}
                    </span>
                  </button>
                  <Button
                    variant="ghost"
                    className="h-8 w-8 p-0 opacity-60 group-hover:opacity-100"
                    onClick={() => remove(project)}
                    aria-label={`Delete ${project.title}`}
                  >
                    <Trash2 size={15} />
                  </Button>
                </div>
              ))}
              {projects.length === 0 && (
                <p className="rounded-xl bg-muted/60 p-4 text-sm text-muted-foreground">
                  No projects yet. Upload a video to begin.
                </p>
              )}
            </div>
          </Card>
        </aside>

        {!current ? (
          <Card className="grid min-h-[480px] place-items-center border-dashed text-center">
            <div className="max-w-sm">
              <span className="mx-auto mb-5 grid h-16 w-16 place-items-center rounded-2xl bg-primary/10 text-primary">
                <Upload size={28} />
              </span>
              <h2 className="font-display text-2xl font-bold">
                Drop in your first demo
              </h2>
              <p className="mt-2 text-muted-foreground">
                Upload MP4, MOV, M4V, or WebM. Your source files and projects
                stay in your configured workspace.
              </p>
            </div>
          </Card>
        ) : (
          <Workspace
            project={current}
            setProject={setCurrent}
            providers={providers}
            transcriptionProvider={transcriptionProvider}
            setTranscriptionProvider={setTranscriptionProvider}
            cleanupProvider={cleanupProvider}
            setCleanupProvider={setCleanupProvider}
            startTranscription={startTranscription}
            saveTranscript={saveTranscript}
            render={render}
            busy={busy}
          />
        )}
      </div>
    </main>
  );
}

function Workspace({
  project,
  setProject,
  providers,
  transcriptionProvider,
  setTranscriptionProvider,
  cleanupProvider,
  setCleanupProvider,
  startTranscription,
  saveTranscript,
  render,
  busy,
}) {
  const hasTranscript = project.transcript_cues?.length > 0;
  const rendered = project.artifacts?.muxed_video;
  function editCue(index, text) {
    setProject({
      ...project,
      transcript_cues: project.transcript_cues.map((cue, position) =>
        position === index
          ? { ...cue, text, over_limit: text.length > cue.char_limit }
          : cue,
      ),
    });
  }
  return (
    <div className="grid gap-5">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Badge className="mb-3">{project.stage}</Badge>
            <h2 className="font-display text-2xl font-bold">{project.title}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {project.project_id}
            </p>
          </div>
          <Film className="text-primary" size={34} />
        </div>
      </Card>
      {!hasTranscript && (
        <Card>
          <div className="mb-5">
            <h3 className="font-display text-xl font-bold">
              1. Transcribe and clean
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Choose speech recognition and a compatible cleanup model.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Select
              label="Transcription"
              value={transcriptionProvider}
              onValueChange={setTranscriptionProvider}
              options={providers.transcription}
            />
            <Select
              label="Cleanup model"
              value={cleanupProvider}
              onValueChange={setCleanupProvider}
              options={providers.cleanup.map((item) => ({
                ...item,
                label: `${item.label}${item.configured ? "" : " · key needed"}`,
              }))}
            />
          </div>
          <Button className="mt-5" onClick={startTranscription}>
            <Sparkles size={17} /> Start transcription
          </Button>
        </Card>
      )}
      {hasTranscript && (
        <Card>
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h3 className="font-display text-xl font-bold">
                2. Edit transcript
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Timing is locked. Keep each line inside its narration budget.
              </p>
            </div>
            <Button variant="outline" onClick={saveTranscript} disabled={busy}>
              <Save size={16} /> Save edits
            </Button>
          </div>
          <div className="grid max-h-[620px] gap-3 overflow-y-auto pr-1">
            {project.transcript_cues.map((cue, index) => (
              <div
                key={cue.index}
                className={`grid gap-3 rounded-xl border p-3 sm:grid-cols-[105px_1fr] ${cue.over_limit ? "border-destructive/50 bg-destructive/5" : "border-border"}`}
              >
                <div className="text-xs font-medium text-muted-foreground">
                  <span className="block text-foreground">Cue {index + 1}</span>
                  {cue.start_seconds.toFixed(2)}–{cue.end_seconds.toFixed(2)}s
                </div>
                <div>
                  <textarea
                    className="min-h-20 w-full resize-y rounded-lg border border-border bg-background p-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                    value={cue.text}
                    onChange={(event) => editCue(index, event.target.value)}
                  />
                  <div
                    className={`mt-1 text-right text-xs ${cue.over_limit ? "text-destructive" : "text-muted-foreground"}`}
                  >
                    {cue.text.length} / {cue.char_limit} characters
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button
              onClick={render}
              disabled={project.transcript_cues.some((cue) => cue.over_limit)}
            >
              <Mic2 size={17} /> Render voiceover
            </Button>
            <a
              className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-semibold"
              href={api.artifact(project.project_id, "transcript_txt")}
            >
              <Download size={16} /> Transcript
            </a>
          </div>
        </Card>
      )}
      {rendered && (
        <Card>
          <h3 className="font-display text-xl font-bold">3. Download result</h3>
          <p className="mb-4 mt-1 text-sm text-muted-foreground">
            Your dubbed video and supporting files are ready.
          </p>
          <div className="flex flex-wrap gap-3">
            <a
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground"
              href={api.artifact(project.project_id, "muxed_video")}
            >
              <Download size={16} /> Dubbed MP4
            </a>
            <a
              className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-semibold"
              href={api.artifact(project.project_id, "subtitled_srt")}
            >
              <Download size={16} /> Subtitles
            </a>
            <a
              className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-semibold"
              href={api.artifact(project.project_id, "narration_wav")}
            >
              <Download size={16} /> Narration
            </a>
          </div>
        </Card>
      )}
    </div>
  );
}
