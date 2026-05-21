from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
from rdkit import Chem, RDLogger

from app.chem.descriptors import calculate_descriptors, canonical_smiles, mol_from_smiles


RDLogger.DisableLog("rdApp.error")

SMILES_COLUMNS = ("smiles", "SMILES", "canonical_smiles", "Canonical SMILES", "structure")
NAME_COLUMNS = ("name", "Name", "compound_id", "Compound ID", "ID", "id")
SMILES_LABEL_RE = re.compile(
    r"(?:SMILES|Canonical\s+SMILES|Structure)\s*[:=]\s*(?P<smiles>[A-Za-z0-9@+\-\[\]\(\)\\/%=#$.:]+)",
    re.IGNORECASE,
)
COMPOUND_LABEL_RE = re.compile(r"(?:compound|example)\s+([A-Za-z0-9\-_.]+)", re.IGNORECASE)
SMILES_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9@+\-\[\]\(\)\\/%=#$.:])([A-Za-z0-9@+\-\[\]\(\)\\/%=#$.:]{4,})(?![A-Za-z0-9@+\-\[\]\(\)\\/%=#$.:])")
ORGANIC_ATOM_RE = re.compile(r"Br|Cl|Si|Na|Li|Mg|Al|Ca|[BCNOPSFIbcnops]")


def parse_upload_file(path: Path, source_filename: str, upload_id: str) -> tuple[list[dict[str, Any]], int]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return parse_csv(path, source_filename, upload_id)
    if suffix == ".sdf":
        return parse_sdf(path, source_filename, upload_id)
    if suffix == ".pdf":
        return parse_patent_pdf(path, source_filename, upload_id)
    raise ValueError("Only CSV, SDF, and patent PDF files are supported.")


def parse_csv(path: Path, source_filename: str, upload_id: str) -> tuple[list[dict[str, Any]], int]:
    df = pd.read_csv(path)
    smiles_column = _find_column(df.columns, SMILES_COLUMNS)
    if smiles_column is None:
        raise ValueError("CSV must include a SMILES column.")

    name_column = _find_column(df.columns, NAME_COLUMNS)
    records: list[dict[str, Any]] = []
    skipped = 0

    for _, row in df.iterrows():
        mol = mol_from_smiles(row.get(smiles_column, ""))
        if mol is None:
            skipped += 1
            continue

        properties = {
            str(column): _clean_value(row[column])
            for column in df.columns
            if column != smiles_column and pd.notna(row[column])
        }
        name = _clean_value(row[name_column]) if name_column else None
        records.append(_build_record(upload_id, source_filename, mol, name, properties))

    return records, skipped


def parse_sdf(path: Path, source_filename: str, upload_id: str) -> tuple[list[dict[str, Any]], int]:
    supplier = Chem.SDMolSupplier(str(path), removeHs=False)
    records: list[dict[str, Any]] = []
    skipped = 0

    for mol in supplier:
        if mol is None:
            skipped += 1
            continue

        properties = {name: mol.GetProp(name) for name in mol.GetPropNames()}
        name = mol.GetProp("_Name") if mol.HasProp("_Name") else properties.get("ID")
        records.append(_build_record(upload_id, source_filename, mol, name, properties))

    return records, skipped


def parse_patent_pdf(path: Path, source_filename: str, upload_id: str) -> tuple[list[dict[str, Any]], int]:
    pages = _extract_pdf_pages(path)
    if not any(text.strip() for _, text in pages):
        raise ValueError(
            "Could not extract text from this PDF. Image-only patent PDFs need OCR or structure-image extraction, "
            "which is not available in this intake path yet."
        )

    records: list[dict[str, Any]] = []
    skipped = 0
    seen_smiles: set[str] = set()

    for page_number, text in pages:
        for candidate in _smiles_candidates(text):
            mol = mol_from_smiles(candidate["smiles"])
            if mol is None:
                skipped += 1
                continue

            canonical = canonical_smiles(mol)
            if canonical in seen_smiles:
                skipped += 1
                continue
            seen_smiles.add(canonical)

            name = candidate.get("name") or f"PDF-p{page_number}-{len(records) + 1}"
            properties = {
                "pdf_page": page_number,
                "extraction_method": candidate["method"],
                "source_snippet": candidate["snippet"],
            }
            records.append(_build_record(upload_id, source_filename, mol, name, properties))

    if not records:
        raise ValueError(
            "No valid text-encoded SMILES were found in this patent PDF. If the compounds are only shown as drawings, "
            "use CSV/SDF export from the patent workflow or add OCR/structure-image extraction."
        )

    return records, skipped


def _build_record(
    upload_id: str,
    source_filename: str,
    mol: Chem.Mol,
    name: Any,
    properties: dict[str, Any],
) -> dict[str, Any]:
    return {
        "upload_id": upload_id,
        "name": str(name) if name not in (None, "") else None,
        "smiles": canonical_smiles(mol),
        "source_filename": source_filename,
        "properties": properties,
        **calculate_descriptors(mol),
    }


def _extract_pdf_pages(path: Path) -> list[tuple[int, str]]:
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError as exc:
            raise ValueError("PDF extraction requires pypdf. Install backend requirements and retry.") from exc

    reader = PdfReader(str(path))
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append((index, _normalize_pdf_text(text)))
    return pages


def _normalize_pdf_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"-\s*\n\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _smiles_candidates(text: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()

    for match in SMILES_LABEL_RE.finditer(text):
        smiles = _clean_smiles_token(match.group("smiles"))
        if smiles and smiles not in seen:
            seen.add(smiles)
            candidates.append(
                {
                    "smiles": smiles,
                    "name": _nearby_compound_label(text, match.start()),
                    "method": "labeled_smiles",
                    "snippet": _snippet(text, match.start(), match.end()),
                }
            )

    for match in SMILES_TOKEN_RE.finditer(text):
        smiles = _clean_smiles_token(match.group(1))
        if not smiles or smiles in seen or not _looks_like_smiles(smiles):
            continue
        seen.add(smiles)
        candidates.append(
            {
                "smiles": smiles,
                "name": _nearby_compound_label(text, match.start()),
                "method": "text_smiles_candidate",
                "snippet": _snippet(text, match.start(), match.end()),
            }
        )

    return candidates


def _clean_smiles_token(token: str) -> str:
    return token.strip().strip(".,;:)]}>\"'")


def _looks_like_smiles(token: str) -> bool:
    if len(token) < 4 or len(token) > 250:
        return False
    if re.fullmatch(r"[A-Za-z]{1,5}\d+(?:\.\d+)?", token):
        return False
    if not ORGANIC_ATOM_RE.search(token):
        return False
    if token.lower().startswith(("http", "www", "claim", "table", "figure", "example")):
        return False
    if not re.search(r"[=#\[\]\(\)@+\-/\\0-9]|Br|Cl|[cnops]", token):
        return False
    if re.search(r"[A-Z][a-z]{2,}", token):
        return False
    return True


def _nearby_compound_label(text: str, offset: int) -> str | None:
    window = text[max(0, offset - 120) : offset]
    matches = list(COMPOUND_LABEL_RE.finditer(window))
    if not matches:
        return None
    return matches[-1].group(0).strip()


def _snippet(text: str, start: int, end: int) -> str:
    return text[max(0, start - 90) : min(len(text), end + 90)].strip()


def _find_column(columns: pd.Index, candidates: tuple[str, ...]) -> str | None:
    normalized = {str(column).strip().lower(): str(column) for column in columns}
    for candidate in candidates:
        match = normalized.get(candidate.lower())
        if match:
            return match
    return None


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value
