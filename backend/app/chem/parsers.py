from __future__ import annotations

import io
import re
import shutil
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
    records, skipped, seen_smiles = _records_from_pdf_pages(pages, upload_id, source_filename)
    if records:
        return records, skipped

    ocr_pages, ocr_note = _extract_pdf_pages_with_ocr(path)
    if ocr_pages:
        ocr_records, ocr_skipped, _ = _records_from_pdf_pages(
            ocr_pages,
            upload_id,
            source_filename,
            seen_smiles=seen_smiles,
            method_prefix="ocr_",
        )
        records.extend(ocr_records)
        skipped += ocr_skipped
        if records:
            return records, skipped

    if not records:
        if not any(text.strip() for _, text in pages):
            detail = (
                "Could not extract selectable text from this PDF. "
                f"{ocr_note} "
                "If the compounds are only chemical drawings without text-encoded SMILES, use CSV/SDF export or a "
                "structure-image extraction tool."
            )
            raise ValueError(detail.strip())
        raise ValueError(
            "No valid text-encoded SMILES were found in this patent PDF. "
            f"{ocr_note} "
            "If the compounds are only shown as drawings, use CSV/SDF export or a structure-image extraction tool."
        )

    return records, skipped


def _records_from_pdf_pages(
    pages: list[tuple[int, str]],
    upload_id: str,
    source_filename: str,
    seen_smiles: set[str] | None = None,
    method_prefix: str = "",
) -> tuple[list[dict[str, Any]], int, set[str]]:
    records: list[dict[str, Any]] = []
    skipped = 0
    seen_smiles = seen_smiles or set()

    for page_number, text in pages:
        for candidate in _smiles_candidates(text):
            mol = None
            parsed_smiles = candidate["smiles"]
            for smiles_variant in _smiles_candidate_variants(candidate["smiles"]):
                mol = mol_from_smiles(smiles_variant)
                if mol is not None:
                    parsed_smiles = smiles_variant
                    break
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
                "extraction_method": f"{method_prefix}{candidate['method']}",
                "source_snippet": candidate["snippet"],
            }
            if parsed_smiles != candidate["smiles"]:
                properties["ocr_corrected_smiles_token"] = candidate["smiles"]
            records.append(_build_record(upload_id, source_filename, mol, name, properties))

    return records, skipped, seen_smiles


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


def _extract_pdf_pages_with_ocr(path: Path) -> tuple[list[tuple[int, str]], str]:
    if shutil.which("tesseract") is None:
        return [], "OCR fallback is unavailable because the tesseract executable is not installed."

    try:
        import fitz  # type: ignore
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError as exc:
        return [], f"OCR fallback is unavailable because {exc.name or 'an OCR dependency'} is not installed."

    pages: list[tuple[int, str]] = []
    try:
        document = fitz.open(str(path))
    except Exception as exc:
        return [], f"OCR fallback could not open this PDF: {exc}."

    try:
        for index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            text = pytesseract.image_to_string(image, config="--psm 6")
            pages.append((index, _normalize_pdf_text(text)))
    except Exception as exc:
        return [], f"OCR fallback failed while reading page images: {exc}."
    finally:
        document.close()

    if not any(text.strip() for _, text in pages):
        return [], "OCR fallback ran, but no text was recognized from the page images."
    return pages, "OCR fallback ran on rendered page images."


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


def _smiles_candidate_variants(smiles: str) -> list[str]:
    variants = [smiles]
    ocr_ring_digit_variant = re.sub(r"(?<=[cnops])i(?=[cnops])", "1", smiles)
    ocr_ring_digit_variant = re.sub(r"(?<=[cnops])I(?=[cnops])", "1", ocr_ring_digit_variant)
    if ocr_ring_digit_variant != smiles:
        variants.append(ocr_ring_digit_variant)
    return variants


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
