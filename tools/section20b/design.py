"""Section 20b's fixed design: cells, arms, the Williams rows and each session's saved schedule.

One module, imported by the session controller and by the scorer, so that the schedule a session ran
and the schedule its scorer expects cannot be two implementations that drift apart. Every constant
here comes from the registration draft (docs/submission/drafts/section20b-registration-draft.md,
GPT Job 71) and must not change after collection starts.
"""
import random

# Fixed work per window, from section 19's stock records (Invoke-Rerun15Session.ps1's $ITER).
WORKLOADS = {"gemm": 120, "softmax": 2600, "copy": 2660}
# What each benchmark must report it ran (GPT Job 75, R6): fp32, this size, this work per iteration,
# this unit. Read from gpu_workload.py's defaults as the 2026-10-09 qualification ran them; each
# matches its formula (gemm 2 x 8192^3 FLOP; copy and softmax 8 bytes moved per element).
WORKLOAD_SPEC = {"gemm": (8192, 1099511627776.0, "FLOP/s"), "softmax": (18310, 1199964160.0, "byte/s"),
                 "copy": (150000000, 1200000000.0, "byte/s")}
# The top target was 2475 MHz until 2026-10-11, when pilot session 1's first attempt stopped at its
# first gemm window there: gemm at 2475 draws 172-182 W against stock's 180 W limit, so the clock fell
# to 2437 (docs/section20b/pilot1-attempt1-20261011/). At 2317 (2310 achieved) stock gemm averaged 144 W
# and peaked at 156 W in section 19. Changed before registration and before any pilot data was read.
TARGETS_MHZ = [1545, 2010, 2317]
CELLS = [(workload, target) for workload in WORKLOADS for target in TARGETS_MHZ]

ARMS = ["A", "E", "P", "EP"]
# A balanced 4x4 Williams square: each arm once per position, and each ordered pair of distinct arms
# as immediate predecessor exactly once across the four rows.
WILLIAMS_ROWS = {1: ["A", "E", "EP", "P"], 2: ["E", "P", "A", "EP"],
                 3: ["P", "EP", "E", "A"], 4: ["EP", "A", "P", "E"]}

SEED_BASE = 71020
# Session numbering, and so seeds and schedules, per stage. Pilot sessions are 1-4. Confirmation
# sessions are numbered from 101, so no confirmation schedule can repeat a pilot one; the draft left
# this open (decided 2026-10-10, before any pilot data).
PILOT_INDICES = (1, 2, 3, 4)
CONFIRMATION_INDICES = tuple(range(101, 133))
WASHOUT_SECONDS = 30.0
PRELOAD_SECONDS = 1.0
WARMUP_ITERATIONS = 5
READER_HZ = 20.0
CADENCE_MEDIAN_MS = (45.0, 55.0)
CADENCE_P99_MAX_MS = 100.0
RETURN_GATE_PCT = 1.5
BAND_PP = 2.0
FAMILY_ALPHA = 0.05
CONTRASTS = ["d_E", "d_P", "d_EP", "d_I"]
SIZING_RANGE = (8, 32)
SIZING_ALLOWANCE = 1.5
SIZING_HALF_WIDTH_PP = 1.0

# NVML calls each reader mode makes per poll, in order. EP keeps the historical logger's order
# (usage, then one field batch 185/186/83); P drops field 83; E is a one-field batch.
MODE_CALLS = {"A": [], "E": [("fields", [83])], "P": [("usage", None), ("fields", [185, 186])],
              "EP": [("usage", None), ("fields", [185, 186, 83])]}


def williams_balanced(rows=WILLIAMS_ROWS):
    """True when each arm occupies each position once and each ordered predecessor pair occurs once."""
    positions = all(sorted(row[i] for row in rows.values()) == sorted(ARMS) for i in range(len(ARMS)))
    pairs = [(row[i], row[i + 1]) for row in rows.values() for i in range(len(row) - 1)]
    expected = {(a, b) for a in ARMS for b in ARMS if a != b}
    return positions and len(pairs) == len(expected) and set(pairs) == expected


def schedule(session_index):
    """The 144 windows of one session, in run order.

    random.Random(71020 + session_index) first shuffles the order of the four Williams rows, then, for
    each row in that order, shuffles the nine cells. Within a cell the row's four arms run contiguously
    in the listed order. Deterministic: the same index always gives the same schedule.
    """
    rng = random.Random(SEED_BASE + session_index)
    rows = list(WILLIAMS_ROWS)
    rng.shuffle(rows)
    windows = []
    for row_visit, row in enumerate(rows):
        cells = list(range(len(CELLS)))
        rng.shuffle(cells)
        for cell_visit, cell in enumerate(cells):
            workload, target = CELLS[cell]
            for position, arm in enumerate(WILLIAMS_ROWS[row]):
                windows.append({"index": len(windows), "row": row, "row_visit": row_visit, "cell": cell,
                                "cell_visit": cell_visit, "workload": workload, "target_mhz": target,
                                "iterations": WORKLOADS[workload], "position": position, "arm": arm})
    return windows


def qualification_schedule():
    """Not data: every cell once, all four arms, cycling through the four Williams rows (36 windows).

    The 2026-10-09 qualification ran only three of the nine cells (12 windows), and the cell it missed,
    gemm at the top target, is the one that failed pilot 1's first attempt. So every cell runs here.
    """
    windows = []
    for cell, (workload, target) in enumerate(CELLS):
        row = 1 + cell % len(WILLIAMS_ROWS)
        for position, arm in enumerate(WILLIAMS_ROWS[row]):
            windows.append({"index": len(windows), "row": row, "row_visit": 0, "cell": cell, "cell_visit": 0,
                            "workload": workload, "target_mhz": target, "iterations": WORKLOADS[workload],
                            "position": position, "arm": arm})
    return windows
