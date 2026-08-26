import { Navigate, useNavigate } from "react-router-dom";
import { Download, FilePenLine, LoaderCircle } from "lucide-react";

import { JobProgress } from "@/components/job-progress";
import { ProjectSteps } from "@/components/project-steps";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useProject } from "@/hooks/use-project";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";

export function ExportScreen() {
  const { project, loading } = useProject();
  const { job } = useApp();
  const navigate = useNavigate();

  if (loading && !project) return <Loading />;
  if (!project) return <Navigate to="/projects" replace />;
  if (!project.transcript_cues?.length) {
    return <Navigate to={`/projects/${project.project_id}/transcribe`} replace />;
  }

  const currentJob =
    job?.project_id === project.project_id && job.kind === "render" ? job : null;
  const rendered = Boolean(project.artifacts?.muxed_video);

  if (!rendered && !currentJob) {
    return <Navigate to={`/projects/${project.project_id}/transcript`} replace />;
  }

  return (
    <section className="mx-auto max-w-5xl">
      <ProjectSteps project={project} active="export" />
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-bold">Export</h1>
          <p className="mt-1 text-muted-foreground">{project.title}</p>
        </div>
        <Button
          variant="outline"
          onClick={() =>
            navigate(`/projects/${project.project_id}/transcript`)
          }
        >
          <FilePenLine size={16} /> Return to editing
        </Button>
      </div>

      <div className="grid gap-5">
        {currentJob && <JobProgress job={currentJob} />}

        {rendered && (
          <Card>
            <h2 className="font-display text-xl font-bold">Dubbed demo</h2>
            <p className="mb-4 mt-1 text-sm text-muted-foreground">
              Preview the final result, then download any supporting asset.
            </p>
            <video
              className="mb-5 max-h-[560px] w-full rounded-xl bg-black"
              controls
              src={api.artifact(project.project_id, "muxed_video")}
            />
            <div className="flex flex-wrap gap-2">
              <Button asChild>
                <a href={api.artifact(project.project_id, "muxed_video")}>
                  <Download size={16} /> Dubbed MP4
                </a>
              </Button>
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
              <Button asChild variant="outline">
                <a href={api.artifact(project.project_id, "narration_wav")}>
                  <Download size={16} /> Narration WAV
                </a>
              </Button>
            </div>
          </Card>
        )}
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
