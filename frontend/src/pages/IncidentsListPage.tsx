import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertOctagon, ArrowRight, Loader2 } from "lucide-react";
import { apiClient } from "../api/client";
import { Layout } from "../components/Layout";
import { IncidentStatusBadge, SeverityBadge } from "../components/StatusBadges";

export const IncidentsListPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [statusFilter, setStatusFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["incidents", projectId, statusFilter, severityFilter],
    queryFn: () =>
      apiClient.listIncidents(projectId!, {
        status: statusFilter || undefined,
        severity: severityFilter || undefined,
        limit: 50,
      }),
    enabled: !!projectId,
  });

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
              <AlertOctagon className="w-6 h-6 text-rose-400" />
              Incidents
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Clustered error spikes across services with origin detection and AI reports.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <select
              aria-label="Filter by incident status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-sm text-slate-200 focus:border-indigo-500"
            >
              <option value="">All Statuses</option>
              <option value="open">Open</option>
              <option value="resolved">Resolved</option>
            </select>

            <select
              aria-label="Filter by incident severity"
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-sm text-slate-200 focus:border-indigo-500"
            >
              <option value="">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>

        {isLoading ? (
          <div className="p-12 flex justify-center items-center text-slate-400">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading incidents...
          </div>
        ) : !data || data.items.length === 0 ? (
          <div className="p-12 text-center bg-slate-900/50 border border-dashed border-slate-800 rounded-xl text-slate-400 text-sm">
            No incidents found. Upload error logs or load a demo scenario from Project Overview.
          </div>
        ) : (
          <div className="space-y-3">
            {data.items.map((inc) => (
              <Link
                key={inc.id}
                to={`/projects/${projectId}/incidents/${inc.id}`}
                className="block bg-slate-900 border border-slate-800 hover:border-indigo-500/50 rounded-xl p-5 transition-colors"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <SeverityBadge severity={inc.severity} />
                    <IncidentStatusBadge status={inc.status} />
                    <span className="text-xs text-slate-400 font-mono">
                      #{inc.id.slice(0, 8)}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400">
                    Started {new Date(inc.started_at).toLocaleString()}
                  </div>
                </div>

                <p className="text-sm font-mono text-white break-words">
                  {inc.origin_pattern_template || "Error Spike Cluster"}
                </p>

                {inc.resolution_note && (
                  <p className="mt-2 text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-1.5">
                    <strong>Resolution:</strong> {inc.resolution_note}
                  </p>
                )}

                <div className="mt-4 pt-3 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <div className="flex flex-wrap gap-1.5">
                    {inc.affected_services.map((srv) => (
                      <span
                        key={srv}
                        className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-medium"
                      >
                        {srv}
                      </span>
                    ))}
                  </div>
                  <span className="text-indigo-400 font-medium inline-flex items-center gap-1">
                    {inc.event_count} events &middot; Inspect incident <ArrowRight className="w-3.5 h-3.5" />
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
};
