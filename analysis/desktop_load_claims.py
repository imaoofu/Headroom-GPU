"""Which paper claims read sweeps measured beside a desktop load?

    python analysis/desktop_load_claims.py [--census docs/desktop-load-census-20261003.csv] [--csv out.csv]

Joins every claim's recorded sources (audit_claims.py logs each file a claim opens) against the census
written by tools/hwinfo-logging/scan_desktop_load_corpus.py. A claim is
    LOAD     if any sweep it reads was measured beside the load (median > 30 fps presented),
    unknown  if none is LOAD but some have no surviving raw HWiNFO log,
    quiet    if every sweep it reads was checked and quiet,
    no-sweep if it reads no RTX 5060 Ti sweep (other cards, public sets, the repository itself).
Written 2026-10-03. It says which numbers stand on contaminated or uncheckable data; it does not say
whether a number is wrong. Ratios inside one session share the load; absolute values do not.
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parent


def sweepKey(source):
    """audit_claims records bare file names; the census is keyed here by sweep stem."""
    name = source.replace("\\", "/").split("/")[-1]
    for suffix in ("_sweep_voltage.csv", "_sweep.csv", "_sweep.json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--census", default=str(REPO / "docs" / "desktop-load-census-20261003.csv"))
    parser.add_argument("--csv", default=None)
    args = parser.parse_args()
    census = {}
    with open(args.census, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            census[row["sweep"].split("/")[-1][: -len("_sweep.json")]] = row["verdict"]

    import audit_claims
    import claims_consumer, claims_crosschip, claims_datasets, claims_reference, claims_repo, claims_submission  # noqa: F401,E401
    results = audit_claims.audit(audit_claims.CLAIMS)

    rows = []
    for r in results:
        verdicts = Counter()
        for s in r.get("sources") or []:
            key = sweepKey(s)
            if key is None:
                continue
            verdicts[census.get(key, "not-5060ti")] += 1
        if verdicts["LOAD"]:
            cls = "LOAD"
        elif verdicts["no-log"] or verdicts["no-column"]:
            cls = "unknown"
        elif verdicts["quiet"]:
            cls = "quiet"
        else:
            cls = "no-sweep"
        rows.append({"claimId": r["claimId"], "document": r["document"], "section": r.get("section", ""),
                     "class": cls, "load": verdicts["LOAD"], "quiet": verdicts["quiet"],
                     "unknown": verdicts["no-log"] + verdicts["no-column"], "status": r["status"],
                     "expected": (r.get("expected") or "")[:160]})
    totals = Counter(r["class"] for r in rows)
    print(f"{len(rows)} claims: " + ", ".join(f"{k} {totals[k]}" for k in ("LOAD", "unknown", "quiet", "no-sweep")))
    bySection = {}
    for r in rows:
        bySection.setdefault((r["document"], r["section"]), Counter())[r["class"]] += 1
    print("\nBy document and section (LOAD / unknown / quiet / no-sweep):")
    for (doc, sec), c in sorted(bySection.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        if c["LOAD"] or c["unknown"]:
            print(f"  {Path(str(doc)).name:14s} {str(sec):12s} {c['LOAD']:3d} / {c['unknown']:3d} / {c['quiet']:3d} / {c['no-sweep']:3d}")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            w = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nWrote {args.csv}.")


if __name__ == "__main__":
    main()
