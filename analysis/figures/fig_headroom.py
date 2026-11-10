"""Figure: per-workload efficiency gain, optimum over the highest clock reached, on two cards.

The gain is the paper's own: claims_consumer._gainsOf, efficiency at the workload's optimum over
efficiency at the highest achieved clock, minus one, in percent. The RTX 5060 Ti bar is the mean
over its six stock suite replicates (REPLICATES_5060), the RTX 3070 Ti bar its one stock suite,
so the means printed here are the ones §5.1 states. Workloads are ordered by the 5060 Ti gain.
One card per model; the gain is an upper bound on what running at the optimum would save.

Usage: python analysis/figures/fig_headroom.py
"""
from statistics import mean

import numpy as np

from common import BLUE, COLUMN_IN, INK_2, ORANGE, plt, save, style
import claims_consumer as cc


def main():
    style()
    g5060 = {n: mean(cc._gainsOf(t)[n] for t in cc.REPLICATES_5060) for n in cc.SUITE_R1_SWEEPS}
    g3070 = cc._gainsOf(cc.SUITE_3070_SWEEPS)
    names = sorted(g5060, key=g5060.get)
    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(COLUMN_IN, 3.0))
    ax.barh(y + 0.2, [g5060[n] for n in names], height=0.38, color=BLUE,
            label=f"RTX 5060 Ti, mean of {len(cc.REPLICATES_5060)} suites (mean {mean(g5060.values()):.1f}%)")
    ax.barh(y - 0.2, [g3070[n] for n in names], height=0.38, color=ORANGE,
            label=f"RTX 3070 Ti, one suite (mean {mean(g3070.values()):.1f}%)")
    ax.set_yticks(y, names)
    ax.set_xlabel("efficiency gain at the optimum over the highest clock (%)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.16), ncol=1)
    ax.tick_params(axis="y", colors=INK_2)
    for n in names:
        print(f"{n}: 5060 Ti {g5060[n]:.1f}%, 3070 Ti {g3070[n]:.1f}%")
    save(fig, "fig_headroom")


if __name__ == "__main__":
    main()
