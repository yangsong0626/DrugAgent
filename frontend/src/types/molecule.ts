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
}

export interface UploadResponse {
  upload_id: string;
  filename: string;
  imported_count: number;
  skipped_count: number;
  molecules: MoleculeRecord[];
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
