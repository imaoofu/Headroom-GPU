"""Explicit, frozen section 20b/22 release evidence. Reads files only; never runs collection.

Kept separate from the legacy sweep census: pilots are sizing data, never results.
The JSON policy inventories every filed cohort path and must be reviewed when days are added.
"""
import collections
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath

POLICY = 'tools/release/v120-cohorts.json'
INDEX = 'manifest/SUPPLEMENTS.json'
REASON = 'v120-registered-evidence'


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=True) + '\n').encode('utf-8')


def safe(value):
    if not isinstance(value, str):
        raise ValueError('Supplement paths must be strings.')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or '\\' in value or ':' in value:
        raise ValueError('Unsafe supplement path: ' + str(value))
    if str(path) != value or value in ('', '.'):
        raise ValueError('Non-canonical supplement path: ' + value)
    return value


def policy(repo):
    plan = json.loads((repo / POLICY).read_text(encoding='utf-8'))
    if plan.get('schema_version') != 1 or not plan.get('cohorts'):
        raise ValueError('Unsupported or empty supplement policy.')
    return plan


def inventory(plan):
    """A fixed file allowlist; diagnostics are inventoried but deliberately not copied."""
    selected = {safe(p): reason for p, reason in plan['evidence'].items()}
    excluded, directories = {}, set()
    for cohort in plan['cohorts']:
        directory = safe(cohort['directory'])
        if directory in directories or not (directory == 'data/probes' or directory.startswith(('data/section20b/', 'data/repeatability/'))):
            raise ValueError('Repeated or out-of-scope supplement cohort: ' + directory)
        directories.add(directory)
        if cohort['kind'] not in ('pilot-sizing', 'repeatability-day', 'diagnostic-probes') or 'README.md' not in cohort['include']:
            raise ValueError('A cohort needs a declared kind and its filed README.')
        if (cohort['kind'] == 'diagnostic-probes') != (directory == 'data/probes'):
            raise ValueError('Diagnostic probes must use their own family directory.')
        if cohort['kind'] == 'diagnostic-probes':
            readmes = cohort.get('json_readmes', {})
            if set(readmes) != {n for n in cohort['include'] if n.endswith('.json')} or any(
                    safe(n) not in cohort['include'] or not n.startswith('README') or not n.endswith('.md')
                    for n in readmes.values()):
                raise ValueError('Each diagnostic probe JSON needs a filed README in the inventory.')
        for key, target in [('include', selected), ('exclude_process_diagnostics', excluded)]:
            for name in cohort[key]:
                relative = directory + '/' + safe(name)
                if relative in selected or relative in excluded:
                    raise ValueError('Repeated supplement path: ' + relative)
                target[relative] = cohort['label'] if key == 'include' else 'process diagnostics, not scorer inputs'
    return selected, excluded


def selection(repo, ignored, files_under):
    plan = policy(repo)
    selected, excluded = inventory(plan)
    present = {p.relative_to(repo).as_posix() for root in ('data/section20b', 'data/repeatability', 'data/probes')
               for p in files_under(repo / root) if p.relative_to(repo).as_posix() not in ignored}
    covered = {p for p in selected if p.startswith(('data/section20b/', 'data/repeatability/', 'data/probes/'))} | set(excluded)
    if present != covered:
        raise ValueError('Supplement inventory changed: ' + str(sorted(present ^ covered)) +
                         '. Review the frozen cohort policy before building.')
    for relative in selected:
        path = repo / relative
        if relative in ignored or not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(repo):
            raise ValueError('Missing, ignored or linked registered evidence: ' + relative)
    return selected


def census(repo, cohort):
    directory = repo / cohort['directory']
    names = cohort['include']
    sweeps = [n for n in names if n.endswith('_sweep.json')]
    samples = [n for n in names if n.endswith('_sweep.csv')]
    if {str(Path(n).with_suffix('.csv')) for n in sweeps} != set(samples):
        raise ValueError('Supplement sweep pairs differ: ' + cohort['directory'])
    points = 0
    for name in samples:
        with (directory / name).open(encoding='utf-8-sig', newline='') as handle:
            points += len(list(csv.DictReader(handle)))
    windows = directory / 'core/windows.jsonl'
    return {'files': len(names), 'sweeps': len(sweeps), 'target_rows': points,
            'voltage_extracts': sum(n.endswith('_sweep_voltage.csv') for n in names),
            'windows': sum(bool(line.strip()) for line in windows.read_text(encoding='utf-8-sig').splitlines())
                       if cohort['kind'] == 'pilot-sizing' else 0,
            'reader_csvs': sum(n.endswith('-reader.csv') for n in names),
            'probe_jsons': sum(n.endswith('.json') for n in names) if cohort['kind'] == 'diagnostic-probes' else 0}


def generated(repo):
    """Exact-byte manifests and short filed README excerpts, one per cohort and family."""
    plan = policy(repo)
    inventory(plan)
    outputs, groups = {}, collections.defaultdict(list)
    total = collections.Counter()
    for cohort in plan['cohorts']:
        root = cohort['directory']
        records = []
        for name in cohort['include']:
            relative = root + '/' + name
            data = (repo / relative).read_bytes()
            records.append({'path': relative, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        counts = census(repo, cohort)
        total.update(counts)
        # First two prose paragraphs, after the title. The complete filed README is also shipped.
        paragraphs = (repo / root / 'README.md').read_text(encoding='utf-8-sig').split('\n\n')
        excerpt = '\n\n'.join(paragraphs[1:3]).strip()
        manifest_root = root.removeprefix('data/')
        if cohort['kind'] == 'diagnostic-probes':
            manifest_root += '/diagnostic-probes'
        name = 'manifest/' + manifest_root + '/MANIFEST.json'
        record = {'schema_version': 1, 'directory': root, 'kind': cohort['kind'], 'label': cohort['label'],
                  'readme': root + '/README.md', 'readme_excerpt': excerpt, 'counts': counts, 'files': records}
        outputs[name] = encode(record)
        groups[root.split('/')[1]].append({'manifest': name, 'directory': root, 'kind': cohort['kind'],
                                          'label': cohort['label'], 'counts': counts, 'readme_excerpt': excerpt})
    for family, cohorts in sorted(groups.items()):
        outputs['manifest/' + family + '/MANIFEST.json'] = encode(cohorts)
    evidence = []
    for relative, reason in sorted(plan['evidence'].items()):
        data = (repo / relative).read_bytes()
        evidence.append({'path': relative, 'reason': reason, 'bytes': len(data),
                         'sha256': hashlib.sha256(data).hexdigest()})
    summary = {'schema_version': 1, 'inventory_source_commit': plan['inventory_source_commit'],
               'policy': POLICY, 'cohorts': len(plan['cohorts']),
               'pilot_sessions': len(groups['section20b']), 'repeatability_days': len(groups['repeatability']),
               'probe_folders': len(groups['probes']),
               'cohort_counts': dict(sorted(total.items())), 'shared_evidence_files': len(evidence),
               'shared_evidence': evidence,
               'interpretation': 'Pilots are sizing data, never results. Section 20b stopped at insufficient precision with no verdict. Section 22 is COMPLETE on five days; gemm and resnet50 WITHIN 3%, copy and reduce INCONCLUSIVE. '
                                 'N=1 chip. No raw HWiNFO logs; voltage joins cannot be independently rebuilt.'}
    outputs[INDEX] = encode(summary)
    outputs['manifest/section20b/README.md'] = (
        '# Section 20b release supplement\n\nSizing data, never results. N=1 chip. '
        'Four filed pilot sessions; stopped at registered insufficient precision, no S from 8 to 32 meets the 1 pp rule. No confirmation verdict. '
        'See MANIFEST.json for each pilot manifest and its filed README excerpt.\n').encode()
    outputs['manifest/repeatability/README.md'] = (
        '# Section 22 release supplement\n\nFive filed days on N=1 chip. The registered stage is COMPLETE; '
        'gemm and resnet50 are WITHIN 3%; copy and reduce are INCONCLUSIVE. '
        'See MANIFEST.json for day manifests and filed README excerpts.\n'
        '\nRun `python analysis/score_repeatability.py data/repeatability/day*` from the release root.\n').encode()
    outputs['manifest/probes/README.md'] = (
        '# Diagnostic probe supplement\n\nFour probe JSONs on N=1 chip, separate from sweep counts. '
        'data/probes/README.md documents launch-bound testing; README-saturation.md documents '
        'saturation, concurrency and unrolling, including invalid 2800 MHz memory-clock/peak figures. '
        'Existing caveats ship unchanged; packaging does not endorse every historical interpretation.\n').encode()
    return outputs, summary


def verify(output, expected, report):
    """Reconcile manifests, counts and exact evidence against the distributed payload."""
    selected, _ = inventory(policy(output))
    generated_files, summary = generated(output)
    for relative, data in generated_files.items():
        if (output / relative).read_bytes() != data:
            raise ValueError('Supplement manifest differs from its evidence: ' + relative)
    actual = {p.relative_to(output).as_posix() for family in ('section20b', 'repeatability', 'probes')
              for p in (output / 'data' / family).rglob('*') if p.is_file()}
    wanted = {p for p in selected if p.startswith(('data/section20b/', 'data/repeatability/', 'data/probes/'))}
    if actual != wanted:
        raise ValueError('Distributed supplement membership differs from the frozen inventory.')
    copied = {r['path'] for r in report['copied_files'] if r['reason'] == REASON}
    if copied != set(selected) or not set(selected) <= set(expected):
        raise ValueError('Registered evidence is missing from the copied-file report or checksums.')
    if report.get('supplements') != summary:
        raise ValueError('The report supplement census differs from the evidence.')
    return summary
