from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MoleculeRecord(BaseModel):
    id: int
    name: Optional[str] = None
    smiles: str
    source_filename: str
    mol_weight: Optional[float] = None
    logp: Optional[float] = None
    hbd: Optional[int] = None
    hba: Optional[int] = None
    tpsa: Optional[float] = None
    rotatable_bonds: Optional[int] = None
    cluster_id: Optional[int] = None
    properties: Dict[str, Any] = Field(default_factory=dict)


class ProjectCreateRequest(BaseModel):
    name: str = "Untitled MedChem Project"
    description: Optional[str] = None


class ProjectRecord(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: str


class ProjectDetail(ProjectRecord):
    uploads: List[Dict[str, Any]] = Field(default_factory=list)
    compound_count: int = 0


class DecisionLogCreateRequest(BaseModel):
    entry_type: str = "decision"
    title: str
    body: Dict[str, Any] = Field(default_factory=dict)


class DecisionLogRecord(BaseModel):
    id: int
    project_id: str
    entry_type: str
    title: str
    body: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class DesignFeedbackRequest(BaseModel):
    smiles: str
    feedback: str
    reason: Optional[str] = None
    design: Dict[str, Any] = Field(default_factory=dict)


class DesignFeedbackRecord(BaseModel):
    id: int
    project_id: str
    smiles: str
    feedback: str
    reason: Optional[str] = None
    design: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class UploadResponse(BaseModel):
    upload_id: str
    project_id: Optional[str] = None
    filename: str
    imported_count: int
    skipped_count: int
    molecules: List[MoleculeRecord]


class CommercialCatalogRecord(BaseModel):
    id: str
    filename: str
    source_type: str = "commercial"
    compound_count: int
    created_at: str


class CommercialCatalogUploadResponse(BaseModel):
    catalog: CommercialCatalogRecord
    imported_count: int
    skipped_count: int


class CommercialAnalogSearchRequest(BaseModel):
    target_smiles: str
    catalog_id: Optional[str] = None
    min_similarity: float = Field(default=0.7, ge=0.0, le=1.0)
    limit: int = Field(default=20, ge=1, le=100)


class CommercialAnalogHit(BaseModel):
    compound_id: int
    catalog_id: str
    vendor: Optional[str] = None
    catalog_number: Optional[str] = None
    name: Optional[str] = None
    smiles: str
    similarity: float
    availability: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    descriptor_deltas: Dict[str, Any] = Field(default_factory=dict)
    rationale: str


class CommercialAnalogSearchResponse(BaseModel):
    target_smiles: str
    searched_count: int
    min_similarity: float
    hits: List[CommercialAnalogHit] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AssayColumnInference(BaseModel):
    name: str
    role: str
    assay_type: str
    unit: Optional[str] = None
    direction: Optional[str] = None
    confidence: float
    numeric_fraction: float
    median_value: Optional[float] = None


class ColumnInferenceResponse(BaseModel):
    compound_count: int
    numeric_columns: List[str]
    potency_columns: List[AssayColumnInference]
    admet_columns: List[AssayColumnInference]
    recommended_potency_column: Optional[str] = None
    recommended_admet_columns: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExportRequest(BaseModel):
    molecule_ids: List[int] = Field(default_factory=list)
    format: str = "csv"


class ClusterSummary(BaseModel):
    cluster_id: int
    size: int
    representative_id: int
    representative_smiles: str
    avg_mol_weight: Optional[float] = None
    avg_logp: Optional[float] = None


class PropertyAlert(BaseModel):
    field: str
    severity: str
    message: str


class RecommendedCompound(BaseModel):
    id: int
    name: Optional[str] = None
    smiles: str
    cluster_id: Optional[int] = None
    score: float
    potency_value: Optional[float] = None
    rationale: str
    alerts: List[PropertyAlert] = Field(default_factory=list)
    admet_notes: List[str] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict)


class ClusterOpportunity(BaseModel):
    cluster_id: int
    compound_count: int
    median_score: float


class PortfolioInsightsResponse(BaseModel):
    compound_count: int
    numeric_columns: List[str]
    detected_potency_column: Optional[str] = None
    detected_admet_columns: List[str] = Field(default_factory=list)
    recommended_compounds: List[RecommendedCompound]
    property_alerts: Dict[str, int]
    cluster_opportunities: List[ClusterOpportunity]
    next_actions: List[str]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DesignIdea(BaseModel):
    title: str
    hypothesis: str
    rationale: str
    priority: str
    suggested_changes: List[str]
    expected_effect: str


class AnalogProposal(BaseModel):
    title: str
    analog_smiles: str
    source: str
    property_goal: str
    rationale: str
    priority: str
    synthetic_note: str
    predicted_descriptors: Dict[str, Any] = Field(default_factory=dict)
    descriptor_deltas: Dict[str, Any] = Field(default_factory=dict)
    reference_molecule_id: Optional[int] = None
    reference_molecule_name: Optional[str] = None


class CompoundDesignIdeasResponse(BaseModel):
    molecule_id: int
    molecule_name: Optional[str] = None
    source_smiles: Optional[str] = None
    potency_column: Optional[str] = None
    potency_value: Optional[float] = None
    detected_admet_columns: List[str] = Field(default_factory=list)
    cluster_compound_count: int
    analog_proposals: List[AnalogProposal] = Field(default_factory=list)
    ideas: List[DesignIdea]
    context: Dict[str, Any] = Field(default_factory=dict)


class DesignSpaceRequest(BaseModel):
    upload_id: str
    target_count: int = Field(default=12000, ge=1000, le=15000)
    cluster_count: Optional[int] = Field(default=None, ge=2, le=60)


class DesignSpacePoint(BaseModel):
    id: int
    name: str
    smiles: str
    source_molecule_id: int
    source_molecule_name: Optional[str] = None
    x: float
    y: float
    cluster_id: int
    score: float
    properties: Dict[str, Any] = Field(default_factory=dict)


class DesignSpaceCluster(BaseModel):
    cluster_id: int
    size: int
    centroid_x: float
    centroid_y: float
    avg_score: float
    representative: DesignSpacePoint


class DesignSpaceResponse(BaseModel):
    upload_id: str
    requested_count: int
    generated_count: int
    projection_method: str
    cluster_count: int
    clusters: List[DesignSpaceCluster]
    points: List[DesignSpacePoint]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NextRoundDesignRequest(BaseModel):
    project_id: Optional[str] = None
    upload_id: Optional[str] = None
    potency_column: Optional[str] = None
    potency_direction: str = "lower_is_better"
    admet_columns: List[str] = Field(default_factory=list)
    objectives: Dict[str, Any] = Field(default_factory=dict)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    count: int = Field(default=24, ge=1, le=80)


class SyntheticFeasibility(BaseModel):
    score: float
    level: str
    reason: str
    features: Dict[str, Any] = Field(default_factory=dict)


class RetrosynthesisStep(BaseModel):
    order: int
    title: str
    operation: str
    disconnection: str
    starting_materials: List[str] = Field(default_factory=list)
    reagent_smiles: List[str] = Field(default_factory=list)
    product_smiles: str
    conditions: str
    rationale: str


class RetrosynthesisPathNode(BaseModel):
    id: str
    label: str
    role: str
    smiles: Optional[str] = None
    note: str


class RetrosynthesisRoute(BaseModel):
    summary: str
    route_type: str
    confidence: str
    starting_materials: List[str] = Field(default_factory=list)
    target_smiles: str
    path_nodes: List[RetrosynthesisPathNode] = Field(default_factory=list)
    steps: List[RetrosynthesisStep] = Field(default_factory=list)
    route_risks: List[str] = Field(default_factory=list)
    chemist_note: str


class PropertyPredictionPlugin(BaseModel):
    id: str
    name: str
    family: str
    level: str
    score: float
    value: Any
    unit: Optional[str] = None
    rationale: str
    evidence: List[str] = Field(default_factory=list)


class PropertyPredictionBundle(BaseModel):
    source: str
    overall_level: str
    plugins: List[PropertyPredictionPlugin] = Field(default_factory=list)


class NextRoundRecommendation(BaseModel):
    smiles: str
    name: str
    score: float
    base_score: Optional[float] = None
    preference_adjustment: float = 0.0
    preference_reasons: List[str] = Field(default_factory=list)
    priority: str
    source_molecule_id: int
    source_molecule_name: Optional[str] = None
    source_smiles: str
    transform_title: Optional[str] = None
    property_goal: Optional[str] = None
    rationale: str
    expected_benefit: str
    main_risk: str
    supporting_evidence: List[str] = Field(default_factory=list)
    synthetic_note: str
    synthetic_feasibility: SyntheticFeasibility
    retrosynthesis_route: RetrosynthesisRoute
    property_predictions: PropertyPredictionBundle
    alerts: List[PropertyAlert] = Field(default_factory=list)
    predicted_descriptors: Dict[str, Any] = Field(default_factory=dict)
    descriptor_deltas: Dict[str, Any] = Field(default_factory=dict)


class NextRoundDesignResponse(BaseModel):
    potency_column: Optional[str] = None
    potency_direction: str
    admet_columns: List[str] = Field(default_factory=list)
    objectives: Dict[str, Any] = Field(default_factory=dict)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    seed_compounds: List[Dict[str, Any]] = Field(default_factory=list)
    recommendations: List[NextRoundRecommendation]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    feedback: List[DesignFeedbackRecord] = Field(default_factory=list)


class SarSummaryRequest(BaseModel):
    project_id: Optional[str] = None
    upload_id: Optional[str] = None
    molecule_ids: List[int] = Field(default_factory=list)
    potency_column: str
    potency_direction: str = "lower_is_better"
    admet_columns: List[str] = Field(default_factory=list)
    min_fold_change: float = 3.0


class SarEvidenceRow(BaseModel):
    scaffold: str
    weaker_compound_id: int
    stronger_compound_id: int
    weaker_name: Optional[str] = None
    stronger_name: Optional[str] = None
    weaker_potency: float
    stronger_potency: float
    fold_change: float
    position: Optional[str] = None
    weaker_substitution: str
    stronger_substitution: str
    note: str


class SarScaffoldVector(BaseModel):
    label: str
    atom_index: int
    x: float
    y: float
    label_x: float
    label_y: float


class SarScaffoldMap(BaseModel):
    scaffold_smiles: Optional[str] = None
    scaffold_svg: str = ""
    vectors: List[SarScaffoldVector] = Field(default_factory=list)


class SarSummaryResponse(BaseModel):
    potency_column: str
    potency_direction: str
    compound_count: int
    analyzable_compound_count: int
    scaffold_count: int
    matched_pair_count: int
    key_sar_trends: List[str]
    risky_modifications: List[str]
    promising_positions: List[str]
    suggested_next_analogs: List[str]
    evidence_table: List[SarEvidenceRow]
    scaffold_groups: Dict[str, List[int]]
    scaffold_map: SarScaffoldMap
    admet_columns: List[str]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SarWorkbenchRequest(SarSummaryRequest):
    pass


class SarRGroupTableRow(BaseModel):
    compound_id: int
    name: Optional[str] = None
    smiles: str
    potency: float
    r_groups: Dict[str, str] = Field(default_factory=dict)
    admet_values: Dict[str, Any] = Field(default_factory=dict)


class SarRGroupTable(BaseModel):
    scaffold: str
    compound_count: int
    positions: List[str]
    rows: List[SarRGroupTableRow]


class SarHeatmapCell(BaseModel):
    scaffold: str
    position: str
    substitution: str
    compound_count: int
    median_potency: float
    best_potency: float
    admet_medians: Dict[str, Any] = Field(default_factory=dict)


class SarHypothesis(BaseModel):
    title: str
    statement: str
    confidence: str
    recommended_action: str


class SarWorkbenchResponse(BaseModel):
    summary: SarSummaryResponse
    rgroup_tables: List[SarRGroupTable]
    heatmap: List[SarHeatmapCell]
    hypotheses: List[SarHypothesis]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BriefingReportRequest(BaseModel):
    project_id: Optional[str] = None
    upload_id: Optional[str] = None
    molecule_ids: List[int] = Field(default_factory=list)
    project_name: str = "Patent-to-SAR Agent Briefing"
    potency_column: Optional[str] = None
    potency_direction: str = "lower_is_better"
    admet_columns: List[str] = Field(default_factory=list)
    min_fold_change: float = 3.0


class BriefingReportResponse(BaseModel):
    title: str
    markdown: str


class DesignProposalReportRequest(NextRoundDesignRequest):
    project_name: str = "MedChem Design Proposal"
    min_fold_change: float = 3.0


class DesignProposalReportResponse(BaseModel):
    title: str
    markdown: str
    recommendation_count: int
    decision_log_id: Optional[int] = None
