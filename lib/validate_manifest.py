#!/usr/bin/env python3
"""validate_manifest.py MANIFEST SCHEMA

Checks a dev.json against its JSON Schema when the jsonschema package is installed (it says
which check ran), and always makes the checks the schema cannot: step names are unique, a node
step has a node version to run under, a setup step's name is not a check's. Standard library
otherwise. Exit 0 when valid, 1 with one line per problem, 2 on an unreadable file.
"""
import json
import sys


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        with open(sys.argv[1], encoding="utf-8") as handle:
            manifest = json.load(handle)
        with open(sys.argv[2], encoding="utf-8") as handle:
            schema = json.load(handle)
    except (OSError, ValueError) as error:
        print("validate_manifest: cannot read: %s" % error, file=sys.stderr)
        return 2
    problems = []
    mode = "structure only"
    try:
        import jsonschema
        mode = "json schema"
        validator = jsonschema.Draft202012Validator(schema)
        for error in sorted(validator.iter_errors(manifest), key=lambda e: list(map(str, e.path))):
            where = "/".join(str(p) for p in error.path) or "(root)"
            problems.append("%s: %s" % (where, error.message))
    except ImportError:
        if not isinstance(manifest, dict):
            problems.append("(root): not an object")
        else:
            for key in ("version", "checks"):
                if key not in manifest:
                    problems.append("(root): %r is required" % key)
            if manifest.get("version") != 1:
                problems.append("version: must be 1")
            for kind in ("setup", "checks"):
                for index, step in enumerate(manifest.get(kind, [])):
                    if not isinstance(step, dict) or not step.get("name") or not step.get("run"):
                        problems.append("%s/%d: a step needs a name and a run" % (kind, index))
    if isinstance(manifest, dict):
        steps = [s for k in ("setup", "checks") for s in manifest.get(k, []) if isinstance(s, dict)]
        if isinstance(manifest.get("parity"), dict):
            steps.append(dict(manifest["parity"], name="parity"))
        seen = set()
        for step in steps:
            name = step.get("name")
            if name in seen:
                problems.append("step name %r is used twice" % name)
            seen.add(name)
            toolchain = step.get("toolchain", "shell")
            if toolchain in ("node", "go", "python") and toolchain not in manifest.get("toolchains", {}):
                problems.append("step %r uses toolchain %r, which toolchains does not declare" % (name, toolchain))
    for problem in problems:
        print("dev.json: " + problem)
    print("validate_manifest: %s, %s" % (mode, "%d problems" % len(problems) if problems else "valid"), file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
