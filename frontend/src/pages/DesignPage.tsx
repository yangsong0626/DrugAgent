import { AlertTriangle, CheckCircle2, Loader2, Network, Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { analogStructureUrl, generateDesignSpace, generateNextRoundDesign, inferAssayColumns, submitDesignFeedback } from "../api/client";
import type { DesignFeedbackRecord, DesignSpace, DesignSpaceCluster, DesignSpacePoint, NextRoundDesign, NextRoundRecommendation } from "../types/molecule";

interface DesignPageProps {
  uploadId?: string;
  projectId?: string;
}

const CLUSTER_COLORS = [
  "#23675e",
  "#b83245",
  "#c7831f",
  "#2f6fad",
  "#7c4d9e",
  "#4f7d2d",
  "#9d4f2d",
  "#1f7a8c",
  "#8c5f1f",
  "#4f6272",
];

export function DesignPage({ uploadId, projectId }: DesignPageProps) {
  const [designSpace, setDesignSpace] = useState<DesignSpace | null>(null);
  const [nextRound, setNextRound] = useState<NextRoundDesign | null>(null);
  const [targetCount, setTargetCount] = useState(12000);
  const [recommendationCount, setRecommendationCount] = useState(24);
  const [potencyColumn, setPotencyColumn] = useState("");
  const [admetColumns, setAdmetColumns] = useState("");
  const [selectedCluster, setSelectedCluster] = useState<number | null>(null);
  const [isDesigning, setIsDesigning] = useState(false);
  const [isRecommending, setIsRecommending] = useState(false);
  const [feedbackBySmiles, setFeedbackBySmiles] = useState<Record<string, DesignFeedbackRecord>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const scope = projectId ? { projectId } : uploadId ? { uploadId } : null;
    if (!scope) return;
    inferAssayColumns(scope)
      .then((columns) => {
        setPotencyColumn(columns.recommended_potency_column ?? "");
        setAdmetColumns(columns.recommended_admet_columns.join(", "));
      })
      .catch(() => undefined);
  }, [projectId, uploadId]);

  async function handleNextRound() {
    const scope = projectId ? { projectId } : uploadId ? { uploadId } : null;
    if (!scope) {
      setError("Upload compounds before generating next-round designs.");
      return;
    }
    setIsRecommending(true);
    setError(null);
    try {
      const response = await generateNextRoundDesign({
          ...scope,
          potencyColumn: potencyColumn.trim() || undefined,
          admetColumns: splitColumns(admetColumns),
          count: Math.max(1, Math.min(80, Math.round(recommendationCount || 24))),
          objectives: {
            improve_potency: true,
            reduce_logp: true,
            improve_solubility: true,
            improve_microsomal_stability: splitColumns(admetColumns).some((column) => /clint|clearance|hlm|mlm/i.test(column)),
          },
          constraints: {
            max_mw: 560,
            max_logp: 5.5,
            max_tpsa: 150,
            prefer_one_step_from_existing: true,
          },
        });
      setNextRound(response);
      setFeedbackBySmiles(Object.fromEntries((response.feedback ?? []).map((item) => [item.smiles, item])));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate next-round designs.");
    } finally {
      setIsRecommending(false);
    }
  }

  async function handleFeedback(recommendation: NextRoundRecommendation, feedback: "like" | "dislike") {
    if (!projectId) {
      setError("Design feedback is saved at the project level. Upload into a project before giving feedback.");
      return;
    }
    setError(null);
    try {
      const record = await submitDesignFeedback(projectId, {
        smiles: recommendation.smiles,
        feedback,
        design: recommendation as unknown as Record<string, unknown>,
      });
      setFeedbackBySmiles((current) => ({ ...current, [record.smiles]: record }));
      await handleNextRound();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save design feedback.");
    }
  }

  async function handleDesignSpace() {
    if (!uploadId) {
      setError("Upload compounds before designing a compound space.");
      return;
    }
    setIsDesigning(true);
    setError(null);
    try {
      const normalizedTargetCount = Math.max(1000, Math.min(15000, Math.round(targetCount || 12000)));
      setTargetCount(normalizedTargetCount);
      const response = await generateDesignSpace({ uploadId, targetCount: normalizedTargetCount });
      setDesignSpace(response);
      setSelectedCluster(response.clusters[0]?.cluster_id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not design compounds.");
    } finally {
      setIsDesigning(false);
    }
  }

  const selectedClusterSummary = useMemo(() => {
    if (!designSpace || selectedCluster === null) return null;
    return designSpace.clusters.find((cluster) => cluster.cluster_id === selectedCluster) ?? null;
  }, [designSpace, selectedCluster]);

  return (
    <section className="page-section design-space-page">
      <div className="section-heading with-actions">
        <div>
          <p className="eyebrow">Design</p>
          <h2>Next-round compound design</h2>
        </div>
        <div className="design-space-controls">
          <label>
            Recommendations
            <input
              min={1}
              max={80}
              step={1}
              type="number"
              value={recommendationCount}
              onChange={(event) => setRecommendationCount(Number(event.target.value))}
            />
          </label>
          <button className="primary-button" disabled={(!uploadId && !projectId) || isRecommending} onClick={handleNextRound}>
            {isRecommending ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
            Recommend next round
          </button>
        </div>
      </div>

      <div className="next-round-controls">
        <label>
          Potency column
          <input value={potencyColumn} onChange={(event) => setPotencyColumn(event.target.value)} placeholder="ic50_nm" />
        </label>
        <label>
          ADMET columns
          <input value={admetColumns} onChange={(event) => setAdmetColumns(event.target.value)} placeholder="clint, solubility" />
        </label>
      </div>

      {!uploadId && !projectId && <p className="status error">Upload CSV, SDF, or patent PDF compounds before designing.</p>}
      {error && <p className="status error">{error}</p>}
      {nextRound ? (
        <NextRoundPanel design={nextRound} feedbackBySmiles={feedbackBySmiles} onFeedback={handleFeedback} />
      ) : (
        <NextRoundEmpty />
      )}

      <div className="section-heading with-actions design-space-heading">
        <div>
          <p className="eyebrow">Design map</p>
          <h2>Enumerated design space</h2>
        </div>
        <div className="design-space-controls">
          <label>
            Compounds
            <input
              min={1000}
              max={15000}
              step={1000}
              type="number"
              value={targetCount}
              onChange={(event) => setTargetCount(Number(event.target.value))}
            />
          </label>
          <button className="primary-button" disabled={!uploadId || isDesigning} onClick={handleDesignSpace}>
            {isDesigning ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
            Design compounds
          </button>
        </div>
      </div>

      {designSpace ? (
        <div className="design-space-layout">
          <div className="tsne-panel">
            <div className="tsne-header">
              <div>
                <strong>{designSpace.generated_count.toLocaleString()} designed compounds</strong>
                <span>
                  {designSpace.cluster_count} clusters · {designSpace.projection_method}
                </span>
              </div>
              <Network size={20} />
            </div>
            <TsneMap points={designSpace.points} selectedCluster={selectedCluster} onSelectCluster={setSelectedCluster} />
          </div>

          <div className="cluster-representatives">
            {selectedClusterSummary && <ClusterFocus cluster={selectedClusterSummary} />}
            <div className="cluster-card-grid">
              {designSpace.clusters.map((cluster) => (
                <ClusterCard
                  cluster={cluster}
                  isSelected={cluster.cluster_id === selectedCluster}
                  key={cluster.cluster_id}
                  onSelect={() => setSelectedCluster(cluster.cluster_id)}
                />
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="design-space-empty">
          <Sparkles size={28} />
          <strong>Generate an enumerated design library from the uploaded data.</strong>
          <span>The map will cluster designed structures and surface one representative compound per cluster.</span>
        </div>
      )}
    </section>
  );
}

function NextRoundEmpty() {
  return (
    <div className="next-round-empty">
      <Sparkles size={24} />
      <strong>Generate a prioritized make/test list from the uploaded SAR.</strong>
      <span>Recommendations include descriptor movement, medchem alerts, and synthesis feasibility.</span>
    </div>
  );
}

function NextRoundPanel({
  design,
  feedbackBySmiles,
  onFeedback,
}: {
  design: NextRoundDesign;
  feedbackBySmiles: Record<string, DesignFeedbackRecord>;
  onFeedback: (recommendation: NextRoundRecommendation, feedback: "like" | "dislike") => void;
}) {
  return (
    <div className="next-round-panel">
      <div className="next-round-header">
        <div>
          <strong>{design.recommendations.length} recommended analogs</strong>
          <span>
            {design.potency_column ?? "No potency endpoint"} · {String(design.metadata.generated_candidate_count ?? 0)} candidates scored ·{" "}
            {String(design.metadata.preference_feedback_count ?? 0)} feedback signals
          </span>
        </div>
      </div>
      <div className="recommendation-grid">
        {design.recommendations.slice(0, 12).map((recommendation) => (
          <RecommendationCard
            feedback={feedbackBySmiles[recommendation.smiles]?.feedback}
            onFeedback={onFeedback}
            recommendation={recommendation}
            key={recommendation.smiles}
          />
        ))}
      </div>
    </div>
  );
}

function RecommendationCard({
  recommendation,
  feedback,
  onFeedback,
}: {
  recommendation: NextRoundRecommendation;
  feedback?: string;
  onFeedback: (recommendation: NextRoundRecommendation, feedback: "like" | "dislike") => void;
}) {
  const alert = recommendation.alerts[0];
  const feasibility = recommendation.synthetic_feasibility;
  return (
    <article className={`recommendation-card priority-${recommendation.priority}`}>
      <div className="recommendation-topline">
        <span>{recommendation.priority}</span>
        <strong>{recommendation.score.toFixed(1)}</strong>
      </div>
      {recommendation.preference_adjustment !== 0 && (
        <div className={recommendation.preference_adjustment > 0 ? "preference-chip positive" : "preference-chip negative"}>
          {recommendation.preference_adjustment > 0 ? "+" : ""}
          {recommendation.preference_adjustment.toFixed(1)} preference
        </div>
      )}
      <img src={analogStructureUrl(recommendation.smiles)} alt={recommendation.name} />
      <h3>{recommendation.transform_title ?? recommendation.name}</h3>
      <p>{recommendation.expected_benefit}</p>
      <div className="feasibility-line">
        {feasibility.level === "easy" ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
        <span>
          {feasibility.level} synthesis · {Math.round(feasibility.score * 100)}%
        </span>
      </div>
      <small>{alert ? alert.message : recommendation.main_risk}</small>
      <div className="feedback-row" aria-label="Design feedback">
        <button className={feedback === "like" ? "active" : ""} onClick={() => onFeedback(recommendation, "like")} title="Like this design">
          <ThumbsUp size={15} />
          Like
        </button>
        <button className={feedback === "dislike" ? "active dislike" : "dislike"} onClick={() => onFeedback(recommendation, "dislike")} title="Dislike this design">
          <ThumbsDown size={15} />
          Dislike
        </button>
      </div>
      <details>
        <summary>Rationale</summary>
        <p>{recommendation.rationale}</p>
        {recommendation.preference_reasons.length > 0 && (
          <ul className="preference-reasons">
            {recommendation.preference_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
        <code>{recommendation.smiles}</code>
      </details>
    </article>
  );
}

function TsneMap({
  points,
  selectedCluster,
  onSelectCluster,
}: {
  points: DesignSpacePoint[];
  selectedCluster: number | null;
  onSelectCluster: (clusterId: number) => void;
}) {
  const viewPoints = useMemo(() => normalizePoints(points), [points]);

  return (
    <svg className="tsne-map" viewBox="0 0 1000 680" role="img" aria-label="t-SNE compound design clusters">
      <rect className="tsne-frame" x="1" y="1" width="998" height="678" rx="8" />
      {viewPoints.map((point) => {
        const selected = selectedCluster === null || selectedCluster === point.cluster_id;
        return (
          <circle
            className={selected ? "tsne-point selected" : "tsne-point"}
            cx={point.screenX}
            cy={point.screenY}
            fill={clusterColor(point.cluster_id)}
            key={point.id}
            onClick={() => onSelectCluster(point.cluster_id)}
            r={selected ? 3.6 : 2.2}
          >
            <title>{`${point.name} · C${point.cluster_id} · score ${point.score}`}</title>
          </circle>
        );
      })}
    </svg>
  );
}

function ClusterFocus({ cluster }: { cluster: DesignSpaceCluster }) {
  const representative = cluster.representative;
  return (
    <div className="cluster-focus">
      <img src={analogStructureUrl(representative.smiles)} alt={`Cluster ${cluster.cluster_id} representative`} />
      <div>
        <p className="eyebrow">Selected cluster</p>
        <h3>C{cluster.cluster_id}</h3>
        <span>
          {cluster.size.toLocaleString()} compounds · avg score {cluster.avg_score}
        </span>
        <code>{representative.smiles}</code>
      </div>
    </div>
  );
}

function ClusterCard({
  cluster,
  isSelected,
  onSelect,
}: {
  cluster: DesignSpaceCluster;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const representative = cluster.representative;
  return (
    <button className={isSelected ? "cluster-card selected" : "cluster-card"} onClick={onSelect}>
      <span className="cluster-swatch" style={{ background: clusterColor(cluster.cluster_id) }} />
      <img src={analogStructureUrl(representative.smiles)} alt={`Representative for cluster ${cluster.cluster_id}`} />
      <strong>C{cluster.cluster_id}</strong>
      <small>
        {cluster.size.toLocaleString()} cmpds · score {cluster.avg_score}
      </small>
    </button>
  );
}

function normalizePoints(points: DesignSpacePoint[]) {
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const width = maxX - minX || 1;
  const height = maxY - minY || 1;

  return points.map((point) => ({
    ...point,
    screenX: 36 + ((point.x - minX) / width) * 928,
    screenY: 36 + (1 - (point.y - minY) / height) * 608,
  }));
}

function clusterColor(clusterId: number) {
  return CLUSTER_COLORS[(clusterId - 1) % CLUSTER_COLORS.length];
}

function splitColumns(value: string) {
  return value
    .split(",")
    .map((column) => column.trim())
    .filter(Boolean);
}
