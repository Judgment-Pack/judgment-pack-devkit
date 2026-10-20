#!/usr/bin/env python3
"""mutants_report.py ROW... < output

Reads the table a mutation run printed (`| row | file | result |`, the result starting with a
verdict and a colon) and prints, for each table row whose name contains one of the ROW texts,
`caught`, `retired` or `NOT CAUGHT (verdict)`, then a line of counts. A ROW text no table row contains is
reported as `no row matched`. Exit status = rows not caught plus texts that matched nothing.
"""
import sys


def main():
    texts = sys.argv[1:]
    seen = {text: 0 for text in texts}
    caught = missed = retired = 0
    for line in sys.stdin:
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] in ("row", "---"):
            continue
        name, result = cells[0], cells[-1]
        matched = [t for t in texts if t in name]
        if not matched:
            continue
        for text in matched:
            seen[text] += 1
        verdict = result.split(":", 1)[0].strip()
        if verdict == "retired":
            retired += 1
            print("retired       %s" % name)
        elif verdict == "caught":
            caught += 1
            print("caught        %s" % name)
        else:
            missed += 1
            print("NOT CAUGHT    %s (%s)" % (name, verdict))
    absent = [t for t, n in seen.items() if n == 0]
    for text in absent:
        print("no row matched: %s" % text)
    print("%d caught, %d not caught, %d retired, %d texts matched no row" % (caught, missed, retired, len(absent)))
    return missed + len(absent)


if __name__ == "__main__":
    sys.exit(min(main(), 255))
