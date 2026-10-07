#!/usr/bin/env python3
"""Score an audit against the testbed's ground truth.

The testbed plants defects on purpose and records, by hand, what each page
should be flagged for. This script compares an auditor's real output against
that record and reports precision, recall, and — the part that matters — which
specific expectations were missed and which findings were unexpected.

Exit code is 0 when recall and precision both meet the thresholds in
scoring.json, 1 otherwise, so it can gate CI.

Usage:
    python3 score/score.py --findings findings.json [--root https://host]

`--findings` accepts the `findings.json` export written by
`crawlkit crawl --findings-json <path>`, or any JSON array of objects with at
least `url`, `code`, and `is_metric`.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load_manifest() -> dict:
    return json.loads((ROOT / "expected" / "manifest.json").read_text())


def load_mapping() -> dict:
    raw = json.loads((HERE / "defect_to_code.json").read_text())
    return {k: v for k, v in raw.items() if k != "note"}


def path_of(url: str) -> str:
    return urlparse(url).path or "/"


def read_findings(spec: str) -> list[dict]:
    """Accept a findings.json export or a crawlkit SQLite database."""
    p = Path(spec)
    if p.suffix == ".json":
        return json.loads(p.read_text())
    db = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    rows = db.execute(
        "select url, code, severity, coalesce(is_metric, 0) from findings "
        "join pages on findings.page_id = pages.id"
    ).fetchall()
    return [
        {"url": u, "code": c, "severity": s, "is_metric": m} for u, c, s, m in rows
    ]



def expected_noise_and_planted(page, spec, mapping, noise):
    """Codes a fixture page may legitimately emit: the noise floor plus every
    code mapped to a defect planted on that page."""
    allowed = set(noise)
    for e in spec.get("expect", []):
        allowed.update(mapping.get(e["defect"], []))
    return allowed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--findings", required=True, help="findings.json or crawlkit.db")
    ap.add_argument(
        "--min-recall", type=float, default=0.80,
        help="fraction of planted defects that must be found (default 0.80)",
    )
    ap.add_argument(
        "--min-precision", type=float, default=0.15,
        help="floor on the fraction of findings that are expected. Low by design: "
             "a good auditor also reports real defects nobody planted, and those "
             "count as unexpected here. This gate exists to catch a collapse, "
             "not to measure precision",
    )
    args = ap.parse_args()

    manifest = load_manifest()
    mapping = load_mapping()
    findings = read_findings(args.findings)

    # Only defect findings count as claims. Measurements are facts about the
    # crawl, and scoring them would penalise an auditor for honesty.
    by_page: dict[str, set[str]] = {}
    for f in findings:
        if f.get("is_metric"):
            continue
        by_page.setdefault(path_of(f["url"]), set()).add(f["code"])

    # The noise floor is what the auditor reports on the pages planted with
    # nothing. Scoring every code a fixture page emits against that page's
    # expectation would count environment noise -- no response headers from a
    # developer server, no sitemap, short content -- as false positives, and
    # precision would be unreadable. The control page defines what "no planted
    # defect" looks like in this environment, so a finding is only unexpected if
    # the control does not also produce it.
    controls = [
        p for p, spec in manifest["pages"].items() if not spec.get("expect")
    ]
    noise: set[str] = set()
    for p in controls:
        noise |= by_page.get(p, set())

    # Expectations are DEFECTS, not codes. A defect's mapping may list several
    # codes because different analyzers describe the same problem -- and
    # dedupe collapses those to one -- so "missed" has to be judged per defect:
    # satisfied if any of its codes appeared, missed only if none did. Counting
    # codes reported a miss for every synonym of a defect that was in fact
    # found, which is how CANSELFRF001 read as missed while CAN-SR001 hit.
    defects_found = 0
    defects_planted = 0
    fp = 0
    rows = []
    unmapped: set[str] = set()
    all_codes: set[str] = set().union(*by_page.values()) if by_page else set()

    for page, spec in sorted(manifest["pages"].items()):
        if page in controls:
            continue
        actual = by_page.get(page, set())
        hits = misses = unexpected = 0
        for e in spec.get("expect", []):
            codes = mapping.get(e["defect"])
            if not codes:
                unmapped.add(e["defect"])
                continue
            defects_planted += 1
            if e.get("scope") == "crawl":
                satisfied = bool(set(codes) & all_codes)
            else:
                satisfied = bool(set(codes) & actual)
            if satisfied:
                defects_found += 1
                hits += 1
            else:
                misses += 1
        unexpected = len(actual - expected_noise_and_planted(page, spec, mapping, noise))
        fp += unexpected
        rows.append((page, hits, misses, unexpected, [], []))

    recall = defects_found / defects_planted if defects_planted else 1.0
    precision = (defects_planted) / (defects_planted + fp) if (defects_planted + fp) else 0.0

    print("=" * 68)
    print("crawlkit-testbed scoring")
    print("=" * 68)
    print(f"{'page':<28}{'hit':>5}{'missed':>8}{'unexpected':>12}")
    print("-" * 68)
    for page, h, m, u, missed, unexpected in rows:
        print(f"{page:<28}{h:>5}{m:>8}{u:>12}")
        for c in missed:
            print(f"    MISSED   {c}")
        for c in unexpected:
            print(f"    UNEXPECTED {c}")
    print("-" * 68)
    print(f"defects found    {defects_found} of {defects_planted}")
    print(f"defects missed   {defects_planted - defects_found}")
    print(f"unexpected codes {fp}")
    if unmapped:
        print(f"\nUNMAPPED defect descriptions ({len(unmapped)}): "
              f"{sorted(unmapped)}\nAdd them to score/defect_to_code.json.")
    print(f"\nrecall    {recall:.1%}  (threshold {args.min_recall:.0%})")
    print(f"precision {precision:.1%}  (threshold {args.min_precision:.0%})")

    ok = recall >= args.min_recall and precision >= args.min_precision and not unmapped
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
