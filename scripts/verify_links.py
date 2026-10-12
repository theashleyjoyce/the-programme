"""Pre-verify every venue link, offline, so requests never wait on one.

Fetches each venue's site once and records whether the page actually names
the venue. backend/linkcheck.py then answers from that cache instantly, and
anything unverified simply shows no button.

    python scripts/verify_links.py --limit 400
    python scripts/verify_links.py --report
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from config import DATA_DIR          # noqa: E402
from linkcheck import stats, verify  # noqa: E402

CANDIDATES = DATA_DIR / "candidate_venues.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-verify venue booking links.")
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    if args.report:
        print(stats())
        return 0

    venues = json.loads(CANDIDATES.read_text())["venues"]
    todo = [v for v in venues if v.get("website")][:args.limit]
    print(f"checking {len(todo)} venues\n")

    ok = bad = 0
    for i, v in enumerate(todo, 1):
        good = verify(v["website"], v["name"])
        ok, bad = ok + good, bad + (not good)
        mark = "ok  " if good else "DROP"
        print(f"  {mark} {v['name'][:30]:32} {v['website'][:46]}", flush=True)
        if i % 25 == 0:
            print(f"       … {i}/{len(todo)}  {ok} verified, {bad} rejected", flush=True)
        time.sleep(0.1)

    print(f"\n{ok} verified, {bad} rejected")
    print(stats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
