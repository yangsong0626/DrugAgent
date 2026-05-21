from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from statistics import median
from typing import Any, Dict, List, Optional


POTENCY_HINTS = ("ic50", "ec50", "ki", "kd", "potency", "activity")
ADMET_HINTS = ("clint", "clearance", "herg", "solubility", "logd", "caco", "permeability", "tox")
IDENTIFIER_HINTS = ("id", "name", "url", "cas", "smiles", "inchi")


def generate_portfolio_insights(molecules: List[Dict[str, Any]]) -> Dict[str, Any]:
    numeric_columns = _numeric_property_columns(molecules)
    potency_column = _best_matching_column(numeric_columns, POTENCY_HINTS)
    admet_columns = [
        column
        for column in numeric_columns
        if column != potency_column and any(hint in column.lower() for hint in ADMET_HINTS)
    ][:5]

    scored = [_score_molecule(molecule, potency_column, admet_columns) for molecule in molecules]
    scored.sort(key=lambda row: row["score"], reverse=True)

    alert_counts = Counter(alert["severity"] for row in scored for alert in row["alerts"])
    cluster_counts = Counter(row["cluster_id"] for row in scored if row["cluster_id"] is not None)
    cluster_score: Dict[int, List[float]] = defaultdict(list)
    for row in scored:
        if row["cluster_id"] is not None:
            cluster_score[int(row["cluster_id"])].append(float(row["score"]))

    recommended = scored[:8]
    next_actions = _next_actions(scored, potency_column, admet_columns, numeric_columns)

    return {
        "compound_count": len(molecules),
        "numeric_columns": numeric_columns,
        "detected_potency_column": potency_column,
        "detected_admet_columns": admet_columns,
        "recommended_compounds": recommended,
        "property_alerts": {
            "high": alert_counts.get("high", 0),
            "medium": alert_counts.get("medium", 0),
            "low": alert_counts.get("low", 0),
        },
        "cluster_opportunities": [
            {
                "cluster_id": cluster_id,
                "compound_count": cluster_counts[cluster_id],
                "median_score": round(median(cluster_score[cluster_id]), 1),
            }
            for cluster_id, _ in cluster_counts.most_common(6)
        ],
        "next_actions": next_actions,
        "metadata": {
            "method": "Rule-based lead triage combining potency, Lipinski-style property fit, ADMET hints, and cluster diversity.",
            "score_range": "0-100",
        },
    }


def _score_molecule(molecule: Dict[str, Any], potency_column: Optional[str], admet_columns: List[str]) -> Dict[str, Any]:
    alerts = _property_alerts(molecule)
    score = 72.0

    potency_value = _parse_number(_property_value(molecule, potency_column)) if potency_column else None
    if potency_value is not None and potency_value > 0:
        score += max(-18.0, min(18.0, 18.0 - (math.log10(potency_value) * 7.0)))

    for alert in alerts:
        score -= {"high": 14.0, "medium": 7.0, "low": 3.0}[alert["severity"]]

    admet_notes = []
    for column in admet_columns:
        value = _parse_number(_property_value(molecule, column))
        if value is None:
            continue
        note, penalty = _admet_signal(column, value)
        if note:
            admet_notes.append(note)
            score -= penalty

    if not alerts:
        score += 8.0

    score = round(max(0.0, min(100.0, score)), 1)
    rationale = _rationale(score, potency_column, potency_value, alerts, admet_notes)

    return {
        "id": int(molecule["id"]),
        "name": molecule.get("name"),
        "smiles": molecule.get("smiles"),
        "cluster_id": molecule.get("cluster_id"),
        "score": score,
        "potency_value": potency_value,
        "rationale": rationale,
        "alerts": alerts,
        "admet_notes": admet_notes,
        "properties": {
            "mol_weight": molecule.get("mol_weight"),
            "logp": molecule.get("logp"),
            "hbd": molecule.get("hbd"),
            "hba": molecule.get("hba"),
            "tpsa": molecule.get("tpsa"),
            "rotatable_bonds": molecule.get("rotatable_bonds"),
        },
    }


def _property_alerts(molecule: Dict[str, Any]) -> List[Dict[str, str]]:
    checks = [
        ("mol_weight", molecule.get("mol_weight"), 500, 650, "MW"),
        ("logp", molecule.get("logp"), 5, 7, "LogP"),
        ("hbd", molecule.get("hbd"), 5, 8, "HBD"),
        ("hba", molecule.get("hba"), 10, 14, "HBA"),
        ("tpsa", molecule.get("tpsa"), 140, 180, "TPSA"),
        ("rotatable_bonds", molecule.get("rotatable_bonds"), 10, 14, "RotB"),
    ]
    alerts = []
    for key, value, medium_cutoff, high_cutoff, label in checks:
        if value is None:
            continue
        severity = None
        if float(value) > high_cutoff:
            severity = "high"
        elif float(value) > medium_cutoff:
            severity = "medium"
        if severity:
            alerts.append(
                {
                    "field": key,
                    "severity": severity,
                    "message": f"{label} {float(value):g} is above the usual oral-drug comfort zone.",
                }
            )
    return alerts


def _next_actions(
    scored: List[Dict[str, Any]],
    potency_column: Optional[str],
    admet_columns: List[str],
    numeric_columns: List[str],
) -> List[str]:
    actions = []
    if potency_column:
        actions.append(f"Use {potency_column} as the default SAR potency endpoint and run matched-pair analysis on the top clusters.")
    elif numeric_columns:
        actions.append(f"Choose a potency endpoint from detected numeric columns: {', '.join(numeric_columns[:5])}.")
    else:
        actions.append("Add at least one measured potency column so the agent can rank compounds beyond property fit.")

    if admet_columns:
        actions.append(f"Track ADMET trade-offs with {', '.join(admet_columns)} while selecting next analogs.")
    else:
        actions.append("Add clearance, hERG, solubility, or permeability columns to expose developability trade-offs.")

    clean_leads = [row for row in scored if row["score"] >= 75 and not row["alerts"]]
    if clean_leads:
        names = ", ".join(row["name"] or f"Compound {row['id']}" for row in clean_leads[:3])
        actions.append(f"Promote {names} as clean starting leads for follow-up design.")
    else:
        actions.append("Prioritize analogs that reduce lipophilicity or size before broad potency optimization.")

    return actions


def _rationale(
    score: float,
    potency_column: Optional[str],
    potency_value: Optional[float],
    alerts: List[Dict[str, str]],
    admet_notes: List[str],
) -> str:
    parts = [f"Score {score:g}/100"]
    if potency_column and potency_value is not None:
        parts.append(f"{potency_column}={potency_value:g}")
    if alerts:
        parts.append(f"{len(alerts)} property alert(s)")
    else:
        parts.append("clean core properties")
    if admet_notes:
        parts.append("; ".join(admet_notes[:2]))
    return "; ".join(parts)


def _numeric_property_columns(molecules: List[Dict[str, Any]]) -> List[str]:
    counts: Counter[str] = Counter()
    numeric_counts: Counter[str] = Counter()
    for molecule in molecules:
        for key, value in molecule.get("properties", {}).items():
            column = str(key)
            if _looks_like_identifier_column(column):
                continue
            counts[column] += 1
            if _is_numeric_property_value(value):
                numeric_counts[column] += 1

    columns = [
        column
        for column, count in numeric_counts.items()
        if count >= max(1, int(counts[column] * 0.6))
    ]
    return sorted(columns, key=lambda column: (-numeric_counts[column], column.lower()))


def _looks_like_identifier_column(column: str) -> bool:
    normalized = column.strip().lower().replace(" ", "_")
    if normalized in IDENTIFIER_HINTS:
        return True
    return normalized.endswith("_id") or normalized.endswith("_url")


def _is_numeric_property_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return not math.isnan(value)
    text = str(value).strip().replace(",", "")
    return bool(re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?(?:\s*[a-zA-Z/%_]+)?", text))


def _best_matching_column(columns: List[str], hints: tuple[str, ...]) -> Optional[str]:
    for hint in hints:
        for column in columns:
            if hint in column.lower():
                return column
    return None


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


def _admet_signal(column: str, value: float) -> tuple[Optional[str], float]:
    normalized = column.lower()
    if "herg" in normalized and value > 10:
        return (f"{column} may indicate hERG liability", 10.0)
    if ("clint" in normalized or "clearance" in normalized) and value > 50:
        return (f"{column} suggests high clearance", 8.0)
    if "logd" in normalized and value > 4:
        return (f"{column} is lipophilic", 5.0)
    if "solubility" in normalized and value < 10:
        return (f"{column} may be low", 6.0)
    return (None, 0.0)
