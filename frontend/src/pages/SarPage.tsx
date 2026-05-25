import { Activity, FlaskConical, Loader2, Table2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { analogStructureUrl, generateSarWorkbench, inferAssayColumns, structureUrl } from "../api/client";
import type { ColumnInference, SarHeatmapCell, SarRGroupTable, SarWorkbench } from "../types/molecule";

interface SarPageProps {
  uploadId?: string;
  projectId?: string;
}

export function SarPage({ uploadId, projectId }: SarPageProps) {
  const [columns, setColumns] = useState<ColumnInference | null>(null);
  const [workbench, setWorkbench] = useState<SarWorkbench | null>(null);
  const [potencyColumn, setPotencyColumn] = useState("");
  const [admetColumns, setAdmetColumns] = useState("");
  const [minFoldChange, setMinFoldChange] = useState(3);
  const [isLoadingColumns, setIsLoadingColumns] = useState(false);
  const [isBuilding, setIsBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const scope = projectId ? { projectId } : uploadId ? { uploadId } : null;
    if (!scope) return;
    setIsLoadingColumns(true);
    setError(null);
    inferAssayColumns(scope)
      .then((response) => {
        setColumns(response);
        setPotencyColumn(response.recommended_potency_column ?? "");
        setAdmetColumns(response.recommended_admet_columns.join(", "));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not infer assay columns"))
      .finally(() => setIsLoadingColumns(false));
  }, [projectId, uploadId]);

  async function handleBuildWorkbench() {
    if (!potencyColumn) return;
    setIsBuilding(true);
    setError(null);
    try {
      setWorkbench(
        await generateSarWorkbench({
          projectId,
          uploadId: projectId ? undefined : uploadId,
          potencyColumn,
          admetColumns: splitColumns(admetColumns),
          minFoldChange,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build SAR workbench");
    } finally {
      setIsBuilding(false);
    }
  }

  const topTable = workbench?.rgroup_tables[0] ?? null;

  return (
    <section className="page-section sar-workbench-page">
      <div className="section-heading with-actions">
        <div>
          <p className="eyebrow">SAR workbench</p>
          <h2>Project SAR analysis</h2>
        </div>
        <button className="primary-button" disabled={!potencyColumn || isBuilding} onClick={handleBuildWorkbench}>
          {isBuilding ? <Loader2 className="spin" size={16} /> : <Activity size={16} />}
          Build SAR
        </button>
      </div>

      {!uploadId && !projectId && <p className="status error">Upload compound data before opening the SAR workbench.</p>}
      {error && <p className="status error">{error}</p>}

      <div className="sar-setup-panel">
        <div className="sar-controls">
          <label>
            Potency column
            <input value={potencyColumn} onChange={(event) => setPotencyColumn(event.target.value)} placeholder="ic50_nm" />
          </label>
          <label>
            ADMET columns
            <input value={admetColumns} onChange={(event) => setAdmetColumns(event.target.value)} placeholder="clint, hERG" />
          </label>
          <label>
            Min fold change
            <input
              min="1.1"
              step="0.1"
              type="number"
              value={minFoldChange}
              onChange={(event) => setMinFoldChange(Number(event.target.value))}
            />
          </label>
        </div>
        <ColumnInferencePanel columns={columns} isLoading={isLoadingColumns} />
      </div>

      {workbench && (
        <div className="sar-workbench-grid">
          <div className="sar-workbench-main">
            <div className="workbench-metrics">
              <span>{workbench.summary.analyzable_compound_count} analyzable</span>
              <span>{workbench.summary.scaffold_count} scaffolds</span>
              <span>{workbench.summary.matched_pair_count} matched pairs</span>
              <span>{workbench.heatmap.length} heatmap cells</span>
            </div>
            <HypothesisPanel workbench={workbench} />
            {topTable && <RGroupTable table={topTable} />}
          </div>
          <div className="sar-workbench-side">
            <HeatmapPanel cells={workbench.heatmap} />
            <EvidencePanel workbench={workbench} />
          </div>
        </div>
      )}
    </section>
  );
}

function ColumnInferencePanel({ columns, isLoading }: { columns: ColumnInference | null; isLoading: boolean }) {
  if (isLoading) {
    return (
      <div className="column-inference-panel muted">
        <Loader2 className="spin" size={16} />
        Inferring assay columns
      </div>
    );
  }
  if (!columns) return null;
  return (
    <div className="column-inference-panel">
      <strong>{columns.compound_count} compounds scanned</strong>
      <div className="assay-chip-row">
        {columns.potency_columns.slice(0, 4).map((column) => (
          <span key={column.name}>{`${column.name} · ${Math.round(column.confidence * 100)}%`}</span>
        ))}
        {columns.admet_columns.slice(0, 6).map((column) => (
          <span key={column.name}>{`${column.name} · ${column.assay_type}`}</span>
        ))}
      </div>
    </div>
  );
}

function HypothesisPanel({ workbench }: { workbench: SarWorkbench }) {
  return (
    <div className="workbench-panel">
      <div className="workbench-panel-title">
        <FlaskConical size={18} />
        <h3>SAR hypotheses</h3>
      </div>
      <div className="hypothesis-list">
        {workbench.hypotheses.map((hypothesis, index) => (
          <article key={`${hypothesis.title}-${index}`}>
            <strong>{hypothesis.title}</strong>
            <p>{hypothesis.statement}</p>
            <span>{hypothesis.recommended_action}</span>
          </article>
        ))}
      </div>
    </div>
  );
}

function RGroupTable({ table }: { table: SarRGroupTable }) {
  const visibleRows = table.rows.slice(0, 18);
  return (
    <div className="workbench-panel rgroup-table-panel">
      <div className="workbench-panel-title">
        <Table2 size={18} />
        <h3>R-group table</h3>
      </div>
      <div className="scaffold-strip">
        <img src={analogStructureUrl(table.scaffold)} alt="Scaffold" />
        <span>{table.compound_count} compounds on the largest scaffold</span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Compound</th>
              <th>Structure</th>
              <th>Potency</th>
              {table.positions.map((position) => (
                <th key={position}>{position}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr key={row.compound_id}>
                <td>{row.name ?? row.compound_id}</td>
                <td>
                  <img className="mini-structure" src={structureUrl(row.compound_id)} alt={row.name ?? `Compound ${row.compound_id}`} />
                </td>
                <td>{formatNumber(row.potency)}</td>
                {table.positions.map((position) => (
                  <td key={`${row.compound_id}-${position}`}>
                    <code>{row.r_groups[position] ?? "H"}</code>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function HeatmapPanel({ cells }: { cells: SarHeatmapCell[] }) {
  const grouped = useMemo(() => {
    const byPosition = new Map<string, SarHeatmapCell[]>();
    cells.slice(0, 36).forEach((cell) => {
      byPosition.set(cell.position, [...(byPosition.get(cell.position) ?? []), cell]);
    });
    return Array.from(byPosition.entries());
  }, [cells]);

  return (
    <div className="workbench-panel heatmap-panel">
      <h3>Substitution heatmap</h3>
      {grouped.map(([position, positionCells]) => (
        <div className="heatmap-row" key={position}>
          <strong>{position}</strong>
          <div>
            {positionCells.slice(0, 8).map((cell) => (
              <span className="heatmap-cell" key={`${cell.position}-${cell.substitution}`}>
                <code>{cell.substitution}</code>
                <small>{formatNumber(cell.median_potency)}</small>
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function EvidencePanel({ workbench }: { workbench: SarWorkbench }) {
  return (
    <div className="workbench-panel evidence-mini-panel">
      <h3>Matched-pair evidence</h3>
      {workbench.summary.evidence_table.slice(0, 8).map((row) => (
        <div className="evidence-mini-row" key={`${row.weaker_compound_id}-${row.stronger_compound_id}`}>
          <strong>{row.position ?? "multi-site"}</strong>
          <span>{`${row.weaker_substitution} -> ${row.stronger_substitution}`}</span>
          <small>{row.fold_change.toFixed(1)}x</small>
        </div>
      ))}
    </div>
  );
}

function splitColumns(value: string) {
  return value
    .split(",")
    .map((column) => column.trim())
    .filter(Boolean);
}

function formatNumber(value: number) {
  if (Math.abs(value) >= 100) return value.toFixed(0);
  if (Math.abs(value) >= 10) return value.toFixed(1);
  return value.toFixed(2);
}
