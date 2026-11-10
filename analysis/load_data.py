"""
Load and validate the GPU-DVFS-Dataset CSVs.

The three published CSVs are stored WIDE: one row per workload, one column per
GPU core frequency. Everything downstream wants LONG format, so this module does
the reshape once and validates the files against each other on the way through.

Source: https://github.com/zyjopensource/GPU-DVFS-Dataset
Hardware: a single NVIDIA V100 (TDP 300 W), 33 workloads, 13 core frequencies.
"""

from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = REPO_ROOT / "data" / "raw"

# Every series in the dataset is normalised to its own value at this frequency,
# which is the V100's stock boost clock. Nothing in the dataset sits above it,
# so this dataset cannot say anything about overclocking - only about running
# at or below stock.
REFERENCE_FREQUENCY_MHZ = 1530


def loadWideMatrix(filename):
    """Read one published CSV as a workload-by-frequency matrix."""
    matrix = pd.read_csv(RAW_DATA_DIR / filename, index_col=0)
    matrix = matrix.dropna(how="all")
    matrix.columns = [int(column) for column in matrix.columns]
    matrix.index.name = "workload"
    return matrix


def loadAllMatrices():
    """Return the (performance, power, efficiency) matrices as published."""
    performance = loadWideMatrix("dataset_performance.csv")
    power = loadWideMatrix("dataset_power.csv")
    efficiency = loadWideMatrix("dataset_efficiency.csv")

    if not (performance.index.equals(power.index) and performance.index.equals(efficiency.index)):
        raise ValueError("The three CSVs do not list the same workloads in the same order.")
    if not (list(performance.columns) == list(power.columns) == list(efficiency.columns)):
        raise ValueError("The three CSVs do not share the same frequency columns.")

    return performance, power, efficiency


def recomputeEfficiency(performance, power):
    """
    Rebuild the efficiency matrix from performance and power alone.

    The dataset defines efficiency as performance-per-watt, normalised to its own
    value at the reference frequency. Recomputing it is a cheap check that we have
    understood the published files correctly before building anything on them.
    """
    performancePerWatt = performance / power
    referenceColumn = performancePerWatt[REFERENCE_FREQUENCY_MHZ]
    return performancePerWatt.div(referenceColumn, axis=0)


def validateAgainstPublishedEfficiency(performance, power, efficiency):
    """Compare our recomputed efficiency against the published file and report the gap."""
    recomputed = recomputeEfficiency(performance, power)
    absoluteDifference = (recomputed - efficiency).abs()
    worstDifference = absoluteDifference.to_numpy().max()

    print(
        f"[VALIDATION] Recomputed efficiency (performance / power, normalised to "
        f"{REFERENCE_FREQUENCY_MHZ} MHz) matches the published efficiency file to within "
        f"{worstDifference:.6f} across all {absoluteDifference.size} cells."
    )
    if worstDifference > 1e-3:
        print(
            "[VALIDATION] WARNING: that gap is larger than rounding in the published "
            "4-decimal files would explain. Do not build on the efficiency file until "
            "this is understood."
        )
    return worstDifference


def toLongFormat(performance, power, efficiency):
    """Flatten the three matrices into one tidy frame, one row per workload-frequency pair."""

    def melt(matrix, valueName):
        melted = matrix.reset_index().melt(
            id_vars="workload", var_name="frequency_mhz", value_name=valueName
        )
        melted["frequency_mhz"] = melted["frequency_mhz"].astype(int)
        return melted

    combined = melt(performance, "performance_normalised")
    combined = combined.merge(melt(power, "power_watts"), on=["workload", "frequency_mhz"])
    combined = combined.merge(melt(efficiency, "efficiency_normalised"), on=["workload", "frequency_mhz"])
    return combined.sort_values(["workload", "frequency_mhz"]).reset_index(drop=True)


def loadDataset(validate=True):
    """Main entry point: return the tidy long-format dataset, validated by default."""
    performance, power, efficiency = loadAllMatrices()
    if validate:
        validateAgainstPublishedEfficiency(performance, power, efficiency)
    return toLongFormat(performance, power, efficiency)


def describeDataset(longFormat):
    """Print a plain-language inventory of what was actually loaded."""
    workloads = longFormat["workload"].unique()
    frequencies = np.sort(longFormat["frequency_mhz"].unique())

    print(
        f"[DATA] Loaded {len(longFormat)} workload-frequency measurements: "
        f"{len(workloads)} workloads across {len(frequencies)} core frequencies "
        f"({frequencies.min()}-{frequencies.max()} MHz)."
    )
    print(
        f"[DATA] The dataset's maximum frequency ({frequencies.max()} MHz) is the V100's stock "
        f"boost clock, so every measurement is at or below stock. This dataset supports "
        f"underclocking and efficiency questions only - it contains no overclocking headroom."
    )
    print(
        f"[DATA] Performance is normalised per workload (1.0000 at {REFERENCE_FREQUENCY_MHZ} MHz); "
        f"power is absolute watts; efficiency is normalised performance-per-watt."
    )


if __name__ == "__main__":
    dataset = loadDataset()
    describeDataset(dataset)
    print()
    print("[DATA] First few rows:")
    print(dataset.head(8).to_string(index=False))
