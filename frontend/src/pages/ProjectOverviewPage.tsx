import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertOctagon,
  ArrowRight,
  DatabaseZap,
  FileText,
  Layers,
  Loader2,
  Play,
  Activity,
} from "lucide-react";
import { apiClient } from "../api/client";
import { Layout } from "../components/Layout";
import {
  IncidentStatusBadge,
  LevelBadge,
  SeverityBadge,
} from "../components/StatusBadges";

export const ProjectOverviewPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();

  const [selectedScenario, setSelectedScenario] = useState(
    "db_pool_exhaustion_low_noise_multi_service"
  );
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["project-stats", projectId],
    queryFn: () => apiClient.getProjectStats(projectId!),
    enabled: !!projectId,
  });

  const { data: incidentsData } = useQuery({
    queryKey: ["incidents", projectId],
    queryFn: () => apiClient.listIncidents(projectId!, { limit: 5 }),
    enabled: !!projectId,
  });

  const { data: demoScenarios } = useQuery({
    queryKey: ["demo-scenarios"],
    queryFn: () => apiClient.listDemoScenarios(),
  });

  const { data: activeBatch } = useQuery({
    queryKey: ["batch", activeBatchId],
    queryFn: () => apiClient.getBatch(activeBatchId!),
    enabled: !!activeBatchId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "done" || status === "failed") return false;
      return 1000;
    },
  });

  useEffect(() => {
    if (activeBatch?.status === "done") {
      void queryClient.invalidateQueries({ queryKey: ["project-stats", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["incidents", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["patterns", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["batches", projectId] });
    }
  }, [activeBatch?.status, projectId, queryClient]);

  const demoMutation = useMutation({
    mutationFn: (scenarioId: string) => apiClient.loadDemoData(projectId!, scenarioId),
    onSuccess: (res) => {
      setActiveBatchId(res.batch_id);
      void queryClient.invalidateQueries({ queryKey: ["project-stats", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["incidents", projectId] });
    },
  });

  const chartData =
    stats?.error_rate_series.map((pt) => ({
      time: new Date(pt.bucket).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
      Total: pt.total_events,
      Errors: pt.error_events,
    })) || [];

  return (
    <Layout>
      <div className="space-y-6">
        {/* Top Action Banner + One-Click Demo Loader */}
        <div className="bg-gradient-to-r from-slate-900 via-slate-900 to-indigo-950/50 border border-slate-800 rounded-2xl p-5 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-white flex items-center gap-2">
              <Activity className="w-5 h-5 text-indigo-400" />
              Project Overview
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Monitor error rates, grouped failure templates, and detected incidents.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
            <label htmlFor="demo-scenario-select" className="sr-only">
              Select demo scenario
            </label>
            <select
              id="demo-scenario-select"
              value={selectedScenario}
              onChange={(e) => setSelectedScenario(e.target.value)}
              className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 text-xs sm:text-sm focus:border-indigo-500 max-w-xs"
            >
              {demoScenarios ? (
                demoScenarios.map((sc) => (
                  <option key={sc.scenario_id} value={sc.scenario_id}>
                    {sc.has_incident ? "⚠ " : "✓ "}
                    {sc.scenario_id} ({sc.total_lines} lines)
                  </option>
                ))
              ) : (
                <option value="db_pool_exhaustion_low_noise_multi_service">
                  db_pool_exhaustion_low_noise_multi_service
                </option>
              )}
            </select>

            <button
              type="button"
              disabled={demoMutation.isPending}
              onClick={() => demoMutation.mutate(selectedScenario)}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium transition-colors whitespace-nowrap"
            >
              {demoMutation.isPending ||
              (activeBatch && activeBatch.status !== "done" && activeBatch.status !== "failed") ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4 fill-current" />
              )}
              Load Demo Incident
            </button>
          </div>
        </div>

        {activeBatch && activeBatch.status !== "done" && (
          <div className="p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 text-sm flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>
              Processing demo batch (status: <strong>{activeBatch.status}</strong>)...
            </span>
          </div>
        )}

        {/* KPI Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>Total Log Events</span>
              <FileText className="w-4 h-4 text-slate-500" />
            </div>
            <div className="text-2xl font-bold text-white mt-2">
              {statsLoading ? "—" : stats?.total_events.toLocaleString() ?? 0}
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>Error / Fatal Events</span>
              <AlertOctagon className="w-4 h-4 text-rose-400" />
            </div>
            <div className="text-2xl font-bold text-rose-400 mt-2">
              {statsLoading ? "—" : stats?.error_events.toLocaleString() ?? 0}
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>Unique Error Patterns</span>
              <Layers className="w-4 h-4 text-amber-400" />
            </div>
            <div className="text-2xl font-bold text-white mt-2">
              {statsLoading ? "—" : stats?.total_patterns.toLocaleString() ?? 0}
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>Open Incidents</span>
              <DatabaseZap className="w-4 h-4 text-indigo-400" />
            </div>
            <div className="text-2xl font-bold text-white mt-2 flex items-baseline gap-2">
              <span>{statsLoading ? "—" : stats?.open_incidents ?? 0}</span>
              <span className="text-xs font-normal text-slate-400">
                ({stats?.resolved_incidents ?? 0} resolved)
              </span>
            </div>
          </div>
        </div>

        {/* Error Rate Chart */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-semibold text-white">Event &amp; Error Rate Over Time</h2>
              <p className="text-xs text-slate-400">1-minute buckets across ingested logs</p>
            </div>
            <Link
              to={`/projects/${projectId}/upload`}
              className="text-xs font-medium text-indigo-400 hover:text-indigo-300"
            >
              Upload more logs &rarr;
            </Link>
          </div>

          {chartData.length === 0 ? (
            <div className="h-56 flex flex-col items-center justify-center text-slate-500 text-sm border border-dashed border-slate-800 rounded-lg">
              <p>No log time-series data yet.</p>
              <p className="text-xs mt-1">Click &ldquo;Load Demo Incident&rdquo; above or upload a log file.</p>
            </div>
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="colorError" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.45} />
                      <stop offset="95%" stopColor="#f43f5e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="time" stroke="#64748b" fontSize={11} />
                  <YAxis stroke="#64748b" fontSize={11} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      borderColor: "#334155",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="Total"
                    stroke="#6366f1"
                    fillOpacity={1}
                    fill="url(#colorTotal)"
                  />
                  <Area
                    type="monotone"
                    dataKey="Errors"
                    stroke="#f43f5e"
                    fillOpacity={1}
                    fill="url(#colorError)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Bottom Grid: Recent Incidents + Top Patterns */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Recent Incidents */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-white">Recent Incidents</h2>
              <Link
                to={`/projects/${projectId}/incidents`}
                className="text-xs font-medium text-indigo-400 hover:text-indigo-300 inline-flex items-center gap-1"
              >
                View all <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {!incidentsData || incidentsData.items.length === 0 ? (
              <div className="flex-1 flex items-center justify-center py-8 text-sm text-slate-500">
                No incidents detected yet.
              </div>
            ) : (
              <div className="space-y-3">
                {incidentsData.items.map((inc) => (
                  <Link
                    key={inc.id}
                    to={`/projects/${projectId}/incidents/${inc.id}`}
                    className="block p-3.5 rounded-lg bg-slate-950/70 border border-slate-800/80 hover:border-indigo-500/40 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <div className="flex items-center gap-2">
                        <SeverityBadge severity={inc.severity} />
                        <IncidentStatusBadge status={inc.status} />
                      </div>
                      <span className="text-xs text-slate-500">
                        {new Date(inc.started_at).toLocaleString()}
                      </span>
                    </div>
                    <p className="text-xs font-mono text-slate-300 truncate">
                      {inc.origin_pattern_template || "Error spike incident"}
                    </p>
                    <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
                      <span>{inc.affected_services.join(", ")}</span>
                      <span>{inc.event_count} events</span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>

          {/* Top Error Patterns */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-white">Top Error Patterns</h2>
              <Link
                to={`/projects/${projectId}/patterns`}
                className="text-xs font-medium text-indigo-400 hover:text-indigo-300 inline-flex items-center gap-1"
              >
                Explore patterns <ArrowRight className="w-3 h-3" />
              </Link>
            </div>

            {!stats || stats.top_patterns.length === 0 ? (
              <div className="flex-1 flex items-center justify-center py-8 text-sm text-slate-500">
                No error patterns extracted yet.
              </div>
            ) : (
              <div className="space-y-2.5">
                {stats.top_patterns.map((pat) => (
                  <div
                    key={pat.id}
                    className="p-3 rounded-lg bg-slate-950/70 border border-slate-800/80 flex items-start justify-between gap-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <LevelBadge level={pat.level} />
                        <span className="text-xs font-medium text-indigo-300">
                          {pat.sample_service}
                        </span>
                      </div>
                      <p className="text-xs font-mono text-slate-300 break-all line-clamp-2">
                        {pat.template}
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      <span className="text-sm font-bold text-white">{pat.total_count}</span>
                      <p className="text-[10px] text-slate-500 uppercase">hits</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </Layout>
  );
};
