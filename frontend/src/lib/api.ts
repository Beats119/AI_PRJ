/** Thin typed client for the AutoGrader /api. */

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    let detail: unknown = resp.statusText;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail)
    );
  }
  return (await resp.json()) as T;
}

const post = <T>(path: string, body?: unknown) =>
  req<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });

export interface VersionSummary {
  id: number;
  version_no: number;
  status: string;
  trusted_tests: number;
}

export interface AssignmentSummary {
  id: number;
  name: string;
  versions: VersionSummary[];
}

export interface TestCaseDto {
  test_id: string;
  input_data: string;
  expected_output: string | null;
  category: string;
  trust_status: string;
  provenance: string;
  validation_method: string;
}

export interface VersionDetail {
  id: number;
  assignment_id: number;
  version_no: number;
  status: string;
  rules_hash: string;
  rules: Record<string, unknown>;
  spec: Record<string, unknown>;
  suite: TestCaseDto[];
  sufficiency: { sufficient?: boolean; conditions?: { name: string; passed: boolean; detail: string }[]; total_trusted?: number };
  unresolved: string[];
}

export interface BatchDto {
  id: number;
  version_id: number;
  status: string;
  submissions: import("./logic").ResultRow[];
}

export interface RunDetail {
  id: number;
  submission_id: number;
  state: string;
  overall_status: string;
  grade: number | null;
  error: string;
  retry_of_run_id: number | null;
  report: Record<string, any> | null;
  evidence: { kind: string; payload: Record<string, any> }[];
  breakdown: {
    name: string;
    configured_weight: string;
    effective_weight: string | null;
    score: string | null;
    contribution: string | null;
    status: string;
    note: string;
  }[];
}

export interface Finding {
  id: number;
  batch_id: number;
  a: { id: number; label: string; filename: string };
  b: { id: number; label: string; filename: string };
  score: number;
  method: string;
  review_status: string;
  disposition_note: string;
}

export const api = {
  health: () => req<{ status: string }>("/api/health"),
  dependencies: () => req<Record<string, any>>("/api/health/dependencies"),
  modelStatus: () => req<Record<string, any>>("/api/settings/model-status"),
  assignments: () => req<AssignmentSummary[]>("/api/assignments"),
  assignment: (id: number) =>
    req<{ id: number; name: string; versions: VersionDetail[] }>(
      `/api/assignments/${id}`
    ),
  createAssignment: (name: string) =>
    post<{ id: number; name: string }>("/api/assignments", { name }),
  createVersion: (assignmentId: number, payload: Record<string, unknown>) =>
    post<VersionDetail>(`/api/assignments/${assignmentId}/versions`, payload),
  activate: (assignmentId: number, versionId: number) =>
    post<VersionDetail>(
      `/api/assignments/${assignmentId}/versions/${versionId}/activate`
    ),
  validateRules: (rules: Record<string, unknown>) =>
    post<{ valid: boolean; problems: string[]; rules_hash?: string }>(
      "/api/assignments/validate-rules",
      { rules }
    ),
  example: () =>
    req<Record<string, unknown>>("/api/examples/add-two-integers"),
  batches: () =>
    req<{ id: number; version_id: number; status: string; submissions: number }[]>(
      "/api/batches"
    ),
  batch: (id: number) => req<BatchDto>(`/api/batches/${id}`),
  createBatch: async (versionId: number, files: File[]): Promise<BatchDto> => {
    const form = new FormData();
    form.append("version_id", String(versionId));
    for (const f of files) form.append("files", f);
    const resp = await fetch("/api/batches", { method: "POST", body: form });
    if (!resp.ok) throw new Error((await resp.json()).detail?.message ?? "upload failed");
    return (await resp.json()) as BatchDto;
  },
  evaluateBatch: (id: number, backend?: string) =>
    post<BatchDto>(`/api/batches/${id}/evaluate`, {
      sandbox_backend: backend ?? null,
    }),
  runs: () =>
    req<
      {
        id: number; submission_id: number; state: string;
        overall_status: string; grade: number | null;
        retry_of_run_id: number | null;
      }[]
    >("/api/evaluations"),
  run: (id: number) => req<RunDetail>(`/api/evaluations/${id}`),
  retryRun: (id: number) => post<RunDetail>(`/api/evaluations/${id}/retry`),
  cancelRun: (id: number) =>
    post<{ id: number; state: string }>(`/api/evaluations/${id}/cancel`),
  submission: (id: number) =>
    req<{ id: number; label: string; filename: string; source: string; status: string }>(
      `/api/submissions/${id}`
    ),
  similarity: (batchId?: number) =>
    req<Finding[]>(
      batchId ? `/api/similarity?batch_id=${batchId}` : "/api/similarity"
    ),
  disposition: (id: number, status: string, note: string) =>
    post<{ id: number; review_status: string }>(
      `/api/similarity/${id}/disposition`,
      { status, note }
    ),
};
