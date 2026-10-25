import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Badge, Card, PageTitle } from "../components/ui";

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-6 border-b border-slate-50 py-2 last:border-0">
      <span className="text-sm text-slate-500">{k}</span>
      <span className="text-right text-sm font-medium text-slate-800">{v}</span>
    </div>
  );
}

export default function Settings() {
  const [deps, setDeps] = useState<any>(null);
  const [model, setModel] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([api.dependencies(), api.modelStatus()])
      .then(([d, m]) => { setDeps(d); setModel(m); })
      .catch((e) => setErr(String(e.message ?? e)));
  }, []);

  if (err) return <p className="text-sm text-red-600">{err}</p>;
  if (!deps) return <p className="text-sm text-slate-500">Loading…</p>;
  const sb = deps.sandbox;
  return (
    <div>
      <PageTitle title="Settings & Health" sub="Live dependency state — nothing here is decorative." />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-800">Sandbox</h2>
          <Row k="Selected backend" v={<Badge status={sb.selected_backend === "docker" ? "active" : "validated"} label={sb.selected_backend} />} />
          <Row k="Docker available" v={sb.docker_available ? "yes" : "no — not installed/reachable on this machine"} />
          <Row k="Docker image" v={<span className="mono text-xs">{sb.docker_image}</span>} />
          <Row k="Fail closed" v={sb.fail_closed ? "yes — docker selected but unavailable" : "n/a"} />
          <p className="mt-3 text-xs leading-relaxed text-slate-400">{sb.process_backend_note}</p>
        </Card>
        <Card className="p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-800">Model (Ollama)</h2>
          <Row k="Base URL" v={<span className="mono text-xs">{model.base_url}</span>} />
          <Row k="Model" v={<span className="mono text-xs">{model.model}</span>} />
          <Row k="Reachable" v={model.reachable ? "yes" : "no"} />
          <Row k="Model available" v={model.model_available ? "yes" : "no"} />
          <p className="mt-3 text-xs leading-relaxed text-slate-400">{model.note}</p>
        </Card>
        <Card className="p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-800">Toolchain</h2>
          <Row k="GCC" v={<span className="mono text-xs">{deps.gcc}</span>} />
          <Row k="Database" v={deps.database} />
          <Row k="Data directory" v={<span className="mono text-xs">{deps.data_dir}</span>} />
        </Card>
        <Card className="p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-800">Grading policies</h2>
          <Row k="Scoring" v="d3-v1 (deterministic, Decimal)" />
          <Row k="Oracle" v="oracle-v2 — instructor examples + independent derivation" />
          <Row k="Reference solutions" v="never used (master prompt §5.2)" />
          <Row k="Similarity" v="flags for review; never a deduction by itself" />
        </Card>
      </div>
    </div>
  );
}
