from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app.chem.parsers import parse_upload_file
from app.chem.rendering import smiles_to_svg
from app.config import UPLOAD_DIR
from app.models.schemas import (
    ClusterSummary,
    BriefingReportRequest,
    BriefingReportResponse,
    CompoundDesignIdeasResponse,
    ExportRequest,
    MoleculeRecord,
    PortfolioInsightsResponse,
    SarSummaryRequest,
    SarSummaryResponse,
    UploadResponse,
)
from app.services.clustering import cluster_molecules
from app.services.design_ideas import generate_design_ideas
from app.services.exporters import molecules_to_csv, molecules_to_sdf
from app.services.portfolio_insights import generate_portfolio_insights
from app.services.report_generator import build_briefing_docx, build_briefing_report
from app.services.sar_summary import generate_sar_summary
from app.storage.database import create_upload, get_molecule, get_molecules_by_ids, insert_molecules, list_molecules

router = APIRouter(prefix="/api")


@router.post("/uploads/csv-sdf", response_model=UploadResponse)
async def upload_csv_sdf(file: UploadFile = File(...)) -> UploadResponse:
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

    create_upload(upload_id, safe_name)
    ids = insert_molecules(records)
    molecules = list_molecules(upload_id)
    cluster_molecules(molecules)
    molecules_by_id = {molecule["id"]: molecule for molecule in list_molecules(upload_id)}
    ordered_molecules = [MoleculeRecord(**molecules_by_id[molecule_id]) for molecule_id in ids]

    return UploadResponse(
        upload_id=upload_id,
        filename=safe_name,
        imported_count=len(ids),
        skipped_count=skipped_count,
        molecules=ordered_molecules,
    )


@router.get("/molecules", response_model=List[MoleculeRecord])
def get_molecules(upload_id: Optional[str] = Query(default=None)) -> List[MoleculeRecord]:
    return [MoleculeRecord(**molecule) for molecule in list_molecules(upload_id)]


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
    if request.molecule_ids:
        molecules = get_molecules_by_ids(request.molecule_ids)
    elif request.upload_id:
        molecules = list_molecules(request.upload_id)
    else:
        raise HTTPException(status_code=400, detail="Provide upload_id or molecule_ids.")

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


def _molecules_for_report_request(request: BriefingReportRequest) -> List[Dict[str, object]]:
    if request.molecule_ids:
        molecules = get_molecules_by_ids(request.molecule_ids)
    elif request.upload_id:
        molecules = list_molecules(request.upload_id)
    else:
        raise HTTPException(status_code=400, detail="Provide upload_id or molecule_ids.")

    if not molecules:
        raise HTTPException(status_code=400, detail="No compounds found for report generation.")
    return molecules


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
