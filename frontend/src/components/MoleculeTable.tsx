import { AlertTriangle, Beaker, Download, FlaskConical, Lightbulb, RefreshCw, Sparkles, Target, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  analogStructureUrl,
  calculateClusters,
  exportCompounds,
  fetchCompoundDesignIdeas,
  fetchMolecules,
  fetchPortfolioInsights,
  structureUrl,
} from "../api/client";
import type { AnalogProposal, CompoundDesignIdeas, DesignIdea, MoleculeRecord, PortfolioInsights, RecommendedCompound } from "../types/molecule";

interface MoleculeTableProps {
  uploadId?: string;
  molecules: MoleculeRecord[];
  onMoleculesChange: (molecules: MoleculeRecord[]) => void;
}

export function MoleculeTable({ uploadId, molecules, onMoleculesChange }: MoleculeTableProps) {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [insights, setInsights] = useState<PortfolioInsights | null>(null);
  const [isLoadingInsights, setIsLoadingInsights] = useState(false);
  const [activeMolecule, setActiveMolecule] = useState<MoleculeRecord | null>(null);
  const [designIdeas, setDesignIdeas] = useState<CompoundDesignIdeas | null>(null);
  const [isLoadingIdeas, setIsLoadingIdeas] = useState(false);

  useEffect(() => {
    if (!uploadId) return;
    fetchMolecules(uploadId).then(onMoleculesChange).catch((err) => setError(err.message));
  }, [onMoleculesChange, uploadId]);

  const allSelected = molecules.length > 0 && selectedIds.size === molecules.length;
  const selectedArray = useMemo(() => Array.from(selectedIds), [selectedIds]);
  const topLeadIds = useMemo(() => insights?.recommended_compounds.slice(0, 5).map((compound) => compound.id) ?? [], [insights]);

  useEffect(() => {
    if (!uploadId) {
      setInsights(null);
      return;
    }
    setIsLoadingInsights(true);
    fetchPortfolioInsights(uploadId)
      .then(setInsights)
      .catch((err) => setError(err.message))
      .finally(() => setIsLoadingInsights(false));
  }, [uploadId, molecules.length]);

  useEffect(() => {
    if (!activeMolecule || !molecules.some((molecule) => molecule.id === activeMolecule.id)) {
      setActiveMolecule(null);
      setDesignIdeas(null);
    }
  }, [activeMolecule, molecules]);

  function toggleAll() {
    setSelectedIds(allSelected ? new Set() : new Set(molecules.map((molecule) => molecule.id)));
  }

  function toggleOne(id: number) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function refreshClusters() {
    if (!uploadId) return;
    setIsBusy(true);
    setError(null);
    try {
      await calculateClusters(uploadId);
      onMoleculesChange(await fetchMolecules(uploadId));
      setInsights(await fetchPortfolioInsights(uploadId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not calculate clusters");
    } finally {
      setIsBusy(false);
    }
  }

  function selectTopLeads() {
    setSelectedIds(new Set(topLeadIds));
  }

  async function handleExport(format: "csv" | "sdf") {
    setError(null);
    try {
      await exportCompounds(selectedArray, format);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    }
  }

  async function openDesignIdeas(molecule: MoleculeRecord) {
    setActiveMolecule(molecule);
    setDesignIdeas(null);
    setIsLoadingIdeas(true);
    setError(null);
    try {
      setDesignIdeas(await fetchCompoundDesignIdeas(molecule.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate design ideas");
    } finally {
      setIsLoadingIdeas(false);
    }
  }

  return (
    <section className="page-section molecule-page">
      <div className="section-heading with-actions">
        <div>
          <p className="eyebrow">Compound review</p>
          <h2>Molecule table</h2>
        </div>
        <div className="actions-row">
          <button className="secondary-button" onClick={refreshClusters} disabled={!uploadId || isBusy}>
            <RefreshCw size={17} className={isBusy ? "spin" : ""} />
            Cluster
          </button>
          <button className="secondary-button" onClick={selectTopLeads} disabled={topLeadIds.length === 0}>
            <Target size={17} />
            Select leads
          </button>
          <button className="secondary-button" onClick={() => handleExport("csv")} disabled={selectedArray.length === 0}>
            <Download size={17} />
            CSV
          </button>
          <button className="secondary-button" onClick={() => handleExport("sdf")} disabled={selectedArray.length === 0}>
            <Download size={17} />
            SDF
          </button>
        </div>
      </div>

      {error && <p className="status error">{error}</p>}
      <PortfolioPanel insights={insights} isLoading={isLoadingInsights} />
      <DesignIdeasPanel
        molecule={activeMolecule}
        designIdeas={designIdeas}
        isLoading={isLoadingIdeas}
        onClose={() => {
          setActiveMolecule(null);
          setDesignIdeas(null);
        }}
      />

      <div className="table-shell">
        <table>
          <thead>
            <tr>
              <th>
                <input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Select all compounds" />
              </th>
              <th>Structure</th>
              <th>Compound</th>
              <th>SMILES</th>
              <th>MW</th>
              <th>LogP</th>
              <th>HBD</th>
              <th>HBA</th>
              <th>TPSA</th>
              <th>RotB</th>
              <th>Cluster</th>
            </tr>
          </thead>
          <tbody>
            {molecules.map((molecule) => (
              <tr
                className={activeMolecule?.id === molecule.id ? "active-row clickable-row" : "clickable-row"}
                key={molecule.id}
                onClick={() => openDesignIdeas(molecule)}
              >
                <td>
                  <input
                    type="checkbox"
                    checked={selectedIds.has(molecule.id)}
                    onClick={(event) => event.stopPropagation()}
                    onChange={() => toggleOne(molecule.id)}
                    aria-label={`Select molecule ${molecule.name ?? molecule.id}`}
                  />
                </td>
                <td>
                  <img className="structure-img" src={structureUrl(molecule.id)} alt={molecule.name ?? molecule.smiles} />
                </td>
                <td>
                  <strong>{molecule.name ?? `Compound ${molecule.id}`}</strong>
                  <span>{molecule.source_filename}</span>
                </td>
                <td className="smiles-cell">{molecule.smiles}</td>
                <td>{formatValue(molecule.mol_weight)}</td>
                <td>{formatValue(molecule.logp)}</td>
                <td>{molecule.hbd ?? "-"}</td>
                <td>{molecule.hba ?? "-"}</td>
                <td>{formatValue(molecule.tpsa)}</td>
                <td>{molecule.rotatable_bonds ?? "-"}</td>
                <td>{molecule.cluster_id ? <span className="cluster-pill">C{molecule.cluster_id}</span> : "-"}</td>
              </tr>
            ))}
            {molecules.length === 0 && (
              <tr>
                <td colSpan={11} className="empty-state">
                  Upload CSV, SDF, or patent PDF compounds to populate the table.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function DesignIdeasPanel({
  molecule,
  designIdeas,
  isLoading,
  onClose,
}: {
  molecule: MoleculeRecord | null;
  designIdeas: CompoundDesignIdeas | null;
  isLoading: boolean;
  onClose: () => void;
}) {
  if (!molecule) return null;

  return (
    <div className="design-panel">
      <div className="design-header">
        <div className="design-title">
          <img className="design-structure" src={structureUrl(molecule.id)} alt={molecule.name ?? molecule.smiles} />
          <div>
            <p className="eyebrow">Compound design</p>
            <h3>{molecule.name ?? `Compound ${molecule.id}`}</h3>
            <span>
              C{molecule.cluster_id ?? "-"} · MW {formatValue(molecule.mol_weight)} · LogP {formatValue(molecule.logp)}
            </span>
          </div>
        </div>
        <button className="icon-button" onClick={onClose} aria-label="Close design ideas">
          <X size={18} />
        </button>
      </div>

      {isLoading && (
        <div className="design-loading">
          <Sparkles size={18} className="spin" />
          Generating medicinal chemistry ideas...
        </div>
      )}

      {!isLoading && designIdeas && (
        <>
          <div className="design-context">
            <span>
              <Beaker size={14} />
              {designIdeas.potency_column
                ? `${designIdeas.potency_column}: ${designIdeas.potency_value ?? "missing"}`
                : "No potency endpoint"}
            </span>
            <span>
              <FlaskConical size={14} />
              {designIdeas.cluster_compound_count} in series
            </span>
            <span>
              <AlertTriangle size={14} />
              {designIdeas.detected_admet_columns.length
                ? designIdeas.detected_admet_columns.join(", ")
                : "No ADMET endpoint"}
            </span>
          </div>

          {designIdeas.analog_proposals.length > 0 ? (
            <div className="analog-grid">
              {designIdeas.analog_proposals.map((analog) => (
                <AnalogCard analog={analog} key={`${analog.title}-${analog.analog_smiles}`} />
              ))}
            </div>
          ) : (
            <div className="idea-grid">
              {designIdeas.ideas.map((idea) => (
                <IdeaCard idea={idea} key={idea.title} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function AnalogCard({ analog }: { analog: AnalogProposal }) {
  return (
    <article className={`analog-card priority-${analog.priority}`}>
      <div className="analog-card-header">
        <div>
          <strong>{analog.title}</strong>
          <span>{analog.property_goal}</span>
        </div>
        <small>{analog.source === "observed_series" ? "Observed" : "Proposed"}</small>
      </div>
      <img className="analog-structure" src={analogStructureUrl(analog.analog_smiles)} alt={analog.title} />
      <div className="smiles-chip">{analog.analog_smiles}</div>
      <DescriptorDeltas deltas={analog.descriptor_deltas} />
      <p>{analog.rationale}</p>
      <div className="expected-effect">{analog.synthetic_note}</div>
    </article>
  );
}

function DescriptorDeltas({ deltas }: { deltas: Record<string, number | null> }) {
  const rows = [
    ["MW", deltas.mol_weight],
    ["LogP", deltas.logp],
    ["TPSA", deltas.tpsa],
    ["RotB", deltas.rotatable_bonds],
  ] as const;

  return (
    <div className="delta-row">
      {rows.map(([label, value]) => (
        <span className={deltaClass(value)} key={label}>
          {label} {formatDelta(value)}
        </span>
      ))}
    </div>
  );
}

function formatDelta(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  if (Math.abs(value) < 0.005) return "0";
  return value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2);
}

function deltaClass(value: number | null | undefined): string {
  if (value === null || value === undefined || Math.abs(value) < 0.005) return "neutral";
  return value < 0 ? "improved" : "watch";
}

function IdeaCard({ idea }: { idea: DesignIdea }) {
  return (
    <article className={`idea-card priority-${idea.priority}`}>
      <div className="idea-heading">
        <Lightbulb size={18} />
        <div>
          <strong>{idea.title}</strong>
          <span>{idea.priority} priority</span>
        </div>
      </div>
      <p>{idea.hypothesis}</p>
      <small>{idea.rationale}</small>
      <ul>
        {idea.suggested_changes.map((change) => (
          <li key={change}>{change}</li>
        ))}
      </ul>
      <div className="expected-effect">{idea.expected_effect}</div>
    </article>
  );
}

function formatValue(value: number | null): string {
  return value === null ? "-" : value.toFixed(2);
}

function PortfolioPanel({ insights, isLoading }: { insights: PortfolioInsights | null; isLoading: boolean }) {
  if (isLoading) {
    return (
      <div className="portfolio-panel loading">
        <Sparkles size={18} className="spin" />
        Scoring compounds and detecting assay columns...
      </div>
    );
  }

  if (!insights) {
    return (
      <div className="portfolio-panel empty">
        <Sparkles size={18} />
        Upload compounds to unlock lead scoring, property alerts, and next-step recommendations.
      </div>
    );
  }

  const highAlerts = insights.property_alerts.high ?? 0;
  const mediumAlerts = insights.property_alerts.medium ?? 0;

  return (
    <div className="portfolio-panel">
      <div className="portfolio-header">
        <div>
          <p className="eyebrow">Smart triage</p>
          <h3>Portfolio co-pilot</h3>
        </div>
        <div className="insight-chips">
          <span>{insights.detected_potency_column ? `Potency: ${insights.detected_potency_column}` : "No potency column detected"}</span>
          <span>{insights.detected_admet_columns.length ? `ADMET: ${insights.detected_admet_columns.join(", ")}` : "No ADMET columns"}</span>
          <span>
            <AlertTriangle size={14} />
            {highAlerts + mediumAlerts} property alerts
          </span>
        </div>
      </div>

      <div className="portfolio-grid">
        <div className="lead-list">
          <h4>Recommended leads</h4>
          {insights.recommended_compounds.slice(0, 5).map((compound) => (
            <LeadCard compound={compound} key={compound.id} />
          ))}
        </div>

        <div className="action-list">
          <h4>Agent next actions</h4>
          <ol>
            {insights.next_actions.map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ol>

          <h4>Cluster opportunities</h4>
          <div className="cluster-grid">
            {insights.cluster_opportunities.length ? (
              insights.cluster_opportunities.map((cluster) => (
                <span key={cluster.cluster_id}>
                  C{cluster.cluster_id} · {cluster.compound_count} cmpds · {cluster.median_score}/100
                </span>
              ))
            ) : (
              <span>Run clustering to reveal series-level opportunities.</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function LeadCard({ compound }: { compound: RecommendedCompound }) {
  return (
    <div className="lead-card">
      <div className="score-ring">{compound.score}</div>
      <img className="lead-structure" src={structureUrl(compound.id)} alt={compound.name ?? `Compound ${compound.id}`} />
      <div>
        <strong>{compound.name ?? `Compound ${compound.id}`}</strong>
        <span>{compound.rationale}</span>
        {compound.alerts.length > 0 && <small>{compound.alerts[0].message}</small>}
      </div>
    </div>
  );
}
