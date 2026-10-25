/** Pure UI logic: formatting, CSV export, filtering, upload validation.
 * Kept dependency-free so it is directly unit-testable. */

/** Format a number for display: at most 2 decimals, no trailing zeros.
 * Fixes the raw-Decimal eyesore of the v1 UI (0.7916666...). */
export function fmt(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return "—";
  return String(Math.round(n * 100) / 100);
}

export function fmtScore(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "no grade";
  return `${fmt(value)} / 100`;
}

/** Neutralize spreadsheet formula injection (prompt §8.4). */
export function csvEscape(field: string): string {
  let f = field;
  if (/^[=+\-@\t\r]/.test(f)) f = `'${f}`;
  if (/[",\n]/.test(f)) f = `"${f.replace(/"/g, '""')}"`;
  return f;
}

export interface ResultRow {
  submission_id: number;
  label: string;
  filename: string;
  status: string;
  run_id: number | null;
  run_state: string | null;
  overall_status: string;
  grade: number | null;
  tests_passed: number | null;
  tests_total: number | null;
  compile_ok: boolean | null;
  flags: string[];
}

export function resultsToCsv(rows: ResultRow[]): string {
  const header = [
    "label", "filename", "submission_status", "run_state", "overall_status",
    "grade", "tests_passed", "tests_total", "compile_ok", "flags",
  ];
  const lines = rows.map((r) =>
    [
      r.label, r.filename, r.status, r.run_state ?? "", r.overall_status,
      r.grade === null ? "" : String(r.grade),
      r.tests_passed === null ? "" : String(r.tests_passed),
      r.tests_total === null ? "" : String(r.tests_total),
      r.compile_ok === null ? "" : String(r.compile_ok),
      r.flags.join(";"),
    ]
      .map(csvEscape)
      .join(",")
  );
  return [header.join(","), ...lines].join("\n");
}

export function filterResults(
  rows: ResultRow[],
  query: string,
  status: string
): ResultRow[] {
  const q = query.trim().toLowerCase();
  return rows.filter((r) => {
    if (status !== "all" && r.overall_status !== status && r.status !== status)
      return false;
    if (!q) return true;
    return (
      r.label.toLowerCase().includes(q) ||
      r.filename.toLowerCase().includes(q) ||
      r.flags.some((f) => f.toLowerCase().includes(q))
    );
  });
}

export function sortByGrade(rows: ResultRow[], dir: 1 | -1): ResultRow[] {
  return [...rows].sort((a, b) => {
    const ga = a.grade === null ? -Infinity : a.grade;
    const gb = b.grade === null ? -Infinity : b.grade;
    return (ga - gb) * dir;
  });
}

export interface UploadProblem {
  file: string;
  problem: string;
}

export function validateUploadFiles(
  files: { name: string; size: number }[]
): UploadProblem[] {
  const problems: UploadProblem[] = [];
  const seen = new Set<string>();
  for (const f of files) {
    if (!f.name.toLowerCase().endsWith(".c"))
      problems.push({ file: f.name, problem: "not a .c file" });
    if (f.size > 1_000_000)
      problems.push({ file: f.name, problem: "exceeds the 1 MB limit" });
    if (f.size === 0) problems.push({ file: f.name, problem: "empty file" });
    if (seen.has(f.name))
      problems.push({ file: f.name, problem: "duplicate filename in selection" });
    seen.add(f.name);
  }
  return problems;
}

/** Test-case display state for the suite preview (prompt §5.1). */
export function testState(t: { trust_status: string }): string {
  switch (t.trust_status) {
    case "trusted":
      return "validated";
    case "untrusted":
      return "requires_review";
    case "rejected":
      return "rejected";
    default:
      return "candidate";
  }
}
