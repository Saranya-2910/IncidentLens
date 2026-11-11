import React, { useState } from "react";
import { Link, NavLink, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertOctagon,
  FileSearch,
  FolderKanban,
  Layers,
  LogOut,
  Menu,
  Settings,
  ShieldAlert,
  Upload,
  X,
} from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { apiClient } from "../api/client";

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, logout } = useAuth();
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => apiClient.getProject(projectId!),
    enabled: !!projectId,
  });

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const navItems = projectId
    ? [
        { to: `/projects/${projectId}`, label: "Overview", icon: Activity, end: true },
        { to: `/projects/${projectId}/incidents`, label: "Incidents", icon: AlertOctagon },
        { to: `/projects/${projectId}/patterns`, label: "Error Patterns", icon: Layers },
        { to: `/projects/${projectId}/upload`, label: "Upload Logs", icon: Upload },
        { to: `/projects/${projectId}/events`, label: "Log Explorer", icon: FileSearch },
        { to: `/projects/${projectId}/settings`, label: "API Keys & Settings", icon: Settings },
      ]
    : [
        { to: "/projects", label: "All Projects", icon: FolderKanban, end: true },
      ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col md:flex-row">
      {/* Mobile Header */}
      <header className="md:hidden flex items-center justify-between px-4 py-3 bg-slate-900 border-b border-slate-800">
        <Link to="/projects" className="flex items-center gap-2 font-bold text-lg text-white">
          <ShieldAlert className="w-6 h-6 text-indigo-400" />
          <span>IncidentLens</span>
        </Link>
        <button
          type="button"
          aria-label="Toggle navigation menu"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-2 rounded-lg text-slate-300 hover:bg-slate-800"
        >
          {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </header>

      {/* Sidebar */}
      <aside
        className={`${
          mobileMenuOpen ? "block" : "hidden"
        } md:flex md:flex-col md:w-64 bg-slate-900/90 border-r border-slate-800 shrink-0 justify-between`}
      >
        <div>
          <div className="hidden md:flex items-center gap-2.5 px-5 py-5 border-b border-slate-800/80">
            <ShieldAlert className="w-6 h-6 text-indigo-400 shrink-0" />
            <Link to="/projects" className="font-bold text-lg tracking-tight text-white">
              IncidentLens
            </Link>
          </div>

          {projectId && (
            <div className="px-4 py-3 border-b border-slate-800/80 bg-slate-900">
              <Link
                to="/projects"
                className="text-xs text-indigo-400 hover:text-indigo-300 font-medium inline-flex items-center gap-1 mb-1"
              >
                &larr; All Projects
              </Link>
              <div className="text-sm font-semibold text-white truncate" title={project?.name}>
                {project?.name || "Loading project..."}
              </div>
            </div>
          )}

          <nav className="p-3 space-y-1" aria-label="Primary Navigation">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/30"
                        : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/70"
                    }`
                  }
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  <span>{item.label}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>

        <div className="p-4 border-t border-slate-800/80 space-y-3">
          {user && (
            <div className="px-2">
              <p className="text-xs font-medium text-slate-300 truncate">{user.name}</p>
              <p className="text-[11px] text-slate-500 truncate">{user.email}</p>
            </div>
          )}
          <button
            type="button"
            onClick={handleLogout}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-slate-400 hover:text-rose-300 hover:bg-rose-500/10 transition-colors"
          >
            <LogOut className="w-4 h-4" />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 min-w-0 p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full">
        {children}
      </main>
    </div>
  );
};
