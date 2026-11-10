# tools/afterburner — read-only profile decoder

**It reads files only.** It never starts Afterburner, applies a profile, or touches NVML or the
GPU.

`decode_profiles.py` decodes the `VFCurve` hex in an NVIDIA `VEN_*.cfg` profile store, or in a
snapshot directory under `data/afterburner-profiles/`. The format is in
`docs/AFTERBURNER-PROFILES.md`: an 8-byte header, 127 real (offset, voltage mV, base MHz) float32
records, then a tail whose first slot repeats the last offset.

```
python tools/afterburner/decode_profiles.py <snapshot dir or VEN cfg>
python tools/afterburner/decode_profiles.py <snapshot dir> --verify-rung B   # or C
python tools/afterburner/decode_profiles.py <snapshot dir or VEN cfg> --json
```

**Where the stored offset changes value, `base + offset` is not the applied clock.** Rung B's
845 mV point is stored as (+176, 2362), which sums to 2538, while the curve editor shows 2362. So
the decoder flags both sides of every offset change and sets `applied_mhz` to null there. The raw
sum stays in `raw_sum_mhz`. **At a flagged point, trust the curve editor, not this tool.**

**`--verify-rung` runs the five pre-run checks from `REGISTERED-PREDICTIONS.md` §1** and prints
each verdict. **Check 3 fails at 650–690 mV for any raised rung.** That comes from how the
check was registered (P4 is stock there), not from the build. So the command exits nonzero even for
a correctly built rung: read the five lines rather than the exit code. Check 5 needs a snapshot
README with a matching hash, so **snapshot the profile store first, then verify the snapshot**.

**Limits:** it reports what the file stores, not what the driver runs. The rung B README records
a runtime disagreement at 845–860 mV that no file decode can resolve. It measures nothing about
voltage on the rail.

Tests: `analysis/test_decode_profiles.py`, run by `python run_tests.py`. Written by GPT (Job 11);
reviewed 2026-09-22.
