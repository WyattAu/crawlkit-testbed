#!/usr/bin/env python3
"""Census the live dogfood targets and compare against the last baseline.

A planted-defect fixture set proves an auditor finds defects that are there. It
cannot tell you whether the *next* commit changes what the auditor says about a
real site, because real sites are nobody's fixture. This script is the other
half: it counts findings per code per site, and diffs that against the last
committed baseline, so a change in crawler behaviour shows up as a number moving
rather than as a vague impression that something shifted.

Live sites are content-churning by nature, so deltas are **reported, not
failed**. A 30% move in `TITLE002` is interesting; it is not proof of a
regression. The only hard failure is a site that crawls to zero pages, because
that means the target moved, the crawler broke, or the run is comparing
nothing.

Usage:
    python3 score/live.py --run run/ --baseline baselines/census.json \
                          --out census.json [--summary summary.md]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Deltas beyond this are flagged in the summary. Flagging is informational: the
# point is to make a change visible, not to gate on a number a site's own edit
# can move.
FLAG_DELTA = 0.25
# Small absolute counts swing wildly in percentage terms -- one fewer finding
# out of three is -33%. A code must move by at least this many findings to be
# flagged at all.
FLAG_MIN_ABS = 5


def census_db(db: Path) -> dict:
    """Findings-per-code and page count from one crawlkit database."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        pages = con.execute("select count(*) from pages").fetchone()[0]
        rows = con.execute(
            "select code, count(*) from findings f "
            "join pages p on f.page_id = p.id "
            "where coalesce(f.is_metric, 0) = 0 group by code"
        ).fetchall()
    finally:
        con.close()
    return {"pages": pages, "codes": {c: n for c, n in rows}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="directory holding <name>/crawlkit.db per target")
    ap.add_argument("--baseline", required=True, help="previous census.json, if any")
    ap.add_argument("--out", required=True, help="where to write the new census")
    ap.add_argument("--summary", help="optional markdown step summary to write")
    ap.add_argument("--index", default=str(ROOT / "targets" / "index.json"))
    args = ap.parse_args()

    index = json.loads(Path(args.index).read_text())["targets"]
    run = Path(args.run)

    census: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sites": {},
    }
    failures: list[str] = []
    for t in index:
        db = run / t["name"] / "crawlkit.db"
        if not db.exists():
            failures.append(f"{t['name']}: no crawlkit.db produced")
            continue
        c = census_db(db)
        if c["pages"] == 0:
            failures.append(f"{t['name']}: crawled 0 pages")
        census["sites"][t["name"]] = c

    Path(args.out).write_text(json.dumps(census, indent=2, sort_keys=True) + "\n")

    # ---- comparison -----------------------------------------------------
    baseline: dict = {}
    bp = Path(args.baseline)
    if bp.exists():
        baseline = json.loads(bp.read_text()).get("sites", {})

    lines = ["| site | code | before | after | delta |", "|---|---|---:|---:|---:|"]
    flagged = 0
    for t in index:
        name = t["name"]
        now = census["sites"].get(name, {})
        was = baseline.get(name, {})
        codes = set(now.get("codes", {})) | set(was.get("codes", {}))
        for code in sorted(codes):
            b, a = was.get("codes", {}).get(code, 0), now.get("codes", {}).get(code, 0)
            if b == a:
                continue
            pct = (a - b) / b if b else 1.0
            if abs(a - b) >= FLAG_MIN_ABS and abs(pct) >= FLAG_DELTA:
                flagged += 1
                lines.append(f"| {name} | {code} | {b} | {a} | {pct:+.0%} |")

    total_now = sum(s["pages"] for s in census["sites"].values())
    md = [
        "# Live-target census",
        "",
        f"Generated {census['generated_at']}.",
        f"Sites: {len(census['sites'])} · pages crawled: {total_now} · "
        f"flagged code movements: {flagged} · failures: {len(failures)}",
        "",
    ]
    if lines:
        md += lines
    else:
        md.append("No code moved beyond the flagging threshold.")
    if failures:
        md += ["", "## Failures", ""] + [f"- {f}" for f in failures]

    text = "\n".join(md) + "\n"
    print(text)
    if args.summary:
        Path(args.summary).write_text(text)

    for f in failures:
        print(f"FAILURE: {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
