import { useEffect, useState } from "react";
import {
  exportBriefingReport,
  fetchPortfolioInsights,
  fetchReportPlaceholder,
  generateBriefingReport,
  structureUrl,
  summarizeSar,
} from "../api/client";
import type { BriefingReport, ReportPlaceholder, SarSummary } from "../types/molecule";

interface ReportPageProps {
  uploadId?: string;
}

export function ReportPage({ uploadId }: ReportPageProps) {
  const [report, setReport] = useState<ReportPlaceholder | null>(null);
  const [potencyColumn, setPotencyColumn] = useState("ic50_nm");
  const [projectName, setProjectName] = useState("Patent-to-SAR Agent Briefing");
  const [admetColumns, setAdmetColumns] = useState("");
  const [minFoldChange, setMinFoldChange] = useState(3);
  const [sarSummary, setSarSummary] = useState<SarSummary | null>(null);
  const [briefing, setBriefing] = useState<BriefingReport | null>(null);
  const [sarError, setSarError] = useState<string | null>(null);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    fetchReportPlaceholder().then(setReport).catch(() => {
      setReport({
        title: "Patent-to-SAR MVP Report",
        markdown: "# Patent-to-SAR MVP Report\n\nReport service is unavailable.",
      });
    });
  }, []);

  useEffect(() => {
    if (!uploadId) return;
    fetchPortfolioInsights(uploadId)
      .then((insights) => {
        if (insights.detected_potency_column) setPotencyColumn(insights.detected_potency_column);
        if (insights.detected_admet_columns.length) setAdmetColumns(insights.detected_admet_columns.join(", "));
      })
      .catch(() => undefined);
  }, [uploadId]);

  async function handleSarSummary() {
    if (!uploadId) return;
    setIsSummarizing(true);
    setSarError(null);
    try {
      setSarSummary(
        await summarizeSar({
          uploadId,
          potencyColumn,
          admetColumns: admetColumns
            .split(",")
            .map((column) => column.trim())
            .filter(Boolean),
          minFoldChange,
        }),
      );
    } catch (err) {
      setSarError(err instanceof Error ? err.message : "Could not generate SAR summary");
    } finally {
      setIsSummarizing(false);
    }
  }

  async function handleBriefingPreview() {
    if (!uploadId) return;
    setIsExporting(true);
    setSarError(null);
    try {
      setBriefing(await generateBriefingReport(reportParams(uploadId, projectName, potencyColumn, admetColumns, minFoldChange)));
    } catch (err) {
      setSarError(err instanceof Error ? err.message : "Could not generate briefing");
    } finally {
      setIsExporting(false);
    }
  }

  async function handleBriefingExport(format: "markdown" | "docx") {
    if (!uploadId) return;
    setIsExporting(true);
    setSarError(null);
    try {
      await exportBriefingReport(reportParams(uploadId, projectName, potencyColumn, admetColumns, minFoldChange), format);
    } catch (err) {
      setSarError(err instanceof Error ? err.message : "Could not export briefing");
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <section className="page-section report-page">
      <div className="section-heading">
        <p className="eyebrow">Project output</p>
        <h2>{report?.title ?? "Report"}</h2>
      </div>
      <article className="markdown-preview">
        {(report?.markdown ?? "Loading report...").split("\n").map((line, index) => {
          if (line.startsWith("# ")) return <h3 key={index}>{line.replace("# ", "")}</h3>;
          if (!line.trim()) return <br key={index} />;
          return <p key={index}>{line}</p>;
        })}
      </article>

      <div className="sar-panel">
        <div className="section-heading compact">
          <p className="eyebrow">SAR summary</p>
          <h2>Matched-pair trends</h2>
        </div>
        <div className="sar-controls">
          <label>
            Project name
            <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
          </label>
          <label>
            Potency column
            <input value={potencyColumn} onChange={(event) => setPotencyColumn(event.target.value)} />
          </label>
          <label>
            ADMET columns
            <input value={admetColumns} onChange={(event) => setAdmetColumns(event.target.value)} placeholder="clint, logd, hERG" />
          </label>
          <label>
            Min fold change
            <input
              type="number"
              min="1.1"
              step="0.1"
              value={minFoldChange}
              onChange={(event) => setMinFoldChange(Number(event.target.value))}
            />
          </label>
          <button className="primary-button" disabled={!uploadId || isSummarizing || !potencyColumn} onClick={handleSarSummary}>
            Generate SAR
          </button>
          <button className="secondary-button" disabled={!uploadId || isExporting} onClick={handleBriefingPreview}>
            Preview briefing
          </button>
          <button className="secondary-button" disabled={!uploadId || isExporting} onClick={() => handleBriefingExport("markdown")}>
            Markdown
          </button>
          <button className="secondary-button" disabled={!uploadId || isExporting} onClick={() => handleBriefingExport("docx")}>
            DOCX
          </button>
        </div>
        {!uploadId && <p className="status error">Upload a CSV, SDF, or patent PDF file before generating SAR.</p>}
        {sarError && <p className="status error">{sarError}</p>}
        {sarSummary && <SarSummaryView summary={sarSummary} />}
        {briefing && (
          <div className="briefing-preview">
            <h3>Markdown preview</h3>
            <pre>{briefing.markdown}</pre>
          </div>
        )}
      </div>
    </section>
  );
}

function reportParams(uploadId: string, projectName: string, potencyColumn: string, admetColumns: string, minFoldChange: number) {
  return {
    uploadId,
    projectName,
    potencyColumn: potencyColumn.trim() || undefined,
    admetColumns: admetColumns
      .split(",")
      .map((column) => column.trim())
      .filter(Boolean),
    minFoldChange,
  };
}

function SarSummaryView({ summary }: { summary: SarSummary }) {
  return (
    <div className="sar-summary">
      <div className="metric-row">
        <span>{summary.analyzable_compound_count} analyzable compounds</span>
        <span>{summary.scaffold_count} scaffolds</span>
        <span>{summary.matched_pair_count} matched pairs</span>
      </div>
      <SarSummaryFigure summary={summary} />
      <SummaryList title="Key SAR Trends" items={summary.key_sar_trends} />
      <SummaryList title="Risky Modifications" items={summary.risky_modifications} />
      <SummaryList title="Promising Positions" items={summary.promising_positions} />
      <SummaryList title="Suggested Next Analogs" items={summary.suggested_next_analogs} />
      <div className="evidence-table">
        <h3>Evidence table</h3>
        <table>
          <thead>
            <tr>
              <th>Pair</th>
              <th>Weaker structure</th>
              <th>Stronger structure</th>
              <th>Position</th>
              <th>Change</th>
              <th>Fold</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            {summary.evidence_table.map((row) => (
              <tr key={`${row.weaker_compound_id}-${row.stronger_compound_id}`}>
                <td>
                  {row.weaker_name ?? row.weaker_compound_id} {"->"} {row.stronger_name ?? row.stronger_compound_id}
                </td>
                <td>
                  <img
                    className="evidence-structure"
                    src={structureUrl(row.weaker_compound_id)}
                    alt={row.weaker_name ?? `Compound ${row.weaker_compound_id}`}
                  />
                </td>
                <td>
                  <img
                    className="evidence-structure"
                    src={structureUrl(row.stronger_compound_id)}
                    alt={row.stronger_name ?? `Compound ${row.stronger_compound_id}`}
                  />
                </td>
                <td>{row.position ?? "multi-site"}</td>
                <td>
                  {row.weaker_substitution} {"->"} {row.stronger_substitution}
                </td>
                <td>{row.fold_change.toFixed(1)}x</td>
                <td>{row.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SarSummaryFigure({ summary }: { summary: SarSummary }) {
  const scaffoldMap = summary.scaffold_map;
  const vectors = scaffoldMap?.vectors ?? [];
  const topTrend = summary.key_sar_trends[0] ?? "Matched-pair changes define the main potency trend.";
  const rightTrend = summary.key_sar_trends[1] ?? summary.promising_positions[0] ?? "A focused R-group scan is tolerated.";
  const lowerTrend = summary.suggested_next_analogs[0] ?? "Retain the favored substituent and scan nearby size and electronics.";
  const leftTrend = summary.promising_positions[0] ?? "This scaffold is the most adaptable site for modification.";
  const riskTrend = summary.risky_modifications[0] ?? "Track ADMET values alongside potency gains.";
  const potencyTrend = summary.evidence_table[0]
    ? `${summary.evidence_table[0].fold_change.toFixed(1)}x potency gain: ${summary.evidence_table[0].weaker_substitution} -> ${summary.evidence_table[0].stronger_substitution}`
    : "Potency gains are supported by matched-pair evidence.";
  const admetTrend = summary.admet_columns.length
    ? `ADMET tracked: ${summary.admet_columns.slice(0, 3).join(", ")}`
    : "Add ADMET columns to expose liability trends.";

  return (
    <div className="sar-figure-scroll">
      <figure className="sar-figure" aria-label="SAR summary map">
        <div className="sar-callout callout-top">{shortenText(topTrend, 118)}</div>
        <div className="sar-callout callout-left-top">{shortenText(riskTrend, 105)}</div>
        <div className="sar-callout callout-left">{shortenText(leftTrend, 105)}</div>
        <div className="sar-callout callout-right-top">{shortenText(rightTrend, 110)}</div>
        <div className="sar-callout callout-right">{shortenText(admetTrend, 80)}</div>
        <div className="sar-callout callout-bottom-left">{shortenText(lowerTrend, 82)}</div>
        <div className="sar-callout callout-bottom-right">
          <strong>Increase overall potency</strong>
          <span>{shortenText(potencyTrend, 96)}</span>
        </div>

        <svg className="sar-map" viewBox="0 0 1040 680" role="img" aria-labelledby="sar-map-title">
          <title id="sar-map-title">Central scaffold with R-group SAR callouts</title>
          <defs>
            <marker id="arrowhead" viewBox="0 0 10 10" refX="8.2" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#0d1720" />
            </marker>
          </defs>

          <line className="sar-arrow" x1="520" y1="236" x2="520" y2="94" />
          <line className="sar-arrow" x1="372" y1="292" x2="284" y2="168" />
          <line className="sar-arrow" x1="360" y1="388" x2="270" y2="388" />
          <line className="sar-arrow" x1="520" y1="446" x2="452" y2="570" />
          <line className="sar-arrow" x1="676" y1="292" x2="756" y2="164" />
          <line className="sar-arrow" x1="688" y1="388" x2="774" y2="388" />
          <line className="sar-arrow" x1="636" y1="446" x2="710" y2="560" />
        </svg>
        <div className="real-scaffold-panel">
          <div
            className="real-scaffold-svg"
            aria-label={scaffoldMap?.scaffold_smiles ? `SAR scaffold ${scaffoldMap.scaffold_smiles}` : "SAR scaffold"}
            dangerouslySetInnerHTML={{ __html: scaffoldMap?.scaffold_svg || "" }}
          />
          <svg className="vector-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {vectors.map((vector) => (
              <line
                key={`${vector.label}-${vector.atom_index}`}
                x1={vector.x}
                y1={vector.y}
                x2={vector.label_x}
                y2={vector.label_y}
              />
            ))}
          </svg>
          {vectors.map((vector, index) => (
            <span
              key={`${vector.label}-${vector.atom_index}`}
              className={`scaffold-vector-label vector-palette-${index % 6}`}
              style={{ left: `${vector.label_x}%`, top: `${vector.label_y}%` }}
            >
              {vector.label}
            </span>
          ))}
        </div>
      </figure>
    </div>
  );
}

function shortenText(text: string, maxLength: number) {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1).trim()}...`;
}

function SummaryList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="summary-list">
      <h3>{title}</h3>
      <ul>
        {items.map((item, index) => (
          <li key={`${title}-${index}-${item}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
