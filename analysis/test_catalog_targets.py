"""Census of the committed bench run lists against the explicit-target rule of 2026-09-30.

The rule is ENFORCED by tools/bench-app/Test-Plan.ps1: a known-card run list that applies a
profile must give every suite a targetsMhz list, or carry card.legacyDerivedGrids with a stated
reason. Its PowerShell tests live in test_bench_app.py and need PowerShell. This file needs none:
it reads the committed catalogs and pins WHICH of them may carry the exemption, so a new run list
cannot add itself to the list without this file changing in the same commit.

Why the rule exists: a grid derived from the card's supported-clock table moved under two
registered tests, overnight on the RTX 3070 Ti (Session D2, 8d NOT SCOREABLE) and under an offset
profile on the RTX 2060 Super (Session E, 4c-offset NOT SCOREABLE). A lesson written down after the
first did not prevent the second.
"""

import json
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "tools" / "bench-app" / "catalog"

# Written before the rule. Adding a name here needs a reason in the run list itself.
EXEMPT = {"localtest-5060ti.json", "sessiond-3070ti.json", "sessiond2-3070ti.json",
          "sessione-2060s.json", "shakedown-3070ti.json"}


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def steps(plan, kind):
    return [step for run in plan["runs"] for step in run["steps"] if step.get("type") == kind]


def main():
    plans = {path.name: json.loads(path.read_text(encoding="utf-8-sig"))
             for path in sorted(CATALOG.glob("*.json"))}
    check(len(plans) >= 7, f"the committed run lists are found ({len(plans)})")

    exempt = set()
    for name, plan in plans.items():
        card = plan["card"]
        reason = str(card.get("legacyDerivedGrids") or "")
        derived = [s["label"] for s in steps(plan, "suite") if not s.get("targetsMhz")]
        needs = not card.get("generic") and bool(steps(plan, "apply-profile")) and bool(derived)
        if reason:
            exempt.add(name)
        if needs:
            check(reason.strip() != "", f"{name}: applies a profile with derived suites, so it states a reason")
        else:
            check(not reason, f"{name}: needs no exemption and carries none")

    check(exempt == EXEMPT, f"exactly the pre-rule run lists are exempt: {sorted(exempt)}")
    for name in sorted(EXEMPT - {"localtest-5060ti.json"}):
        check(plans[name].get("retired") is True, f"{name}: exempt, and retired, so it never runs again")
    check("not measurement-grade" in plans["localtest-5060ti.json"]["title"],
          "the one active exempt list is the engine smoke test, not measurement-grade")
    e2 = plans["sessione2-2060s.json"]
    check("legacyDerivedGrids" not in e2["card"] and all(s.get("targetsMhz") for s in steps(e2, "suite")),
          "Session E2, the re-run the rule is modelled on, states every target and has no exemption")


if __name__ == "__main__":
    main()
