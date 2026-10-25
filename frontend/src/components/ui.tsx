import type { ReactNode } from "react";

/** Status is never conveyed by colour alone: every badge carries an
 * icon + text label (prompt §8.7). */
const STATUS_META: Record<string, { icon: string; cls: string }> = {
  complete: { icon: "✓", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  completed: { icon: "✓", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  passed: { icon: "✓", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  partial: { icon: "◐", cls: "bg-amber-50 text-amber-800 ring-amber-200" },
  provisional: { icon: "◐", cls: "bg-amber-50 text-amber-800 ring-amber-200" },
  incomplete: { icon: "!", cls: "bg-red-50 text-red-700 ring-red-200" },
  failed: { icon: "✕", cls: "bg-red-50 text-red-700 ring-red-200" },
  error: { icon: "✕", cls: "bg-red-50 text-red-700 ring-red-200" },
  active: { icon: "●", cls: "bg-indigo-50 text-indigo-700 ring-indigo-200" },
  validated: { icon: "✓", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  draft: { icon: "✎", cls: "bg-slate-100 text-slate-600 ring-slate-200" },
  superseded: { icon: "↺", cls: "bg-slate-100 text-slate-500 ring-slate-200" },
  queued: { icon: "…", cls: "bg-slate-100 text-slate-600 ring-slate-200" },
  stored: { icon: "•", cls: "bg-slate-100 text-slate-600 ring-slate-200" },
  duplicate: { icon: "⧉", cls: "bg-amber-50 text-amber-800 ring-amber-200" },
  pending: { icon: "?", cls: "bg-amber-50 text-amber-800 ring-amber-200" },
  confirmed_concern: { icon: "⚑", cls: "bg-red-50 text-red-700 ring-red-200" },
  dismissed: { icon: "✓", cls: "bg-slate-100 text-slate-600 ring-slate-200" },
  trusted: { icon: "✓", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  untrusted: { icon: "?", cls: "bg-amber-50 text-amber-800 ring-amber-200" },
  rejected: { icon: "✕", cls: "bg-red-50 text-red-700 ring-red-200" },
  validated_test: { icon: "✓", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  requires_review: { icon: "?", cls: "bg-amber-50 text-amber-800 ring-amber-200" },
};

export function Badge({ status, label }: { status: string; label?: string }) {
  const meta = STATUS_META[status] ?? { icon: "•", cls: "bg-slate-100 text-slate-600 ring-slate-200" };
  return (
    <span
      data-status={status}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${meta.cls}`}
    >
      <span aria-hidden>{meta.icon}</span>
      {label ?? status.replace(/_/g, " ")}
    </span>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl bg-white shadow-sm ring-1 ring-slate-200 ${className}`}>
      {children}
    </div>
  );
}

export function PageTitle({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-5">
      <h1 className="text-xl font-semibold tracking-tight text-slate-900">{title}</h1>
      {sub && <p className="mt-1 text-sm text-slate-500">{sub}</p>}
    </div>
  );
}

export function ScoreBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  const color = pct >= 85 ? "bg-emerald-500" : pct >= 60 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="h-1.5 w-full rounded bg-slate-100" role="progressbar" aria-valuenow={pct}>
      <div className={`h-1.5 rounded ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white/60 px-6 py-10 text-center text-sm text-slate-500">
      {children}
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-200">
      {message}
    </div>
  );
}
