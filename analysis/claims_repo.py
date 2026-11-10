"""Claims about the REPOSITORY's own state, pinned against CLAUDE.md.

WHY THIS MODULE IS NOT SPLIT BY HARDWARE LIKE THE OTHER THREE
    claims_consumer / claims_crosschip / claims_reference are split by which CARD the data came
    from, because a shared constant between them is how a claim would silently read the wrong
    hardware. Nothing here reads hardware at all - these claims read the claims registry and the
    paper's own headings. A fourth hardware module would be the wrong shape; this is a different
    axis, and it says so rather than being inferred.

WHY CLAUDE.md IS AUDITED AT ALL
    Its claim count went stale four times - 87 -> 119 -> 185 -> 204 - and on 2026-08-30 it carried
    TWO CONTRADICTORY counts for one quantity simultaneously, which is worse than one stale number
    because neither can be trusted and nothing flags which is which. The file already tells readers
    to run --coverage instead of believing it. This makes that instruction unnecessary for the four
    numbers below, which is better than repeating it.

    ⚠️ WHAT THIS DELIBERATELY DOES NOT DO. It pins NUMBERS, never sentences. CLAUDE.md is the file
    that gets edited most and edited fastest, and an auditor that fails on a rephrased clause would
    be a tax on the thing the file is for. Every claim here renders the shortest substring that
    contains the digits and nothing else.

    It also cannot pin the check count from `run_tests.py`. That number is produced by a different
    runner counting a different thing, and a second implementation of it here would be two counting
    methods that can disagree - the exact failure this project keeps finding. CLAUDE.md points at
    `run_tests.py` for that one instead.

🔑 THE ENVIRONMENT SPLIT, AND WHY IT IS ONE CLAIM PER LEG RATHER THAN TWO EVERYWHERE
    `data/raw/` is gitignored and fetched, so claims_reference registers its 28 claims only when it
    is present, and the registry is 25 larger there once header-pinned-count is counted. A claim
    can therefore only honestly pin the total for the environment it is RUNNING in - `len(CLAIMS)`
    is the with-reference total in one leg and the without-reference total in the other, and there
    is no way to compute the other one that is not a hardcoded subtraction pretending to be a
    measurement.

    So exactly one of the two total claims registers in any given run, and each CI leg verifies its
    own number. Between them both figures in CLAUDE.md's table are covered, and neither is guessed.
    An unguarded version of this idea broke both checks legs on 2026-09-02.
"""

import collections
import pathlib

from audit_claims import CLAIMS, claim, unauditedSections

CLAUDE = "CLAUDE.md"
PAPER = "docs/PAPER_DRAFT.md"

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _referenceDataPresent():
    """Whether the FETCHED datasets are present, and therefore which total the registry represents.

    Defined here rather than imported from claims_consumer on purpose. It reads no hardware, and
    importing it would couple this module to a hardware module for no gain - the coupling that
    CLAUDE.md's "keep them apart" rule exists to prevent.

    ⚠️ TWO datasets since 2026-09-13, not one. claims_datasets.py registers section 2.7 against
    the published consumer sets under data/external/, which are fetched and gitignored exactly as
    data/raw/ is, so the registry size now depends on both. An environment holding one but not the
    other registers NEITHER total and says so below, rather than pinning a number that describes
    no CI leg - a partial fetch producing a plausible-looking count is precisely the failure the
    guarded totals exist to prevent.
    """
    return ((_REPO_ROOT / "data" / "raw" / "dataset_performance.csv").exists()
            and (_REPO_ROOT / "data" / "external" / "all-gpus.json").exists())


def _partialFetch():
    """One of the two fetched datasets present and the other missing."""
    raw = (_REPO_ROOT / "data" / "raw" / "dataset_performance.csv").exists()
    external = (_REPO_ROOT / "data" / "external" / "all-gpus.json").exists()
    return raw != external


def _sectionsWithClaims():
    """The (document, section) pairs the audit engine would consider audited.

    unauditedSections() takes audit RESULTS, but uses only these two fields of them, so this
    builds the same shape straight from the registry. Auditing from inside a claim would recurse.
    """
    return [{"document": c["document"], "section": c.get("section")} for c in CLAIMS]


def _familyCount(prefix):
    """Claims attributed to a section or any of its subsections."""
    return sum(1 for c in CLAIMS
               if c.get("section") and (c["section"] == prefix
                                        or c["section"].startswith(prefix + ".")))


if _referenceDataPresent():

    @claim("claudemd-claims-with-reference", CLAUDE)
    def claimsWithReference():
        """The complete registry, which is what a local run and the V100 reference CI leg see."""
        return f"**{len(CLAIMS)} of {len(CLAIMS)}**"

    @claim("claudemd-unaudited-sections", CLAUDE)
    def unauditedSectionCount():
        """Sections with no claim at all.

        Guarded with the rest because it moves with the registry: without claims_reference the
        sections IT pins revert to unaudited, so this number is environment-dependent for the
        same reason the totals are.
        """
        count = len(unauditedSections([PAPER], _sectionsWithClaims()))
        return f"**{count} numbered sections are still unaudited**"

    @claim("claudemd-section-families", CLAUDE)
    def sectionFamilyCounts():
        """The unevenness, which is the useful part - see the sentence this pins.

        ⚠️ THE FIGURES THIS REPLACED DID NOT REPRODUCE. CLAUDE.md carried "§5.7 ... 80 claims ...
        §5.5 carries 53" and neither survives any counting method tried: by registry attribution
        the families are 84 and 30, and by pinned-numbers they are far larger. The derivation was
        never written down, so it could not be checked, and a figure nobody can reproduce is worse
        than one that is merely out of date. Counted here by section attribution, stated in the
        docstring so the method travels with the number.
        """
        return f"**{_familyCount('5.7')} claims between them and §5.5 carries {_familyCount('5.5')}**"

    @claim("header-unaudited-count", PAPER)
    def paperHeaderUnauditedCount():
        """The paper header's own count of sections carrying no claims.

        ⛔ THE PAPER SAID THIS COULD NOT BE PINNED, AND THE REASON IT GAVE WAS FALSE. It read:
        "it is computed from the audit results rather than during them, so a claim cannot reach it
        without circularity." There is no circularity - unauditedSections() uses only the
        (document, section) pairs of its results argument, and those come straight off the
        registry, which is fully populated by import time. _sectionsWithClaims() builds exactly
        that shape without auditing anything.

        The header also contradicted itself while asserting this: it said "18 numbered sections"
        and then called it "that 19" two lines later, because the figure had been corrected in one
        place and not the other. Which is the failure the whole auditor exists to prevent, sitting
        in the paragraph describing the auditor.
        """
        count = len(unauditedSections([PAPER], _sectionsWithClaims()))
        return f"**{count} numbered sections carry no claims at all**"

elif _partialFetch():
    print("  [SKIP] claims_repo: exactly one of data/raw/ and data/external/ is present. Neither "
          "registry total is pinned in this environment, because neither CI leg looks like it - "
          "run scripts/Get-Dataset.ps1 with no -Only, or move the other aside too.")

else:

    @claim("claudemd-claims-without-reference", CLAUDE)
    def claimsWithoutReference():
        """The registry as the "checks" CI leg sees it, with both fetched datasets absent."""
        return f"**{len(CLAIMS)} of {len(CLAIMS)}**"



# -------------------------------------------------------------------------------------------
# The dataset size, pinned at last. UNGUARDED on purpose: data/frequency-sweeps is committed,
# not fetched, so this claim registers identically in both CI legs and in a fresh clone.
#
# 🔑 WHY IT IS HERE AND NOT IN A DATA MODULE. It is a fact about the repository's own contents -
# how many sweeps it ships - which is this module's axis. The other four data modules pin what
# the sweeps MEASURED; this pins how many there are.
#
# ⛔ "359" SAT IN THE ABSTRACT UNPINNED FROM 2026-09-12 TO 09-14, and it got there by being
# incremented rather than recounted: the line previously read 342, a 2060 Super arrived with 17
# sweeps, and 342 + 17 was written down. That is exactly how this file's own claim total went
# stale four times. The number happened to be right - build_data_manifest.py reconciles it
# exactly - but nothing could have told anyone that, which is the part this fixes.

@claim("paper-dataset-grade-total", PAPER, "Abstract")
def datasetGradeSweepTotal():
    """The abstract's headline dataset size, recomputed from the tree at audit time."""
    import build_data_manifest

    manifest = build_data_manifest.buildManifest(build_data_manifest.loadSessions())
    datasetGrade = sum(1 for entry in manifest if entry["category"] == "dataset-grade")
    verification = sum(1 for entry in manifest if entry["category"] == "verification")
    # ⛔ This rendered "{datasetGrade + verification} dataset-grade sweeps" until 2026-09-26: it
    # called the three verification runs dataset-grade, the adjective the manifest denies them.
    # Found by GPT Job 23; the formula carried the paper's error rather than catching it.
    return (f"**{datasetGrade + verification} sweeps across four chips and three "
            f"architectures**, of which {datasetGrade} are dataset-grade")


@claim("paper-dataset-grade-per-card", PAPER, "Abstract")
def datasetGradePerCard():
    """The per-card breakdown, so the total cannot drift away from its own components.

    Pinned separately because the total was right while one component was not: a wrong exclusion
    rule put the 5060 Ti at 298 and the other three cards at their correct values, and only the
    per-card view showed which one to go looking at.
    """
    import build_data_manifest

    manifest = build_data_manifest.buildManifest(build_data_manifest.loadSessions())
    counts = collections.Counter(entry["gpu"] for entry in manifest
                                 if entry["category"] == "dataset-grade")
    return (f"{counts['NVIDIA GeForce RTX 5060 Ti']} on\nan RTX 5060 Ti (Blackwell GB206), "
            f"{counts['NVIDIA GeForce RTX 3070 Ti']} on an RTX 3070 Ti (Ampere GA104), "
            f"{counts['NVIDIA GeForce RTX 2060 SUPER']} on an RTX 2060 Super")


@claim("6-flagged-sweeps", PAPER, "6")
def flaggedDatasetGradeSweeps():
    """Section 6's provenance paragraph: how many dataset-grade sweeps carry a flag (2026-09-28)."""
    import build_data_manifest

    manifest = build_data_manifest.buildManifest(build_data_manifest.loadSessions())
    datasetGrade = [entry for entry in manifest if entry["category"] == "dataset-grade"]
    flagged = sum(1 for entry in datasetGrade if entry["flags"])
    return f"{flagged} of the {len(datasetGrade)} dataset-grade sweeps carry at least one flag"
