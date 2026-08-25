const API_ROOT = import.meta.env.VITE_API_URL || "/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_ROOT}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

export const api = {
  providers: () => request("/providers"),
  projects: () => request("/projects"),
  project: (id) => request(`/projects/${id}`),
  createProject: (file) => {
    const body = new FormData();
    body.append("video", file);
    return request("/projects", { method: "POST", body });
  },
  deleteProject: (id) => request(`/projects/${id}`, { method: "DELETE" }),
  transcribe: (id, configuration) =>
    request(`/projects/${id}/transcribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(configuration),
    }),
  job: (projectId, jobId) => request(`/projects/${projectId}/jobs/${jobId}`),
  saveTranscript: (id, cues) =>
    request(`/projects/${id}/transcript`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cues }),
    }),
  render: (id) => request(`/projects/${id}/render`, { method: "POST" }),
  artifact: (id, name) => `${API_ROOT}/projects/${id}/artifacts/${name}`,
};
