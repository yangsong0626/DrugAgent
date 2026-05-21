from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors


def mol_from_smiles(smiles: str) -> Chem.Mol | None:
    mol = Chem.MolFromSmiles(str(smiles).strip())
    if mol is None:
        return None
    Chem.SanitizeMol(mol)
    return mol


def canonical_smiles(mol: Chem.Mol) -> str:
    return Chem.MolToSmiles(mol, canonical=True)


def calculate_descriptors(mol: Chem.Mol) -> dict[str, float | int]:
    return {
        "mol_weight": round(float(Descriptors.MolWt(mol)), 3),
        "logp": round(float(Crippen.MolLogP(mol)), 3),
        "hbd": int(Lipinski.NumHDonors(mol)),
        "hba": int(Lipinski.NumHAcceptors(mol)),
        "tpsa": round(float(rdMolDescriptors.CalcTPSA(mol)), 3),
        "rotatable_bonds": int(Lipinski.NumRotatableBonds(mol)),
    }
