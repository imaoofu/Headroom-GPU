# tools/xbar — the crossbar-clock intervention (REGISTERED-PREDICTIONS §14)

**These scripts CHANGE GPU STATE** through mVolt+ (`b00nz/mVolt`), a third-party tool that
writes undocumented NVIDIA interfaces. They set the **XBAR clock offset only**: no voltage, ratio,
SYS, video, core, memory or power control. Every exit path sets the offset back to 0 and re-applies
Afterburner Profile 3 (stock), then reads the state back and says if it did not take. A driver reset
clears settings silently, so any display-driver event voids what follows it.

**RTX 5060 Ti only**, the card of §12 and §14: Profile 3 is stock (180 W), and Profile 1 is curve 3
(P4's curve, memory +0, 200 W), checked against the committed snapshot hash `8EC197F30E21D116`. The
gate hashes only the store's `[Startup]` and `[Profile1]`–`[Profile5]` sections, because Afterburner
appends `[Defaults]` and `[Settings]` on its own (it did so during the 2026-10-01 dry run).

| file | what it does |
|---|---|
| `Invoke-XbarCalibration.ps1` | §14 step 0, clocks only. `-ReadOnly` saves `--version`, `--list-gpus` and `--status` and writes nothing. Otherwise it locks the core with `nvidia-smi -lgc`, steps through XBAR offsets under a `layernorm` load and records HWiNFO's reported and measured crossbar clocks, VID and memory clock. **It never reads throughput**, because §14 forbids seeing an outcome before collection |
| `calibration_report.py` | Joins one calibration run's HWiNFO log to its windows and scores gates C0a (reported and measured agree at offset 0), C0b (a negative offset moves the measured clock by at least 50 MHz, then returns) and C0d (VID within one 5 mV code) |
| `Invoke-Xbar14Session.ps1` | The registered session, unattended, in §14's order. `-DryRun` forces every offset to 0 and prefixes labels `xbar14dry-`, so the whole pipeline runs with no treatment outcome. `-Quick` (dry runs only) sweeps the first target of each bracket. `-ManageChatGpt` closes the ChatGPT desktop app (package `OpenAI.Codex`: `ChatGPT.exe` plus `codex.exe`) before the first sweep and relaunches it through Explorer, unelevated, after the card is back on stock, on every exit path. Closing it kills any GPT job running inside it |

| `hwinfo_memory_in_window.py` | After collection: the NVIDIA memory clock inside each benchmark window, from HWiNFO and from nvidia-smi, written beside the sweeps as `hwinfo-memory-in-window.csv`. `analysis/score_xbar14.py` reads it for the memory condition |

Scoring: `analysis/score_xbar14.py <dir> --memory-rule literal|section13` (see §14's result for why
both are printed).

## Order of use

1. **Read-only first.** `.\Invoke-XbarCalibration.ps1 -MvoltPath <path>\mVolt+.exe -ReadOnly`, then
   read the saved JSON: the adapter id, and whether `--status` reports the XBAR offset and a SYS clock.
2. **C0a and C0b**, on stock at 1560 MHz: `-Profile 3 -TargetMhz 1560 -OffsetsMhz "0,-100,0"`. If
   the measured crossbar does not move under the lock, stop: §14 is not run as registered.
3. **C0c, choose each arm's offset** from clocks only: S at 1560/1710/1867 into 1312–1372 MHz; C at
   1402 into 1455–1515; N on curve 3 (`-Profile 1`) at 1710 into 1605–1665 and at 1867 into
   1770–1830. Positive offsets need `-AllowPositive` and step by at most +50 MHz.
4. **Write the calibration file** (`gpuId`, `mvoltVersion`, `offsets.S1560 … N1867`) and commit it
   with the calibration logs before collection.
5. **Dry run:** `.\Invoke-Xbar14Session.ps1 -MvoltPath … -DryRun [-Quick]`.
6. **The session:** `.\Invoke-Xbar14Session.ps1 -MvoltPath … -CalibrationPath …`. Before leaving the
   machine: HWiNFO open with its Sensors window, Codex, ChatGPT and llama-server closed, and no other
   mVolt+ window.

Afterwards: join every sweep with `tools/frequency-sweep/join_hwinfo_voltage.py`, which outputs the
measured crossbar column as `crossbarMeasured`, and score against §14. When the work is done, reset
every mVolt+ control, verify stock as in the registry's safety envelope, and uninstall mVolt+.

**Limits.** One card. The offset is a request through an undocumented tool; only the measured clock
is evidence it happened. HWiNFO shows no SYS clock on this card. mVolt+ shows no VRAM bandwidth,
and its bandwidth tile is PCIe traffic.
