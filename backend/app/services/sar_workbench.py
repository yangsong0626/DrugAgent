from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

from app.services.sar_summary import _parse_number, _prepare_compounds, generate_sar_summary


def build_sar_workbench(
    molecules: list[dict[str, Any]],
    potency_column: str,
    potency_direction: str = "lower_is_better",
    admet_columns: list[str] | None = None,
    min_fold_change: float = 3.0,
) -> dict[str, Any]:
    admet_columns = admet_columns or []
    summary = generate_sar_summary(
        molecules=molecules,
        potency_column=potency_column,
        potency_direction=potency_direction,
        admet_columns=admet_columns,
        min_fold_change=min_fold_change,
    )
    compounds = _prepare_compounds(molecules, potency_column)
    rgroup_tables = _build_rgroup_tables(compounds, admet_columns)
    heatmap = _build_heatmap(compounds, potency_direction, admet_columns)
    hypotheses = _build_hypotheses(summary, heatmap)

    return {
        "summary": summary,
        "rgroup_tables": rgroup_tables,
        "heatmap": heatmap,
        "hypotheses": hypotheses,
        "metadata": {
            "method": "SAR summary plus scaffold-level R-group tables and median potency/property rollups.",
            "limitations": summary.get("metadata", {}).get("limitations"),
        },
    }


def _build_rgroup_tables(compounds: list[Any], admet_columns: list[str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for compound in compounds:
        grouped[compound.scaffold].append(compound)

    tables: list[dict[str, Any]] = []
    for scaffold, members in grouped.items():
        positions = sorted({position for compound in members for position in compound.r_groups})
        rows = []
        for compound in sorted(members, key=lambda item: item.potency):
            admet_values = {
                column: _parse_number(_property_value(compound.properties, column))
                for column in admet_columns
                if _property_value(compound.properties, column) is not None
            }
            rows.append(
                {
                    "compound_id": compound.id,
                    "name": compound.name,
                    "smiles": compound.smiles,
                    "potency": compound.potency,
                    "r_groups": {position: compound.r_groups.get(position, "H") for position in positions},
                    "admet_values": admet_values,
                }
            )
        tables.append(
            {
                "scaffold": scaffold,
                "compound_count": len(members),
                "positions": positions,
                "rows": rows,
            }
        )

    tables.sort(key=lambda table: table["compound_count"], reverse=True)
    return tables[:12]


def _build_heatmap(compounds: list[Any], potency_direction: str, admet_columns: list[str]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for compound in compounds:
        for position, substitution in compound.r_groups.items():
            buckets[(compound.scaffold, position, substitution)].append(compound)

    cells = []
    for (scaffold, position, substitution), members in buckets.items():
        potency_values = [compound.potency for compound in members]
        admet_medians = {}
        for column in admet_columns:
            values = [
                _parse_number(_property_value(compound.properties, column))
                for compound in members
            ]
            values = [value for value in values if value is not None]
            if values:
                admet_medians[column] = round(median(values), 3)

        cells.append(
            {
                "scaffold": scaffold,
                "position": position,
                "substitution": substitution,
                "compound_count": len(members),
                "median_potency": round(median(potency_values), 3),
                "best_potency": round(min(potency_values) if potency_direction == "lower_is_better" else max(potency_values), 3),
                "admet_medians": admet_medians,
            }
        )

    cells.sort(key=lambda cell: (cell["position"], cell["median_potency"]))
    return cells[:120]


def _build_hypotheses(summary: dict[str, Any], heatmap: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hypotheses: list[dict[str, Any]] = []
    for trend in summary.get("key_sar_trends", [])[:4]:
        hypotheses.append(
            {
                "title": "Potency-driving matched pair",
                "statement": trend,
                "confidence": "medium" if summary.get("matched_pair_count", 0) < 5 else "high",
                "recommended_action": "Prioritize nearby analogs that keep the favored vector while scanning size and electronics.",
            }
        )

    for risk in summary.get("risky_modifications", [])[:3]:
        hypotheses.append(
            {
                "title": "Potency/ADMET trade-off",
                "statement": risk,
                "confidence": "medium",
                "recommended_action": "Treat this as a conditional design move and pair it with an ADMET counter-scan.",
            }
        )

    position_counts: dict[str, int] = defaultdict(int)
    for cell in heatmap:
        position_counts[cell["position"]] += cell["compound_count"]
    for position, count in sorted(position_counts.items(), key=lambda item: item[1], reverse=True)[:3]:
        hypotheses.append(
            {
                "title": f"{position} exploration depth",
                "statement": f"{position} has {count} observed substitution data points in the current series.",
                "confidence": "medium",
                "recommended_action": "Use this position for the next focused R-group scan if synthesis is tractable.",
            }
        )

    if not hypotheses:
        hypotheses.append(
            {
                "title": "More matched data needed",
                "statement": "The current upload does not contain enough same-scaffold potency data to support strong SAR hypotheses.",
                "confidence": "low",
                "recommended_action": "Add potency values for close analogs or lower the matched-pair fold-change threshold.",
            }
        )
    return hypotheses[:10]


def _property_value(properties: dict[str, Any], column: str) -> Any:
    if column in properties:
        return properties[column]
    lowered = column.lower()
    for key, value in properties.items():
        if str(key).lower() == lowered:
            return value
    return None
