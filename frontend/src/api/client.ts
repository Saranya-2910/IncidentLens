import type {
  ApiKeyCreatedResponse,
  ApiKeyItem,
  AuthResponse,
  BatchUploadResponse,
  DemoScenarioItem,
  ErrorPattern,
  ExplainTriggerResponse,
  Incident,
  IncidentDetail,
  IncidentReport,
  LoadDemoDataResponse,
  LogBatch,
  LogEvent,
  PaginatedResponse,
  Project,
  ProjectStats,
  SimilarIncidentsResponse,
  User,
} from "../types/api";

const API_BASE_URL =
  import.meta.env.VITE_API_URL?.replace(/\/+$/, "") || "/api/v1";

const TOKEN_STORAGE_KEY = "incidentlens_token";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function getStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    // ignore storage restriction
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(options.headers || {});

  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (response.status === 204) {
    return undefined as T;
  }

  let data: unknown = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    data = await response.json();
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    if (
      typeof data === "object" &&
      data !== null &&
      "error" in data &&
      typeof (data as { error: { code?: string; message?: string } }).error === "object"
    ) {
      const errObj = (data as { error: { code?: string; message?: string } }).error;
      throw new ApiError(
        response.status,
        errObj.code || "API_ERROR",
        errObj.message || response.statusText
      );
    }
    throw new ApiError(
      response.status,
      "HTTP_ERROR",
      typeof data === "string" ? data : response.statusText
    );
  }

  return data as T;
}

export const apiClient = {
  // Authentication
  register: async (payload: {
    name: string;
    email: string;
    password: string;
  }): Promise<AuthResponse> => {
    const res = await request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setStoredToken(res.access_token);
    return res;
  },

  login: async (payload: {
    email: string;
    password: string;
  }): Promise<AuthResponse> => {
    const res = await request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setStoredToken(res.access_token);
    return res;
  },

  logout: async (): Promise<void> => {
    try {
      await request<void>("/auth/logout", { method: "POST" });
    } finally {
      setStoredToken(null);
    }
  },

  getMe: (): Promise<User> => request<User>("/auth/me"),

  // Projects
  listProjects: (): Promise<Project[]> => request<Project[]>("/projects"),

  createProject: (payload: {
    name: string;
    description?: string;
  }): Promise<Project> =>
    request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getProject: (projectId: string): Promise<Project> =>
    request<Project>(`/projects/${projectId}`),

  updateProject: (
    projectId: string,
    payload: { name?: string; description?: string }
  ): Promise<Project> =>
    request<Project>(`/projects/${projectId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteProject: (projectId: string): Promise<void> =>
    request<void>(`/projects/${projectId}`, { method: "DELETE" }),

  getProjectStats: (projectId: string): Promise<ProjectStats> =>
    request<ProjectStats>(`/projects/${projectId}/stats`),

  // API Keys
  listApiKeys: (projectId: string): Promise<ApiKeyItem[]> =>
    request<ApiKeyItem[]>(`/projects/${projectId}/api-keys`),

  createApiKey: (
    projectId: string,
    label: string
  ): Promise<ApiKeyCreatedResponse> =>
    request<ApiKeyCreatedResponse>(`/projects/${projectId}/api-keys`, {
      method: "POST",
      body: JSON.stringify({ label }),
    }),

  revokeApiKey: (projectId: string, keyId: string): Promise<void> =>
    request<void>(`/projects/${projectId}/api-keys/${keyId}`, {
      method: "DELETE",
    }),

  // Logs & Demo Seeding
  listDemoScenarios: (): Promise<DemoScenarioItem[]> =>
    request<DemoScenarioItem[]>("/projects/demo-scenarios"),

  loadDemoData: (
    projectId: string,
    scenarioId?: string
  ): Promise<LoadDemoDataResponse> =>
    request<LoadDemoDataResponse>(`/projects/${projectId}/demo-data`, {
      method: "POST",
      body: JSON.stringify({ scenario_id: scenarioId || null }),
    }),

  uploadLogFile: (projectId: string, file: File): Promise<BatchUploadResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    return request<BatchUploadResponse>(`/projects/${projectId}/logs/upload`, {
      method: "POST",
      body: formData,
    });
  },

  listBatches: (projectId: string): Promise<LogBatch[]> =>
    request<LogBatch[]>(`/projects/${projectId}/batches`),

  getBatch: (batchId: string): Promise<LogBatch> =>
    request<LogBatch>(`/batches/${batchId}`),

  searchEvents: (
    projectId: string,
    params: {
      service?: string;
      level?: string;
      pattern_id?: string;
      text?: string;
      limit?: number;
      offset?: number;
    } = {}
  ): Promise<PaginatedResponse<LogEvent>> => {
    const qs = new URLSearchParams();
    if (params.service) qs.set("service", params.service);
    if (params.level) qs.set("level", params.level);
    if (params.pattern_id) qs.set("pattern_id", params.pattern_id);
    if (params.text) qs.set("text", params.text);
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    if (params.offset !== undefined) qs.set("offset", String(params.offset));
    const queryStr = qs.toString();
    return request<PaginatedResponse<LogEvent>>(
      `/projects/${projectId}/events${queryStr ? `?${queryStr}` : ""}`
    );
  },

  getEventDetail: (projectId: string, eventId: number): Promise<LogEvent> =>
    request<LogEvent>(`/projects/${projectId}/events/${eventId}`),

  // Patterns
  listPatterns: (
    projectId: string,
    params: {
      level?: string;
      service?: string;
      limit?: number;
      offset?: number;
    } = {}
  ): Promise<PaginatedResponse<ErrorPattern>> => {
    const qs = new URLSearchParams();
    if (params.level) qs.set("level", params.level);
    if (params.service) qs.set("service", params.service);
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    if (params.offset !== undefined) qs.set("offset", String(params.offset));
    const queryStr = qs.toString();
    return request<PaginatedResponse<ErrorPattern>>(
      `/projects/${projectId}/patterns${queryStr ? `?${queryStr}` : ""}`
    );
  },

  // Incidents & Explanations
  listIncidents: (
    projectId: string,
    params: {
      status?: string;
      severity?: string;
      limit?: number;
      offset?: number;
    } = {}
  ): Promise<PaginatedResponse<Incident>> => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.severity) qs.set("severity", params.severity);
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    if (params.offset !== undefined) qs.set("offset", String(params.offset));
    const queryStr = qs.toString();
    return request<PaginatedResponse<Incident>>(
      `/projects/${projectId}/incidents${queryStr ? `?${queryStr}` : ""}`
    );
  },

  getIncidentDetail: (incidentId: string): Promise<IncidentDetail> =>
    request<IncidentDetail>(`/incidents/${incidentId}`),

  triggerExplain: (
    incidentId: string,
    force = false
  ): Promise<ExplainTriggerResponse> =>
    request<ExplainTriggerResponse>(`/incidents/${incidentId}/explain`, {
      method: "POST",
      body: JSON.stringify({ force }),
    }),

  getIncidentReport: (incidentId: string): Promise<IncidentReport> =>
    request<IncidentReport>(`/incidents/${incidentId}/report`),

  getSimilarIncidents: (incidentId: string): Promise<SimilarIncidentsResponse> =>
    request<SimilarIncidentsResponse>(`/incidents/${incidentId}/similar`),

  resolveIncident: (
    incidentId: string,
    payload: { status: "open" | "resolved"; resolution_note?: string }
  ): Promise<Incident> =>
    request<Incident>(`/incidents/${incidentId}/resolve`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
