import { createContext, useContext } from "react";
import { toast } from "sonner";

export const AppContext = createContext(null);

export function showError(reason, id) {
  toast.error(reason?.message || String(reason), { id });
}

export function projectRoute(project) {
  if (
    project.artifacts?.muxed_video ||
    project.active_job?.kind === "render"
  ) {
    return `/projects/${project.project_id}/export`;
  }
  if (project.transcript_cues?.length) {
    return `/projects/${project.project_id}/transcript`;
  }
  return `/projects/${project.project_id}/transcribe`;
}

export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp must be used inside App");
  return value;
}
