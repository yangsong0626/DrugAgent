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


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    imported_count: int
    skipped_count: int
    molecules: List[MoleculeRecord]


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


class SarSummaryRequest(BaseModel):
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


class BriefingReportRequest(BaseModel):
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
