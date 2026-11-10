# Does the load floor survive an NVML clock offset? (worklist 4c) — 2026-09-22

**RTX 5060 Ti, driver 616.92, one session, operator present.** This is the **first NVML clock-offset
write ever exercised on this card.** Registered before collection in
`docs/REGISTERED-PREDICTIONS.md` §6 (commit `d0b9724`). Runner:
`tools/hwinfo-logging/experiments/Run-OffsetPrecondition.ps1`. Tool:
`tools/nvml-offset/Set-NvmlClockOffset.ps1`.

**Design.** Stock Profile 3, verified by memory clock under load (13801 MHz). `gemm`, ascending,
**1000–1700 MHz in 15 points (~50 MHz apart)**, HWiNFO at 0.50 s, voltage time-joined.

| run | NVML P0 graphics offset | verified |
|---|---|---|
| **A1** | 0 | read-back 0 |
| **B** | **−300 MHz** | read-back −300 |
| **A2** | 0, after reset | read-back 0; reset in a `finally` block |

## The registered prediction holds: the offset SHIFTS the V/F curve

| target | 1005–1252 | 1297 | 1350 | 1402 | 1447 | 1500 | 1545 | 1597 | 1642 | 1695 |
|---|---|---|---|---|---|---|---|---|---|---|
| V, A1 | 0.720 | 0.720 | 0.720 | 0.720 | 0.720 | 0.720 | 0.720 | 0.730 | 0.740 | 0.755 |
| **V, B (−300)** | 0.720 | **0.730** | **0.740** | **0.755** | **0.765** | **0.785** | **0.795** | **0.810** | **0.820** | **0.835** |
| V, A2 | 0.720 | 0.720 | 0.720 | 0.720 | 0.720 | 0.720 | 0.720 | 0.730 | 0.740 | 0.755 |

- **Two regions survive.** B holds 0.720 V through **1245 MHz achieved**, then rises from **1290**. So
  its floor end is **1245–1290**, against a registered ~1270 (the A floor end of 1567–1575, minus
  300). **That is within the registered one grid step.**
- **B's voltage at f equals stock voltage at f+300**:
  - **9 of 9 six-step pairs report the IDENTICAL VID code** (B at point *i* against A1 at *i+6*;
    target gaps 292–300 MHz). **Use this form.**
  - ~~within 2 mV / within 3 mV~~ *Narrowed the same evening:* those figures interpolate between
    5 mV codes, so they measure the interpolation, not sub-code agreement. The reported voltage is a
    VID lookup, not rail voltage, so this shows the **lookup** shifted, not the delivered voltage.
- **So Guerreiro et al.'s offset behaviour, voltage constant across all frequencies, does NOT
  occur here.** Their path was `nvidia-settings` on Maxwell/Pascal/Kepler. **This one run does not
  contradict their result on their hardware.** ~~It says `nvmlDeviceSetClockOffsets` on Blackwell
  behaves differently.~~ *Narrowed 2026-09-22:* their control method and GPU generation both differ
  from this run, **together**, so this does not show that the API caused the difference.

**Registered as open, and now answered: locked clocks still achieve their target.** Every B point
reads `held`, and B's achieved clocks match A1's to within 7.3 MHz, one step of the card's
~7.5 MHz clock table. The offset moves the voltage
for a given clock. It does not move the lock.

## What the shifted curve does to efficiency

| | B vs A1, same target |
|---|---|
| throughput | **within 1.05%** at every point, close to the A2-vs-A1 spread (0.78%). The clock is the same, so the work rate is too |
| efficiency, ≤1200 MHz | −0.7% to +1.4%: unchanged inside the shifted floor |
| efficiency, ≥1252 MHz | **−5.5% to −17.2%**: the same clock now costs more voltage |

**The efficiency cliff moved down with the floor.** Each run's efficiency argmax sits inside its
own floor: A1 at **1440**, A2 at **1537**, B at **1192 MHz achieved**. **But those argmaxes are
near-ties**, with margins to the runner-up of **1.09%, 0.45% and 0.12%**. That is the same fragility
`../5060ti-stock-repro-20260922/` measured. **Quote the shifted floor, not the argmax.**

## Crossbar clock was associated with the shifted curve (an observation)

At the same locked core clock, B's crossbar clock is **higher at 15 of 15 points**, by 30–338 MHz:
1785 against 1447 MHz at 1537, for example. Against A1 six grid steps higher, **8 of 9 pairs agree
within the A1-vs-A2 control's 15 MHz spread**, and the 1057 MHz point misses by 30. ~~**So XBAR tracked
where on the V/F curve the card sat, not the core clock.**~~ *Too categorical, narrowed the same
evening by an outside audit:* six B points have no shifted A1 partner, one pair misses, and nothing
here intervenes on XBAR. **Say "associated with the shifted curve configuration over the overlap".** That is consistent with CLAUDE.md's statement that XBAR
tracks *the curve configuration*. **This is one run, and it was not what this experiment was
designed to test. It is an observation, not a result.**

## Validity

- **A2 matches A1 at every point**: voltage to 0 mV at all 15, throughput within ±0.8%. There was no
  drift, and **the reset took**.
- Memory 13801 MHz, 180 W power limit, and every lock held in all three runs.
- Each run had its own HWiNFO log. The raw logs are in the gitignored `data/HWiNFO-Data/`. Every point
  has 25–44 samples.

## What this does NOT establish

- **One chip, one run per condition, one workload** (`gemm`), and **one offset (−300)**. Linearity in
  the offset is untested.
- **The 4d validation pair as designed is superseded rather than run.** Its criterion, *"power at
  a locked f with a −300 offset should match power at f+300 without one"*, is **not a valid
  prediction** of a shifted lookup, so retire it (~~"cannot hold as worded"~~ was too categorical).
  Both sit at the same reported voltage, but B runs ~300 MHz slower, and **B draws 8.9–11.3 W less at
  all nine pairs**, e.g. 49.98 W at 1004 MHz against 60.34 W at 1295. ~~The question 4d existed to
  answer is answered more directly by the voltage pairing above.~~ **It is not:** VID pairing shows the
  lookup shifted, not that the machine state matches. That needs a matched-clock comparison of an
  offset against a separately configured curve. Not run.
- Whether the offset survives a driver reset, or an Afterburner profile applied **after** it, is still
  unverified. The runner applied the profile first and reset the offset at the end.

## Prior art — the mechanism is known; searched the same evening

Search log: `docs/gpt-findings/2026-09-22-nvml-offset-prior-art-search.md`. **A global offset shifting
the whole V/F curve is established practice**, from Afterburner users and NVIDIA's NVML naming.
**170tune** (`cachenetics/170tune`, 2026-08-30, read here) shows it on a CMP 170HX by pinning the
clock and watching power fall, and describes a floor: *"below about 1350 the rail bottoms out… extra
offset is inert"*. **What this directory adds is narrower:**
- measured voltage readback, where 170tune had none;
- the f ↔ f+300 pairing (identical VID codes, 9 of 9 six-step pairs);
- the floor end located under an offset;
- on Blackwell.

## Why it matters for what comes next

**For this project, an NVML offset moves the load floor programmatically**: no Afterburner, no
hand-built curve, no slot juggling. *A capability, not a discovery; see the prior-art section above.* The floor-ladder design (`REGISTERED-PREDICTIONS.md` §1) currently needs curves built
by hand, one per slot. **An offset ladder could run unattended.** It would not be the same
manipulation: a global offset shifts the **whole** curve, while the registered rungs raise only the
floor region. So it would complement the rungs, not replace them.
