"""Regression checks for the read-only measurement hash gate.

All writes occur in a temporary Git repository. The real data tree is only read
once to copy the voltage file involved in the documented 855 MHz mutation.
"""

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_data_hashes as gate

ROOT = Path(__file__).resolve().parent.parent
RELATIVE_VOLTAGE = Path(
    "data/frequency-sweeps/rtx3070ti-20260825/hwinfo-silent/"
    "20260827-170331_rtx3070ti-silent-gemm-matched2130-hwinfo_sweep_voltage.csv"
)

passed = 0


def check(description, condition):
    global passed
    if not condition:
        print(f"  [FAIL] {description}")
        raise AssertionError(description)
    passed += 1
    print(f"  [PASS] {description}")


def run_quiet(fn, *args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        verdict = fn(*args)
    return verdict, output.getvalue()


with tempfile.TemporaryDirectory(prefix="headroom-hash-test-") as temporary:
    root = Path(temporary)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
    voltage = root / RELATIVE_VOLTAGE
    voltage.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / RELATIVE_VOLTAGE, voltage)
    subprocess.run(["git", "add", "--", RELATIVE_VOLTAGE.as_posix()], cwd=root, check=True,
                   capture_output=True)
    manifest = root / gate.DEFAULT_MANIFEST
    original = voltage.read_bytes()

    verdict, output = run_quiet(gate.check, root, manifest)
    check("missing baseline fails closed", verdict == 1 and "hash list missing" in output)

    verdict, _ = run_quiet(gate.write, root, manifest)
    check("write generates a temporary baseline", verdict == 0 and manifest.is_file())
    saved = json.loads(manifest.read_text(encoding="utf-8"))
    check("baseline records the normalization convention",
          saved["normalization"] == gate.NORMALIZATION)
    verdict, _ = run_quiet(gate.check, root, manifest)
    check("unaltered copied voltage file passes", verdict == 0)
    manifest.write_bytes(b"\xef\xbb\xbf" + manifest.read_bytes())
    verdict, _ = run_quiet(gate.check, root, manifest)
    check("PowerShell-style UTF-8 BOM on the hash list is accepted", verdict == 0)

    normalized = original.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    voltage.write_bytes(normalized.replace(b"\n", b"\r\n"))
    verdict, _ = run_quiet(gate.check, root, manifest)
    check("CRLF checkout matches an LF baseline", verdict == 0)
    voltage.write_bytes(normalized.replace(b"\n", b"\r"))
    verdict, _ = run_quiet(gate.check, root, manifest)
    check("lone-CR checkout also matches", verdict == 0)

    # The documented failure: only the 855 MHz row's voltage changes, in the temp copy.
    lines = normalized.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if line.startswith(b"855,")]
    check("source has exactly one 855 MHz row", len(hits) == 1)
    index = hits[0]
    check("855 MHz row carries the expected original 0.819 V",
          lines[index].count(b",0.819,") == 1)
    lines[index] = lines[index].replace(b",0.819,", b",0.900,")
    voltage.write_bytes(b"".join(lines))
    verdict, output = run_quiet(gate.check, root, manifest)
    check("855 MHz 0.819 to 0.900 V mutation fails as changed",
          verdict == 1 and "[changed]" in output and RELATIVE_VOLTAGE.as_posix() in output)

    voltage.write_bytes(original)
    voltage.unlink()
    verdict, output = run_quiet(gate.check, root, manifest)
    check("deleted tracked measurement fails", verdict == 1 and "[missing or symlinked]" in output)
    voltage.write_bytes(original)

    new_file = root / "data/frequency-sweeps/new-run_sweep.csv"
    new_file.write_bytes(b"target,voltage\n855,0.819\n")
    verdict, output = run_quiet(gate.check, root, manifest)
    check("nonignored new CSV fails even before git add",
          verdict == 1 and "[unhashed new]" in output and "new-run_sweep.csv" in output)
    new_file.unlink()

    readme = root / "data/frequency-sweeps/README.md"
    readme.write_text("legitimate documentation edit\n", encoding="utf-8")
    (root / "data/MANIFEST.csv").write_text("generated metadata\n", encoding="utf-8")
    ignored = root / "data/external/download.csv"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("third-party download\n", encoding="utf-8")
    (root / ".gitignore").write_text("data/external/*.csv\n", encoding="utf-8")
    verdict, _ = run_quiet(gate.check, root, manifest)
    check("README, generated manifest and ignored download are outside scope", verdict == 0)

    # Widened scope: a profile snapshot is a record too, and was unguarded in the first version.
    profile = root / "data/afterburner-profiles/snap/VEN_10DE.cfg"
    profile.parent.mkdir(parents=True)
    profile.write_bytes(b"[Profile1]\nVFCurve=0000\n")
    subprocess.run(["git", "add", "--", "data/afterburner-profiles/snap/VEN_10DE.cfg"], cwd=root,
                   check=True, capture_output=True)
    verdict, output = run_quiet(gate.check, root, manifest)
    check("an unhashed profile snapshot (.cfg) is in scope and fails",
          verdict == 1 and "VEN_10DE.cfg" in output)
    run_quiet(gate.write, root, manifest)
    profile.write_bytes(b"[Profile1]\nVFCurve=FFFF\n")
    verdict, output = run_quiet(gate.check, root, manifest)
    check("an edited profile snapshot fails as changed", verdict == 1 and "[changed]" in output)
    (root / "data/.gitkeep").write_text("", encoding="utf-8")
    profile.write_bytes(b"[Profile1]\nVFCurve=0000\n")
    verdict, _ = run_quiet(gate.check, root, manifest)
    check(".gitkeep is outside scope", verdict == 0)
    saved = json.loads(manifest.read_text(encoding="utf-8"))

    saved["algorithm"] = "md5"
    manifest.write_text(json.dumps(saved), encoding="utf-8")
    verdict, output = run_quiet(gate.check, root, manifest)
    check("unsupported hash-list metadata fails closed",
          verdict == 1 and "unsupported value" in output)

print(f"{passed} checks passed.")
