import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Layers, Loader2 } from "lucide-react";
import { apiClient } from "../api/client";
import { Layout } from "../components/Layout";
import { LevelBadge } from "../components/StatusBadges";

export const PatternsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [levelFilter, setLevelFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["patterns", projectId, levelFilter],
    queryFn: () =>
      apiClient.listPatterns(projectId!, {
        level: levelFilter || undefined,
        limit: 100,
      }),
    enabled: !!projectId,
  });

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
              <Layers className="w-6 h-6 text-indigo-400" />
              Normalized Error Patterns
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Variable tokens and stack traces collapsed into fingerprinted templates.
            </p>
          </div>

          <select
            aria-label="Filter patterns by level"
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-sm text-slate-200 focus:border-indigo-500 self-start"
          >
            <option value="">All Severities</option>
            <option value="FATAL">FATAL</option>
            <option value="ERROR">ERROR</option>
            <option value="WARN">WARN</option>
            <option value="INFO">INFO</option>
          </select>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          {isLoading ? (
            <div className="p-12 flex justify-center items-center text-slate-400">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading patterns...
            </div>
          ) : !data || data.items.length === 0 ? (
            <div className="p-12 text-center text-slate-500 text-sm">
              No patterns detected yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-950/60 text-xs uppercase text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="px-5 py-3 font-medium">Level / Service</th>
                    <th className="px-5 py-3 font-medium">Template</th>
                    <th className="px-5 py-3 font-medium text-right">Occurrences</th>
                    <th className="px-5 py-3 font-medium">Last Seen</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {data.items.map((pat) => (
                    <tr key={pat.id} className="hover:bg-slate-800/30">
                      <td className="px-5 py-3.5 align-top whitespace-nowrap">
                        <div className="flex flex-col items-start gap-1">
                          <LevelBadge level={pat.level} />
                          <span className="text-xs font-medium text-indigo-300">
                            {pat.sample_service}
                          </span>
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <p className="font-mono text-xs text-slate-200 break-words">
                          {pat.template}
                        </p>
                        <div className="mt-1.5 flex flex-wrap gap-2 text-[11px] text-slate-500">
                          <span>Fingerprint: {pat.fingerprint.slice(0, 12)}</span>
                          {pat.example_event_ids.length > 0 && (
                            <span>
                              Sample Event IDs:{" "}
                              {pat.example_event_ids.map((eid) => `#${eid}`).join(", ")}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-5 py-3.5 text-right font-mono font-bold text-white align-top">
                        {pat.total_count.toLocaleString()}
                      </td>
                      <td className="px-5 py-3.5 text-xs text-slate-400 whitespace-nowrap align-top">
                        {new Date(pat.last_seen).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
};
