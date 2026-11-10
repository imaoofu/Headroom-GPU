# Release selection

Use the classification in analysis/build_data_manifest.py. Select only category `dataset-grade`; retain every provenance flag. Include each session JSON, matching samples CSV, existing `_sweep_voltage.csv`, and ancestor README through data/frequency-sweeps/. Missing READMEs are reported, never invented.

SOURCE-CENSUS retains excluded and verification rows as an inventory, not measurements. data/MANIFEST describes the copied dataset-grade sweeps. The original census script's --check compares the complete private source tree to its paper and is not a release gate.

Include numeric curve JSON/README, collection and analysis source in the builder's CODE_ROOTS, and LICENSE files. Omit fixtures, caches, raw profile stores, transcripts, machine-info, third-party tables and unrelated source history. Raw HWiNFO is opt-in; the default release cannot independently regenerate joins from omitted logs. RELEASE-REPORT.json lists file-level omissions and ignored inputs.

## Section 20b and 22 supplements

The explicit tools/release/v120-cohorts.json policy selects separate pilot/day cohorts. manifest/SUPPLEMENTS.json and family/per-cohort manifests record exact evidence hashes, README excerpts and separate counts; these never change the legacy sweep census. Pilots are sizing data, never results; stopped at insufficient precision. Five repeatability days are COMPLETE, N=1 chip. Explicit exceptions ship both attempt ledgers, registered rules, eleven witnessed profile stores and the curve3 reference CFG; they need identifier/redistribution review. Process transcripts, controller logs, workload stdout/stderr and watcher signals stay out; parsed workload result records stay in windows.jsonl. All other filed cohort evidence, four probe JSONs and both probe READMEs are retained. Raw HWiNFO always stays out in this mode. Registered evidence is byte-preserved even with --strip-emoji: the filed runner TXT is hashed at launch. Its CRLF launch-hash reconstruction is the scorer's responsibility.
