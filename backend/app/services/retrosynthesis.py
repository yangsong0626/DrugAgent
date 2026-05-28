from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem


@dataclass(frozen=True)
class RetroTemplate:
    name: str
    reaction_smarts: str
    disconnection: str
    operation: str
    conditions: str
    rationale: str


RETRO_TEMPLATES = (
    RetroTemplate(
        name="Williamson ether disconnection to phenol and 2-bromoethanol",
        reaction_smarts="[c:1][O:2][CH2:3][CH2:4][OH:5]>>[c:1][OH:2].[Br][CH2:3][CH2:4][OH:5]",
        disconnection="Ar-OCH2",
        operation="Phenol alkylation with a hydroxyethyl electrophile",
        conditions="2-bromoethanol or protected equivalent, base, polar aprotic solvent",
        rationale="RDKit retrosynthetic template disconnects the aryl ether into a reusable phenol intermediate and a hydroxyethyl electrophile.",
    ),
    RetroTemplate(
        name="Williamson ether disconnection to phenol and bromoacetonitrile",
        reaction_smarts="[c:1][O:2][CH2:3][C:4]#[N:5]>>[c:1][OH:2].[Br][CH2:3][C:4]#[N:5]",
        disconnection="Ar-OCH2",
        operation="Phenol alkylation with bromoacetonitrile",
        conditions="bromoacetonitrile, base, EtOH/DMF screen",
        rationale="RDKit retrosynthetic template disconnects cyanomethoxy analogs to phenol plus a compact cyanoalkyl electrophile.",
    ),
    RetroTemplate(
        name="Aryl methyl ether deprotection to phenol",
        reaction_smarts="[c:1][O:2][CH3:3]>>[c:1][OH:2].[CH3:3]I",
        disconnection="Ar-OCH3",
        operation="Methyl ether deprotection to phenol",
        conditions="BBr3 or HBr/AcOH screen, then neutralization",
        rationale="RDKit retrosynthetic template treats the methyl ether as a protected phenol branch point.",
    ),
    RetroTemplate(
        name="Aryl ethyl ether deprotection to phenol",
        reaction_smarts="[c:1][O:2][CH2:3][CH3:4]>>[c:1][OH:2].[I][CH2:3][CH3:4]",
        disconnection="Ar-OEt",
        operation="Ethyl ether deprotection to phenol",
        conditions="BBr3 or HBr/AcOH screen, then neutralization",
        rationale="RDKit retrosynthetic template treats the ethyl ether as a phenol precursor.",
    ),
    RetroTemplate(
        name="Aryl nitrile disconnection from aryl halide",
        reaction_smarts="[c:1][C:2]#[N:3]>>[c:1][Br].[C:2]#[N:3]",
        disconnection="Ar-CN",
        operation="Aryl halide cyanation",
        conditions="Zn(CN)2 or CuCN, Pd/Cu catalyst screen",
        rationale="RDKit retrosynthetic template maps the nitrile analog to an aryl halide precursor plus cyanide source.",
    ),
)


def propose_retrosynthesis_route(
    smiles: str,
    source_smiles: str | None = None,
    transform_title: str | None = None,
    synthetic_feasibility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an explainable, medicinal-chemist-facing route sketch.

    This is not a full route planner. It turns the same conservative transform
    used for analog generation into a plausible disconnection and make/test route
    so chemists can quickly judge whether the proposed design is worth pursuing.
    """

    product_smiles = _canonical(smiles) or smiles
    source = _canonical(source_smiles) if source_smiles else None
    transform = transform_title or "Conservative analog transform"
    feasibility = synthetic_feasibility or {}
    template = _route_template(transform)
    rdkit_plan = _plan_with_rdkit_templates(product_smiles, source, transform)
    if rdkit_plan:
        starting_materials = rdkit_plan["starting_materials"]
        steps = rdkit_plan["steps"]
        route_type = "RDKit open-source retrosynthesis template route"
        summary = rdkit_plan["summary"]
    else:
        starting_materials = _starting_materials(source, template)
        intermediate = _common_intermediate(source, product_smiles, transform)
        steps = [
            {
                "order": 1,
                "title": template["step_title"],
                "operation": template["operation"],
                "disconnection": template["disconnection"],
                "starting_materials": starting_materials,
                "reagent_smiles": [],
                "product_smiles": product_smiles,
                "conditions": template["conditions"],
                "rationale": template["rationale"],
            }
        ]
        if intermediate:
            steps = [
                {
                    "order": 1,
                    "title": "Prepare common phenol intermediate",
                    "operation": "Unmask or access the phenol handle from the matched uploaded alkoxy analog.",
                    "disconnection": "Ar-Oalkyl",
                    "starting_materials": starting_materials,
                    "reagent_smiles": [],
                    "product_smiles": intermediate,
                    "conditions": "Run demethylation/dealkylation, or resynthesize the matched core through the phenol intermediate if direct cleavage is not selective.",
                    "rationale": "A shared phenol intermediate gives the chemist a reusable branch point for this vector.",
                },
                {
                    "order": 2,
                    "title": template["step_title"],
                    "operation": template["operation"],
                    "disconnection": template["disconnection"],
                    "starting_materials": [intermediate],
                    "reagent_smiles": [],
                    "product_smiles": product_smiles,
                    "conditions": template["conditions"],
                    "rationale": template["rationale"],
                },
            ]
        route_type = "one-step analog from uploaded compound" if source else "standalone route sketch"
        summary = template["summary"]

    if template.get("follow_up"):
        steps.append(
            {
                "order": 2,
                "title": template["follow_up"]["title"],
                "operation": template["follow_up"]["operation"],
                "disconnection": template["follow_up"]["disconnection"],
                "starting_materials": [product_smiles],
                "reagent_smiles": [],
                "product_smiles": product_smiles,
                "conditions": template["follow_up"]["conditions"],
                "rationale": template["follow_up"]["rationale"],
            }
        )

    confidence = _confidence(feasibility)
    return {
        "summary": summary,
        "route_type": route_type,
        "confidence": confidence,
        "starting_materials": starting_materials,
        "target_smiles": product_smiles,
        "path_nodes": _path_nodes(source, product_smiles, steps, template),
        "steps": steps,
        "route_risks": _route_risks(template, feasibility),
        "chemist_note": _chemist_note(transform, feasibility, source, used_rdkit=bool(rdkit_plan)),
    }


def _route_template(transform_title: str) -> dict[str, Any]:
    title = transform_title.lower()
    if "to phenol" in title or "hydroxyl" in title or "hydroxy" in title:
        return {
            "summary": "Disconnect the aryl O bond and make the phenol or alcohol analog from the matched uploaded aryl precursor.",
            "step_title": "Install or unmask the hydroxyl handle",
            "operation": "Substitution, demethylation, or late-stage hydroxylation depending on the available precursor.",
            "disconnection": "C-OH",
            "conditions": "Use a demethylation/dealkylation screen for alkoxy precursors, or evaluate SNAr/metal-mediated hydroxylation for activated aryl halides.",
            "rationale": "The design keeps the same vector while testing whether added polarity is tolerated.",
        }
    if "nitrile" in title or "cyanomethoxy" in title:
        return {
            "summary": "Disconnect at the aryl or alkyl nitrile bond and introduce cyanide from the uploaded halide or alcohol-like precursor.",
            "step_title": "Introduce the nitrile vector",
            "operation": "Cyanation or alkylation with a cyanoalkyl building block.",
            "disconnection": "C-CN",
            "conditions": "For aryl halides, screen metal-catalyzed cyanation; for alkoxy analogs, use a haloacetonitrile-type electrophile from the phenol/alcohol precursor.",
            "rationale": "Nitrile installation is a compact polarity scan that is usually compatible with parallel analog synthesis.",
        }
    if "fluoride" in title or "fluoro" in title or "difluoromethoxy" in title:
        return {
            "summary": "Use the uploaded halide/alkoxy analog as the nearest precursor and introduce fluorine or a fluoroalkoxy handle late.",
            "step_title": "Install fluorinated substituent",
            "operation": "Halogen exchange, deoxyfluorination, or fluoroalkylation selected by precursor class.",
            "disconnection": "C-F or O-CF",
            "conditions": "Prioritize commercial fluoro building blocks or late-stage fluorination conditions; confirm regioselectivity on electron-rich aryl systems.",
            "rationale": "Fluorinated analogs often preserve vector occupancy while tuning size, electronics, and metabolic stability.",
        }
    if "methoxy" in title or "ethoxy" in title or "isopropoxy" in title:
        return {
            "summary": "Disconnect the aryl ether and make the analog by alkylating the corresponding phenol intermediate.",
            "step_title": "Form aryl ether analog",
            "operation": "Phenol alkylation or SNAr ether formation.",
            "disconnection": "Ar-Oalkyl",
            "conditions": "Use phenol plus alkyl halide/sulfonate under mild base, or SNAr from an activated aryl halide where appropriate.",
            "rationale": "Alkoxy homologation is a standard parallel synthesis move for size and lipophilicity scans.",
        }
    if "methyl" in title:
        return {
            "summary": "Disconnect the aryl methyl replacement and use a halogenated or boronate precursor for late-stage substituent exchange.",
            "step_title": "Exchange aryl methyl vector",
            "operation": "Cross-coupling, halogenation-functionalization, or benzylic oxidation/replacement.",
            "disconnection": "Ar-substituent",
            "conditions": "Prefer an existing aryl halide/boronate series intermediate; otherwise plan a short resynthesis from the matched core.",
            "rationale": "The route tests whether the methyl vector is a binding feature or a property liability.",
        }
    return {
        "summary": "Use the closest uploaded analog as a matched precursor and apply the single-site design transform late in the sequence.",
        "step_title": "Late-stage matched analog transform",
        "operation": "Single-site functional group interconversion.",
        "disconnection": "Modified SAR vector",
        "conditions": "Choose conditions from the precursor functional group and protect only if the uploaded scaffold contains incompatible groups.",
        "rationale": "Keeping the route close to an uploaded compound preserves interpretability and speeds make/test cycling.",
    }


def _plan_with_rdkit_templates(product_smiles: str, source_smiles: str | None, transform_title: str) -> dict[str, Any] | None:
    product = Chem.MolFromSmiles(product_smiles)
    if product is None:
        return None

    ranked_templates = _rank_retro_templates(transform_title)
    for retro_template in ranked_templates:
        reaction = AllChem.ReactionFromSmarts(retro_template.reaction_smarts)
        precursor_sets = reaction.RunReactants((product,))
        for precursor_set in precursor_sets:
            precursors = _sanitize_precursors(precursor_set)
            if not precursors:
                continue
            core_precursor, reagent_smiles = _split_core_and_reagents(precursors, product_smiles)
            if not core_precursor:
                continue
            starting_materials = [core_precursor, *reagent_smiles]
            steps = []
            if source_smiles and source_smiles != core_precursor:
                steps.append(
                    {
                        "order": 1,
                        "title": "Access RDKit precursor",
                        "operation": "Convert uploaded analog to the retrosynthetic precursor selected by the RDKit template planner.",
                        "disconnection": "precursor access",
                        "starting_materials": [source_smiles],
                        "reagent_smiles": [],
                        "product_smiles": core_precursor,
                        "conditions": "Use dealkylation, functional-group interconversion, or short resynthesis from the matched series intermediate.",
                        "rationale": "This connects the open-source template route to the closest uploaded analog.",
                    }
                )
                starting_materials.insert(0, source_smiles)

            steps.append(
                {
                    "order": len(steps) + 1,
                    "title": retro_template.name,
                    "operation": retro_template.operation,
                    "disconnection": retro_template.disconnection,
                    "starting_materials": [core_precursor],
                    "reagent_smiles": reagent_smiles,
                    "product_smiles": product_smiles,
                    "conditions": retro_template.conditions,
                    "rationale": retro_template.rationale,
                }
            )
            return {
                "summary": (
                    f"Open-source RDKit reaction templates proposed a route by disconnecting {retro_template.disconnection}. "
                    "The displayed scheme is the forward synthesis path assembled from those retrosynthetic precursors."
                ),
                "starting_materials": _dedupe_preserve_order(starting_materials),
                "steps": steps,
            }
    return None


def _rank_retro_templates(transform_title: str) -> list[RetroTemplate]:
    title = transform_title.lower()
    scored = []
    for template in RETRO_TEMPLATES:
        score = 0
        name = template.name.lower()
        if "hydroxyethoxy" in title and "2-bromoethanol" in name:
            score += 10
        if "cyanomethoxy" in title and "bromoacetonitrile" in name:
            score += 10
        if "methoxy" in title and "methyl ether" in name:
            score += 8
        if "ethoxy" in title and "ethyl ether" in name:
            score += 8
        if "nitrile" in title and "nitrile" in name:
            score += 7
        scored.append((score, template))
    return [template for _, template in sorted(scored, key=lambda item: item[0], reverse=True)]


def _sanitize_precursors(precursor_set: tuple[Chem.Mol, ...]) -> list[str]:
    smiles = []
    for precursor in precursor_set:
        try:
            Chem.SanitizeMol(precursor)
        except Exception:
            continue
        canonical = Chem.MolToSmiles(precursor, canonical=True)
        if canonical:
            smiles.append(canonical)
    return _dedupe_preserve_order(smiles)


def _split_core_and_reagents(precursors: list[str], product_smiles: str) -> tuple[str | None, list[str]]:
    if not precursors:
        return None, []
    product_heavy_atoms = _heavy_atom_count(product_smiles)
    core = max(precursors, key=lambda smiles: _heavy_atom_count(smiles))
    if _heavy_atom_count(core) >= product_heavy_atoms:
        return None, []
    reagents = [smiles for smiles in precursors if smiles != core]
    return core, reagents


def _heavy_atom_count(smiles: str) -> int:
    mol = Chem.MolFromSmiles(smiles)
    return mol.GetNumHeavyAtoms() if mol is not None else 0


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _starting_materials(source_smiles: str | None, template: dict[str, Any]) -> list[str]:
    materials = []
    if source_smiles:
        materials.append(source_smiles)
    if template["disconnection"] == "Ar-Oalkyl":
        materials.append("phenol intermediate or activated aryl halide")
    elif template["disconnection"] == "C-CN":
        materials.append("cyanide source or haloacetonitrile building block")
    elif template["disconnection"] == "C-F or O-CF":
        materials.append("fluorinating reagent or fluoroalkyl building block")
    elif template["disconnection"] == "C-OH":
        materials.append("phenol/alcohol precursor or aryl halide")
    else:
        materials.append("matched series intermediate")
    return materials


def _path_nodes(
    source_smiles: str | None,
    product_smiles: str,
    steps: list[dict[str, Any]],
    template: dict[str, Any],
) -> list[dict[str, Any]]:
    nodes = []
    if source_smiles:
        nodes.append(
            {
                "id": "starting-material-1",
                "label": "Uploaded starting material",
                "role": "starting_material",
                "smiles": source_smiles,
                "note": "Closest matched compound already present in the project.",
            }
        )
    else:
        nodes.append(
            {
                "id": "starting-material-1",
                "label": "Matched series intermediate",
                "role": "starting_material",
                "smiles": None,
                "note": "No uploaded source structure was available for this route sketch.",
            }
        )

    for step in steps[:-1]:
        nodes.append(
            {
                "id": f"intermediate-{step['order']}",
                "label": f"Intermediate {step['order']}",
                "role": "intermediate",
                "smiles": step.get("product_smiles"),
                "note": step.get("title") or template["step_title"],
            }
        )

    nodes.append(
        {
            "id": "target",
            "label": "Designed target",
            "role": "target",
            "smiles": product_smiles,
            "note": "Final next-round design candidate.",
        }
    )
    return nodes


def _common_intermediate(source_smiles: str | None, product_smiles: str, transform_title: str) -> str | None:
    if not source_smiles:
        return None
    title = transform_title.lower()
    if not any(token in title for token in ("methoxy", "ethoxy", "isopropoxy", "phenol", "hydroxyethoxy", "cyanomethoxy", "fluoromethoxy")):
        return None
    source_mol = Chem.MolFromSmiles(source_smiles)
    if source_mol is None:
        return None

    reaction_smarts = (
        "[c:1][O:2][CH2][CH3]>>[c:1][OH]",
        "[c:1][O:2][CH3]>>[c:1][OH]",
        "[c:1][O:2][CH]([CH3])[CH3]>>[c:1][OH]",
    )
    for smarts in reaction_smarts:
        reaction = AllChem.ReactionFromSmarts(smarts)
        for products in reaction.RunReactants((source_mol,)):
            candidate = products[0]
            try:
                Chem.SanitizeMol(candidate)
            except Exception:
                continue
            smiles = Chem.MolToSmiles(candidate, canonical=True)
            if smiles not in {source_smiles, product_smiles}:
                return smiles
    return None


def _route_risks(template: dict[str, Any], feasibility: dict[str, Any]) -> list[str]:
    risks = []
    if template["disconnection"] in {"C-F or O-CF", "C-CN"}:
        risks.append("Regioselectivity and functional-group compatibility should be checked before scale-up.")
    if template["disconnection"] == "C-OH":
        risks.append("Added donor polarity can reduce permeability or introduce conjugation liability.")
    if feasibility.get("level") in {"moderate", "hard"}:
        risks.append(str(feasibility.get("reason") or "Synthetic feasibility is below the easy range."))
    return risks or ["No major route-specific risk from the current rule set."]


def _confidence(feasibility: dict[str, Any]) -> str:
    score = float(feasibility.get("score") or 0)
    if score >= 0.74:
        return "high"
    if score >= 0.48:
        return "medium"
    return "low"


def _chemist_note(transform_title: str, feasibility: dict[str, Any], source_smiles: str | None, used_rdkit: bool = False) -> str:
    source_note = "anchored to the uploaded source compound" if source_smiles else "not anchored to an uploaded source compound"
    level = feasibility.get("level") or "unknown"
    engine_note = "planned with open-source RDKit reaction templates" if used_rdkit else "generated from project analog transform rules"
    return f"Route sketch for {transform_title}; {engine_note}; {source_note}. Current feasibility call: {level}."


def _canonical(smiles: str | None) -> str | None:
    if not smiles:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol, canonical=True)
