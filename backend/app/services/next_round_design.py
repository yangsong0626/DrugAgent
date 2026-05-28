from __future__ import annotations

import math
import re
from typing import Any

from app.services.column_inference import infer_assay_columns
from app.services.design_ideas import _canonical_smiles_set, _generated_analogs
from app.services.design_preferences import apply_preference_profile
from app.services.medchem_alerts import medchem_alerts
from app.services.property_predictions import predict_property_plugins
from app.services.retrosynthesis import propose_retrosynthesis_route
from app.services.synthetic_feasibility import score_synthetic_feasibility


DEFAULT_OBJECTIVES = {
    "improve_potency": True,
    "reduce_logp": True,
    "improve_solubility": True,
    "improve_microsomal_stability": False,
}


def generate_next_round_designs(
    molecules: list[dict[str, Any]],
    potency_column: str | None = None,
    potency_direction: str = "lower_is_better",
    admet_columns: list[str] | None = None,
    objectives: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
    count: int = 24,
    preference_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not molecules:
        raise ValueError("Upload compounds before generating next-round designs.")
    if potency_direction not in {"lower_is_better", "higher_is_better"}:
        raise ValueError("potency_direction must be lower_is_better or higher_is_better.")

    inferred = infer_assay_columns(molecules)
    potency_column = potency_column or inferred.get("recommended_potency_column")
    admet_columns = admet_columns or inferred.get("recommended_admet_columns", [])
    objectives = {**DEFAULT_OBJECTIVES, **(objectives or {})}
    constraints = constraints or {}
    count = max(1, min(int(count), 80))

    seeds = _seed_molecules(molecules, potency_column, potency_direction, max_seeds=int(constraints.get("max_seed_compounds", 10)))
    tested_smiles = _canonical_smiles_set(molecules)

    candidates = []
    for seed in seeds:
        for analog in _generated_analogs(seed, tested_smiles):
            candidate = _candidate_from_analog(
                analog=analog,
                seed=seed,
                potency_column=potency_column,
                potency_direction=potency_direction,
                admet_columns=admet_columns,
                objectives=objectives,
                constraints=constraints,
            )
            if candidate is not None:
                candidates.append(candidate)

    candidates = _dedupe_and_rank(candidates)
    candidates = apply_preference_profile(candidates, preference_profile or {})
    selected = candidates[:count]
    return {
        "potency_column": potency_column,
        "potency_direction": potency_direction,
        "admet_columns": admet_columns,
        "objectives": objectives,
        "constraints": constraints,
        "seed_compounds": [_seed_summary(seed, potency_column) for seed in seeds],
        "recommendations": selected,
        "metadata": {
            "generated_candidate_count": len(candidates),
            "preference_feedback_count": (preference_profile or {}).get("feedback_count", 0),
            "method": (
                "Conservative RDKit analog transforms from the best uploaded compounds, scored by objective fit, "
                "descriptor movement, medchem alerts, synthetic feasibility, and project design feedback."
            ),
        },
    }


def _candidate_from_analog(
    analog: dict[str, Any],
    seed: dict[str, Any],
    potency_column: str | None,
    potency_direction: str,
    admet_columns: list[str],
    objectives: dict[str, Any],
    constraints: dict[str, Any],
) -> dict[str, Any] | None:
    descriptors = analog.get("predicted_descriptors") or {}
    if not _passes_constraints(descriptors, constraints):
        return None

    smiles = analog["analog_smiles"]
    alerts = medchem_alerts(smiles, descriptors)
    feasibility = score_synthetic_feasibility(
        smiles=smiles,
        source_smiles=seed.get("smiles"),
        transform_title=analog.get("title"),
        descriptor_deltas=analog.get("descriptor_deltas"),
    )
    score, score_parts = _score_candidate(analog, descriptors, alerts, feasibility, objectives)
    priority = "high" if score >= 78 else "medium" if score >= 58 else "low"

    if constraints.get("prefer_one_step_from_existing") and feasibility["score"] < 0.48:
        return None

    route = propose_retrosynthesis_route(
        smiles=smiles,
        source_smiles=seed.get("smiles"),
        transform_title=analog.get("title"),
        synthetic_feasibility=feasibility,
    )
    property_predictions = predict_property_plugins(smiles, descriptors=descriptors, alerts=alerts)

    return {
        "smiles": smiles,
        "name": f"NRD-{seed.get('id')}-{_slug(analog.get('title', 'analog'))}",
        "score": score,
        "base_score": score,
        "preference_adjustment": 0.0,
        "preference_reasons": [],
        "priority": priority,
        "source_molecule_id": int(seed["id"]),
        "source_molecule_name": seed.get("name"),
        "source_smiles": seed.get("smiles"),
        "transform_title": analog.get("title"),
        "property_goal": analog.get("property_goal"),
        "rationale": _rationale(analog, objectives, score_parts, potency_column, potency_direction),
        "expected_benefit": _expected_benefit(analog, objectives),
        "main_risk": _main_risk(alerts, feasibility),
        "supporting_evidence": _supporting_evidence(seed, analog, potency_column, admet_columns),
        "synthetic_note": feasibility["reason"],
        "synthetic_feasibility": feasibility,
        "retrosynthesis_route": route,
        "property_predictions": property_predictions,
        "alerts": alerts,
        "predicted_descriptors": descriptors,
        "descriptor_deltas": analog.get("descriptor_deltas") or {},
    }


def _score_candidate(
    analog: dict[str, Any],
    descriptors: dict[str, Any],
    alerts: list[dict[str, str]],
    feasibility: dict[str, Any],
    objectives: dict[str, Any],
) -> tuple[float, dict[str, float]]:
    deltas = analog.get("descriptor_deltas") or {}
    score_parts = {
        "base": 48.0,
        "feasibility": float(feasibility["score"]) * 20.0,
        "priority": {"high": 10.0, "medium": 6.0, "low": 2.0}.get(analog.get("priority"), 4.0),
        "property": 0.0,
        "alerts": 0.0,
    }

    if objectives.get("reduce_logp"):
        score_parts["property"] += max(-4.0, min(12.0, -float(deltas.get("logp") or 0) * 12.0))
    if objectives.get("improve_solubility"):
        score_parts["property"] += max(-4.0, min(8.0, float(deltas.get("tpsa") or 0) / 8.0))
    if objectives.get("improve_microsomal_stability"):
        score_parts["property"] += max(-2.0, min(8.0, -float(deltas.get("logp") or 0) * 8.0))
        score_parts["property"] += 3.0 if "methyl" in str(analog.get("title", "")).lower() else 0.0

    if descriptors.get("mol_weight") is not None:
        score_parts["property"] -= max(0.0, (float(descriptors["mol_weight"]) - 520.0) / 18.0)
    if descriptors.get("logp") is not None:
        score_parts["property"] -= max(0.0, (float(descriptors["logp"]) - 4.5) * 3.0)

    for alert in alerts:
        score_parts["alerts"] -= {"high": 14.0, "medium": 7.0, "low": 3.0}.get(alert["severity"], 4.0)

    score = round(max(1.0, min(99.0, sum(score_parts.values()))), 1)
    return score, score_parts


def _seed_molecules(
    molecules: list[dict[str, Any]],
    potency_column: str | None,
    potency_direction: str,
    max_seeds: int,
) -> list[dict[str, Any]]:
    if not potency_column:
        return molecules[:max_seeds]

    scored = []
    for molecule in molecules:
        value = _parse_number(_property_value(molecule, potency_column))
        if value is None:
            continue
        potency_rank = value if potency_direction == "lower_is_better" else -value
        property_penalty = max(0.0, float(molecule.get("logp") or 0) - 4.5) + max(0.0, float(molecule.get("mol_weight") or 0) - 520) / 80
        scored.append((potency_rank + property_penalty, molecule))
    scored.sort(key=lambda item: item[0])
    return [molecule for _, molecule in scored[:max(1, max_seeds)]] or molecules[:max_seeds]


def _passes_constraints(descriptors: dict[str, Any], constraints: dict[str, Any]) -> bool:
    checks = {
        "max_mw": ("mol_weight", float),
        "max_logp": ("logp", float),
        "max_tpsa": ("tpsa", float),
        "max_hbd": ("hbd", int),
        "max_hba": ("hba", int),
        "max_rotatable_bonds": ("rotatable_bonds", int),
    }
    for key, (descriptor_key, caster) in checks.items():
        if key in constraints and descriptors.get(descriptor_key) is not None:
            if caster(descriptors[descriptor_key]) > caster(constraints[key]):
                return False
    if constraints.get("avoid_hbd_increase") and int(descriptors.get("hbd") or 0) > int(constraints.get("source_hbd_limit", 5)):
        return False
    return True


def _rationale(
    analog: dict[str, Any],
    objectives: dict[str, Any],
    score_parts: dict[str, float],
    potency_column: str | None,
    potency_direction: str,
) -> str:
    parts = [analog.get("rationale") or "Conservative analog proposal."]
    if potency_column:
        direction = "lower" if potency_direction == "lower_is_better" else "higher"
        parts.append(f"Ranked for {direction} {potency_column} while preserving interpretable single-site SAR.")
    if objectives.get("reduce_logp") and (analog.get("descriptor_deltas", {}).get("logp") or 0) < 0:
        parts.append("Descriptor movement supports lower lipophilicity.")
    parts.append(f"Objective fit contribution {score_parts['property']:.1f}; feasibility contribution {score_parts['feasibility']:.1f}.")
    return " ".join(parts)


def _expected_benefit(analog: dict[str, Any], objectives: dict[str, Any]) -> str:
    deltas = analog.get("descriptor_deltas") or {}
    benefits = []
    if (deltas.get("logp") or 0) < -0.05:
        benefits.append(f"LogP {float(deltas['logp']):+.2f}")
    if (deltas.get("mol_weight") or 0) < -1:
        benefits.append(f"MW {float(deltas['mol_weight']):+.1f}")
    if objectives.get("improve_solubility") and (deltas.get("tpsa") or 0) > 0:
        benefits.append(f"TPSA {float(deltas['tpsa']):+.1f}")
    return "; ".join(benefits) or analog.get("property_goal") or "Focused SAR probe."


def _main_risk(alerts: list[dict[str, str]], feasibility: dict[str, Any]) -> str:
    if alerts:
        high_or_first = sorted(alerts, key=lambda item: {"high": 0, "medium": 1, "low": 2}.get(item["severity"], 3))[0]
        return high_or_first["message"]
    if feasibility["level"] != "easy":
        return feasibility["reason"]
    return "No major property or structural alert from the rule set."


def _supporting_evidence(
    seed: dict[str, Any],
    analog: dict[str, Any],
    potency_column: str | None,
    admet_columns: list[str],
) -> list[str]:
    evidence = [f"Derived from uploaded compound {seed.get('name') or seed.get('id')} using {analog.get('title')}."]
    if potency_column and (value := _property_value(seed, potency_column)) is not None:
        evidence.append(f"Source {potency_column}: {value}.")
    for column in admet_columns[:3]:
        if (value := _property_value(seed, column)) is not None:
            evidence.append(f"Source {column}: {value}.")
    evidence.append(analog.get("synthetic_note") or "Conservative single-site transform.")
    return evidence


def _seed_summary(seed: dict[str, Any], potency_column: str | None) -> dict[str, Any]:
    return {
        "id": int(seed["id"]),
        "name": seed.get("name"),
        "smiles": seed.get("smiles"),
        "potency_value": _parse_number(_property_value(seed, potency_column)) if potency_column else None,
        "properties": {
            "mol_weight": seed.get("mol_weight"),
            "logp": seed.get("logp"),
            "tpsa": seed.get("tpsa"),
        },
    }


def _dedupe_and_rank(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {}
    for candidate in candidates:
        smiles = candidate["smiles"]
        if smiles not in unique or candidate["score"] > unique[smiles]["score"]:
            unique[smiles] = candidate
    return sorted(unique.values(), key=lambda item: item["score"], reverse=True)


def _property_value(molecule: dict[str, Any], column: str | None) -> Any:
    if not column:
        return None
    properties = molecule.get("properties", {})
    if column in properties:
        return properties[column]
    lowered = {str(key).lower(): value for key, value in properties.items()}
    return lowered.get(column.lower())


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if math.isnan(value):
            return None
        return float(value)
    match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:32] or "analog"
