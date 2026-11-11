import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, FileUp, Loader2, Terminal, UploadCloud } from "lucide-react";
import { apiClient, ApiError } from "../api/client";
import { Layout } from "../components/Layout";
import { BatchStatusBadge } from "../components/StatusBadges";

export const UploadLogsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);

  const { data: batches, isLoading } = useQuery({
    queryKey: ["batches", projectId],
    queryFn: () => apiClient.listBatches(projectId!),
    enabled: !!projectId,
    refetchInterval: (query) => {
      const list = query.state.data;
      const hasPending = list?.some(
        (b) => b.status !== "done" && b.status !== "failed"
      );
      return hasPending ? 1500 : false;
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => apiClient.uploadLogFile(projectId!, file),
    onSuccess: (res) => {
      setUploadError(null);
      setUploadSuccess(`Batch queued (${res.batch_id.slice(0, 8)}...)`);
      setSelectedFile(null);
      void queryClient.invalidateQueries({ queryKey: ["batches", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["project-stats", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["incidents", projectId] });
    },
    onError: (err) => {
      setUploadSuccess(null);
      setUploadError(err instanceof ApiError ? err.message : "Upload failed");
    },
  });

  const handleUpload = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;
    uploadMutation.mutate(selectedFile);
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Upload &amp; Ingestion</h1>
          <p className="text-sm text-slate-400 mt-1">
            Upload raw application logs (.log, .txt, .json, .ndjson) or stream via API Key.
          </p>
        </div>

        {/* File Upload Card */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h2 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
            <UploadCloud className="w-5 h-5 text-indigo-400" />
            Upload Log File
          </h2>

          {uploadError && (
            <div className="mb-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{uploadError}</span>
            </div>
          )}

          {uploadSuccess && (
            <div className="mb-4 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{uploadSuccess}</span>
            </div>
          )}

          <form onSubmit={handleUpload} className="space-y-4">
            <label
              htmlFor="log-file-input"
              className="flex flex-col items-center justify-center border-2 border-dashed border-slate-700 hover:border-indigo-500/60 rounded-xl p-8 cursor-pointer bg-slate-950/60 transition-colors"
            >
              <FileUp className="w-8 h-8 text-indigo-400 mb-2" />
              <span className="text-sm font-medium text-slate-200">
                {selectedFile ? selectedFile.name : "Choose a log file to upload"}
              </span>
              <span className="text-xs text-slate-500 mt-1">
                Supports JSON Lines, standard syslog, or plain text (max 50 MB)
              </span>
              <input
                id="log-file-input"
                type="file"
                accept=".log,.txt,.json,.ndjson,text/plain,application/json"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                className="sr-only"
              />
            </label>

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={!selectedFile || uploadMutation.isPending}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
              >
                {uploadMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Upload &amp; Analyze Logs
              </button>
            </div>
          </form>
        </div>

        {/* Ingestion Batches History */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">Ingestion Batches</h2>
            <span className="text-xs text-slate-400">Auto-updates during processing</span>
          </div>

          {isLoading ? (
            <div className="p-8 text-center text-slate-400 text-sm">Loading batches...</div>
          ) : !batches || batches.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">
              No log batches ingested yet. Upload a file or load a demo scenario from Overview.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-950/60 text-xs uppercase text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="px-5 py-3 font-medium">Source / File</th>
                    <th className="px-5 py-3 font-medium">Status</th>
                    <th className="px-5 py-3 font-medium">Events Parsed</th>
                    <th className="px-5 py-3 font-medium">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {batches.map((b) => (
                    <tr key={b.id} className="hover:bg-slate-800/30">
                      <td className="px-5 py-3">
                        <div className="font-medium text-white">
                          {b.filename || "API Stream"}
                        </div>
                        <div className="text-xs text-slate-500">
                          source: {b.source} &middot; {b.id.slice(0, 8)}
                        </div>
                      </td>
                      <td className="px-5 py-3">
                        <BatchStatusBadge status={b.status} />
                        {b.error && (
                          <p className="text-xs text-rose-400 mt-1 max-w-xs truncate">
                            {b.error}
                          </p>
                        )}
                      </td>
                      <td className="px-5 py-3 text-slate-300 font-mono">
                        {b.line_count.toLocaleString()}
                      </td>
                      <td className="px-5 py-3 text-xs text-slate-400">
                        {new Date(b.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* HTTP Stream Quick Guide */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-2">
            <Terminal className="w-4 h-4 text-indigo-400" />
            HTTP API Streaming Example
          </h3>
          <p className="text-xs text-slate-400 mb-3">
            Send raw NDJSON or JSON arrays directly using a project API Key from Settings:
          </p>
          <pre className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono text-indigo-300 overflow-x-auto">
{`curl -X POST http://localhost:8000/api/v1/ingest \\
  -H "X-API-Key: il_live_<prefix>_<secret>" \\
  -H "Content-Type: application/x-ndjson" \\
  --data-binary @app.log`}
          </pre>
        </div>
      </div>
    </Layout>
  );
};
