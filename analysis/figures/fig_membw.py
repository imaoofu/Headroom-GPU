"""Figure: a flattened curve holds a bandwidth-bound kernel back, at matched memory clock.

RTX 5060 Ti, one session (REGISTERED-PREDICTIONS 12, data/frequency-sweeps/5060ti-memmatched-20260926/).
"Flattened" is the full-tune curve with its memory offset removed, so both arms run memory at
13801 MHz. Top: `membw` throughput. Bottom: the crossbar clock HWiNFO reports, joined by time. The
shaded band is the registered comparison range, 1560-1867 MHz. A closing stock sweep checks that
the session did not drift. One sweep per arm; the crossbar was observed, never set.

Usage: python analysis/figures/fig_membw.py
"""
from common import BLUE, COLUMN_IN, INK_2, INK_3, SWEEPS, one, plt, save, style, voltage_extract
from analyze_sweep import loadSweep

DIRECTORY = SWEEPS / "5060ti-memmatched-20260926"
ARMS = [
    ("stock-membw", "stock, opening", INK_2, "o", "-"),
    ("stock-membw-r2", "stock, closing", INK_3, "o", ":"),
    ("curve3-membw", "flattened curve", BLUE, "s", "-"),
]
BAND = (1560, 1867)


def main():
    style()
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(COLUMN_IN, 3.6), sharex=True,
                                      gridspec_kw={"hspace": 0.1})
    for ax in (top, bottom):
        ax.axvspan(*BAND, color="#efeeea", zorder=0, linewidth=0)
    for tag, label, colour, marker, style_ in ARMS:
        path = one(f"*_5060ti-4j-{tag}_sweep.csv", DIRECTORY)
        rows = sorted(loadSweep(path), key=lambda r: r["target"])
        top.plot([r["target"] for r in rows], [r["throughput"] / 1e9 for r in rows],
                 color=colour, marker=marker, linestyle=style_, markersize=3, label=label)
        if tag != "stock-membw-r2":
            xbar = voltage_extract(path)
            t = sorted(xbar)
            bottom.plot(t, [xbar[k][1] for k in t], color=colour, marker=marker, linestyle=style_,
                        markersize=3, label=label)
    top.set_ylabel("membw throughput (GB/s)")
    bottom.set_ylabel("crossbar clock (MHz)")
    bottom.set_xlabel("locked core clock (MHz)")
    top.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3, columnspacing=1.0, handlelength=1.8)
    top.text(sum(BAND) / 2, top.get_ylim()[1], "registered range", ha="center", va="top",
             fontsize=6.2, color=INK_2)
    save(fig, "fig_membw")


if __name__ == "__main__":
    main()
