from __future__ import annotations

import gzip
import bz2
from pathlib import Path
from typing import Any

import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem

from app.chem.descriptors import calculate_descriptors, canonical_smiles, mol_from_smiles


SMILES_COLUMNS = ("smiles", "SMILES", "canonical_smiles", "Canonical SMILES", "structure")
NAME_COLUMNS = ("name", "Name", "compound_name", "Compound Name", "compound_id", "Compound ID", "ID", "id")
VENDOR_COLUMNS = ("vendor", "Vendor", "supplier", "Supplier", "source", "Source")
CATALOG_COLUMNS = ("catalog_number", "Catalog Number", "catalog_id", "Catalog ID", "vendor_id", "Vendor ID", "sku", "SKU")


def parse_commercial_catalog(path: Path, source_filename: str) -> tuple[list[dict[str, Any]], int]:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    suffix = suffixes[-1] if suffixes else ""
    inner_suffix = suffixes[-2] if suffix == ".gz" and len(suffixes) > 1 else suffix
    if suffix == ".csv":
        return _parse_commercial_csv(path, source_filename)
    if suffix == ".sdf":
        return _parse_commercial_sdf(path, source_filename)
    if inner_suffix in {".cxsmiles", ".smi", ".smiles", ".txt"}:
        return _parse_enamine_real_smiles(path, source_filename, compression=suffix if suffix in {".gz", ".bz2"} else None)
    raise ValueError("Commercial catalog upload must be CSV, SDF, SMILES, CXSMILES, TXT, or compressed SMILES/CXSMILES.")


def find_similar_commercial_analogs(
    target_smiles: str,
    compounds: list[dict[str, Any]],
    min_similarity: float = 0.45,
    limit: int = 20,
) -> dict[str, Any]:
    target_mol = mol_from_smiles(target_smiles)
    if target_mol is None:
        raise ValueError("Target SMILES is invalid.")
    target_fp = _fingerprint(target_mol)
    target_descriptors = calculate_descriptors(target_mol)

    hits = []
    for compound in compounds:
        mol = mol_from_smiles(compound.get("smiles", ""))
        if mol is None:
            continue
        similarity = float(DataStructs.TanimotoSimilarity(target_fp, _fingerprint(mol)))
        if similarity < min_similarity:
            continue
        descriptor_deltas = _descriptor_deltas(target_descriptors, compound)
        hits.append(
            {
                "compound_id": int(compound["id"]),
                "catalog_id": compound["catalog_id"],
                "vendor": compound.get("vendor"),
                "catalog_number": compound.get("catalog_number"),
                "name": compound.get("name"),
                "smiles": compound["smiles"],
                "similarity": round(similarity, 3),
                "availability": _availability_label(compound),
                "properties": {
                    "mol_weight": compound.get("mol_weight"),
                    "logp": compound.get("logp"),
                    "tpsa": compound.get("tpsa"),
                    "hbd": compound.get("hbd"),
                    "hba": compound.get("hba"),
                    "rotatable_bonds": compound.get("rotatable_bonds"),
                },
                "descriptor_deltas": descriptor_deltas,
                "rationale": _hit_rationale(similarity, descriptor_deltas, compound),
            }
        )

    hits.sort(key=lambda item: (item["similarity"], -abs(float(item["descriptor_deltas"].get("mol_weight") or 0))), reverse=True)
    return {
        "target_smiles": canonical_smiles(target_mol),
        "searched_count": len(compounds),
        "min_similarity": min_similarity,
        "hits": hits[: max(1, min(limit, 100))],
        "metadata": {
            "fingerprint": "RDKit Morgan radius 2, 2048 bits",
            "method": "Commercial catalog analog search by Tanimoto similarity to the selected design.",
        },
    }


def _parse_commercial_csv(path: Path, source_filename: str) -> tuple[list[dict[str, Any]], int]:
    df = pd.read_csv(path)
    smiles_column = _find_column(df.columns, SMILES_COLUMNS)
    if smiles_column is None:
        raise ValueError("Commercial catalog CSV must include a SMILES column.")

    name_column = _find_column(df.columns, NAME_COLUMNS)
    vendor_column = _find_column(df.columns, VENDOR_COLUMNS)
    catalog_column = _find_column(df.columns, CATALOG_COLUMNS)
    records = []
    skipped = 0
    seen = set()
    for _, row in df.iterrows():
        mol = mol_from_smiles(row.get(smiles_column, ""))
        if mol is None:
            skipped += 1
            continue
        smiles = canonical_smiles(mol)
        if smiles in seen:
            skipped += 1
            continue
        seen.add(smiles)
        properties = {
            str(column): _clean_value(row[column])
            for column in df.columns
            if column != smiles_column and pd.notna(row[column])
        }
        properties["source_filename"] = source_filename
        records.append(
            {
                "vendor": _clean_text(row.get(vendor_column)) if vendor_column else None,
                "catalog_number": _clean_text(row.get(catalog_column)) if catalog_column else None,
                "name": _clean_text(row.get(name_column)) if name_column else None,
                "smiles": smiles,
                "properties": properties,
                **calculate_descriptors(mol),
            }
        )
    return records, skipped


def _parse_commercial_sdf(path: Path, source_filename: str) -> tuple[list[dict[str, Any]], int]:
    supplier = Chem.SDMolSupplier(str(path), removeHs=False)
    records = []
    skipped = 0
    seen = set()
    for mol in supplier:
        if mol is None:
            skipped += 1
            continue
        smiles = canonical_smiles(mol)
        if smiles in seen:
            skipped += 1
            continue
        seen.add(smiles)
        props = {name: mol.GetProp(name) for name in mol.GetPropNames()}
        records.append(
            {
                "vendor": _first_property(props, VENDOR_COLUMNS),
                "catalog_number": _first_property(props, CATALOG_COLUMNS),
                "name": mol.GetProp("_Name") if mol.HasProp("_Name") else _first_property(props, NAME_COLUMNS),
                "smiles": smiles,
                "properties": {**props, "source_filename": source_filename},
                **calculate_descriptors(mol),
            }
        )
    return records, skipped


def _parse_enamine_real_smiles(path: Path, source_filename: str, compression: str | None = None) -> tuple[list[dict[str, Any]], int]:
    if compression == ".gz":
        opener = gzip.open
    elif compression == ".bz2":
        opener = bz2.open
    else:
        opener = open
    records = []
    skipped = 0
    seen = set()
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parsed = _parse_smiles_line(stripped)
            if parsed is None:
                skipped += 1
                continue
            smiles_token, catalog_number, name = parsed
            mol = mol_from_smiles(smiles_token)
            if mol is None:
                skipped += 1
                continue
            smiles = canonical_smiles(mol)
            if smiles in seen:
                skipped += 1
                continue
            seen.add(smiles)
            properties = {
                "source_filename": source_filename,
                "source_line": line_number,
                "commercial_database": "Enamine REAL",
                "raw_catalog_line": stripped[:500],
            }
            records.append(
                {
                    "vendor": "Enamine REAL",
                    "catalog_number": catalog_number,
                    "name": name or catalog_number,
                    "smiles": smiles,
                    "properties": properties,
                    **calculate_descriptors(mol),
                }
            )
    return records, skipped


def _parse_smiles_line(line: str) -> tuple[str, str | None, str | None] | None:
    if "\t" in line:
        parts = [part.strip() for part in line.split("\t") if part.strip()]
    else:
        parts = line.split()
    if not parts:
        return None

    smiles_token = parts[0]
    if smiles_token.upper() in {"SMILES", "CXSMILES"}:
        return None
    catalog_number = None
    name = None
    for part in parts[1:]:
        if part.startswith("|") and part.endswith("|"):
            continue
        if catalog_number is None:
            catalog_number = part
        elif name is None:
            name = part
            break
    return smiles_token, catalog_number, name


def _fingerprint(mol: Chem.Mol):
    return AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)


def _descriptor_deltas(target: dict[str, Any], compound: dict[str, Any]) -> dict[str, float | None]:
    deltas = {}
    for key in ("mol_weight", "logp", "tpsa", "hbd", "hba", "rotatable_bonds"):
        if target.get(key) is None or compound.get(key) is None:
            deltas[key] = None
        else:
            deltas[key] = round(float(compound[key]) - float(target[key]), 3)
    return deltas


def _availability_label(compound: dict[str, Any]) -> str:
    vendor = compound.get("vendor")
    catalog_number = compound.get("catalog_number")
    if vendor and catalog_number:
        return f"{vendor} · {catalog_number}"
    return str(vendor or catalog_number or "Commercial catalog hit")


def _hit_rationale(similarity: float, deltas: dict[str, Any], compound: dict[str, Any]) -> str:
    notes = [f"{similarity:.2f} Morgan similarity to the selected design."]
    if deltas.get("logp") is not None:
        notes.append(f"LogP delta {float(deltas['logp']):+.2f}.")
    if deltas.get("mol_weight") is not None:
        notes.append(f"MW delta {float(deltas['mol_weight']):+.1f}.")
    if compound.get("vendor") or compound.get("catalog_number"):
        notes.append("Vendor identifiers are present for procurement follow-up.")
    return " ".join(notes)


def _find_column(columns, candidates: tuple[str, ...]) -> str | None:
    exact = {str(column): str(column) for column in columns}
    lowered = {str(column).lower(): str(column) for column in columns}
    for candidate in candidates:
        if candidate in exact:
            return exact[candidate]
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def _first_property(properties: dict[str, Any], candidates: tuple[str, ...]) -> str | None:
    lowered = {key.lower(): value for key, value in properties.items()}
    for candidate in candidates:
        if candidate in properties:
            return _clean_text(properties[candidate])
        if candidate.lower() in lowered:
            return _clean_text(lowered[candidate.lower()])
    return None


def _clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value
