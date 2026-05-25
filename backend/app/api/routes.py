from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app.chem.parsers import parse_upload_file
from app.chem.rendering import smiles_to_svg
from app.config import UPLOAD_DIR
from app.models.schemas import (
    ClusterSummary,
    BriefingReportRequest,
    BriefingReportResponse,
    ColumnInferenceResponse,
    DecisionLogCreateRequest,
    DecisionLogRecord,
    DesignFeedbackRequest,
    DesignFeedbackRecord,
    DesignProposalReportRequest,
    DesignProposalReportResponse,
    CompoundDesignIdeasResponse,
    DesignSpaceRequest,
    DesignSpaceResponse,
    ExportRequest,
    MoleculeRecord,
    NextRoundDesignRequest,
    NextRoundDesignResponse,
    PortfolioInsightsResponse,
    ProjectCreateRequest,
    ProjectDetail,
    ProjectRecord,
    SarSummaryRequest,
    SarSummaryResponse,
    SarWorkbenchRequest,
    SarWorkbenchResponse,
    UploadResponse,
)
from app.services.clustering import cluster_molecules
from app.services.column_inference import infer_assay_columns
from app.services.design_ideas import generate_design_ideas
from app.services.design_proposal_report import (
    build_design_proposal_docx,
    build_design_proposal_report,
    decision_log_body_from_report,
)
from app.services.design_space import generate_design_space
from app.services.design_preferences import build_preference_profile
from app.services.exporters import molecules_to_csv, molecules_to_sdf
from app.services.portfolio_insights import generate_portfolio_insights
from app.services.next_round_design import generate_next_round_designs
from app.services.report_generator import build_briefing_docx, build_briefing_report
from app.services.sar_summary import generate_sar_summary
from app.services.sar_workbench import build_sar_workbench
from app.storage.database import (
    create_project,
    create_decision_log,
    create_upload,
    get_molecule,
    get_molecules_by_ids,
    get_project,
    insert_molecules,
    list_molecules,
    list_molecules_for_project,
    list_decision_logs,
    list_design_feedback,
    list_projects,
    list_uploads,
    upsert_design_feedback,
)

router = APIRouter(prefix="/api")


@router.post("/uploads/csv-sdf", response_model=UploadResponse)
async def upload_csv_sdf(file: UploadFile = File(...), project_id: str | None = Form(default=None)) -> UploadResponse:
    return await _ingest_upload(file=file, project_id=project_id)


@router.post("/projects", response_model=ProjectRecord)
def create_medchem_project(request: ProjectCreateRequest) -> ProjectRecord:
    project_id = str(uuid4())
    create_project(project_id, request.name.strip() or "Untitled MedChem Project", request.description)
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=500, detail="Project creation failed.")
    return ProjectRecord(**project)


@router.get("/projects", response_model=List[ProjectDetail])
def get_projects() -> List[ProjectDetail]:
    details: List[ProjectDetail] = []
    for project in list_projects():
        uploads = list_uploads(project["id"])
        details.append(
            ProjectDetail(
                **project,
                uploads=uploads,
                compound_count=len(list_molecules_for_project(project["id"])),
            )
        )
    return details


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project_detail(project_id: str) -> ProjectDetail:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return ProjectDetail(
        **project,
        uploads=list_uploads(project_id),
        compound_count=len(list_molecules_for_project(project_id)),
    )


@router.post("/projects/{project_id}/decision-log", response_model=DecisionLogRecord)
def add_project_decision_log(project_id: str, request: DecisionLogCreateRequest) -> DecisionLogRecord:
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    record = create_decision_log(
        project_id=project_id,
        entry_type=request.entry_type.strip() or "decision",
        title=request.title.strip() or "Untitled decision",
        body=request.body,
    )
    return DecisionLogRecord(**record)


@router.get("/projects/{project_id}/timeline", response_model=List[DecisionLogRecord])
def get_project_timeline(project_id: str) -> List[DecisionLogRecord]:
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return [DecisionLogRecord(**record) for record in list_decision_logs(project_id)]


@router.post("/projects/{project_id}/design-feedback", response_model=DesignFeedbackRecord)
def add_design_feedback(project_id: str, request: DesignFeedbackRequest) -> DesignFeedbackRecord:
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    feedback = request.feedback.strip().lower()
    if feedback not in {"like", "dislike"}:
        raise HTTPException(status_code=400, detail="Feedback must be like or dislike.")
    record = upsert_design_feedback(
        project_id=project_id,
        smiles=request.smiles,
        feedback=feedback,
        reason=request.reason,
        design=request.design,
    )
    create_decision_log(
        project_id=project_id,
        entry_type="design_feedback",
        title=f"{feedback.title()} design",
        body={
            "summary": f"User marked a design as {feedback}.",
            "smiles": request.smiles,
            "reason": request.reason,
            "transform_title": request.design.get("transform_title"),
            "property_goal": request.design.get("property_goal"),
        },
    )
    return DesignFeedbackRecord(**record)


@router.get("/projects/{project_id}/design-feedback", response_model=List[DesignFeedbackRecord])
def get_design_feedback(project_id: str) -> List[DesignFeedbackRecord]:
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return [DesignFeedbackRecord(**record) for record in list_design_feedback(project_id)]


@router.post("/projects/{project_id}/uploads", response_model=UploadResponse)
async def upload_project_compounds(project_id: str, file: UploadFile = File(...)) -> UploadResponse:
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return await _ingest_upload(file=file, project_id=project_id)


async def _ingest_upload(file: UploadFile, project_id: str | None = None) -> UploadResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".csv", ".sdf", ".pdf"}:
        raise HTTPException(status_code=400, detail="Upload a CSV, SDF, or patent PDF file.")

    upload_id = str(uuid4())
    safe_name = Path(file.filename or f"upload{suffix}").name
    stored_path = UPLOAD_DIR / f"{upload_id}{suffix}"
    stored_path.write_bytes(await file.read())

    try:
        records, skipped_count = parse_upload_file(stored_path, safe_name, upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if project_id and get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    create_upload(upload_id, safe_name, project_id)
    ids = insert_molecules(records)
    molecules = list_molecules(upload_id)
    cluster_molecules(molecules)
    molecules_by_id = {molecule["id"]: molecule for molecule in list_molecules(upload_id)}
    ordered_molecules = [MoleculeRecord(**molecules_by_id[molecule_id]) for molecule_id in ids]

    return UploadResponse(
        upload_id=upload_id,
        project_id=project_id,
        filename=safe_name,
        imported_count=len(ids),
        skipped_count=skipped_count,
        molecules=ordered_molecules,
    )


@router.get("/molecules", response_model=List[MoleculeRecord])
def get_molecules(upload_id: Optional[str] = Query(default=None)) -> List[MoleculeRecord]:
    return [MoleculeRecord(**molecule) for molecule in list_molecules(upload_id)]


@router.get("/projects/{project_id}/molecules", response_model=List[MoleculeRecord])
def get_project_molecules(project_id: str) -> List[MoleculeRecord]:
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return [MoleculeRecord(**molecule) for molecule in list_molecules_for_project(project_id)]


@router.get("/assays/columns", response_model=ColumnInferenceResponse)
def infer_columns(
    upload_id: Optional[str] = Query(default=None),
    project_id: Optional[str] = Query(default=None),
) -> ColumnInferenceResponse:
    molecules = _molecules_from_scope(upload_id=upload_id, project_id=project_id)
    if not molecules:
        raise HTTPException(status_code=400, detail="Upload compounds before inferring assay columns.")
    return ColumnInferenceResponse(**infer_assay_columns(molecules))


@router.get("/molecules/{molecule_id}/structure.svg")
def get_structure_svg(molecule_id: int) -> Response:
    molecule = get_molecule(molecule_id)
    if molecule is None:
        raise HTTPException(status_code=404, detail="Molecule not found.")
    return Response(content=smiles_to_svg(molecule["smiles"]), media_type="image/svg+xml")


@router.get("/structures/render.svg")
def render_structure_svg(smiles: str = Query(..., min_length=1)) -> Response:
    try:
        svg = smiles_to_svg(smiles)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid SMILES.") from exc
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/molecules/{molecule_id}/design-ideas", response_model=CompoundDesignIdeasResponse)
def get_compound_design_ideas(molecule_id: int) -> CompoundDesignIdeasResponse:
    molecule = get_molecule(molecule_id)
    if molecule is None:
        raise HTTPException(status_code=404, detail="Molecule not found.")
    related_molecules = list_molecules(str(molecule["upload_id"]))
    return CompoundDesignIdeasResponse(**generate_design_ideas(molecule, related_molecules))


@router.post("/clusters", response_model=List[ClusterSummary])
def calculate_clusters(upload_id: Optional[str] = Query(default=None), threshold: float = Query(default=0.55)) -> List[ClusterSummary]:
    molecules = list_molecules(upload_id)
    return [ClusterSummary(**summary) for summary in cluster_molecules(molecules, threshold)]


@router.get("/insights/portfolio", response_model=PortfolioInsightsResponse)
def portfolio_insights(upload_id: Optional[str] = Query(default=None)) -> PortfolioInsightsResponse:
    molecules = list_molecules(upload_id)
    if not molecules:
        raise HTTPException(status_code=400, detail="Upload compounds before generating portfolio insights.")
    return PortfolioInsightsResponse(**generate_portfolio_insights(molecules))


@router.post("/design/space", response_model=DesignSpaceResponse)
def create_design_space(request: DesignSpaceRequest) -> DesignSpaceResponse:
    molecules = list_molecules(request.upload_id)
    if not molecules:
        raise HTTPException(status_code=400, detail="Upload compounds before generating a design space.")
    try:
        design_space = generate_design_space(
            molecules=molecules,
            upload_id=request.upload_id,
            target_count=request.target_count,
            cluster_count=request.cluster_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DesignSpaceResponse(**design_space)


@router.post("/design/next-round", response_model=NextRoundDesignResponse)
def create_next_round_design(request: NextRoundDesignRequest) -> NextRoundDesignResponse:
    molecules = _molecules_from_scope(upload_id=request.upload_id, project_id=request.project_id)
    if not molecules:
        raise HTTPException(status_code=400, detail="Upload compounds before generating next-round designs.")
    feedback_rows = list_design_feedback(request.project_id) if request.project_id else []
    preference_profile = build_preference_profile(feedback_rows)
    try:
        designs = generate_next_round_designs(
            molecules=molecules,
            potency_column=request.potency_column,
            potency_direction=request.potency_direction,
            admet_columns=request.admet_columns,
            objectives=request.objectives,
            constraints=request.constraints,
            count=request.count,
            preference_profile=preference_profile,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    designs["feedback"] = feedback_rows
    return NextRoundDesignResponse(**designs)


@router.post("/exports/compounds")
def export_compounds(request: ExportRequest) -> Response:
    molecules = get_molecules_by_ids(request.molecule_ids)
    if not molecules:
        raise HTTPException(status_code=400, detail="Select at least one compound to export.")

    export_format = request.format.lower()
    if export_format == "csv":
        return Response(
            content=molecules_to_csv(molecules),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=selected_compounds.csv"},
        )
    if export_format == "sdf":
        return Response(
            content=molecules_to_sdf(molecules),
            media_type="chemical/x-mdl-sdfile",
            headers={"Content-Disposition": "attachment; filename=selected_compounds.sdf"},
        )

    raise HTTPException(status_code=400, detail="Export format must be csv or sdf.")


@router.post("/sar/summary", response_model=SarSummaryResponse)
def summarize_sar(request: SarSummaryRequest) -> SarSummaryResponse:
    molecules = _molecules_for_sar_request(request)

    if not molecules:
        raise HTTPException(status_code=400, detail="No compounds found for SAR summary.")

    try:
        summary = generate_sar_summary(
            molecules=molecules,
            potency_column=request.potency_column,
            potency_direction=request.potency_direction,
            admet_columns=request.admet_columns,
            min_fold_change=request.min_fold_change,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SarSummaryResponse(**summary)


@router.post("/sar/workbench", response_model=SarWorkbenchResponse)
def sar_workbench(request: SarWorkbenchRequest) -> SarWorkbenchResponse:
    molecules = _molecules_for_sar_request(request)
    if not molecules:
        raise HTTPException(status_code=400, detail="No compounds found for SAR workbench.")

    try:
        workbench = build_sar_workbench(
            molecules=molecules,
            potency_column=request.potency_column,
            potency_direction=request.potency_direction,
            admet_columns=request.admet_columns,
            min_fold_change=request.min_fold_change,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SarWorkbenchResponse(**workbench)


@router.post("/reports/briefing", response_model=BriefingReportResponse)
def generate_briefing_report(request: BriefingReportRequest) -> BriefingReportResponse:
    molecules = _molecules_for_report_request(request)
    report = build_briefing_report(
        molecules=molecules,
        project_name=request.project_name,
        potency_column=request.potency_column,
        potency_direction=request.potency_direction,
        admet_columns=request.admet_columns,
        min_fold_change=request.min_fold_change,
    )
    return BriefingReportResponse(title=report["title"], markdown=report["markdown"])


@router.post("/reports/briefing/export")
def export_briefing_report(request: BriefingReportRequest, format: str = Query(default="markdown")) -> Response:
    molecules = _molecules_for_report_request(request)
    report = build_briefing_report(
        molecules=molecules,
        project_name=request.project_name,
        potency_column=request.potency_column,
        potency_direction=request.potency_direction,
        admet_columns=request.admet_columns,
        min_fold_change=request.min_fold_change,
    )
    export_format = format.lower()
    if export_format in {"markdown", "md"}:
        return Response(
            content=report["markdown"],
            media_type="text/markdown",
            headers={"Content-Disposition": "attachment; filename=medchem_briefing.md"},
        )
    if export_format == "docx":
        return Response(
            content=build_briefing_docx(report),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": "attachment; filename=medchem_briefing.docx"},
        )
    raise HTTPException(status_code=400, detail="Report format must be markdown or docx.")


@router.post("/reports/design-proposal", response_model=DesignProposalReportResponse)
def generate_design_proposal_report(request: DesignProposalReportRequest) -> DesignProposalReportResponse:
    molecules = _molecules_from_scope(upload_id=request.upload_id, project_id=request.project_id)
    feedback_rows = list_design_feedback(request.project_id) if request.project_id else []
    report = build_design_proposal_report(
        molecules=molecules,
        project_name=request.project_name,
        potency_column=request.potency_column,
        potency_direction=request.potency_direction,
        admet_columns=request.admet_columns,
        objectives=request.objectives,
        constraints=request.constraints,
        count=request.count,
        min_fold_change=request.min_fold_change,
        preference_profile=build_preference_profile(feedback_rows),
    )
    decision_log_id = _record_design_proposal_decision(request.project_id, report)
    return DesignProposalReportResponse(
        title=report["title"],
        markdown=report["markdown"],
        recommendation_count=len(report["design"].get("recommendations", [])),
        decision_log_id=decision_log_id,
    )


@router.post("/reports/design-proposal/export")
def export_design_proposal_report(request: DesignProposalReportRequest, format: str = Query(default="markdown")) -> Response:
    molecules = _molecules_from_scope(upload_id=request.upload_id, project_id=request.project_id)
    feedback_rows = list_design_feedback(request.project_id) if request.project_id else []
    report = build_design_proposal_report(
        molecules=molecules,
        project_name=request.project_name,
        potency_column=request.potency_column,
        potency_direction=request.potency_direction,
        admet_columns=request.admet_columns,
        objectives=request.objectives,
        constraints=request.constraints,
        count=request.count,
        min_fold_change=request.min_fold_change,
        preference_profile=build_preference_profile(feedback_rows),
    )
    _record_design_proposal_decision(request.project_id, report)
    export_format = format.lower()
    if export_format in {"markdown", "md"}:
        return Response(
            content=report["markdown"],
            media_type="text/markdown",
            headers={"Content-Disposition": "attachment; filename=medchem_design_proposal.md"},
        )
    if export_format == "docx":
        return Response(
            content=build_design_proposal_docx(report),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": "attachment; filename=medchem_design_proposal.docx"},
        )
    raise HTTPException(status_code=400, detail="Report format must be markdown or docx.")


def _molecules_for_report_request(request: BriefingReportRequest) -> List[Dict[str, object]]:
    if request.molecule_ids:
        molecules = get_molecules_by_ids(request.molecule_ids)
    elif request.project_id:
        molecules = list_molecules_for_project(request.project_id)
    elif request.upload_id:
        molecules = list_molecules(request.upload_id)
    else:
        raise HTTPException(status_code=400, detail="Provide upload_id or molecule_ids.")

    if not molecules:
        raise HTTPException(status_code=400, detail="No compounds found for report generation.")
    return molecules


def _molecules_for_sar_request(request: SarSummaryRequest) -> List[Dict[str, object]]:
    if request.molecule_ids:
        return get_molecules_by_ids(request.molecule_ids)
    if request.project_id:
        return list_molecules_for_project(request.project_id)
    if request.upload_id:
        return list_molecules(request.upload_id)
    raise HTTPException(status_code=400, detail="Provide project_id, upload_id, or molecule_ids.")


def _molecules_from_scope(upload_id: str | None = None, project_id: str | None = None) -> List[Dict[str, object]]:
    if project_id:
        if get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return list_molecules_for_project(project_id)
    if upload_id:
        return list_molecules(upload_id)
    raise HTTPException(status_code=400, detail="Provide project_id or upload_id.")


def _record_design_proposal_decision(project_id: str | None, report: Dict[str, Any]) -> int | None:
    if not project_id:
        return None
    if get_project(project_id) is None:
        return None
    record = create_decision_log(
        project_id=project_id,
        entry_type="design_proposal",
        title=f"Design proposal: {report['title']}",
        body=decision_log_body_from_report(report),
    )
    return int(record["id"])


@router.get("/reports/placeholder")
def report_placeholder() -> Dict[str, str]:
    return {
        "title": "Patent-to-SAR MVP Report",
        "markdown": (
            "# Patent-to-SAR MVP Report\n\n"
            "Upload CSV/SDF compounds or patent PDFs with text-encoded SMILES to review descriptors, "
            "scaffold-like similarity clusters, SAR trends, analog design proposals, and selected compound exports.\n\n"
            "PDF extraction currently handles SMILES present in selectable PDF text. Image-only chemical drawings "
            "need OCR or structure-image extraction before import."
        ),
    }
