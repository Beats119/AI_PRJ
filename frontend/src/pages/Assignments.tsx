import { useCallback, useEffect, useState } from "react";
import { api, type AssignmentSummary, type VersionDetail } from "../lib/api";
import { testState } from "../lib/logic";
import { Badge, Card, EmptyState, ErrorBox, PageTitle } from "../components/ui";

const inputCls =
  "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100";
const labelCls = "mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500";

export default function Assignments() {
  const [list, setList] = useState<AssignmentSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<VersionDetail[]>([]);
  const [name, setName] = useState("");
  const [err, setErr] = useState("");

  const refresh = useCallback(() => {
    api.assignments().then(setList).catch((e) => setErr(String(e.message ?? e)));
  }, []);
  useEffect(refresh, [refresh]);

  useEffect(() => {
    if (selected === null) return;
    api.assignment(selected).then((a) => setDetail(a.versions)).catch(() => setDetail([]));
  }, [selected, list]);

  return (
    <div>
      <PageTitle
        title="Assignments"
        sub="Create an assignment, prepare its trusted suite, review the evidence, then activate the version. Drafts below the sufficiency bar can never be activated."
      />
      {err && <ErrorBox message={err} />}

      <Card className="mb-6 p-4">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            api.createAssignment(name).then((a) => {
              setName(""); refresh(); setSelected(a.id);
            }).catch((e) => setErr(String(e.message ?? e)));
          }}
        >
          <input
            className={inputCls}
            placeholder="New assignment name, e.g. Add two integers"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label="Assignment name"
          />
          <button className="shrink-0 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500">
            Create assignment
          </button>
        </form>
      </Card>

      {list.length === 0 && <EmptyState>No assignments yet. Create your first one above.</EmptyState>}

      <div className="space-y-3">
        {list.map((a) => (
          <Card key={a.id} className="p-4">
            <button
              className="flex w-full items-center justify-between text-left"
              onClick={() => setSelected(selected === a.id ? null : a.id)}
              aria-expanded={selected === a.id}
            >
              <span className="font-medium text-slate-800">{a.name}</span>
              <span className="flex gap-2">
                {a.versions.map((v) => (
                  <Badge key={v.id} status={v.status} label={`v${v.version_no} · ${v.status}`} />
                ))}
                {a.versions.length === 0 && <span className="text-xs text-slate-400">no versions</span>}
              </span>
            </button>
            {selected === a.id && (
              <div className="mt-4 border-t border-slate-100 pt-4">
                <VersionWizard
                  assignmentId={a.id}
                  onCreated={refresh}
                />
                {detail.map((v) => (
                  <VersionView key={v.id} v={v} assignmentId={a.id} onActivated={refresh} />
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}

function VersionWizard({
  assignmentId, onCreated,
}: { assignmentId: number; onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [problem, setProblem] = useState("");
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [examplesText, setExamplesText] = useState("[]");
  const [rulesText, setRulesText] = useState("");
  const [problems, setProblems] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (!open)
    return (
      <button
        onClick={() => setOpen(true)}
        className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-100"
      >
        + New version (guided)
      </button>
    );

  const loadExample = () =>
    api.example().then((ex: any) => {
      setProblem(ex.problem); setInput(ex.input); setOutput(ex.output);
      setExamplesText(JSON.stringify(ex.examples, null, 1));
      setRulesText(JSON.stringify(ex.rules, null, 1));
    });

  const validate = () => {
    try {
      const rules = JSON.parse(rulesText);
      api.validateRules(rules).then((r) => setProblems(r.valid ? [] : r.problems));
    } catch (e) {
      setProblems([`rules JSON does not parse: ${String(e)}`]);
    }
  };

  const submit = () => {
    setBusy(true); setErr("");
    try {
      const payload = {
        problem, input, output,
        examples: JSON.parse(examplesText),
        rules: JSON.parse(rulesText),
      };
      api.createVersion(assignmentId, payload)
        .then(() => { setOpen(false); onCreated(); })
        .catch((e) => setErr(String(e.message ?? e)))
        .finally(() => setBusy(false));
    } catch (e) {
      setErr(`JSON parse error: ${String(e)}`);
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">New version — problem, examples, rules</h3>
        <button onClick={loadExample} className="text-sm font-medium text-indigo-600 hover:underline">
          Load the worked example
        </button>
      </div>
      <div className="grid gap-3">
        <div>
          <label className={labelCls} htmlFor="f-problem">Problem statement</label>
          <textarea id="f-problem" className={inputCls} rows={2} value={problem} onChange={(e) => setProblem(e.target.value)} />
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className={labelCls} htmlFor="f-input">Input contract</label>
            <textarea id="f-input" className={inputCls} rows={2} value={input} onChange={(e) => setInput(e.target.value)} />
          </div>
          <div>
            <label className={labelCls} htmlFor="f-output">Output contract</label>
            <textarea id="f-output" className={inputCls} rows={2} value={output} onChange={(e) => setOutput(e.target.value)} />
          </div>
        </div>
        <div>
          <label className={labelCls} htmlFor="f-examples">Instructor examples (JSON array of input/expected/category)</label>
          <textarea id="f-examples" className={`${inputCls} mono text-xs`} rows={4} value={examplesText} onChange={(e) => setExamplesText(e.target.value)} />
        </div>
        <div>
          <label className={labelCls} htmlFor="f-rules">Grading rules (JSON) — metrics, weights, thresholds</label>
          <textarea id="f-rules" className={`${inputCls} mono text-xs`} rows={10} value={rulesText} onChange={(e) => setRulesText(e.target.value)} />
        </div>
      </div>
      {problems.length > 0 && (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-red-200">
          <strong>Rules problems:</strong>
          <ul className="mt-1 list-disc pl-5">
            {problems.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        </div>
      )}
      {err && <div className="mt-3"><ErrorBox message={err} /></div>}
      <div className="mt-4 flex gap-2">
        <button onClick={validate} className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-50">
          Validate rules
        </button>
        <button
          onClick={submit} disabled={busy}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {busy ? "Preparing suite…" : "Create version & prepare suite"}
        </button>
        <button onClick={() => setOpen(false)} className="px-3 py-2 text-sm text-slate-500 hover:underline">
          Cancel
        </button>
      </div>
      <p className="mt-3 text-xs text-slate-400">
        Preparation runs the real pipeline: specification → bounded candidate generation → oracle
        verification (instructor examples + independent derivation; no reference solutions) → the
        sufficiency bar. Nothing becomes score-affecting until you activate a validated version.
      </p>
    </div>
  );
}

function VersionView({
  v, assignmentId, onActivated,
}: { v: VersionDetail; assignmentId: number; onActivated: () => void }) {
  const [showSuite, setShowSuite] = useState(false);
  const [err, setErr] = useState("");
  const conditions = v.sufficiency.conditions ?? [];
  return (
    <div className="mt-4 rounded-xl border border-slate-200 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-medium text-slate-800">Version {v.version_no}</span>
          <Badge status={v.status} />
          <span className="mono text-xs text-slate-400">rules {v.rules_hash.slice(0, 15)}…</span>
        </div>
        {v.status === "validated" && (
          <button
            onClick={() =>
              api.activate(assignmentId, v.id).then(onActivated).catch((e) => setErr(String(e.message ?? e)))
            }
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
          >
            Activate this version
          </button>
        )}
        {v.status === "draft" && (
          <span className="text-xs text-red-600">
            Draft — below the sufficiency bar, cannot be activated.
          </span>
        )}
      </div>
      {err && <div className="mt-2"><ErrorBox message={err} /></div>}

      {v.unresolved.length > 0 && (
        <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 ring-1 ring-amber-200">
          <strong>Needs review / unresolved:</strong>
          <ul className="mt-1 list-disc pl-5">
            {v.unresolved.map((u, i) => <li key={i}>{u}</li>)}
          </ul>
        </div>
      )}

      {conditions.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-medium text-slate-700">
            Sufficiency evidence ({conditions.filter((c) => c.passed).length}/{conditions.length} conditions pass)
          </summary>
          <ul className="mt-2 space-y-1 text-sm">
            {conditions.map((c) => (
              <li key={c.name} className="flex gap-2">
                <span aria-hidden>{c.passed ? "✓" : "✕"}</span>
                <span className="mono text-xs text-slate-500">{c.name}</span>
                <span className="text-slate-600">{c.detail}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      <button
        onClick={() => setShowSuite(!showSuite)}
        className="mt-3 text-sm font-medium text-indigo-600 hover:underline"
        aria-expanded={showSuite}
      >
        {showSuite ? "Hide" : "Preview"} test suite ({v.suite.length} cases)
      </button>
      {showSuite && (
        <div className="mt-2 max-h-80 overflow-auto rounded-lg border border-slate-100">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-3 py-2">Test</th><th className="px-3 py-2">Input</th>
                <th className="px-3 py-2">Expected</th><th className="px-3 py-2">Category</th>
                <th className="px-3 py-2">State</th><th className="px-3 py-2">Verified by</th>
              </tr>
            </thead>
            <tbody>
              {v.suite.map((t) => (
                <tr key={t.test_id} className="border-t border-slate-50">
                  <td className="px-3 py-1.5 mono text-xs">{t.test_id}</td>
                  <td className="px-3 py-1.5 mono text-xs">{JSON.stringify(t.input_data)}</td>
                  <td className="px-3 py-1.5 mono text-xs">{t.expected_output ?? "—"}</td>
                  <td className="px-3 py-1.5 text-xs">{t.category}</td>
                  <td className="px-3 py-1.5"><Badge status={testState(t) === "validated" ? "trusted" : testState(t)} label={testState(t)} /></td>
                  <td className="px-3 py-1.5 text-xs text-slate-500">{t.validation_method}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
