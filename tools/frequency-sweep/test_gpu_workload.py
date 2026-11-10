"""
Tests for the extended workload suite in gpu_workload.py.

WHAT THESE CAN AND CANNOT CHECK
    They run with no GPU and no PyTorch. So they check the SUITE'S ARITHMETIC - the declared
    intensities, the ordering, the VRAM budget - and they cannot check that any kernel runs, that
    the sizes chosen actually fit, or that a workload is bound by what its intensity suggests.
    3.3.1 is the standing reminder that the last of those is an empirical question: membw is
    declared at 0.167 FLOP/byte and is issue-limited rather than bandwidth-limited over most of
    the range.

    A suite entry is NOT validated until it has been run on the card, calibrated, and its
    frequency response looked at. Nothing here substitutes for that.

WHY THE AGREEMENT TEST EXISTS
    suiteDeclaredIntensity() computes intensity from operation counts. The builders in
    buildSuiteWorkload() compute it again from the tensors they allocate. Two derivations of one
    number is a drift risk, and it drifted immediately: the first draft's conv figure was wrong by
    a factor of two and softmax and layernorm by four, in the table a docstring claimed could not
    drift. The agreement checks below are what would have caught it, and did.

⚠️ HOW INDEPENDENT THE AGREEMENT CHECK ACTUALLY IS
    Less than it looks, and the limit is worth stating rather than discovering later. The two
    derivations are independent in STRUCTURE - how FLOPs and bytes are combined - but they SHARE
    the shape constants, because builderIntensity() imports SOFTMAX_FLOPS_PER_ELEMENT,
    CONV_CHANNELS and the rest from the module under test. So it catches a wrong FORMULA and does
    not catch a wrong CONSTANT: setting the softmax count to 20 leaves both sides agreeing at the
    same wrong number.

    That mutation was caught, but by the axis-coverage checks noticing a workload had moved out
    of the memory-bound group - which is luck rather than design. The constants themselves are
    only really testable against a profiler on the card, and that is part of validating the suite
    rather than something this file can do.

A LARGER GAP IN THE SAME CHECK, FOUND BY MUTATION TESTING 2026-08-30
    The drift check compares suiteDeclaredIntensity() against builderIntensity() below. Neither
    is buildSuiteWorkload(). The comparison is between the formula and a longhand copy of the
    formula written out in this file - the code that actually runs on the card is in neither
    side of it.

    Six coefficients inside buildSuiteWorkload() were changed one at a time - softmax 5.0 to 4.0,
    layernorm 8.0 to 6.0, conv's leading 2.0 to 1.0, attention's 4.0 to 2.0, and two byte counts
    - and ALL SIX survived the full suite. The docstring for builderIntensity says sharing code
    would defeat the test, which is right about independence and wrong about what is being
    compared: independence from the builder is not independence, it is absence.

    The reason it is written this way is real - buildSuiteWorkload allocates torch tensors
    interleaved with its arithmetic, so it cannot be called without a GPU. Fixing it means
    extracting the flop/byte arithmetic into a torch-free function the builder then calls, so
    the runtime path is the tested path. That is a change to the collection tool with 3070 Ti
    runs still outstanding on it, so it is deferred until after collection.

    Until then the guard is in analysis/claims_consumer.py: 5.5-intensity-* pins every declared
    intensity to the stock-suite README table, so a drift in suiteDeclaredIntensity or in the
    shape constants fails the audit. It does NOT cover a drift in the builder alone. See
    docs/MUTATION_TESTING.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gpu_workload as workload  # noqa: E402


CHECKS = []


def check(description, condition):
    """Record and print one assertion.

    The marker matters: run_tests.py counts "[PASS]" and "[FAIL]" occurrences in a suite's output
    to decide how many assertions it made, and treats a suite reporting zero as SILENT and
    failing. A suite that prints its own tally in some other format looks like one that asserted
    nothing, which is what this file did on its first run.
    """
    passed = bool(condition)
    CHECKS.append((description, passed))
    print(f"  {'[PASS]' if passed else '[FAIL]'} {description}")


# ---------------------------------------------------------------- the suite itself

names = workload.suiteWorkloadNames()

# 11 since bgemm8 and bgemm16 were retired on 2026-08-28 for measuring launch overhead rather
# than arithmetic intensity. With gemm and membw that is 13 workloads, inside the 12-16 the V100
# subsampling put the constrained result's stability at.
check("the suite has 11 entries", len(names) == 11)
check("no duplicate workload names", len(names) == len(set(names)))
check("gemm and membw are NOT in the suite - they are untouched",
      "gemm" not in names and "membw" not in names)

check("every suite name has a declared intensity",
      all(workload.suiteDeclaredIntensity(name) >= 0.0 for name in names))

# ---------------------------------------------------------------- the axis

intensities = [workload.suiteDeclaredIntensity(name) for name in names]

check("copy sits at zero intensity - the bottom of the axis",
      workload.suiteDeclaredIntensity("copy") == 0.0)

ladder = [workload.suiteDeclaredIntensity(f"bgemm{n}") for n in workload.LADDER_SIZES]
check("the ladder is strictly increasing in intensity",
      all(earlier < later for earlier, later in zip(ladder, ladder[1:])))
check("the ladder doubles at each step, because the inner sizes do",
      all(abs(later / earlier - 2.0) < 1e-9 for earlier, later in zip(ladder, ladder[1:-1])))

# The whole point of the suite is to span the axis rather than cluster on it. Combined with the
# two existing workloads the span has to cover several orders of magnitude, or the leave-one-out
# design has nothing to generalise across.
withExisting = sorted(intensities + [0.167, 1365.0])
check("the suite plus the existing two spans at least three orders of magnitude",
      withExisting[-1] / max(withExisting[1], 1e-9) > 1000.0)
check("at least 4 workloads below 1 FLOP/byte - the memory-bound end is populated",
      sum(1 for value in withExisting if value < 1.0) >= 4)
check("at least 4 workloads above 100 FLOP/byte - so is the compute-bound end",
      sum(1 for value in withExisting if value > 100.0) >= 4)
check("at least 4 workloads in the middle decade, 1 to 100",
      sum(1 for value in withExisting if 1.0 <= value <= 100.0) >= 4)

# ---------------------------------------------------------------- dtype

check("fp16 doubles every non-zero intensity, because it halves the bytes",
      all(abs(workload.suiteDeclaredIntensity(name, 2)
              - 2 * workload.suiteDeclaredIntensity(name, 4)) < 1e-9 for name in names))

# ---------------------------------------------------------------- VRAM

# Both cards must run the identical suite or the paired comparison does not hold, so the budget
# is the 8 GB card's, not the 16 GB one's.
check("the per-workload tensor target leaves room on an 8 GB card",
      workload.SUITE_TARGET_BYTES < 2.0e9)

for inner in workload.LADDER_SIZES:
    batch = max(1, int(workload.SUITE_TARGET_BYTES / (3.0 * inner * inner * 4)))
    allocated = 3.0 * batch * inner * inner * 4
    check(f"bgemm{inner} allocates at most the target", allocated <= workload.SUITE_TARGET_BYTES * 1.001)
    check(f"bgemm{inner} allocates a non-trivial amount", allocated > workload.SUITE_TARGET_BYTES * 0.5)

# ---------------------------------------------------------------- the drift check

def builderIntensity(name, elementBytes):
    """Re-derive intensity the way the GPU builders do, from shapes rather than from the formula.

    Deliberately written out longhand rather than importing anything from the builder: the point
    is that two INDEPENDENT derivations agree. Sharing code here would defeat the test.
    """
    if name.startswith("bgemm"):
        inner = int(name[len("bgemm"):])
        batch = max(1, int(workload.SUITE_TARGET_BYTES / (3.0 * inner * inner * elementBytes)))
        return (2.0 * batch * inner ** 3) / (3.0 * batch * inner ** 2 * elementBytes)
    if name == "copy":
        return 0.0
    if name == "reduce":
        count = int(workload.SUITE_TARGET_BYTES / elementBytes)
        return float(count) / (count * elementBytes)
    if name in ("softmax", "layernorm"):
        rows, columns = 8192, 4096
        perElement = (workload.SOFTMAX_FLOPS_PER_ELEMENT if name == "softmax"
                      else workload.LAYERNORM_FLOPS_PER_ELEMENT)
        return (perElement * rows * columns) / (2.0 * rows * columns * elementBytes)
    if name == "conv":
        channels, spatial, batch = workload.CONV_CHANNELS, 128, 4
        flops = 2.0 * batch * channels * channels * workload.CONV_KERNEL ** 2 * spatial * spatial
        moved = 2.0 * batch * channels * spatial * spatial * elementBytes
        return flops / moved
    if name == "attention":
        heads, headDim = workload.ATTENTION_HEADS, workload.ATTENTION_HEAD_DIM
        sequence, batch = workload.ATTENTION_DEFAULT_SEQUENCE, 4
        flops = 4.0 * batch * heads * sequence ** 2 * headDim
        moved = 4.0 * batch * heads * sequence * headDim * elementBytes
        return flops / moved
    raise ValueError(name)


for name in names:
    for elementBytes in (4, 2):
        declared = workload.suiteDeclaredIntensity(name, elementBytes)
        derived = builderIntensity(name, elementBytes)
        check(f"{name} at {elementBytes}B: formula and shapes agree "
              f"({declared:.4f} vs {derived:.4f})",
              abs(declared - derived) < 1e-6)

# ---------------------------------------------------------------- unknown names

try:
    workload.suiteDeclaredIntensity("not-a-workload")
    check("an unknown workload raises", False)
except ValueError:
    check("an unknown workload raises", True)

# ---------------------------------------------------------------- energy counter

# No device sits at this PCI address, so the counter must decline rather than read another card.
# It returns None the same way on a machine with no NVML at all, such as a CI runner.
check("an energy counter for a nonexistent PCI address is None, not a guess",
      workload.openEnergyCounter("0000:ff:1f.0") is None)


def main():
    failures = [description for description, passed in CHECKS if not passed]
    print(f"{len(CHECKS)} checks, {len(failures)} failed.")
    if failures:
        print(f"FAILED: {', '.join(failures)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
