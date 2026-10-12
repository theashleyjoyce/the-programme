"""Token and cost accounting for The Programme.

This exists to earn the Tokenomics row (8 pts), which is explicit that
"Estimates alone get half." So every number the report quotes comes from here,
and every number here comes from a real API response.

What is measured vs. assumed, stated plainly:

  MEASURED  - input, cached input, and output tokens. These are read off
              `response.usage` on real calls. They are facts.
  ASSUMED   - the dollar price per million tokens, and the usage pattern used
              for the per-month and at-scale projections.

The two are kept apart on purpose. Token counts are evidence; prices are a
multiplier you set once. If a price is wrong, every dollar figure moves
together and nothing has to be re-measured.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

# --- pricing ---------------------------------------------------------------

# !! VERIFY BEFORE SUBMITTING !!
# USD per 1,000,000 tokens. These are placeholders until confirmed against the
# provider's live pricing page or the course materials. Override without
# editing code by setting PRICE_INPUT_PER_M / PRICE_CACHED_PER_M /
# PRICE_OUTPUT_PER_M in .env.
#
# Cached input is normally billed at a steep discount to fresh input; that
# discount is the whole reason the caching work in this app pays for itself,
# so the report should quote the real figure, not this placeholder.
DEFAULT_PRICING: dict[str, float] = {
    "input_per_m": 1.25,
    "cached_input_per_m": 0.125,
    "output_per_m": 10.00,
}


def pricing() -> dict[str, float]:
    """Pricing with .env overrides applied."""
    return {
        "input_per_m": float(os.getenv("PRICE_INPUT_PER_M", DEFAULT_PRICING["input_per_m"])),
        "cached_input_per_m": float(os.getenv("PRICE_CACHED_PER_M", DEFAULT_PRICING["cached_input_per_m"])),
        "output_per_m": float(os.getenv("PRICE_OUTPUT_PER_M", DEFAULT_PRICING["output_per_m"])),
    }


PRICING_IS_VERIFIED = os.getenv("PRICING_VERIFIED", "").strip().lower() in {"1", "true", "yes"}


# --- measurement -----------------------------------------------------------


@dataclass
class Usage:
    """One model call's token counts, straight off the API response.

    `input_tokens` is fresh (uncached) input only. Providers report total input
    with a cached subset inside it, so `from_response` subtracts to keep the
    three buckets non-overlapping -- otherwise cached tokens get billed twice
    in the report.
    """

    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    @classmethod
    def from_response(cls, response: Any) -> "Usage":
        usage = getattr(response, "usage", None)
        if usage is None:
            return cls()

        total_input = int(getattr(usage, "input_tokens", 0) or 0)
        output = int(getattr(usage, "output_tokens", 0) or 0)

        details = getattr(usage, "input_tokens_details", None)
        cached = int(getattr(details, "cached_tokens", 0) or 0) if details else 0

        return cls(
            input_tokens=max(total_input - cached, 0),
            cached_input_tokens=cached,
            output_tokens=output,
            calls=1,
        )

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            calls=self.calls + other.calls,
        )

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.cached_input_tokens + self.output_tokens

    @property
    def cache_hit_rate(self) -> float:
        """Share of input tokens served from cache. The cost-cutting headline."""
        total_input = self.input_tokens + self.cached_input_tokens
        return (self.cached_input_tokens / total_input) if total_input else 0.0

    def cost_usd(self, prices: dict[str, float] | None = None) -> float:
        p = prices or pricing()
        return (
            self.input_tokens / 1_000_000 * p["input_per_m"]
            + self.cached_input_tokens / 1_000_000 * p["cached_input_per_m"]
            + self.output_tokens / 1_000_000 * p["output_per_m"]
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "total_tokens": self.total_tokens,
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "cost_usd": round(self.cost_usd(), 6),
        }


# --- projection ------------------------------------------------------------

# !! ASSUMPTION, state it in the report !!
# Plans a typical user requests per month. 4 = roughly one night out a week.
# Defended in the report rather than hidden here.
PLANS_PER_USER_PER_MONTH = int(os.getenv("PLANS_PER_USER_PER_MONTH", "4"))
SCALE_TIERS = (1, 100, 10_000)


@dataclass
class TokenomicsReport:
    """Every figure the Tokenomics section needs, computed from real runs."""

    runs_measured: int
    mean_usage: dict[str, Any]
    cost_per_run_usd: float
    cost_per_user_per_month_usd: float
    monthly_cost_by_users: dict[str, float]
    plans_per_user_per_month: int
    prices_used: dict[str, float]
    pricing_verified: bool
    note: str

    def to_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        return path


def build_report(usages: Iterable[Usage]) -> TokenomicsReport:
    """Average real runs, then project. Averaging before costing keeps one
    unusually long night from setting the headline number."""
    runs = [u for u in usages if u.calls]
    if not runs:
        raise ValueError("No measured runs. Run the app before reporting tokenomics.")

    n = len(runs)
    total = Usage()
    for u in runs:
        total = total + u

    mean = Usage(
        input_tokens=round(total.input_tokens / n),
        cached_input_tokens=round(total.cached_input_tokens / n),
        output_tokens=round(total.output_tokens / n),
        calls=round(total.calls / n),
    )

    prices = pricing()
    per_run = mean.cost_usd(prices)
    per_user_month = per_run * PLANS_PER_USER_PER_MONTH

    note = (
        "Token counts are measured from real API responses. "
        + (
            "Prices confirmed against the provider's pricing page."
            if PRICING_IS_VERIFIED
            else "PRICES ARE UNVERIFIED PLACEHOLDERS -- confirm before submitting."
        )
    )

    return TokenomicsReport(
        runs_measured=n,
        mean_usage=mean.as_dict(),
        cost_per_run_usd=round(per_run, 6),
        cost_per_user_per_month_usd=round(per_user_month, 4),
        monthly_cost_by_users={f"{t:,}": round(per_user_month * t, 2) for t in SCALE_TIERS},
        plans_per_user_per_month=PLANS_PER_USER_PER_MONTH,
        prices_used=prices,
        pricing_verified=PRICING_IS_VERIFIED,
        note=note,
    )
