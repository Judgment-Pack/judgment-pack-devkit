# Checked-in generated documents

`dev.json` remains the check runner manifest. `jpdev.json` version1 declares generators; it is
not another check runner or an alias for `dev.json`. Copy `lib/generated_docs.py` to
`scripts/dev/generated_docs.py` when adopting this check. The checker uses Python's standard
library and validates the complete declaration before running repository-owned build commands.
`templates/jpdev.schema.json` documents the same shape; the checker also rejects duplicate names,
escaping, symlinked, ambiguous and overlapping output paths without requiring a schema package.

```json
{
  "version": 1,
  "generators": [
    {
      "name": "reference",
      "run": "node scripts/gen-reference.mjs",
      "outputs": ["docs/reference.md"],
      "timeout": 120,
      "dependencies": ["node_modules"]
    }
  ]
}
```

Each output is an explicit repository-relative regular file, with no empty, `.` or `..`
segment. Declare every output file individually; directories/globs are unsupported. The optional
`timeout` is an integer1–3600 seconds (default120). The optional `dependencies` list contains
explicit existing `node_modules` directories only, such as `node_modules` or
`packages/example/node_modules`. Omit it when the generator needs no installed npm dependencies.
The example command/output must be adjusted to the repository's actual generator.

Add the ordinary `dev.json` check (and keep the generator's useful existing coverage):

```json
{"name":"generated-docs","run":"python3 scripts/dev/generated_docs.py","toolchain":"shell","summary":"^generated-docs:","timeout":300}
```

Choose the toolchain needed by the generator, such as `go` when it resolves a Go package closure.
Run `python3 scripts/dev/generated_docs.py` from the repository root, or specify `--root` and an
optional repository-relative `--config`. It lists tracked and nonignored untracked candidate
files through Git, copies those regular files into a fresh temporary source tree per generator,
removes that copy's declared outputs, executes the command there and compares only the declared
outputs against the candidate. It never regenerates over the candidate to compare it. Missing
checked-in or regenerated outputs fail, as do different bytes; diagnostics name the file and
regeneration command. Command failures retain ordinary exit statuses and bounded log diagnostics;
timeouts stop the process group. Only the checker-created temporary directory is removed.

Put `TMPDIR` beneath session scratch. The checker refuses a symlinked temporary base. It excludes
Git metadata, installed dependency trees, virtual environments, common cache directories,
credential directories and environment secret files before source copying. A source symlink is
unsupported; it never recursively follows an external source target. `JPDEV_SCRATCH` inside the
source root is excluded as well. Gitignored required generator inputs must be declared installed
dependencies or made explicit repository source; do not silently depend on local caches as source.

Explicit `node_modules` trees are linked for reads rather than copied; this supports generators
that import installed build dependencies without copying caches, credentials or external trees.
Declared outputs may not lie in those trees and every output ancestor is checked for symlinks
before removal and after execution. A generator must not install dependencies, run package
lifecycle scripts, clean shared state, or modify a linked dependency/candidate root. These are
trusted repository build commands, not an operating-system sandbox: linking does not prevent
arbitrary command code from writing elsewhere. Use dependency installation during normal setup,
then use read-only dependency resolution during generation.

The checker does not claim live-service evidence, advisory clearance or automatic selection of
other checks. Existing deterministic checks and release/CI gates still apply.
