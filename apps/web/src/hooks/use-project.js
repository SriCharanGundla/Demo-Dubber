import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { showError, useApp } from "@/lib/app-context";

export function useProject() {
  const { projectId } = useParams();
  const { projects, loadProject } = useApp();
  const [loading, setLoading] = useState(true);
  const project = projects.find((item) => item.project_id === projectId) || null;

  useEffect(() => {
    setLoading(true);
    loadProject(projectId)
      .catch((reason) => showError(reason, `load-project-${projectId}`))
      .finally(() => setLoading(false));
  }, [loadProject, projectId]);

  return { project, projectId, loading };
}
