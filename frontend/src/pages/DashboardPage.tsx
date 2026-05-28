import { Activity, ArrowRight, Boxes, ClipboardList, Database, FileText, FlaskConical, Network, ShoppingCart, Table2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { fetchCommercialCatalogs, fetchProjectTimeline, inferAssayColumns } from "../api/client";
import type { CommercialCatalog, ColumnInference, DecisionLogRecord, MoleculeRecord } from "../types/molecule";

interface DashboardPageProps {
  uploadId?: string;
  projectId?: string;
  projectName?: string;
  molecules: MoleculeRecord[];
  onNavigate: (tab: "upload" | "molecules" | "sar" | "design" | "report") => void;
}

export function DashboardPage({ uploadId, projectId, projectName, molecules, onNavigate }: DashboardPageProps) {
  const [columns, setColumns] = useState<ColumnInference | null>(null);
  const [timeline, setTimeline] = useState<DecisionLogRecord[]>([]);
  const [catalogs, setCatalogs] = useState<CommercialCatalog[]>([]);

  useEffect(() => {
    const scope = projectId ? { projectId } : uploadId ? { uploadId } : null;
    if (!scope) return;
    inferAssayColumns(scope).then(setColumns).catch(() => undefined);
  }, [projectId, uploadId]);

  useEffect(() => {
    fetchCommercialCatalogs().then(setCatalogs).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!projectId) return;
    fetchProjectTimeline(projectId).then(setTimeline).catch(() => undefined);
  }, [projectId]);

  const stats = useMemo(() => buildStats(molecules), [molecules]);
  const enamineCatalog = catalogs.find((catalog) => catalog.source_type === "enamine_real" || /enamine|real/i.test(catalog.filename));

  return (
    <section className="page-section dashboard-page">
      <div className="section-heading with-actions dashboard-heading">
        <div>
          <p className="eyebrow">Project dashboard</p>
          <h2>{projectName ?? "Drug discovery workspace"}</h2>
        </div>
        <button className="primary-button" onClick={() => onNavigate(uploadId ? "design" : "upload")}>
          {uploadId ? <Network size={16} /> : <Database size={16} />}
          {uploadId ? "Open design" : "Upload data"}
        </button>
      </div>

      <div className="dashboard-kpis">
        <KpiCard icon={<FlaskConical size={20} />} label="Compounds" value={molecules.length.toLocaleString()} note={uploadId ? "Loaded in active project" : "No active upload"} />
        <KpiCard icon={<Table2 size={20} />} label="Potency endpoint" value={columns?.recommended_potency_column ?? "-"} note={`${columns?.recommended_admet_columns.length ?? 0} ADMET columns detected`} />
        <KpiCard icon={<Boxes size={20} />} label="Series" value={stats.clusterCount ? stats.clusterCount.toString() : "-"} note={stats.namedCount ? `${stats.namedCount} named compounds` : "Cluster after upload"} />
        <KpiCard icon={<ShoppingCart size={20} />} label="Enamine REAL" value={enamineCatalog ? enamineCatalog.compound_count.toLocaleString() : "-"} note={enamineCatalog?.filename ?? "Upload REAL catalog for buyable analogs"} />
      </div>

      <div className="dashboard-grid">
        <div className="workflow-panel">
          <div className="panel-title">
            <ClipboardList size={18} />
            <strong>Discovery workflow</strong>
          </div>
          <WorkflowAction icon={<Database size={18} />} title="Ingest and normalize compounds" detail="CSV, SDF, patent PDFs, commercial catalogs" enabled onClick={() => onNavigate("upload")} />
          <WorkflowAction icon={<FlaskConical size={18} />} title="Review compound table" detail="Structures, descriptors, clusters, exports" enabled={Boolean(uploadId)} onClick={() => onNavigate("molecules")} />
          <WorkflowAction icon={<Table2 size={18} />} title="Analyze SAR" detail="Endpoint inference, R-group tables, matched evidence" enabled={Boolean(uploadId || projectId)} onClick={() => onNavigate("sar")} />
          <WorkflowAction icon={<Network size={18} />} title="Design next round" detail="MPO, predictions, route, Enamine REAL analogs" enabled={Boolean(uploadId || projectId)} onClick={() => onNavigate("design")} />
          <WorkflowAction icon={<FileText size={18} />} title="Generate project report" detail="Briefing, design proposal, decision context" enabled={Boolean(uploadId || projectId)} onClick={() => onNavigate("report")} />
        </div>

        <div className="readiness-panel">
          <div className="panel-title">
            <Activity size={18} />
            <strong>Readiness checks</strong>
          </div>
          <ReadinessRow label="Compound structures" state={molecules.length > 0 ? "ready" : "missing"} detail={molecules.length ? `${molecules.length} valid structures` : "Upload project compounds"} />
          <ReadinessRow label="Potency column" state={columns?.recommended_potency_column ? "ready" : "missing"} detail={columns?.recommended_potency_column ?? "No endpoint inferred yet"} />
          <ReadinessRow label="ADMET context" state={(columns?.recommended_admet_columns.length ?? 0) > 0 ? "ready" : "optional"} detail={columns?.recommended_admet_columns.slice(0, 3).join(", ") || "Optional but useful for MPO"} />
          <ReadinessRow label="Commercial analog source" state={enamineCatalog ? "ready" : "missing"} detail={enamineCatalog ? enamineCatalog.filename : "Upload Enamine REAL CXSMILES"} />
          <ReadinessRow label="Decision history" state={timeline.length > 0 ? "ready" : "optional"} detail={timeline.length ? `${timeline.length} timeline entries` : "Captured as chemists give feedback"} />
        </div>

        <div className="timeline-panel">
          <div className="panel-title">
            <ClipboardList size={18} />
            <strong>Recent decisions</strong>
          </div>
          {timeline.length ? (
            timeline.slice(0, 5).map((entry) => (
              <div className="timeline-item" key={entry.id}>
                <span>{entry.entry_type.replace("_", " ")}</span>
                <strong>{entry.title}</strong>
                <small>{entry.created_at}</small>
              </div>
            ))
          ) : (
            <div className="dashboard-empty-state">Design feedback, report generation, and make/buy decisions will appear here.</div>
          )}
        </div>
      </div>
    </section>
  );
}

function KpiCard({ icon, label, value, note }: { icon: ReactNode; label: string; value: string; note: string }) {
  return (
    <div className="dashboard-kpi">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function WorkflowAction({ icon, title, detail, enabled, onClick }: { icon: ReactNode; title: string; detail: string; enabled: boolean; onClick: () => void }) {
  return (
    <button className="workflow-action" disabled={!enabled} onClick={onClick}>
      {icon}
      <span>
        <strong>{title}</strong>
        <small>{detail}</small>
      </span>
      <ArrowRight size={16} />
    </button>
  );
}

function ReadinessRow({ label, state, detail }: { label: string; state: "ready" | "missing" | "optional"; detail: string }) {
  return (
    <div className={`readiness-row readiness-${state}`}>
      <span>{state}</span>
      <div>
        <strong>{label}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function buildStats(molecules: MoleculeRecord[]) {
  return {
    clusterCount: new Set(molecules.map((molecule) => molecule.cluster_id).filter((clusterId) => clusterId !== null)).size,
    namedCount: molecules.filter((molecule) => molecule.name).length,
  };
}
