import type {
  BriefingReport,
  ClusterSummary,
  CompoundDesignIdeas,
  MoleculeRecord,
  PortfolioInsights,
  ReportPlaceholder,
  SarSummary,
  UploadResponse,
} from "../types/molecule";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

export async function uploadCompoundFile(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/uploads/csv-sdf`, {
    method: "POST",
    body: formData,
  });
  return parseJson<UploadResponse>(response);
}

export async function fetchMolecules(uploadId?: string): Promise<MoleculeRecord[]> {
  const query = uploadId ? `?upload_id=${encodeURIComponent(uploadId)}` : "";
  const response = await fetch(`${API_BASE_URL}/api/molecules${query}`);
  return parseJson<MoleculeRecord[]>(response);
}

export async function calculateClusters(uploadId?: string): Promise<ClusterSummary[]> {
  const query = uploadId ? `?upload_id=${encodeURIComponent(uploadId)}` : "";
  const response = await fetch(`${API_BASE_URL}/api/clusters${query}`, { method: "POST" });
  return parseJson<ClusterSummary[]>(response);
}

export async function fetchPortfolioInsights(uploadId?: string): Promise<PortfolioInsights> {
  const query = uploadId ? `?upload_id=${encodeURIComponent(uploadId)}` : "";
  const response = await fetch(`${API_BASE_URL}/api/insights/portfolio${query}`);
  return parseJson<PortfolioInsights>(response);
}

export async function fetchCompoundDesignIdeas(moleculeId: number): Promise<CompoundDesignIdeas> {
  const response = await fetch(`${API_BASE_URL}/api/molecules/${moleculeId}/design-ideas`);
  return parseJson<CompoundDesignIdeas>(response);
}

export async function fetchReportPlaceholder(): Promise<ReportPlaceholder> {
  const response = await fetch(`${API_BASE_URL}/api/reports/placeholder`);
  return parseJson<ReportPlaceholder>(response);
}

export async function summarizeSar(params: {
  uploadId: string;
  potencyColumn: string;
  admetColumns: string[];
  minFoldChange: number;
}): Promise<SarSummary> {
  const response = await fetch(`${API_BASE_URL}/api/sar/summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      upload_id: params.uploadId,
      potency_column: params.potencyColumn,
      admet_columns: params.admetColumns,
      min_fold_change: params.minFoldChange,
    }),
  });
  return parseJson<SarSummary>(response);
}

export async function generateBriefingReport(params: {
  uploadId: string;
  projectName: string;
  potencyColumn?: string;
  admetColumns: string[];
  minFoldChange: number;
}): Promise<BriefingReport> {
  const response = await fetch(`${API_BASE_URL}/api/reports/briefing`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(reportPayload(params)),
  });
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
  const response = await fetch(`${API_BASE_URL}/api/reports/briefing/export?format=${format}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(reportPayload(params)),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? "Report export failed");
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

export function structureUrl(moleculeId: number): string {
  return `${API_BASE_URL}/api/molecules/${moleculeId}/structure.svg`;
}

export function analogStructureUrl(smiles: string): string {
  return `${API_BASE_URL}/api/structures/render.svg?smiles=${encodeURIComponent(smiles)}`;
}

export async function exportCompounds(moleculeIds: number[], format: "csv" | "sdf"): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/exports/compounds`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ molecule_ids: moleculeIds, format }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? "Export failed");
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
