from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem

from app.chem.descriptors import calculate_descriptors
from app.services.portfolio_insights import generate_portfolio_insights


RDLogger.DisableLog("rdApp.warning")

DESCRIPTOR_KEYS = ("mol_weight", "logp", "hbd", "hba", "tpsa", "rotatable_bonds")


@dataclass(frozen=True)
class AnalogTransform:
    title: str
    reaction_smarts: str
    property_goal: str
    rationale: str
    priority: str = "medium"
    synthetic_note: str = "Matched analog from a conservative single-site substitution."
    max_products: int = 4


TRANSFORMS = (
    AnalogTransform(
        title="Aryl chloride to aryl fluoride",
        reaction_smarts="[c:1][Cl:2]>>[c:1]F",
        property_goal="Lower molecular weight and lipophilicity",
        rationale="Fluorine often preserves an aryl substituent vector while reducing size and LogP versus chlorine.",
        priority="high",
    ),
    AnalogTransform(
        title="Aryl chloride to phenol",
        reaction_smarts="[c:1][Cl:2]>>[c:1][OH]",
        property_goal="Improve polarity and solubility",
        rationale="Phenol replacement is a high-polarity probe for whether the aryl halide vector tolerates hydrogen bonding.",
        priority="medium",
        synthetic_note="Diagnostic polarity analog; watch permeability and phase-II metabolism.",
    ),
    AnalogTransform(
        title="Aryl bromide to aryl fluoride",
        reaction_smarts="[c:1][Br:2]>>[c:1]F",
        property_goal="Lower molecular weight and lipophilicity",
        rationale="Replacing bromine with fluorine can reduce heavy-atom burden while keeping the vector occupied.",
        priority="high",
    ),
    AnalogTransform(
        title="Aryl bromide to phenol",
        reaction_smarts="[c:1][Br:2]>>[c:1][OH]",
        property_goal="Improve polarity and solubility",
        rationale="Phenol replacement can reduce lipophilicity and test whether a polar group is tolerated at the halogen vector.",
        priority="medium",
        synthetic_note="Diagnostic polarity analog; watch permeability and conjugation liability.",
    ),
    AnalogTransform(
        title="Aryl chloride to nitrile",
        reaction_smarts="[c:1][Cl:2]>>[c:1]C#N",
        property_goal="Add polarity without adding donors",
        rationale="A nitrile can lower lipophilicity and add a compact polar acceptor-like vector.",
        priority="medium",
    ),
    AnalogTransform(
        title="Aryl fluoride to nitrile",
        reaction_smarts="[c:1][F:2]>>[c:1]C#N",
        property_goal="Add polarity without adding donors",
        rationale="A nitrile can increase polarity and keep a compact linear vector.",
        priority="medium",
    ),
    AnalogTransform(
        title="Aryl fluoride to phenol",
        reaction_smarts="[c:1][F:2]>>[c:1][OH]",
        property_goal="Improve polarity and solubility",
        rationale="Phenol replacement can expose whether the vector can trade hydrophobic occupancy for polarity.",
        priority="medium",
        synthetic_note="Diagnostic polarity analog; monitor permeability and conjugation liability.",
    ),
    AnalogTransform(
        title="Aryl iodide to aryl fluoride",
        reaction_smarts="[c:1][I:2]>>[c:1]F",
        property_goal="Lower molecular weight and lipophilicity",
        rationale="Fluorine can preserve vector occupancy while removing a large heavy atom.",
        priority="high",
    ),
    AnalogTransform(
        title="Aryl iodide to nitrile",
        reaction_smarts="[c:1][I:2]>>[c:1]C#N",
        property_goal="Add polarity without adding donors",
        rationale="Nitrile replacement can reduce heavy-atom burden while adding a compact polar vector.",
        priority="medium",
    ),
    AnalogTransform(
        title="Ethoxy to methoxy",
        reaction_smarts="[c:1][O:2][CH2:3][CH3:4]>>[c:1][O:2][CH3]",
        property_goal="Reduce size and lipophilicity",
        rationale="Shortening ethoxy to methoxy reduces molecular weight and hydrophobic surface area.",
        priority="high",
    ),
    AnalogTransform(
        title="Ethoxy to phenol",
        reaction_smarts="[c:1][O:2][CH2:3][CH3:4]>>[c:1][OH]",
        property_goal="Improve polarity and reduce size",
        rationale="Removing the ethyl group creates a compact polarity probe at the same oxygen vector.",
        priority="medium",
        synthetic_note="Good solubility probe; watch permeability because this adds a donor.",
    ),
    AnalogTransform(
        title="Ethoxy to fluoromethoxy",
        reaction_smarts="[c:1][O:2][CH2:3][CH3:4]>>[c:1][O:2][CH2]F",
        property_goal="Reduce size while adding polarity",
        rationale="Fluoromethoxy keeps the alkoxy vector but trims carbon count and adds a polar C-F handle.",
        priority="medium",
    ),
    AnalogTransform(
        title="Ethoxy to hydroxyethoxy",
        reaction_smarts="[c:1][O:2][CH2:3][CH3:4]>>[c:1][O:2][CH2][CH2][OH]",
        property_goal="Improve polarity and solubility",
        rationale="A terminal alcohol can improve solubility while preserving an ether-linked vector.",
        priority="medium",
        synthetic_note="Good solubility probe; watch permeability because this adds a donor.",
    ),
    AnalogTransform(
        title="Ethoxy to cyanomethoxy",
        reaction_smarts="[c:1][O:2][CH2:3][CH3:4]>>[c:1][O:2][CH2]C#N",
        property_goal="Improve polarity without adding donors",
        rationale="Cyanomethoxy keeps the ether vector and adds a compact polar handle for solubility and electronics.",
        priority="medium",
    ),
    AnalogTransform(
        title="Ethoxy to difluoromethoxy",
        reaction_smarts="[c:1][O:2][CH2:3][CH3:4]>>[c:1][O:2]C(F)F",
        property_goal="Scan electronics while limiting size",
        rationale="Difluoromethoxy changes electronics and metabolic stability while staying close to the alkoxy vector.",
        priority="low",
    ),
    AnalogTransform(
        title="Ethoxy to carboxymethoxy ester",
        reaction_smarts="[c:1][O:2][CH2:3][CH3:4]>>[c:1][O:2][CH2]C(=O)OC",
        property_goal="Increase polarity for solubility screening",
        rationale="A carboxymethoxy ester is a quick polarity scan that can reveal whether this vector tolerates a larger polar group.",
        priority="low",
        synthetic_note="Exploratory solubility analog; consider acid follow-up if ester is tolerated.",
    ),
    AnalogTransform(
        title="Isopropoxy to ethoxy",
        reaction_smarts="[c:1][O:2][CH:3]([CH3:4])[CH3:5]>>[c:1][O:2][CH2][CH3]",
        property_goal="Reduce size while keeping an alkoxy vector",
        rationale="A smaller alkoxy group can test whether potency needs branching or only vector occupancy.",
        priority="medium",
    ),
    AnalogTransform(
        title="Isopropoxy to methoxy",
        reaction_smarts="[c:1][O:2][CH:3]([CH3:4])[CH3:5]>>[c:1][O:2][CH3]",
        property_goal="Minimize lipophilic bulk",
        rationale="Methoxy is a compact analog that can improve ligand efficiency and solubility pressure.",
        priority="medium",
    ),
    AnalogTransform(
        title="Isopropoxy to phenol",
        reaction_smarts="[c:1][O:2][CH:3]([CH3:4])[CH3:5]>>[c:1][OH]",
        property_goal="Improve polarity and reduce size",
        rationale="Phenol replacement tests whether branched alkoxy bulk is needed or whether polarity is tolerated.",
        priority="medium",
        synthetic_note="Good solubility probe; watch permeability because this adds a donor.",
    ),
    AnalogTransform(
        title="Isopropoxy to fluoromethoxy",
        reaction_smarts="[c:1][O:2][CH:3]([CH3:4])[CH3:5]>>[c:1][O:2][CH2]F",
        property_goal="Reduce size while adding polarity",
        rationale="Fluoromethoxy is a compact polarity-increasing replacement for branched alkoxy bulk.",
        priority="medium",
    ),
    AnalogTransform(
        title="Isopropoxy to cyanomethoxy",
        reaction_smarts="[c:1][O:2][CH:3]([CH3:4])[CH3:5]>>[c:1][O:2][CH2]C#N",
        property_goal="Improve polarity without adding donors",
        rationale="Cyanomethoxy trims branching and adds a compact polar handle.",
        priority="medium",
    ),
    AnalogTransform(
        title="Aryl methyl to fluoro",
        reaction_smarts="[c:1][CH3:2]>>[c:1]F",
        property_goal="Remove metabolic soft spot",
        rationale="Replacing aryl methyl with fluorine can reduce oxidative metabolism while keeping a small substituent.",
        priority="medium",
    ),
    AnalogTransform(
        title="Aryl methyl to hydroxymethyl",
        reaction_smarts="[c:1][CH3:2]>>[c:1][CH2][OH]",
        property_goal="Improve polarity and address metabolic soft spots",
        rationale="Hydroxymethyl replacement probes whether a methyl metabolic soft spot can become a polar tolerated handle.",
        priority="medium",
        synthetic_note="Useful exposure probe; watch for metabolic conjugation.",
    ),
    AnalogTransform(
        title="Aryl methyl to nitrile",
        reaction_smarts="[c:1][CH3:2]>>[c:1]C#N",
        property_goal="Improve polarity without adding donors",
        rationale="Nitrile replacement removes a methyl soft spot and adds a compact polar vector.",
        priority="medium",
    ),
    AnalogTransform(
        title="Methoxy to phenol",
        reaction_smarts="[c:1][O:2][CH3:3]>>[c:1][OH]",
        property_goal="Improve polarity and solubility",
        rationale="Demethylation increases polarity and can reveal whether the methoxy group is a masking group or a binding feature.",
        priority="low",
        synthetic_note="Useful as a diagnostic analog; watch permeability because this adds a donor.",
    ),
    AnalogTransform(
        title="Methoxy to fluoromethoxy",
        reaction_smarts="[c:1][O:2][CH3:3]>>[c:1][O:2][CH2]F",
        property_goal="Scan electronics while adding polarity",
        rationale="Fluoromethoxy keeps the ether vector and changes electronics with modest size increase.",
        priority="low",
    ),
    AnalogTransform(
        title="Methoxy to cyanomethoxy",
        reaction_smarts="[c:1][O:2][CH3:3]>>[c:1][O:2][CH2]C#N",
        property_goal="Improve polarity without adding donors",
        rationale="Cyanomethoxy adds a compact polar handle and tests whether the vector tolerates extra acceptor character.",
        priority="medium",
    ),
    AnalogTransform(
        title="Add aryl hydroxyl scan",
        reaction_smarts="[cH:1]>>[c:1][OH]",
        property_goal="Improve polarity and solubility",
        rationale="A one-position phenol scan can identify solvent-exposed vectors that tolerate polarity.",
        priority="low",
        synthetic_note="Exploratory positional scan; prioritize sites with plausible synthetic access.",
        max_products=6,
    ),
    AnalogTransform(
        title="Add aryl nitrile scan",
        reaction_smarts="[cH:1]>>[c:1]C#N",
        property_goal="Improve polarity without adding donors",
        rationale="A nitrile positional scan adds compact polarity and electronics without donor burden.",
        priority="low",
        synthetic_note="Exploratory positional scan; use if the aryl vector has tractable functionalization chemistry.",
        max_products=6,
    ),
)


def generate_design_ideas(
    molecule: Dict[str, Any],
    related_molecules: List[Dict[str, Any]],
) -> Dict[str, Any]:
    insights = generate_portfolio_insights(related_molecules)
    potency_column = insights.get("detected_potency_column")
    admet_columns = insights.get("detected_admet_columns", [])
    potency_value = _parse_number(_property_value(molecule, potency_column)) if potency_column else None
    same_cluster = [
        other
        for other in related_molecules
        if other.get("id") != molecule.get("id")
        and molecule.get("cluster_id") is not None
        and other.get("cluster_id") == molecule.get("cluster_id")
    ]
    tested_smiles = _canonical_smiles_set(related_molecules)

    analogs = _generated_analogs(molecule, tested_smiles)
    analogs = _rank_analogs(analogs)

    return {
        "molecule_id": int(molecule["id"]),
        "molecule_name": molecule.get("name"),
        "source_smiles": molecule.get("smiles"),
        "potency_column": potency_column,
        "potency_value": potency_value,
        "detected_admet_columns": admet_columns,
        "cluster_compound_count": len(same_cluster) + (1 if molecule.get("cluster_id") is not None else 0),
        "analog_proposals": analogs[:18],
        "ideas": _summary_ideas(molecule, analogs, potency_column),
        "context": {
            "cluster_id": molecule.get("cluster_id"),
            "generated_analog_count": len([analog for analog in analogs if analog["source"] == "generated"]),
            "tested_compound_count": len(tested_smiles),
            "stronger_tested_neighbor_count": len(_stronger_tested_neighbors(same_cluster, potency_column, potency_value)),
            "method": (
                "Conservative RDKit reaction transforms filtered against every uploaded tested compound. "
                "Descriptor deltas are calculated from generated structures, not potency predictions."
            ),
        },
    }


def _generated_analogs(molecule: Dict[str, Any], tested_smiles: set[str]) -> List[Dict[str, Any]]:
    mol = Chem.MolFromSmiles(molecule.get("smiles", ""))
    if mol is None:
        return []

    current_descriptors = _descriptor_snapshot(molecule)
    current_smiles = Chem.MolToSmiles(mol, canonical=True)
    seen = set(tested_smiles)
    seen.add(current_smiles)
    proposals: List[Dict[str, Any]] = []

    for transform in TRANSFORMS:
        reaction = AllChem.ReactionFromSmarts(transform.reaction_smarts)
        accepted_for_transform = 0
        for products in reaction.RunReactants((mol,)):
            if accepted_for_transform >= transform.max_products:
                break
            product = products[0]
            try:
                Chem.SanitizeMol(product)
            except Exception:
                continue

            smiles = Chem.MolToSmiles(product, canonical=True)
            if smiles in seen:
                continue
            seen.add(smiles)

            descriptors = calculate_descriptors(product)
            deltas = _descriptor_deltas(current_descriptors, descriptors)
            if not _has_property_gain(deltas, transform.property_goal):
                continue

            proposals.append(
                {
                    "title": transform.title,
                    "analog_smiles": smiles,
                    "source": "generated",
                    "property_goal": transform.property_goal,
                    "rationale": transform.rationale,
                    "priority": _priority_for_delta(transform.priority, deltas),
                    "synthetic_note": transform.synthetic_note,
                    "predicted_descriptors": descriptors,
                    "descriptor_deltas": deltas,
                    "reference_molecule_id": None,
                    "reference_molecule_name": None,
                }
            )
            accepted_for_transform += 1

    return proposals


def _summary_ideas(
    molecule: Dict[str, Any],
    analogs: List[Dict[str, Any]],
    potency_column: Optional[str],
) -> List[Dict[str, Any]]:
    if analogs:
        return [
            {
                "title": "Make a structure-first analog set",
                "hypothesis": "The proposed structures test property improvements with conservative single-site changes.",
            "rationale": "Prioritize analogs that improve LogP, molecular weight, or ADMET pressure before broad expansion.",
            "priority": "high",
            "suggested_changes": [analog["title"] for analog in analogs[:4]],
            "expected_effect": "Creates a focused make/test list with untested structures and interpretable descriptor shifts.",
        }
    ]

    return [
        {
            "title": "No conservative analog transform matched",
            "hypothesis": "This structure may need scaffold-aware enumeration rather than generic single-site transforms.",
            "rationale": f"Current SMILES: {molecule.get('smiles')}",
            "priority": "medium",
            "suggested_changes": [
                "Add more same-series compounds to reveal productive vectors, while proposals remain filtered against tested structures.",
                "Use the SAR summary to identify a modifiable vector.",
                f"Measure {potency_column} for close analogs." if potency_column else "Add a potency column before expanding the series.",
            ],
            "expected_effect": "Gives the agent enough context to propose makeable analog structures.",
        }
    ]


def _rank_analogs(analogs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def rank_key(analog: Dict[str, Any]) -> tuple[int, float]:
        priority_rank = {"high": 0, "medium": 1, "low": 2}.get(analog["priority"], 3)
        deltas = analog["descriptor_deltas"]
        gain = 0.0
        gain += max(0.0, -float(deltas.get("logp") or 0)) * 10
        gain += max(0.0, -float(deltas.get("mol_weight") or 0)) / 10
        gain += max(0.0, -float(deltas.get("rotatable_bonds") or 0)) * 2
        return (priority_rank, -gain)

    unique: Dict[str, Dict[str, Any]] = {}
    for analog in analogs:
        smiles = analog["analog_smiles"]
        if smiles not in unique or rank_key(analog) < rank_key(unique[smiles]):
            unique[smiles] = analog
    return sorted(unique.values(), key=rank_key)


def _canonical_smiles_set(molecules: List[Dict[str, Any]]) -> set[str]:
    smiles_set = set()
    for molecule in molecules:
        mol = Chem.MolFromSmiles(molecule.get("smiles", ""))
        if mol is not None:
            smiles_set.add(Chem.MolToSmiles(mol, canonical=True))
    return smiles_set


def _stronger_tested_neighbors(
    same_cluster: List[Dict[str, Any]],
    potency_column: Optional[str],
    potency_value: Optional[float],
) -> List[Dict[str, Any]]:
    if not potency_column or potency_value is None:
        return []
    return [
        molecule
        for molecule in same_cluster
        if (neighbor_potency := _parse_number(_property_value(molecule, potency_column))) is not None
        and neighbor_potency < potency_value
    ]


def _descriptor_snapshot(molecule: Dict[str, Any]) -> Dict[str, Optional[float]]:
    return {key: _number(molecule.get(key)) for key in DESCRIPTOR_KEYS}


def _descriptor_deltas(
    current: Dict[str, Optional[float]],
    proposed: Dict[str, Optional[float]],
) -> Dict[str, Optional[float]]:
    deltas: Dict[str, Optional[float]] = {}
    for key in DESCRIPTOR_KEYS:
        before = current.get(key)
        after = proposed.get(key)
        deltas[key] = round(float(after) - float(before), 3) if before is not None and after is not None else None
    return deltas


def _has_property_gain(deltas: Dict[str, Optional[float]], property_goal: str) -> bool:
    normalized = property_goal.lower()
    if "lipophilicity" in normalized and (deltas.get("logp") or 0) < -0.05:
        return True
    if "molecular weight" in normalized and (deltas.get("mol_weight") or 0) < -1:
        return True
    if "size" in normalized and (deltas.get("mol_weight") or 0) < -1:
        return True
    if "polarity" in normalized and (deltas.get("tpsa") or 0) > 0:
        return True
    if "metabolic" in normalized and (deltas.get("mol_weight") or 0) < 5:
        return True
    return any((deltas.get(key) or 0) < 0 for key in ("mol_weight", "logp", "rotatable_bonds"))


def _priority_for_delta(base_priority: str, deltas: Dict[str, Optional[float]]) -> str:
    if (deltas.get("logp") or 0) <= -0.4 or (deltas.get("mol_weight") or 0) <= -25:
        return "high"
    return base_priority


def _property_value(molecule: Dict[str, Any], column: Optional[str]) -> Any:
    if not column:
        return None
    properties = molecule.get("properties", {})
    if column in properties:
        return properties[column]
    lowered = {str(key).lower(): value for key, value in properties.items()}
    return lowered.get(column.lower())


def _parse_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if math.isnan(value):
            return None
        return float(value)
    match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)
