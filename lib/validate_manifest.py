#!/usr/bin/env python3
"""validate_manifest.py MANIFEST SCHEMA

Checks a dev.json against its JSON Schema when the jsonschema package is installed (it says
which check ran), and always makes the checks the schema cannot: step names are unique, a node
step has a node version to run under. The go version is also held to a release number here,
because the fallback without the jsonschema package has no schema. Standard library otherwise. Exit 0 when valid, 1 with one line per problem, 2 on an unreadable file.
"""
import json
import os
import re
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
            if "notes" in manifest:
                notes = manifest["notes"]
                if not isinstance(notes, list):
                    problems.append("notes: not an array")
                else:
                    for index, note in enumerate(notes):
                        if not isinstance(note, str) or not note or len(note) > 240:
                            problems.append("notes/%d: must be a non-empty string of at most 240 characters" % index)
            for kind in ("setup", "checks"):
                for index, step in enumerate(manifest.get(kind, [])):
                    if not isinstance(step, dict) or not step.get("name") or not step.get("run"):
                        problems.append("%s/%d: a step needs a name and a run" % (kind, index))
            if "handover" in manifest:
                handover = manifest["handover"]
                if not isinstance(handover, dict):
                    problems.append("handover: not an object")
                else:
                    for key in handover:
                        if key not in ("boundary_paths", "shared_paths", "schema_probe"):
                            problems.append("handover: unknown member %r" % key)
                    if "schema_probe" in handover and (not isinstance(handover["schema_probe"], str) or not handover["schema_probe"]):
                        problems.append("handover/schema_probe: must be a non-empty string")
                    for key in ("boundary_paths", "shared_paths"):
                        if key not in handover:
                            continue
                        paths = handover[key]
                        if not isinstance(paths, list):
                            problems.append("handover/%s: not an array" % key)
                        else:
                            for index, path in enumerate(paths):
                                if not isinstance(path, str) or not path:
                                    problems.append("handover/%s/%d: must be a non-empty string" % (key, index))
    if isinstance(manifest, dict):
        steps = [s for k in ("setup", "checks") for s in manifest.get(k, []) if isinstance(s, dict)]
        if isinstance(manifest.get("parity"), dict):
            steps.append(dict(manifest["parity"], name="parity"))
        go_version = manifest.get("toolchains", {}).get("go", {}).get("version") if isinstance(manifest.get("toolchains"), dict) and isinstance(manifest["toolchains"].get("go"), dict) else None
        if go_version is not None and not (isinstance(go_version, str) and re.fullmatch(r"[0-9]+\.[0-9]+(\.[0-9]+)?", go_version)):
            problems.append("toolchains/go/version: %r is not a Go release number such as 1.26 or 1.26.5" % (go_version,))
        python = manifest.get("toolchains", {}).get("python", {}) if isinstance(manifest.get("toolchains"), dict) else {}
        venv = python.get("venv") if isinstance(python, dict) else None
        if venv is not None and (not isinstance(venv, str) or not venv or os.path.isabs(venv)
                                 or ".." in venv.split("/") or os.path.normpath(venv) == "."):
            problems.append("toolchains/python/venv: venv must be a relative child path of the clone")
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
