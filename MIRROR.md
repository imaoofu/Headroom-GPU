# About this repository

This repository mirrors **Headroom dataset v1.2.0**, published on Zenodo:
[10.5281/zenodo.23547564](https://doi.org/10.5281/zenodo.23547564) (all versions:
[10.5281/zenodo.23251532](https://doi.org/10.5281/zenodo.23251532)). The Zenodo record is the
version of record; cite it, not this repository. See `README.md` and `DATASHEET.md`.

**Every file here is byte-identical to the Zenodo release**, except two that the release does not
contain: this note and `.gitattributes` (`* -text`, so Git never rewrites line endings and the
checksums hold on every platform). To check, from this folder:

```
sha256sum -c --ignore-missing SHA256SUMS
```

Three files of the Zenodo release are left out, because they only check documents of the
author's private development repository that are not distributed, and they fail without them:

- `analysis/verify_citations.py` and `analysis/test_verify_citations.py`, a citation checker for
  the project's working documents;
- `analysis/test_repo_conventions.py`, a check on the private repository's own notes.

`SHA256SUMS` still lists them, which is why the command above uses `--ignore-missing`. They are in
the Zenodo zip for anyone who wants them. Later versions are added here as new commits, each
tagged with its Zenodo version.
