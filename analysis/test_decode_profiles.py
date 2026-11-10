"""Committed Afterburner blobs and awkward offset-boundary cases."""

import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "afterburner"))
from decode_profiles import decode_hex, load_profiles, next_record_pairing, verify_rung  # noqa: E402

REFERENCE = ROOT / "data/afterburner-profiles/5060ti-profiles-20260908b-p4-plateau-3030.json"
RUNG_B = ROOT / "data/afterburner-profiles/5060ti-profiles-20260922-rungB"
RTX3070TI = ROOT / "data/afterburner-profiles/3070ti-profiles-20260923"
# mV -> (P1 stock, P2 Edit 1, P3 Edit 2): the hand-decoded table in that snapshot's README,
# which next-record pairing reproduces exactly (checked 2026-09-23, before the lenient mode existed).
RTX3070TI_TABLE = {
    718.75: (1185, 1200, 1185), 812.5: (1485, 1200, 1485), 825.0: (1515, 1200, 1500),
    831.25: (1530, 1215, 1500), 868.75: (1620, 1575, 1500), 875.0: (1635, 1635, 1500),
    1200.0: (1995, 1995, 1500),
}


def check(description, condition):
    if not condition:
        raise AssertionError(description)
    print(f"[PASS] {description}")


def rejects(description, action):
    try:
        action()
    except ValueError:
        print(f"[PASS] {description}")
        return
    raise AssertionError(description)


def main():
    reference = json.loads(REFERENCE.read_text(encoding="utf-8-sig"))["profiles"]
    for name in (f"Profile{i}" for i in range(1, 6)):
        decoded = decode_hex(reference[name]["vf_curve_hex"])
        check(f"{name}: all 127 raw triples reproduce the committed decode exactly",
              [point.legacy_decode() for point in decoded] == reference[name]["curve_points"])

    path, profiles = load_profiles(RUNG_B)
    check("rung B snapshot resolves to its NVIDIA VEN cfg", path.name.startswith("VEN_10DE"))
    for name in ("Profile2", "Profile3", "Profile4", "Profile5"):
        check(f"rung B {name}: unchanged from committed 09-08b decode",
              [point.legacy_decode() for point in profiles[name].points] ==
              reference[name]["curve_points"])

    rung = profiles["Profile1"]
    point_845 = rung.at(845)
    check("rung B 845 mV: raw (+176, 2362) sums to 2538 but applied is flagged",
          (point_845.offset_mhz, point_845.base_mhz, point_845.raw_sum_mhz,
           point_845.applied_mhz, point_845.offset_boundary) ==
          (176.0, 2362.0, 2538.0, None, True))
    check("rung B 720 mV: stable-offset point safely reads 1702",
          rung.at(720).applied_mhz == 1702.0 and not rung.at(720).offset_boundary)
    check("rung B 850 and 860 mV: both sides of offset changes are flagged",
          rung.at(850).applied_mhz is None and rung.at(860).applied_mhz is None)
    check("935 mV plateau boundary is flagged, including on historical P1",
          rung.at(935).offset_boundary and
          decode_hex(reference["Profile1"]["vf_curve_hex"])[
              rung.at(935).index].applied_mhz is None)
    check("supported-clock filter preserves historical counts without hiding uncertainty",
          [len(profiles[f"Profile{i}"].supported_points()) for i in range(1, 6)] ==
          [126, 125, 122, 126, 126] and point_845 in rung.supported_points())

    checks = verify_rung(RUNG_B, profiles, "B")
    check("rung B five registered checks score pass/pass/fail/pass/pass",
          [item.passed for item in checks] == [True, True, False, True, True])
    check("check 3 has definite failures in the documented 650-690 mV region",
          all(f"{voltage}.0" in checks[2].detail for voltage in (660, 665, 670, 675, 685)))
    check("check 4 states its raw-sum and boundary limitation",
          "raw check does not certify live applied clocks" in checks[3].detail)
    check("check 5 labels pre-run chronology as source-reported",
          "source-reported" in checks[4].detail)

    blob = bytearray.fromhex(reference["Profile1"]["vf_curve_hex"])
    damaged_header = bytearray(blob)
    damaged_header[0] ^= 1
    rejects("corrupt header rejected", lambda: decode_hex(damaged_header.hex()))
    damaged_tail = bytearray(blob)
    struct.pack_into("<f", damaged_tail, 8 + 127 * 12, 42.0)
    rejects("wrong repeated-offset tail rejected", lambda: decode_hex(damaged_tail.hex()))
    rejects("truncated blob rejected", lambda: decode_hex(blob[:-1].hex()))

    with tempfile.TemporaryDirectory() as temporary:
        copy = Path(temporary) / path.name
        shutil.copyfile(path, copy)
        _, copied_profiles = load_profiles(copy)
        check("snapshot check fails without README/hash provenance",
              not verify_rung(copy, copied_profiles, "B")[4].passed)

    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools/afterburner/decode_profiles.py"),
         str(RUNG_B), "--verify-rung", "B"],
        capture_output=True, text=True,
    )
    check("CLI exits nonzero and prints the five expected verdict lines",
          completed.returncode == 1 and
          [line.split(":", 2)[1].strip() for line in completed.stdout.splitlines()] ==
          ["PASS", "PASS", "FAIL", "PASS", "PASS"])
    json_run = subprocess.run(
        [sys.executable, str(ROOT / "tools/afterburner/decode_profiles.py"),
         str(RUNG_B), "--json"],
        capture_output=True, text=True, check=True,
    )
    cli_points = json.loads(json_run.stdout)["profiles"]["Profile1"]["points"]
    cli_845 = next(point for point in cli_points if point["voltage_mv"] == 845)
    check("JSON output keeps raw 2538 while withholding applied clock at 845 mV",
          cli_845["raw_sum_mhz"] == 2538 and cli_845["applied_mhz"] is None and
          cli_845["offset_boundary"])


    # The 3070 Ti store: three slots and a nonzero tail. Lenient mode and next-record pairing
    # were drafted by the local model (L1, 2026-09-24) and reviewed; these pin them.
    rejects("default load still refuses the 3-slot 3070 Ti store", lambda: load_profiles(RTX3070TI))
    rejects("lenient slots without allow_tail still refuse the nonzero tail",
            lambda: load_profiles(RTX3070TI, allow_partial=True))
    _, ti = load_profiles(RTX3070TI, allow_partial=True, allow_tail=True)
    check("lenient load returns exactly the three filled slots", list(ti) == ["Profile1", "Profile2", "Profile3"])
    for slot, name in enumerate(ti):
        paired = next_record_pairing(ti[name].points)
        by_mv = {point.voltage_mv: paired[i] for i, point in enumerate(ti[name].points)}
        check(f"3070 Ti {name}: next-record pairing reproduces the hand-decoded table, last is None",
              all(by_mv[mv] == row[slot] for mv, row in RTX3070TI_TABLE.items()) and paired[-1] is None)
    rung_pairs = next_record_pairing(profiles["Profile1"].points)
    check("next-record pairing reads rung B's 845 mV as 2362, the editor's value",
          rung_pairs[rung.at(845).index] == 2362)


if __name__ == "__main__":
    main()
