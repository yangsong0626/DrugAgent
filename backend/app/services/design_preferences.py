from __future__ import annotations

from collections import Counter
from typing import Any


LIKE_VALUES = {"like", "liked", "up", "positive"}
DISLIKE_VALUES = {"dislike", "disliked", "down", "negative"}


def build_preference_profile(feedback_rows: list[dict[str, Any]]) -> dict[str, Any]:
    transform_weights: Counter[str] = Counter()
    goal_weights: Counter[str] = Counter()
    alert_weights: Counter[str] = Counter()
    descriptor_direction_weights: Counter[str] = Counter()
    exact_feedback: dict[str, str] = {}

    for row in feedback_rows:
        feedback = _normalized_feedback(row.get("feedback"))
        if feedback == "neutral":
            continue
        sign = 1 if feedback == "like" else -1
        design = row.get("design") or {}
        smiles = row.get("smiles")
        if smiles:
            exact_feedback[str(smiles)] = feedback

        if transform := design.get("transform_title"):
            transform_weights[str(transform)] += sign
        if goal := design.get("property_goal"):
            goal_weights[str(goal)] += sign
        for alert in design.get("alerts", []) or []:
            if alert.get("field"):
                alert_weights[str(alert["field"])] += sign
        for key, value in (design.get("descriptor_deltas") or {}).items():
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if abs(numeric) < 0.01:
                continue
            direction = "decrease" if numeric < 0 else "increase"
            descriptor_direction_weights[f"{key}:{direction}"] += sign

    return {
        "feedback_count": len(feedback_rows),
        "like_count": sum(1 for row in feedback_rows if _normalized_feedback(row.get("feedback")) == "like"),
        "dislike_count": sum(1 for row in feedback_rows if _normalized_feedback(row.get("feedback")) == "dislike"),
        "transform_weights": dict(transform_weights),
        "goal_weights": dict(goal_weights),
        "alert_weights": dict(alert_weights),
        "descriptor_direction_weights": dict(descriptor_direction_weights),
        "exact_feedback": exact_feedback,
    }


def apply_preference_profile(candidates: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    if not profile or not profile.get("feedback_count"):
        return candidates

    reranked = []
    for candidate in candidates:
        adjustment, reasons = _preference_adjustment(candidate, profile)
        next_candidate = {**candidate}
        next_candidate["base_score"] = candidate["score"]
        next_candidate["preference_adjustment"] = round(adjustment, 1)
        next_candidate["preference_reasons"] = reasons
        next_candidate["score"] = round(max(1.0, min(99.0, float(candidate["score"]) + adjustment)), 1)
        next_candidate["priority"] = "high" if next_candidate["score"] >= 78 else "medium" if next_candidate["score"] >= 58 else "low"
        reranked.append(next_candidate)

    return sorted(reranked, key=lambda item: item["score"], reverse=True)


def _preference_adjustment(candidate: dict[str, Any], profile: dict[str, Any]) -> tuple[float, list[str]]:
    exact_feedback = profile.get("exact_feedback", {}).get(candidate.get("smiles"))
    if exact_feedback == "dislike":
        return -25.0, ["You previously disliked this exact design."]
    if exact_feedback == "like":
        return 6.0, ["You previously liked this exact design."]

    adjustment = 0.0
    reasons = []
    transform = candidate.get("transform_title")
    if transform and (weight := profile.get("transform_weights", {}).get(transform, 0)):
        delta = max(-10.0, min(10.0, float(weight) * 4.0))
        adjustment += delta
        reasons.append(_reason("transform", transform, delta))

    goal = candidate.get("property_goal")
    if goal and (weight := profile.get("goal_weights", {}).get(goal, 0)):
        delta = max(-6.0, min(6.0, float(weight) * 2.0))
        adjustment += delta
        reasons.append(_reason("goal", goal, delta))

    for key, value in (candidate.get("descriptor_deltas") or {}).items():
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if abs(numeric) < 0.01:
            continue
        direction = "decrease" if numeric < 0 else "increase"
        weight = profile.get("descriptor_direction_weights", {}).get(f"{key}:{direction}", 0)
        if weight:
            delta = max(-4.0, min(4.0, float(weight) * 1.2))
            adjustment += delta
            reasons.append(_reason("descriptor", f"{key} {direction}", delta))

    for alert in candidate.get("alerts", []) or []:
        field = alert.get("field")
        if field and (weight := profile.get("alert_weights", {}).get(field, 0)):
            delta = max(-5.0, min(3.0, float(weight) * 1.5))
            adjustment += delta
            reasons.append(_reason("alert", field, delta))

    return adjustment, reasons[:4]


def _normalized_feedback(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in LIKE_VALUES:
        return "like"
    if normalized in DISLIKE_VALUES:
        return "dislike"
    return "neutral"


def _reason(kind: str, label: str, delta: float) -> str:
    direction = "boosted" if delta > 0 else "downranked"
    return f"{direction} because your feedback {('favored' if delta > 0 else 'penalized')} {kind}: {label}"
