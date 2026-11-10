"""Figure: the core-clock range each dataset sweeps, in absolute MHz, with no normalisation.

Every row is drawn in MHz on one axis, deliberately. Comparing ranges as a percentage needs one
reference clock per card, and the sources do not share one: the public consumer sets declare a
default or reference clock, the V100 set has a stock clock, and this work's cards record a lock ceiling. Scoring
the public sets against a spec-sheet boost clock is how this paper's section 2.7 was wrong for four
weeks, so nothing here is divided by anything.

Bars: the swept core-clock grid (thin extension: an extra low-range sweep on the same card).
Ticks: the public sets' declared default or stock clock. Open diamonds: the highest clock any of the
twelve workloads reached at stock in that session, the same definition on all four cards. Triangles: the median
efficiency-optimal target where it is located (the V100 reference and this work's four cards).

Usage: python analysis/figures/fig_ranges.py   (needs the fetched data/external and data/raw sets)
"""
import csv
import re
import statistics

import pandas as pd

from common import BLUE, FULL_IN, INK, INK_2, INK_3, REPO, SWEEPS, one, plt, save, style
from analyze_sweep import loadSweep
from compare_consumer import STATED_BASE_CLOCK_MHZ
from fig_floor_optimum import CARDS, WORKLOADS, card_data


def public_rows():
    rows = []
    for name, filename in (("GTX 1080 Ti (consumer)", "gtx1080ti.csv"),
                           ("RTX 2070 Super (consumer)", "gtx2070s.csv")):
        cores = sorted(pd.read_csv(REPO / "data" / "external" / filename)["coreF"].unique())
        rows.append({"name": f"{name.split(' (')[0]}, public set", "grid": [float(c) for c in cores],
                     "default": STATED_BASE_CLOCK_MHZ[name], "optimum": None, "extension": None,
                     "reached": None, "ours": False})
    # Two OLDER consumer sets, added 2026-09-29 after the second cold novelty check found them
    # (docs/PRIOR-ART-20260929.md, addendum 3). Their reference clocks are the sources' own, not
    # measured or spec-sheet values: 1100 MHz is the coreF of the GTX 980 reference CSV in the same
    # repository, and 975 MHz is the final line of gpuPTXModel's GTX Titan X core-clock profile,
    # which its gpu_info README labels the default. Only the GTX 980's LOW regime is fetched; its
    # 700-1500 MHz high regime is a separate sweep at another memory clock and is not drawn.
    cores = sorted(pd.read_csv(REPO / "data" / "external" /
                               "gtx980-low-dvfs-real-small-workload-Performance-Power.csv")["coreF"].unique())
    rows.append({"name": "GTX 980 low regime, public set", "grid": [float(c) for c in cores],
                 "default": 1100.0, "optimum": None, "extension": None, "reached": None,
                 "ours": False})
    # Not a plain CSV: application-name lines, then "mem,core,runtime,power,energy" rows.
    text = (REPO / "data" / "external" / "aggregated_dataset_gtxtitanx.csv").read_text(encoding="utf-8-sig")
    cores = sorted({float(line.split(",")[1]) for line in text.splitlines()
                    if re.match(r"^\d+(\.\d+)?,\d", line)})
    rows.append({"name": "GTX Titan X, public set", "grid": cores, "default": 975.0,
                 "optimum": None, "extension": None, "reached": None, "ours": False})
    with open(REPO / "data" / "raw" / "dataset_efficiency.csv", encoding="utf-8-sig") as handle:
        table = list(csv.reader(handle))
    freqs = [float(f) for f in table[0][1:]]
    optima = [freqs[max(range(len(freqs)), key=lambda i: float(r[i + 1]))] for r in table[1:]]
    rows.append({"name": "Tesla V100, public set", "grid": freqs, "default": max(freqs),
                 "optimum": statistics.median(optima), "extension": None, "reached": None,
                 "ours": False})
    return rows


# An extra low-range sweep on the same card, drawn as a thin extension of its bar.
EXTENSIONS = {
    "RTX 5060 Ti (Blackwell)": "5060ti-q1-llm-20260927/*_5060ti-q1-decode-asc_sweep.csv",
    "RTX 2060 Super (Turing)": "rtx2060s-20260912/*_rtx2060s-lowrange/*_rtx2060s-lowrange-gemm_sweep.csv",
}


def our_rows():
    rows = []
    for name, directory, pattern in CARDS:
        targets, _, median_opt, _, _, _ = card_data(directory, pattern)
        reached = max(r["mhz"] for w in WORKLOADS
                      for r in loadSweep(one(pattern.format(w=w), SWEEPS / directory)))
        extension = None
        if name in EXTENSIONS:
            extension = min(r["target"] for r in loadSweep(one(EXTENSIONS[name])))
        rows.append({"name": f"{name.split(' (')[0]}, this work", "grid": targets, "default": None,
                     "optimum": median_opt, "extension": extension, "reached": reached,
                     "ours": True})
    return rows


def main():
    style()
    rows = public_rows() + our_rows()
    fig, ax = plt.subplots(figsize=(FULL_IN, 3.3))
    for y, row in enumerate(reversed(rows)):
        lo, hi = min(row["grid"]), max(row["grid"])
        colour = BLUE if row["ours"] else INK_2
        if row["extension"] is not None:
            ax.plot([row["extension"], lo], [y, y], color=colour, linewidth=1.2, alpha=0.6,
                    solid_capstyle="butt")
        ax.plot([lo, hi], [y, y], color=colour, linewidth=6, solid_capstyle="butt", alpha=0.85)
        ax.plot(row["grid"], [y] * len(row["grid"]), linestyle="none", marker="|", color="white",
                markersize=6, markeredgewidth=0.6)
        if row["default"] is not None:
            ax.plot([row["default"]], [y], marker="|", color=INK, markersize=13, markeredgewidth=1.6,
                    linestyle="none")
        if row["reached"] is not None:
            ax.plot([row["reached"]], [y + 0.32], marker="D", markerfacecolor="white",
                    markeredgecolor=INK, markersize=4, linestyle="none")
        if row["optimum"] is not None:
            ax.plot([row["optimum"]], [y + 0.32], marker="v", color=INK, markersize=5,
                    linestyle="none")
        print(f"{row['name']}: grid {lo:g}-{hi:g}, default {row['default']}, "
              f"reached {row['reached']}, optimum {row['optimum']}, extension {row['extension']}")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r["name"] for r in reversed(rows)])
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_xlabel("core clock (MHz)")
    ax.grid(axis="y", visible=False)
    legend = [
        plt.Line2D([], [], color=INK_2, linewidth=6, alpha=0.85, label="swept grid, public set"),
        plt.Line2D([], [], color=BLUE, linewidth=6, alpha=0.85, label="swept grid, this work"),
        plt.Line2D([], [], color=BLUE, linewidth=1.2, alpha=0.6, label="extra low-range sweep"),
        plt.Line2D([], [], color=INK, marker="|", markersize=10, markeredgewidth=1.6,
                   linestyle="none", label="declared default, reference or stock clock"),
        plt.Line2D([], [], marker="D", markerfacecolor="white", markeredgecolor=INK, markersize=4,
                   linestyle="none", label="highest clock any workload reached at stock"),
        plt.Line2D([], [], marker="v", color=INK, markersize=5, linestyle="none",
                   label="median efficiency optimum"),
    ]
    ax.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3)
    ax.axhline(3.5, color=INK_3, linewidth=0.5)
    save(fig, "fig_ranges")


if __name__ == "__main__":
    main()
