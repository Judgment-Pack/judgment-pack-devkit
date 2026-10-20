#!/usr/bin/env bash
# tests/run.sh: the kit's own tests. No network, no node; needs git, python3, rsync, flock and go.
set -u
kit=$(cd "$(dirname "$0")/.." && pwd)
cd "$kit" || exit 2
work=$(mktemp -d)
trap 'rm -rf -- "${work:?}"' EXIT
export JPDEV_SCRATCH=$work/scratch XDG_CONFIG_HOME=$work/config HOME=$work/home
mkdir -p "$HOME" "$XDG_CONFIG_HOME"
unset CI JPDEV_VENV JPDEV_LOCK JPDEV_NODE_RSS_MB JPDEV_NODE_TIMEOUT_S JPDEV_GO_ULIMIT_KB JPDEV_GO_TIMEOUT_S JPDEV_PY_ULIMIT_KB JPDEV_NVM_DIR JPDEV_GO_SDK_DIR JPDEV_NAME_PATTERNS JPDEV_FIXTURE_UNSET
# What jpdev check exports to its steps: a run of these tests under it must not inherit it.
unset JPDEV_ROOT JPDEV_WRAP JPDEV_NODE_BIN JPDEV_GO_BIN JPDEV_LOGDIR JPDEV_STEP_TIMEOUT
jpdev=$kit/bin/jpdev
fixture=$kit/tests/fixture/dev.json
pass=0 fail=0

ok() { pass=$((pass + 1)); printf 'ok    %s\n' "$1"; }
bad() { fail=$((fail + 1)); printf 'FAIL  %s\n' "$1"; [ -z "${2:-}" ] || printf '%s\n' "$2" | head -n 20 | sed 's/^/      /'; }
# expect NAME STATUS PATTERN OUTPUT STATUS-GOT
expect() {
  local name=$1 want=$2 pattern=$3 out=$4 got=$5
  if [ "$got" -ne "$want" ]; then bad "$name (exit $got, wanted $want)" "$out"
  elif [ -n "$pattern" ] && ! grep -qE -- "$pattern" <<< "$out"; then bad "$name (no line matching: $pattern)" "$out"
  else ok "$name"; fi
}
absent() {
  if grep -qE -- "$2" <<< "$3"; then bad "$1 (unexpected line matching: $2)" "$3"; else ok "$1"; fi
}

# --- the public runner, with no caps
out=$("$kit/templates/check.sh" --manifest "$fixture" 2>/dev/null) && s=0 || s=$?
# JPDEV_ROOT is unset: the template's own location is the kit, whose git root is this repository.
expect "check.sh stops at the first failure and exits with the failure count" 1 'FAIL +fails ' "$out" "$s"
expect "check.sh marks what did not run" 1 'NOT RUN +after-failure' "$out" "$s"
expect "check.sh prints a matching count line" 1 'Tests 3 passed' "$out" "$s"
expect "check.sh abbreviates more than three matching lines" 1 '4 lines matched; last: ok d' "$out" "$s"
expect "check.sh skips an optional step whose variable is unset" 1 'SKIP +optional-skip' "$out" "$s"
expect "check.sh skips a step whose variable is unset and says why" 1 'SKIP +needs-variable +needs JPDEV_FIXTURE_UNSET' "$out" "$s"
expect "check.sh prints the first 40 lines of a failure and says how many more" 1 '\.\.\. 10 more lines' "$out" "$s"
absent "check.sh prints no 41st line of a failure" 'output line 41$' "$out"
expect "check.sh prints the totals" 1 '== 5 passed, 1 failed, 2 skipped, 1 not run ==' "$out" "$s"
out=$("$kit/templates/check.sh" --manifest "$fixture" --all 2>/dev/null) && s=0 || s=$?
expect "check.sh --all runs past a failure" 1 'PASS +after-failure' "$out" "$s"
out=$("$kit/templates/check.sh" --manifest "$fixture" --only first,python-version 2>/dev/null) && s=0 || s=$?
expect "check.sh --only runs the named checks and exits 0" 0 '== 2 passed, 0 failed, 0 skipped, 0 not run ==' "$out" "$s"
out=$("$kit/templates/check.sh" --manifest "$fixture" --skip fails,after-failure,needs-variable 2>/dev/null) && s=0 || s=$?
expect "check.sh --skip leaves the rest" 0 '== 5 passed' "$out" "$s"
out=$(JPDEV_FIXTURE_UNSET=1 "$kit/templates/check.sh" --manifest "$fixture" --only needs-variable 2>/dev/null) && s=0 || s=$?
expect "check.sh runs a step whose variable is set" 0 'PASS +needs-variable' "$out" "$s"
out=$("$kit/templates/check.sh" --manifest "$fixture" --setup 2>/dev/null) && s=0 || s=$?
expect "check.sh --setup runs the setup steps" 0 'PASS +prepare' "$out" "$s"
out=$(CI=true "$kit/templates/check.sh" --manifest "$fixture" --only needs-variable 2>/dev/null) && s=0 || s=$?
expect "under CI a skipped step is a failure" 1 'FAIL +needs-variable +needs JPDEV_FIXTURE_UNSET, which CI must set' "$out" "$s"
out=$(CI=true "$kit/templates/check.sh" --manifest "$fixture" --only optional-skip 2>/dev/null) && s=0 || s=$?
expect "under CI a step marked optional may still be skipped" 0 'SKIP +optional-skip' "$out" "$s"
out=$("$kit/templates/check.sh" --manifest "$fixture" --only first,nosuchcheck 2>&1) && s=0 || s=$?
expect "check.sh --only with an unknown name fails and names it" 2 'no step named nosuchcheck' "$out" "$s"
out=$("$kit/templates/check.sh" --manifest "$fixture" --skip nosuchcheck 2>&1) && s=0 || s=$?
expect "check.sh --skip with an unknown name fails and names it" 2 'no step named nosuchcheck' "$out" "$s"
slow=$work/slow.json
cat > "$slow" <<'JSON'
{"version": 1, "checks": [{"name": "slow", "run": "sleep 30", "timeout": 1}]}
JSON
out=$("$kit/templates/check.sh" --manifest "$slow" 2>/dev/null) && s=0 || s=$?
expect "check.sh stops a check that passes its timeout" 1 'check: stopped for time' "$out" "$s"

# the two runners agree on a step that passes its timeout
cat > "$work/shell-slow.json" <<'JSON'
{"version": 1, "checks": [{"name": "slow", "run": "sleep 6", "toolchain": "shell", "timeout": 1}]}
JSON
SECONDS=0
out=$("$kit/templates/check.sh" --manifest "$work/shell-slow.json" 2>/dev/null) && s=0 || s=$?
expect "check.sh fails a shell step that passes its timeout" 1 'FAIL +slow' "$out" "$s"
if [ "$SECONDS" -lt 5 ]; then ok "check.sh stops the step at its timeout"; else bad "check.sh stops the step at its timeout (took ${SECONDS}s)"; fi
SECONDS=0
out=$("$jpdev" check --manifest "$work/shell-slow.json" 2>/dev/null) && s=0 || s=$?
expect "jpdev check fails a shell step that passes its timeout, as check.sh does" 1 'FAIL +slow' "$out" "$s"
if [ "$SECONDS" -lt 5 ]; then ok "jpdev check stops the step at its timeout"; else bad "jpdev check stops the step at its timeout (took ${SECONDS}s)"; fi

# --- jpdev check, with the caps
out=$("$jpdev" check --manifest "$fixture" --all 2>"$work/err") && s=0 || s=$?
expect "jpdev check runs the go and python steps under their caps" 1 'PASS +go-version' "$out" "$s"
expect "jpdev check names the failure" 1 'FAIL +fails ' "$out" "$s"
if grep -q 'go version go' <<< "$out" && grep -q 'Python 3' <<< "$out"; then ok "jpdev check prints the counts the checks printed"; else bad "jpdev check prints the counts the checks printed" "$out"; fi
out=$("$jpdev" check --manifest "$fixture" --skip fails,after-failure,needs-variable 2>/dev/null) && s=0 || s=$?
expect "jpdev check exits 0 when every check passes" 0 '== 5 passed' "$out" "$s"
out=$(JPDEV_GO_ULIMIT_KB=1000 "$jpdev" check --manifest "$fixture" --only go-version 2>/dev/null) && s=0 || s=$?
expect "jpdev check applies the Go address-space cap (a 1 MB cap fails the step)" 1 'FAIL +go-version' "$out" "$s"
out=$("$jpdev" check --manifest "$fixture" --only go-env 2>/dev/null) && s=0 || s=$?
expect "jpdev check runs a Go step" 0 'PASS +go-env' "$out" "$s"
golog=$(cat "$JPDEV_SCRATCH"/logs/*/go-env.log 2>/dev/null)
expect "a Go step runs with GOFLAGS=-mod=mod" 0 '^-mod=mod$' "$golog" 0
expect "a Go step runs with a per-clone cache under the scratch directory" 0 "^$JPDEV_SCRATCH/gocache/" "$golog" 0

# --- the node cap
"$kit/lib/rsscap.sh" 6000 1 -- sleep 5 2>/dev/null; s=$?
expect "rsscap stops a run that passes its time limit with 124" 124 "" "" "$s"
"$kit/lib/rsscap.sh" 20 10 -- python3 -c 'import time; x = bytearray(200_000_000); time.sleep(5)' 2>/dev/null; s=$?
expect "rsscap stops a run that passes its memory limit with 137" 137 "" "" "$s"
"$kit/lib/rsscap.sh" 6000 10 -- bash -c 'exit 7' 2>/dev/null; s=$?
expect "rsscap passes the command's own status through" 7 "" "" "$s"

# wrap.sh node: the resident-memory cap stops a step and the runner reports it
if command -v node > /dev/null; then
  JPDEV_NODE_RSS_MB=150 "$kit/lib/wrap.sh" node -- node -e 'const b = Buffer.alloc(400e6, 1); setTimeout(() => b.length, 8000)' > /dev/null 2>&1; s=$?
  expect "wrap.sh node stops a step over the memory cap with 137" 137 "" "" "$s"
  JPDEV_NODE_RSS_MB=2000 "$kit/lib/wrap.sh" node -- node -e '1' > /dev/null 2>&1; s=$?
  expect "wrap.sh node lets a step under the cap finish" 0 "" "" "$s"
  cat > "$work/node-cap.json" <<'JSON'
{"version": 1, "checks": [{"name": "greedy", "run": "node -e 'const b = Buffer.alloc(400e6, 1); setTimeout(() => b.length, 8000)'", "toolchain": "node"}]}
JSON
  out=$(JPDEV_WRAP=$kit/lib/wrap.sh JPDEV_NODE_RSS_MB=150 "$kit/templates/check.sh" --manifest "$work/node-cap.json" 2>/dev/null) && s=0 || s=$?
  expect "a node step stopped for memory is reported as a failure with exit 137" 1 'FAIL +greedy +.*exit 137' "$out" "$s"
  expect "the report says it was the memory cap" 1 'STOPPED for memory' "$out" "$s"
else
  ok "wrap.sh node (skipped: node is not on PATH)"
fi
# wrap.sh python: the address-space cap, the timeout and the manifest's virtual environment
out=$(JPDEV_PY_ULIMIT_KB=1234567 "$kit/lib/wrap.sh" python -- bash -c 'ulimit -v' 2>&1); s=$?
expect "wrap.sh python applies ulimit -v from JPDEV_PY_ULIMIT_KB" 0 '^1234567$' "$out" "$s"
JPDEV_STEP_TIMEOUT=1 "$kit/lib/wrap.sh" python -- sleep 5 > /dev/null 2>&1; s=$?
expect "wrap.sh python stops a step at its timeout with 124" 124 "" "" "$s"
vclone=$work/vclone
mkdir -p "$vclone/myvenv/bin"
printf '#!/bin/sh\necho from-the-venv\n' > "$vclone/myvenv/bin/python3"
chmod +x "$vclone/myvenv/bin/python3"
git init -q -b main "$vclone"
cat > "$vclone/dev.json" <<'JSON'
{"version": 1, "toolchains": {"python": {"venv": "myvenv"}}, "checks": [{"name": "which", "run": "python3", "toolchain": "python", "summary": "venv"}]}
JSON
out=$(cd "$vclone" && "$jpdev" check 2>/dev/null) && s=0 || s=$?
expect "the python step runs in the virtual environment the manifest names" 0 'from-the-venv' "$out" "$s"

# the virtual environment is first on PATH for every step, whatever its toolchain
pyclone=$work/pyclone
git init -q -b main "$pyclone"
python3 -m venv --without-pip "$pyclone/pyvenv"
purelib=$("$pyclone/pyvenv/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
printf 'WHERE = "in-the-venv"\n' > "$purelib/jpdev_venv_marker.py"
mkdir -p "$work/nvm/versions/node/v99.0.0/bin"
printf '#!/bin/sh\necho v99.0.0\n' > "$work/nvm/versions/node/v99.0.0/bin/node"
chmod +x "$work/nvm/versions/node/v99.0.0/bin/node"
cat > "$pyclone/dev.json" <<'JSON'
{"version": 1,
 "toolchains": {"node": {"version": "99"}, "go": {}, "python": {"venv": "pyvenv"}},
 "checks": [
  {"name": "node-step", "run": "python3 -c 'import jpdev_venv_marker as m; print(\"node:\", m.WHERE)'", "toolchain": "node", "summary": "^node:"},
  {"name": "go-step", "run": "python3 -c 'import jpdev_venv_marker as m; print(\"go:\", m.WHERE)'", "toolchain": "go", "summary": "^go:"},
  {"name": "shell-step", "run": "python3 -c 'import jpdev_venv_marker as m; print(\"shell:\", m.WHERE)'", "toolchain": "shell", "summary": "^shell:"},
  {"name": "python-step", "run": "python3 -c 'import jpdev_venv_marker as m; print(\"python:\", m.WHERE)'", "toolchain": "python", "summary": "^python:"}]}
JSON
out=$(cd "$pyclone" && JPDEV_NVM_DIR=$work/nvm "$jpdev" check --all 2>/dev/null) && s=0 || s=$?
expect "a node step imports a module installed in the manifest's virtual environment" 0 'node: in-the-venv' "$out" "$s"
expect "a go step imports a module installed in the manifest's virtual environment" 0 'go: in-the-venv' "$out" "$s"
expect "a shell step imports a module installed in the manifest's virtual environment" 0 'shell: in-the-venv' "$out" "$s"
expect "a python step imports a module installed in the manifest's virtual environment" 0 'python: in-the-venv' "$out" "$s"
expect "the four steps pass" 0 '== 4 passed, 0 failed' "$out" "$s"
# with no virtual environment declared, no step finds the module
sed 's/, "python": {"venv": "pyvenv"}//' "$pyclone/dev.json" | sed 's/"toolchain": "python"/"toolchain": "shell"/' > "$pyclone/novenv.json"
out=$(cd "$pyclone" && JPDEV_NVM_DIR=$work/nvm "$jpdev" check --all --manifest "$pyclone/novenv.json" 2>/dev/null) && s=0 || s=$?
expect "with no virtual environment declared the module is not found, in any step" 4 '== 0 passed, 4 failed' "$out" "$s"

# --- the Go release the manifest names (toolchains.go.version)
# The stubs are releases no real Go has, so a match on the go installed here cannot pass for them.
mkdir -p "$work/sdk/go1.77.5/bin" "$work/sdk/go1.76.9/bin"
for rel in 1.77.5 1.76.9; do
  cat > "$work/sdk/go$rel/bin/go" <<'STUB'
#!/bin/sh
[ "$1" = version ] && echo "go version goRELEASE linux/amd64"
exit 0
STUB
  sed -i "s/RELEASE/$rel/" "$work/sdk/go$rel/bin/go"
  chmod +x "$work/sdk/go$rel/bin/go"
done
goclone=$work/goclone
mkdir -p "$goclone"
git init -q -b main "$goclone"
for want in 1.77.5 1.77 1.76; do
  cat > "$goclone/dev.json" <<JSON
{"version": 1, "toolchains": {"go": {"version": "$want"}}, "checks": [{"name": "which-go", "run": "go version", "toolchain": "go", "summary": "^go version"}]}
JSON
  out=$(cd "$goclone" && JPDEV_GO_SDK_DIR=$work/sdk "$jpdev" check 2>&1) && s=0 || s=$?
  case $want in 1.76) rel=1.76.9 ;; *) rel=1.77.5 ;; esac
  expect "jpdev check selects an installed Go that matches go.version $want" 0 "go version go$rel linux/amd64" "$out" "$s"
done
cat > "$goclone/dev.json" <<'JSON'
{"version": 1, "toolchains": {"go": {"version": "1.7"}}, "checks": [{"name": "which-go", "run": "go version", "toolchain": "go", "summary": "^go version"}]}
JSON
# a go on PATH is one candidate too: 1.7 is not a prefix of 1.77 to it either
mkdir -p "$work/pathgo"
cp "$work/sdk/go1.77.5/bin/go" "$work/pathgo/go"
out=$(cd "$goclone" && PATH=$work/pathgo:$PATH JPDEV_GO_SDK_DIR=$work/none "$jpdev" check 2>&1) && s=0 || s=$?
expect "go.version 1.7 does not match a go1.77.5 on PATH" 0 'the manifest names go 1\.7 and no matching Go is installed' "$out" "$s"
sed -i 's/"1\.7"/"1.77"/' "$goclone/dev.json"
out=$(cd "$goclone" && PATH=$work/pathgo:$PATH JPDEV_GO_SDK_DIR=$work/none "$jpdev" check 2>&1) && s=0 || s=$?
expect "go.version 1.77 matches a go1.77.5 on PATH" 0 'go version go1\.77\.5 linux/amd64' "$out" "$s"
absent "go.version 1.77 on PATH needs no warning" 'no matching Go is installed' "$out"
sed -i 's/"1\.77"/"1.7"/' "$goclone/dev.json"
out=$(cd "$goclone" && JPDEV_GO_SDK_DIR=$work/sdk "$jpdev" check 2>&1) && s=0 || s=$?
expect "go.version 1.7 does not match go1.76 or go1.77" 0 'the manifest names go 1\.7 and no matching Go is installed' "$out" "$s"
absent "go.version 1.7 selects no stub" 'go version go1\.7[67]\.' "$out"
cat > "$goclone/dev.json" <<'JSON'
{"version": 1, "toolchains": {"go": {"version": "1.99.0"}}, "checks": [{"name": "which-go", "run": "go version", "toolchain": "go", "summary": "^go version"}]}
JSON
out=$(cd "$goclone" && JPDEV_GO_SDK_DIR=$work/sdk "$jpdev" check 2>&1) && s=0 || s=$?
expect "jpdev check says so when no installed Go matches go.version, and runs the go on PATH" 0 'the manifest names go 1\.99\.0 and no matching Go is installed' "$out" "$s"
expect "the go steps still run when no Go matches" 0 'PASS +which-go' "$out" "$s"
absent "no stub Go is used when none matches" 'go version go1\.7[67]\.' "$out"
git -C "$goclone" add dev.json
git -C "$goclone" -c user.name=test -c user.email=test@example.com commit -q -m go
git init -q --bare -b main "$work/goorigin.git"
git -C "$goclone" remote add origin "$work/goorigin.git"
git -C "$goclone" push -q origin main
out=$(JPDEV_GO_SDK_DIR=$work/sdk "$jpdev" setup "$goclone" 2>&1) && s=0 || s=$?
expect "setup says no matching Go is installed" 0 'go +go version .*\(the manifest names go 1\.99\.0 and no matching Go is installed: this one is used\)' "$out" "$s"
sed -i 's/1\.99\.0/1.77.5/' "$goclone/dev.json"
out=$(JPDEV_GO_SDK_DIR=$work/sdk "$jpdev" setup "$goclone" 2>&1) && s=0 || s=$?
expect "setup says which Go it selected" 0 "go +go version go1\.77\.5 linux/amd64 \\(selected for the manifest's go 1\.77\.5\\)" "$out" "$s"
printf '{"version": 1, "toolchains": {"go": {"version": "latest"}}, "checks": [{"name": "a", "run": "true"}]}\n' > "$work/badgo.json"
out=$(python3 "$kit/lib/validate_manifest.py" "$work/badgo.json" "$kit/templates/dev.schema.json" 2>&1) && s=0 || s=$?
expect "the schema refuses a Go version that is not a release number" 1 "dev.json:" "$out" "$s"

# --- the runner template records the kit version it came from
line2=$(sed -n 2p "$kit/templates/check.sh")
want="# from judgment-pack-devkit v$("$jpdev" --version | awk '{ print $2 }') (templates/check.sh)"
if [ "$line2" = "$want" ]; then ok "templates/check.sh line 2 names the kit version jpdev --version prints"; else bad "templates/check.sh line 2 names the kit version jpdev --version prints" "line 2: $line2
wanted: $want"; fi
if cmp -s "$kit/templates/check.sh" "$kit/scripts/dev/check.sh"; then ok "scripts/dev/check.sh is the template, line 2 included"; else bad "scripts/dev/check.sh is the template, line 2 included"; fi

# --- the lock
lock=$work/test.lock
( flock 9; sleep 4 ) 9> "$lock" &
holder=$!
sleep 1
JPDEV_LOCK=$lock timeout 2 "$kit/lib/wrap.sh" go -- echo got-it > "$work/locked.out" 2>&1; s=$?
expect "wrap.sh go waits while another process holds the machine lock" 124 "" "" "$s"
wait "$holder"
out=$(JPDEV_LOCK=$lock timeout 20 "$kit/lib/wrap.sh" go -- echo got-it 2>&1); s=$?
expect "wrap.sh go runs the command once the lock is free" 0 'got-it' "$out" "$s"

# --- the manifest schema
dup=$work/dup.json
cat > "$dup" <<'JSON'
{"version": 1, "checks": [{"name": "a", "run": "true"}, {"name": "a", "run": "true", "toolchain": "node"}]}
JSON
out=$(python3 "$kit/lib/validate_manifest.py" "$dup" "$kit/templates/dev.schema.json" 2>&1) && s=0 || s=$?
expect "the manifest check refuses a repeated step name" 1 "used twice" "$out" "$s"
expect "the manifest check refuses a node step with no node toolchain" 1 "toolchain 'node'" "$out" "$s"
out=$(python3 "$kit/lib/validate_manifest.py" "$kit/templates/dev.json" "$kit/templates/dev.schema.json" 2>&1) && s=0 || s=$?
expect "the template manifest is valid" 0 "valid" "$out" "$s"
out=$(python3 "$kit/lib/validate_manifest.py" "$kit/examples/judgment-pack-agent.dev.json" "$kit/templates/dev.schema.json" 2>&1) && s=0 || s=$?
expect "the agent repository's example manifest is valid" 0 "valid" "$out" "$s"
printf '{"version": 2, "checks": []}\n' > "$work/bad.json"
out=$(python3 "$kit/lib/validate_manifest.py" "$work/bad.json" "$kit/templates/dev.schema.json" 2>&1) && s=0 || s=$?
expect "the manifest check refuses a wrong version" 1 "dev.json:" "$out" "$s"

# --- mutants
out=$("$jpdev" mutants --manifest "$fixture" --row alpha 2>/dev/null) && s=0 || s=$?
expect "jpdev mutants reports a caught row" 0 'caught +alpha is checked' "$out" "$s"
out=$("$jpdev" mutants --manifest "$fixture" --row beta 2>/dev/null) && s=0 || s=$?
expect "jpdev mutants reports a row nothing caught and exits 1" 1 'NOT CAUGHT +beta is checked' "$out" "$s"
out=$("$jpdev" mutants --manifest "$fixture" --row delta 2>/dev/null) && s=0 || s=$?
expect "jpdev mutants reports a text that matches no row" 1 'no row matched: delta' "$out" "$s"
out=$("$jpdev" mutants --manifest "$fixture" --row alpha --row gamma 2>/dev/null) && s=0 || s=$?
expect "jpdev mutants takes several rows and says a row is retired" 0 'retired +gamma is checked' "$out" "$s"
if [ -e "$kit/tests/fixture/.mutated" ]; then bad "jpdev mutants leaves the clone alone"; rm -f "$kit/tests/fixture/.mutated" "$kit/.mutated"; else ok "jpdev mutants leaves the clone alone"; fi
if [ -e "$kit/.mutated" ]; then bad "jpdev mutants ran in the clone itself"; rm -f "$kit/.mutated"; else ok "jpdev mutants ran in a scratch copy"; fi
if ls "$JPDEV_SCRATCH"/mutants/* > /dev/null 2>&1; then bad "jpdev mutants removes its scratch copy"; else ok "jpdev mutants removes its scratch copy"; fi

# --- the record gate
mkdir -p "$work/home" "$XDG_CONFIG_HOME/jpdev"
printf '%s\n' 'unlikely-name-xyz' > "$XDG_CONFIG_HOME/jpdev/name-patterns"
slash=/
clean=$work/clean.md
printf '## Report\nAll rows held.\nlog: %s/logs/run.txt\nhome: %s/notes/x\n' "$JPDEV_SCRATCH" "$HOME" > "$clean"
out=$("$jpdev" record post --pr 7 --file "$clean" --repo Example/repo --dry-run 2>&1) && s=0 || s=$?
expect "record accepts a text whose scratch and home paths reduce" 0 'would post .* on pr #7 of Example/repo' "$out" "$s"
dirty=$work/dirty.md
printf 'see %shome%ssomeone%sproject%sfile.txt for details\n' "$slash" "$slash" "$slash" "$slash" > "$dirty"
out=$("$jpdev" record post --pr 7 --file "$dirty" --repo Example/repo --dry-run 2>&1) && s=0 || s=$?
expect "record refuses a path that remains" 1 'refused: a local path remains' "$out" "$s"
tmpath=$work/tmp.md
printf 'build in %stmp%sbuild-1\n' "$slash" "$slash" > "$tmpath"
out=$("$jpdev" record post --issue 3 --file "$tmpath" --dry-run 2>&1) && s=0 || s=$?
expect "record refuses a temporary-directory path" 1 'refused: a local path remains' "$out" "$s"
printf '%s\n' '# names that must not appear' 'forbidden[- ]name' '' > "$work/patterns"
named=$work/named.md
printf 'thanks to Forbidden Name for the review\n' > "$named"
out=$(JPDEV_NAME_PATTERNS=$work/patterns "$jpdev" record post --pr 7 --file "$named" --dry-run 2>&1) && s=0 || s=$?
expect "record refuses a text that matches a name pattern" 1 'match a pattern of the name list' "$out" "$s"
absent "record does not echo the matched name" 'Forbidden' "$out"
out=$(JPDEV_NAME_PATTERNS=$work/patterns "$jpdev" record post --pr 7 --file "$clean" --dry-run 2>&1) && s=0 || s=$?
expect "record accepts a clean text with a name list present" 0 'would post' "$out" "$s"
out=$(JPDEV_NAME_PATTERNS=$work/absent-patterns "$jpdev" record post --pr 7 --file "$clean" --dry-run 2>&1) && s=0 || s=$?
expect "record refuses to post without a name-pattern file" 1 'refused: no name-pattern file' "$out" "$s"
out=$(JPDEV_NAME_PATTERNS=$work/absent-patterns "$jpdev" record post --pr 7 --file "$clean" --dry-run --no-name-check 2>&1) && s=0 || s=$?
expect "record --no-name-check posts without the file and says so" 0 'did not run' "$out" "$s"
expect "record --no-name-check still posts" 0 'would post' "$out" "$s"
out=$(JPDEV_NAME_PATTERNS=$work/absent-patterns "$jpdev" record post --pr 7 --file "$dirty" --dry-run --no-name-check 2>&1) && s=0 || s=$?
expect "record --no-name-check still refuses a path" 1 'a local path remains' "$out" "$s"
: > "$work/empty-patterns"
out=$(JPDEV_NAME_PATTERNS=$work/empty-patterns "$jpdev" record post --pr 7 --file "$clean" --dry-run 2>&1) && s=0 || s=$?
expect "record warns on a name-pattern file with no pattern" 0 'holds no pattern' "$out" "$s"
printf '%s\n' '# only a comment' '' > "$work/comment-patterns"
out=$(JPDEV_NAME_PATTERNS=$work/comment-patterns "$jpdev" record post --pr 7 --file "$clean" --dry-run 2>&1) && s=0 || s=$?
expect "record warns on a name-pattern file of comments only" 0 'holds no pattern' "$out" "$s"
printf '%s\n' '(unclosed' 'zork quux' > "$work/bad-patterns"
printf 'the Zork Quux review\n' > "$work/zork.md"
out=$(JPDEV_NAME_PATTERNS=$work/bad-patterns "$jpdev" record post --pr 7 --file "$work/zork.md" --dry-run 2>&1) && s=0 || s=$?
expect "record refuses when the name-pattern file holds an invalid regex" 1 'cannot compile' "$out" "$s"
absent "record does not post after an invalid pattern" 'would post' "$out"
# a grep that fails after the patterns compiled (a stub that exits 3 on the matching call) refuses too
mkdir -p "$work/stubbin"
real_grep=$(command -v grep)
printf '#!/bin/sh\ncase "$*" in *-nEif*) exit 3 ;; esac\nexec %s "$@"\n' "$real_grep" > "$work/stubbin/grep"
chmod +x "$work/stubbin/grep"
out=$(PATH=$work/stubbin:$PATH JPDEV_NAME_PATTERNS=$XDG_CONFIG_HOME/jpdev/name-patterns "$jpdev" record post --pr 7 --file "$clean" --dry-run 2>&1) && s=0 || s=$?
expect "record refuses when the name check itself fails" 1 'the name check failed \(grep exit 3\)' "$out" "$s"
out=$("$jpdev" record post --file "$clean" --dry-run 2>&1) && s=0 || s=$?
expect "record needs a pull request or an issue" 2 'give --pr N or --issue N' "$out" "$s"

# --- env
printf 'JPDEV_NODE_RSS_MB=4321\nJPDEV_GO_TIMEOUT_S=99\n' > "$XDG_CONFIG_HOME/jpdev.env.tmp"
mkdir -p "$XDG_CONFIG_HOME/jpdev"; mv "$XDG_CONFIG_HOME/jpdev.env.tmp" "$XDG_CONFIG_HOME/jpdev/env"
out=$(JPDEV_GO_TIMEOUT_S=55 "$jpdev" env 2>&1) && s=0 || s=$?
expect "env reports a config-file value as such" 0 'JPDEV_NODE_RSS_MB +4321 +config file' "$out" "$s"
expect "env lets the environment win over the config file" 0 'JPDEV_GO_TIMEOUT_S +55 +environment' "$out" "$s"
expect "env reports a default as such" 0 'JPDEV_PY_ULIMIT_KB +4000000 +default' "$out" "$s"
rm -f "$XDG_CONFIG_HOME/jpdev/env"

# --- setup, on a local origin
origin=$work/origin.git
seed=$work/seed
git init -q --bare -b main "$origin"
git init -q -b main "$seed"
cp "$fixture" "$seed/dev.json"
git -C "$seed" add dev.json
git -C "$seed" -c user.name=test -c user.email=test@example.com commit -q -m seed
git -C "$seed" remote add origin "$origin"
git -C "$seed" push -q origin main
git clone -q "$origin" "$work/clone"
out=$("$jpdev" setup "$work/clone" --repo Example/repo --branch topic --base origin/main 2>&1) && s=0 || s=$?
expect "setup makes the branch from the base" 0 'branch +topic at' "$out" "$s"
expect "setup runs the manifest's setup steps" 0 'PASS +prepare' "$out" "$s"
expect "setup names the toolchains" 0 'python +Python' "$out" "$s"
if [ "$(git -C "$work/clone" rev-parse --abbrev-ref HEAD)" = topic ]; then ok "setup leaves the clone on the new branch"; else bad "setup leaves the clone on the new branch"; fi
out=$("$jpdev" setup "$work/clone" --branch topic 2>&1) && s=0 || s=$?
expect "setup reuses an existing clone and an existing branch" 0 'branch +topic' "$out" "$s"
out=$("$jpdev" setup "$work/not-a-clone" 2>&1) && s=0 || s=$?
expect "setup asks for --repo when the directory is not a clone" 2 'give --repo' "$out" "$s"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
