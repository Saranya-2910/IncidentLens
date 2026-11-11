import React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { AuthPage } from "./pages/AuthPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ProjectOverviewPage } from "./pages/ProjectOverviewPage";
import { UploadLogsPage } from "./pages/UploadLogsPage";
import { EventsExplorerPage } from "./pages/EventsExplorerPage";
import { PatternsPage } from "./pages/PatternsPage";
import { IncidentsListPage } from "./pages/IncidentsListPage";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { ProjectSettingsPage } from "./pages/ProjectSettingsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { user, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading workspace...
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

const PublicOnlyRoute: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { user, isLoading } = useAuth();
  if (isLoading) return null;
  if (user) {
    return <Navigate to="/projects" replace />;
  }
  return <>{children}</>;
};

export function AppRoutes() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <PublicOnlyRoute>
            <AuthPage />
          </PublicOnlyRoute>
        }
      />

      <Route
        path="/projects"
        element={
          <ProtectedRoute>
            <ProjectsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/projects/:projectId"
        element={
          <ProtectedRoute>
            <ProjectOverviewPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/projects/:projectId/upload"
        element={
          <ProtectedRoute>
            <UploadLogsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/projects/:projectId/events"
        element={
          <ProtectedRoute>
            <EventsExplorerPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/projects/:projectId/patterns"
        element={
          <ProtectedRoute>
            <PatternsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/projects/:projectId/incidents"
        element={
          <ProtectedRoute>
            <IncidentsListPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/projects/:projectId/incidents/:incidentId"
        element={
          <ProtectedRoute>
            <IncidentDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/projects/:projectId/settings"
        element={
          <ProtectedRoute>
            <ProjectSettingsPage />
          </ProtectedRoute>
        }
      />

      <Route path="*" element={<Navigate to="/projects" replace />} />
    </Routes>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
