"""
Characterise the dataset before modelling anything.

Two questions this answers, both of which the prediction script depends on:

  1. How much efficiency does running at stock frequency actually give up?
     That gap is the whole point of the project, so it gets measured first,
     from published data, before any model exists to take credit for it.

  2. Do workloads differ enough for a per-workload prediction to be worth making?
     If every workload peaked at the same frequency, one lookup table would beat
     any model and the project would need a different question.
"""

from load_data import REFERENCE_FREQUENCY_MHZ, loadDataset, describeDataset

import numpy as np
import pandas as pd


def summariseWorkload(workloadRows):
    """Reduce one workload's frequency sweep to the handful of numbers we care about."""
    ordered = workloadRows.sort_values("frequency_mhz")
    bestRow = ordered.loc[ordered["efficiency_normalised"].idxmax()]
    stockRow = ordered.loc[ordered["frequency_mhz"] == REFERENCE_FREQUENCY_MHZ].iloc[0]
    lowestRow = ordered.iloc[0]

    return pd.Series(
        {
            "optimal_frequency_mhz": int(bestRow["frequency_mhz"]),
            "efficiency_at_optimum": bestRow["efficiency_normalised"],
            "efficiency_at_stock": stockRow["efficiency_normalised"],
            "headroom_gap_pct": (bestRow["efficiency_normalised"] - 1.0) * 100.0,
            "performance_kept_at_optimum": bestRow["performance_normalised"],
            "performance_given_up_pct": (1.0 - bestRow["performance_normalised"]) * 100.0,
            "power_at_optimum_watts": bestRow["power_watts"],
            "power_at_stock_watts": stockRow["power_watts"],
            "power_saved_pct": (1.0 - bestRow["power_watts"] / stockRow["power_watts"]) * 100.0,
            # How much performance survives running at the lowest available frequency.
            # High values mean the workload barely cares about core clock, which is the
            # classic signature of a memory-bound kernel.
            "performance_at_lowest_frequency": lowestRow["performance_normalised"],
        }
    )


def buildWorkloadSummary(dataset):
    """One row per workload, describing its efficiency optimum."""
    summary = dataset.groupby("workload", sort=False).apply(
        summariseWorkload, include_groups=False
    )
    summary["optimal_frequency_mhz"] = summary["optimal_frequency_mhz"].astype(int)
    return summary


def reportHeadroomGap(summary):
    """State how much efficiency stock frequency leaves on the table."""
    gaps = summary["headroom_gap_pct"]
    print(
        f"[GAP] Running every workload at stock ({REFERENCE_FREQUENCY_MHZ} MHz) rather than at its "
        f"own efficiency optimum gives up a mean of {gaps.mean():.1f}% efficiency "
        f"(median {gaps.median():.1f}%, range {gaps.min():.1f}%-{gaps.max():.1f}%)."
    )
    print(
        f"[GAP] At those optima the workloads give up a mean of "
        f"{summary['performance_given_up_pct'].mean():.1f}% performance and save a mean of "
        f"{summary['power_saved_pct'].mean():.1f}% power."
    )
    print(
        "[GAP] This is measured directly from the published dataset, not predicted. "
        "It is the quantity the project exists to explain, so it is stated before any "
        "model is fitted."
    )


def reportOptimumSpread(summary):
    """Show whether the optimal frequency actually varies across workloads."""
    counts = summary["optimal_frequency_mhz"].value_counts().sort_index()
    distinctOptima = len(counts)
    mostCommon = counts.idxmax()
    mostCommonShare = counts.max() / counts.sum() * 100.0

    print(
        f"[SPREAD] Across {len(summary)} workloads the efficiency optimum lands on "
        f"{distinctOptima} distinct frequencies. The single most common optimum is "
        f"{mostCommon} MHz, which is best for {counts.max()} of {counts.sum()} workloads "
        f"({mostCommonShare:.0f}%)."
    )
    if mostCommonShare > 80.0:
        print(
            "[SPREAD] WARNING: one frequency is optimal for nearly everything. A fixed-frequency "
            "lookup will be very hard to beat, and a per-workload model may not be worth making."
        )
    print()
    print("[SPREAD] Optimal frequency distribution:")
    for frequency, count in counts.items():
        bar = "#" * count
        print(f"           {frequency:>5} MHz  {bar} ({count})")


def reportSensitivityGroups(summary):
    """
    Split workloads by how much they respond to core frequency at all.

    Performance retained at the lowest frequency is a proxy for memory-boundedness:
    a kernel that keeps ~100% of its throughput at 757 MHz was never compute-bound.
    """
    retained = summary["performance_at_lowest_frequency"]
    insensitive = summary[retained >= 0.90]
    sensitive = summary[retained < 0.70]

    print(
        f"[SENSITIVITY] {len(insensitive)} of {len(summary)} workloads keep at least 90% of their "
        f"performance at the lowest frequency tested - these are effectively memory-bound and are "
        f"where the largest efficiency gains sit."
    )
    if len(insensitive) > 0:
        print(f"[SENSITIVITY]   Least frequency-sensitive: {', '.join(insensitive.index[:8])}")
    print(
        f"[SENSITIVITY] {len(sensitive)} workloads drop below 70% performance at the lowest "
        f"frequency - these are compute-bound and scale close to linearly with core clock."
    )
    if len(sensitive) > 0:
        print(f"[SENSITIVITY]   Most frequency-sensitive: {', '.join(sensitive.index[:8])}")

    correlation = np.corrcoef(retained, summary["optimal_frequency_mhz"])[0, 1]
    print(
        f"[SENSITIVITY] Correlation between performance retained at the lowest frequency and the "
        f"optimal frequency is {correlation:+.3f}. A strong negative value would mean "
        f"memory-bound workloads prefer lower clocks, which is the mechanism the literature predicts."
    )


def main():
    dataset = loadDataset()
    describeDataset(dataset)
    print()

    summary = buildWorkloadSummary(dataset)
    reportHeadroomGap(summary)
    print()
    reportOptimumSpread(summary)
    print()
    reportSensitivityGroups(summary)

    outputPath = dataset.attrs.get("output_dir")
    del outputPath  # placeholder: writing summary tables lands in a later version

    print()
    print("[SUMMARY] Per-workload table:")
    columns = [
        "optimal_frequency_mhz",
        "headroom_gap_pct",
        "performance_given_up_pct",
        "power_saved_pct",
    ]
    print(summary[columns].round(2).to_string())


if __name__ == "__main__":
    main()
