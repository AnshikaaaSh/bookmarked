// Every call to the FastAPI backend goes through here.

const BASE = ""; // same origin — the API serves this page

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, options);
  } catch {
    throw new ApiError("Can't reach the backend. Is `uvicorn backend.main:app --reload` running?", 0);
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    /* non-JSON error body */
  }

  if (!response.ok) {
    throw new ApiError(payload?.detail || `Request failed (${response.status})`, response.status);
  }
  return payload;
}

const postJSON = (path, body) =>
  request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const api = {
  health: () => request("/api/health"),
  sources: () => request("/api/sources"),
  ask: (question, opts = {}) => postJSON("/api/ask", { question, ...opts }),
  recommend: (liked) => postJSON("/api/recommend", { liked }),
  outline: (topic) => postJSON("/api/write/outline", { topic }),
  graphs: () => request("/api/graphs"),
  graph: (sourceId, position) => request(`/api/graph/${encodeURIComponent(sourceId)}?position=${position}`),
};

export { ApiError };
