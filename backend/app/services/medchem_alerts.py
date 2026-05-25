from __future__ import annotations

from typing import Any

from rdkit import Chem


REACTIVE_SMARTS = (
    ("acid_chloride", "C(=O)Cl", "high", "Acid chloride is usually too reactive for a final screening compound."),
    ("alkyl_halide", "[CX4][Cl,Br,I]", "medium", "Alkyl halide can be reactive or unstable in biological assays."),
    ("aldehyde", "[CX3H1](=O)[#6]", "medium", "Aldehyde can form covalent adducts and create assay liabilities."),
    ("michael_acceptor", "C=CC=O", "medium", "Michael acceptor motif may be reactive."),
    ("hydrazine", "NN", "medium", "Hydrazine-like motif can carry safety and stability risk."),
    ("peroxide", "OO", "high", "Peroxide motif is a stability and safety concern."),
    ("aniline", "c[NH2]", "low", "Aniline can carry tox or metabolic activation risk depending on context."),
    ("catechol", "c1c([OH])c([OH])cccc1", "medium", "Catechol may create oxidation and conjugation liabilities."),
)


def medchem_alerts(smiles: str, descriptors: dict[str, Any] | None = None) -> list[dict[str, str]]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return [{"field": "structure", "severity": "high", "message": "Invalid SMILES."}]

    alerts: list[dict[str, str]] = []
    descriptors = descriptors or {}
    alerts.extend(_property_alerts(descriptors))
    alerts.extend(_substructure_alerts(mol))
    alerts.extend(_rdkit_filter_alerts(mol))
    return _dedupe_alerts(alerts)


def _property_alerts(descriptors: dict[str, Any]) -> list[dict[str, str]]:
    checks = [
        ("mol_weight", descriptors.get("mol_weight"), 500, 650, "MW"),
        ("logp", descriptors.get("logp"), 5, 7, "LogP"),
        ("hbd", descriptors.get("hbd"), 5, 8, "HBD"),
        ("hba", descriptors.get("hba"), 10, 14, "HBA"),
        ("tpsa", descriptors.get("tpsa"), 140, 180, "TPSA"),
        ("rotatable_bonds", descriptors.get("rotatable_bonds"), 10, 14, "RotB"),
    ]
    alerts = []
    for key, value, medium_cutoff, high_cutoff, label in checks:
        if value is None:
            continue
        numeric = float(value)
        if numeric > high_cutoff:
            alerts.append({"field": key, "severity": "high", "message": f"{label} {numeric:g} is well above the usual oral-drug comfort zone."})
        elif numeric > medium_cutoff:
            alerts.append({"field": key, "severity": "medium", "message": f"{label} {numeric:g} is above the usual oral-drug comfort zone."})
    return alerts


def _substructure_alerts(mol: Chem.Mol) -> list[dict[str, str]]:
    alerts = []
    for name, smarts, severity, message in REACTIVE_SMARTS:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is not None and mol.HasSubstructMatch(pattern):
            alerts.append({"field": name, "severity": severity, "message": message})
    return alerts


def _rdkit_filter_alerts(mol: Chem.Mol) -> list[dict[str, str]]:
    try:
        from rdkit.Chem import FilterCatalog
    except ImportError:
        return []

    params = FilterCatalog.FilterCatalogParams()
    params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
    catalog = FilterCatalog.FilterCatalog(params)
    matches = catalog.GetMatches(mol)
    return [
        {
            "field": "pains",
            "severity": "medium",
            "message": f"PAINS-like alert: {match.GetDescription()}",
        }
        for match in matches[:3]
    ]


def _dedupe_alerts(alerts: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    unique = []
    for alert in alerts:
        key = (alert["field"], alert["message"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(alert)
    return unique
