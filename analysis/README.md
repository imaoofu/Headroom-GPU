# analysis/

Everything here reads committed measurements and computes from them. **Nothing in this folder touches
a GPU, locks a clock or changes a setting**; collection lives under `tools/`. N=1 chip per card model
throughout: repeated sweeps and workloads are repeated outcomes on one card, not more cards.

## What is here

| files | what they do |
|---|---|
| `score_*.py` | One scorer per registered study in `docs/REGISTERED-PREDICTIONS.md`, each written before its data except where the paper says otherwise (§3.4). For example `score_repeatability.py` (§22), `score_section20b.py` (§20b), `score_session16.py` (§16). Each prints its own verdict and its limits. |
| `audit_claims.py` and `claims_*.py` | The claims auditor. Each claim renders the exact string the paper must contain, computed from the CSVs at audit time, and must match once. `claims_consumer.py` holds this project's sweeps and every cross-card claim, `claims_crosschip.py` the 3070 Ti two-BIOS study, `claims_reference.py` the public V100 set, `claims_datasets.py` the published consumer sets, `claims_submission.py` the submission paper, and `claims_repo.py` the repository's own state. A claim declares `mixedProvenance` when it compares sweeps of different provenance tiers; that declaration is the "comparison record" the paper refers to. |
| `build_data_manifest.py` | The census: classifies every sweep under `data/` by a stated rule and writes `data/MANIFEST.json`. `--check` fails if the totals stop reconciling. |
| `check_data_hashes.py` | Checks every committed measurement file against `docs/data-measurement-hashes.json`. |
| `verify_citations.py` | Checks that every cited arXiv id and DOI is registered or listed as a lead. |
| `analyze_*.py`, `compare_*.py`, `characterize.py`, `paper_uncertainty.py`, `membw_chord_history.py` | Descriptive analyses behind particular sections of the papers. |
| `import_bench_session.py` | Imports a shop-card session collected by the bench app. |
| `wang_tpds_figure4.py` | Re-runs a published model's figure from its released artifact (paper §2). |
| `models/` | Everything that predicts rather than measures, with its own README. |
| `figures/` | The paper's figures, with their scripts and caption facts, with its own README. |
| `test_*.py` | Tests for the files above. Run every suite with `python run_tests.py` from the repository root. |

## Running it

From the repository root:

```
python run_tests.py
python analysis/audit_claims.py
python analysis/build_data_manifest.py --check
python analysis/check_data_hashes.py --check
```

Some claims and tests need the fetched public datasets (`scripts/Get-Dataset.ps1`), and a few tests need
Windows PowerShell; both say so when skipped. Read counts off these commands, not off any document.
