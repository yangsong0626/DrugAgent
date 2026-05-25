from __future__ import annotations

from typing import Any

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors


EASY_TRANSFORM_HINTS = (
    "fluoride",
    "methoxy",
    "ethoxy",
    "nitrile",
    "phenol",
    "methyl",
    "hydroxyl",
    "aryl",
)


def score_synthetic_feasibility(
    smiles: str,
    source_smiles: str | None = None,
    transform_title: str | None = None,
    descriptor_deltas: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"score": 0.0, "level": "hard", "reason": "Invalid structure.", "features": {}}

    descriptor_deltas = descriptor_deltas or {}
    heavy_atoms = mol.GetNumHeavyAtoms()
    rings = rdMolDescriptors.CalcNumRings(mol)
    hetero_atoms = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() not in {1, 6})
    chiral_centers = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True))
    bertz = float(Descriptors.BertzCT(mol))

    score = 0.92
    score -= max(0, heavy_atoms - 38) * 0.012
    score -= max(0, rings - 4) * 0.045
    score -= max(0, chiral_centers - 1) * 0.08
    score -= max(0.0, bertz - 900.0) / 2200.0
    score -= max(0, hetero_atoms - 10) * 0.01

    if transform_title and any(hint in transform_title.lower() for hint in EASY_TRANSFORM_HINTS):
        score += 0.08
    if source_smiles:
        score += 0.06
    if abs(float(descriptor_deltas.get("mol_weight") or 0)) <= 35:
        score += 0.03

    score = round(max(0.05, min(0.99, score)), 2)
    level = "easy" if score >= 0.74 else "moderate" if score >= 0.48 else "hard"
    reason = _reason(level, source_smiles, transform_title, heavy_atoms, rings, chiral_centers)

    return {
        "score": score,
        "level": level,
        "reason": reason,
        "features": {
            "heavy_atoms": heavy_atoms,
            "rings": rings,
            "hetero_atoms": hetero_atoms,
            "chiral_centers": chiral_centers,
            "bertz_complexity": round(bertz, 1),
        },
    }


def _reason(
    level: str,
    source_smiles: str | None,
    transform_title: str | None,
    heavy_atoms: int,
    rings: int,
    chiral_centers: int,
) -> str:
    source_note = "from an uploaded analog" if source_smiles else "as a standalone proposal"
    transform_note = f" via {transform_title}" if transform_title else ""
    if level == "easy":
        return f"Likely tractable {source_note}{transform_note}; modest size and complexity."
    if level == "moderate":
        return f"Moderate synthesis risk {source_note}{transform_note}; review route before prioritizing."
    return (
        f"Higher synthesis risk {source_note}{transform_note}; "
        f"{heavy_atoms} heavy atoms, {rings} rings, {chiral_centers} chiral center(s)."
    )
