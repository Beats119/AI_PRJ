import { useEffect, useState } from "react";
import { api, type Finding } from "../lib/api";
import { fmt } from "../lib/logic";
import { Badge, Card, EmptyState, PageTitle } from "../components/ui";

export default function Similarity() {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [err, setErr] = useState("");

  const refresh = () =>
    api.similarity().then(setFindings).catch((e) => setErr(String(e.message ?? e)));
  useEffect(() => { refresh(); }, []);

  const act = (f: Finding, status: string) =>
    api.disposition(f.id, status, notes[f.id] ?? f.disposition_note ?? "")
      .then(refresh)
      .catch((e) => setErr(String(e.message ?? e)));

  return (
    <div>
      <PageTitle
        title="Similarity Review"
        sub="Flagged pairs are evidence for a human decision — never proof of copying, and recording a disposition never changes any grade."
      />
      {err && <p className="mb-3 text-sm text-red-600">{err}</p>}
      {findings.length === 0 && (
        <EmptyState>
          No flagged pairs. Pairs at or above the rules' similarity threshold (default 0.85)
          from evaluated batches will appear here.
        </EmptyState>
      )}
      <div className="space-y-3">
        {findings.map((f) => (
          <Card key={f.id} className="p-4">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-medium text-slate-800">
                {f.a.label} <span className="mono text-xs text-slate-400">({f.a.filename})</span>
              </span>
              <span className="text-slate-400">↔</span>
              <span className="font-medium text-slate-800">
                {f.b.label} <span className="mono text-xs text-slate-400">({f.b.filename})</span>
              </span>
              <Badge status={f.review_status} />
              <span className="ml-auto text-sm">
                similarity <strong>{fmt(f.score)}</strong>
                <span className="mono ml-2 text-xs text-slate-400">{f.method}</span>
              </span>
            </div>
            <div className="mt-3 h-1.5 w-full rounded bg-slate-100" role="progressbar" aria-valuenow={f.score * 100} aria-label="similarity">
              <div className="h-1.5 rounded bg-red-500" style={{ width: `${f.score * 100}%` }} />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input
                className="w-72 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
                placeholder="Reviewer note (optional)"
                value={notes[f.id] ?? f.disposition_note ?? ""}
                onChange={(e) => setNotes({ ...notes, [f.id]: e.target.value })}
                aria-label={`Note for finding ${f.id}`}
              />
              <button
                onClick={() => act(f, "dismissed")}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
              >
                Dismiss
              </button>
              <button
                onClick={() => act(f, "confirmed_concern")}
                className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500"
              >
                Confirm concern
              </button>
              {f.review_status !== "pending" && (
                <button
                  onClick={() => act(f, "pending")}
                  className="px-2 py-1.5 text-sm text-slate-500 hover:underline"
                >
                  Reopen
                </button>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
