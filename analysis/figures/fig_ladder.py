"""Figure: on the RTX 5060 Ti, where the curve leaves the floor against where the optimum lands.

x is the clock each applied curve reaches at the 0.720 V floor, read from its saved profile by
analysis/models/predict_from_curve.py. y is the median, over every committed suite sweep of that
configuration, of each sweep's efficiency-optimal target; bars span the interquartile range of
those per-sweep optima. The dotted line is "optimum equals the floor end". Horizontal lines are the
suite's target grid.

Configurations: stock; split (Profile 5, rung A); the control (Profile 2, an edit ABOVE the floor);
rungs B and C (registered before they were built); full tune (Profile 4, rung D). One chip.

Usage: python analysis/figures/fig_ladder.py
"""
import statistics

import numpy as np

from common import BLUE, COLUMN_IN, INK, INK_2, INK_3, ORANGE, plt, save, style
import predict_from_curve as model

# (configuration, label, colour, marker, x nudge in MHz so overlapping points stay visible)
SERIES = [
    ("stock", "stock", INK_2, "o", -14),
    ("split", "rung A (factory floor region)", BLUE, "o", 0),
    ("repair", "control: edit above the floor", ORANGE, "D", 14),
    ("rungB", "rungs B and C, registered first", BLUE, "s", 0),
    ("rungC", None, BLUE, "s", 0),
    ("fulltune", "rung D (floor region +465 MHz)", BLUE, "^", 0),
]


def main():
    style()
    curves = model.loadEfficiencyCurves() + model.loadLadderCurves()
    targets = sorted({t for _, _, curve in curves for t in curve})
    fig, ax = plt.subplots(figsize=(COLUMN_IN, 2.9))
    for t in targets:
        if 1300 <= t <= 2200:
            ax.axhline(t, color="#eeeeea", linewidth=0.6, zorder=0)
    ax.plot([1400, 2100], [1400, 2100], color=INK_3, linestyle=":", linewidth=0.9,
            label="optimum = floor end")
    for configuration, label, colour, marker, nudge in SERIES:
        optima = [max(curve, key=curve.get) for c, _, curve in curves if c == configuration]
        x = model.floorExtentMhz(configuration) + nudge
        med = statistics.median(optima)
        q1, q3 = np.percentile(optima, [25, 75])
        ax.errorbar([x], [med], yerr=[[med - q1], [q3 - med]], color=colour, marker=marker,
                    markersize=5, capsize=2, linewidth=0.9, linestyle="none",
                    label=f"{label} (n={len(optima)} each)" if configuration == "rungB" else
                    (f"{label} (n={len(optima)})" if label else "_nolegend_"))
        print(f"{configuration}: floor end {x - nudge:g}, median optimum {med:g}, "
              f"IQR {q1:g}-{q3:g}, n={len(optima)}")
    ax.set_xlim(1420, 2080)
    ax.set_ylim(1420, 2080)
    ax.set_xlabel("clock the curve reaches at 0.720 V (MHz)")
    ax.set_ylabel("median efficiency-optimal target (MHz)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, fontsize=5.8, handletextpad=0.4, columnspacing=0.8)
    ax.set_aspect("equal")
    save(fig, "fig_ladder")


if __name__ == "__main__":
    main()
