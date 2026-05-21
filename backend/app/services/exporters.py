from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd
from rdkit import Chem


EXPORT_COLUMNS = [
    "id",
    "name",
    "smiles",
    "source_filename",
    "mol_weight",
    "logp",
    "hbd",
    "hba",
    "tpsa",
    "rotatable_bonds",
    "cluster_id",
]


def molecules_to_csv(molecules: list[dict[str, Any]]) -> str:
    df = pd.DataFrame([{key: molecule.get(key) for key in EXPORT_COLUMNS} for molecule in molecules])
    return df.to_csv(index=False)


def molecules_to_sdf(molecules: list[dict[str, Any]]) -> str:
    buffer = StringIO()
    writer = Chem.SDWriter(buffer)
    for molecule in molecules:
        mol = Chem.MolFromSmiles(molecule["smiles"])
        if mol is None:
            continue
        mol.SetProp("_Name", str(molecule.get("name") or molecule["id"]))
        for key in EXPORT_COLUMNS:
            value = molecule.get(key)
            if value is not None:
                mol.SetProp(key, str(value))
        writer.write(mol)
    writer.flush()
    return buffer.getvalue()
