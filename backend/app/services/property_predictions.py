from __future__ import annotations

import math
from typing import Any

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Lipinski, QED, rdMolDescriptors


def predict_property_plugins(
    smiles: str,
    descriptors: dict[str, Any] | None = None,
    alerts: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Run lightweight open-source RDKit property prediction plugins.

    These are intentionally transparent heuristic predictors rather than opaque
    trained models. They are useful for prioritization and triage, not final
    ADMET calls.
    """

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {
            "source": "RDKit open-source descriptors and filter catalogs",
            "overall_level": "risk",
            "plugins": [
                {
                    "id": "structure_validity",
                    "name": "Structure validity",
                    "family": "structure",
                    "level": "risk",
                    "score": 0.0,
                    "value": "invalid",
                    "unit": None,
                    "rationale": "RDKit could not parse this SMILES.",
                    "evidence": [],
                }
            ],
        }

    descriptors = descriptors or _descriptor_snapshot(mol)
    alerts = alerts or []
    plugins = [
        _solubility_plugin(mol, descriptors),
        _permeability_plugin(mol, descriptors),
        _clearance_risk_plugin(mol, descriptors),
        _herg_risk_plugin(mol, descriptors),
        _qed_plugin(mol),
        _pains_reactive_plugin(mol, alerts),
    ]
    return {
        "source": "RDKit open-source descriptors, QED, SMARTS, and FilterCatalog",
        "overall_level": _overall_level(plugins),
        "plugins": plugins,
    }


def _descriptor_snapshot(mol: Chem.Mol) -> dict[str, Any]:
    return {
        "mol_weight": float(Descriptors.MolWt(mol)),
        "logp": float(Crippen.MolLogP(mol)),
        "hbd": int(Lipinski.NumHDonors(mol)),
        "hba": int(Lipinski.NumHAcceptors(mol)),
        "tpsa": float(rdMolDescriptors.CalcTPSA(mol)),
        "rotatable_bonds": int(Lipinski.NumRotatableBonds(mol)),
    }


def _solubility_plugin(mol: Chem.Mol, descriptors: dict[str, Any]) -> dict[str, Any]:
    logp = float(descriptors.get("logp") or Crippen.MolLogP(mol))
    mw = float(descriptors.get("mol_weight") or Descriptors.MolWt(mol))
    rotors = float(descriptors.get("rotatable_bonds") or Lipinski.NumRotatableBonds(mol))
    aromatic_atoms = sum(1 for atom in mol.GetAtoms() if atom.GetIsAromatic())
    heavy_atoms = max(1, mol.GetNumHeavyAtoms())
    aromatic_proportion = aromatic_atoms / heavy_atoms
    log_s = 0.16 - (0.63 * logp) - (0.0062 * mw) + (0.066 * rotors) - (0.74 * aromatic_proportion)
    level = "favorable" if log_s >= -4.0 else "caution" if log_s >= -5.5 else "risk"
    score = _clip01((log_s + 7.0) / 5.0)
    return {
        "id": "rdkit_esol_proxy",
        "name": "Solubility proxy",
        "family": "solubility",
        "level": level,
        "score": round(score, 2),
        "value": round(log_s, 2),
        "unit": "cLogS",
        "rationale": "ESOL-style RDKit descriptor heuristic using LogP, MW, rotatable bonds, and aromatic proportion.",
        "evidence": [f"LogP {logp:.2f}", f"MW {mw:.1f}", f"aromatic proportion {aromatic_proportion:.2f}"],
    }


def _permeability_plugin(mol: Chem.Mol, descriptors: dict[str, Any]) -> dict[str, Any]:
    tpsa = float(descriptors.get("tpsa") or rdMolDescriptors.CalcTPSA(mol))
    hbd = int(descriptors.get("hbd") or Lipinski.NumHDonors(mol))
    rotors = int(descriptors.get("rotatable_bonds") or Lipinski.NumRotatableBonds(mol))
    logp = float(descriptors.get("logp") or Crippen.MolLogP(mol))
    penalty = max(0.0, (tpsa - 90.0) / 70.0) + max(0.0, (hbd - 2) * 0.2) + max(0.0, (rotors - 8) * 0.08)
    if logp < 0.0:
        penalty += min(0.4, abs(logp) * 0.12)
    if logp > 5.0:
        penalty += min(0.45, (logp - 5.0) * 0.18)
    score = _clip01(1.0 - penalty)
    level = "favorable" if score >= 0.68 else "caution" if score >= 0.42 else "risk"
    return {
        "id": "rdkit_passive_permeability_proxy",
        "name": "Permeability proxy",
        "family": "permeability",
        "level": level,
        "score": round(score, 2),
        "value": round(score * 100),
        "unit": "proxy score",
        "rationale": "Passive permeability proxy from TPSA, HBD, rotatable bonds, and LogP comfort range.",
        "evidence": [f"TPSA {tpsa:.1f}", f"HBD {hbd}", f"RotB {rotors}", f"LogP {logp:.2f}"],
    }


def _clearance_risk_plugin(mol: Chem.Mol, descriptors: dict[str, Any]) -> dict[str, Any]:
    logp = float(descriptors.get("logp") or Crippen.MolLogP(mol))
    aromatic_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
    hetero_atoms = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() not in {1, 6})
    soft_spot_pattern = Chem.MolFromSmarts("[cX3][CH3]")
    soft_spots = len(mol.GetSubstructMatches(soft_spot_pattern)) if soft_spot_pattern is not None else 0
    risk = 0.18 + max(0.0, (logp - 2.5) * 0.16) + aromatic_rings * 0.08 + soft_spots * 0.12 - min(0.22, hetero_atoms * 0.025)
    risk = _clip01(risk)
    level = "favorable" if risk <= 0.34 else "caution" if risk <= 0.62 else "risk"
    return {
        "id": "rdkit_clearance_risk_proxy",
        "name": "Clearance risk",
        "family": "metabolism",
        "level": level,
        "score": round(1.0 - risk, 2),
        "value": round(risk * 100),
        "unit": "risk index",
        "rationale": "Microsomal-clearance-like risk proxy from lipophilicity, aromatic ring count, hetero atoms, and aryl methyl soft spots.",
        "evidence": [f"LogP {logp:.2f}", f"aromatic rings {aromatic_rings}", f"aryl methyl soft spots {soft_spots}", f"hetero atoms {hetero_atoms}"],
    }


def _herg_risk_plugin(mol: Chem.Mol, descriptors: dict[str, Any]) -> dict[str, Any]:
    logp = float(descriptors.get("logp") or Crippen.MolLogP(mol))
    mw = float(descriptors.get("mol_weight") or Descriptors.MolWt(mol))
    basic_amine_pattern = Chem.MolFromSmarts("[NX3;H0,H1,H2;!$(NC=O)]")
    basic_amine = bool(basic_amine_pattern is not None and mol.HasSubstructMatch(basic_amine_pattern))
    aromatic_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
    risk = 0.12 + max(0.0, (logp - 3.0) * 0.16) + max(0.0, (mw - 420.0) / 520.0) + aromatic_rings * 0.05
    if basic_amine:
        risk += 0.25
    risk = _clip01(risk)
    level = "favorable" if risk <= 0.32 else "caution" if risk <= 0.58 else "risk"
    return {
        "id": "rdkit_herg_liability_proxy",
        "name": "hERG liability proxy",
        "family": "safety",
        "level": level,
        "score": round(1.0 - risk, 2),
        "value": round(risk * 100),
        "unit": "risk index",
        "rationale": "Rule-based hERG liability proxy from lipophilicity, size, aromaticity, and basic amine pattern.",
        "evidence": [f"basic amine {'yes' if basic_amine else 'no'}", f"LogP {logp:.2f}", f"MW {mw:.1f}", f"aromatic rings {aromatic_rings}"],
    }


def _qed_plugin(mol: Chem.Mol) -> dict[str, Any]:
    qed = float(QED.qed(mol))
    level = "favorable" if qed >= 0.55 else "caution" if qed >= 0.35 else "risk"
    return {
        "id": "rdkit_qed",
        "name": "Drug-likeness",
        "family": "developability",
        "level": level,
        "score": round(qed, 2),
        "value": round(qed, 2),
        "unit": "QED",
        "rationale": "RDKit QED estimate of oral small-molecule drug-likeness.",
        "evidence": [],
    }


def _pains_reactive_plugin(mol: Chem.Mol, alerts: list[dict[str, str]]) -> dict[str, Any]:
    pains = [alert for alert in alerts if alert.get("field") == "pains"]
    reactive = [alert for alert in alerts if alert.get("severity") in {"medium", "high"} and alert.get("field") != "pains"]
    issue_count = len(pains) + len(reactive)
    level = "favorable" if issue_count == 0 else "caution" if issue_count <= 2 else "risk"
    score = 1.0 if issue_count == 0 else 0.62 if issue_count <= 2 else 0.25
    evidence = [alert["message"] for alert in [*pains, *reactive][:4] if alert.get("message")]
    return {
        "id": "rdkit_pains_reactive_filters",
        "name": "PAINS/reactive filters",
        "family": "liability",
        "level": level,
        "score": score,
        "value": issue_count,
        "unit": "alerts",
        "rationale": "RDKit FilterCatalog PAINS plus project SMARTS filters for reactive or unstable motifs.",
        "evidence": evidence or ["No PAINS or high-risk reactive alert from the current filter set."],
    }


def _overall_level(plugins: list[dict[str, Any]]) -> str:
    levels = [plugin["level"] for plugin in plugins]
    if "risk" in levels:
        return "risk"
    if "caution" in levels:
        return "caution"
    return "favorable"


def _clip01(value: float) -> float:
    if math.isnan(value):
        return 0.0
    return max(0.0, min(1.0, value))
