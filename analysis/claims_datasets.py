"""Claims over the PUBLISHED CONSUMER datasets - section 2.7.

WHY THIS MODULE EXISTS, AND WHAT IT IS AN APOLOGY FOR
    Section 2.7 was one of the paper's unaudited sections, and on 2026-09-13 it produced two
    retractions in a single day. Both were about the same sentence, and neither could have been
    caught by anything in this repository:

      1. "the released consumer data sweeps at or above stock" - read off a *-features.csv, whose
         frequency columns are normalised multipliers, rather than the *-Performance-Power.csv
         the analysis actually loads. The release contains GTX 980 sweeps from 400 MHz.
      2. "every consumer part later than Maxwell sweeps at or above stock" - computed against the
         RATED BOOST CLOCK from a specs database. That describes a reference card. The dataset
         authors state the default operating clock of the cards they used, and against those
         numbers each sweep BRACKETS its default, with two of five core points below it.

    The second error was reproducible: compare_consumer.py and the paper agreed exactly, because
    both computed it the same wrong way from the same wrong reference. Reproducibility guarantees
    agreement, not correctness. What was missing was a claim rendering a string a reader could
    dispute, which is what this module adds.

WHY IT IS A FOURTH DATA MODULE
    The existing three split by STUDY: this project's own sweeps, the 3070 Ti two-BIOS comparison,
    and the public V100 set. These claims are over a fourth body of data - consumer DVFS sets
    published by others, under data/external/ - and read by nothing else here.

WHY IT CAN REGISTER NOTHING
    data/external/ is gitignored and fetched by scripts/Get-Dataset.ps1. A missing file registers
    nothing and says so, the same contract claims_reference.py has for data/raw/. THE SKIP IS NOT
    A PASS. CI's "V100 reference claims" job fetches these sets so that some machine checks them;
    it did not until this module existed.
"""

import json

import pandas as pd

from audit_claims import claim, REPO_ROOT

PAPER = "docs/PAPER_DRAFT.md"
EXTERNAL = REPO_ROOT / "data" / "external"

# The DEFAULT OPERATING CLOCK the dataset authors declare for the cards they actually used, from
# the README of HKBU-HPML/GPU-DVFS-Job-Schedule ("Base Core Frequency (MHz)") - the repository
# scripts/Get-Dataset.ps1 downloads both of these files from.
#
# These are the numbers that corrected section 2.7, so they are stated here with their source
# rather than derived from a specs database. Each lands exactly on a swept grid point in BOTH
# axes, which is what identifies it as the centre of the sweep rather than a nominal figure -
# and that is asserted below rather than assumed.
DECLARED_DEFAULT_MHZ = {"gtx1080ti": (1800, 5000), "gtx2070s": (1880, 6300)}

FILES = {
    "gtx1080ti": "gtx1080ti-dvfs-real-Performance-Power.csv",
    "gtx2070s": "gtx2070s-dvfs-real-Performance-Power.csv",
}

SPEC_NAMES = {"gtx1080ti": "GeForce GTX 1080 Ti", "gtx2070s": "GeForce RTX 2070 SUPER"}


def _load():
    """Every file these claims read. Returns None if any of them is absent."""
    frames = {}
    for key, filename in FILES.items():
        path = EXTERNAL / filename
        if not path.exists():
            return None
        frames[key] = pd.read_csv(path)

    specs = EXTERNAL / "all-gpus.json"
    if not specs.exists():
        return None
    raw = json.load(open(specs, encoding="utf-8"))
    rows = raw if isinstance(raw, list) else raw.get("gpus", [])
    byName = {row.get("name"): row for row in rows}
    frames["boost"] = {key: byName[name]["boostClock"] for key, name in SPEC_NAMES.items()}
    return frames


DATA = _load()

if DATA is None:
    print("  [SKIP] claims_datasets: the published consumer sets are not downloaded - run "
          "scripts/Get-Dataset.ps1. Section 2.7 is NOT audited in this run.")
else:

    def coreFrequencies(key):
        return sorted(int(f) for f in DATA[key]["coreF"].unique())

    # ------------------------------------------------------------ 2.7 the swept ranges
    # Absolute megahertz, read from the Performance-Power files. The first retraction came from
    # reading a different file in the same release, so these are pinned in MHz rather than in the
    # normalised units that caused it.

    @claim("2.7-1080ti-range", PAPER, "2.7")
    def range1080ti():
        core = coreFrequencies("gtx1080ti")
        return f"| Wang & Chu [21] | Titan X, GTX 1080 Ti | {core[0]}–{core[-1]} MHz |"

    @claim("2.7-2070s-range", PAPER, "2.7")
    def range2070s():
        core = coreFrequencies("gtx2070s")
        return f"| Wang *et al.* [22] | RTX 2070 Super | {core[0]}–{core[-1]} MHz |"

    # ------------------------------------------------------------ 2.7 the corrected comparison
    # The whole point of the second retraction is that the same sweep read against the two
    # available references gives opposite answers. Both are pinned, so the paper cannot quote
    # one without the other and cannot drop the reference-card row to tidy the table.

    @claim("2.7-1080ti-vs-boost", PAPER, "2.7")
    def boost1080ti():
        core, boost = coreFrequencies("gtx1080ti"), DATA["boost"]["gtx1080ti"]
        return f"| {100 * core[0] / boost:.0f}–{100 * core[-1] / boost:.0f}% |"

    @claim("2.7-1080ti-vs-declared", PAPER, "2.7")
    def declared1080ti():
        core, base = coreFrequencies("gtx1080ti"), DECLARED_DEFAULT_MHZ["gtx1080ti"][0]
        return f"| **{100 * core[0] / base:.0f}–{100 * core[-1] / base:.0f}%** ({base} MHz) |"

    @claim("2.7-2070s-vs-declared", PAPER, "2.7")
    def declared2070s():
        core, base = coreFrequencies("gtx2070s"), DECLARED_DEFAULT_MHZ["gtx2070s"][0]
        return f"| **{100 * core[0] / base:.0f}–{100 * core[-1] / base:.0f}%** ({base} MHz) |"

    # ------------------------------------------------------------ 2.7 below-default coverage
    # "Two of five core frequencies sitting below it" is the sentence that replaced "at or above
    # stock only". It is arithmetic over the swept grid and the declared default, so it is pinned
    # as arithmetic. Both datasets happen to share the shape; if they stop sharing it the claim
    # raises rather than silently reporting one of them.

    @claim("2.7-below-default-count", PAPER, "2.7")
    def belowDefaultCount():
        shapes = set()
        for key, (base, _) in DECLARED_DEFAULT_MHZ.items():
            core = coreFrequencies(key)
            shapes.add((len([f for f in core if f < base]), len(core)))
        if len(shapes) != 1:
            raise AssertionError(
                f"the two datasets no longer share a below-default shape: {shapes}. The paper "
                f"states one figure for both, so it needs rewriting rather than re-rendering.")
        below, total = shapes.pop()
        words = {2: "two", 3: "three", 4: "four", 5: "five"}
        return (f"**{words.get(below, below)} of {words.get(total, total)} core frequencies "
                f"sitting below")

    @claim("2.7-declared-floor-pct", PAPER, "2.7")
    def declaredFloorPercent():
        floors = set()
        for key, (base, _) in DECLARED_DEFAULT_MHZ.items():
            floors.add(round(100 * coreFrequencies(key)[0] / base))
        if len(floors) != 1:
            raise AssertionError(f"the two sweeps no longer share a floor: {floors}")
        return f"down to {floors.pop()}%"

    # ------------------------------------------------------------ the constant's own guard
    # Not a sentence of the paper - a guard on DECLARED_DEFAULT_MHZ above. The reason 1800 and
    # 1880 are believed to be the sweeps' centre, rather than a nominal spec quoted in a README,
    # is that each falls exactly on a swept grid point in BOTH axes. If that ever stopped being
    # true the constant would be unsupported and every claim above would be measuring against
    # nothing, while still rendering a plausible string.

    @claim("2.7-declared-defaults-are-grid-points", PAPER, "2.7")
    def declaredDefaultsAreGridPoints():
        for key, (baseCore, baseMemory) in DECLARED_DEFAULT_MHZ.items():
            core = set(int(f) for f in DATA[key]["coreF"].unique())
            memory = set(int(f) for f in DATA[key]["memF"].unique())
            if baseCore not in core or baseMemory not in memory:
                raise AssertionError(
                    f"{key}: the authors' declared default ({baseCore} core / {baseMemory} "
                    f"memory) is no longer a swept grid point, so it cannot be read as the centre "
                    f"of the sweep. core={sorted(core)} memory={sorted(memory)}")
        return "fall exactly on a swept grid point"
