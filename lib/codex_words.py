#!/usr/bin/env python3
"""codex_words.py BRIEF WORDFILE...: list the words of the word files that the brief contains.

A word file holds one entry per line: TERM or TERM => the neutral phrasing to use instead.
Lines that start with # and blank lines are ignored. A TERM matches case-insensitively at the
start of a word, with any letters after it, and a TERM of several words matches across any run
of whitespace and hyphens (so a term wrapped over two lines, or written with hyphens, is found;
the line reported is the line the match starts on). Evasion inside a single word (a letter
replaced or inserted) is out of scope: this is a vocabulary check, not a filter. Text inside a
paired run of backticks is an identifier, path or command and is not checked. A word file that
does not exist is skipped (the config may extend the list).
Prints one line per hit and exits 1 when there is any, 0 when the brief is clean, 2 on a
usage or read error.
"""
import os
import re
import sys

GENERIC = "describe the input and the documented refusal instead"


def load(path):
    entries = []
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            term, _, suggestion = line.partition("=>")
            term = " ".join(term.split())
            if term:
                entries.append((term, suggestion.strip() or GENERIC))
    return entries


def blank(text):
    """Blank text while preserving line boundaries and offsets."""
    return re.sub(r"[^\n]", " ", text)


def mask_inline_backticks(line):
    """Blank paired inline spans, or return the whole line unchanged if unbalanced."""
    runs = list(re.finditer(r"`+", line))
    spans = []
    index = 0
    while index < len(runs):
        opener = runs[index]
        for closing in range(index + 1, len(runs)):
            if len(runs[closing].group(0)) == len(opener.group(0)):
                spans.append((opener.start(), runs[closing].end()))
                index = closing + 1
                break
        else:
            return line
    chars = list(line)
    for start, end in spans:
        chars[start:end] = blank(line[start:end])
    return "".join(chars)


def mask_backticks(text):
    """Blank balanced inline spans and fenced blocks, preserving unbalanced text."""
    lines = text.splitlines(keepends=True)
    masked = []
    index = 0
    while index < len(lines):
        body = lines[index].rstrip("\r\n")
        opened = re.fullmatch(r"[ \t]{0,3}(`{3,})[^`]*", body)
        if not opened:
            masked.append(mask_inline_backticks(lines[index]))
            index += 1
            continue
        width = len(opened.group(1))
        closing = index + 1
        while closing < len(lines):
            candidate = lines[closing].rstrip("\r\n")
            if re.fullmatch(r"[ \t]{0,3}`{%d,}[ \t]*" % width, candidate):
                break
            closing += 1
        if closing == len(lines):
            masked.extend(lines[index:])
            break
        masked.extend(blank(line) for line in lines[index:closing + 1])
        index = closing + 1
    return "".join(masked)


def main(argv):
    if len(argv) < 3:
        print("usage: codex_words.py BRIEF WORDFILE...", file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
        entries = []
        for path in argv[2:]:
            if os.path.isfile(path):
                entries.extend(load(path))
    except OSError as err:
        print("codex_words.py: %s" % err, file=sys.stderr)
        return 2
    text = mask_backticks("\n".join(lines))
    hits = 0
    for term, suggestion in entries:
        words = [re.escape(part) for part in term.split()]
        pattern = re.compile(r"(?<![A-Za-z0-9])" + r"[\s-]+".join(words) + r"[A-Za-z]*", re.IGNORECASE)
        for found in pattern.finditer(text):
            hits += 1
            number = text.count("\n", 0, found.start()) + 1
            print('line %d: "%s": %s' % (number, " ".join(found.group(0).split()), suggestion))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
