# Split-curve `membw`, clean protocol - 2026-08-24

Three sweeps. It withdraws a correction that was itself a correction, and the sequence is the
point of this directory.

## What was measured

`20260824-203810_5060ti-splitcurve-clean-membw-fine_sweep.csv` - the split-region curve of paper
5.7.6 on the 10-point 1400-2100 MHz grid, the same grid and timings as the clean memory-only
ceiling of 2026-08-23 and the rebuilt repaired curve of the same evening.

Configuration PROBED before starting, not assumed: at a locked 3090 MHz target the core read
2979.4 MHz mean (2977 min, 3000 max), which is the split signature - the original tune reads
~2947, the rebuilt repair ~2906, memory-only ~2593 and stock ~2610. Memory under load read
16301 MHz, confirming the +2500 offset against a stock 13801. Encoder and decoder both 0% at
preflight, recorded in the session JSON.

## Why it exists

Section 5.7.6 said twice that the split curve does something on `membw`, and both statements were
reached by comparing runs of unequal provenance.

  1. The first version compared a 2026-08-22 split-curve sweep against a 2026-08-20 memory-only
     sweep. Both predated the capture-software finding of 5.4.4 and neither verified its
     conditions. It concluded the split curve reached the ceiling, within 0.4% at seven of ten
     points. That conclusion was RIGHT, and it was right by accident: two similarly contaminated
     runs cancelled.

  2. The second version re-measured the ceiling clean and left the split curve where it was. Clean
     against contaminated, in the opposite direction, giving an apparent -3.18% deficit and a
     rewritten "three-way trade" built on it.

  3. This run cleans the other side. The split curve rose +3.19% over its predecessor and lands at
     -0.11% mean against the ceiling, 7 of 10 points within 0.4% - statistically the same place
     the repaired curve sits at -0.39%.

## Is the rise contamination, or a different curve?

Contamination, on three independent grounds:

  - MAGNITUDE. +3.19% against the +3.30% by which the memory-only ceiling moved when it was
    re-measured clean, and in the range 5.4.4 measured for capture software (+4.22% mid-band).
  - FREQUENCY SIGNATURE. The rise declines with frequency: +3.06% across 1402-1710 MHz against
    +2.24% across 1867-2100. That is the direction 5.4.4 measured. A voltage-curve difference
    would show as a step at the voltage boundary, not a smooth decline.
  - AN ISOLATED POINT. The largest single jump is +7.63% at 1792 MHz, flanked by +2.5% and +2.2%.
    No V/F curve produces a hole at one grid point. A transient contaminant does, and this is the
    same "roughly one run in three" outlier 5.4.4 attributes to capture software.

Controlled for: the memory offset was applied in all three runs (peak memory clock 16301-16312
MHz in each), so the difference is not a missing overclock.

## What is NOT established

The split-curve profile applied on 2026-08-24 is not proven bit-identical to the one applied on
2026-08-22 - the profile was not saved, and the probe reads clocks rather than the curve. The
clock signature matches and the three lines of evidence above all point at contamination, but a
small profile difference is not formally excluded.

n=1 per configuration on `membw`. The agreement between the ceiling, the repair and the split
curve is the only replication here.

## The lesson

**A comparison is only as clean as its dirtier half.** Correcting one side of a pair is not a
partial fix. It converts a symmetric error into an asymmetric one, and it looks like diligence
while doing it. The provenance audit had already flagged step 2 as a mixed comparison whose risk
ran against the finding, and recorded in `analysis/claims_consumer.py` that -3.18% was an upper
bound rather than a measurement. That note was written the same morning this run confirmed it.


---

## The replicate, and what it cost the first run's numbers

`20260824-210054_..._-r2_sweep.csv`, twenty minutes after the first, profile untouched, re-probed
before starting (2980.9 MHz at a locked 3090 target, memory 16301 MHz), encoder and decoder 0%.

It does not confirm r1. It corrects it.

| | vs the ceiling | within 0.4% |
|---|---|---|
| r1 alone | -0.11% | 7 of 10 |
| r2 alone | -0.73% | 2 of 10 |
| **mean of both** | **-0.42%** | 4 of 10 |

r2 contains a **-6.91%** single-point dip at 1867 MHz. The same point reads 395.1 GB/s in r1 and
367.1 GB/s in r2, so it is not a property of the configuration.

**Two consequences.**

1. **"Within 0.4% at N of ten points" is not a usable statistic here.** Two replicates of one
   configuration give seven and two. It reports which run happened to contain a dip. The paper now
   quotes band means only, and says so.

2. **The isolated-point argument for contamination is withdrawn.** This directory's original
   README argued that the 2026-08-22 run's +7.63% hole at 1792 MHz proved a transient contaminant,
   because no voltage curve can make a hole at one grid point. The premise is true; the conclusion
   does not follow. A verified-quiet run made one twenty minutes later.

The frequency-signature argument is withdrawn too, and for a worse reason: it was never applicable.
With both known dips excluded the rise is flat across the band (+2.89% below 1710 MHz against
+2.58% above 1942), and 5.4.4's low/high boundary is near 2010 MHz - nine of these ten points sit
below it, where 5.4.4 predicts a *uniform* offset. The earlier internal split had no basis in that
finding.

**What survives is magnitude alone:** a uniform +2.77% rise against the +3.30% the ceiling moved
and 5.4.4's +4.22% for this band. Contamination remains the leading explanation and is no longer
a demonstrated one. A slightly different applied profile is not excluded.

**The withdrawal of -3.18% does not depend on any of that.** It rests on two verified-quiet
sweeps of the current configuration reading -0.42% against a verified-quiet ceiling.

## Single-point dips, separately

Of the five verified-quiet `membw` sweeps on this grid, two carry a 6-7% single-point dip at a
different frequency each: the tuned sweep of 2026-08-22 at 1477 MHz (-5.93%), and r2 here at
1867 MHz (-6.91%). The other three have nothing worse than 1.0%.

This retires the standing explanation that the "wandering `membw` dip" was the capture software of
5.4.4. It survives the encoder guard. Cause unidentified, and it sets a floor on what a single
`membw` sweep can resolve on this card - larger than any configuration difference this section
reports.


---

## r3, and what it cost the dip framing

`20260824-211535_..._-r3_sweep.csv`, forty minutes after r1, profile untouched, re-probed
(2976.5 MHz at a locked 3090 target, card warmer at 60.5 C), encoder and decoder 0%.

| | vs the ceiling | within 0.4% |
|---|---|---|
| r1 | -0.11% | 7 of 10 |
| r2 | -0.73% | 2 of 10 |
| r3 | -0.57% | 6 of 10 |
| **mean of three** | **-0.47%** | - |

Against the repaired curve's -0.39%: they agree to **0.08 percentage points**. Conclusion
unchanged - both configurations sit at the bandwidth ceiling, and the repair is dominated.

**What r3 broke was this directory's own framing from an hour earlier.** The r2 write-up said
"two of five verified-quiet runs carry a 6-7% dip, the other three have nothing worse than 1.0%".
r3's worst point is **-2.17%**, which sits between those two groups. With six runs the worst-point
departures are -0.36%, -0.59%, -1.00%, -2.17%, -5.93%, -6.91%: a continuum. The "two of five" was
a 3% threshold laid across a continuous distribution measured on five samples, and it did not
survive the sixth.

**The useful statistic is the per-point run-to-run spread**, which three sweeps of one
configuration can actually measure: median **0.46%**, max **4.19%**, and eight of ten points
replicate to within 1%. The two that do not are 1477 and 1867 MHz. Restricted to the eight that
do, the split curve is **-0.14%** from the ceiling rather than -0.47%.

Both figures belong in the paper. The whole-band mean is dragged down by points that do not
replicate; the subset is chosen after seeing which points behaved. Neither alone is honest.
