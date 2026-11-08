"""Single source of truth for content-based recommendation rules."""

import math
from decimal import Decimal

CALORIE_CATEGORIES = ("Rendah", "Sedang", "Tinggi")
NUTRIENT_PRIORITIES = ("Protein", "Karbohidrat", "Lemak")
BALANCED_REFERENCE = {
    "Protein": 0.15,
    "Karbohidrat": 0.55,
    "Lemak": 0.30,
}
CALORIE_WEIGHT = 0.5
PRIORITY_WEIGHT = 0.5


def calorie_category(calories: Decimal | float) -> str:
    """Return the single per-serving category; 300 and 500 belong to Sedang."""
    value = float(calories)
    if not math.isfinite(value) or value < 0:
        raise ValueError("Nilai kalori harus finite dan tidak negatif.")
    if value < 300:
        return "Rendah"
    if value <= 500:
        return "Sedang"
    return "Tinggi"


def calorie_score(calories: float, category: str) -> float:
    """Score candidate calories against the selected category (equation 1-3)."""
    if not math.isfinite(calories) or calories < 0:
        raise ValueError("Nilai kalori harus finite dan tidak negatif.")
    if category == "Rendah":
        distance, scale = max(0.0, calories - 300), 300.0
    elif category == "Sedang":
        distance, scale = max(0.0, 300 - calories, calories - 500), 200.0
    elif category == "Tinggi":
        distance, scale = max(0.0, 500 - calories), 200.0
    else:
        raise ValueError("Kategori kalori tidak dikenali.")
    return max(0.0, 1.0 - distance / scale)


def min_max_scores(values: list[float]) -> list[float]:
    """Normalize catalogue values to [0, 1]; a constant feature is neutral."""
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Nilai normalisasi harus finite.")
    if not values:
        return []
    low, high = min(values), max(values)
    if high == low:
        return [0.5] * len(values)
    scores = [(value - low) / (high - low) for value in values]
    return [min(1.0, max(0.0, score)) for score in scores]


def balanced_score(proportions: dict[str, float]) -> float:
    """Prototype score against a fixed 15/55/30 macro-energy reference."""
    if not all(
        math.isfinite(proportions[nutrient])
        for nutrient in BALANCED_REFERENCE
    ):
        raise ValueError("Proporsi energi harus finite.")
    deviation = sum(
        abs(proportions[nutrient] - reference)
        for nutrient, reference in BALANCED_REFERENCE.items()
    )
    return max(0.0, 1.0 - deviation / 2.0)


def combined_score(calorie: float, priority: float) -> float:
    """Weighted content-based score on a 0–100 scale."""
    if not all(math.isfinite(value) and 0 <= value <= 1 for value in (calorie, priority)):
        raise ValueError("Komponen skor harus berada pada rentang 0–1.")
    return 100.0 * (
        CALORIE_WEIGHT * calorie + PRIORITY_WEIGHT * priority
    )
