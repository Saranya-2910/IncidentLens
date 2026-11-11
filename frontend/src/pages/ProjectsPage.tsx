import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, FolderPlus, Loader2, Plus, Trash2, FolderKanban, AlertCircle } from "lucide-react";
import { apiClient, ApiError } from "../api/client";
import { Layout } from "../components/Layout";

export const ProjectsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { data: projects, isLoading, error } = useQuery({
    queryKey: ["projects"],
    queryFn: () => apiClient.listProjects(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: { name: string; description?: string }) =>
      apiClient.createProject(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      setShowCreate(false);
      setName("");
      setDescription("");
      setErrorMsg(null);
    },
    onError: (err) => {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to create project");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.deleteProject(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    createMutation.mutate({
      name: name.trim(),
      description: description.trim() || undefined,
    });
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Projects</h1>
            <p className="text-sm text-slate-400 mt-1">
              Isolated workspaces for application logs, patterns, and root-cause analysis
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowCreate(!showCreate)}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors self-start"
          >
            <Plus className="w-4 h-4" />
            New Project
          </button>
        </div>

        {showCreate && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
            <h2 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
              <FolderPlus className="w-4 h-4 text-indigo-400" />
              Create New Project
            </h2>
            {errorMsg && (
              <div className="mb-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
                {errorMsg}
              </div>
            )}
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label htmlFor="proj-name" className="block text-sm font-medium text-slate-300 mb-1">
                  Project Name
                </label>
                <input
                  id="proj-name"
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Production Checkout API"
                  className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label htmlFor="proj-desc" className="block text-sm font-medium text-slate-300 mb-1">
                  Description (optional)
                </label>
                <input
                  id="proj-desc"
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Microservice cluster logs for EU-West production"
                  className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-white text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium inline-flex items-center gap-2"
                >
                  {createMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                  Create Project
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-16 text-slate-400">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading projects...
          </div>
        ) : error ? (
          <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            Failed to load projects.
          </div>
        ) : !projects || projects.length === 0 ? (
          <div className="text-center py-16 bg-slate-900/50 border border-dashed border-slate-800 rounded-2xl">
            <FolderKanban className="w-10 h-10 text-slate-600 mx-auto mb-3" />
            <h3 className="text-base font-medium text-white">No projects yet</h3>
            <p className="text-sm text-slate-400 mt-1 mb-5">
              Create your first project to upload logs or load a simulated incident.
            </p>
            <button
              type="button"
              onClick={() => setShowCreate(true)}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium"
            >
              <Plus className="w-4 h-4" />
              Create First Project
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((proj) => (
              <div
                key={proj.id}
                className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col justify-between hover:border-slate-700 transition-colors"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <Link
                      to={`/projects/${proj.id}`}
                      className="text-base font-semibold text-white hover:text-indigo-300 transition-colors"
                    >
                      {proj.name}
                    </Link>
                    <button
                      type="button"
                      aria-label={`Delete project ${proj.name}`}
                      onClick={() => {
                        if (window.confirm(`Delete "${proj.name}" and all its logs?`)) {
                          deleteMutation.mutate(proj.id);
                        }
                      }}
                      className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                  <p className="text-sm text-slate-400 mt-1.5 line-clamp-2">
                    {proj.description || "No description provided."}
                  </p>
                </div>

                <div className="mt-5 pt-4 border-t border-slate-800/80 flex items-center justify-between">
                  <span className="text-xs text-slate-500">
                    Created {new Date(proj.created_at).toLocaleDateString()}
                  </span>
                  <Link
                    to={`/projects/${proj.id}`}
                    className="inline-flex items-center gap-1 text-xs font-medium text-indigo-400 hover:text-indigo-300"
                  >
                    Open dashboard <ArrowRight className="w-3.5 h-3.5" />
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
};
