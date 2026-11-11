import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, KeyRound, Loader2, Plus, Settings, Trash2 } from "lucide-react";
import { apiClient } from "../api/client";
import { Layout } from "../components/Layout";

export const ProjectSettingsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();

  const [keyLabel, setKeyLabel] = useState("");
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [projectSaved, setProjectSaved] = useState(false);

  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => apiClient.getProject(projectId!),
    enabled: !!projectId,
  });

  React.useEffect(() => {
    if (project) {
      setEditName(project.name);
      setEditDesc(project.description || "");
    }
  }, [project]);

  const { data: apiKeys, isLoading: keysLoading } = useQuery({
    queryKey: ["api-keys", projectId],
    queryFn: () => apiClient.listApiKeys(projectId!),
    enabled: !!projectId,
  });

  const updateProjectMutation = useMutation({
    mutationFn: () =>
      apiClient.updateProject(projectId!, {
        name: editName.trim(),
        description: editDesc.trim() || undefined,
      }),
    onSuccess: () => {
      setProjectSaved(true);
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      setTimeout(() => setProjectSaved(false), 2500);
    },
  });

  const createKeyMutation = useMutation({
    mutationFn: (label: string) => apiClient.createApiKey(projectId!, label),
    onSuccess: (created) => {
      setNewlyCreatedKey(created.raw_key);
      setKeyLabel("");
      void queryClient.invalidateQueries({ queryKey: ["api-keys", projectId] });
    },
  });

  const revokeKeyMutation = useMutation({
    mutationFn: (keyId: string) => apiClient.revokeApiKey(projectId!, keyId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["api-keys", projectId] });
    },
  });

  const handleCopyKey = async () => {
    if (!newlyCreatedKey) return;
    await navigator.clipboard.writeText(newlyCreatedKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            <Settings className="w-6 h-6 text-indigo-400" />
            Project Settings &amp; API Keys
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Configure project metadata and manage scoped ingestion API keys.
          </p>
        </div>

        {/* Project Details Form */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
          <h2 className="text-base font-semibold text-white">General Details</h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              updateProjectMutation.mutate();
            }}
            className="space-y-4 max-w-xl"
          >
            <div>
              <label htmlFor="settings-name" className="block text-sm font-medium text-slate-300 mb-1">
                Project Name
              </label>
              <input
                id="settings-name"
                type="text"
                required
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-sm text-white focus:border-indigo-500"
              />
            </div>
            <div>
              <label htmlFor="settings-desc" className="block text-sm font-medium text-slate-300 mb-1">
                Description
              </label>
              <input
                id="settings-desc"
                type="text"
                value={editDesc}
                onChange={(e) => setEditDesc(e.target.value)}
                className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-sm text-white focus:border-indigo-500"
              />
            </div>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={updateProjectMutation.isPending}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium"
              >
                Save Changes
              </button>
              {projectSaved && (
                <span className="text-xs text-emerald-400 flex items-center gap-1">
                  <Check className="w-3.5 h-3.5" /> Saved
                </span>
              )}
            </div>
          </form>
        </div>

        {/* Ingestion API Keys */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5">
          <div>
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              <KeyRound className="w-5 h-5 text-indigo-400" />
              Ingestion API Keys
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Raw API keys are displayed only once upon creation and stored hashed in the database.
            </p>
          </div>

          {newlyCreatedKey && (
            <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 space-y-2">
              <div className="text-sm font-semibold text-emerald-300">
                API Key Created — Copy it now (it will not be shown again!)
              </div>
              <div className="flex items-center gap-2">
                <code className="flex-1 p-2.5 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs text-emerald-200 break-all">
                  {newlyCreatedKey}
                </code>
                <button
                  type="button"
                  onClick={handleCopyKey}
                  className="px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium inline-flex items-center gap-1.5 shrink-0"
                >
                  {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!keyLabel.trim()) return;
              createKeyMutation.mutate(keyLabel.trim());
            }}
            className="flex flex-col sm:flex-row gap-2.5 max-w-xl"
          >
            <input
              type="text"
              required
              value={keyLabel}
              onChange={(e) => setKeyLabel(e.target.value)}
              placeholder="Key label (e.g. prod-k8s-collector)"
              aria-label="API Key Label"
              className="flex-1 px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-sm text-white placeholder-slate-500 focus:border-indigo-500"
            />
            <button
              type="submit"
              disabled={createKeyMutation.isPending}
              className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium whitespace-nowrap"
            >
              {createKeyMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Plus className="w-4 h-4" />
              )}
              Create Key
            </button>
          </form>

          {keysLoading ? (
            <div className="py-6 text-sm text-slate-400">Loading keys...</div>
          ) : !apiKeys || apiKeys.length === 0 ? (
            <div className="py-6 text-sm text-slate-500">No ingestion API keys created yet.</div>
          ) : (
            <div className="overflow-x-auto border border-slate-800 rounded-lg">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-950/60 text-xs uppercase text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-2.5">Label</th>
                    <th className="px-4 py-2.5">Prefix</th>
                    <th className="px-4 py-2.5">Status</th>
                    <th className="px-4 py-2.5 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {apiKeys.map((k) => {
                    const isRevoked = !!k.revoked_at;
                    return (
                      <tr key={k.id} className="hover:bg-slate-800/20">
                        <td className="px-4 py-3 font-medium text-white">{k.label}</td>
                        <td className="px-4 py-3 font-mono text-xs text-slate-400">
                          il_live_{k.key_prefix}_***
                        </td>
                        <td className="px-4 py-3 text-xs">
                          {isRevoked ? (
                            <span className="px-2 py-0.5 rounded bg-rose-500/15 text-rose-400 border border-rose-500/30">
                              Revoked
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                              Active
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {!isRevoked && (
                            <button
                              type="button"
                              onClick={() => {
                                if (window.confirm(`Revoke API key "${k.label}"?`)) {
                                  revokeKeyMutation.mutate(k.id);
                                }
                              }}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-rose-400 hover:bg-rose-500/15"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                              Revoke
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
};
