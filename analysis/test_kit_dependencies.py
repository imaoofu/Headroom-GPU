"""Review-only fixtures for the proposed kit dependency gate; no GPU tooling is executed."""
import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Works beside the review proposal or after applying its production paths.
ROOT = Path(os.environ.get('HEADROOM_JOB88_REPO', Path.cwd())).resolve()
CHECKER = HERE / 'check_kit_dependencies.py'
if not CHECKER.is_file():
    ROOT = HERE.parent
    CHECKER = ROOT / 'tools/collection-kit/check_kit_dependencies.py'
SPEC = importlib.util.spec_from_file_location('kit_dependencies', CHECKER)
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
PS = shutil.which('powershell.exe') or shutil.which('pwsh')


@unittest.skipUnless(PS, 'PowerShell unavailable: kit gate was not verified')
class KitDependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)

    def write(self, path, text):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding='utf-8-sig')
        return Path(path)

    def check(self, pairs):
        return GATE.check(self.repo, pairs, PS)['errors']

    def test_sibling_import_missing_even_if_source_exists(self):
        main = self.write('tools/sweep/main.py', 'from helper import run\n')
        helper = self.write('tools/sweep/helper.py', 'def run(): pass\n')
        self.assertTrue(self.check([(main, main)]))
        self.assertEqual(self.check([(main, main), (helper, helper)]), [])

    def test_relocated_python_resolves_at_destination(self):
        main = self.write('tools/kit/main.py', 'import helper\n')
        helper = self.write('tools/kit/helper.py', '')
        self.assertTrue(self.check([(main, Path('main.py')), (helper, helper)]))
        self.assertEqual(self.check([(main, Path('main.py')), (helper, Path('helper.py'))]), [])

    def test_variable_dot_source_and_guard_cannot_hide_omission(self):
        main = self.write('tools/logger/main.ps1', '$helper=Join-Path $PSScriptRoot "Helper.ps1"\nif(Test-Path $helper){. $helper}\n')
        helper = self.write('tools/logger/Helper.ps1', '# helper\n')
        errors = self.check([(main, main)])
        self.assertTrue(any('dot source missing' in e for e in errors))
        self.assertEqual(self.check([(main, main), (helper, helper)]), [])

    def test_direct_dot_source_and_parent_path(self):
        main = self.write('tools/sweep/main.ps1', '. (Join-Path $PSScriptRoot "..\\Helper.ps1")\n')
        helper = self.write('tools/Helper.ps1', '')
        self.assertTrue(self.check([(main, main)]))
        self.assertEqual(self.check([(main, main), (helper, helper)]), [])

    def test_root_collect_layout_checks_child_paths(self):
        main = self.write('tools/kit/Collect.ps1', '$kit=$PSScriptRoot\n$child=Join-Path $kit "tools\\sweep\\main.py"\n')
        child = self.write('tools/sweep/main.py', 'import sys\n')
        self.assertEqual(self.check([(main, Path('Collect.ps1')), (child, child)]), [])

    def test_dynamic_file_import_resolves_from_kit(self):
        main = self.write('tools/app/main.py', 'import importlib.util\nfrom pathlib import Path\nTARGET=Path(__file__).resolve().parents[1]/"screen"/"main.py"\nSPEC=importlib.util.spec_from_file_location("screen", TARGET)\n')
        helper = self.write('tools/screen/main.py', '')
        self.assertTrue(self.check([(main, main)]))
        self.assertEqual(self.check([(main, main), (helper, helper)]), [])

    def test_unknown_dynamic_import_and_dot_source_fail_closed(self):
        py = self.write('dynamic.py', 'import importlib.util\nimportlib.util.spec_from_file_location("x", make_path())\n')
        ps = self.write('dynamic.ps1', '. $unresolved\n')
        errors = self.check([(py, py), (ps, ps)])
        self.assertTrue(any('Unresolved Python file import' in e for e in errors))
        self.assertTrue(any('Unresolved dot source' in e for e in errors))

    def test_aliased_file_import_and_dynamic_import(self):
        py = self.write('main.py', 'from importlib.util import spec_from_file_location as load\nfrom pathlib import Path\np=Path(__file__).resolve().parent/"missing.py"\nload("x", p)\n')
        self.assertTrue(any('missing.py' in e for e in self.check([(py, py)])))
        self.write('main.py', 'import importlib as loader\nload=loader.import_module\nload("missing")\n')
        self.assertTrue(any('Dynamic Python import' in e for e in self.check([(py, py)])))

    def test_literal_dot_source_must_not_assume_script_directory(self):
        ps = self.write('tools/main.ps1', '. "Helper.ps1"\n')
        helper = self.write('tools/Helper.ps1', '')
        self.assertTrue(any('Unresolved dot source' in e for e in self.check([(ps, ps), (helper, helper)])))

    def test_package_submodule_not_just_initializer(self):
        py = self.write('main.py', 'from package import helper\n')
        init = self.write('package/__init__.py', '')
        helper = self.write('package/helper.py', '')
        self.assertTrue(any('package/helper.py' in e for e in self.check([(py, py), (init, init)])))
        self.assertEqual(self.check([(py, py), (init, init), (helper, helper)]), [])
        self.write('main.py', 'import package.helper\n')
        self.assertTrue(any('package/__init__.py' in e for e in self.check([(py, py), (helper, helper)])))

    def test_stdlib_and_declared_external_packages_are_not_local(self):
        py = self.write('main.py', 'import sys, ctypes, torch\nfrom pathlib import Path\n')
        self.assertEqual(self.check([(py, py)]), [])

    def test_invalid_powershell_fails_without_executing(self):
        ps = self.write('bad.ps1', 'if ( {\n')
        self.assertTrue(any('syntax' in e for e in self.check([(ps, ps)])))

    def test_manifest_rejects_duplicate_and_unrecognized_entries(self):
        manifest = self.write('Sync.ps1', '$files = @(\n @{ From = "a.py"; To = "A.py" },\n @{ From = "b.py"; To = "a.py" }\n)\n')
        with self.assertRaises(ValueError): GATE.manifest(self.repo / manifest)
        self.write('Sync.ps1', '$files = @(\n @{ From = $dynamic; To = "a.py" }\n)\n')
        with self.assertRaises(ValueError): GATE.manifest(self.repo / manifest)

    def test_current_manifest_and_each_real_import_omission(self):
        pairs = GATE.manifest(ROOT / 'tools/collection-kit/Sync-Kit.ps1')
        current = GATE.check(ROOT, pairs, PS)
        throttle = Path('tools/stability-logger/ThrottleReasons.ps1')
        if not any(b == throttle for _, b in pairs):
            self.assertTrue(any('ThrottleReasons.ps1' in e for e in current['errors']))
            complete = pairs + [(throttle, throttle)]
        else:
            self.assertEqual(current['errors'], [])
            complete = pairs
        self.assertEqual(GATE.check(ROOT, complete, PS)['errors'], [])
        for dependency in ('tools/stability-logger/ThrottleReasons.ps1',
                           'tools/frequency-sweep/app_workloads.py',
                           'tools/hwinfo-logging/check_desktop_load.py',
                           'tools/bench-app/catalog/build_sessiond.py',
                           'tools/bench-app/catalog/build_sessione.py'):
            with self.subTest(dependency=dependency):
                removed = [(a, b) for a, b in complete if b.as_posix() != dependency]
                errors = GATE.check(ROOT, removed, PS)['errors']
                self.assertTrue(any(dependency in e for e in errors), errors)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(KitDependencyTests)
    names = [test.id() for test in suite]  # the runner empties the suite as it goes
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    for test, reason in result.skipped: print('[SKIP] ' + test.id() + ': ' + reason)
    bad = {test.id() for test, _ in result.failures + result.errors + result.skipped}
    for name in names:
        if name not in bad:
            print('[PASS] ' + name.rsplit('.', 1)[-1].replace('_', ' '))
    raise SystemExit(0 if result.wasSuccessful() else 1)
