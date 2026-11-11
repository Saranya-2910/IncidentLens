import React from "react";
import { AlertTriangle, CheckCircle2, HelpCircle, ShieldAlert, ShieldCheck, Clock } from "lucide-react";

export const SeverityBadge: React.FC<{ severity: string }> = ({ severity }) => {
  const s = severity.toLowerCase();
  const styles: Record<string, string> = {
    critical: "bg-red-500/15 text-red-400 border-red-500/30",
    high: "bg-orange-500/15 text-orange-400 border-orange-500/30",
    medium: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    low: "bg-sky-500/15 text-sky-400 border-sky-500/30",
  };
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border uppercase tracking-wider ${
        styles[s] || "bg-slate-800 text-slate-300 border-slate-700"
      }`}
    >
      {s}
    </span>
  );
};

export const LevelBadge: React.FC<{ level: string }> = ({ level }) => {
  const l = level.toUpperCase();
  const styles: Record<string, string> = {
    FATAL: "bg-red-600/20 text-red-400 border-red-500/40",
    CRITICAL: "bg-red-600/20 text-red-400 border-red-500/40",
    ERROR: "bg-rose-500/15 text-rose-400 border-rose-500/30",
    WARN: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    INFO: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
    DEBUG: "bg-slate-800 text-slate-400 border-slate-700",
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-semibold border ${
        styles[l] || "bg-slate-800 text-slate-300 border-slate-700"
      }`}
    >
      {l}
    </span>
  );
};

export const IncidentStatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const isResolved = status === "resolved";
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${
        isResolved
          ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
          : "bg-rose-500/15 text-rose-400 border-rose-500/30"
      }`}
    >
      {isResolved ? (
        <CheckCircle2 className="w-3.5 h-3.5" />
      ) : (
        <AlertTriangle className="w-3.5 h-3.5" />
      )}
      {isResolved ? "Resolved" : "Open"}
    </span>
  );
};

export const ValidationStatusBadge: React.FC<{ status: string; unsupportedCount?: number }> = ({
  status,
  unsupportedCount = 0,
}) => {
  if (status === "verified") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
        <ShieldCheck className="w-3.5 h-3.5" />
        Evidence Verified (100% Supported)
      </span>
    );
  }
  if (status === "partial") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/15 text-amber-300 border border-amber-500/30">
        <ShieldAlert className="w-3.5 h-3.5" />
        Partial Verification ({unsupportedCount} unsupported claim{unsupportedCount === 1 ? "" : "s"})
      </span>
    );
  }
  if (status === "unverified" || status === "failed") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/15 text-red-300 border border-red-500/30">
        <AlertTriangle className="w-3.5 h-3.5" />
        {status === "failed" ? "Verification Failed" : "Unverified"}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700">
      <HelpCircle className="w-3.5 h-3.5" />
      {status}
    </span>
  );
};

export const BatchStatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const s = status.toLowerCase();
  if (s === "done") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
        <CheckCircle2 className="w-3 h-3" /> Done
      </span>
    );
  }
  if (s === "failed") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-500/15 text-red-400 border border-red-500/30">
        <AlertTriangle className="w-3 h-3" /> Failed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 animate-pulse">
      <Clock className="w-3 h-3" /> {status}
    </span>
  );
};
