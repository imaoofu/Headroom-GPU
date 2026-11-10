"""Read MSI Afterburner VFCurve records without trusting offset boundaries.

Usage:
    python tools/afterburner/decode_profiles.py SNAPSHOT_DIR_OR_VEN_CFG
    python tools/afterburner/decode_profiles.py SNAPSHOT_DIR --verify-rung B
    python tools/afterburner/decode_profiles.py SNAPSHOT_DIR --json
    python tools/afterburner/decode_profiles.py SNAPSHOT_DIR --lenient
    python tools/afterburner/decode_profiles.py SNAPSHOT_DIR --pairing next

The raw triple is (offset MHz, voltage mV, base MHz). At a change in stored
offset, base + offset can mispair: rung B stores (+176, 845 mV, 2362 MHz),
while the editor shows 2362 MHz. Adjacent records on both sides of every
offset change are marked uncertain. ``raw_sum_mhz`` preserves the arithmetic;
``applied_mhz`` is None at flagged points. This is a file decoder, not a GPU
control or a rail-voltage measurement.

Two store shapes the committed 5060 Ti files do not have:

* ``--lenient`` reads a store that has fewer than five profile slots (the
  RTX 3070 Ti has three, plus an empty ``Startup``) and whose VFCurve tail is
  not zero-filled. Only the tail check is skipped; the tail values are not
  decoded.
* ``--pairing next`` reports the next-record pairing, ``base[i] + offset[i+1]``.
  The stored offset lags by one record on both cards, but this is supported
  by two committed files and one editor tooltip rather than by documentation.
  The naive ``base + offset`` reading remains the default.
"""

import argparse
import configparser
import hashlib
import json
import math
import re
import struct
from dataclasses import asdict, dataclass
from pathlib import Path


HEADER = bytes.fromhex("000002007f000000")
RECORD_COUNT = 127
RECORD_SIZE = 12
BLOB_SIZE = 3224
SUPPORTED_CLOCK_MHZ = 3090.0
PROFILES = tuple(f"Profile{i}" for i in range(1, 6))


@dataclass(frozen=True)
class CurvePoint:
    index: int
    voltage_mv: float
    base_mhz: float
    offset_mhz: float
    raw_sum_mhz: float
    applied_mhz: float | None
    offset_boundary: bool

    def legacy_decode(self):
        """The four raw fields in the committed 2026-09-08 JSON decode."""
        return {
            "voltage_mv": self.voltage_mv,
            "base_mhz": self.base_mhz,
            "offset_mhz": self.offset_mhz,
            "applied_mhz": self.raw_sum_mhz,
        }


@dataclass(frozen=True)
class Profile:
    name: str
    power_limit_pct: str
    core_clk_boost_khz: str
    mem_clk_boost_khz: str
    points: tuple[CurvePoint, ...]

    def at(self, voltage_mv):
        matches = [point for point in self.points if point.voltage_mv == voltage_mv]
        if len(matches) != 1:
            raise ValueError(f"{self.name}: expected one {voltage_mv} mV point, found {len(matches)}")
        return matches[0]

    def supported_points(self):
        """Historical <=3090 raw-sum filter; flagged points stay flagged."""
        return tuple(point for point in self.points if point.raw_sum_mhz <= SUPPORTED_CLOCK_MHZ)


def decode_hex(hex_text, *, allow_tail=False):
    try:
        blob = bytes.fromhex(hex_text)
    except ValueError as exc:
        raise ValueError("VFCurve is not valid hexadecimal") from exc
    if len(blob) != BLOB_SIZE:
        raise ValueError(f"VFCurve has {len(blob)} bytes; expected {BLOB_SIZE}")
    if blob[:8] != HEADER:
        raise ValueError(f"VFCurve header {blob[:8].hex()} is not {HEADER.hex()}")
    end = 8 + RECORD_COUNT * RECORD_SIZE
    triples = list(struct.iter_unpack("<fff", blob[8:end]))
    if len(triples) != RECORD_COUNT:
        raise ValueError("VFCurve did not yield 127 float32 triples")
    if not allow_tail:
        # Every one of the 20 committed profile blobs checked on 2026-09-22
        # repeats the final real offset as the first float of the next slot.
        # Only the bytes AFTER that float are zero-filled. Reject other tails.
        trailing_offset = struct.unpack_from("<f", blob, end)[0]
        if trailing_offset != triples[-1][0] or any(blob[end + 4:]):
            raise ValueError("VFCurve tail is not final offset repeated, then zero-filled")
    voltages = [voltage for _, voltage, _ in triples]
    if (not all(math.isfinite(value) for triple in triples for value in triple)
            or not all(left < right for left, right in zip(voltages, voltages[1:]))):
        raise ValueError("VFCurve has nonfinite fields or nonascending voltages")
    points = []
    for index, (offset, voltage, base) in enumerate(triples):
        # The 845 mV artifact still carries the 840 mV offset; only the NEXT
        # record (850) changes. Flag both sides of a transition, rather than
        # looking only for offset[i] != offset[i-1].
        boundary = ((index > 0 and offset != triples[index - 1][0])
                    or (index + 1 < RECORD_COUNT and offset != triples[index + 1][0]))
        raw_sum = base + offset
        points.append(CurvePoint(index, voltage, base, offset, raw_sum,
                                 None if boundary else raw_sum, boundary))
    return tuple(points)


def load_profiles(path, *, allow_partial=False, allow_tail=False):
    """Read the NVIDIA VEN cfg from a snapshot directory or an explicit file."""
    path = Path(path)
    if path.is_dir():
        candidates = list(path.glob("VEN_10DE*.cfg"))
        if len(candidates) != 1:
            raise ValueError(f"{path}: expected one NVIDIA VEN_10DE cfg, found {len(candidates)}")
        path = candidates[0]
    if not path.is_file() or not path.name.startswith("VEN_10DE"):
        raise ValueError(f"{path}: expected an existing NVIDIA VEN_10DE cfg")
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read_string(path.read_text(encoding="utf-8-sig"))
    if not allow_partial:
        missing = set(PROFILES) - set(parser.sections())
        if missing:
            raise ValueError(f"{path}: missing profiles: {', '.join(sorted(missing))}")
    profiles = {}
    for name in PROFILES:
        if name not in parser.sections():
            if not allow_partial:
                raise ValueError(f"{path}: missing profile {name}")
            continue
        section = parser[name]
        # In lenient mode a slot with no VFCurve is not a profile; skip it rather than decode an
        # empty hex string. The default still decodes it and fails, as before (review 2026-09-24:
        # the model's draft skipped it in both modes, changing the default it was told to keep).
        if allow_partial and not section.get("VFCurve", "").strip():
            continue
        try:
            profiles[name] = Profile(
                name=name,
                power_limit_pct=section["PowerLimit"],
                core_clk_boost_khz=section["CoreClkBoost"],
                mem_clk_boost_khz=section["MemClkBoost"],
                points=decode_hex(section["VFCurve"], allow_tail=allow_tail),
            )
        except KeyError as exc:
            raise ValueError(f"{path}: {name} missing {exc.args[0]}") from exc
    if not profiles:
        raise ValueError(f"{path}: no profile with a VFCurve")
    return path, profiles


def next_record_pairing(points):
    """The editor's next-record reading: base[i] + offset[i+1]; last is None."""
    paired = tuple(
        points[index].base_mhz + points[index + 1].offset_mhz
        for index in range(len(points) - 1)
    )
    return paired + (None,)


@dataclass(frozen=True)
class Check:
    number: int
    passed: bool
    detail: str


def verify_rung(snapshot, profiles, rung="B"):
    """The five §1 pre-run checks, with uncertainty stated at offset boundaries."""
    if rung not in ("B", "C"):
        raise ValueError(f"unknown rung {rung!r}")
    candidate = profiles["Profile1"]
    stock = profiles["Profile3"]
    high = profiles["Profile4"]
    split = profiles["Profile5"]
    window = (1624, 1777) if rung == "B" else (1778, 1931)
    at_720 = candidate.at(720)
    check1 = (at_720.applied_mhz is not None
              and window[0] <= at_720.applied_mhz <= window[1])

    # Equality of STORED fields can be checked even where applied_mhz is
    # uncertain. Check 2 says >=860 mV, exactly as registered.
    mismatches = [point.voltage_mv for point in candidate.points
                  if point.voltage_mv >= 860 and
                  (point.voltage_mv, point.base_mhz, point.offset_mhz) !=
                  (split.points[point.index].voltage_mv,
                   split.points[point.index].base_mhz,
                   split.points[point.index].offset_mhz)]
    check2 = not mismatches

    violations = []
    uncertain_below = []
    for point in candidate.points:
        if point.voltage_mv >= 850:
            continue
        low = stock.points[point.index]
        upper = high.points[point.index]
        if point.voltage_mv != low.voltage_mv or point.voltage_mv != upper.voltage_mv:
            raise ValueError(f"profile voltage grids disagree at index {point.index}")
        if (point.offset_boundary or low.offset_boundary or upper.offset_boundary):
            uncertain_below.append(point.voltage_mv)
            continue
        if not min(low.applied_mhz, upper.applied_mhz) <= point.applied_mhz <= max(
            low.applied_mhz, upper.applied_mhz
        ):
            violations.append(point.voltage_mv)
    # An unassessable envelope is not a pass. Rung B has definite violations
    # at 660-685 mV, regardless of the flagged 650/690/695 boundaries.
    check3 = not violations and not uncertain_below

    point_850 = candidate.at(850)
    point_860 = candidate.at(860)
    # Raw arithmetic reproduces the registered check. The CLI explicitly
    # warns that a boundary-flagged raw sum cannot certify the live curve.
    check4 = point_860.raw_sum_mhz > point_850.raw_sum_mhz

    snapshot = Path(snapshot)
    readme = snapshot / "README.md" if snapshot.is_dir() else snapshot.parent / "README.md"
    cfg_path = next(snapshot.glob("VEN_10DE*.cfg"), None) if snapshot.is_dir() else snapshot
    readme_text = readme.read_text(encoding="utf-8-sig") if readme.is_file() else ""
    sha_prefix = re.search(r"SHA-256 begins `([0-9a-fA-F]+)`", readme_text)
    # The README hash is of the file as Afterburner wrote it, with CRLF endings. Git stores it
    # with LF, so a Linux checkout differs byte-wise; hash the CRLF form on every platform.
    cfg_crlf = (cfg_path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                if cfg_path and cfg_path.is_file() else b"")
    hash_matches = bool(sha_prefix and cfg_crlf and
                        hashlib.sha256(cfg_crlf).hexdigest().startswith(
                            sha_prefix.group(1).lower()))
    check5 = bool(hash_matches and "before any rung" in readme_text)

    return (
        Check(1, check1, f"720 mV: {at_720.applied_mhz} MHz; window {window[0]}-{window[1]}"),
        Check(2, check2, f"stored triples >=860 mV vs P5: {len(mismatches)} differences"),
        Check(3, check3,
              f"definite envelope failures below 850 mV: {violations}; "
              f"boundary-uncertain voltages: {uncertain_below}"),
        Check(4, check4,
              f"raw 850 -> 860 mV: {point_850.raw_sum_mhz:g} -> "
              f"{point_860.raw_sum_mhz:g} MHz; "
              f"boundary flags: {point_850.offset_boundary}/{point_860.offset_boundary}; "
              "raw check does not certify live applied clocks"),
        Check(5, check5,
              "snapshot cfg exists, README hash matches, and README states pre-run timing; "
              "chronology is source-reported, not proved by file contents"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="snapshot directory or NVIDIA VEN cfg")
    parser.add_argument("--verify-rung", nargs="?", const="B", choices=("B", "C"),
                        help="run the five registered floor-ladder pre-run checks (default B)")
    parser.add_argument("--json", action="store_true", help="emit all raw points and safety flags")
    parser.add_argument("--lenient", action="store_true",
                        help="read stores with fewer than five profiles and a nonzero tail")
    parser.add_argument("--pairing", choices=("stored", "next"), default="stored",
                        help="stored: base+offset (default); next: base[i]+offset[i+1]")
    args = parser.parse_args()
    if args.json and args.verify_rung:
        parser.error("choose --json or --verify-rung")
    if args.verify_rung and args.lenient:
        parser.error("--verify-rung is 5060 Ti only; it cannot be combined with --lenient")
    try:
        source, profiles = load_profiles(args.source,
                                         allow_partial=args.lenient,
                                         allow_tail=args.lenient)
        if args.verify_rung:
            checks = verify_rung(args.source, profiles, args.verify_rung)
            for check in checks:
                print(f"CHECK {check.number}: {'PASS' if check.passed else 'FAIL'}: {check.detail}")
            return 1 if any(not check.passed for check in checks) else 0
        if args.json:
            output = {name: {"power_limit_pct": profile.power_limit_pct,
                             "core_clk_boost_khz": profile.core_clk_boost_khz,
                             "mem_clk_boost_khz": profile.mem_clk_boost_khz,
                             "points": [asdict(point) for point in profile.points],
                             "next_pair_mhz": [value for value in next_record_pairing(profile.points)]}
                      for name, profile in profiles.items()}
            print(json.dumps({"source": str(source), "profiles": output}, indent=2))
            return
        if args.pairing == "next":
            for name, profile in profiles.items():
                paired = next_record_pairing(profile.points)
                lines = [f"  {point.voltage_mv:g} mV: {clock:g} MHz (next-record pairing)"
                         for point, clock in zip(profile.points, paired)
                         if clock is not None and clock <= SUPPORTED_CLOCK_MHZ]
                print(f"{name}: next-record pairing, {len(lines)} points <=3090 MHz; "
                      "NOT the committed default reading")
                for line in lines:
                    print(line)
            return
        for name, profile in profiles.items():
            uncertain = [point for point in profile.points if point.offset_boundary]
            print(f"{name}: 127 raw points; {len(profile.supported_points())} raw sums <=3090 MHz; "
                  f"{len(uncertain)} offset-boundary points flagged")
            for point in uncertain:
                print(f"  {point.voltage_mv:g} mV: stored offset {point.offset_mhz:+g}, "
                      f"base {point.base_mhz:g}, raw sum {point.raw_sum_mhz:g}; "
                      "applied clock UNRESOLVED")
    except (OSError, ValueError, configparser.Error) as exc:
        parser.exit(2, f"decode failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
