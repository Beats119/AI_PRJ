import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { fmt } from "../lib/logic";
import { Badge, Card, EmptyState, PageTitle } from "../components/ui";

export default function Runs() {
  const [runs, setRuns] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const refresh = () =>
    api.runs().then(setRuns).catch((e) => setErr(String(e.message ?? e)));
  useEffect(() => { refresh(); }, []);

  return (
    <div>
      <PageTitle
        title="Evaluation Runs"
        sub="Durable lifecycle states (queued → preparing → compiling → testing → analyzing → validating evidence → scoring → reporting → terminal). Refreshing the page never loses a run; a retry creates a new run linked to its predecessor."
      />
      {err && <p className="mb-3 text-sm text-red-600">{err}</p>}
      {runs.length === 0 && <EmptyState>No runs yet.</EmptyState>}
      {runs.length > 0 && (
        <Card>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-4 py-2">Run</th><th className="px-4 py-2">Submission</th>
                <th className="px-4 py-2">State</th><th className="px-4 py-2">Outcome</th>
                <th className="px-4 py-2">Grade</th><th className="px-4 py-2">Retry of</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-t border-slate-50">
                  <td className="px-4 py-2 mono text-xs">run-{r.id}</td>
                  <td className="px-4 py-2 mono text-xs">submission-{r.submission_id}</td>
                  <td className="px-4 py-2"><Badge status={r.state} /></td>
                  <td className="px-4 py-2">{r.overall_status || "—"}</td>
                  <td className="px-4 py-2 font-medium">{fmt(r.grade)}</td>
                  <td className="px-4 py-2 mono text-xs">{r.retry_of_run_id ? `run-${r.retry_of_run_id}` : "—"}</td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => api.retryRun(r.id).then(refresh)}
                      className="font-medium text-indigo-600 hover:underline"
                    >
                      Retry
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
