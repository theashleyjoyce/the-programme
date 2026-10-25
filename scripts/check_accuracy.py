"""Check the report and slides against the app they describe.

Run this before submitting, and after any change to the app. A report is only
worth the trust it earns, and a single number that no longer matches reality
costs more than it gains.

It has already caught two real errors: a terminal colour code printed as the
guardrail count, and a claim of thirteen kinds of evening after the form had
grown to nineteen. That second one is gone for good: counting the kinds was
both corny and limiting, so the docs describe the range instead of sizing it.

    python scripts/check_accuracy.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from planner import catalogue        # noqa: E402
from sources import dataset_status   # noqa: E402

G, R, Y, X = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def main() -> int:
    report = (ROOT / "report.html")
    slides = (ROOT / "slides.html")
    if not report.is_file() or not slides.is_file():
        print(f"{R}Build them first: python scripts/build_report.py{X}")
        return 1

    rep, sld = report.read_text(), slides.read_text()
    D = dataset_status()
    out = subprocess.run([sys.executable, "-I", str(ROOT / "test_guardrails.py")],
                         capture_output=True, text=True, cwd=ROOT)
    clean = re.sub(r"\x1b\[[0-9;]*m", "", out.stdout)
    m = re.search(r"(\d+)\s+passed,\s+(\d+)\s+failed", clean)
    passed, failed = (int(m.group(1)), int(m.group(2))) if m else (0, -1)

    led = json.loads((ROOT / "output" / "spend_ledger.json").read_text())

    checks = [
        ("venues in the report", f"{D['venues_known']:,}" in rep, f"{D['venues_known']:,}"),
        ("venues in the slides", f"{D['venues_known']:,}" in sld, f"{D['venues_known']:,}"),
        ("neighbourhoods", str(D["neighborhoods"]) in rep, str(D["neighborhoods"])),
        ("guardrails, report", f">{passed}</span>" in rep, str(passed)),
        ("guardrails, slides", f"{passed} guardrails" in sld, str(passed)),
        ("every guardrail passes", failed == 0, f"{failed} failing"),
        ("no placeholder repo URL", "YOUR-USERNAME" not in rep, "set REPO_URL"),
        ("no missing screenshots", "SCREENSHOT TO ADD" not in rep, "add them"),
        ("prices are the checked ones",
         abs(led.get("prices_used", {}).get("input_per_m", 0) - 0.20) < 1e-9,
         str(led.get("prices_used"))),
    ]

    bad = 0
    print(f"\n{'check':30} {'state':8} detail")
    print("-" * 66)
    for label, good, detail in checks:
        bad += not good
        colour = G if good else R
        print(f"{label:30} {colour}{'ok' if good else 'STALE':8}{X} {detail}")

    print()
    if bad:
        print(f"{R}{bad} thing(s) out of date. Rerun build_report.py and "
              f"build_slides.py, then fix whatever remains.{X}")
    else:
        print(f"{G}Report and slides match the app.{X}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
