"""Checks for analysis/score_xbar14.py, written 2026-10-01 after GPT Job 40 found three defects that
no test could see: the section 13 memory rule tested only an upper bound, the references' memory was
never checked, and a null on a subset of S targets was reported as NOT SUFFICIENT."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_xbar14 as s

failures = 0


def check(condition, text):
    global failures
    print(("[PASS] " if condition else "[FAIL] ") + text)
    failures += 0 if condition else 1


def point(achieved=1702.0, xbar=1335.0, mem=(13801, 13801), hw=(13801, 13801)):
    # Achieved clocks deliberately differ from targets (rule 10 of the GPT brief).
    return {"achieved": achieved, "xbar": xbar, "vid": 0.760, "throughput": 340.0,
            "memMin": mem[0], "memMax": mem[1], "hwMin": hw[0], "hwMax": hw[1]}


s.MEMORY_RULE = "section13"
check(s.memoryFailure(point(mem=(810, 810), hw=(810, 810))) is not None,
      "section13: an all-idle point (810 throughout) fails the bounded maximum")
check(s.memoryFailure(point(mem=(810, 14001), hw=(13801, 13801))) is None,
      "section13: a single idle sample with stock maxima passes")
check(s.memoryFailure(point(mem=(13801, 16301))) is not None,
      "section13: a maximum of 16301 (a live +2500 offset) fails")
check(s.scoreable(point(), [point(mem=(13801, 16301), hw=(13801, 16301))], s.S_WINDOW, 0) != [],
      "a clean arm against a bracket at 16301 is not scoreable")
check(s.scoreable(point(achieved=1702.0), [point(achieved=1694.5), point(achieved=1702.0)], s.S_WINDOW, 0) == [],
      "core within 10 MHz of the bracket MEAN passes when achieved differs from target")
check(s.scoreable(point(achieved=1715.0), [point(achieved=1702.0)], s.S_WINDOW, 0) != [],
      "core 13 MHz from the bracket fails")
check(s.scoreable(point(xbar=1400.0), [point()], s.S_WINDOW, 0) != [],
      "measured XBAR outside S's window fails")
s.MEMORY_RULE = "literal"
check(s.memoryFailure(point(mem=(13801, 14001))) is not None, "literal: one 14001 sample fails")
check(s.memoryFailure(point()) is None, "literal: 13801 throughout passes")

check(s.sVerdictOf({1560: 1.0, 1710: 1.0, 1867: 1.0}, True) == "NOT SUFFICIENT",
      "S: null at all three targets is NOT SUFFICIENT")
check(s.sVerdictOf({1560: 1.0}, True).startswith("no registered verdict"),
      "S: null at one scoreable target is not a registered NOT SUFFICIENT")
check(s.sVerdictOf({1560: 0.95, 1710: 0.89, 1867: 0.87}, True) == "SUFFICIENT, FULL",
      "S: ratios within 0.03 of section 12 at every scoreable target are FULL")
check(s.sVerdictOf({1560: 0.95, 1710: 0.89, 1867: 0.87}, False) == "NOT SCOREABLE",
      "S: an uninterpretable session is NOT SCOREABLE whatever the ratios")
check(s.sVerdictOf({1560: 0.96, 1710: 0.99, 1867: 0.87}, True) == "MIXED", "S: a split is MIXED")

print(f"\n{failures} failure(s).")
sys.exit(1 if failures else 0)
