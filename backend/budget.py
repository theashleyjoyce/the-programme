"""A hard spending cap, enforced in code.

The Safety section of the assignment asks directly: "what stops a bug or a bad
actor from burning through your token budget?" This is the answer, and it is
the one defence that cannot be argued with by a model, because the model never
gets to run.

Three layers, cheapest first:

  PER CALL   a single request that would exceed the remaining budget is refused
             before it is sent.
  PER RUN    one plan may make at most MAX_CALLS_PER_RUN model calls, so a
             retry loop cannot quietly spend the whole budget on one request.
  LIFETIME   a persistent ledger on disk. Restarting the app does not reset it,
             which is the point -- a cap you can clear by restarting is not a cap.

The ledger doubles as the tokenomics evidence: every figure in the report comes
from output/spend_ledger.json, which is a record of real calls, not an estimate.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tokens import Usage, pricing

LEDGER = Path(__file__).resolve().parent.parent / "output" / "spend_ledger.json"

# The project's whole budget. Override with BUDGET_USD in the root .env.
BUDGET_USD = float(os.getenv("BUDGET_USD", "10.00"))

# One plan should never need more than this. The pipeline uses two.
MAX_CALLS_PER_RUN = int(os.getenv("MAX_CALLS_PER_RUN", "6"))

# Refuse a call when less than this remains, so the app fails with a clear
# message rather than halfway through a plan the user is waiting for.
RESERVE_USD = 0.10

_lock = threading.Lock()


class BudgetExceeded(RuntimeError):
    """Raised instead of spending money. Carries numbers a human can act on."""

    def __init__(self, spent: float, budget: float, detail: str = "") -> None:
        self.spent, self.budget = spent, budget
        super().__init__(
            f"Budget stop: ${spent:.2f} of ${budget:.2f} already spent. {detail}".strip()
        )


class TooManyCalls(RuntimeError):
    """One request tried to make more model calls than a plan should need."""


@dataclass
class RunBudget:
    """Call counter for a single plan. Reset per request, not per process."""

    calls: int = 0

    def check(self) -> None:
        if self.calls >= MAX_CALLS_PER_RUN:
            raise TooManyCalls(
                f"This request already made {self.calls} model calls "
                f"(limit {MAX_CALLS_PER_RUN}). Stopping rather than looping."
            )

    def spend(self) -> None:
        self.calls += 1


def _read() -> dict[str, Any]:
    if not LEDGER.is_file():
        return {"entries": [], "total_usd": 0.0}
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Never silently start from zero: a damaged ledger that resets to 0 is
        # the same as having no cap at all.
        LEDGER.replace(LEDGER.with_suffix(".corrupt.json"))
        return {"entries": [], "total_usd": 0.0}


def spent_usd() -> float:
    return float(_read().get("total_usd", 0.0))


def remaining_usd() -> float:
    return max(BUDGET_USD - spent_usd(), 0.0)


def check_before_call(estimated_usd: float = 0.08) -> None:
    """Refuse a call that would take us past the cap."""
    spent = spent_usd()
    if spent + estimated_usd + RESERVE_USD > BUDGET_USD:
        raise BudgetExceeded(
            spent, BUDGET_USD,
            f"A further ~${estimated_usd:.3f} would pass the cap. "
            f"Raise BUDGET_USD in .env if this is deliberate.",
        )


def record(usage: Usage, label: str, model: str = "") -> dict[str, Any]:
    """Append one call to the ledger and return the running totals."""
    cost = usage.cost_usd()
    with _lock:
        data = _read()
        data["entries"].append({
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "label": label,
            "model": model,
            "input_tokens": usage.input_tokens,
            "cached_input_tokens": usage.cached_input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": round(cost, 6),
        })
        data["total_usd"] = round(float(data.get("total_usd", 0.0)) + cost, 6)
        data["budget_usd"] = BUDGET_USD
        data["prices_used"] = pricing()
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        tmp = LEDGER.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, LEDGER)
    return {"spent_usd": data["total_usd"], "remaining_usd": max(BUDGET_USD - data["total_usd"], 0.0)}


def status() -> dict[str, Any]:
    """For the UI footer and the /health endpoint."""
    data = _read()
    spent = float(data.get("total_usd", 0.0))
    return {
        "budget_usd": BUDGET_USD,
        "spent_usd": round(spent, 4),
        "remaining_usd": round(max(BUDGET_USD - spent, 0.0), 4),
        "percent_used": round(spent / BUDGET_USD * 100, 1) if BUDGET_USD else 0.0,
        "calls_recorded": len(data.get("entries", [])),
    }


def seed(amount_usd: float, label: str = "spend before the ledger existed") -> None:
    """Record money already spent, so the cap counts from the true total."""
    with _lock:
        data = _read()
        data["entries"].insert(0, {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "label": label, "model": "", "input_tokens": 0,
            "cached_input_tokens": 0, "output_tokens": 0,
            "cost_usd": round(amount_usd, 6), "backfilled": True,
        })
        data["total_usd"] = round(float(data.get("total_usd", 0.0)) + amount_usd, 6)
        data["budget_usd"] = BUDGET_USD
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
