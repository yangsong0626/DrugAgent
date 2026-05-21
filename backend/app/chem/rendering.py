from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import Draw

from app.chem.descriptors import mol_from_smiles


def smiles_to_svg(smiles: str, width: int = 260, height: int = 180) -> str:
    mol = mol_from_smiles(smiles)
    if mol is None:
        return empty_svg(width, height, "Invalid molecule")

    drawer = Draw.MolDraw2DSVG(width, height)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def empty_svg(width: int, height: int, label: str) -> str:
    return (
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\">"
        "<rect width=\"100%\" height=\"100%\" fill=\"#f8fafc\"/>"
        f"<text x=\"50%\" y=\"50%\" dominant-baseline=\"middle\" text-anchor=\"middle\" "
        f"font-family=\"Arial\" font-size=\"14\" fill=\"#64748b\">{label}</text>"
        "</svg>"
    )
