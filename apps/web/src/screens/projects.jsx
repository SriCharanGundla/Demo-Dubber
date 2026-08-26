import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  FilePenLine,
  FolderOpen,
  Pencil,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { projectRoute, showError, useApp } from "@/lib/app-context";

function stageLabel(project) {
  if (project.active_job?.kind === "render") return "Rendering dubbed demo";
  if (project.active_job?.kind === "transcription") return "Transcribing audio";
  if (project.artifacts?.muxed_video) return "Ready to download";
  if (project.transcript_cues?.length) return "Transcript ready";
  return "Ready to transcribe";
}

export function ProjectsScreen() {
  const { projects, refreshProjects, jobActive } = useApp();
  const [editingId, setEditingId] = useState(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [savingId, setSavingId] = useState(null);
  const navigate = useNavigate();

  function beginRename(project) {
    setEditingId(project.project_id);
    setDraftTitle(project.title);
  }

  async function saveRename(project) {
    const title = draftTitle.trim();
    if (!title) return;
    setSavingId(project.project_id);
    try {
      await api.renameProject(project.project_id, title);
      await refreshProjects();
      setEditingId(null);
      toast.success("Project renamed", { id: `rename-${project.project_id}` });
    } catch (reason) {
      showError(reason, `rename-${project.project_id}`);
    } finally {
      setSavingId(null);
    }
  }

  function remove(project) {
    toast.warning(`Delete ${project.title}?`, {
      id: `delete-${project.project_id}`,
      description: "The project and all generated files will be removed.",
      action: {
        label: "Delete",
        onClick: async () => {
          try {
            await api.deleteProject(project.project_id);
            await refreshProjects();
            toast.success("Project deleted", {
              id: `delete-${project.project_id}`,
            });
          } catch (reason) {
            showError(reason, `delete-${project.project_id}`);
          }
        },
      },
      cancel: { label: "Cancel" },
      duration: 10000,
    });
  }

  return (
    <section>
      <div className="mb-7 max-w-3xl">
        <h1 className="font-display text-4xl font-bold tracking-tight sm:text-5xl">
          Projects
        </h1>
        <p className="mt-2 text-muted-foreground">
          Resume a saved demo exactly where you left it.
        </p>
      </div>

      {projects.length === 0 ? (
        <Card className="grid min-h-[420px] place-items-center border-dashed text-center">
          <div className="max-w-sm">
            <span className="mx-auto mb-5 grid h-16 w-16 place-items-center rounded-2xl bg-primary/10 text-primary">
              <FolderOpen size={28} />
            </span>
            <h2 className="font-display text-2xl font-bold">No projects yet</h2>
            <p className="mt-2 text-muted-foreground">
              Use New video to upload MP4, MOV, M4V, or WebM.
            </p>
          </div>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {projects.map((project) => (
            <Card key={project.project_id} className="grid gap-5 overflow-hidden">
              <div className="flex min-w-0 items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  {editingId === project.project_id ? (
                    <form
                      className="flex gap-2"
                      onSubmit={(event) => {
                        event.preventDefault();
                        saveRename(project);
                      }}
                    >
                      <Input
                        autoFocus
                        value={draftTitle}
                        maxLength={120}
                        onChange={(event) => setDraftTitle(event.target.value)}
                        disabled={savingId === project.project_id}
                        aria-label="Project name"
                      />
                      <Button
                        size="sm"
                        type="submit"
                        disabled={!draftTitle.trim() || savingId === project.project_id}
                      >
                        Save
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        type="button"
                        onClick={() => setEditingId(null)}
                        aria-label="Cancel rename"
                      >
                        <X size={16} />
                      </Button>
                    </form>
                  ) : (
                    <>
                      <div className="flex min-w-0 items-center gap-2">
                        <h2 className="truncate font-display text-xl font-bold">
                          {project.title}
                        </h2>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => beginRename(project)}
                          disabled={jobActive}
                          aria-label={`Rename ${project.title}`}
                        >
                          <Pencil size={15} />
                        </Button>
                      </div>
                      <p className="mt-1 truncate text-xs text-muted-foreground">
                        {project.project_id}
                      </p>
                    </>
                  )}
                </div>
                <Badge
                  variant={project.artifacts?.muxed_video ? "success" : "info"}
                >
                  {stageLabel(project)}
                </Badge>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  onClick={() => navigate(projectRoute(project))}
                  disabled={jobActive}
                >
                  Resume <ArrowRight size={16} />
                </Button>
                {project.transcript_cues?.length > 0 && (
                  <Button
                    variant="outline"
                    onClick={() =>
                      navigate(`/projects/${project.project_id}/transcript`)
                    }
                    disabled={jobActive}
                  >
                    <FilePenLine size={16} /> Edit transcript
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  className="ml-auto text-destructive"
                  onClick={() => remove(project)}
                  disabled={jobActive}
                  aria-label={`Delete ${project.title}`}
                >
                  <Trash2 size={17} />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}
