"""REGISTERED-PREDICTIONS §13 scorer: the committed session, plus edited copies in a temp directory.

The committed directory is only read. Each edited case copies it first, so no measurement file is
written or changed.
"""

import csv
import shutil
import tempfile
from pathlib import Path

from score_q1_llm import DEFAULT_DIR, RULE_PICK, score


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise AssertionError(message)
    print(f"[PASS] {message}")


def edited(workload, target, **fields):
    """Score `workload` on a copy whose rows at `target` (both directions) carry `fields`."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for path in DEFAULT_DIR.glob("*_sweep*"):
            shutil.copy(path, root / path.name)
        for path in root.glob(f"*_5060ti-q1-{workload}-*_sweep.csv"):
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                header, rows = reader.fieldnames, list(reader)
            for row in rows:
                if int(float(row["target_frequency_mhz"])) == target:
                    row.update({k: str(v) for k, v in fields.items()})
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=header, quoting=csv.QUOTE_ALL)
                writer.writeheader()
                writer.writerows(rows)
        return score(root, workload)


def main():
    decode, prefill = score(DEFAULT_DIR, "decode"), score(DEFAULT_DIR, "prefill")
    check(decode["verdict"] == "HOLDS" and decode["best"] == RULE_PICK,
          "the committed decode session holds, with its maximum at 1560")
    check(abs(decode["d"] - 0.0214) < 0.0005, "decode repeat noise d is 2.14%")
    check(prefill["verdict"] == "HOLDS" and prefill["best"] == RULE_PICK,
          "the committed prefill session holds, with its maximum at 1560")
    check(not decode["problems"] and not prefill["problems"], "every interpretability check passes")

    # 1125 MHz decode draws ~62 W; 70 tok/s there beats 1560's 0.84 tok/J by far more than d.
    check(edited("decode", 1125, bench_throughput=70)["verdict"] == "FAILS BELOW",
          "a maximum below 1560 by more than d fails below")
    check(edited("decode", 1995, bench_throughput=110)["verdict"] == "FAILS ABOVE",
          "a maximum above 1560 by more than d fails above")
    near = edited("decode", 1342, bench_throughput=round(0.8445 * 1.01 * 65.16, 3))
    check(near["best"] == 1342 and near["verdict"] == "HOLDS",
          "a maximum elsewhere but within d of E(1560) still holds")
    check(edited("decode", 900, memory_clock_max_mhz=16301)["verdict"] == "UNINTERPRETABLE",
          "a memory offset live at one point (16301 MHz) is uninterpretable")
    check(edited("decode", 900, memory_clock_max_mhz=14001)["verdict"] == "HOLDS",
          "14001 MHz, stock's second loaded state, is accepted (amendment 15:10)")
    check(edited("prefill", 2212, bench_ok="False")["verdict"] == "UNINTERPRETABLE",
          "a failed benchmark point is uninterpretable")


if __name__ == "__main__":
    main()
