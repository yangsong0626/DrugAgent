export interface MoleculeRecord {
  id: number;
  name: string | null;
  smiles: string;
  source_filename: string;
  mol_weight: number | null;
  logp: number | null;
  hbd: number | null;
  hba: number | null;
  tpsa: number | null;
  rotatable_bonds: number | null;
  cluster_id: number | null;
  properties: Record<string, number | string | null>;
}

export interface ProjectRecord {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface ProjectDetail extends ProjectRecord {
  uploads: Record<string, unknown>[];
  compound_count: number;
}

export interface DecisionLogRecord {
  id: number;
  project_id: string;
  entry_type: string;
  title: string;
  body: Record<string, unknown>;
  created_at: string;
}

export interface DesignFeedbackRecord {
  id: number;
  project_id: string;
  smiles: string;
  feedback: "like" | "dislike" | string;
  reason: string | null;
  design: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface UploadResponse {
  upload_id: string;
  project_id: string | null;
  filename: string;
  imported_count: number;
  skipped_count: number;
  molecules: MoleculeRecord[];
}

export interface AssayColumnInference {
  name: string;
  role: string;
  assay_type: string;
  unit: string | null;
  direction: string | null;
  confidence: number;
  numeric_fraction: number;
  median_value?: number | null;
}

export interface ColumnInference {
  compound_count: number;
  numeric_columns: string[];
  potency_columns: AssayColumnInference[];
  admet_columns: AssayColumnInference[];
  recommended_potency_column: string | null;
  recommended_admet_columns: string[];
  metadata: Record<string, unknown>;
}

export interface ClusterSummary {
  cluster_id: number;
  size: number;
  representative_id: number;
  representative_smiles: string;
  avg_mol_weight: number | null;
  avg_logp: number | null;
}

export interface ReportPlaceholder {
  title: string;
  markdown: string;
}

export interface BriefingReport {
  title: string;
  markdown: string;
}

export interface DesignProposalReport {
  title: string;
  markdown: string;
  recommendation_count: number;
  decision_log_id: number | null;
}

export interface SarEvidenceRow {
  scaffold: string;
  weaker_compound_id: number;
  stronger_compound_id: number;
  weaker_name: string | null;
  stronger_name: string | null;
  weaker_potency: number;
  stronger_potency: number;
  fold_change: number;
  position: string | null;
  weaker_substitution: string;
  stronger_substitution: string;
  note: string;
}

export interface SarScaffoldVector {
  label: string;
  atom_index: number;
  x: number;
  y: number;
  label_x: number;
  label_y: number;
}

export interface SarScaffoldMap {
  scaffold_smiles: string | null;
  scaffold_svg: string;
  vectors: SarScaffoldVector[];
}

export interface SarSummary {
  potency_column: string;
  potency_direction: string;
  compound_count: number;
  analyzable_compound_count: number;
  scaffold_count: number;
  matched_pair_count: number;
  key_sar_trends: string[];
  risky_modifications: string[];
  promising_positions: string[];
  suggested_next_analogs: string[];
  evidence_table: SarEvidenceRow[];
  scaffold_groups: Record<string, number[]>;
  scaffold_map: SarScaffoldMap;
  admet_columns: string[];
  metadata: Record<string, unknown>;
}

export interface SarRGroupTableRow {
  compound_id: number;
  name: string | null;
  smiles: string;
  potency: number;
  r_groups: Record<string, string>;
  admet_values: Record<string, number | string | null>;
}

export interface SarRGroupTable {
  scaffold: string;
  compound_count: number;
  positions: string[];
  rows: SarRGroupTableRow[];
}

export interface SarHeatmapCell {
  scaffold: string;
  position: string;
  substitution: string;
  compound_count: number;
  median_potency: number;
  best_potency: number;
  admet_medians: Record<string, number | string | null>;
}

export interface SarHypothesis {
  title: string;
  statement: string;
  confidence: string;
  recommended_action: string;
}

export interface SarWorkbench {
  summary: SarSummary;
  rgroup_tables: SarRGroupTable[];
  heatmap: SarHeatmapCell[];
  hypotheses: SarHypothesis[];
  metadata: Record<string, unknown>;
}

export interface PropertyAlert {
  field: string;
  severity: "high" | "medium" | "low" | string;
  message: string;
}

export interface RecommendedCompound {
  id: number;
  name: string | null;
  smiles: string;
  cluster_id: number | null;
  score: number;
  potency_value: number | null;
  rationale: string;
  alerts: PropertyAlert[];
  admet_notes: string[];
  properties: Record<string, number | string | null>;
}

export interface ClusterOpportunity {
  cluster_id: number;
  compound_count: number;
  median_score: number;
}

export interface PortfolioInsights {
  compound_count: number;
  numeric_columns: string[];
  detected_potency_column: string | null;
  detected_admet_columns: string[];
  recommended_compounds: RecommendedCompound[];
  property_alerts: Record<string, number>;
  cluster_opportunities: ClusterOpportunity[];
  next_actions: string[];
  metadata: Record<string, unknown>;
}

export interface DesignIdea {
  title: string;
  hypothesis: string;
  rationale: string;
  priority: "high" | "medium" | "low" | string;
  suggested_changes: string[];
  expected_effect: string;
}

export interface AnalogProposal {
  title: string;
  analog_smiles: string;
  source: "generated" | "observed_series" | string;
  property_goal: string;
  rationale: string;
  priority: "high" | "medium" | "low" | string;
  synthetic_note: string;
  predicted_descriptors: Record<string, number | string | null>;
  descriptor_deltas: Record<string, number | null>;
  reference_molecule_id: number | null;
  reference_molecule_name: string | null;
}

export interface CompoundDesignIdeas {
  molecule_id: number;
  molecule_name: string | null;
  source_smiles: string | null;
  potency_column: string | null;
  potency_value: number | null;
  detected_admet_columns: string[];
  cluster_compound_count: number;
  analog_proposals: AnalogProposal[];
  ideas: DesignIdea[];
  context: Record<string, unknown>;
}

export interface DesignSpacePoint {
  id: number;
  name: string;
  smiles: string;
  source_molecule_id: number;
  source_molecule_name: string | null;
  x: number;
  y: number;
  cluster_id: number;
  score: number;
  properties: Record<string, number | string | null>;
}

export interface DesignSpaceCluster {
  cluster_id: number;
  size: number;
  centroid_x: number;
  centroid_y: number;
  avg_score: number;
  representative: DesignSpacePoint;
}

export interface DesignSpace {
  upload_id: string;
  requested_count: number;
  generated_count: number;
  projection_method: string;
  cluster_count: number;
  clusters: DesignSpaceCluster[];
  points: DesignSpacePoint[];
  metadata: Record<string, unknown>;
}

export interface SyntheticFeasibility {
  score: number;
  level: "easy" | "moderate" | "hard" | string;
  reason: string;
  features: Record<string, number | string | null>;
}

export interface NextRoundRecommendation {
  smiles: string;
  name: string;
  score: number;
  base_score: number | null;
  preference_adjustment: number;
  preference_reasons: string[];
  priority: "high" | "medium" | "low" | string;
  source_molecule_id: number;
  source_molecule_name: string | null;
  source_smiles: string;
  transform_title: string | null;
  property_goal: string | null;
  rationale: string;
  expected_benefit: string;
  main_risk: string;
  supporting_evidence: string[];
  synthetic_note: string;
  synthetic_feasibility: SyntheticFeasibility;
  alerts: PropertyAlert[];
  predicted_descriptors: Record<string, number | string | null>;
  descriptor_deltas: Record<string, number | string | null>;
}

export interface NextRoundDesign {
  potency_column: string | null;
  potency_direction: string;
  admet_columns: string[];
  objectives: Record<string, unknown>;
  constraints: Record<string, unknown>;
  seed_compounds: Record<string, unknown>[];
  recommendations: NextRoundRecommendation[];
  metadata: Record<string, unknown>;
  feedback: DesignFeedbackRecord[];
}
