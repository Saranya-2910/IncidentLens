import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthPage } from "./pages/AuthPage";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { apiClient } from "./api/client";
import * as AuthHook from "./hooks/useAuth";

vi.mock("./api/client", async () => {
  const actual = await vi.importActual<typeof import("./api/client")>("./api/client");
  return {
    ...actual,
    apiClient: {
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      getMe: vi.fn(),
      getProject: vi.fn(),
      getIncidentDetail: vi.fn(),
      getIncidentReport: vi.fn(),
      getSimilarIncidents: vi.fn(),
      getEventDetail: vi.fn(),
      triggerExplain: vi.fn(),
      resolveIncident: vi.fn(),
    },
  };
});

describe("IncidentLens Frontend", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("toggles between Sign In and Create Account on AuthPage", async () => {
    const user = userEvent.setup();
    vi.spyOn(AuthHook, "useAuth").mockReturnValue({
      user: null,
      isLoading: false,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <MemoryRouter>
        <AuthPage />
      </MemoryRouter>
    );

    expect(screen.getByRole("button", { name: /Sign in to Workspace/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Create account/i }));
    expect(screen.getByLabelText(/Full Name/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Account" })).toBeInTheDocument();
  });

  it("renders verified report, flags unsupported claims, and reveals cited log lines on click", async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    vi.spyOn(AuthHook, "useAuth").mockReturnValue({
      user: {
        id: "user-1",
        name: "Alice SRE",
        email: "alice@example.com",
        created_at: "2026-11-10T10:00:00Z",
      },
      isLoading: false,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    vi.mocked(apiClient.getProject).mockResolvedValue({
      id: "proj-1",
      user_id: "user-1",
      name: "Prod API",
      description: "Test",
      created_at: "2026-11-10T10:00:00Z",
    });

    vi.mocked(apiClient.getIncidentDetail).mockResolvedValue({
      id: "inc-1",
      project_id: "proj-1",
      status: "open",
      severity: "critical",
      started_at: "2026-11-10T14:00:00Z",
      ended_at: "2026-11-10T14:05:00Z",
      origin_pattern_id: "pat-1",
      origin_pattern_template: "QueuePool limit of size <NUM> reached",
      affected_services: ["checkout-service", "api-gateway"],
      event_count: 15,
      resolution_note: null,
      resolved_at: null,
      created_at: "2026-11-10T14:05:00Z",
      origin_candidates: [
        {
          pattern_id: "pat-1",
          score: 120,
          service: "checkout-service",
          template: "QueuePool limit of size <NUM> reached",
          level: "ERROR",
          count: 10,
          first_seen: "2026-11-10T14:00:00Z",
          reason: "Appeared at onset; Backend origin service",
        },
      ],
      patterns: [],
      timeline: [],
    });

    vi.mocked(apiClient.getIncidentReport).mockResolvedValue({
      id: "rep-1",
      incident_id: "inc-1",
      version: 1,
      status: "done",
      summary: "Connection pool exhausted in checkout-service.",
      root_cause: "SQLAlchemy QueuePool saturated at max 20 connections.",
      confidence: "high",
      severity: "critical",
      affected_services: ["checkout-service"],
      suggested_fixes: ["Increase pool size to 50"],
      claims: [
        {
          text: "QueuePool timed out waiting for connection.",
          cited_line_ids: ["L1"],
          cited_event_ids: [101],
          invalid_citations: [],
          supported: true,
          status: "supported",
        },
        {
          text: "Hallucinated backup wipe happened.",
          cited_line_ids: [],
          cited_event_ids: [],
          invalid_citations: ["L999"],
          supported: false,
          status: "unsupported",
        },
      ],
      evidence_lines: [
        {
          short_id: "L1",
          event_id: 101,
          ts: "2026-11-10T14:00:01Z",
          service: "checkout-service",
          level: "ERROR",
          message: "TimeoutError: QueuePool limit of size 20 overflow 10 reached",
        },
      ],
      validation_status: "partial",
      unsupported_claim_count: 1,
      model_name: "gemini-2.0-flash",
      prompt_version: "v1.0",
      input_tokens: 450,
      output_tokens: 180,
      total_incident_events: 1500,
      selected_evidence_lines: 12,
      error: null,
      created_at: "2026-11-10T14:06:00Z",
      disclaimer: "AI-generated hypothesis; verify before taking action.",
    });

    vi.mocked(apiClient.getSimilarIncidents).mockResolvedValue({
      incident_id: "inc-1",
      items: [
        {
          incident_id: "inc-0",
          similarity_score: 0.91,
          status: "resolved",
          severity: "high",
          started_at: "2026-11-01T10:00:00Z",
          ended_at: "2026-11-01T10:15:00Z",
          summary: "Prior DB Pool timeout",
          root_cause: "QueuePool exhausted",
          suggested_fixes: [],
          resolution_note: "Increased pool_size from 20 to 50.",
          resolved_at: "2026-11-01T11:00:00Z",
        },
      ],
    });

    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/projects/proj-1/incidents/inc-1"]}>
          <Routes>
            <Route
              path="/projects/:projectId/incidents/:incidentId"
              element={<IncidentDetailPage />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    // 1. Verify disclaimer, root cause, unsupported claim warning, and similar incident
    await waitFor(() => {
      expect(screen.getByText(/SQLAlchemy QueuePool saturated/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/AI-generated hypothesis; verify before taking action/i)).toBeInTheDocument();
    expect(screen.getByText(/Unsupported Claim \(No Valid Citation\)/i)).toBeInTheDocument();
    expect(screen.getByText(/91% match/i)).toBeInTheDocument();
    expect(screen.getByText(/Increased pool_size from 20 to 50\./i)).toBeInTheDocument();

    // 2. Evidence text is initially hidden until [L1] citation pill is clicked
    expect(screen.queryByText(/TimeoutError: QueuePool limit of size 20/i)).not.toBeInTheDocument();

    // 3. Click citation [L1] -> reveals exact log line inline
    await user.click(screen.getByRole("button", { name: /\[L1\]/i }));
    await waitFor(() => {
      expect(screen.getByText(/TimeoutError: QueuePool limit of size 20 overflow 10 reached/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/\[L1\] Event #101/i)).toBeInTheDocument();
  });
});
