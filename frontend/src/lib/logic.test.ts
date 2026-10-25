import { describe, expect, it } from "vitest";
import {
  csvEscape, filterResults, fmt, resultsToCsv, sortByGrade,
  testState, validateUploadFiles, type ResultRow,
} from "./logic";

const row = (patch: Partial<ResultRow>): ResultRow => ({
  submission_id: 1, label: "Asha", filename: "asha.c", status: "stored",
  run_id: 1, run_state: "completed", overall_status: "complete",
  grade: 90, tests_passed: 20, tests_total: 24, compile_ok: true,
  flags: [], ...patch,
});

describe("fmt", () => {
  it("never shows raw long decimals (the v1 UI bug)", () => {
    expect(fmt(0.7916666666666666)).toBe("0.79");
    expect(fmt("75.20000000000002")).toBe("75.2");
    expect(fmt(100)).toBe("100");
    expect(fmt(null)).toBe("—");
  });
});

describe("CSV export safety", () => {
  it("neutralizes formula-leading cells", () => {
    expect(csvEscape("=2+2")).toBe("'=2+2");
    expect(csvEscape("+cmd")).toBe("'+cmd");
    expect(csvEscape("@SUM(A1)")).toBe("'@SUM(A1)");
    expect(csvEscape("normal")).toBe("normal");
    expect(csvEscape('a,"b"')).toBe('"a,""b"""');
  });
  it("exports rows with headers", () => {
    const csv = resultsToCsv([row({ label: "=HYPERLINK(x)" })]);
    expect(csv.split("\n")[0]).toContain("label,filename");
    expect(csv).toContain("'=HYPERLINK(x)");
  });
});

describe("filtering and sorting", () => {
  const rows = [
    row({ label: "Asha", filename: "asha.c", grade: 90 }),
    row({ label: "Bala", filename: "bala.c", grade: 40, overall_status: "partial", flags: ["suspected_infinite_loop"] }),
    row({ label: "Cyrus", filename: "cyrus.c", grade: null, overall_status: "incomplete" }),
  ];
  it("filters by query across label and flags", () => {
    expect(filterResults(rows, "infinite", "all")).toHaveLength(1);
    expect(filterResults(rows, "ash", "all")).toHaveLength(1);
  });
  it("filters by status", () => {
    expect(filterResults(rows, "", "partial")).toHaveLength(1);
  });
  it("sorts with ungraded rows last when descending", () => {
    const sorted = sortByGrade(rows, -1);
    expect(sorted[0].label).toBe("Asha");
    expect(sorted[2].grade).toBeNull();
  });
});

describe("upload validation", () => {
  it("rejects non-C, oversize, empty and duplicate names", () => {
    const problems = validateUploadFiles([
      { name: "a.py", size: 10 },
      { name: "b.c", size: 2_000_000 },
      { name: "c.c", size: 0 },
      { name: "d.c", size: 5 },
      { name: "d.c", size: 6 },
    ]);
    expect(problems.map((p) => p.problem)).toEqual([
      "not a .c file", "exceeds the 1 MB limit", "empty file",
      "duplicate filename in selection",
    ]);
  });
});

describe("test states (prompt §5.1 vocabulary)", () => {
  it("maps trust to display states", () => {
    expect(testState({ trust_status: "trusted" })).toBe("validated");
    expect(testState({ trust_status: "untrusted" })).toBe("requires_review");
    expect(testState({ trust_status: "rejected" })).toBe("rejected");
  });
});
