"""Figure: every workload's efficiency curve on the RTX 5060 Ti at stock, one panel each.

The same stock suite as Fig. 2's 5060 Ti column (5060ti-stock-repro-20260922, replicate 1). Each
panel is one workload: efficiency relative to its own peak against the locked core clock, with the
triangle at its efficiency-optimal target and the dashed line at the last target still at the
lowest reported voltage (from that suite's `gemm` voltage extract). Fig. 2 shows only the median
and interquartile range of these twelve curves.

Usage: python analysis/figures/fig_workloads.py
"""
from common import BLUE, FULL_IN, INK, INK_3, SWEEPS, one, plt, save, style, voltage_extract
from analyze_sweep import efficiencyPeak, loadSweep
from fig_floor_optimum import TIE_V, WORKLOADS

DIRECTORY = SWEEPS / "5060ti-stock-repro-20260922"
PATTERN = "*_5060ti-stock-suite-rep1-{w}_sweep.csv"


def main():
    style()
    volts = voltage_extract(one(PATTERN.format(w="gemm"), DIRECTORY))
    floor_v = min(v for v, _ in volts.values())
    floor_end = max(t for t, (v, _) in volts.items() if v <= floor_v + TIE_V)
    fig, axes = plt.subplots(3, 4, figsize=(FULL_IN, 4.0), sharex=True, sharey=True,
                             gridspec_kw={"hspace": 0.35, "wspace": 0.12})
    for ax, workload in zip(axes.flat, WORKLOADS):
        rows = loadSweep(one(PATTERN.format(w=workload), DIRECTORY))
        peak = efficiencyPeak(rows)
        rows = sorted(rows, key=lambda r: r["target"])
        ax.plot([r["target"] for r in rows], [100 * r["efficiency"] / peak["efficiency"] for r in rows],
                color=BLUE, marker="o", markersize=2.2)
        ax.axvline(floor_end, color=INK_3, linestyle="--", linewidth=0.8)
        ax.plot([peak["target"]], [103], marker="v", color=INK, markersize=4, linestyle="none")
        ax.set_title(f"{workload}: optimum {peak['target']}", fontsize=6.8, color=INK, pad=2)
        ax.set_ylim(40, 107)
        print(f"{workload}: optimum {peak['target']}, lowest {100 * min(r['efficiency'] for r in rows) / peak['efficiency']:.0f}% of peak")
    for ax in axes[-1]:
        ax.set_xlabel("locked core clock (MHz)")
    for ax in axes[:, 0]:
        ax.set_ylabel("efficiency, % of peak")
    handles = [plt.Line2D([], [], color=BLUE, marker="o", markersize=2.2, label="efficiency"),
               plt.Line2D([], [], color=INK, marker="v", linestyle="none", label="optimum"),
               plt.Line2D([], [], color=INK_3, linestyle="--", linewidth=0.8,
                          label=f"last target at {floor_v:.3f} V ({floor_end} MHz)")]
    fig.legend(handles=handles, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.03))
    save(fig, "fig_workloads")


if __name__ == "__main__":
    main()
