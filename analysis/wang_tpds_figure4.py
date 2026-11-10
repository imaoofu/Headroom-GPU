"""Re-run Wang et al.'s TPDS Figure 4 model from their own publication-era commit.

Wang, Mei, Liu, Leung, Li & Chu (arXiv:2104.00486) report a 4.3% narrow-interval saving and a
36.4% wide-interval saving on a GTX 1080 Ti, with optima "close to the allowed lowest setting" in
both. Their repository, HKBU-HPML/GPU-DVFS-Job-Schedule, kept the fitted parameters (apps.pkl) and
the plotting notebook at commit 8a0a2e0, "finalize the TPDS version." (2021-04-26).

This script loads both from that commit, runs the notebook's own solve_dvfs() under five parameter
conditions, and compares the narrow optima with the released CSV's raw grid argmin. It needs a
local clone of the repository, made OUTSIDE this one:

    git clone https://github.com/HKBU-HPML/GPU-DVFS-Job-Schedule.git <somewhere outside the repo>
    python analysis/wang_tpds_figure4.py <that clone>

It writes nothing. The pickle is opened with a class allowlist (numpy scalar and dtype only).
Limits, stated in the output: this is the authors' MODEL, not their meter readings, which were
never released; and the CSV's power is GPU telemetry, not their system-scope energy.
"""
import copy
import importlib
import io
import json
import math
import pickle
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

COMMIT = "8a0a2e0ef402b84c428496ce037c6753f19f0873"
CSV = "csvs/gtx1080ti-dvfs-real-Performance-Power.csv"
DEFAULT_CORE_MHZ = 1800  # the README's declared default; f^Gc = 1 in the model
P0_DIVISOR, GAMMA_DIVISOR = 4.75, 4.65  # applied inside solve_dvfs, on every call


class AllowlistUnpickler(pickle.Unpickler):
    ALLOWED = {("numpy.core.multiarray", "scalar"), ("numpy._core.multiarray", "scalar"),
               ("numpy", "dtype")}

    def find_class(self, module, name):
        if (module, name) not in self.ALLOWED:
            raise pickle.UnpicklingError(f"refusing {module}.{name}")
        for candidate in (module, module.replace("numpy.core", "numpy._core"),
                          module.replace("numpy._core", "numpy.core")):
            try:
                return getattr(importlib.import_module(candidate), name)
            except (ImportError, AttributeError):
                continue
        raise pickle.UnpicklingError(f"cannot resolve {module}.{name}")


def gitShow(repo, path):
    return subprocess.run(["git", "-C", str(repo), "show", f"{COMMIT}:{path}"],
                          check=True, capture_output=True).stdout


def loadSolver(notebookBytes):
    """The notebook's own solve_dvfs, extracted verbatim. It is arithmetic only."""
    cells = json.loads(notebookBytes.decode("utf-8"))["cells"]
    source = next("".join(c["source"]) for c in cells if "def solve_dvfs" in "".join(c["source"]))
    body = source[source.index("def solve_dvfs"):source.index("def plot_app")]
    namespace = {"math": math}
    exec(body, namespace)  # noqa: S102 - pinned third-party commit, pure arithmetic
    saved = "".join("".join(output.get("text", ""))
                    for cell in cells if cell["cell_type"] == "code"
                    and "plot_app(save_filename" in "".join(cell["source"])
                    for output in cell.get("outputs", []))
    return namespace["solve_dvfs"], saved


def undivided(apps):
    fresh = copy.deepcopy(apps)
    for app in fresh.values():
        app["p0"] *= P0_DIVISOR
        app["gamma"] *= GAMMA_DIVISOR
    return fresh


def main(repo):
    repo = Path(repo)
    apps = AllowlistUnpickler(io.BytesIO(gitShow(repo, "apps.pkl"))).load()
    solve, savedOutput = loadSolver(gitShow(repo, "plot.ipynb"))
    names = list(apps)[:20]  # the notebook plots the first 20 of the ordered 30
    print(f"Commit {COMMIT[:7]} holds {len(apps)} fitted applications; Figure 4 plots the first 20.")
    print("The notebook's saved output reads: " + " and ".join(savedOutput.split()) + ".")

    def mean(results):
        return 100 * sum(r[0] for r in results) / len(results)

    historical = list(copy.deepcopy(apps).values())
    narrowPlotted = [solve(a, narrow=True) for a in historical][:20]
    widePlotted = [solve(a, narrow=False) for a in historical][:20]
    narrowOriginal = [solve(a, narrow=True) for a in undivided(apps).values()][:20]
    wideOriginal = [solve(a, narrow=False) for a in undivided(apps).values()][:20]
    wideOnce = [solve(a, narrow=False) for a in copy.deepcopy(apps).values()][:20]

    print("\nMean modelled saving over the 20, by parameter condition:")
    # gamma multiplies memory frequency in the paper's power model; it is NOT static power
    # (corrected 2026-09-26 after GPT Job 22; the first version called both "static terms").
    print(f"  narrow, saved fit, undivided                  {mean(narrowOriginal):7.3f}%  (paper states 4.3%)")
    print(f"  wide,   saved fit, undivided                  {mean(wideOriginal):7.3f}%")
    print(f"  narrow, p0 and gamma divided once (plotted)   {mean(narrowPlotted):7.3f}%")
    print(f"  wide,   p0 and gamma divided once             {mean(wideOnce):7.3f}%")
    print(f"  wide,   p0 and gamma divided twice (plotted)  {mean(widePlotted):7.3f}%  (paper states 36.4%)")
    print(f"{mean(narrowOriginal):.3f}% rounds to {mean(narrowOriginal):.1f}% at one decimal: close to "
          "the stated 4.3%, and not a reproduction of it.")
    print("Widening the interval alone moves the mean from "
          f"{mean(narrowOriginal):.2f}% to {mean(wideOriginal):.2f}%; the plotted "
          f"{mean(widePlotted):.2f}% also needs p0 divided by {P0_DIVISOR} and gamma by "
          f"{GAMMA_DIVISOR}, twice.")

    lowest = math.sqrt((0.8 - 0.5) / 2.0) + 0.5
    for label, results in (("plotted (divided once)", narrowPlotted),
                           ("original parameters", narrowOriginal)):
        atLowest = sum(abs(r[1] - lowest) < 1e-9 for r in results)
        print(f"\nNarrow optima, {label}: {atLowest} of 20 at the lowest allowed core setting "
              f"({lowest:.3f} x {DEFAULT_CORE_MHZ} = {lowest * DEFAULT_CORE_MHZ:.0f} MHz).")
        print("  core MHz: " + ", ".join(f"{mhz} x{n}" for mhz, n in sorted(
            Counter(round(r[1] * DEFAULT_CORE_MHZ) for r in results).items())))

    table = pd.read_csv(io.BytesIO(gitShow(repo, CSV)))
    table["energy"] = table["time/ms"] * table["power/W"]
    rawBest = table.loc[table.groupby("appName")["energy"].idxmin()].set_index("appName")["coreF"]
    grid = sorted(table["coreF"].unique())
    exact = oneStep = within100 = 0
    for name, result in zip(names, narrowOriginal):
        modelled = result[1] * DEFAULT_CORE_MHZ
        nearest = min(grid, key=lambda g: abs(g - modelled))
        exact += nearest == rawBest[name]
        oneStep += abs(nearest - rawBest[name]) <= 100
        within100 += abs(modelled - rawBest[name]) <= 100
    edges = Counter("low" if rawBest[n] == grid[0] else "high" if rawBest[n] == grid[-1]
                    else "interior" for n in names)
    print(f"\nRaw CSV argmin of time x GPU power for the same 20: {edges['low']} low, "
          f"{edges['interior']} interior, {edges['high']} high.")
    print(f"After rounding each modelled clock to the nearest sampled one, the undivided narrow model "
          f"lands on the raw argmin for {exact} of 20 and within one 100 MHz step for {oneStep} of "
          f"20; unrounded, {within100} of 20 are within 100 MHz.")
    print("That agreement is IN-SAMPLE: the fit was made to the same CSV rows the argmin reads.")
    print("\nLimits: this is the released GPU-telemetry fit and CSV. The paper's commercial-meter "
          "readings were never released, and none of the 20 saved fits lies inside all of the "
          "parameter ranges the paper states for its application library (its section 5.1.3), so "
          "this cannot show how the authors obtained 4.3%, or that their measurements are wrong.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python analysis/wang_tpds_figure4.py <clone of GPU-DVFS-Job-Schedule>")
    main(sys.argv[1])
