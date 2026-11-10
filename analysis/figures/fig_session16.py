"""Figure: REGISTERED-PREDICTIONS section 16 on the RTX 5060 Ti, each workload's optimum per arm.

One session, factory-floor curve (P5) -> lifted-floor curve (P4) -> edit above the floor (P2) ->
P5 again. Left: each workload's efficiency-optimal target on the opening P5 suite against P4.
Right: the opening P5 suite against P2, the control; its changed count is against the opening P5
suite, the same comparison as the P5 repeat count printed beside it. Lines that coincide are drawn
once, their width and label giving how many workloads share them; grey lines did not move. The
dotted line is the predicted P4 median. Optima come from analysis/score_session16.py, the
registered scorer, on the committed sweeps.

Usage: python analysis/figures/fig_session16.py
"""
from collections import Counter

from common import BLUE, FULL_IN, INK, INK_3, ORANGE, REPO, plt, save, style
from score_session16 import score

SESSION = REPO / "data" / "frequency-sweeps" / "5060ti-session16-20261006"


def panel(ax, before, after, colour, right_label, title):
    pairs = Counter((before[w], after[w]) for w in before)
    for (y0, y1), n in sorted(pairs.items()):
        moved = y0 != y1
        ax.plot([0, 1], [y0, y1], color=colour if moved else INK_3, linewidth=0.8 + 0.7 * n,
                marker="o", markersize=3, solid_capstyle="round", zorder=3 if moved else 2)
        if n > 1:
            if moved:
                ax.annotate(f"{n} workloads", (0.5, (y0 + y1) / 2), xytext=(0, 7),
                            textcoords="offset points", ha="center", fontsize=6.2, color=INK, zorder=5)
            else:
                # Left of the start point, where no line runs: at mid-panel it read as belonging
                # to layernorm's 1702 -> 1545 path (GPT Job 56, F09); above or below it, it sat
                # on the lines that leave 1545 in both directions.
                ax.annotate(f"{n}\nworkloads", (0, y0), xytext=(-6, 0), textcoords="offset points",
                            ha="right", va="center", multialignment="center", fontsize=6.2, color=INK,
                            zorder=5)
    ax.set_xticks([0, 1], ["factory floor\n(P5, opening)", right_label])
    ax.set_xlim(-0.45, 1.25)
    ax.set_title(title, fontsize=6.8, color=INK, loc="left")


def main():
    style()
    r = score(SESSION)
    p5, p4, p2 = r["optima"]["p5a"], r["optima"]["p4"], r["optima"]["p2"]
    changed_vs_p5a = sum(1 for w in p5 if p2[w] != p5[w])
    fig, axes = plt.subplots(1, 2, figsize=(FULL_IN * 0.75, 2.8), sharey=True,
                             gridspec_kw={"wspace": 0.28})
    for t in r["targets"]:
        if 1300 <= t <= 2700:
            for ax in axes:
                ax.axhline(t, color="#eeeeea", linewidth=0.6, zorder=0)
    panel(axes[0], p5, p4, BLUE, "lifted floor\n(P4, +465 MHz)",
          "Floor edit, predicted median 2010 MHz\n"
          f"median {r['medians']['p5a']:g} → {r['medians']['p4']:g} MHz; "
          f"{len(r['p4_above'])} of 12 moved up")
    axes[0].axhline(2010, color=BLUE, linestyle=":", linewidth=0.8, zorder=1)
    panel(axes[1], p5, p2, ORANGE, "edit above floor\n(P2, control)",
          "Control, predicted median unchanged\n"
          f"median {r['medians']['p5a']:g} → {r['medians']['p2']:g} MHz; {changed_vs_p5a} of 12 changed\n"
          f"(the P5 suite against its own repeat: {len(r['p5_repeat_changed'])})")
    axes[0].set_ylabel("efficiency-optimal target (MHz)")
    axes[0].set_ylim(1300, 2700)
    print(f"medians {r['medians']}; above {len(r['p4_above'])}; P2 changed vs opening P5 "
          f"{changed_vs_p5a}; vs both P5 suites {len(r['p2_moved'])}; "
          f"P5 repeat changed {len(r['p5_repeat_changed'])}")
    save(fig, "fig_session16")


if __name__ == "__main__":
    main()
