"""Illustrative ROI scenario calculator.

Multiplies user-editable assumptions from ``config/roi_assumptions.yml``
into scenario tables. Every output is labeled as assumption-driven; this
module never claims observed savings, outcomes, or recruitment results.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_ASSUMPTIONS_PATH = Path("config/roi_assumptions.yml")


class RoiAssumptions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cost_per_feasibility_review: float = Field(ge=0)
    deprioritized_review_share: float = Field(ge=0, le=1)
    cost_per_underperforming_site_activation: float = Field(ge=0)
    site_activations_per_cycle: float = Field(ge=0)
    activation_decisions_influenced_share: float = Field(ge=0, le=1)


class Scenario(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str
    review_multiplier: float = Field(ge=0)
    activation_multiplier: float = Field(ge=0)


class RoiConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    disclaimer: str
    currency: str = "USD"
    assumptions: RoiAssumptions
    scenarios: dict[str, Scenario]
    reviews_per_cycle: float = Field(ge=0)


class ScenarioResult(BaseModel):
    scenario_key: str
    label: str
    currency: str
    reviews_deprioritized: float
    illustrative_review_effort_value: float
    activations_influenced: float
    illustrative_activation_value: float
    illustrative_total_value: float
    disclaimer: str


def load_roi_config(path: Path | str = DEFAULT_ASSUMPTIONS_PATH) -> RoiConfig:
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return RoiConfig.model_validate(raw)


def compute_scenarios(config: RoiConfig) -> list[ScenarioResult]:
    """Deterministic arithmetic over the configured assumptions.

    reviews_deprioritized = reviews_per_cycle * deprioritized_share * mult
    activations_influenced = activations_per_cycle * influenced_share * mult
    Values are those counts times the corresponding assumed unit costs.
    """
    a = config.assumptions
    results: list[ScenarioResult] = []
    for key, scenario in config.scenarios.items():
        reviews_deprioritized = (
            config.reviews_per_cycle * a.deprioritized_review_share * scenario.review_multiplier
        )
        review_value = reviews_deprioritized * a.cost_per_feasibility_review
        activations_influenced = (
            a.site_activations_per_cycle
            * a.activation_decisions_influenced_share
            * scenario.activation_multiplier
        )
        activation_value = activations_influenced * a.cost_per_underperforming_site_activation
        results.append(
            ScenarioResult(
                scenario_key=key,
                label=scenario.label,
                currency=config.currency,
                reviews_deprioritized=round(reviews_deprioritized, 2),
                illustrative_review_effort_value=round(review_value, 2),
                activations_influenced=round(activations_influenced, 2),
                illustrative_activation_value=round(activation_value, 2),
                illustrative_total_value=round(review_value + activation_value, 2),
                disclaimer=config.disclaimer.strip(),
            )
        )
    return results


def render_markdown(results: list[ScenarioResult]) -> str:
    if not results:
        return "No scenarios configured."
    lines = [
        "# Illustrative ROI Scenarios",
        "",
        f"> {results[0].disclaimer}",
        "",
        "| Scenario | Reviews deprioritized | Review-effort value |"
        " Activations influenced | Activation value | Total (illustrative) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in results:
        lines.append(
            f"| {r.label} | {r.reviews_deprioritized:,.1f}"
            f" | {r.currency} {r.illustrative_review_effort_value:,.0f}"
            f" | {r.activations_influenced:,.1f}"
            f" | {r.currency} {r.illustrative_activation_value:,.0f}"
            f" | {r.currency} {r.illustrative_total_value:,.0f} |"
        )
    lines.append("")
    lines.append(
        "All figures are products of editable assumptions in"
        " `config/roi_assumptions.yml` — not observed outcomes."
    )
    return "\n".join(lines)
