"""Shared style and data access for the submission figures.

Every figure is drawn from the committed CSVs by a script in this directory, so a figure cannot
drift from the data it shows. Output goes to docs/submission/figures/ as PDF (for the paper) and
PNG (for review).

Style follows the repository's dataviz rules for a static print figure: light surface only, one
y-axis per panel (never a second scale), thin marks, recessive grid, a legend whenever there are
two or more series, and markers or dashes as secondary encoding so a grayscale print still reads.
Colours are slots 1 and 2 of the validated reference palette, plus neutral inks for references.
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SWEEPS = REPO / "data" / "frequency-sweeps"
OUT = REPO / "docs" / "submission" / "figures"
sys.path.insert(0, str(REPO / "analysis"))
sys.path.insert(0, str(REPO / "analysis" / "models"))

# Validated with the dataviz skill's validator, --mode light --pairs all (2026-09-28).
BLUE = "#2a78d6"      # categorical slot 1: the treatment, or the quantity of interest
ORANGE = "#eb6834"    # categorical slot 2: a second treatment (the control)
INK = "#0b0b0b"       # primary text
INK_2 = "#52514e"     # secondary text; also the stock/reference series
INK_3 = "#898781"     # muted: reference lines
GRID = "#e4e3df"
SURFACE = "#fcfcfb"

# IEEE two-column: one column is 3.5 in, the full width 7.16 in.
COLUMN_IN = 3.5
FULL_IN = 7.16


def style():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial"],
        "font.size": 7.5,
        "axes.titlesize": 8,
        "axes.labelsize": 7.5,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 6.8,
        "axes.edgecolor": INK_3,
        "axes.labelcolor": INK,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.facecolor": SURFACE,
        "figure.facecolor": "white",
        "lines.linewidth": 1.2,
        "lines.markersize": 3.5,
        "legend.frameon": False,
        "pdf.fonttype": 42,
        "savefig.dpi": 300,
    })


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / name}.pdf and .png")


def one(pattern, base=SWEEPS):
    """Exactly one file matching a glob, or an error naming the pattern."""
    found = sorted(base.glob(pattern))
    if len(found) != 1:
        raise FileNotFoundError(f"expected one file for {pattern}, found {len(found)}")
    return found[0]


def voltage_extract(sweep_csv):
    """{target: (voltage, crossbar)} from a sweep's joined HWiNFO extract."""
    import csv
    path = sweep_csv.with_name(sweep_csv.stem + "_voltage.csv")
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return {int(float(r["target"])): (float(r["voltage"]), float(r["crossbar"]))
                for r in csv.DictReader(handle)}
