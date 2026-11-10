"""Proposed static kit dependency gate. Never imports or executes copied tooling.

Checks a clean staging layout, rather than letting stale USB files hide omissions.
Requires Python 3.10+ and PowerShell 5.1 or 7 for parsing only. External Python
packages (torch) and executables/DLLs are outside this local-source check.
Unsupported dynamic local imports/dot sources fail closed, with a source location.
"""
import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


EXTERNAL_MODULES = {"torch"}
MANIFEST_ENTRY = re.compile(
    r'^\s*@\{\s*From\s*=\s*"([^"\n]+)";\s*To\s*=\s*"([^"\n]+)"\s*\}', re.M)

# Parse only: no dot-sourcing, evaluation, or invocation of copied scripts.
PS_PARSE = r'''
$ErrorActionPreference='Stop'
$paths=Get-Content -LiteralPath $env:HEADROOM_KIT_PARSE_INPUT -Raw | ConvertFrom-Json
$result=@()
foreach ($path in $paths.paths) {
    $errors=$null; $tokens=$null
    $tree=[System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)
    $joins=@(); $dots=@(); $assignments=@(); $modules=@()
    foreach ($node in $tree.FindAll({param($n) $n -is [System.Management.Automation.Language.CommandAst]},$true)) {
        $elements=@($node.CommandElements | ForEach-Object { $_.Extent.Text })
        $entry=@{line=$node.Extent.StartLineNumber; elements=$elements}
        if ($node.GetCommandName() -eq 'Join-Path') { $joins+=$entry }
        if ($node.InvocationOperator.ToString() -eq 'Dot') { $dots+=$entry }
        if ($node.GetCommandName() -eq 'Import-Module') { $modules+=$entry }
    }
    foreach ($node in $tree.FindAll({param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst]},$true)) {
        $assignments+=@{left=$node.Left.Extent.Text; right=$node.Right.Extent.Text}
    }
    $result+=@{path=$path; errors=@($errors | ForEach-Object {$_.Message}); joins=$joins; dots=$dots; assignments=$assignments; modules=$modules}
}
@{files=$result} | ConvertTo-Json -Depth 10 -Compress
'''


def relative_path(value):
    value = value.replace('\\', '/')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or ':' in value:
        raise ValueError(f"Unsafe manifest path: {value}")
    return path


def manifest(sync_path):
    text = sync_path.read_text(encoding='utf-8-sig')
    block = text.split('$files = @(', 1)[1].split('\n)', 1)[0]
    pairs = [(relative_path(a), relative_path(b)) for a, b in MANIFEST_ENTRY.findall(block)]
    # Fail closed if somebody changes the manifest's syntax instead of silently dropping entries.
    uncommented = '\n'.join(line for line in block.splitlines() if not line.lstrip().startswith('#'))
    if not pairs or len(pairs) != uncommented.count('@{'):
        raise ValueError('Unsupported Sync-Kit manifest syntax.')
    destinations = [b.as_posix().lower() for _, b in pairs]
    if len(set(destinations)) != len(destinations):
        raise ValueError('Duplicate kit destination (Windows paths are case insensitive).')
    return pairs


def stage(repo, pairs, kit):
    for source, destination in pairs:
        target = kit / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / source, target)


def path_value(node, values):
    """Tiny AST path evaluator, deliberately without eval/exec."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return values[node.id]
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == 'Path' and len(node.args) == 1:
            return Path(path_value(node.args[0], values))
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'resolve' and not node.args:
            return path_value(node.func.value, values).resolve()
    if isinstance(node, ast.Attribute) and node.attr in ('parent', 'parents'):
        return getattr(path_value(node.value, values), node.attr)
    if isinstance(node, ast.Subscript):
        return path_value(node.value, values)[path_value(node.slice, values)]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return path_value(node.left, values) / path_value(node.right, values)
    raise ValueError('Unsupported dynamic path expression.')


def python_dependencies(source, destination, repo):
    tree = ast.parse(destination.read_text(encoding='utf-8-sig'), filename=str(source))
    result, unresolved = [], []
    values = {'__file__': str(destination)}
    bindings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                bindings[name.asname or name.name.split('.')[0]] = name.name if name.asname else name.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            for name in node.names:
                bindings[name.asname or name.name] = (node.module or '') + '.' + name.name
    def callable_name(node):
        if isinstance(node, ast.Name):
            return bindings.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return callable_name(node.value) + '.' + node.attr
        return ast.unparse(node)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = path_value(node.value, values)
            except (KeyError, ValueError, TypeError, AttributeError, IndexError):
                pass
            bindings[node.targets[0].id] = callable_name(node.value)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module or '']
            for module in modules:
                base = destination.parent
                level = getattr(node, 'level', 0)
                for _ in range(max(0, level - 1)):
                    base = base.parent
                if not module and level:
                    modules_from = [n.name for n in node.names]
                else:
                    modules_from = [module]
                for name in modules_from:
                    top = name.split('.')[0]
                    if not level and top in sys.stdlib_module_names | EXTERNAL_MODULES:
                        continue
                    # Script siblings resolve before repository-root modules; no repo PYTHONPATH.
                    bases = [base] if level else [base, destination.parents[len(source.parts)-1]]
                    candidates = [b.joinpath(*name.split('.')).with_suffix('.py') for b in bases]
                    packages = [b.joinpath(*name.split('.')) / '__init__.py' for b in bases]
                    target = next((p for p in candidates + packages if p.is_file()), candidates[0])
                    result.append((node.lineno, target, f'Python import {name}'))
                    for length in range(1, len(name.split('.'))):
                        prefix = Path(*name.split('.')[:length])
                        if (repo / source.parent / prefix / '__init__.py').is_file():
                            result.append((node.lineno, base / prefix / '__init__.py', 'Python package initializer'))
                    # from package import submodule: check source-known submodules too,
                    # rather than mistaking them for symbols exported by __init__.py.
                    if isinstance(node, ast.ImportFrom) and module:
                        for imported in node.names:
                            known = repo / source.parent / Path(*name.split('.')) / (imported.name + '.py')
                            if known.is_file():
                                result.append((node.lineno, base / Path(*name.split('.')) / (imported.name + '.py'), 'Python package submodule'))
        if isinstance(node, ast.Call):
            call = callable_name(node.func)
            if call.endswith('spec_from_file_location'):
                try:
                    target = path_value(node.args[1], values)
                    result.append((node.lineno, Path(target), 'Python file import'))
                except (KeyError, ValueError, TypeError, AttributeError, IndexError):
                    unresolved.append((node.lineno, 'Unresolved Python file import'))
            elif call in ('__import__', 'importlib.import_module'):
                unresolved.append((node.lineno, 'Dynamic Python import requires explicit support'))
            elif call in ('exec', 'eval', 'runpy.run_path') or call.endswith('.SourceFileLoader'):
                unresolved.append((node.lineno, 'Dynamic Python loader requires explicit support'))
        if isinstance(node, ast.Call) and ast.unparse(node.func).startswith('sys.path.'):
            unresolved.append((node.lineno, 'sys.path mutation requires explicit support'))
    return result, unresolved


def ps_string(expression):
    if len(expression) >= 2 and expression[0] in "\"'" and expression[-1] == expression[0]:
        content = expression[1:-1]
        if expression[0] == '"' and ('$' in content or '`' in content):
            raise ValueError('Dynamic PowerShell string')
        return content.replace("''", "'")
    raise ValueError('Not a literal PowerShell string')


def ps_dependencies(parsed, destination, kit):
    refs, unresolved = [], []
    values = {'$PSScriptRoot': destination.parent, '$kit': kit, '$script:kit': kit}
    def join(elements):
        if len(elements) != 3 or elements[0].lower() != 'join-path':
            raise ValueError('Unsupported Join-Path')
        return values[elements[1]] / ps_string(elements[2]).replace('\\', '/')
    # Resolve variable-based dot sources as well as direct Join-Path forms.
    for assignment in parsed['assignments']:
        rhs = assignment['right'].strip().strip('()')
        match = re.fullmatch(r'(Join-Path)\s+(\$[\w:]+)\s+((?:"[^"\n]*"|\x27[^\x27\n]*\x27))', rhs, re.I)
        if match:
            try:
                values[assignment['left']] = join(list(match.groups()))
            except (KeyError, ValueError):
                pass
    for command in parsed['joins']:
        elements = command['elements']
        try:
            target = join(elements)
            if target.suffix.lower() in ('.ps1', '.py'):
                refs.append((command['line'], target, 'PowerShell local script path'))
        except (KeyError, ValueError):
            # Output paths and repo-only fallback branches are not import statements.
            # Dot sources below still fail if their target cannot be resolved.
            pass
    for command in parsed['dots']:
        expression = command['elements'][0]
        try:
            if expression in values:
                target = values[expression]
            elif expression.startswith('(Join-Path'):
                match = re.fullmatch(r'\((Join-Path)\s+(\$[\w:]+)\s+(.+)\)', expression, re.I)
                target = join(list(match.groups()))
            else:
                # Dot-sourcing a bare relative string uses the caller's working directory,
                # not PSScriptRoot. Do not certify a sibling file on that assumption.
                raise ValueError('Dot source is not anchored to the kit layout')
            refs.append((command['line'], target, 'PowerShell dot source'))
        except (KeyError, ValueError, AttributeError):
            unresolved.append((command['line'], f'Unresolved dot source {expression}'))
    for command in parsed['modules']:
        unresolved.append((command['line'], 'Import-Module requires explicit support'))
    return refs, unresolved


def check(repo, pairs, ps):
    errors, edges, code_files = [], [], 0
    with tempfile.TemporaryDirectory(prefix='headroom-kit-check-') as temporary:
        kit = Path(temporary) / 'kit'
        stage(repo, pairs, kit)
        sources = {kit / destination: source for source, destination in pairs}
        paths = [str(p) for p in sources if p.suffix.lower() == '.ps1']
        input_path = Path(temporary) / 'parse.json'
        input_path.write_text(json.dumps({'paths': paths}), encoding='utf-8')
        import os
        run = subprocess.run([ps, '-NoProfile', '-NonInteractive', '-Command', PS_PARSE],
                             capture_output=True, text=True, encoding='utf-8', timeout=60,
                             env={**os.environ, 'HEADROOM_KIT_PARSE_INPUT': str(input_path)})
        if run.returncode:
            raise ValueError('PowerShell parsing failed: ' + run.stderr)
        parsed = {Path(p['path']): p for p in json.loads(run.stdout)['files']}
        for destination, source in sources.items():
            if destination.suffix.lower() not in ('.py', '.ps1'):
                continue
            code_files += 1
            if destination.suffix.lower() == '.py':
                refs, unknown = python_dependencies(source, destination, repo)
            else:
                entry = parsed[destination]
                for error in entry['errors']:
                    errors.append(f'{source}: PowerShell syntax: {error}')
                refs, unknown = ps_dependencies(entry, destination, kit)
            for line, message in unknown:
                errors.append(f'{source}:{line}: {message}')
            for line, target, kind in refs:
                target = target.resolve()
                try:
                    name = target.relative_to(kit).as_posix()
                except ValueError:
                    errors.append(f'{source}:{line}: {kind} escapes kit')
                    continue
                edges.append((source.as_posix(), line, name, kind))
                if not target.is_file():
                    errors.append(f'{source}:{line}: {kind} missing in kit: {name}')
    return {'files': len(pairs), 'code_files': code_files, 'edges': sorted(set(edges)),
            'errors': sorted(set(errors))}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--sync-script', type=Path)
    parser.add_argument('--powershell', default=shutil.which('powershell.exe') or shutil.which('pwsh'))
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if not args.powershell:
        parser.error('PowerShell 5.1 or 7 is required for parsing; no unchecked success.')
    try:
        result = check(args.repo_root, manifest(args.sync_script or args.repo_root / 'tools/collection-kit/Sync-Kit.ps1'), args.powershell)
    except (OSError, ValueError, SyntaxError, subprocess.SubprocessError) as error:
        print(f'Kit dependency check failed: {error}')
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Checked {result['code_files']} Python/PowerShell files from {result['files']} copy entries; {len(result['edges'])} local references.")
        for error in result['errors']:
            print(error)
        print('Kit dependencies resolve.' if not result['errors'] else 'Kit dependencies do not resolve. Do not sync this manifest.')
        print('External packages, executables, DLLs, and hardware behavior were not verified.')
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
