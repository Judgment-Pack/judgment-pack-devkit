"""Handwritten manifests exercise actual runners, never an installed jpdev copy."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNERS = (ROOT / 'templates/check.sh', ROOT / 'scripts/dev/check.sh')


class IncompleteChecklistTests(unittest.TestCase):
    def run_checks(self, runner, arguments=(), first_exit=0, prior_failures=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logs = root / 'logs'
            env = dict(os.environ, JPDEV_ROOT=str(root), JPDEV_LOGDIR=str(logs))
            for key in ('CI', 'JPDEV_WRAP', 'JPDEV_VENV', 'JPDEV_STEP_TIMEOUT'):
                env.pop(key, None)
            # Renaming a previously writable directory works even as root. It
            # retains the directory and any prior logs, without permission mocks.
            first = ('mv "$JPDEV_LOGDIR" "$JPDEV_LOGDIR.saved"; '
                     'printf blocked > "$JPDEV_LOGDIR"; '
                     'printf "retained\n"; exit %d' % first_exit)
            checks = ([{'name': 'prior', 'run': 'exit 8'}] if prior_failures else [])
            checks += [{'name': 'first', 'run': first, 'summary': '^retained$'},
                       {'name': 'second', 'run': 'printf ran > second-ran'},
                       {'name': 'unselected', 'run': 'printf ran > unselected-ran'}]
            manifest = root / 'dev.json'
            manifest.write_text(json.dumps({'version': 1, 'checks': checks}), encoding='utf-8')
            result = subprocess.run([str(runner), '--manifest', str(manifest), *arguments],
                                    env=env, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=15)
            return result, (root / 'second-ran').exists(), (root / 'unselected-ran').exists()

    def test_infrastructure_incomplete_is_nonzero(self):
        for runner in RUNNERS:
            for arguments in ((), ('--all',), ('--only', 'first,second')):
                with self.subTest(runner=runner, arguments=arguments):
                    result, second, unselected = self.run_checks(runner, arguments)
                    self.assertEqual(result.returncode, 1, 'incomplete selected checklist must be nonzero: ' + result.stdout)
                    self.assertRegex(result.stdout, r'PASS +first')
                    self.assertRegex(result.stdout, r'NOT RUN +second')
                    self.assertIn('1 passed, 0 failed, 0 skipped,', result.stdout)
                    self.assertIn('infrastructure failure: cannot persist the completed check log', result.stdout)
                    self.assertFalse(second, 'second sentinel ran after infrastructure failure')
                    self.assertFalse(unselected, 'later sentinel ran after infrastructure failure')
                    if arguments == ('--only', 'first,second'):
                        self.assertNotIn('NOT RUN  unselected', result.stdout)
                        self.assertIn('1 not run; infrastructure failure', result.stdout)
                    else:
                        self.assertIn('2 not run; infrastructure failure', result.stdout)

    def test_all_selected_completed_preserves_check_exit(self):
        for runner in RUNNERS:
            for first_exit, expected_status, expected_row in ((0, 0, 'PASS'), (7, 1, 'FAIL')):
                with self.subTest(runner=runner, first_exit=first_exit):
                    result, second, unselected = self.run_checks(runner, ('--only', 'first'), first_exit)
                    self.assertEqual(result.returncode, expected_status, result.stdout)
                    self.assertRegex(result.stdout, expected_row + r' +first')
                    self.assertIn('0 not run; infrastructure failure', result.stdout)
                    self.assertFalse(second)
                    self.assertFalse(unselected)

    def test_incomplete_preserves_failed_check_count(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                result, second, unselected = self.run_checks(runner, ('--all',), 7, 1)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertRegex(result.stdout, r'FAIL +prior +.*exit 8')
                self.assertRegex(result.stdout, r'FAIL +first +.*exit 7')
                self.assertIn('0 passed, 2 failed, 0 skipped, 2 not run', result.stdout)
                self.assertFalse(second)
                self.assertFalse(unselected)


if __name__ == '__main__':
    unittest.main()
