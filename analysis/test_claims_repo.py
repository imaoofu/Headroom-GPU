"""
Tests for the environment split in claims_repo.py.

WHY THIS FILE EXISTS
    claims_repo pins CLAUDE.md's own registry counts, and `len(CLAIMS)` means a DIFFERENT number
    depending on whether `data/raw/` is present - 208 with it, 180 without. So the module registers
    the with-reference total in one environment and the without-reference total in the other, and
    exactly one of them must ever exist.

    That guard was written correctly and then immediately broken by an edit: a fourth claim,
    appended to the end of the file on 2026-09-05, landed inside the `else:` branch instead of the
    `if`. In the environment it was tested in, it simply never registered - the audit passed, said
    208 of 208, and looked entirely healthy. It would have failed the OTHER CI leg, where it would
    have rendered a count computed without the reference claims and compared it to a paper that
    says 18.

    An indentation mistake that is invisible in one environment and fatal in the other is exactly
    the defect class this repo keeps finding, and it is not visible to the claims themselves: a
    claim that does not register cannot fail. So these tests assert the SHAPE of the registration
    rather than the values.

RUN
    python analysis/test_claims_repo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_claims                                     # noqa: E402
import claims_consumer                                  # noqa: E402,F401 - registers claims
import claims_crosschip                                 # noqa: E402,F401 - registers claims
import claims_repo                                      # noqa: E402

CHECKS = []


def check(description):
    def register(function):
        CHECKS.append((description, function))
        return function
    return register


def _ids():
    return {c["claimId"] for c in audit_claims.CLAIMS}


@check("exactly one of the two environment-dependent total claims is registered")
def onlyOneTotalRegisters():
    present = _ids() & {"claudemd-claims-with-reference", "claudemd-claims-without-reference"}
    assert len(present) == 1, f"expected exactly one total claim, got {sorted(present)}"


@check("the registered total claim matches the environment it registered for")
def totalMatchesEnvironment():
    expected = ("claudemd-claims-with-reference" if claims_repo._referenceDataPresent()
                else "claudemd-claims-without-reference")
    assert expected in _ids(), f"{expected} did not register"


@check("the total claim renders the live registry size, not a stored number")
def totalIsComputed():
    """The whole point of a claim is that it recomputes. A hardcoded string would pass the audit
    on the day it was written and never fail afterwards, which is the failure mode audit_claims
    was built to prevent - so assert the rendered value TRACKS the registry."""
    claim = next(c for c in audit_claims.CLAIMS
                 if c["claimId"].startswith("claudemd-claims-"))
    before = claim["render"]()
    audit_claims.CLAIMS.append({"claimId": "_probe", "document": "x", "section": None,
                                "render": lambda: "", "mixedProvenance": None})
    try:
        after = claim["render"]()
    finally:
        audit_claims.CLAIMS.pop()
    assert before != after, f"render did not track the registry: {before!r} both times"


@check("every claims_repo claim that reads unaudited sections is guarded on the reference data")
def unauditedClaimsAreGuarded():
    """unauditedSections() moves with the registry, because dropping claims_reference reverts the
    sections IT pins to unaudited. Any such claim registering in BOTH environments would render
    two different numbers against one document and fail one leg. This is the bug that prompted
    the file."""
    if claims_repo._referenceDataPresent():
        return  # the guarded branch is the one that runs; nothing to prove here
    leaked = _ids() & {"claudemd-unaudited-sections", "header-unaudited-count",
                       "claudemd-section-families"}
    assert not leaked, f"reference-dependent claims registered without data/raw: {sorted(leaked)}"


@check("the section-family counter distinguishes a section from one that merely shares a prefix")
def familyPrefixIsExact():
    """_familyCount('5.7') must count 5.7 and 5.7.x and NOT a hypothetical 5.70. String
    startswith('5.7') would match both; the implementation appends the dot for that reason."""
    original = list(audit_claims.CLAIMS)
    audit_claims.CLAIMS.clear()
    try:
        for section in ("5.7", "5.7.1", "5.70", "5.5"):
            audit_claims.CLAIMS.append({"claimId": f"_p{section}", "document": "x",
                                        "section": section, "render": lambda: "",
                                        "mixedProvenance": None})
        assert claims_repo._familyCount("5.7") == 2, "5.70 must not count as a 5.7 subsection"
    finally:
        audit_claims.CLAIMS.clear()
        audit_claims.CLAIMS.extend(original)


def main():
    failures = 0
    for description, function in CHECKS:
        try:
            function()
            print(f"[PASS] {description}")
        except AssertionError as error:
            failures += 1
            print(f"[FAIL] {description}\n       {error}")
    print("ALL CHECKS PASSED" if not failures else f"{failures} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
