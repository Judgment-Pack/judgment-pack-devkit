"""Handwritten fixture repositories exercise `jpdev check --changed` through bin/jpdev, and the
same fixtures `scripts/dev/check.sh --changed` through the vendored runner and selection code."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
JPDEV = ROOT / 'bin' / 'jpdev'
FIXTURE = ROOT / 'tests' / 'fixture'
SPEC = importlib.util.spec_from_file_location('changed_checks', ROOT / 'lib' / 'changed_checks.py')
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
ALL = {'docs-lint', 'go-vet', 'go-test', 'python-tests', 'whitespace'}
# What jpdev check exports to its steps, and settings a caller's machine may hold.
DROPPED = ('CI', 'JPDEV_ROOT', 'JPDEV_WRAP', 'JPDEV_NODE_BIN', 'JPDEV_GO_BIN', 'JPDEV_LOGDIR',
           'JPDEV_STEP_TIMEOUT', 'JPDEV_VENV', 'JPDEV_NAME_PATTERNS', 'JPDEV_GO_SDK_DIR', 'JPDEV_NVM_DIR')


class GlobTests(unittest.TestCase):
    def matches(self, glob, path):
        return bool(c.glob_regex(glob).fullmatch(path))

    def test_star_stays_within_one_segment(self):
        self.assertTrue(self.matches('*.md', 'README.md'))
        self.assertFalse(self.matches('*.md', 'docs/guide.md'))
        self.assertTrue(self.matches('docs/*.md', 'docs/guide.md'))
        self.assertFalse(self.matches('docs/*.md', 'docs/api/guide.md'))

    def test_question_mark_is_one_character_of_a_segment(self):
        self.assertTrue(self.matches('go.su?', 'go.sum'))
        self.assertFalse(self.matches('go.su?', 'go.su'))
        self.assertFalse(self.matches('a?b', 'a/b'))

    def test_double_star_segment_spans_directories(self):
        self.assertTrue(self.matches('**/*.go', 'main.go'))
        self.assertTrue(self.matches('**/*.go', 'cmd/tool/main.go'))
        self.assertTrue(self.matches('docs/**', 'docs/a/b.md'))
        self.assertFalse(self.matches('docs/**', 'docsx/a.md'))
        self.assertTrue(self.matches('tests/**/*.py', 'tests/unit_test.py'))
        self.assertTrue(self.matches('tests/**/*.py', 'tests/a/b/unit_test.py'))
        self.assertFalse(self.matches('tests/**/*.py', 'lib/tests/unit_test.py'))
        self.assertTrue(self.matches('**', '.github/workflows/ci.yml'))

    def test_other_characters_are_literal(self):
        self.assertTrue(self.matches('a+b.(c)', 'a+b.(c)'))
        self.assertFalse(self.matches('a.md', 'aXmd'))
        self.assertFalse(self.matches('docs/*.md', 'docs/guide.md.orig'))

    def test_refused_globs_are_named(self):
        cases = {
            '': 'must be a non-empty string',
            '/docs/**': 'must be relative to the repository root',
            '../docs/**': 'has an empty, . or .. segment',
            './docs/x.md': 'has an empty, . or .. segment',
            'docs//x.md': 'has an empty, . or .. segment',
            'docs/': 'has an empty, . or .. segment',
            'docs/**.md': '** must be a whole segment',
            'a***': '** must be a whole segment',
            '{a,b}.md': 'is not supported',
            '[ab].md': 'is not supported',
            'docs\\x.md': 'is not supported',
        }
        for glob, message in cases.items():
            with self.subTest(glob=glob), self.assertRaisesRegex(c.Refused, re.escape(message)):
                c.glob_regex(glob)


def git(cwd, *args):
    return subprocess.run(['git', '-c', 'user.name=test', '-c', 'user.email=test@example.com',
                           '-c', 'commit.gpgsign=false'] + list(args), cwd=str(cwd), check=True,
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class ChangedCheckTests(unittest.TestCase):
    """A clone of a fixture origin, on a topic branch, with the mapping of tests/fixture."""

    LABEL = 'jpdev check --changed'

    def seed(self, seed):
        """Add files to the fixture origin before its first commit."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='changed-checks-')
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.env = {k: v for k, v in os.environ.items() if k not in DROPPED and not k.startswith('GIT_')}
        for name in ('home', 'config', 'scratch'):
            (self.work / name).mkdir()
        self.env.update(HOME=str(self.work / 'home'), XDG_CONFIG_HOME=str(self.work / 'config'),
                        JPDEV_SCRATCH=str(self.work / 'scratch'), JPDEV_LOCK=str(self.work / 'scratch' / 'lock'))
        seed = self.work / 'seed'
        git(self.work, 'init', '-q', '-b', 'main', str(seed))
        shutil.copy(str(FIXTURE / 'changed-dev.json'), str(seed / 'dev.json'))
        shutil.copy(str(FIXTURE / 'changed-jpdev.json'), str(seed / 'jpdev.json'))
        files = {'README.md': '# fixture\n', 'docs/guide.md': 'guide\n', 'go.mod': 'module example.com/fixture\n',
                 'cmd/tool/main.go': 'package main\n', 'tests/unit_test.py': 'pass\n', 'scripts/tool.sh': 'true\n'}
        for name, text in files.items():
            self.write(name, text, seed)
        self.seed(seed)
        git(seed, 'add', '-A')
        git(seed, 'commit', '-q', '-m', 'seed')
        git(self.work, 'init', '-q', '--bare', '-b', 'main', str(self.work / 'origin.git'))
        git(seed, 'push', '-q', str(self.work / 'origin.git'), 'main')
        self.clone = self.work / 'clone'
        git(self.work, 'clone', '-q', str(self.work / 'origin.git'), str(self.clone))
        git(self.clone, 'switch', '-q', '-c', 'topic')

    def write(self, name, text, root=None):
        path = (root or self.clone) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit_base(self, message):
        """Commit everything on the topic branch and return the commit, a BASE for --changed."""
        git(self.clone, 'add', '-A')
        git(self.clone, 'commit', '-q', '-m', message)
        return git(self.clone, 'rev-parse', 'HEAD').stdout.decode().strip()

    def mapping(self, change):
        value = json.loads((FIXTURE / 'changed-jpdev.json').read_text())
        change(value)
        self.write('jpdev.json', json.dumps(value))

    def check(self, *args):
        result = subprocess.run([str(JPDEV), 'check'] + list(args), cwd=str(self.clone), env=self.env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, timeout=120)
        return result.returncode, result.stdout, result.stderr

    def ran(self, out):
        """The steps of the check summary block, by name."""
        return {m.group(2) for m in re.finditer(r'^(PASS|FAIL|SKIP|NOT RUN) +(\S+)', out, re.M)}

    def test_docs_only_change_runs_the_docs_steps_only(self):
        self.write('docs/guide.md', 'guide, edited\n')
        self.write('README.md', '# fixture, edited\n')
        git(self.clone, 'add', 'README.md')
        status, out, err = self.check('--changed')
        self.assertEqual(status, 0, out + err)
        self.assertEqual(self.ran(out), {'docs-lint', 'whitespace'}, out)
        self.assertIn('== %s: 2 changed paths since origin/main (merge base ' % self.LABEL, out)
        self.assertRegex(out, r'(?m)^selected +docs-lint +docs/\*\*, \*\.md$')
        self.assertRegex(out, r'(?m)^not selected +go-test +no changed path maps to it$')
        self.assertIn('== 2 of 5 checks selected ==', out)
        self.assertIn('== 2 passed, 0 failed, 0 skipped, 0 not run ==', out)
        self.assertLess(out.index('== ' + self.LABEL), out.index('== check summary'))

    def test_mapped_go_path_runs_the_go_steps(self):
        self.write('cmd/tool/main.go', 'package main\n\nfunc main() {}\n')
        git(self.clone, 'commit', '-q', '-am', 'go change')
        status, out, err = self.check('--changed')
        self.assertEqual(status, 0, out + err)
        self.assertEqual(self.ran(out), {'go-vet', 'go-test', 'whitespace'}, out)
        self.assertRegex(out, r'(?m)^selected +go-vet +\*\*/\*\.go$')
        self.assertRegex(out, r'(?m)^not selected +docs-lint +no changed path maps to it$')

    def test_unmapped_path_runs_the_whole_list(self):
        self.write('docs/guide.md', 'guide, edited\n')
        self.write('scripts/new.sh', 'true\n')
        status, out, err = self.check('--changed')
        self.assertEqual(status, 0, out + err)
        self.assertIn('unmapped path scripts/new.sh: whole list', out)
        self.assertIn('== whole list: 5 checks ==', out)
        self.assertEqual(self.ran(out), ALL, out)

    def test_paths_of_several_rules_select_the_union(self):
        self.write('docs/guide.md', 'guide, edited\n')
        self.write('tests/unit_test.py', 'assert True\n')
        status, out, err = self.check('--changed')
        self.assertEqual(status, 0, out + err)
        self.assertEqual(self.ran(out), {'docs-lint', 'python-tests', 'whitespace'}, out)
        self.assertRegex(out, r'(?m)^selected +whitespace +docs/\*\*, tests/\*\*/\*\.py$')

    def test_a_rename_counts_the_path_it_leaves(self):
        git(self.clone, 'mv', 'scripts/tool.sh', 'docs/tool.md')
        git(self.clone, 'commit', '-q', '-m', 'move')
        status, out, err = self.check('--changed')
        self.assertEqual(status, 0, out + err)
        self.assertIn('unmapped path scripts/tool.sh: whole list', out)
        self.assertEqual(self.ran(out), ALL, out)

    def test_a_change_to_a_selection_input_runs_the_whole_list(self):
        self.write('docs/guide.md', 'guide, edited\n')
        self.mapping(lambda value: value['changed'].append({'paths': ['**'], 'checks': ['whitespace']}))
        status, out, err = self.check('--changed')
        self.assertEqual(status, 0, out + err)
        self.assertIn('selection input changed: jpdev.json: whole list', out)
        self.assertEqual(self.ran(out), ALL, out)
        git(self.clone, 'checkout', '-q', '--', 'jpdev.json')
        manifest = json.loads((self.clone / 'dev.json').read_text())
        manifest['checks'][0]['run'] = "echo 'docs-lint ran again'"
        self.write('dev.json', json.dumps(manifest))
        status, out, err = self.check('--changed')
        self.assertEqual(status, 0, out + err)
        self.assertIn('selection input changed: dev.json: whole list', out)
        self.assertEqual(self.ran(out), ALL, out)

    def test_a_change_to_the_vendored_runner_runs_the_whole_list(self):
        runner = self.clone / 'scripts' / 'dev' / 'check.sh'
        runner.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(ROOT / 'templates' / 'check.sh'), str(runner))
        self.mapping(lambda value: value['changed'].append({'paths': ['scripts/dev/**'], 'checks': ['whitespace']}))
        base = self.commit_base('vendored runner')
        with runner.open('a') as handle:
            handle.write('# a line after the runner\n')
        status, out, err = self.check('--changed', base)
        self.assertEqual(status, 0, out + err)
        self.assertIn('selection input changed: scripts/dev/check.sh: whole list', out)
        self.assertEqual(self.ran(out), ALL, out)

    def test_a_change_to_the_vendored_selection_code_runs_the_whole_list(self):
        selection = self.clone / 'scripts' / 'dev' / 'changed_checks.py'
        selection.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(ROOT / 'scripts' / 'dev' / 'changed_checks.py'), str(selection))
        self.mapping(lambda value: value['changed'].append({'paths': ['scripts/dev/**'], 'checks': ['whitespace']}))
        base = self.commit_base('vendored selection code')
        with selection.open('a') as handle:
            handle.write('# a line after the selection code\n')
        status, out, err = self.check('--changed', base)
        self.assertEqual(status, 0, out + err)
        self.assertIn('selection input changed: scripts/dev/changed_checks.py: whole list', out)
        self.assertEqual(self.ran(out), ALL, out)

    def test_failures_name_the_kit_version(self):
        version = subprocess.run([str(JPDEV), '--version'], stdout=subprocess.PIPE, universal_newlines=True,
                                 check=True).stdout.strip()
        status, out, err = self.check('--changed', 'no-such-ref')
        self.assertEqual(status, 2, out + err)
        self.assertIn('jpdev: check --changed: refused by this kit, %s' % version, err)
        status, out, err = self.check('--chagned')
        self.assertEqual(status, 2, out + err)
        self.assertIn('check: unknown argument --chagned; this kit is %s' % version, err)

    def test_a_symlinked_manifest_retargeted_runs_the_whole_list(self):
        manifest = json.loads((FIXTURE / 'changed-dev.json').read_text())
        self.write('manifests/a.json', json.dumps(manifest))
        manifest['checks'][0]['run'] = "echo 'docs-lint ran from b'"
        self.write('manifests/b.json', json.dumps(manifest))
        (self.clone / 'dev.json').unlink()
        os.symlink('manifests/a.json', str(self.clone / 'dev.json'))
        self.mapping(lambda value: value['changed'].append({'paths': ['*.json'], 'checks': ['whitespace']}))
        base = self.commit_base('linked manifest')
        (self.clone / 'dev.json').unlink()
        os.symlink('manifests/b.json', str(self.clone / 'dev.json'))
        status, out, err = self.check('--changed', base)
        self.assertEqual(status, 0, out + err)
        self.assertIn('selection input changed: dev.json: whole list', out)
        self.assertEqual(self.ran(out), ALL, out)

    def test_a_staged_change_the_worktree_reverted_still_counts(self):
        self.write('cmd/tool/main.go', 'package main\n\nfunc main() {}\n')
        git(self.clone, 'add', 'cmd/tool/main.go')
        self.write('cmd/tool/main.go', 'package main\n')
        self.write('docs/guide.md', 'guide, edited\n')
        status, out, err = self.check('--changed')
        self.assertEqual(status, 0, out + err)
        self.assertEqual(self.ran(out), {'docs-lint', 'go-vet', 'go-test', 'whitespace'}, out)

    def test_a_commit_the_index_and_worktree_reverted_still_counts(self):
        self.write('cmd/tool/main.go', 'package main\n\nfunc main() {}\n')
        git(self.clone, 'commit', '-q', '-am', 'go change')
        self.write('cmd/tool/main.go', 'package main\n')
        git(self.clone, 'add', 'cmd/tool/main.go')
        self.write('docs/guide.md', 'guide, edited\n')
        status, out, err = self.check('--changed')
        self.assertEqual(status, 0, out + err)
        self.assertEqual(self.ran(out), {'docs-lint', 'go-vet', 'go-test', 'whitespace'}, out)

    def test_a_submodule_change_counts_whatever_its_ignore_setting(self):
        sub = self.work / 'sub'
        git(self.work, 'init', '-q', '-b', 'main', str(sub))
        (sub / 'lib.txt').write_text('one\n')
        git(sub, 'add', 'lib.txt')
        git(sub, 'commit', '-q', '-m', 'one')
        git(self.clone, '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', str(sub), 'third_party/lib')
        git(self.clone, 'config', '-f', '.gitmodules', 'submodule.third_party/lib.ignore', 'all')
        base = self.commit_base('submodule ignored by .gitmodules')
        (sub / 'lib.txt').write_text('two\n')
        git(sub, 'commit', '-q', '-am', 'two')
        bumped = git(sub, 'rev-parse', 'HEAD').stdout.decode().strip()
        with self.subTest(case='ignore = all in .gitmodules, a committed pointer bump'):
            git(self.clone, 'update-index', '--cacheinfo', '160000,%s,third_party/lib' % bumped)
            git(self.clone, 'commit', '-q', '-m', 'bump')
            self.write('docs/guide.md', 'guide, edited\n')
            status, out, err = self.check('--changed', base)
            self.assertEqual(status, 0, out + err)
            self.assertIn('unmapped path third_party/lib: whole list', out)
            self.assertEqual(self.ran(out), ALL, out)
        git(self.clone, 'reset', '-q', '--hard', base)
        with self.subTest(case='ignore = dirty in the clone configuration, a changed file in the submodule'):
            git(self.clone, 'config', 'submodule.third_party/lib.ignore', 'dirty')
            (self.clone / 'third_party' / 'lib' / 'lib.txt').write_text('edited\n')
            self.write('docs/guide.md', 'guide, edited\n')
            status, out, err = self.check('--changed', base)
            self.assertEqual(status, 0, out + err)
            self.assertIn('unmapped path third_party/lib: whole list', out)
            self.assertEqual(self.ran(out), ALL, out)

    def test_no_mapping_runs_the_whole_list(self):
        self.write('jpdev.json', json.dumps({'version': 1, 'generators': [
            {'name': 'reference', 'run': 'true', 'outputs': ['docs/reference.md']}]}))
        git(self.clone, 'commit', '-q', '-am', 'generators only')
        self.write('docs/guide.md', 'guide, edited\n')
        status, out, err = self.check('--changed', 'HEAD')
        self.assertEqual(status, 0, out + err)
        self.assertIn('no change mapping in jpdev.json: whole list', out)
        self.assertEqual(self.ran(out), ALL, out)
        git(self.clone, 'rm', '-q', 'jpdev.json')
        git(self.clone, 'commit', '-q', '-m', 'no declaration')
        status, out, err = self.check('--changed', 'HEAD')
        self.assertEqual(status, 0, out + err)
        self.assertIn('no jpdev.json: whole list', out)
        self.assertEqual(self.ran(out), ALL, out)

    def test_no_changed_path_runs_the_whole_list(self):
        status, out, err = self.check('--changed')
        self.assertEqual(status, 0, out + err)
        self.assertIn('== %s: 0 changed paths since origin/main' % self.LABEL, out)
        self.assertIn('no changed path: whole list', out)
        self.assertEqual(self.ran(out), ALL, out)

    def test_base_names_the_commit_to_compare_with(self):
        self.write('cmd/tool/main.go', 'package main\n\nfunc main() {}\n')
        git(self.clone, 'commit', '-q', '-am', 'go change')
        self.write('docs/guide.md', 'guide, edited\n')
        status, out, err = self.check('--changed', 'HEAD')
        self.assertEqual(status, 0, out + err)
        self.assertIn('1 changed path since HEAD', out)
        self.assertEqual(self.ran(out), {'docs-lint', 'whitespace'}, out)
        status, out, err = self.check('--changed', 'origin/main', '--skip', 'whitespace')
        self.assertEqual(status, 0, out + err)
        self.assertEqual(self.ran(out), {'docs-lint', 'go-vet', 'go-test'}, out)

    def test_invalid_mapping_is_refused_with_a_named_message(self):
        cases = [
            ('unknown check', lambda v: v['changed'][1]['checks'].append('go-tset'),
             "jpdev.json changed[1].checks: no check named 'go-tset' in dev.json"),
            ('escaping glob', lambda v: v['changed'][0]['paths'].append('../docs/**'),
             "jpdev.json changed[0].paths: glob '../docs/**': has an empty, . or .. segment"),
            ('partial double star', lambda v: v['changed'][0]['paths'].append('docs/**.md'),
             "jpdev.json changed[0].paths: glob 'docs/**.md': ** must be a whole segment"),
            ('brace', lambda v: v['changed'][0]['paths'].append('{docs,site}/**'),
             "jpdev.json changed[0].paths: glob '{docs,site}/**': { } is not supported (only *, ? and a ** segment are)"),
            ('empty mapping', lambda v: v.update(changed=[]),
             'jpdev.json changed: must be a non-empty array of rules'),
            ('object mapping', lambda v: v.update(changed={'docs/**': ['docs-lint']}),
             'jpdev.json changed: must be a non-empty array of rules'),
            ('missing checks', lambda v: v['changed'][2].pop('checks'),
             'jpdev.json changed[2]: a rule has exactly the members paths and checks'),
            ('extra member', lambda v: v['changed'][0].update(why='docs'),
             'jpdev.json changed[0]: a rule has exactly the members paths and checks'),
            ('empty paths', lambda v: v['changed'][0].update(paths=[]),
             'jpdev.json changed[0].paths: must be a non-empty array of non-empty strings'),
            ('empty glob', lambda v: v['changed'][0].update(paths=['']),
             'jpdev.json changed[0].paths: must be a non-empty array of non-empty strings'),
            ('repeated check', lambda v: v['changed'][0].update(checks=['docs-lint', 'docs-lint']),
             'jpdev.json changed[0].checks: names a value twice'),
            ('unknown member', lambda v: v.update(chnaged=[]), "jpdev.json: unknown member 'chnaged'"),
            ('version', lambda v: v.update(version=2), 'jpdev.json: version must be 1'),
        ]
        self.write('docs/guide.md', 'guide, edited\n')
        for label, change, message in cases:
            with self.subTest(case=label):
                self.mapping(change)
                status, out, err = self.check('--changed')
                self.assertEqual(status, 2, out + err)
                self.assertIn(self.LABEL + ': refused: ' + message + '\n', err)
                self.assertEqual(out, '')
                self.assertNotIn('check: running', err)
        self.write('jpdev.json', '{"version": 1, "changed": [')
        status, out, err = self.check('--changed')
        self.assertEqual(status, 2, out + err)
        self.assertIn(self.LABEL + ': refused: jpdev.json: not readable JSON', err)

    def test_an_unresolved_base_is_refused(self):
        status, out, err = self.check('--changed', 'no-such-ref')
        self.assertEqual(status, 2, out + err)
        self.assertIn("refused: cannot resolve BASE 'no-such-ref' to a commit", err)
        self.assertEqual(out, '')
        git(self.clone, 'remote', 'remove', 'origin')
        status, out, err = self.check('--changed')
        self.assertEqual(status, 2, out + err)
        self.assertIn('refused: no default branch found (origin/HEAD, origin/main or origin/master); name BASE', err)
        status, out, err = self.check('--changed', 'main')
        self.assertEqual(status, 0, out + err)
        self.assertIn('0 changed paths since main', out)

    def test_changed_and_only_are_not_given_together(self):
        status, out, err = self.check('--changed', '--only', 'docs-lint')
        self.assertEqual(status, 2, out + err)
        self.assertIn('--changed and --only both choose the steps; give one', err)


class VendoredChangedCheckTests(ChangedCheckTests):
    """Every fixture of ChangedCheckTests again, through the clone's vendored scripts/dev/check.sh and
    scripts/dev/changed_checks.py instead of bin/jpdev: the same selection, refusals and report."""

    LABEL = 'check.sh --changed'

    def seed(self, seed):
        runner = seed / 'scripts' / 'dev' / 'check.sh'
        runner.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(ROOT / 'scripts' / 'dev' / 'check.sh'), str(runner))
        shutil.copy(str(ROOT / 'scripts' / 'dev' / 'changed_checks.py'), str(runner.parent / 'changed_checks.py'))

    def check(self, *args, runner=None, env=None):
        result = subprocess.run([str(runner or self.clone / 'scripts' / 'dev' / 'check.sh')] + list(args),
                                cwd=str(self.clone), env=env or self.env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                                timeout=120)
        return result.returncode, result.stdout, result.stderr

    def report(self, out, label):
        """The selection block, from its heading to its last line, with the runner's name left out."""
        lines = out.split('== check summary')[0].splitlines()
        return [line.replace(label, 'RUNNER') for line in lines if not line.startswith('PASS ')]

    def test_the_kit_and_the_vendored_runner_select_alike(self):
        cases = [('docs', {'docs/guide.md': 'guide, edited\n'}),
                 ('go and tests', {'cmd/tool/main.go': 'package main\n\nfunc main() {}\n', 'tests/unit_test.py': 'assert 1\n'}),
                 ('unmapped', {'scripts/new.sh': 'true\n'})]
        for label, files in cases:
            with self.subTest(case=label):
                for name, text in files.items():
                    self.write(name, text)
                status, vendored, err = self.check('--changed')
                self.assertEqual(status, 0, vendored + err)
                status, kit, err = ChangedCheckTests.check(self, '--changed')
                self.assertEqual(status, 0, kit + err)
                self.assertEqual(self.report(vendored, self.LABEL), self.report(kit, ChangedCheckTests.LABEL))
                self.assertEqual(self.ran(vendored), self.ran(kit))
                git(self.clone, 'checkout', '-q', '--', '.')
                git(self.clone, 'clean', '-qfd')

    def test_the_template_in_the_kit_uses_the_kit_selection_code(self):
        self.write('docs/guide.md', 'guide, edited\n')
        env = dict(self.env, JPDEV_ROOT=str(self.clone))
        status, out, err = self.check('--changed', runner=ROOT / 'templates' / 'check.sh', env=env)
        self.assertEqual(status, 0, out + err)
        self.assertEqual(self.ran(out), {'docs-lint', 'whitespace'}, out)

    def test_failures_name_the_kit_version(self):
        line2 = (ROOT / 'templates' / 'check.sh').read_text().splitlines()[1]
        self.assertRegex(line2, r'^# from judgment-pack-devkit v[0-9]+\.[0-9]+\.[0-9]+ \(templates/check\.sh\)$')
        status, out, err = self.check('--chagned')
        self.assertEqual(status, 2, out + err)
        self.assertIn('check.sh: unknown argument --chagned (this runner is %s)\n' % line2[2:].split(' (')[0], err)

    def test_changed_needs_the_vendored_selection_code(self):
        (self.clone / 'scripts' / 'dev' / 'changed_checks.py').unlink()
        self.write('docs/guide.md', 'guide, edited\n')
        status, out, err = self.check('--changed')
        self.assertEqual(status, 2, out + err)
        self.assertIn('check.sh: --changed needs changed_checks.py beside this script', err)
        self.assertEqual(out, '')

    def test_changed_selects_checks_not_setup_steps(self):
        status, out, err = self.check('--setup', '--changed')
        self.assertEqual(status, 2, out + err)
        self.assertIn('check.sh: --changed selects checks, not setup steps', err)


SCHEMA_KEYWORDS = {'$schema', 'title', 'description', 'type', 'const', 'enum', 'required', 'anyOf', 'properties',
                   'additionalProperties', 'items', 'minItems', 'uniqueItems', 'minLength', 'minimum',
                   'maximum', 'multipleOf', 'pattern'}
SCHEMA_TYPES = {'object': dict, 'array': list, 'string': str}


def schema_errors(schema, value, where='$'):
    """The JSON Schema keywords templates/jpdev.schema.json uses, with the standard library alone.

    A keyword outside that set fails the test, so the schema cannot outgrow this reader unseen.
    """
    unknown = set(schema) - SCHEMA_KEYWORDS
    if unknown:
        raise AssertionError('the stdlib schema reader does not know %s' % sorted(unknown))
    kind = schema.get('type')
    if kind == 'integer' and not (type(value) is int):
        return ['%s: not an integer' % where]
    if kind in SCHEMA_TYPES and not isinstance(value, SCHEMA_TYPES[kind]):
        return ['%s: not %s' % (where, kind)]
    errors = []
    if 'const' in schema and (value != schema['const'] or isinstance(value, bool) != isinstance(schema['const'], bool)):
        errors.append('%s: not %r' % (where, schema['const']))
    if 'enum' in schema and not any(value == option and type(value) is type(option) for option in schema['enum']):
        errors.append('%s: not one of %r' % (where, schema['enum']))
    if 'anyOf' in schema and all(schema_errors(option, value, where) for option in schema['anyOf']):
        errors.append('%s: matches no anyOf option' % where)
    if isinstance(value, dict):
        errors += ['%s: %s is required' % (where, key) for key in schema.get('required', []) if key not in value]
        for key, item in value.items():
            if key in schema.get('properties', {}):
                errors += schema_errors(schema['properties'][key], item, '%s.%s' % (where, key))
            elif schema.get('additionalProperties') is False:
                errors.append('%s: %s is not allowed' % (where, key))
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0):
            errors.append('%s: fewer than %d items' % (where, schema['minItems']))
        if schema.get('uniqueItems') and len({json.dumps(i, sort_keys=True) for i in value}) != len(value):
            errors.append('%s: repeated items' % where)
        for index, item in enumerate(value):
            if 'items' in schema:
                errors += schema_errors(schema['items'], item, '%s[%d]' % (where, index))
    if isinstance(value, str):
        if len(value) < schema.get('minLength', 0):
            errors.append('%s: too short' % where)
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            errors.append('%s: does not match the pattern' % where)
    if type(value) is int and not schema.get('minimum', value) <= value <= schema.get('maximum', value):
        errors.append('%s: out of range' % where)
    if type(value) in (int, float) and 'multipleOf' in schema and value % schema['multipleOf']:
        errors.append('%s: not a multiple of %r' % (where, schema['multipleOf']))
    return errors


class DeclarationTests(unittest.TestCase):
    def test_shipped_mappings_name_steps_of_their_manifests(self):
        for config, manifest in ((ROOT / 'templates' / 'jpdev.json', ROOT / 'templates' / 'dev.json'),
                                 (ROOT / 'jpdev.json', ROOT / 'dev.json'),
                                 (FIXTURE / 'changed-jpdev.json', FIXTURE / 'changed-dev.json')):
            with self.subTest(config=str(config.relative_to(ROOT))):
                rules, no_mapping = c.load_rules(config.parent, c.step_names(str(manifest)), manifest.name,
                                                 config.name)
                self.assertIsNone(no_mapping)
                self.assertTrue(rules)

    def test_the_schema_holds_the_shape_the_command_reads(self):
        # The standard-library reader always runs, so the test never skips; the jsonschema package,
        # where it is installed, reads the same vectors too.
        schema = json.loads((ROOT / 'templates' / 'jpdev.schema.json').read_text())
        readers = [('stdlib', lambda value: schema_errors(schema, value))]
        try:
            import jsonschema
            validator = jsonschema.Draft202012Validator(schema)
            readers.append(('jsonschema', lambda value: list(validator.iter_errors(value))))
        except ImportError:
            pass
        good = json.loads((FIXTURE / 'changed-jpdev.json').read_text())
        for reader, errors in readers:
            for value in (good, json.loads((ROOT / 'templates' / 'jpdev.json').read_text()),
                          json.loads((ROOT / 'jpdev.json').read_text())):
                self.assertEqual(errors(value), [], reader)
        bad = {
            'no declaration': lambda v: v.pop('changed'),
            'empty mapping': lambda v: v.update(changed=[]),
            'object mapping': lambda v: v.update(changed={'docs/**': ['docs-lint']}),
            'string rule': lambda v: v.update(changed=['docs/**']),
            'missing checks': lambda v: v['changed'][0].pop('checks'),
            'extra member': lambda v: v['changed'][0].update(why='docs'),
            'empty paths': lambda v: v['changed'][0].update(paths=[]),
            'empty checks': lambda v: v['changed'][0].update(checks=[]),
            'repeated glob': lambda v: v['changed'][0].update(paths=['docs/**', 'docs/**']),
            'repeated check': lambda v: v['changed'][0].update(checks=['docs-lint', 'docs-lint']),
            'number glob': lambda v: v['changed'][0].update(paths=[1]),
            'number check': lambda v: v['changed'][0].update(checks=[1]),
            'escaping glob': lambda v: v['changed'][0].update(paths=['../docs/**']),
            'rooted glob': lambda v: v['changed'][0].update(paths=['/docs/**']),
            'partial double star': lambda v: v['changed'][0].update(paths=['docs/**.md']),
            'brace': lambda v: v['changed'][0].update(paths=['{docs,site}/**']),
            'check name': lambda v: v['changed'][0].update(checks=['docs lint']),
        }
        for reader, errors in readers:
            for label, change in bad.items():
                with self.subTest(reader=reader, case=label):
                    value = copy.deepcopy(good)
                    change(value)
                    self.assertNotEqual(errors(value), [], label)


if __name__ == '__main__':
    unittest.main()
