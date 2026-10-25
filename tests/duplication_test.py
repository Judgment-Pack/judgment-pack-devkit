"""Handwritten fixture repositories exercise the duplication check through its command line."""
import copy
import importlib.util
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = Path(os.environ.get('DUPLICATION_HELPER', str(ROOT / 'lib' / 'duplication.py')))
SPEC = importlib.util.spec_from_file_location('duplication', str(HELPER))
d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)

# One function, 29 tokens: def total ( rows ) : / result = 0 / for row in rows : /
# if row . amount > 0 : / result + = row . amount / return result. It spans 6 lines.
LEDGER = '''import os


def total(rows):
    result = 0
    for row in rows:
        if row.amount > 0:
            result += row.amount
    return result


def name(value):
    return value.strip().lower()
'''
# The same function after other code, with a comment inside it: 7 lines (8-14).
REPORT = '''"""Report helpers."""


class Ledger:
    pass


def total(rows):
    # copied from the ledger
    result = 0
    for row in rows:
        if row.amount > 0:
            result += row.amount
    return result
'''
# The copy between ignore markers, in the comment syntax of the language.
REPORT_IGNORED = '''"""Report helpers."""


class Ledger:
    pass


# duplication:ignore-start
def total(rows):
    result = 0
    for row in rows:
        if row.amount > 0:
            result += row.amount
    return result
# duplication:ignore-end
'''
# The marker text in a string is not a marker: the copy is still read.
REPORT_STRING_MARKER = '''"""Report helpers."""

MARK = "duplication:ignore-start"


def total(rows):
    result = 0
    for row in rows:
        if row.amount > 0:
            result += row.amount
    return result
'''
# 59 tokens on lines 6-12.
AUDIT_GO = '''package audit

import "strings"

// Normalize trims and lowers each name.
func Normalize(names []string) []string {
	out := make([]string, 0, len(names))
	for _, name := range names {
		out = append(out, strings.ToLower(strings.TrimSpace(name)))
	}
	return out
}
'''
# The same tokens laid out differently, with a comment: lines 7-14.
EXPORT_GO = '''package export

import (
	"strings"
)

func Normalize(names []string) []string {
	out := make([]string, 0, len(names)) // capacity first
	for _, name := range names {
		out = append(out,
			strings.ToLower(strings.TrimSpace(name)))
	}
	return out
}
'''
# The Go copy between a block-comment start marker and a line-comment end marker.
EXPORT_GO_IGNORED = '''package export

import (
	"strings"
)

/* duplication:ignore-start: kept apart from audit on purpose */
func Normalize(names []string) []string {
	out := make([]string, 0, len(names)) // capacity first
	for _, name := range names {
		out = append(out,
			strings.ToLower(strings.TrimSpace(name)))
	}
	return out
}
// duplication:ignore-end
'''
# Three copies in one file (lines 1-6, 12-17, 23-28): two pairs, each copy against the one before it.
THREE = '''def total(rows):
    result = 0
    for row in rows:
        if row.amount > 0:
            result += row.amount
    return result


first = 1


def total(rows):
    result = 0
    for row in rows:
        if row.amount > 0:
            result += row.amount
    return result


second = 2


def total(rows):
    result = 0
    for row in rows:
        if row.amount > 0:
            result += row.amount
    return result
'''
PYTHON = {'languages': ['python'], 'min_tokens': 20, 'min_lines': 5}


def texts(language, text):
    """The token texts of a text, a barrier shown as <barrier>, and its marker problems."""
    vocabulary = {}
    ids, _, _, problems = d.tokenize(text, language, vocabulary, itertools.count(-1, -1))
    names = {value: key for key, value in vocabulary.items()}
    return [names.get(token, '<barrier>') for token in ids], problems


class Fixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='duplication-fixture-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def declare(self, duplication):
        self.write('jpdev.json', json.dumps({'version': 1, 'duplication': duplication}))

    def cli(self, *args):
        return subprocess.run([sys.executable, str(HELPER), '--root', str(self.root)] + list(args),
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)


class DuplicatePairs(Fixture):
    def test_a_copy_above_the_threshold_fails_and_names_both_places(self):
        self.declare(PYTHON)
        self.write('src/ledger.py', LEDGER)
        self.write('tools/report.py', REPORT)
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            'duplication: 1 duplicate pair (at least 20 tokens over at least 5 lines, 2 files of python)',
            '  src/ledger.py:4-9 and tools/report.py:8-14: 29 tokens',
        ])

    def test_the_token_threshold_is_inclusive(self):
        self.write('src/ledger.py', LEDGER)
        self.write('tools/report.py', REPORT)
        self.declare(dict(PYTHON, min_tokens=29))
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('  src/ledger.py:4-9 and tools/report.py:8-14: 29 tokens', result.stdout)
        self.declare(dict(PYTHON, min_tokens=30))
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout,
                         'duplication: no duplicate block (at least 30 tokens over at least 5 lines, 2 files of python)\n')

    def test_each_place_must_span_the_line_threshold(self):
        # The ledger copy spans 6 lines and the report copy 7: the shorter one decides.
        self.write('src/ledger.py', LEDGER)
        self.write('tools/report.py', REPORT)
        self.declare(dict(PYTHON, min_lines=6))
        self.assertEqual(self.cli().returncode, 1)
        self.declare(dict(PYTHON, min_lines=7))
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('duplication: no duplicate block', result.stdout)

    def test_layout_and_comments_do_not_hide_a_copy(self):
        self.declare({'languages': ['go'], 'min_tokens': 50, 'min_lines': 5})
        self.write('audit/normalize.go', AUDIT_GO)
        self.write('export/normalize.go', EXPORT_GO)
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('  audit/normalize.go:6-12 and export/normalize.go:7-14: 59 tokens', result.stdout)

    def test_three_copies_in_one_file_make_two_pairs(self):
        self.declare(PYTHON)
        self.write('three.py', THREE)
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[1:], [
            '  three.py:1-6 and three.py:12-17: 29 tokens',
            '  three.py:12-17 and three.py:23-28: 29 tokens',
        ])

    def test_a_repeated_short_pattern_is_not_a_copy_of_itself(self):
        # "0," repeated: every run of 10 tokens recurs 2 tokens later, but the two places overlap.
        self.declare({'languages': ['python'], 'min_tokens': 10, 'min_lines': 1})
        self.write('table.py', 'VALUES = [\n' + '    0,\n' * 300 + ']\n')
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('duplication: no duplicate block', result.stdout)


class IgnoreBlock(Fixture):
    def test_the_ignore_block_suppresses_an_intentional_copy(self):
        self.declare(PYTHON)
        self.write('src/ledger.py', LEDGER)
        self.write('tools/report.py', REPORT_IGNORED)
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout,
                         'duplication: no duplicate block (at least 20 tokens over at least 5 lines, 2 files of python)\n')

    def test_the_markers_work_in_block_and_line_comments(self):
        self.declare({'languages': ['go'], 'min_tokens': 50, 'min_lines': 5})
        self.write('audit/normalize.go', AUDIT_GO)
        self.write('export/normalize.go', EXPORT_GO_IGNORED)
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('duplication: no duplicate block', result.stdout)

    def test_the_marker_text_in_a_string_is_not_a_marker(self):
        self.declare(PYTHON)
        self.write('src/ledger.py', LEDGER)
        self.write('tools/report.py', REPORT_STRING_MARKER)
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('  src/ledger.py:4-9 and tools/report.py:6-11: 29 tokens', result.stdout)
        self.assertNotIn('ignore marker problem', result.stdout)

    def test_an_ignored_region_does_not_join_the_code_around_it(self):
        tokens, problems = texts('python', 'a = 1\n# duplication:ignore-start\nb = 2\n# duplication:ignore-end\nc = 3\n')
        self.assertEqual(tokens, ['a', '=', '1', '<barrier>', 'c', '=', '3'])
        self.assertEqual(problems, [])

    def test_marker_problems_fail_and_name_the_line(self):
        self.declare(PYTHON)
        self.write('a.py', 'x = 1\n# duplication:ignore-start\ny = 2\n')
        self.write('b.py', 'x = 1  # duplication:ignore-end\n')
        self.write('c.py', '# duplication:ignore-start\n# duplication:ignore-start\nz = 3\n# duplication:ignore-end\n')
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[-4:], [
            'duplication: 3 ignore marker problems',
            '  a.py:2: duplication:ignore-start is never closed by a duplication:ignore-end',
            '  b.py:1: duplication:ignore-end without a duplication:ignore-start before it',
            '  c.py:2: duplication:ignore-start inside the ignore block opened at line 1',
        ])


class Tokens(unittest.TestCase):
    def test_go_strings_and_comments(self):
        tokens, _ = texts('go', 'x := `a // b` + "c /* d" // e\n/* f */ y\n')
        self.assertEqual(tokens, ['x', ':', '=', '`a // b`', '+', '"c /* d"', 'y'])

    def test_script_strings_and_comments(self):
        for language in ('javascript', 'typescript'):
            with self.subTest(language=language):
                tokens, _ = texts(language, "const u = 'http://x'; // note\nconst t = `line\n// in template`;\n")
                self.assertEqual(tokens, ['const', 'u', '=', "'http://x'", ';', 'const', 't', '=',
                                          '`line\n// in template`', ';'])

    def test_python_strings_and_comments(self):
        tokens, _ = texts('python', 'a = "#" # note\nb = """x\n# not a comment\n"""\n')
        self.assertEqual(tokens, ['a', '=', '"#"', 'b', '=', '"""x\n# not a comment\n"""'])

    def test_shell_comments_start_a_word(self):
        tokens, _ = texts('shell', 'echo "$#" ${#list[@]} a#b # note\n')
        self.assertEqual(tokens, ['echo', '"$#"', '$', '{', '#', 'list', '[', '@', ']', '}', 'a', '#', 'b'])

    def test_an_unclosed_quote_ends_at_the_line_end(self):
        tokens, _ = texts('go', 'a := "open\nb := 1\n')
        self.assertEqual(tokens, ['a', ':', '=', '"open', 'b', ':', '=', '1'])

    def test_a_string_over_lines_ends_on_its_last_line(self):
        vocabulary = {}
        _, firsts, lasts, _ = d.tokenize('x = """a\nb\nc"""\n', 'python', vocabulary, itertools.count(-1, -1))
        self.assertEqual((firsts, lasts), ([1, 1, 1], [1, 1, 3]))


class Scope(Fixture):
    def test_off_without_a_declaration(self):
        result = self.cli()
        self.assertEqual((result.returncode, result.stdout),
                         (0, 'duplication: off: there is no jpdev.json (a repository opts in with its thresholds)\n'))
        self.write('jpdev.json', json.dumps({'version': 1, 'generators': [
            {'name': 'reference', 'run': 'true', 'outputs': ['docs/reference.md']}]}))
        self.write('src/ledger.py', LEDGER)
        self.write('tools/report.py', REPORT)
        result = self.cli()
        self.assertEqual((result.returncode, result.stdout), (0, 'duplication: off: jpdev.json declares no duplication '
                                                               'member (a repository opts in with its thresholds)\n'))

    def test_only_the_declared_languages_are_read(self):
        self.declare({'languages': ['go'], 'min_tokens': 20, 'min_lines': 5})
        self.write('src/ledger.py', LEDGER)
        self.write('tools/report.py', REPORT)
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('0 files of go', result.stdout)

    def test_paths_and_exclude_globs(self):
        self.write('src/ledger.py', LEDGER)
        self.write('tools/report.py', REPORT)
        self.declare(dict(PYTHON, paths=['src/**']))
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('1 file of python', result.stdout)
        self.declare(dict(PYTHON, exclude=['tools/*.py']))
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('1 file of python', result.stdout)
        self.declare(dict(PYTHON, paths=['**/*.py'], exclude=['docs/**']))
        self.assertEqual(self.cli().returncode, 1)

    def test_ignored_files_and_links_are_not_read(self):
        self.declare(PYTHON)
        self.write('src/ledger.py', LEDGER)
        self.write('.gitignore', 'build/\n')
        self.write('build/ledger.py', LEDGER)
        (self.root / 'link.py').symlink_to(self.root / 'src' / 'ledger.py')
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('1 file of python', result.stdout)

    def test_tracked_and_untracked_files_are_read(self):
        self.declare(PYTHON)
        self.write('src/ledger.py', LEDGER)
        subprocess.run(['git', 'add', 'src/ledger.py'], cwd=str(self.root), check=True, capture_output=True)
        self.write('tools/report.py', REPORT)
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('2 files of python', result.stdout)

    def test_the_vendored_step_of_the_template_manifest_fails_the_check_list(self):
        step = [s for s in json.loads((ROOT / 'templates' / 'dev.json').read_text())['checks']
                if s['name'] == 'duplication']
        self.assertEqual(len(step), 1, 'templates/dev.json lists the duplication step once')
        self.write('dev.json', json.dumps({'version': 1, 'checks': step}))
        (self.root / 'scripts' / 'dev').mkdir(parents=True)
        shutil.copy(str(HELPER), str(self.root / 'scripts' / 'dev' / 'duplication.py'))
        self.declare(PYTHON)
        self.write('src/ledger.py', LEDGER)
        self.write('tools/report.py', REPORT)
        env = {k: v for k, v in os.environ.items() if not k.startswith('JPDEV_') and k != 'CI'}
        env['JPDEV_ROOT'] = str(self.root)
        result = subprocess.run([str(ROOT / 'templates' / 'check.sh'), '--manifest', str(self.root / 'dev.json')],
                                env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r'(?m)^FAIL +duplication ')
        self.assertIn('    duplication: 1 duplicate pair (at least 20 tokens', result.stdout)
        self.assertIn('    src/ledger.py:4-9 and tools/report.py:8-14: 29 tokens', result.stdout)


GOOD = {'languages': ['go', 'javascript', 'python', 'shell', 'typescript'], 'paths': ['**', 'src/*.go'],
        'exclude': ['**/testdata/**', 'gen/?.ts'], 'min_tokens': 10, 'min_lines': 1}
# A change to a good declaration, the member the refusal names, and the words it says.
REFUSED = [
    ('version 2', lambda v: v.update(version=2), 'jpdev.json version: 1 is required (got 2)'),
    ('not an object', lambda v: v.update(duplication=[]), 'jpdev.json duplication: an object is required'),
    ('unknown member', lambda v: v['duplication'].update(threshold=50),
     "jpdev.json duplication: unknown member 'threshold' (allowed: exclude, languages, min_lines, min_tokens, paths)"),
    ('missing languages', lambda v: v['duplication'].pop('languages'), 'jpdev.json duplication.languages: required'),
    ('missing min_tokens', lambda v: v['duplication'].pop('min_tokens'), 'jpdev.json duplication.min_tokens: required'),
    ('missing min_lines', lambda v: v['duplication'].pop('min_lines'), 'jpdev.json duplication.min_lines: required'),
    ('empty languages', lambda v: v['duplication'].update(languages=[]),
     'jpdev.json duplication.languages: a non-empty list of language names is required'),
    ('unknown language', lambda v: v['duplication'].update(languages=['go', 'cobol']),
     'jpdev.json duplication.languages[1]: "cobol" is not one of go, javascript, python, shell, typescript'),
    ('repeated language', lambda v: v['duplication'].update(languages=['go', 'go']),
     "jpdev.json duplication.languages[1]: 'go' is repeated"),
    ('min_tokens too small', lambda v: v['duplication'].update(min_tokens=9),
     'jpdev.json duplication.min_tokens: an integer from 10 to 10000 is required (got 9)'),
    ('min_tokens oversized', lambda v: v['duplication'].update(min_tokens=10001),
     'jpdev.json duplication.min_tokens: an integer from 10 to 10000 is required (got 10001)'),
    ('min_tokens boolean', lambda v: v['duplication'].update(min_tokens=True),
     'jpdev.json duplication.min_tokens: an integer from 10 to 10000 is required (got true)'),
    ('min_tokens string', lambda v: v['duplication'].update(min_tokens='50'),
     'jpdev.json duplication.min_tokens: an integer from 10 to 10000 is required (got "50")'),
    ('min_lines zero', lambda v: v['duplication'].update(min_lines=0),
     'jpdev.json duplication.min_lines: an integer from 1 to 10000 is required (got 0)'),
    ('min_lines oversized', lambda v: v['duplication'].update(min_lines=10001),
     'jpdev.json duplication.min_lines: an integer from 1 to 10000 is required (got 10001)'),
    ('empty paths', lambda v: v['duplication'].update(paths=[]),
     'jpdev.json duplication.paths: a non-empty list of globs is required'),
    ('parent segment', lambda v: v['duplication'].update(paths=['../src/**']),
     "jpdev.json duplication.paths[0]: '../src/**' has an empty, . or .. segment"),
    ('rooted glob', lambda v: v['duplication'].update(paths=['/src/**']),
     "jpdev.json duplication.paths[0]: '/src/**' must be relative to the repository root"),
    ('partial double star', lambda v: v['duplication'].update(paths=['src/**.py']),
     "jpdev.json duplication.paths[0]: 'src/**.py': ** must be a whole segment"),
    ('character class', lambda v: v['duplication'].update(paths=['[ab]/*.py']),
     "jpdev.json duplication.paths[0]: '[ab]/*.py': '[' is not supported"),
    ('empty glob', lambda v: v['duplication'].update(paths=['']),
     'jpdev.json duplication.paths[0]: must be a non-empty string'),
    ('empty exclude', lambda v: v['duplication'].update(exclude=[]),
     'jpdev.json duplication.exclude: a non-empty list of globs is required'),
    ('repeated exclude', lambda v: v['duplication'].update(exclude=['gen/**', 'gen/**']),
     "jpdev.json duplication.exclude[1]: 'gen/**' is repeated"),
]


class Configuration(Fixture):
    def declaration(self, change=None):
        value = {'version': 1, 'duplication': copy.deepcopy(GOOD)}
        if change:
            change(value)
        return value

    def test_a_good_declaration_is_read(self):
        config = d.settings(self.declaration())
        self.assertEqual((config['languages'], config['min_tokens'], config['min_lines']),
                         (GOOD['languages'], 10, 1))

    def test_each_invalid_declaration_is_refused_with_its_member_named(self):
        for name, change, message in REFUSED:
            with self.subTest(case=name):
                with self.assertRaises(d.Refused) as caught:
                    d.settings(self.declaration(change))
                self.assertEqual(str(caught.exception), message)

    def test_the_command_refuses_before_reading_any_file(self):
        self.write('src/ledger.py', LEDGER)
        self.write('tools/report.py', REPORT)
        self.declare(dict(PYTHON, min_tokens=5))
        result = self.cli()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, 'duplication: refused: jpdev.json duplication.min_tokens: an integer from '
                                        '10 to 10000 is required (got 5)\n')
        self.write('jpdev.json', '{"version": 1, "duplication": ')
        result = self.cli()
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.startswith('duplication: refused: jpdev.json cannot be read as JSON: '), result.stderr)
        self.write('jpdev.json', '[]')
        result = self.cli()
        self.assertEqual((result.returncode, result.stderr), (2, 'duplication: refused: jpdev.json: an object is required\n'))

    def test_the_shipped_declarations_are_read(self):
        template = json.loads((ROOT / 'templates' / 'jpdev.json').read_text())
        self.assertIsNotNone(d.settings(template), 'templates/jpdev.json shows the duplication member')


class Schema(unittest.TestCase):
    """templates/jpdev.schema.json holds the shape the command reads."""

    def setUp(self):
        self.schema = json.loads((ROOT / 'templates' / 'jpdev.schema.json').read_text())
        self.member = self.schema['properties']['duplication']

    def test_the_schema_and_the_command_name_the_same_members_and_bounds(self):
        member = self.member
        self.assertEqual(sorted(member['properties']), list(d.MEMBERS))
        self.assertEqual(member['required'], ['languages', 'min_tokens', 'min_lines'])
        self.assertFalse(member['additionalProperties'])
        self.assertEqual(member['properties']['languages']['items']['enum'], sorted(d.LANGUAGES))
        for name, bounds in (('min_tokens', d.MIN_TOKENS), ('min_lines', d.MIN_LINES)):
            limits = member['properties'][name]
            self.assertEqual((limits['type'], limits['minimum'], limits['maximum']), ('integer',) + bounds)

    def test_the_schema_and_the_command_agree_on_every_vector(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest('the jsonschema package is not installed')
        validator = jsonschema.Draft202012Validator(self.schema)
        good = {'version': 1, 'duplication': copy.deepcopy(GOOD)}
        self.assertEqual(list(validator.iter_errors(good)), [])
        self.assertEqual(list(validator.iter_errors({'version': 1, 'duplication': dict(PYTHON)})), [],
                         'a declaration of duplication alone is valid')
        self.assertEqual(list(validator.iter_errors(json.loads((ROOT / 'templates' / 'jpdev.json').read_text()))), [])
        for name, change, _ in REFUSED:
            value = copy.deepcopy(good)
            change(value)
            with self.subTest(case=name):
                self.assertTrue(list(validator.iter_errors(value)), 'the schema accepts what the command refuses')


if __name__ == '__main__':
    unittest.main()
