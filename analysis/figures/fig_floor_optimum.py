"""Figure: voltage and suite efficiency against clock, one stock session per card.

Top row: the voltage each card reports while running `gemm` at each locked target, from the HWiNFO
log joined by time to that sweep. Bottom row: for each target, the median across the twelve
workloads of efficiency relative to that workload's own peak, with the interquartile range shaded.
The dashed line marks the last target still at the card's lowest reported voltage; the triangle is
the median of the twelve per-workload optima. Every panel pair is one card and one session.

Usage: python analysis/figures/fig_floor_optimum.py
"""
import statistics

import numpy as np

from common import (BLUE, FULL_IN, INK, INK_2, INK_3, SWEEPS, one, plt, save, style,
                    voltage_extract)
from analyze_sweep import efficiencyPeak, loadSweep

WORKLOADS = ["copy", "reduce", "softmax", "layernorm", "bgemm32", "bgemm64", "bgemm128",
             "bgemm256", "bgemm1024", "attention", "conv", "gemm"]

# One stock suite per card, each with a voltage extract joined to its own `gemm` sweep.
CARDS = [
    ("RTX 5060 Ti (Blackwell)", "5060ti-stock-repro-20260922", "*_5060ti-stock-suite-rep1-{w}_sweep.csv"),
    ("RTX 3070 Ti (Ampere)", "rtx3070ti-sessiond-20260924", "*/*_rtx3070ti-sessiond-stock-1-{w}_sweep.csv"),
    ("RTX 3060 (Ampere)", "rtx3060-20260910", "*_rtx3060-suite/*_rtx3060-suite-{w}_sweep.csv"),
    ("RTX 2060 Super (Turing)", "rtx2060s-sessione2-20260927", "*_rtx2060s-sessione2-stock-4-{w}_sweep.csv"),
]
TIE_V = 0.003   # under half of the smallest (5 mV) voltage code


def card_data(directory, pattern):
    base = SWEEPS / directory
    sweeps = {w: loadSweep(one(pattern.format(w=w), base)) for w in WORKLOADS}
    targets = sorted({r["target"] for rows in sweeps.values() for r in rows})
    relative = {t: [] for t in targets}
    optima = []
    for rows in sweeps.values():
        peak = efficiencyPeak(rows)
        optima.append(peak["target"])
        for r in rows:
            relative[r["target"]].append(r["efficiency"] / peak["efficiency"])
    volts = voltage_extract(one(pattern.format(w="gemm"), base))
    floor_v = min(v for v, _ in volts.values())
    floor_end = max(t for t, (v, _) in volts.items() if v <= floor_v + TIE_V)
    return targets, relative, statistics.median(optima), volts, floor_v, floor_end


def main():
    style()
    fig, axes = plt.subplots(2, 4, figsize=(FULL_IN, 3.4), sharex="col",
                             gridspec_kw={"height_ratios": [1, 1.35], "hspace": 0.12,
                                          "wspace": 0.32})
    for col, (name, directory, pattern) in enumerate(CARDS):
        targets, relative, median_opt, volts, floor_v, floor_end = card_data(directory, pattern)
        top, bottom = axes[0, col], axes[1, col]

        vt = sorted(volts)
        top.plot(vt, [volts[t][0] for t in vt], color=INK_2, marker="o", markersize=2.5)
        for ax in (top, bottom):
            ax.axvline(floor_end, color=INK_3, linestyle="--", linewidth=0.8)
        top.set_title(f"{name}\nmin. on grid {floor_v:.3f} V", color=INK, fontsize=7.4)

        med = [100 * statistics.median(relative[t]) for t in targets]
        q1 = [100 * np.percentile(relative[t], 25) for t in targets]
        q3 = [100 * np.percentile(relative[t], 75) for t in targets]
        bottom.fill_between(targets, q1, q3, color=BLUE, alpha=0.18, linewidth=0,
                            label="interquartile range")
        bottom.plot(targets, med, color=BLUE, marker="o", markersize=2.5,
                    label="median of 12 workloads")
        bottom.plot([median_opt], [101.5], marker="v", color=INK, markersize=4.5, linestyle="none",
                    label="median optimum")
        bottom.set_ylim(40, 104)
        bottom.set_xlabel("locked core clock (MHz)")
        if col == 0:
            top.set_ylabel("reported voltage (V)")
            bottom.set_ylabel("efficiency, % of own peak")
        print(f"{name}: floor {floor_v:.3f} V ends at {floor_end}; median optimum {median_opt:g}")
    handles, labels = axes[1, 0].get_legend_handles_labels()
    handles.append(plt.Line2D([], [], color=INK_3, linestyle="--", linewidth=0.8))
    labels.append("last grid point at the lowest voltage")
    fig.legend(handles, labels, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.06))
    save(fig, "fig_floor_optimum")


if __name__ == "__main__":
    main()
