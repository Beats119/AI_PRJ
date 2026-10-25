import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type BatchDto, type RunDetail } from "../lib/api";
import {
  filterResults, fmt, fmtScore, resultsToCsv, sortByGrade,
  validateUploadFiles,
} from "../lib/logic";
import { Badge, Card, EmptyState, ErrorBox, PageTitle, ScoreBar } from "../components/ui";

export default function Results() {
  const [versions, setVersions] = useState<{ id: number; label: string }[]>([]);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [batches, setBatches] = useState<{ id: number; status: string; submissions: number }[]>([]);
  const [batch, setBatch] = useState<BatchDto | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [gradeDir, setGradeDir] = useState<1 | -1>(-1);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [inspectId, setInspectId] = useState<number | null>(null);

  const refreshBatches = useCallback(() => {
    api.batches().then(setBatches).catch(() => {});
  }, []);
  useEffect(refreshBatches, [refreshBatches]);

  useEffect(() => {
    api.assignments().then((as) => {
      const vs: { id: number; label: string }[] = [];
      for (const a of as)
        for (const v of a.versions)
          if (v.status === "active" || v.status === "validated")
            vs.push({ id: v.id, label: `${a.name} — v${v.version_no} (${v.status})` });
      setVersions(vs);
      if (vs.length && versionId === null) setVersionId(vs[vs.length - 1].id);
    }).catch(() => {});
  }, [versionId]);

  const uploadProblems = useMemo(
    () => validateUploadFiles(files.map((f) => ({ name: f.name, size: f.size }))),
    [files]
  );

  const upload = async () => {
    if (versionId === null || files.length === 0) return;
    setBusy("uploading"); setErr("");
    try {
      const b = await api.createBatch(versionId, files);
      setBatch(b); setFiles([]); refreshBatches();
    } catch (e: any) {
      setErr(String(e.message ?? e));
    } finally { setBusy(""); }
  };

  const evaluate = async () => {
    if (!batch) return;
    setBusy("evaluating"); setErr("");
    try {
      setBatch(await api.evaluateBatch(batch.id));
      refreshBatches();
    } catch (e: any) {
      setErr(String(e.message ?? e));
    } finally { setBusy(""); }
  };

  const rows = useMemo(() => {
    if (!batch) return [];
    return sortByGrade(filterResults(batch.submissions, query, status), gradeDir);
  }, [batch, query, status, gradeDir]);

  const exportCsv = () => {
    if (!batch) return;
    const blob = new Blob([resultsToCsv(batch.submissions)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `batch-${batch.id}-results.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <PageTitle
        title="Submissions & Results"
        sub="Upload a whole class batch at once. Every submission is graded against the same active version; peers form the similarity corpus. Duplicates are detected, never silently dropped."
      />
      {err && <ErrorBox message={err} />}

      <Card className="mb-6 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="grid gap-1 text-sm">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Assignment version</span>
            <select
              className="rounded-lg border border-slate-300 px-3 py-2"
              value={versionId ?? ""}
              onChange={(e) => setVersionId(Number(e.target.value))}
            >
              {versions.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
            </select>
          </label>
          <label className="grid gap-1 text-sm">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Student .c files (multiple)</span>
            <input
              type="file" accept=".c" multiple
              aria-label="Choose C files"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              className="rounded-lg border border-slate-300 px-3 py-1.5"
            />
          </label>
          <button
            onClick={upload}
            disabled={busy !== "" || files.length === 0 || uploadProblems.length > 0}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {busy === "uploading" ? "Uploading…" : `Upload batch (${files.length})`}
          </button>
          {batches.length > 0 && (
            <label className="grid gap-1 text-sm">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Open batch</span>
              <select
                className="rounded-lg border border-slate-300 px-3 py-2"
                value={batch?.id ?? ""}
                onChange={(e) => api.batch(Number(e.target.value)).then(setBatch)}
              >
                <option value="">Select…</option>
                {batches.map((b) => (
                  <option key={b.id} value={b.id}>Batch {b.id} · {b.submissions} files · {b.status}</option>
                ))}
              </select>
            </label>
          )}
        </div>
        {uploadProblems.length > 0 && (
          <ul className="mt-3 list-disc pl-5 text-sm text-red-600">
            {uploadProblems.map((p, i) => <li key={i}>{p.file}: {p.problem}</li>)}
          </ul>
        )}
        {files.length > 0 && uploadProblems.length === 0 && (
          <p className="mt-3 text-sm text-slate-500">
            Ready: {files.map((f) => f.name).join(", ")} — labels default to filenames.
          </p>
        )}
      </Card>

      {!batch && <EmptyState>Upload a batch or open an existing one to see consolidated results.</EmptyState>}

      {batch && (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-800">
              Batch {batch.id} · {batch.submissions.length} submissions · <Badge status={batch.status} />
            </h2>
            <div className="flex gap-2">
              <button
                onClick={evaluate} disabled={busy !== ""}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {busy === "evaluating" ? "Evaluating…" : "Evaluate batch"}
              </button>
              <button onClick={exportCsv} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50">
                Export CSV
              </button>
            </div>
          </div>
          <div className="flex flex-wrap gap-3 px-4 py-3">
            <input
              className="w-64 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
              placeholder="Search label, filename, flag…"
              value={query} onChange={(e) => setQuery(e.target.value)}
              aria-label="Search results"
            />
            <select
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
              value={status} onChange={(e) => setStatus(e.target.value)}
              aria-label="Filter by status"
            >
              <option value="all">All outcomes</option>
              <option value="complete">Complete</option>
              <option value="partial">Partial</option>
              <option value="provisional">Provisional</option>
              <option value="incomplete">Incomplete</option>
              <option value="duplicate">Duplicates</option>
            </select>
            <button
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
              onClick={() => setGradeDir(gradeDir === 1 ? -1 : 1)}
            >
              Grade {gradeDir === -1 ? "↓ high first" : "↑ low first"}
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-2">Submission</th><th className="px-4 py-2">Tests</th>
                  <th className="px-4 py-2">Compile</th><th className="px-4 py-2">Outcome</th>
                  <th className="px-4 py-2">Grade</th><th className="px-4 py-2">Flags</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.submission_id} className="border-t border-slate-50 hover:bg-slate-50/60">
                    <td className="px-4 py-2">
                      <div className="font-medium text-slate-800">{r.label}</div>
                      <div className="mono text-xs text-slate-400">{r.filename}</div>
                    </td>
                    <td className="px-4 py-2">
                      {r.tests_total ? `${r.tests_passed}/${r.tests_total}` : "—"}
                    </td>
                    <td className="px-4 py-2">
                      {r.compile_ok === null ? "—" : r.compile_ok ? "✓ ok" : "✕ failed"}
                    </td>
                    <td className="px-4 py-2">
                      {r.status === "duplicate" ? <Badge status="duplicate" /> :
                        r.overall_status ? <Badge status={r.overall_status} /> :
                        <Badge status={r.run_state ?? "queued"} />}
                    </td>
                    <td className="px-4 py-2">
                      <div className="font-semibold">{fmtScore(r.grade)}</div>
                      {r.grade !== null && <div className="mt-1 w-24"><ScoreBar value={r.grade} /></div>}
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex flex-wrap gap-1">
                        {r.flags.map((f) => (
                          <span key={f} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{f}</span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-2">
                      {r.run_id && (
                        <button
                          onClick={() => setInspectId(inspectId === r.run_id ? null : r.run_id)}
                          className="font-medium text-indigo-600 hover:underline"
                        >
                          Investigate
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                    No submissions match the current filter.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
          {inspectId !== null && <Investigation runId={inspectId} />}
        </Card>
      )}
    </div>
  );
}

function Investigation({ runId }: { runId: number }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [source, setSource] = useState("");
  useEffect(() => {
    api.run(runId).then((r) => {
      setRun(r);
      if (r.report?.submission_hash) {
        // source fetched via submissions endpoint using the run's submission
        fetch(`/api/submissions/${(r as any).submission_id}`)
          .then((x) => x.json()).then((s) => setSource(s.source ?? "")).catch(() => {});
      }
    }).catch(() => {});
  }, [runId]);
  if (!run) return <div className="border-t border-slate-100 px-4 py-4 text-sm text-slate-500">Loading investigation…</div>;
  if (!run.report)
    return (
      <div className="border-t border-slate-100 px-4 py-4 text-sm">
        Run state: <Badge status={run.state} />
        {run.error && <p className="mt-2 text-red-600">{run.error}</p>}
      </div>
    );
  const correctness = run.evidence.find((e) => e.kind === "correctness");
  const failing = (correctness?.payload?.evidence?.failing ?? []) as any[];
  const report: any = run.report;
  return (
    <div className="border-t-2 border-indigo-100 bg-slate-50/50 px-4 py-4">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold text-slate-800">
          Investigation — {report.submission_name}
        </h3>
        <Badge status={report.overall_status} />
        <span className="text-sm font-semibold">{fmtScore(report.overall_grade)}</span>
        <span className="mono text-xs text-slate-400">run {run.id} · rules {String(report.rules_hash).slice(0, 15)}…</span>
        <span className="ml-auto flex gap-3 text-sm">
          <a className="font-medium text-indigo-600 hover:underline" href={`/api/submissions/${(run as any).submission_id}/report?format=html`} target="_blank" rel="noreferrer">HTML report</a>
          <a className="font-medium text-indigo-600 hover:underline" href={`/api/submissions/${(run as any).submission_id}/report?format=txt`} target="_blank" rel="noreferrer">TXT</a>
          <a className="font-medium text-indigo-600 hover:underline" href={`/api/submissions/${(run as any).submission_id}/report?format=json`} target="_blank" rel="noreferrer">JSON</a>
        </span>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Rubric breakdown — every point traceable
          </h4>
          <table className="w-full rounded-lg bg-white text-sm ring-1 ring-slate-200">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-400">
              <tr><th className="px-3 py-2">Metric</th><th className="px-3 py-2">Weight</th>
                <th className="px-3 py-2">Eff. weight</th><th className="px-3 py-2">Score</th>
                <th className="px-3 py-2">Contrib.</th><th className="px-3 py-2">Status</th></tr>
            </thead>
            <tbody>
              {run.breakdown.map((b) => (
                <tr key={b.name} className="border-t border-slate-50">
                  <td className="px-3 py-1.5 font-medium">{b.name}</td>
                  <td className="px-3 py-1.5">{fmt(Number(b.configured_weight) * 100)}</td>
                  <td className="px-3 py-1.5">{b.effective_weight === null ? "excluded" : fmt(Number(b.effective_weight) * 100)}</td>
                  <td className="px-3 py-1.5">{b.score === null ? "—" : fmt(b.score)}</td>
                  <td className="px-3 py-1.5 font-medium">{b.contribution === null ? "—" : fmt(b.contribution)}</td>
                  <td className="px-3 py-1.5"><Badge status={b.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {failing.length > 0 && (
            <>
              <h4 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Failing tests — input / expected / actual
              </h4>
              <div className="space-y-2">
                {failing.slice(0, 5).map((f, i) => (
                  <div key={i} className="rounded-lg bg-white px-3 py-2 text-xs ring-1 ring-slate-200">
                    <span className="mono font-semibold">{f.test_id}</span>
                    <span className="text-slate-500"> — {f.outcome}:</span>{" "}
                    input <code>{JSON.stringify(f.input)}</code> · expected{" "}
                    <code>{JSON.stringify(f.expected)}</code> · actual{" "}
                    <code>{JSON.stringify(f.actual ?? f.error)}</code>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Source</h4>
          <pre className="max-h-96 overflow-auto rounded-lg bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">{source || "…"}</pre>
          {report.limitations?.length > 0 && (
            <>
              <h4 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Limitations recorded with this grade
              </h4>
              <ul className="list-disc space-y-1 pl-5 text-xs text-slate-500">
                {report.limitations.slice(0, 4).map((l: string, i: number) => <li key={i}>{l}</li>)}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
