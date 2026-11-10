"""Score REGISTERED-PREDICTIONS section 15 (registered 2026-10-03), without collecting data.

Usage: python analysis/score_rerun15.py r1|r2|r3 DIRECTORY

DIRECTORY/rerun15-inputs.json binds logical roles to evidence, avoiding guesses from filenames.
The manifest has {"sweeps": {ROLE: DESCRIPTOR}, "references": {"r1": DESCRIPTOR,
"r2": DESCRIPTOR}}. Relative evidence paths resolve against DIRECTORY. A descriptor has:
  sweep: path to *_sweep.csv (omitted for the fixed historical references)
  hwinfo: raw HWiNFO CSV; utc_offset_minutes: the collection-time offset, e.g. -420
  nvidia_samples: optional CSV with timestamp_unix and memory_clock_mhz
  wrapper: wrapper-result.json (defaults beside the sweep)
  witness: {profile_store: saved pre-arm NVIDIA VEN_*.cfg, snapshot: curve3|rungB|rungC,
            profile_slot: 1|2|3|4, witnessed_at_unix: pre-arm epoch seconds,
            driver: "616.92", power_limit_w: 180|200, memory_loaded_mhz: 13801|16301,
            offsets_mhz: nonempty map of all offsets read from mVolt+,
            restored_byte_for_byte: true, afterburner_closed: true}
Instead of nvidia_samples, each sweep row may carry memory_clock_samples_mhz, a JSON array of
its actual in-window readings. Min/avg/max summaries cannot establish the registered median or
low count. Missing evidence is NOT SCOREABLE, never inferred from those summaries.

R1 roles: stock-open-membw, stock-gemm, curve3-membw, curve3-gemm, stock-close-membw.
R2 roles: stock-open-membw, p4-membw, p2-membw, stock-close-membw.
R3 roles: {stock-open,rungB,rungC,stock-close}-{each score_control10.WORKLOADS entry}.
Each role may instead be a list of up to two descriptors: a failed desktop-load attempt then
its sole retry. Both attempts are checked; a later good sweep cannot hide a prior second failure.
Historical references always use the literal committed CSVs below, as recorded: each point's
recorded memory maximum must be 13801 or 14001, and the minimum and mean are reported (section 15,
amended 2026-10-03 before collection). Reference descriptors are optional and unused.
HWiNFO's NVIDIA memory column is the one immediately before Crossbar.

Limits: N=1 chip. Witnesses are collection records, not live checks by this offline scorer.
This file does not certify manual app closure, operator absence, or the runner's reset paths.
"""

import argparse
import csv
import datetime
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

from analyze_sweep import efficiencyPeak, loadSweep
from score_control10 import WORKLOADS, read_suite, stock_return

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "frequency-sweeps"
BAND = [1402, 1477, 1560, 1635, 1710, 1792, 1867, 1942, 2025, 2100]
GRID = [1237, 1395, 1545, 1702, 1852, 2010, 2167, 2317, 2475, 2625, 2782, 2932, 3090]
HISTORICAL = {
    "r1": DATA / "5060ti-memmatched-20260926/20260926-155100_5060ti-4j-stock-membw_sweep.csv",
    "r2": DATA / "membw-anomaly-20260819/20260820-211630_5060ti-stock-volt-membw_sweep.csv",
}
ORIGINAL_RUNGS = {"rungB": DATA / "5060ti-rungB-suite-20260923",
                  "rungC": DATA / "5060ti-rungC-suite-20260926"}
SNAPSHOTS = {name: ROOT / "data/afterburner-profiles" / directory for name, directory in (
    ("curve3", "5060ti-profiles-20260926-curve3"),
    ("rungB", "5060ti-profiles-20260922-rungB"),
    ("rungC", "5060ti-profiles-20260926-rungC"))}
SECTIONS = ("Startup", "Profile1", "Profile2", "Profile3", "Profile4", "Profile5")


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("a reading is not finite")
    return result


def csv_rows(path, encoding="utf-8-sig"):
    with Path(path).open(newline="", encoding=encoding) as handle:
        return list(csv.DictReader(handle))


def json_read(path):
    with Path(path).open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def resolve(directory, value):
    path = Path(value)
    return path if path.is_absolute() else directory / path


def section_hash(path):
    """Profile-Hash.ps1's LF, sorted-key canonicalization, including Startup and every slot."""
    sections, current = {}, None
    for raw in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, {})
        elif current and line and not line.startswith(";") and "=" in line:
            key, value = line.split("=", 1)
            sections[current][key.strip()] = value.strip()
    text = ""
    for name in SECTIONS:
        if name not in sections:
            raise ValueError(f"the profile store lacks [{name}]")
        text += f"[{name}]\n"
        text += "".join(f"{key}={sections[name][key]}\n" for key in sorted(sections[name]))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def memory_rule(values, loaded, hwinfo=False):
    """Exact state rule after converting HWiNFO's one-decimal raw clock to effective integer MHz."""
    vals = [round(number(v) * 8) if hwinfo else number(v) for v in values]
    if not vals:
        raise ValueError("there are no in-window memory readings")
    low = sum(v < loaded for v in vals)
    median, maximum = statistics.median(vals), max(vals)
    ok = median == loaded and maximum in (loaded, loaded + 200) and low <= 1 and all(v >= 0 for v in vals)
    return {"ok": ok, "count": len(vals), "low": low, "median": median, "maximum": maximum}


def hwinfo_read(path, offset):
    with Path(path).open(newline="", encoding="latin-1") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError("the HWiNFO log is empty")
    header = rows[0]
    xbars = [i for i, c in enumerate(header) if c == "GPU Crossbar Clock [MHz]"]
    if len(xbars) != 1:
        raise ValueError("the NVIDIA Crossbar block is missing or ambiguous")
    x = xbars[0]
    mem = max((i for i, c in enumerate(header[:x]) if c == "GPU Memory Clock [MHz]"), default=-1)
    if mem < 0 or x - mem >= 6:
        raise ValueError("no NVIDIA memory column next to Crossbar")
    # The measured clock is not the memory-state code tested by the registration.
    fps = header.index("Framerate Presented (avg) [FPS]") if "Framerate Presented (avg) [FPS]" in header else None
    bus = next((i for i in range(x + 1, min(x + 13, len(header))) if header[i] == "GPU Bus Load [%]"), None)
    if bus is None:
        bus = max((i for i in range(mem, x) if header[i] == "GPU Bus Load [%]"), default=None)
    tz = datetime.timezone(datetime.timedelta(minutes=number(offset)))
    parsed = []
    for row in rows[1:]:
        try:
            stamp = datetime.datetime.strptime(row[0] + " " + row[1], "%d.%m.%Y %H:%M:%S.%f")
        except (ValueError, IndexError):
            # HWiNFO emits extra unit/header lines; malformed numeric data are refused below.
            continue
        parsed.append((stamp.replace(tzinfo=tz).timestamp(), row))
    return parsed, mem, x, fps, bus


def roles_for(part):
    if part == "r3":
        return [f"{arm}-{workload}" for arm in ("stock-open", "rungB", "rungC", "stock-close") for workload in WORKLOADS]
    return (["stock-open-membw", "stock-gemm", "curve3-membw", "curve3-gemm", "stock-close-membw"]
            if part == "r1" else ["stock-open-membw", "p4-membw", "p2-membw", "stock-close-membw"])


def configuration(directory, descriptor, role, loaded):
    w = descriptor.get("witness", {})
    if not isinstance(w, dict):
        return ["the pre-arm witness is not an object"]
    failures = []
    expected = "rungB" if role.startswith("rungB-") else "rungC" if role.startswith("rungC-") else "curve3"
    snapshot = w.get("snapshot", expected)
    if role.startswith(("rungB-", "rungC-", "curve3-")) and snapshot != expected:
        failures.append(f"the witness names {snapshot}, not {expected}")
    try:
        canonical = list(SNAPSHOTS[snapshot].glob("VEN_10DE*.cfg"))
        if len(canonical) != 1 or section_hash(resolve(directory, w["profile_store"])) != section_hash(canonical[0]):
            failures.append("Startup and Profile1-5 do not hash-match the named committed store")
    except (KeyError, OSError, ValueError) as exc:
        failures.append(f"the profile-store witness cannot be checked ({exc})")
    power = 180 if role.startswith("stock-") else 200
    slot = 3 if role.startswith("stock-") else 4 if role.startswith("p4-") else 2 if role.startswith("p2-") else 1
    if w.get("profile_slot") != slot:
        failures.append(f"the applied-profile witness is not slot {slot}")
    if w.get("driver") != "616.92":
        failures.append("the driver witness is not 616.92")
    if w.get("power_limit_w") != power or w.get("memory_loaded_mhz") != loaded:
        failures.append(f"the live power/memory witness is not {power} W and {loaded} MHz")
    offsets = w.get("offsets_mhz")
    if not isinstance(offsets, dict) or not offsets or any(v != 0 for v in offsets.values()):
        failures.append("the recorded mVolt+ offsets are missing or not all zero")
    if role.startswith(("rungB-", "rungC-", "curve3-")):
        if w.get("restored_byte_for_byte") is not True or w.get("afterburner_closed") is not True:
            failures.append("the byte-for-byte restoration with Afterburner closed is not recorded")
    return failures


def read_evidence(directory, descriptor, role, grid, historical=None):
    if not isinstance(descriptor, dict):
        raise ValueError(f"{role}'s evidence descriptor must be an object")
    path = historical or resolve(directory, descriptor["sweep"])
    try:
        rows = loadSweep(path)
    except ZeroDivisionError as exc:
        raise ValueError(f"{role} has zero board power") from exc
    targets = [r["target"] for r in rows]
    if sorted(targets) != grid or len(set(targets)) != len(targets):
        raise ValueError(f"{role} does not have every usable registered target exactly once")
    if any(r["throughput"] <= 0 or r["power"] <= 0 or
           not all(math.isfinite(r[k]) for k in ("throughput", "power", "mhz")) for r in rows):
        raise ValueError(f"{role} has invalid throughput, power or achieved clocks")
    raw = {int(number(r["target_frequency_mhz"])): r for r in csv_rows(path)}
    if len(raw) != len(rows):
        raise ValueError(f"{role} has extra, duplicate or excluded benchmark points")
    loaded = 16301 if role.startswith(("p4-", "p2-", "rungB-", "rungC-")) else 13801
    result = {"path": path, "rows": {r["target"]: r for r in rows}, "failures": [], "checks": [], "xbar": {}}
    if historical is None:
        try:
            wrapper = json_read(resolve(directory, descriptor.get("wrapper", str(path.parent / "wrapper-result.json"))))
            if not isinstance(wrapper, dict):
                raise ValueError("the wrapper record is not an object")
            bad = (wrapper.get("desktopLoad") == "DESKTOP LOAD" or
                   any(wrapper.get(k) in (8, "8") for k in ("exitCode", "sweepExitCode", "wrapperExitCode")))
            result["desktop_failed"] = bad
            if bad:
                result["failures"].append("the wrapper reports DESKTOP LOAD or exit 8")
            elif wrapper.get("desktopLoad") != "quiet" or wrapper.get("sweepExitCode") not in (0, "0"):
                result["failures"].append("the wrapper does not record a successful quiet sweep")
        except (OSError, ValueError) as exc:
            result["failures"].append(f"the wrapper record is unavailable ({exc})")
        result["failures"].extend(configuration(directory, descriptor, role, loaded))
        try:
            witnessed = number(descriptor["witness"]["witnessed_at_unix"])
            if witnessed >= min(number(p["window_start_unix"]) for p in raw.values()):
                result["failures"].append("the configuration witness was not recorded before collection")
        except (KeyError, TypeError, ValueError) as exc:
            result["failures"].append(f"the pre-arm witness time is unavailable ({exc})")
    else:
        # Section 15 (amended 2026-10-03, before collection): a named historical comparator is
        # used as recorded. It predates the per-sample memory record, so it is held only to its
        # recorded per-point maximum lying in the stock loaded pair, and its minimum and mean are
        # reported beside that.
        for target, point in raw.items():
            try:
                low, mean, high = (number(point[k]) for k in
                                   ("memory_clock_min_mhz", "memory_clock_avg_mhz", "memory_clock_max_mhz"))
                ok = high in (13801, 14001)
                result["checks"].append(f"At {target} MHz, the recorded memory clock runs {low:g} to {high:g} MHz "
                                        f"(mean {mean:g}); the maximum {'is' if ok else 'is not'} in the stock loaded pair.")
                if not ok:
                    result["failures"].append(f"{target} MHz has a recorded memory maximum outside 13801-14001")
            except (KeyError, TypeError, ValueError) as exc:
                result["failures"].append(f"{target} MHz lacks a recorded memory range ({exc})")
        return result
    try:
        hw, mem, xbar, fps, bus = hwinfo_read(resolve(directory, descriptor["hwinfo"]), descriptor["utc_offset_minutes"])
    except (KeyError, OSError, ValueError) as exc:
        hw = None
        result["failures"].append(f"HWiNFO in-window evidence is unavailable ({exc})")
    samples = csv_rows(resolve(directory, descriptor["nvidia_samples"])) if descriptor.get("nvidia_samples") else None
    for target, point in raw.items():
        try:
            start, end = number(point["window_start_unix"]), number(point["window_end_unix"])
            if start >= end:
                raise ValueError("the benchmark window is empty or reversed")
            checks = []
            try:
                if samples is not None:
                    ns = [number(s["memory_clock_mhz"]) for s in samples
                          if start <= number(s["timestamp_unix"]) <= end]
                else:
                    ns = json.loads(point["memory_clock_samples_mhz"])
                    if not isinstance(ns, list):
                        raise ValueError("the memory samples are not an array")
                checks.append(("nvidia-smi", memory_rule(ns, loaded)))
            except (KeyError, TypeError, ValueError) as exc:
                result["failures"].append(f"{target} MHz lacks nvidia-smi sample evidence ({exc})")
            if hw is not None:
                window = [row for stamp, row in hw if start <= stamp <= end]
                checks.append(("HWiNFO", memory_rule([r[mem] for r in window], loaded, hwinfo=True)))
                result["xbar"][target] = statistics.median(number(r[xbar]) for r in window)
                if historical is None:
                    if fps is None or bus is None:
                        result["failures"].append(f"{target} MHz has no complete desktop-load telemetry")
                    else:
                        f = statistics.median(number(r[fps]) for r in window)
                        b = statistics.median(number(r[bus]) for r in window)
                        result["checks"].append(f"At {target} MHz, desktop telemetry is {f:g} fps and {b:g}% bus load.")
                        # Framerate alone (section 15 amended 2026-10-03, before collection);
                        # kernels reach 13-36% bus load by themselves on quiet desktops.
                        if f > 30:
                            result["desktop_failed"] = True
                            result["failures"].append(f"{target} MHz exceeds 30 fps or 10% bus load")
            for instrument, check in checks:
                result["checks"].append(f"At {target} MHz, {instrument} has {check['count']} readings, "
                                        f"median {check['median']:g} MHz, maximum {check['maximum']:g} MHz, "
                                        f"and {check['low']} low readings; the memory gate "
                                        f"{'passes' if check['ok'] else 'fails'}.")
                if not check["ok"]:
                    result["failures"].append(f"{target} MHz fails the {instrument} memory rule")
        except (KeyError, TypeError, ValueError, IndexError, statistics.StatisticsError) as exc:
            result["failures"].append(f"{target} MHz lacks usable in-window evidence ({exc})")
    return result


def read_role(directory, descriptor, role, grid):
    attempts = descriptor if isinstance(descriptor, list) else [descriptor]
    if not 1 <= len(attempts) <= 2:
        raise ValueError(f"{role} must have one attempt or one attempt plus its sole retry")
    if any(not isinstance(d, dict) for d in attempts):
        raise ValueError(f"{role}'s evidence descriptors must be objects")
    readings = []
    for i, d in enumerate(attempts):
        try:
            readings.append(read_evidence(directory, d, role, grid))
        except (KeyError, OSError, ValueError, TypeError):
            if i != 0 or len(attempts) != 2:
                raise
            path = resolve(directory, d["sweep"])
            w = json_read(resolve(directory, d.get("wrapper", str(path.parent / "wrapper-result.json"))))
            if w.get("desktopLoad") != "DESKTOP LOAD" and not any(w.get(k) in (8, "8") for k in ("exitCode", "sweepExitCode", "wrapperExitCode")):
                raise ValueError(f"{role}'s incomplete first attempt has no desktop-load failure record")
            readings.append({"path": path, "desktop_failed": True})
    chosen = readings[-1]
    if len(readings) == 2:
        first = readings[0]
        if not first.get("desktop_failed"):
            chosen["failures"].append("a retry was supplied without an initial desktop-load failure")
        if first["path"] == chosen["path"]:
            chosen["failures"].append("the retry reuses the failed sweep file")
        chosen["checks"].insert(0, "The initial desktop-load attempt was failed and excluded; the sole retry is used.")
    return chosen


def score(part, directory):
    directory = Path(directory).resolve()
    manifest = json_read(directory / "rerun15-inputs.json")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("sweeps"), dict):
        raise ValueError("the input manifest must contain a sweeps object")
    if not isinstance(manifest.get("references", {}), dict):
        raise ValueError("the references must be an object")
    evidence, lines, predictions = {}, [], {}
    roles = roles_for(part)
    for role in roles:
        grid = GRID if part == "r3" or role.endswith("gemm") else BAND
        try:
            e = read_role(directory, manifest["sweeps"][role], role, grid)
        except (KeyError, OSError, ValueError, TypeError) as exc:
            e = {"rows": {}, "xbar": {}, "checks": [], "failures": [str(exc)]}
        evidence[role] = e
        lines.extend(f"For {role}, {line}" for line in e["checks"])
        lines.append(f"The evidence gate for {role} {'passes' if not e['failures'] else 'fails'}.")
        lines.extend(f"For {role}, {failure}." for failure in e["failures"])

    def prediction(name, dependencies, evaluate):
        if any(not evidence[d]["rows"] for d in dependencies):
            status, detail = "NOT SCOREABLE", "required benchmark points are missing"
        else:
            try:
                holds, detail = evaluate()
                status = "HOLDS" if holds else "FAILS"
                if any(evidence[d]["failures"] for d in dependencies) or not drift_ok:
                    status = "NOT SCOREABLE"
            except (KeyError, OSError, ValueError, ZeroDivisionError) as exc:
                status, detail = "NOT SCOREABLE", str(exc)
        predictions[name] = status
        lines.append(f"The {name} prediction is {status}: {detail}.")

    if part in ("r1", "r2"):
        a, z = evidence["stock-open-membw"], evidence["stock-close-membw"]
        drift = None
        if a["rows"] and z["rows"]:
            drift = 100 * (statistics.mean(r["throughput"] for r in z["rows"].values()) /
                           statistics.mean(r["throughput"] for r in a["rows"].values()) - 1)
        drift_ok = drift is not None and abs(drift) <= 1.5 + 1e-12 and not a["failures"] and not z["failures"]
        lines.append(f"The closing/opening stock full-band mean drift is {drift if drift is not None else 'unavailable'}%; "
                     f"the 1.5% drift gate {'passes' if drift_ok else 'fails'}.")
        treatment = "curve3-membw" if part == "r1" else "p4-membw"
        band = [t for t in BAND if 1560 <= t <= 1867]
        ratios = lambda: {t: evidence[treatment]["rows"][t]["throughput"] / a["rows"][t]["throughput"] for t in band}
        prediction("primary plateau", [treatment, "stock-open-membw"],
                   lambda: (all(r < 1 for r in ratios().values()), f"treatment/opening stock ratios are {ratios()}"))
        telemetry_targets = [t for t in BAND if 1402 <= t <= 1867]

        def telemetry():
            tx = [evidence[treatment]["xbar"][t] for t in telemetry_targets]
            sx = [a["xbar"][t] for t in telemetry_targets]
            return (all(1300 <= x <= 1360 for x in tx) and all(b > a for a, b in zip(sx, sx[1:])),
                    f"treatment crossbar clocks are {tx}, and opening stock clocks are {sx}; stock must rise at each target")
        prediction("crossbar telemetry", [treatment, "stock-open-membw"], telemetry)
        if part == "r1":
            def power():
                values = {t: evidence["curve3-gemm"]["rows"][t]["power"] /
                          evidence["stock-gemm"]["rows"][t]["power"] for t in GRID if 1545 <= t <= 2475}
                return all(v < 1 for v in values.values()), f"curve 3/stock board-power ratios are {values}"
            prediction("secondary gemm power", ["curve3-gemm", "stock-gemm"], power)
            try:
                descriptive = {t: evidence[treatment]["rows"][t]["throughput"] / a["rows"][t]["throughput"] for t in (1560, 1710, 1867)}
                lines.append(f"Reported, not scored: curve 3/stock ratios are {descriptive}, beside section 12's 0.924, 0.886, 0.863.")
            except KeyError:
                lines.append("Reported, not scored: the three curve 3/stock ratios are unavailable.")
        else:
            def repair():
                values = {t: evidence["p2-membw"]["rows"][t]["throughput"] /
                          evidence["p4-membw"]["rows"][t]["throughput"] for t in band}
                return all(v > 1 for v in values.values()) and values[1867] >= 1.08, f"P2/P4 ratios are {values}; 1867 must be at least 1.08"
            prediction("repair", ["p2-membw", "p4-membw"], repair)
            lines.append("Reported, not scored: P4/stock is not memory-matched, and the 08-20 oc profile is not proved identical to today's P4.")
        try:
            evidence["historical-stock"] = read_evidence(directory, manifest.get("references", {}).get(part, {}),
                                                         "historical-stock", BAND, HISTORICAL[part])
        except (KeyError, OSError, ValueError, TypeError) as exc:
            evidence["historical-stock"] = {"rows": {}, "checks": [], "failures": [str(exc)]}
        old = evidence["historical-stock"]
        lines.append(f"The named historical stock CSV is {HISTORICAL[part].relative_to(ROOT).as_posix()}.")
        lines.extend(f"For the historical reference, {line}" for line in old["checks"])
        lines.extend(f"The historical reference is NOT SCOREABLE because {reason}." for reason in old["failures"])

        def load_prediction():
            clean = statistics.mean(r["throughput"] for r in a["rows"].values())
            previous = statistics.mean(r["throughput"] for r in old["rows"].values())
            uplift = 100 * (clean / previous - 1)
            return uplift >= 3 - 1e-12, f"the clean/old full-band mean uplift is {uplift:.6f}%, against at least 3%"
        prediction("load uplift", ["stock-open-membw", "historical-stock"], load_prediction)
    else:
        suites, optima, medians = {}, {}, {}
        for arm in ("stock-open", "rungB", "rungC", "stock-close"):
            if all(evidence[f"{arm}-{w}"]["rows"] for w in WORKLOADS):
                # Reuse section 10's optimum rule, retaining TARGET rather than achieved MHz.
                suites[arm], targets = read_suite({w: evidence[f"{arm}-{w}"]["path"] for w in WORKLOADS})
                optima[arm] = {w: suites[arm][w]["optimum"] for w in WORKLOADS}
                medians[arm] = statistics.median(optima[arm].values())
                lines.append(f"The {arm} target-grid optima are {optima[arm]}, with median {medians[arm]:g} MHz.")
        drift = stock_return(suites["stock-open"], suites["stock-close"], GRID) if "stock-open" in suites and "stock-close" in suites else {}
        drift_ok = bool(drift) and max(drift.values()) <= 1.5 + 1e-12 and all(
            not evidence[f"{arm}-{w}"]["failures"] for arm in ("stock-open", "stock-close") for w in WORKLOADS)
        lines.append(f"The stock per-workload median absolute matched-target throughput changes are {drift}%; "
                     f"the worst-workload 1.5% drift gate {'passes' if drift_ok else 'fails'}.")
        for arm, predicted in (("rungB", 1702), ("rungC", 1852)):
            dependencies = [f"{arm}-{w}" for w in WORKLOADS]
            prediction(f"{arm} primary median", dependencies,
                       lambda arm=arm, p=predicted: (medians[arm] == p, f"the median is {medians[arm]:g} MHz; the prediction is {p} MHz"))
            prediction(f"{arm} secondary count", dependencies,
                       lambda arm=arm, p=predicted: (sum(t == p for t in optima[arm].values()) >= 7,
                                                    f"{sum(t == p for t in optima[arm].values())} of 12 workloads land on {p} MHz; at least 7 are required"))
        prediction("tertiary monotone distinct rungs", roles,
                   lambda: (medians["stock-open"] <= medians["rungB"] < medians["rungC"] and
                            medians["stock-close"] <= medians["rungB"],
                            f"opening stock/B/C/closing stock medians are {medians}; B and C must be distinct, above both stock medians"))
        for arm in ("rungB", "rungC"):
            try:
                paths = {w: list(ORIGINAL_RUNGS[arm].glob(f"*_{'5060ti-' + arm + '-suite-' + w}_sweep.csv")) for w in WORKLOADS}
                if any(len(p) != 1 for p in paths.values()):
                    raise ValueError("the original suite is incomplete or ambiguous")
                originals = {w: efficiencyPeak(loadSweep(paths[w][0]))["target"] for w in WORKLOADS}
                agrees = sum(optima[arm][w] == originals[w] for w in WORKLOADS)
                agreement = {w: {"original": optima[arm][w] == originals[w],
                                  **{s: optima[arm][w] == optima[s][w] for s in ("stock-open", "stock-close")}}
                             for w in WORKLOADS}
                stocks = {s: sum(agreement[w][s] for w in WORKLOADS) for s in ("stock-open", "stock-close")}
                original_count = sum(t == (1702 if arm == "rungB" else 1852) for t in originals.values())
                lines.append(f"Reported, not scored: {arm} per-workload original optima are {originals}; "
                             f"agreement is {agrees} of 12 with that original and {stocks} with this session's stock suites; "
                             f"the original has {original_count} of 12 on its prediction (the registry says 9 of 12); "
                             f"the per-workload agreements are {agreement}.")
            except (KeyError, OSError, ValueError) as exc:
                lines.append(f"Reported, not scored: {arm} original/stock agreement is unavailable ({exc}).")

    failed_evidence = any(e["failures"] for e in evidence.values())
    verdict = ("NOT SCOREABLE" if failed_evidence or not drift_ok or "NOT SCOREABLE" in predictions.values()
               else "HOLDS" if all(p == "HOLDS" for p in predictions.values()) else "FAILS")
    lines.append(f"The {part.upper()} verdict is {verdict}; individual predictions retain their own verdicts above.")
    lines.append("N=1 chip, one session and one accepted collection per arm; twelve workloads are repeated outcomes on that chip.")
    lines.append("The configuration witnesses are saved records; manual app closure, operator absence, complete offset-domain coverage, and reset/restoration on exit require runner review.")
    lines.append("Section 15 was registered 2026-10-03 before collection, with these scoring choices adopted; no results are pooled with the originals.")
    return {"verdict": verdict, "predictions": predictions, "evidence": evidence, "lines": lines}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("part", choices=("r1", "r2", "r3"))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        result = score(args.part, args.directory)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"The {args.part.upper()} verdict is NOT SCOREABLE because the input cannot be read: {exc}.")
        print("N=1 chip; no collection was run by this scorer.")
        return 2
    print("\n".join(result["lines"]))
    return 2 if result["verdict"] == "NOT SCOREABLE" else 1 if result["verdict"] == "FAILS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
