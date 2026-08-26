import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import {
  Download,
  Film,
  LoaderCircle,
  Mic2,
  Play,
  Save,
  Volume2,
} from "lucide-react";
import { toast } from "sonner";

import { ProjectSteps } from "@/components/project-steps";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useProject } from "@/hooks/use-project";
import { api } from "@/lib/api";
import { showError, useApp } from "@/lib/app-context";

export function TranscriptScreen() {
  const { project, loading } = useProject();
  const { loadProject, busy, setBusy, jobActive, setJob } = useApp();
  const [cues, setCues] = useState([]);
  const [previews, setPreviews] = useState({});
  const navigate = useNavigate();

  useEffect(() => {
    if (project?.transcript_cues) setCues(project.transcript_cues);
  }, [project?.project_id, project?.updated_at, project?.transcript_cues]);

  if (loading && !project) return <Loading />;
  if (!project) return <Navigate to="/projects" replace />;
  if (!project.transcript_cues?.length) {
    return <Navigate to={`/projects/${project.project_id}/transcribe`} replace />;
  }

  function editCue(position, text) {
    setCues((current) =>
      current.map((cue, index) =>
        index === position
          ? { ...cue, text, over_limit: text.length > cue.char_limit }
          : cue,
      ),
    );
    setPreviews((current) => {
      const next = { ...current };
      delete next[position];
      return next;
    });
  }

  async function save() {
    setBusy(true);
    toast.info("Saving transcript…", { id: "save-transcript" });
    try {
      await api.saveTranscript(project.project_id, cues);
      const saved = await loadProject(project.project_id);
      setCues(saved.transcript_cues);
      toast.success("Transcript saved", { id: "save-transcript" });
      return saved;
    } catch (reason) {
      showError(reason, "save-transcript");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function continueToExport() {
    const saved = await save();
    if (!saved) return;

    setBusy(true);
    try {
      const next = await api.render(project.project_id);
      setJob(next);
      toast.info("Dubbed demo render started", { id: `job-${next.id}` });
      navigate(`/projects/${project.project_id}/export`);
    } catch (reason) {
      showError(reason, "start-render");
    } finally {
      setBusy(false);
    }
  }

  function toggleOriginalPreview(position, kind) {
    setPreviews((current) => ({
      ...current,
      [position]: {
        ...current[position],
        original: current[position]?.original === kind ? null : kind,
      },
    }));
  }

  async function testTts(position) {
    const cue = cues[position];
    setPreviews((current) => ({
      ...current,
      [position]: { ...current[position], ttsLoading: true },
    }));
    try {
      const preview = await api.createTtsPreview(project.project_id, cue.index, {
        text: cue.text,
      });
      setPreviews((current) => ({
        ...current,
        [position]: { ...current[position], ttsLoading: false, tts: preview },
      }));
      toast.success(`Cue ${position + 1} preview ready`, {
        id: `tts-${project.project_id}-${cue.index}`,
      });
    } catch (reason) {
      setPreviews((current) => ({
        ...current,
        [position]: { ...current[position], ttsLoading: false },
      }));
      showError(reason, `tts-${project.project_id}-${cue.index}`);
    }
  }

  const hasErrors = cues.some((cue) => cue.over_limit);

  return (
    <section className="mx-auto max-w-6xl">
      <ProjectSteps project={project} active="transcript" />
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-bold">Edit transcript</h1>
          <p className="mt-1 text-muted-foreground">{project.title}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={save}
            disabled={busy || jobActive}
            aria-label="Save edits"
            title="Save edits"
          >
            <Save size={16} />
            <span className="sr-only">Save edits</span>
          </Button>
          <Button
            onClick={continueToExport}
            disabled={busy || jobActive || hasErrors}
          >
            Export
          </Button>
        </div>
      </div>

      <Card className="mb-5">
        <h2 className="font-display text-lg font-bold">Transcript</h2>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <a href={api.transcriptExport(project.project_id, "srt")}>
              <Download size={16} /> SRT
            </a>
          </Button>
          <Button asChild variant="outline">
            <a href={api.transcriptExport(project.project_id, "txt")}>
              <Download size={16} /> TXT
            </a>
          </Button>
        </div>
      </Card>

      <div className="grid gap-4">
        {cues.map((cue, position) => {
          const preview = previews[position] || {};
          const originalAudio = api.originalPreview(
            project.project_id,
            "audio",
            cue.index,
          );
          const originalVideo = api.originalPreview(
            project.project_id,
            "video",
            cue.index,
          );
          return (
            <Card
              key={cue.index}
              className={cue.over_limit ? "border-destructive/50" : undefined}
            >
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-display font-bold">Cue {position + 1}</h2>
                  <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-medium text-muted-foreground">
                    <span className="tabular-nums">
                      {cue.start_seconds.toFixed(2)}–{cue.end_seconds.toFixed(2)}s
                    </span>
                    <span aria-hidden="true">·</span>
                    <span className="tabular-nums">
                      cue duration {(cue.end_seconds - cue.start_seconds).toFixed(2)}s
                    </span>
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  {cue.speaker && <Badge>{cue.speaker}</Badge>}
                  <Button
                    size="icon"
                    variant={preview.original === "audio" ? "default" : "outline"}
                    className="h-8 w-8"
                    onClick={() => toggleOriginalPreview(position, "audio")}
                    aria-label={`Toggle original audio for cue ${position + 1}`}
                    aria-pressed={preview.original === "audio"}
                    title="Original audio"
                  >
                    <Volume2 size={15} />
                  </Button>
                  <Button
                    size="icon"
                    variant={preview.original === "video" ? "default" : "outline"}
                    className="h-8 w-8"
                    onClick={() => toggleOriginalPreview(position, "video")}
                    aria-label={`Toggle original video for cue ${position + 1}`}
                    aria-pressed={preview.original === "video"}
                    title="Original video"
                  >
                    <Film size={15} />
                  </Button>
                  <Button
                    size="icon"
                    variant="outline"
                    className="h-8 w-8"
                    onClick={() => testTts(position)}
                    disabled={
                      busy || jobActive || preview.ttsLoading || !cue.text.trim()
                    }
                    aria-label={`Test fitted TTS for cue ${position + 1}`}
                    title="Test fitted TTS"
                  >
                    {preview.ttsLoading ? (
                      <LoaderCircle className="animate-spin" size={15} />
                    ) : (
                      <Mic2 size={15} />
                    )}
                  </Button>
                </div>
              </div>

              <div className="grid items-start gap-4 lg:grid-cols-2">
                <label className="text-sm font-medium">
                  <span className="mb-2 block">Original</span>
                  <Textarea
                    className="h-24 min-h-24"
                    value={cue.original_text}
                    disabled
                  />
                </label>
                <label className="text-sm font-medium">
                  <span className="mb-2 block">Editable</span>
                  <Textarea
                    className="h-24 min-h-24"
                    value={cue.text}
                    onChange={(event) => editCue(position, event.target.value)}
                    disabled={busy || jobActive}
                  />
                  <span
                    className={`mt-1 block text-right text-xs ${cue.over_limit ? "text-destructive" : "text-muted-foreground"}`}
                  >
                    {cue.text.length} / {cue.char_limit} characters
                  </span>
                </label>
              </div>

              {preview.original === "audio" && (
                <audio className="mt-4 w-full" controls src={originalAudio} />
              )}
              {preview.original === "video" && (
                <video
                  className="mt-4 max-h-80 w-full rounded-xl bg-black"
                  controls
                  src={originalVideo}
                />
              )}
              {preview.tts && (
                <div className="mt-4 grid gap-3 rounded-xl bg-muted/50 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={preview.tts.fitted ? "success" : "warning"}>
                      {preview.tts.fitted ? "Fits cue" : "Needs shorter text"}
                    </Badge>
                    <span className="text-sm text-muted-foreground">
                      Generated {preview.tts.duration_seconds.toFixed(2)}s / available{" "}
                      {preview.tts.available_seconds.toFixed(2)}s · speed{" "}
                      {preview.tts.applied_speed.toFixed(2)}×
                    </span>
                  </div>
                  <div>
                    <p className="mb-1 text-xs font-medium text-muted-foreground">
                      Natural delivery ·{" "}
                      {preview.tts.natural_duration_seconds.toFixed(2)}s
                    </p>
                    <audio
                      className="w-full"
                      controls
                      src={preview.tts.natural_audio_url}
                    />
                  </div>
                  <div>
                    <p className="mb-1 flex items-center gap-1 text-xs font-medium text-muted-foreground">
                      <Play size={12} /> Fitted delivery
                    </p>
                    <audio
                      className="w-full"
                      controls
                      src={preview.tts.audio_url}
                    />
                  </div>
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </section>
  );
}

function Loading() {
  return (
    <Card className="grid min-h-64 place-items-center">
      <LoaderCircle className="animate-spin text-primary" />
    </Card>
  );
}
