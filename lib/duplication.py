#!/usr/bin/env python3
"""The duplication check: name each block of code that appears in two places.

Off unless the repository's jpdev.json declares a `duplication` member: the languages to read, a
token threshold, a line threshold and, optionally, path globs and a file size limit. A file over
the limit, or with a NUL byte near its start, is not read and is named. A pair is reported when two places
share at least min_tokens tokens and each place spans at least min_lines lines. Layout and
comments are not tokens; identifiers, keywords, numbers, string literals and each punctuation
character are. The code between a comment holding `duplication:ignore-start` and a comment holding
`duplication:ignore-end` is left out, so an intentional copy can be marked. Standard library only.

Exit status: 0 when no pair is found or the check is off, 1 when a pair or an ignore marker problem
is found (the report names each), 2 when the configuration is refused.
"""
import argparse
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import sys

MIN_TOKENS = (10, 10000)
MIN_LINES = (1, 10000)
MAX_FILE_BYTES = (1024, 104857600)
DEFAULT_MAX_FILE_BYTES = 1048576
MEMBERS = ('exclude', 'languages', 'max_file_bytes', 'min_lines', 'min_tokens', 'paths')
# A file whose first BINARY_PROBE bytes hold a NUL byte is binary and is not read.
BINARY_PROBE = 8192
# The most recent places of each run of min_tokens tokens that a later place is compared with.
RECENT = 16

_C_COMMENTS = r'//[^\n]*|/\*[\s\S]*?(?:\*/|\Z)'
# A quoted string that may not span a line ends at the line's end when it is not closed.
_LINE_STRINGS = r'"(?:[^"\\\n]|\\[\s\S])*"?|' r"'(?:[^'\\\n]|\\[\s\S])*'?"
_SCRIPT_STRINGS = _LINE_STRINGS + r'|`(?:[^`\\]|\\[\s\S])*`?'
# name: (file extensions, comment syntax, string syntax)
LANGUAGES = {
    'go': (('.go',), _C_COMMENTS, _LINE_STRINGS + r'|`[^`]*`?'),
    'javascript': (('.cjs', '.js', '.jsx', '.mjs'), _C_COMMENTS, _SCRIPT_STRINGS),
    'python': (('.py', '.pyi'), r'#[^\n]*',
               r'"""(?:[^\\]|\\[\s\S])*?(?:"""|\Z)|' r"'''(?:[^\\]|\\[\s\S])*?(?:'''|\Z)|" + _LINE_STRINGS),
    # A shell comment starts where a word may start: `$#` and `${x#y}` are not comments.
    'shell': (('.bash', '.sh'), r'(?<![^\s;|&()])#[^\n]*', r"'[^']*'?|" r'"(?:[^"\\]|\\[\s\S])*"?'),
    'typescript': (('.cts', '.mts', '.ts', '.tsx'), _C_COMMENTS, _SCRIPT_STRINGS),
}
SCANNERS = {name: re.compile(r'(?P<comment>%s)|(?P<string>%s)|(?P<word>\w+)|(?P<space>\s+)|(?P<punct>[^\w\s])'
                             % (comments, strings)) for name, (_, comments, strings) in LANGUAGES.items()}
MARKER = re.compile(r'(?<![\w-])duplication:ignore-(start|end)(?![\w-])')
_MOD, _BASE = (1 << 61) - 1, 1000003
_STRIDE = 1 << 40


class Refused(ValueError):
    pass


def glob_pattern(glob, where):
    """A compiled full-path pattern: * and ? stay within one segment, a ** segment spans any number."""
    if not isinstance(glob, str) or not glob:
        raise Refused('%s: must be a non-empty string' % where)
    if glob.startswith('/'):
        raise Refused('%s: %r must be relative to the repository root' % (where, glob))
    for character in '[]{}\\':
        if character in glob:
            raise Refused('%s: %r: %r is not supported' % (where, glob, character))
    parts = glob.split('/')
    if any(part in ('', '.', '..') for part in parts):
        raise Refused('%s: %r has an empty, . or .. segment' % (where, glob))
    if any('**' in part and part != '**' for part in parts):
        raise Refused('%s: %r: ** must be a whole segment' % (where, glob))
    expression = ''
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if part == '**':
            expression += '.*' if last else '(?:[^/]+/)*'
        else:
            expression += ''.join('[^/]*' if c == '*' else '[^/]' if c == '?' else re.escape(c) for c in part)
            expression += '' if last else '/'
    return re.compile(expression, re.S)


def _integer(value, bounds, where):
    if type(value) is not int or not bounds[0] <= value <= bounds[1]:
        raise Refused('%s: an integer from %d to %d is required (got %s)' % (where, bounds[0], bounds[1], json.dumps(value)))
    return value


def _globs(value, where):
    if not isinstance(value, list) or not value:
        raise Refused('%s: a non-empty list of globs is required' % where)
    patterns = []
    for index, glob in enumerate(value):
        here = '%s[%d]' % (where, index)
        patterns.append(glob_pattern(glob, here))
        if glob in value[:index]:
            raise Refused('%s: %r is repeated' % (here, glob))
    return patterns


def settings(declaration, name='jpdev.json'):
    """The validated duplication settings of a parsed jpdev.json, or None when it declares none."""
    if not isinstance(declaration, dict):
        raise Refused('%s: an object is required' % name)
    if type(declaration.get('version')) is not int or declaration.get('version') != 1:
        raise Refused('%s version: 1 is required (got %s)' % (name, json.dumps(declaration.get('version'))))
    if 'duplication' not in declaration:
        return None
    value, where = declaration['duplication'], name + ' duplication'
    if not isinstance(value, dict):
        raise Refused('%s: an object is required' % where)
    for member in sorted(value):
        if member not in MEMBERS:
            raise Refused('%s: unknown member %r (allowed: %s)' % (where, member, ', '.join(MEMBERS)))
    for member in ('languages', 'min_tokens', 'min_lines'):
        if member not in value:
            raise Refused('%s.%s: required' % (where, member))
    languages = value['languages']
    if not isinstance(languages, list) or not languages:
        raise Refused('%s.languages: a non-empty list of language names is required' % where)
    for index, language in enumerate(languages):
        here = '%s.languages[%d]' % (where, index)
        if not isinstance(language, str) or language not in LANGUAGES:
            raise Refused('%s: %s is not one of %s' % (here, json.dumps(language), ', '.join(sorted(LANGUAGES))))
        if language in languages[:index]:
            raise Refused('%s: %r is repeated' % (here, language))
    return {
        'languages': sorted(languages),
        'paths': _globs(value.get('paths', ['**']), where + '.paths'),
        'exclude': _globs(value['exclude'], where + '.exclude') if 'exclude' in value else [],
        'min_tokens': _integer(value['min_tokens'], MIN_TOKENS, where + '.min_tokens'),
        'min_lines': _integer(value['min_lines'], MIN_LINES, where + '.min_lines'),
        'max_file_bytes': _integer(value.get('max_file_bytes', DEFAULT_MAX_FILE_BYTES), MAX_FILE_BYTES,
                                   where + '.max_file_bytes'),
    }


def candidates(root, config):
    """The repository-relative paths in scope and their languages: tracked and not-ignored files."""
    listed = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=str(root),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if listed.returncode:
        raise Refused('%s: not a git work tree (git ls-files exited %d)' % (root, listed.returncode))
    by_extension = {extension: language for language in config['languages'] for extension in LANGUAGES[language][0]}
    result = []
    for value in sorted({os.fsdecode(raw) for raw in listed.stdout.split(b'\0') if raw}):
        language = by_extension.get(os.path.splitext(value)[1])
        if (language is None or not any(p.fullmatch(value) for p in config['paths'])
                or any(p.fullmatch(value) for p in config['exclude'])):
            continue
        path = root / value
        # A symbolic link is not followed, whether it is the file or a directory above it (a
        # tracked directory replaced by a link), and a tracked file deleted from the work tree is
        # not read: the path must resolve to itself, a regular file below the root.
        if path.is_symlink() or not path.is_file() or path.resolve() != path:
            continue
        result.append((value, language))
    return result


def tokenize(text, language, vocabulary, barriers):
    """The token ids of a text with the first and last line of each, and its ignore marker problems.

    A region between the markers is replaced by one barrier: an id no other token has, so no
    duplicate block reaches into it or joins the code before it to the code after it.
    """
    ids, firsts, lasts, problems = [], [], [], []
    line, at, opened = 1, 0, None
    for match in SCANNERS[language].finditer(text):
        start, value, kind = match.start(), match.group(), match.lastgroup
        line += text.count('\n', at, start)
        at = start
        if kind == 'comment':
            for marker in MARKER.finditer(value):
                where = line + value.count('\n', 0, marker.start())
                if marker.group(1) == 'start' and opened is not None:
                    problems.append((where, 'duplication:ignore-start inside the ignore block opened at line %d' % opened))
                elif marker.group(1) == 'start':
                    opened = where
                    ids.append(next(barriers))
                    firsts.append(where)
                    lasts.append(where)
                elif opened is None:
                    problems.append((where, 'duplication:ignore-end without a duplication:ignore-start before it'))
                else:
                    opened = None
        elif kind != 'space' and opened is None:
            ids.append(vocabulary.setdefault(value, len(vocabulary) + 1))
            firsts.append(line)
            # A token on one line shares the line's number object: a large file stays small.
            lasts.append(line + value.count('\n') if '\n' in value else line)
    if opened is not None:
        problems.append((opened, 'duplication:ignore-start is never closed by a duplication:ignore-end'))
    return ids, firsts, lasts, problems


def windows(ids, size):
    """(position, hash) of every run of `size` tokens, by a rolling polynomial hash."""
    if len(ids) < size:
        return
    power = pow(_BASE, size - 1, _MOD)
    value = 0
    for token in ids[:size]:
        value = (value * _BASE + token) % _MOD
    yield 0, value
    for position in range(1, len(ids) - size + 1):
        value = ((value - ids[position - 1] * power) * _BASE + ids[position + size - 1]) % _MOD
        yield position, value


def _examine(files, first, i, second, j, floor, min_tokens, min_lines, found):
    """Extend the shared run at (first, i) and (second, j) to its whole block and report it.

    Returns the end of the block in the second file, whether it was reported, and whether it is a
    run that repeats itself: two places in one file whose shared tokens go on past the second
    place's start, cut there so the places do not overlap.
    """
    a, b = files[first][1], files[second][1]
    start_a, start_b = i, j
    while start_a > 0 and start_b > floor and a[start_a - 1] == b[start_b - 1]:
        start_a, start_b = start_a - 1, start_b - 1
    # Two places in one file may not overlap: the block stops where its second place starts.
    limit = start_b if first == second else len(a)
    end_a, end_b = i, j
    while end_a < limit and end_b < len(b) and a[end_a] == b[end_b]:
        end_a, end_b = end_a + 1, end_b + 1
    repeats = end_a > limit or (first == second and end_a == limit and end_b < len(b) and a[end_a] == b[end_b])
    if end_a > limit:
        end_a, end_b = limit, limit + (start_b - start_a)
    count = end_a - start_a
    reported = False
    if count >= min_tokens:
        places = []
        for index, start, end in ((first, start_a, end_a), (second, start_b, end_b)):
            path, _, firsts, lasts = files[index]
            places.append((path, firsts[start], lasts[end - 1]))
        if min(last - first_line + 1 for _, first_line, last in places) >= min_lines:
            found.append((places[0], places[1], count))
            reported = True
    return max(end_b, j + 1), reported, repeats


def duplicates(files, min_tokens, min_lines):
    """Each pair of places sharing at least min_tokens tokens over at least min_lines lines.

    files is a list of (path, ids, first lines, last lines). Each run of min_tokens tokens is
    compared with the places the same run appeared before, the most recent first, until one makes
    a reported pair: three copies make two pairs, and a copy is still named when a nearer place of
    the same tokens spans too few lines. The RECENT most recent places of a run are kept. A pair is
    extended both ways to its whole shared block, and each block is examined once. After a run
    that repeats itself in one file (a table of one short row) and is not reported, the other
    places of that file are passed over for that run; the places in other files are still compared.
    """
    seen, examined, found = {}, {}, []
    for second, (_, b, _, _) in enumerate(files):
        for j, value in windows(b, min_tokens):
            here = second * _STRIDE + j
            earlier = seen.get(value)
            if earlier is None:
                seen[value] = here
                continue
            if type(earlier) is int:
                earlier = seen[value] = [earlier]
            skip_file = None
            for previous in reversed(earlier):
                first, i = divmod(previous, _STRIDE)
                if first == skip_file:
                    continue
                key = (first, second, j - i)
                state = examined.get(key)
                if state is None or j >= state[0]:
                    state = examined[key] = _examine(files, first, i, second, j, state[0] if state else 0,
                                                     min_tokens, min_lines, found)
                if state[1]:
                    break
                if state[2]:
                    skip_file = second
            earlier.append(here)
            if len(earlier) > RECENT:
                del earlier[0]
    return sorted(found)


def check(root, config):
    """The pairs, the ignore marker problems, the number of files read and the files not read."""
    vocabulary, barriers, files, problems, skipped = {}, itertools.count(-1, -1), [], [], []
    for value, language in candidates(root, config):
        path = root / value
        size = path.stat().st_size
        if size > config['max_file_bytes']:
            skipped.append((value, '%d bytes, over max_file_bytes %d (a large generated file belongs in exclude)'
                            % (size, config['max_file_bytes'])))
            continue
        data = path.read_bytes()
        if b'\0' in data[:BINARY_PROBE]:
            skipped.append((value, 'binary (a NUL byte in its first %d bytes)' % BINARY_PROBE))
            continue
        text = data.decode('utf-8', 'replace').replace('\r\n', '\n')
        ids, firsts, lasts, found = tokenize(text, language, vocabulary, barriers)
        files.append((value, ids, firsts, lasts))
        problems.extend((value, line, message) for line, message in found)
    return duplicates(files, config['min_tokens'], config['min_lines']), problems, len(files), skipped


def plural(count, word):
    return '%d %s%s' % (count, word, '' if count == 1 else 's')


def notices(skipped):
    for path, reason in skipped:
        print('  not read: %s: %s' % (path, reason))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--root', type=Path, default=Path.cwd(), help='the repository (default: the working directory)')
    parser.add_argument('--config', default='jpdev.json', help='the declaration, relative to the root (default: jpdev.json)')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        path = root / args.config
        if not path.is_file():
            print('duplication: off: there is no %s (a repository opts in with its thresholds)' % args.config)
            return 0
        try:
            declaration = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise Refused('%s cannot be read as JSON: %s' % (args.config, error))
        config = settings(declaration, args.config)
        if config is None:
            print('duplication: off: %s declares no duplication member (a repository opts in with its thresholds)'
                  % args.config)
            return 0
        try:
            pairs, problems, count, skipped = check(root, config)
        except MemoryError:
            raise Refused('out of memory reading the files in scope; put large generated files in exclude or '
                          'lower max_file_bytes')
    except (Refused, OSError, subprocess.SubprocessError) as error:
        print('duplication: refused: %s' % error, file=sys.stderr)
        return 2
    scope = 'at least %s over at least %s, %s of %s%s' % (
        plural(config['min_tokens'], 'token'), plural(config['min_lines'], 'line'), plural(count, 'file'),
        ', '.join(config['languages']), '; %s not read' % plural(len(skipped), 'file') if skipped else '')
    if not pairs and not problems:
        print('duplication: no duplicate block (%s)' % scope)
        notices(skipped)
        return 0
    if pairs:
        print('duplication: %s (%s)' % (plural(len(pairs), 'duplicate pair'), scope))
        for (path_a, first_a, last_a), (path_b, first_b, last_b), tokens in pairs:
            print('  %s:%d-%d and %s:%d-%d: %d tokens' % (path_a, first_a, last_a, path_b, first_b, last_b, tokens))
    if problems:
        print('duplication: %s' % plural(len(problems), 'ignore marker problem'))
        for path, line, message in sorted(problems):
            print('  %s:%d: %s' % (path, line, message))
    notices(skipped)
    return 1


if __name__ == '__main__':
    sys.exit(main())
