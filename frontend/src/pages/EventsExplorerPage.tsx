import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, FileSearch, Loader2, Search } from "lucide-react";
import { apiClient } from "../api/client";
import { Layout } from "../components/Layout";
import { LevelBadge } from "../components/StatusBadges";

export const EventsExplorerPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();

  const [searchText, setSearchText] = useState("");
  const [appliedText, setAppliedText] = useState("");
  const [service, setService] = useState("");
  const [level, setLevel] = useState("");
  const [offset, setOffset] = useState(0);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const limit = 50;

  const { data, isLoading } = useQuery({
    queryKey: ["events", projectId, appliedText, service, level, offset],
    queryFn: () =>
      apiClient.searchEvents(projectId!, {
        text: appliedText || undefined,
        service: service || undefined,
        level: level || undefined,
        limit,
        offset,
      }),
    enabled: !!projectId,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setOffset(0);
    setAppliedText(searchText);
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            <FileSearch className="w-6 h-6 text-indigo-400" />
            Log Explorer
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Search parsed log events and inspect joined multi-line stack traces.
          </p>
        </div>

        {/* Filters */}
        <form
          onSubmit={handleSearch}
          className="bg-slate-900 border border-slate-800 rounded-xl p-4 grid grid-cols-1 sm:grid-cols-4 gap-3"
        >
          <div className="sm:col-span-2 relative">
            <label htmlFor="event-search-input" className="sr-only">
              Search message text
            </label>
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
            <input
              id="event-search-input"
              type="text"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Search message text (e.g. QueuePool, Timeout)..."
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-sm text-white placeholder-slate-500 focus:border-indigo-500"
            />
          </div>

          <div>
            <label htmlFor="event-service-input" className="sr-only">
              Filter by service
            </label>
            <input
              id="event-service-input"
              type="text"
              value={service}
              onChange={(e) => {
                setService(e.target.value);
                setOffset(0);
              }}
              placeholder="Service (e.g. checkout-service)"
              className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-sm text-white placeholder-slate-500 focus:border-indigo-500"
            />
          </div>

          <div className="flex gap-2">
            <select
              aria-label="Filter by log level"
              value={level}
              onChange={(e) => {
                setLevel(e.target.value);
                setOffset(0);
              }}
              className="flex-1 px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-sm text-slate-200 focus:border-indigo-500"
            >
              <option value="">All Levels</option>
              <option value="FATAL">FATAL</option>
              <option value="ERROR">ERROR</option>
              <option value="WARN">WARN</option>
              <option value="INFO">INFO</option>
              <option value="DEBUG">DEBUG</option>
            </select>
            <button
              type="submit"
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium"
            >
              Filter
            </button>
          </div>
        </form>

        {/* Results Table */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          {isLoading ? (
            <div className="p-12 flex justify-center items-center text-slate-400">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Searching logs...
            </div>
          ) : !data || data.items.length === 0 ? (
            <div className="p-12 text-center text-slate-500 text-sm">
              No log events match your filter criteria.
            </div>
          ) : (
            <div className="divide-y divide-slate-800/70">
              {data.items.map((evt) => {
                const isExpanded = expandedId === evt.id;
                return (
                  <div key={evt.id} className="hover:bg-slate-800/30 transition-colors">
                    <button
                      type="button"
                      onClick={() => setExpandedId(isExpanded ? null : evt.id)}
                      className="w-full text-left px-4 py-3 flex items-start gap-3"
                    >
                      <span className="mt-0.5 text-slate-500">
                        {isExpanded ? (
                          <ChevronDown className="w-4 h-4" />
                        ) : (
                          <ChevronRight className="w-4 h-4" />
                        )}
                      </span>
                      <span className="text-xs font-mono text-slate-500 whitespace-nowrap pt-0.5">
                        #{evt.id} &middot;{" "}
                        {new Date(evt.ts).toLocaleTimeString()}
                      </span>
                      <LevelBadge level={evt.level} />
                      <span className="text-xs font-medium text-indigo-300 whitespace-nowrap pt-0.5">
                        {evt.service}
                      </span>
                      <span className="text-xs font-mono text-slate-200 break-all line-clamp-2 flex-1">
                        {evt.message}
                      </span>
                    </button>

                    {isExpanded && (
                      <div className="px-10 pb-4 pt-1 space-y-2 text-xs">
                        <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 font-mono text-slate-300 whitespace-pre-wrap break-words">
                          {evt.message}
                        </div>
                        <div className="flex flex-wrap gap-4 text-slate-400">
                          <span>Timestamp (UTC): {evt.ts}</span>
                          {evt.trace_id && <span>Trace ID: {evt.trace_id}</span>}
                          <span>Batch ID: {evt.batch_id}</span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination */}
          {data && data.total > 0 && (
            <div className="px-4 py-3 bg-slate-950/60 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
              <span>
                Showing {offset + 1}–{Math.min(offset + limit, data.total)} of{" "}
                {data.total.toLocaleString()} events
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                  className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={offset + limit >= data.total}
                  onClick={() => setOffset(offset + limit)}
                  className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
};
