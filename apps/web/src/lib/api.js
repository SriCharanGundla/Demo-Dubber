const API_ROOT = import.meta.env?.VITE_API_URL || "/api";

export function resolveApiUrl(path, apiRoot = API_ROOT) {
  if (!path || /^https?:\/\//i.test(path)) return path;
  if (apiRoot === "/api") return path;
  if (path.startsWith("/api/")) {
    return `${apiRoot.replace(/\/api\/?$/, "")}${path}`;
  }
  return `${apiRoot}${path.startsWith("/") ? path : `/${path}`}`;
}

async function request(path, options = {}) {
  const response = await fetch(`${API_ROOT}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(body.detail || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

export const api = {
  mediaUrl: resolveApiUrl,
  providers: () => request("/providers"),
  voices: () => request("/voices"),
  projects: () => request("/projects"),
  project: (id) => request(`/projects/${id}`),
  createProject: (file) => {
    const body = new FormData();
    body.append("video", file);
    return request("/projects", { method: "POST", body });
  },
  deleteProject: (id) => request(`/projects/${id}`, { method: "DELETE" }),
  renameProject: (id, title) =>
    request(`/projects/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
  transcribe: (id, configuration) =>
    request(`/projects/${id}/transcribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(configuration),
    }),
  job: (projectId, jobId) => request(`/projects/${projectId}/jobs/${jobId}`),
  activeJob: (projectId) => request(`/projects/${projectId}/jobs/active`),
  latestJob: (projectId) => request(`/projects/${projectId}/jobs/latest`),
  saveTranscript: (id, cues) =>
    request(`/projects/${id}/transcript`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cues: cues.map(({ index, text }) => ({ index, text })),
      }),
    }),
  render: (id) => request(`/projects/${id}/render`, { method: "POST" }),
  artifact: (id, name) => `${API_ROOT}/projects/${id}/artifacts/${name}`,
  transcriptExport: (id, format) =>
    `${API_ROOT}/projects/${id}/exports/${format}`,
  originalPreview: (id, kind, cueIndex) =>
    `${API_ROOT}/projects/${id}/previews/original/${kind}/${cueIndex}`,
  createTtsPreview: (id, cueIndex, configuration) =>
    request(`/projects/${id}/previews/tts/${cueIndex}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(configuration),
    }),
};
