import { useState } from "react";
import Overview from "./pages/Overview";
import Assignments from "./pages/Assignments";
import Results from "./pages/Results";
import Similarity from "./pages/Similarity";
import Runs from "./pages/Runs";
import Settings from "./pages/Settings";

const NAV = [
  { id: "overview", label: "Overview", icon: "▦" },
  { id: "assignments", label: "Assignments", icon: "✎" },
  { id: "results", label: "Submissions & Results", icon: "☰" },
  { id: "similarity", label: "Similarity Review", icon: "⧉" },
  { id: "runs", label: "Evaluation Runs", icon: "▶" },
  { id: "settings", label: "Settings & Health", icon: "⚙" },
] as const;

type Section = (typeof NAV)[number]["id"];

export default function App() {
  const [section, setSection] = useState<Section>("overview");
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col bg-slate-900 text-slate-200">
        <div className="px-5 pb-4 pt-6">
          <div className="text-lg font-semibold tracking-tight text-white">
            AutoGrader
          </div>
          <div className="text-xs text-slate-400">
            Evidence-based grading for C
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3" aria-label="Primary">
          {NAV.map((n) => (
            <button
              key={n.id}
              onClick={() => setSection(n.id)}
              aria-current={section === n.id ? "page" : undefined}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm font-medium transition ${
                section === n.id
                  ? "bg-indigo-600 text-white"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white"
              }`}
            >
              <span aria-hidden className="w-4 text-center">{n.icon}</span>
              {n.label}
            </button>
          ))}
        </nav>
        <div className="px-5 py-4 text-xs leading-relaxed text-slate-500">
          Deterministic scoring (d3-v1) · oracle-v2 ·
          no reference solutions, ever.
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-8 py-6">
        {section === "overview" && <Overview go={(s) => setSection(s as Section)} />}
        {section === "assignments" && <Assignments />}
        {section === "results" && <Results />}
        {section === "similarity" && <Similarity />}
        {section === "runs" && <Runs />}
        {section === "settings" && <Settings />}
      </main>
    </div>
  );
}
