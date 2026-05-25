from __future__ import annotations

import re
from statistics import median
from typing import Any


POTENCY_PATTERNS = (
    (re.compile(r"\b(pic50|pec50|pki|pkd)\b", re.IGNORECASE), "higher_is_better", None, "potency"),
    (re.compile(r"\b(ic50|ec50|ki|kd|ac50|gi50)\b", re.IGNORECASE), "lower_is_better", "nM", "potency"),
)

ADMET_PATTERNS = (
    (re.compile(r"(clint|intrinsic.*clearance|clearance|hlm|mlm|rlm|hepatocyte)", re.IGNORECASE), "lower_is_better", None, "clearance"),
    (re.compile(r"(solubility|kinetic.*sol|thermo.*sol)", re.IGNORECASE), "higher_is_better", None, "solubility"),
    (re.compile(r"(pampa|caco|mdck|permeability|papp)", re.IGNORECASE), "higher_is_better", None, "permeability"),
    (re.compile(r"(herg|cyp|tox|ames|micronucleus)", re.IGNORECASE), "lower_is_better", None, "safety"),
    (re.compile(r"(fub|ppb|protein.*binding)", re.IGNORECASE), None, None, "binding"),
    (re.compile(r"(logd|logp|tpsa|psa|mw|molecular.*weight)", re.IGNORECASE), None, None, "property"),
)

UNIT_PATTERNS = (
    (re.compile(r"\b(nm|nanomolar)\b", re.IGNORECASE), "nM"),
    (re.compile(r"\b(um|µm|micromolar)\b", re.IGNORECASE), "uM"),
    (re.compile(r"\b(mm|millimolar)\b", re.IGNORECASE), "mM"),
    (re.compile(r"(ul/min/mg|uL/min/mg|µL/min/mg)", re.IGNORECASE), "uL/min/mg"),
    (re.compile(r"(ml/min/kg|mL/min/kg)", re.IGNORECASE), "mL/min/kg"),
)


def infer_assay_columns(molecules: list[dict[str, Any]]) -> dict[str, Any]:
    columns = _property_columns(molecules)
    potency_columns = []
    admet_columns = []
    numeric_columns = []

    for column, values in columns.items():
        numeric_values = [_parse_number(value) for value in values]
        numeric_values = [value for value in numeric_values if value is not None]
        numeric_fraction = len(numeric_values) / max(len(values), 1)
        if numeric_fraction >= 0.4:
            numeric_columns.append(column)

        potency = _infer_potency_column(column, numeric_fraction, numeric_values)
        if potency:
            potency_columns.append(potency)
            continue

        admet = _infer_admet_column(column, numeric_fraction, numeric_values)
        if admet:
            admet_columns.append(admet)

    potency_columns.sort(key=lambda item: item["confidence"], reverse=True)
    admet_columns.sort(key=lambda item: item["confidence"], reverse=True)

    return {
        "compound_count": len(molecules),
        "numeric_columns": sorted(numeric_columns),
        "potency_columns": potency_columns,
        "admet_columns": admet_columns,
        "recommended_potency_column": potency_columns[0]["name"] if potency_columns else None,
        "recommended_admet_columns": [column["name"] for column in admet_columns[:5]],
        "metadata": {
            "method": "Column-name pattern matching with numeric coverage and value-range checks.",
        },
    }


def _property_columns(molecules: list[dict[str, Any]]) -> dict[str, list[Any]]:
    columns: dict[str, list[Any]] = {}
    for molecule in molecules:
        properties = molecule.get("properties") or {}
        for key, value in properties.items():
            columns.setdefault(str(key), []).append(value)
    return columns


def _infer_potency_column(column: str, numeric_fraction: float, numeric_values: list[float]) -> dict[str, Any] | None:
    normalized = _normalize_column(column)
    for pattern, direction, default_unit, assay_kind in POTENCY_PATTERNS:
        if not pattern.search(normalized):
            continue
        confidence = 0.64 + min(numeric_fraction, 1.0) * 0.26
        unit = _infer_unit(column) or default_unit
        if numeric_values and median(numeric_values) <= 20 and unit == "nM":
            confidence -= 0.08
            unit = "uM" if any(token in normalized for token in ("um", "µm", "micro")) else unit
        return {
            "name": column,
            "role": assay_kind,
            "assay_type": _assay_type_from_name(normalized),
            "unit": unit,
            "direction": direction,
            "confidence": round(max(0.0, min(confidence, 0.98)), 2),
            "numeric_fraction": round(numeric_fraction, 2),
        }
    return None


def _infer_admet_column(column: str, numeric_fraction: float, numeric_values: list[float]) -> dict[str, Any] | None:
    normalized = _normalize_column(column)
    for pattern, direction, unit, category in ADMET_PATTERNS:
        if not pattern.search(normalized):
            continue
        confidence = 0.58 + min(numeric_fraction, 1.0) * 0.27
        return {
            "name": column,
            "role": "admet" if category not in {"property"} else "property",
            "assay_type": category,
            "unit": _infer_unit(column) or unit,
            "direction": direction,
            "confidence": round(max(0.0, min(confidence, 0.95)), 2),
            "numeric_fraction": round(numeric_fraction, 2),
            "median_value": round(median(numeric_values), 3) if numeric_values else None,
        }
    return None


def _normalize_column(column: str) -> str:
    return re.sub(r"[_\-]+", " ", column).strip().lower()


def _infer_unit(column: str) -> str | None:
    for pattern, unit in UNIT_PATTERNS:
        if pattern.search(column):
            return unit
    return None


def _assay_type_from_name(column: str) -> str:
    if any(token in column for token in ("cell", "cellular", "ec50")):
        return "cellular_potency"
    if any(token in column for token in ("biochem", "enzyme", "ic50", "ki", "kd")):
        return "biochemical_potency"
    return "potency"


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None
