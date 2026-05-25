import type {
  BriefingReport,
  ClusterSummary,
  ColumnInference,
  CompoundDesignIdeas,
  DecisionLogRecord,
  DesignFeedbackRecord,
  DesignProposalReport,
  DesignSpace,
  MoleculeRecord,
  NextRoundDesign,
  PortfolioInsights,
  ProjectRecord,
  ReportPlaceholder,
  SarSummary,
  SarWorkbench,
  UploadResponse,
} from "../types/molecule";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
const API_BASE_URL_CANDIDATES = [
  configuredApiBaseUrl,
  "http://localhost:8000",
  "http://127.0.0.1:8000",
  "http://localhost:8001",
  "http://127.0.0.1:8001",
].filter((url, index, urls): url is string => Boolean(url) && urls.indexOf(url) === index);

let activeApiBaseUrl = API_BASE_URL_CANDIDATES[0] ?? "http://localhost:8000";

async function fetchApi(path: string, initFactory?: () => RequestInit): Promise<Response> {
  const bases = [activeApiBaseUrl, ...API_BASE_URL_CANDIDATES.filter((url) => url !== activeApiBaseUrl)];
  let lastError: unknown;

  for (const baseUrl of bases) {
    try {
      const response = await fetch(`${baseUrl}${path}`, initFactory?.());
      if (response.status === 404 && baseUrl !== bases[bases.length - 1]) {
        lastError = new Error("API route not found on this backend");
        continue;
      }
      activeApiBaseUrl = baseUrl;
      return response;
    } catch (err) {
      lastError = err;
    }
  }

  throw lastError instanceof Error ? lastError : new Error("Could not reach the API server");
}

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(formatApiError(payload.detail) ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

function formatApiError(detail: unknown): string | null {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const record = item as { loc?: unknown[]; msg?: unknown };
          const location = Array.isArray(record.loc) ? record.loc.filter((part) => part !== "body").join(".") : "";
          const message = typeof record.msg === "string" ? record.msg : JSON.stringify(item);
          return location ? `${location}: ${message}` : message;
        }
        return String(item);
      })
      .join("; ");
  }
  if (typeof detail === "object") return JSON.stringify(detail);
  return String(detail);
}

export async function uploadCompoundFile(file: File): Promise<UploadResponse> {
  const response = await fetchApi("/api/uploads/csv-sdf", () => {
    const formData = new FormData();
    formData.append("file", file);
    return {
      method: "POST",
      body: formData,
    };
  });
  return parseJson<UploadResponse>(response);
}

export async function createProject(params: { name: string; description?: string }): Promise<ProjectRecord> {
  const response = await fetchApi("/api/projects", () => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  }));
  return parseJson<ProjectRecord>(response);
}

export async function uploadProjectCompoundFile(projectId: string, file: File): Promise<UploadResponse> {
  const response = await fetchApi(`/api/projects/${encodeURIComponent(projectId)}/uploads`, () => {
    const formData = new FormData();
    formData.append("file", file);
    return {
      method: "POST",
      body: formData,
    };
  });
  return parseJson<UploadResponse>(response);
}

export async function fetchMolecules(uploadId?: string): Promise<MoleculeRecord[]> {
  const query = uploadId ? `?upload_id=${encodeURIComponent(uploadId)}` : "";
  const response = await fetchApi(`/api/molecules${query}`);
  return parseJson<MoleculeRecord[]>(response);
}

export async function fetchProjectMolecules(projectId: string): Promise<MoleculeRecord[]> {
  const response = await fetchApi(`/api/projects/${encodeURIComponent(projectId)}/molecules`);
  return parseJson<MoleculeRecord[]>(response);
}

export async function fetchProjectTimeline(projectId: string): Promise<DecisionLogRecord[]> {
  const response = await fetchApi(`/api/projects/${encodeURIComponent(projectId)}/timeline`);
  return parseJson<DecisionLogRecord[]>(response);
}

export async function createDecisionLog(
  projectId: string,
  params: { entryType?: string; title: string; body?: Record<string, unknown> },
): Promise<DecisionLogRecord> {
  const response = await fetchApi(`/api/projects/${encodeURIComponent(projectId)}/decision-log`, () => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      entry_type: params.entryType ?? "decision",
      title: params.title,
      body: params.body ?? {},
    }),
  }));
  return parseJson<DecisionLogRecord>(response);
}

export async function fetchDesignFeedback(projectId: string): Promise<DesignFeedbackRecord[]> {
  const response = await fetchApi(`/api/projects/${encodeURIComponent(projectId)}/design-feedback`);
  return parseJson<DesignFeedbackRecord[]>(response);
}

export async function submitDesignFeedback(
  projectId: string,
  params: {
    smiles: string;
    feedback: "like" | "dislike";
    reason?: string;
    design: Record<string, unknown>;
  },
): Promise<DesignFeedbackRecord> {
  const response = await fetchApi(`/api/projects/${encodeURIComponent(projectId)}/design-feedback`, () => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  }));
  return parseJson<DesignFeedbackRecord>(response);
}

export async function inferAssayColumns(params: { uploadId?: string; projectId?: string }): Promise<ColumnInference> {
  const query = params.projectId
    ? `?project_id=${encodeURIComponent(params.projectId)}`
    : params.uploadId
      ? `?upload_id=${encodeURIComponent(params.uploadId)}`
      : "";
  const response = await fetchApi(`/api/assays/columns${query}`);
  return parseJson<ColumnInference>(response);
}

export async function calculateClusters(uploadId?: string): Promise<ClusterSummary[]> {
  const query = uploadId ? `?upload_id=${encodeURIComponent(uploadId)}` : "";
  const response = await fetchApi(`/api/clusters${query}`, () => ({ method: "POST" }));
  return parseJson<ClusterSummary[]>(response);
}

export async function fetchPortfolioInsights(uploadId?: string): Promise<PortfolioInsights> {
  const query = uploadId ? `?upload_id=${encodeURIComponent(uploadId)}` : "";
  const response = await fetchApi(`/api/insights/portfolio${query}`);
  return parseJson<PortfolioInsights>(response);
}

export async function fetchCompoundDesignIdeas(moleculeId: number): Promise<CompoundDesignIdeas> {
  const response = await fetchApi(`/api/molecules/${moleculeId}/design-ideas`);
  return parseJson<CompoundDesignIdeas>(response);
}

export async function generateDesignSpace(params: {
  uploadId: string;
  targetCount: number;
  clusterCount?: number;
}): Promise<DesignSpace> {
  const payload: { upload_id: string; target_count: number; cluster_count?: number } = {
    upload_id: params.uploadId,
    target_count: Math.max(1000, Math.min(15000, Math.round(params.targetCount || 12000))),
  };
  if (params.clusterCount !== undefined) {
    payload.cluster_count = params.clusterCount;
  }

  const response = await fetchApi("/api/design/space", () => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
  return parseJson<DesignSpace>(response);
}

export async function generateNextRoundDesign(params: {
  uploadId?: string;
  projectId?: string;
  potencyColumn?: string;
  admetColumns?: string[];
  count?: number;
  objectives?: Record<string, unknown>;
  constraints?: Record<string, unknown>;
}): Promise<NextRoundDesign> {
  const response = await fetchApi("/api/design/next-round", () => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: params.projectId,
      upload_id: params.uploadId,
      potency_column: params.potencyColumn || null,
      admet_columns: params.admetColumns ?? [],
      count: params.count ?? 24,
      objectives: params.objectives ?? {},
      constraints: params.constraints ?? {},
    }),
  }));
  return parseJson<NextRoundDesign>(response);
}

export async function fetchReportPlaceholder(): Promise<ReportPlaceholder> {
  const response = await fetchApi("/api/reports/placeholder");
  return parseJson<ReportPlaceholder>(response);
}

export async function summarizeSar(params: {
  uploadId: string;
  potencyColumn: string;
  admetColumns: string[];
  minFoldChange: number;
}): Promise<SarSummary> {
  const response = await fetchApi("/api/sar/summary", () => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      upload_id: params.uploadId,
      potency_column: params.potencyColumn,
      admet_columns: params.admetColumns,
      min_fold_change: params.minFoldChange,
    }),
  }));
  return parseJson<SarSummary>(response);
}

export async function generateSarWorkbench(params: {
  uploadId?: string;
  projectId?: string;
  potencyColumn: string;
  potencyDirection?: string;
  admetColumns: string[];
  minFoldChange: number;
}): Promise<SarWorkbench> {
  const response = await fetchApi("/api/sar/workbench", () => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: params.projectId,
      upload_id: params.uploadId,
      potency_column: params.potencyColumn,
      potency_direction: params.potencyDirection ?? "lower_is_better",
      admet_columns: params.admetColumns,
      min_fold_change: params.minFoldChange,
    }),
  }));
  return parseJson<SarWorkbench>(response);
}

export async function generateBriefingReport(params: {
  uploadId: string;
  projectName: string;
  potencyColumn?: string;
  admetColumns: string[];
  minFoldChange: number;
}): Promise<BriefingReport> {
  const response = await fetchApi("/api/reports/briefing", () => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(reportPayload(params)),
  }));
  return parseJson<BriefingReport>(response);
}

export async function exportBriefingReport(
  params: {
    uploadId: string;
    projectName: string;
    potencyColumn?: string;
    admetColumns: string[];
    minFoldChange: number;
  },
  format: "markdown" | "docx",
): Promise<void> {
  const response = await fetchApi(`/api/reports/briefing/export?format=${format}`, () => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(reportPayload(params)),
  }));
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(formatApiError(payload.detail) ?? "Report export failed");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = format === "docx" ? "medchem_briefing.docx" : "medchem_briefing.md";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function generateDesignProposalReport(params: {
  uploadId?: string;
  projectId?: string;
  projectName: string;
  potencyColumn?: string;
  admetColumns: string[];
  minFoldChange: number;
  count: number;
}): Promise<DesignProposalReport> {
  const response = await fetchApi("/api/reports/design-proposal", () => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(designProposalPayload(params)),
  }));
  return parseJson<DesignProposalReport>(response);
}

export async function exportDesignProposalReport(
  params: {
    uploadId?: string;
    projectId?: string;
    projectName: string;
    potencyColumn?: string;
    admetColumns: string[];
    minFoldChange: number;
    count: number;
  },
  format: "markdown" | "docx",
): Promise<void> {
  const response = await fetchApi(`/api/reports/design-proposal/export?format=${format}`, () => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(designProposalPayload(params)),
  }));
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(formatApiError(payload.detail) ?? "Design proposal export failed");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = format === "docx" ? "medchem_design_proposal.docx" : "medchem_design_proposal.md";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function reportPayload(params: {
  uploadId: string;
  projectName: string;
  potencyColumn?: string;
  admetColumns: string[];
  minFoldChange: number;
}) {
  return {
    upload_id: params.uploadId,
    project_name: params.projectName,
    potency_column: params.potencyColumn || null,
    admet_columns: params.admetColumns,
    min_fold_change: params.minFoldChange,
  };
}

function designProposalPayload(params: {
  uploadId?: string;
  projectId?: string;
  projectName: string;
  potencyColumn?: string;
  admetColumns: string[];
  minFoldChange: number;
  count: number;
}) {
  return {
    project_id: params.projectId ?? null,
    upload_id: params.projectId ? null : params.uploadId,
    project_name: params.projectName,
    potency_column: params.potencyColumn || null,
    admet_columns: params.admetColumns,
    min_fold_change: params.minFoldChange,
    count: params.count,
    objectives: {
      improve_potency: true,
      reduce_logp: true,
      improve_solubility: true,
      improve_microsomal_stability: params.admetColumns.some((column) => /clint|clearance|hlm|mlm/i.test(column)),
    },
    constraints: {
      max_mw: 560,
      max_logp: 5.5,
      max_tpsa: 150,
      prefer_one_step_from_existing: true,
    },
  };
}

export function structureUrl(moleculeId: number): string {
  return `${activeApiBaseUrl}/api/molecules/${moleculeId}/structure.svg`;
}

export function analogStructureUrl(smiles: string): string {
  return `${activeApiBaseUrl}/api/structures/render.svg?smiles=${encodeURIComponent(smiles)}`;
}

export async function exportCompounds(moleculeIds: number[], format: "csv" | "sdf"): Promise<void> {
  const response = await fetchApi("/api/exports/compounds", () => ({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ molecule_ids: moleculeIds, format }),
  }));
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(formatApiError(payload.detail) ?? "Export failed");
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `selected_compounds.${format}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
