import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Eye,
  History,
  Info,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Wrench,
} from "lucide-react";
import { apiClient } from "../api/client";
import { Layout } from "../components/Layout";
import {
  IncidentStatusBadge,
  LevelBadge,
  SeverityBadge,
  ValidationStatusBadge,
} from "../components/StatusBadges";
import type { EvidenceLine, LogEvent } from "../types/api";

export const IncidentDetailPage: React.FC = () => {
  const { projectId, incidentId } = useParams<{
    projectId: string;
    incidentId: string;
  }>();
  const queryClient = useQueryClient();

  const [expandedCitations, setExpandedCitations] = useState<Record<string, boolean>>({});
  const [rawEventsCache, setRawEventsCache] = useState<Record<number, LogEvent>>({});
  const [loadingRawId, setLoadingRawId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"timeline" | "patterns">("timeline");

  const [showResolveForm, setShowResolveForm] = useState(false);
  const [resolutionNote, setResolutionNote] = useState("");

  const { data: incident, isLoading: incLoading } = useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => apiClient.getIncidentDetail(incidentId!),
    enabled: !!incidentId,
  });

  const { data: report, isLoading: repLoading } = useQuery({
    queryKey: ["incident-report", incidentId],
    queryFn: () => apiClient.getIncidentReport(incidentId!),
    enabled: !!incidentId,
    refetchInterval: (query) => {
      const st = query.state.data?.status;
      if (st === "pending" || st === "processing") return 1200;
      return false;
    },
  });

  const { data: similarData } = useQuery({
    queryKey: ["similar-incidents", incidentId],
    queryFn: () => apiClient.getSimilarIncidents(incidentId!),
    enabled: !!incidentId,
  });

  const explainMutation = useMutation({
    mutationFn: (force: boolean) => apiClient.triggerExplain(incidentId!, force),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["incident-report", incidentId] });
      void queryClient.invalidateQueries({ queryKey: ["similar-incidents", incidentId] });
    },
  });

  const resolveMutation = useMutation({
    mutationFn: (payload: { status: "open" | "resolved"; resolution_note?: string }) =>
      apiClient.resolveIncident(incidentId!, payload),
    onSuccess: () => {
      setShowResolveForm(false);
      void queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
      void queryClient.invalidateQueries({ queryKey: ["incidents", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["project-stats", projectId] });
    },
  });

  const evidenceByShortId = React.useMemo(() => {
    const map: Record<string, EvidenceLine> = {};
    if (report?.evidence_lines) {
      for (const line of report.evidence_lines) {
        map[line.short_id] = line;
      }
    }
    return map;
  }, [report]);

  const toggleCitation = (claimIdx: number, lineId: string) => {
    const key = `${claimIdx}-${lineId}`;
    setExpandedCitations((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const handleInspectRawEvent = async (eventId: number) => {
    if (!projectId || rawEventsCache[eventId]) return;
    setLoadingRawId(eventId);
    try {
      const rawEvt = await apiClient.getEventDetail(projectId, eventId);
      setRawEventsCache((prev) => ({ ...prev, [eventId]: rawEvt }));
    } finally {
      setLoadingRawId(null);
    }
  };

  if (incLoading) {
    return (
      <Layout>
        <div className="flex items-center justify-center py-20 text-slate-400">
          <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading incident details...
        </div>
      </Layout>
    );
  }

  if (!incident) {
    return (
      <Layout>
        <div className="p-6 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
          Incident not found or access denied.
        </div>
      </Layout>
    );
  }

  const isGenerating =
    explainMutation.isPending ||
    report?.status === "pending" ||
    report?.status === "processing";

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header Card */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
            <div className="space-y-2">
              <div className="flex items-center gap-2.5 flex-wrap">
                <SeverityBadge severity={incident.severity} />
                <IncidentStatusBadge status={incident.status} />
                <span className="text-xs font-mono text-slate-500">
                  ID: {incident.id}
                </span>
              </div>

              <h1 className="text-xl font-bold text-white font-mono break-words pt-1">
                {incident.origin_pattern_template || "Error Spike Incident"}
              </h1>

              <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400 pt-1">
                <span className="inline-flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  Started: {new Date(incident.started_at).toLocaleString()}
                </span>
                {incident.ended_at && (
                  <span>Ended: {new Date(incident.ended_at).toLocaleString()}</span>
                )}
                <span>Total Error Events: {incident.event_count}</span>
              </div>

              <div className="flex flex-wrap gap-1.5 pt-2">
                {incident.affected_services.map((srv) => (
                  <span
                    key={srv}
                    className="px-2.5 py-1 rounded-md bg-slate-800 border border-slate-700 text-xs font-medium text-indigo-300"
                  >
                    {srv}
                  </span>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap gap-2 shrink-0">
              {incident.status === "open" ? (
                <button
                  type="button"
                  onClick={() => {
                    setResolutionNote(incident.resolution_note || "");
                    setShowResolveForm(!showResolveForm);
                  }}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition-colors"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  Mark Resolved
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() =>
                    resolveMutation.mutate({ status: "open" })
                  }
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium transition-colors"
                >
                  Reopen Incident
                </button>
              )}
            </div>
          </div>

          {incident.resolution_note && (
            <div className="mt-4 p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 text-sm">
              <div className="font-semibold flex items-center gap-1.5 text-emerald-300 mb-0.5">
                <CheckCircle2 className="w-4 h-4" />
                Saved Resolution Note
              </div>
              <p>{incident.resolution_note}</p>
            </div>
          )}

          {showResolveForm && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                resolveMutation.mutate({
                  status: "resolved",
                  resolution_note: resolutionNote,
                });
              }}
              className="mt-4 pt-4 border-t border-slate-800 space-y-3"
            >
              <label
                htmlFor="resolution-note-input"
                className="block text-sm font-medium text-slate-200"
              >
                Resolution Note (saved for future similar-incident recommendations)
              </label>
              <textarea
                id="resolution-note-input"
                rows={2}
                required
                value={resolutionNote}
                onChange={(e) => setResolutionNote(e.target.value)}
                placeholder="e.g. Increased SQLAlchemy pool_size from 20 to 50 and restarted checkout workers."
                className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-sm text-white placeholder-slate-500 focus:border-emerald-500"
              />
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={resolveMutation.isPending}
                  className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium"
                >
                  Save Resolution
                </button>
                <button
                  type="button"
                  onClick={() => setShowResolveForm(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 text-sm font-medium"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>

        {/* AI Root-Cause Explanation Panel */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Bot className="w-5 h-5 text-indigo-400" />
                AI Root-Cause Analysis
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Grounded exclusively in redacted, verified log line citations
              </p>
            </div>

            <div className="flex items-center gap-2">
              {(!report || report.status === "not_generated" || report.status === "failed") && (
                <button
                  type="button"
                  disabled={isGenerating}
                  onClick={() => explainMutation.mutate(false)}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
                >
                  {isGenerating ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Sparkles className="w-4 h-4" />
                  )}
                  Generate Root-Cause Report
                </button>
              )}

              {report && report.status === "done" && (
                <button
                  type="button"
                  disabled={isGenerating}
                  onClick={() => explainMutation.mutate(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isGenerating ? "animate-spin" : ""}`} />
                  Regenerate
                </button>
              )}
            </div>
          </div>

          {repLoading ? (
            <div className="py-8 text-center text-slate-400 text-sm">Loading report status...</div>
          ) : isGenerating ? (
            <div className="py-10 flex flex-col items-center justify-center text-indigo-300 space-y-2">
              <Loader2 className="w-7 h-7 animate-spin" />
              <p className="text-sm font-medium">
                Selecting compact evidence, redacting PII/secrets, and verifying citations...
              </p>
            </div>
          ) : report?.status === "failed" ? (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
              <strong>Report generation failed:</strong> {report.error || "Unknown error"}
            </div>
          ) : !report || report.status === "not_generated" ? (
            <div className="py-10 text-center border border-dashed border-slate-800 rounded-xl space-y-2">
              <Sparkles className="w-8 h-8 text-indigo-400/70 mx-auto" />
              <p className="text-sm text-slate-300">
                No AI explanation has been generated for this incident yet.
              </p>
              <p className="text-xs text-slate-500">
                Click &ldquo;Generate Root-Cause Report&rdquo; to inspect verified evidence claims.
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Disclaimer Banner */}
              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/25 text-amber-200/90 text-xs flex items-start gap-2.5">
                <Info className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
                <span>{report.disclaimer}</span>
              </div>

              {/* Telemetry & Verification Header */}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <ValidationStatusBadge
                  status={report.validation_status}
                  unsupportedCount={report.unsupported_claim_count}
                />
                <div className="flex flex-wrap gap-3 text-xs text-slate-400 font-mono">
                  <span>Model: {report.model_name}</span>
                  <span>Prompt: {report.prompt_version}</span>
                  <span>
                    Evidence: {report.selected_evidence_lines}/{report.total_incident_events} lines
                  </span>
                  <span>
                    Tokens: {report.input_tokens + report.output_tokens}
                  </span>
                </div>
              </div>

              {/* Summary & Root Cause */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-1.5">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Executive Summary
                  </h3>
                  <p className="text-sm text-slate-100 leading-relaxed">{report.summary}</p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                      Probable Root Cause
                    </h3>
                    {report.confidence && (
                      <span className="text-[11px] px-2 py-0.5 rounded bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 uppercase font-medium">
                        {report.confidence} confidence
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-indigo-100 leading-relaxed">{report.root_cause}</p>
                </div>
              </div>

              {/* Verified Evidence Claims (Clickable Citations) */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-white">
                  Evidence-Linked Claims (Click any citation pill to inspect exact log line)
                </h3>
                <div className="space-y-3">
                  {report.claims.map((claim, idx) => (
                    <div
                      key={idx}
                      className={`p-4 rounded-xl border ${
                        claim.supported
                          ? "bg-slate-950/70 border-slate-800"
                          : "bg-amber-950/20 border-amber-500/40"
                      }`}
                    >
                      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                        <div className="space-y-2 flex-1">
                          {!claim.supported && (
                            <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-bold uppercase bg-amber-500/20 text-amber-300 border border-amber-500/40">
                              <AlertTriangle className="w-3 h-3" />
                              Unsupported Claim (No Valid Citation)
                            </div>
                          )}
                          <p className="text-sm text-slate-100">{claim.text}</p>
                        </div>

                        <div className="flex flex-wrap gap-1.5 shrink-0">
                          {claim.cited_line_ids.map((lid) => {
                            const isOpen = !!expandedCitations[`${idx}-${lid}`];
                            return (
                              <button
                                key={lid}
                                type="button"
                                onClick={() => toggleCitation(idx, lid)}
                                className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-mono font-semibold border transition-colors ${
                                  isOpen
                                    ? "bg-indigo-600 text-white border-indigo-500"
                                    : "bg-indigo-500/15 text-indigo-300 border-indigo-500/30 hover:bg-indigo-500/25"
                                }`}
                              >
                                {isOpen ? (
                                  <ChevronDown className="w-3 h-3" />
                                ) : (
                                  <ChevronRight className="w-3 h-3" />
                                )}
                                [{lid}]
                              </button>
                            );
                          })}
                          {claim.invalid_citations.map((badId) => (
                            <span
                              key={badId}
                              className="inline-flex items-center px-2 py-1 rounded-md text-xs font-mono bg-rose-500/20 text-rose-300 border border-rose-500/40 line-through"
                              title="Hallucinated citation not found in evidence set"
                            >
                              [{badId}]
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Expanded Inline Log Evidence */}
                      {claim.cited_line_ids.some(
                        (lid) => expandedCitations[`${idx}-${lid}`]
                      ) && (
                        <div className="mt-3 pt-3 border-t border-slate-800/80 space-y-2.5">
                          {claim.cited_line_ids
                            .filter((lid) => expandedCitations[`${idx}-${lid}`])
                            .map((lid) => {
                              const ev = evidenceByShortId[lid];
                              if (!ev) return null;
                              const rawEvt = rawEventsCache[ev.event_id];
                              return (
                                <div
                                  key={lid}
                                  className="p-3 rounded-lg bg-slate-900 border border-slate-700/80 space-y-2"
                                >
                                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                                    <div className="flex items-center gap-2">
                                      <span className="font-mono font-bold text-indigo-300">
                                        [{lid}] Event #{ev.event_id}
                                      </span>
                                      <LevelBadge level={ev.level} />
                                      <span className="text-slate-300 font-medium">
                                        {ev.service}
                                      </span>
                                      <span className="text-slate-500 font-mono">
                                        {new Date(ev.ts).toISOString()}
                                      </span>
                                    </div>
                                    <button
                                      type="button"
                                      onClick={() => handleInspectRawEvent(ev.event_id)}
                                      className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-400 hover:text-indigo-300"
                                    >
                                      <Eye className="w-3 h-3" />
                                      {loadingRawId === ev.event_id
                                        ? "Fetching raw..."
                                        : rawEvt
                                        ? "Raw Stored Log Loaded"
                                        : "Inspect Raw Stored Event"}
                                    </button>
                                  </div>
                                  <pre className="text-xs font-mono text-slate-200 whitespace-pre-wrap break-words bg-slate-950 p-2.5 rounded border border-slate-800">
                                    {ev.message}
                                  </pre>
                                  {rawEvt && (
                                    <div className="text-[11px] space-y-1">
                                      <span className="text-emerald-400 font-semibold">
                                        Stored Raw Database Line (Batch #{rawEvt.batch_id.slice(0, 8)}):
                                      </span>
                                      <pre className="font-mono text-emerald-200/90 whitespace-pre-wrap break-words bg-emerald-950/20 p-2 rounded border border-emerald-500/20">
                                        {rawEvt.raw_line}
                                      </pre>
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Suggested Fixes */}
              {report.suggested_fixes.length > 0 && (
                <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                    <Wrench className="w-3.5 h-3.5 text-indigo-400" />
                    Suggested Remediation Steps
                  </h3>
                  <ul className="list-disc list-inside space-y-1 text-sm text-slate-200">
                    {report.suggested_fixes.map((fix, i) => (
                      <li key={i}>{fix}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Similar Past Incidents Panel */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <History className="w-5 h-5 text-indigo-400" />
                Similar Past Incidents
              </h2>
              <p className="text-xs text-slate-400">
                Matched within this project using semantic vector similarity
              </p>
            </div>
          </div>

          {!similarData || similarData.items.length === 0 ? (
            <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 text-xs text-slate-500">
              No similar historical incidents matched above the similarity threshold in this project.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {similarData.items.map((match) => (
                <Link
                  key={match.incident_id}
                  to={`/projects/${projectId}/incidents/${match.incident_id}`}
                  className="block p-4 rounded-xl bg-slate-950/80 border border-slate-800 hover:border-indigo-500/50 transition-colors space-y-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-xs font-mono font-bold">
                      {Math.round(match.similarity_score * 100)}% match
                    </span>
                    <IncidentStatusBadge status={match.status} />
                  </div>
                  <p className="text-xs font-medium text-white line-clamp-2">
                    {match.summary || match.root_cause}
                  </p>
                  {match.resolution_note && (
                    <div className="text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/20 rounded p-2">
                      <strong>Resolved by:</strong> {match.resolution_note}
                    </div>
                  )}
                  <div className="text-[11px] text-slate-500">
                    Occurred {new Date(match.started_at).toLocaleString()}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Origin Candidates Ranked Panel */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-amber-400" />
            Origin Pattern Candidates (Ranked Deterministically)
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/70 text-slate-400 uppercase border-b border-slate-800">
                <tr>
                  <th className="px-4 py-2.5">Rank</th>
                  <th className="px-4 py-2.5">Service</th>
                  <th className="px-4 py-2.5">Pattern Template</th>
                  <th className="px-4 py-2.5">Scoring Reasons</th>
                  <th className="px-4 py-2.5 text-right">Score</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {incident.origin_candidates.map((cand, idx) => (
                  <tr key={cand.pattern_id} className="hover:bg-slate-800/30">
                    <td className="px-4 py-3 font-mono font-bold text-indigo-300">
                      #{idx + 1}
                    </td>
                    <td className="px-4 py-3 font-medium text-white whitespace-nowrap">
                      {cand.service}
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-300 max-w-md break-words">
                      {cand.template}
                    </td>
                    <td className="px-4 py-3 text-slate-400 max-w-sm">
                      {cand.reason}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-bold text-white">
                      {cand.score}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Timeline & Participating Patterns Tabs */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-800 flex gap-4">
            <button
              type="button"
              onClick={() => setActiveTab("timeline")}
              className={`text-sm font-medium pb-1 border-b-2 transition-colors ${
                activeTab === "timeline"
                  ? "border-indigo-500 text-white"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              Cascade Timeline ({incident.timeline.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("patterns")}
              className={`text-sm font-medium pb-1 border-b-2 transition-colors ${
                activeTab === "patterns"
                  ? "border-indigo-500 text-white"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              Incident Patterns ({incident.patterns.length})
            </button>
          </div>

          {activeTab === "timeline" ? (
            <div className="divide-y divide-slate-800/60 max-h-96 overflow-y-auto">
              {incident.timeline.map((item) => (
                <div
                  key={item.event_id}
                  className="px-5 py-3 flex items-start gap-3 text-xs hover:bg-slate-800/30"
                >
                  <span className="font-mono text-slate-500 whitespace-nowrap pt-0.5">
                    {new Date(item.timestamp).toLocaleTimeString()}
                  </span>
                  <LevelBadge level={item.level} />
                  <span className="font-medium text-indigo-300 whitespace-nowrap pt-0.5">
                    {item.service}
                  </span>
                  <span className="font-mono text-slate-200 break-words flex-1">
                    {item.message}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="divide-y divide-slate-800/60">
              {incident.patterns.map((p) => (
                <div
                  key={p.pattern_id}
                  className="px-5 py-3 flex items-start justify-between gap-4 text-xs"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      {p.level && <LevelBadge level={p.level} />}
                      <span className="font-medium text-indigo-300">{p.sample_service}</span>
                    </div>
                    <p className="font-mono text-slate-200">{p.template}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <span className="font-mono font-bold text-white">{p.count}x</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
};
