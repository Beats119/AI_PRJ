import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { fmt } from "../lib/logic";
import { Badge, Card, PageTitle } from "../components/ui";

export default function Overview({ go }: { go: (s: string) => void }) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([
      api.assignments(), api.batches(), api.runs(), api.similarity(),
      api.dependencies(),
    ])
      .then(([assignments, batches, runs, findings, deps]) =>
        setData({ assignments, batches, runs, findings, deps })
      )
      .catch((e) => setErr(String(e.message ?? e)));
  }, []);

  if (err) return <p className="text-sm text-red-600">Could not reach the API: {err}. Is `autograder api` running?</p>;
  if (!data) return <p className="text-sm text-slate-500">Loading…</p>;

  const activeVersions = data.assignments.reduce(
    (n: number, a: any) => n + a.versions.filter((v: any) => v.status === "active").length, 0
  );
  const pending = data.findings.filter((f: any) => f.review_status === "pending").length;
  const cards = [
    { label: "Assignments", value: data.assignments.length, hint: `${activeVersions} active version(s)`, go: "assignments" },
    { label: "Batches", value: data.batches.length, hint: "submission batches", go: "results" },
    { label: "Evaluation runs", value: data.runs.length, hint: "durable, refresh-safe", go: "runs" },
    { label: "Similarity flags pending", value: pending, hint: "review never changes grades", go: "similarity" },
  ];
  return (
    <div>
      <PageTitle
        title="Overview"
        sub="One assignment → many submissions → one consolidated, evidence-backed result set."
      />
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {cards.map((c) => (
          <button key={c.label} onClick={() => go(c.go)} className="text-left">
            <Card className="p-4 transition hover:ring-indigo-300">
              <div className="text-2xl font-semibold text-slate-900">{c.value}</div>
              <div className="mt-0.5 text-sm font-medium text-slate-700">{c.label}</div>
              <div className="text-xs text-slate-400">{c.hint}</div>
            </Card>
          </button>
        ))}
      </div>

      <Card className="mt-6 p-4">
        <h2 className="mb-1 text-sm font-semibold text-slate-800">Environment</h2>
        <p className="text-sm text-slate-600">
          Sandbox backend:{" "}
          <strong>{data.deps.sandbox.selected_backend}</strong>
          {data.deps.sandbox.docker_available
            ? " (Docker available)"
            : " (Docker not available on this machine — process isolation, honestly reported)"}{" "}
          · GCC: <span className="mono text-xs">{data.deps.gcc}</span> · Ollama:{" "}
          {data.deps.ollama.reachable ? "reachable" : "unreachable — deterministic mode"}
        </p>
      </Card>

      <Card className="mt-6">
        <h2 className="border-b border-slate-100 px-4 py-3 text-sm font-semibold text-slate-800">
          Recent evaluation runs
        </h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
              <th className="px-4 py-2">Run</th><th className="px-4 py-2">State</th>
              <th className="px-4 py-2">Outcome</th><th className="px-4 py-2">Grade</th>
            </tr>
          </thead>
          <tbody>
            {data.runs.slice(0, 8).map((r: any) => (
              <tr key={r.id} className="border-t border-slate-50">
                <td className="px-4 py-2 mono text-xs">run-{r.id}</td>
                <td className="px-4 py-2"><Badge status={r.state} /></td>
                <td className="px-4 py-2">{r.overall_status || "—"}</td>
                <td className="px-4 py-2 font-medium">{fmt(r.grade)}</td>
              </tr>
            ))}
            {data.runs.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-slate-400">
                No runs yet — create an assignment, then upload a batch.
              </td></tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
