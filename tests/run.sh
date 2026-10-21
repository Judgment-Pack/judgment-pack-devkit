#!/usr/bin/env bash
# tests/run.sh: the kit's own tests. No network, no node; needs git, python3, rsync, flock and go.
set -u
kit=$(cd "$(dirname "$0")/.." && pwd)
cd "$kit" || exit 2
work=$(mktemp -d)
trap 'rm -rf -- "${work:?}"' EXIT
export JPDEV_SCRATCH=$work/scratch XDG_CONFIG_HOME=$work/config HOME=$work/home
mkdir -p "$HOME" "$XDG_CONFIG_HOME"
unset CI JPDEV_VENV JPDEV_LOCK JPDEV_NODE_RSS_MB JPDEV_NODE_TIMEOUT_S JPDEV_GO_ULIMIT_KB JPDEV_GO_TIMEOUT_S JPDEV_PY_ULIMIT_KB JPDEV_NVM_DIR JPDEV_GO_SDK_DIR JPDEV_NAME_PATTERNS JPDEV_CODEX_MODEL_DEFAULT JPDEV_CODEX_SANDBOX JPDEV_CODEX_WORDS JPDEV_FIXTURE_UNSET
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
expect "check.sh prints the handover path counts" 1 'handover: boundary 2 paths, shared 3 paths; see AGENTS.md "Before you hand over"' "$out" "$s"
printf '{"version": 1, "checks": [{"name": "pass", "run": "true"}]}\n' > "$work/no-handover.json"
out=$("$kit/templates/check.sh" --manifest "$work/no-handover.json" 2>/dev/null) && s=0 || s=$?
absent "check.sh prints no handover line when the manifest has none" '^handover:' "$out"
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
expect "jpdev check prints the handover path counts" 1 'handover: boundary 2 paths, shared 3 paths' "$out" "$s"
if grep -q 'go version go' <<< "$out" && grep -q 'Python 3' <<< "$out"; then ok "jpdev check prints the counts the checks printed"; else bad "jpdev check prints the counts the checks printed" "$out"; fi
out=$("$jpdev" check --manifest "$fixture" --skip fails,after-failure,needs-variable 2>/dev/null) && s=0 || s=$?
expect "jpdev check exits 0 when every check passes" 0 '== 5 passed' "$out" "$s"
out=$(JPDEV_GO_ULIMIT_KB=1000 "$jpdev" check --manifest "$fixture" --only go-version 2>/dev/null) && s=0 || s=$?
expect "jpdev check applies the Go address-space cap (a 1 MB cap fails the step)" 1 'FAIL +go-version' "$out" "$s"
out=$("$jpdev" check --manifest "$fixture" --only go-env 2>/dev/null) && s=0 || s=$?
expect "jpdev check runs a Go step" 0 'PASS +go-env' "$out" "$s"
golog=$(cat "$JPDEV_SCRATCH"/logs/*/go-env.log 2>/dev/null)
expect "a Go step runs with GOFLAGS=-mod=readonly" 0 '^-mod=readonly$' "$golog" 0
absent "a Go step does not run with -mod=mod" '^-mod=mod$' "$golog"
out=$(GOFLAGS=-mod=mod "$jpdev" check --manifest "$fixture" --only go-env 2>/dev/null) && s=0 || s=$?
golog=$(cat "$JPDEV_SCRATCH"/logs/*/go-env.log 2>/dev/null | tail -n 2)
expect "a GOFLAGS in the environment does not reach a Go step" 0 '^-mod=readonly$' "$golog" 0
expect "a Go step runs with a per-clone cache under the scratch directory" 0 "^$JPDEV_SCRATCH/gocache/" "$golog" 0

# a Go step leaves go.mod byte-identical: under -mod=mod, go vet drops the "// indirect" marker of a
# module the code imports directly; under -mod=readonly it does not (the module is a local replace)
gomod=$work/gomod
mkdir -p "$gomod/dep"
git init -q -b main "$gomod"
printf 'module example.com/dep\n\ngo 1.21\n' > "$gomod/dep/go.mod"
printf 'package dep\n\nfunc F() int { return 1 }\n' > "$gomod/dep/dep.go"
printf 'module example.com/app\n\ngo 1.21\n\nrequire example.com/dep v0.0.0 // indirect\n\nreplace example.com/dep => ./dep\n' > "$gomod/go.mod"
printf 'package main\n\nimport "example.com/dep"\n\nfunc main() { _ = dep.F() }\n' > "$gomod/main.go"
cat > "$gomod/dev.json" <<'JSON'
{"version": 1, "toolchains": {"go": {}}, "checks": [{"name": "vet", "run": "go vet . && go build -o /dev/null .", "toolchain": "go"}]}
JSON
before=$(sha256sum "$gomod/go.mod")
out=$(cd "$gomod" && "$jpdev" check 2>&1) && s=0 || s=$?
expect "a Go step that vets and builds passes on a read-only module" 0 'PASS +vet' "$out" "$s"
after=$(sha256sum "$gomod/go.mod")
if [ "$before" = "$after" ]; then ok "a Go step leaves go.mod byte-identical"; else bad "a Go step leaves go.mod byte-identical" "$(cat "$gomod/go.mod")"; fi
# the same step under -mod=mod does rewrite it, which is what the test above must catch
(cd "$gomod" && GOFLAGS=-mod=mod go vet . > /dev/null 2>&1)
if [ "$before" != "$(sha256sum "$gomod/go.mod")" ]; then ok "the test module is one that -mod=mod rewrites"; else bad "the test module is one that -mod=mod rewrites"; fi
printf 'module example.com/app\n\ngo 1.21\n\nrequire example.com/dep v0.0.0 // indirect\n\nreplace example.com/dep => ./dep\n' > "$gomod/go.mod"
# a module the files lack fails the step and leaves go.mod alone
printf 'package main\n\nimport _ "example.com/missing"\n\nfunc main() {}\n' > "$gomod/main.go"
before=$(sha256sum "$gomod/go.mod")
out=$(cd "$gomod" && GOPROXY=off "$jpdev" check 2>&1) && s=0 || s=$?
expect "a Go step that needs a module go.mod lacks fails" 1 'FAIL +vet' "$out" "$s"
if [ "$before" = "$(sha256sum "$gomod/go.mod")" ]; then ok "a failed Go step leaves go.mod byte-identical"; else bad "a failed Go step leaves go.mod byte-identical"; fi

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
printf '{"version": 1, "checks": [{"name": "a", "run": "true"}], "handover": {"boundary_paths": ["gate"], "shared_paths": ["contract"]}}\n' > "$work/handover.json"
out=$(python3 "$kit/lib/validate_manifest.py" "$work/handover.json" "$kit/templates/dev.schema.json" 2>&1) && s=0 || s=$?
expect "the schema accepts handover path lists" 0 "valid" "$out" "$s"
printf '{"version": 1, "checks": [{"name": "a", "run": "true"}], "handover": {"boundary_paths": ["gate"], "shared_paths": [], "other": []}}\n' > "$work/handover-unknown.json"
out=$(python3 "$kit/lib/validate_manifest.py" "$work/handover-unknown.json" "$kit/templates/dev.schema.json" 2>&1) && s=0 || s=$?
expect "the schema refuses an unknown handover member" 1 "dev.json:" "$out" "$s"
printf '{"version": 1, "checks": [{"name": "a", "run": "true"}], "handover": {"boundary_paths": [""], "shared_paths": []}}\n' > "$work/handover-empty.json"
out=$(python3 "$kit/lib/validate_manifest.py" "$work/handover-empty.json" "$kit/templates/dev.schema.json" 2>&1) && s=0 || s=$?
expect "the schema refuses an empty handover path" 1 "dev.json:" "$out" "$s"
out=$(python3 "$kit/lib/validate_manifest.py" "$kit/tests/fixture/handover-empty-shared.json" "$kit/templates/dev.schema.json" 2>&1) && s=0 || s=$?
expect "the schema refuses an empty shared handover path" 1 "dev.json:" "$out" "$s"
printf '{"version": 1, "checks": [{"name": "a", "run": "true"}], "handover": {"schema_probe": "scripts/schema-probe.sh"}}\n' > "$work/handover-probe.json"
out=$(python3 "$kit/lib/validate_manifest.py" "$work/handover-probe.json" "$kit/templates/dev.schema.json" 2>&1) && s=0 || s=$?
expect "the schema accepts handover.schema_probe" 0 "valid" "$out" "$s"
printf '{"version": 1, "checks": [{"name": "a", "run": "true"}], "handover": {"schema_probe": ""}}\n' > "$work/handover-empty-probe.json"
out=$(python3 "$kit/lib/validate_manifest.py" "$work/handover-empty-probe.json" "$kit/templates/dev.schema.json" 2>&1) && s=0 || s=$?
expect "the schema refuses an empty handover.schema_probe" 1 "handover/schema_probe" "$out" "$s"
printf '{"version": 2, "checks": []}\n' > "$work/bad.json"
out=$(python3 "$kit/lib/validate_manifest.py" "$work/bad.json" "$kit/templates/dev.schema.json" 2>&1) && s=0 || s=$?
expect "the manifest check refuses a wrong version" 1 "dev.json:" "$out" "$s"
if command -v actionlint > /dev/null; then
  out=$(actionlint "$kit/templates/ci-check.yml" "$kit/templates/update-branches.yml" 2>&1) && s=0 || s=$?
  expect "the workflow templates pass actionlint" 0 "" "$out" "$s"
else
  out=$(python3 - "$kit/templates/ci-check.yml" "$kit/templates/update-branches.yml" <<'PY'
import sys, yaml
for path in sys.argv[1:]: yaml.safe_load(open(path, encoding="utf-8"))
print("parsed workflow templates")
PY
  ) && s=0 || s=$?
  expect "the workflow templates parse as YAML" 0 "parsed workflow templates" "$out" "$s"
fi

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

# --- jpdev push
real_git=$(command -v git)
mkdir -p "$work/gitstub"
cat > "$work/gitstub/git" <<STUB
#!/usr/bin/env bash
for a in "\$@"; do
  if [ "\$a" = check-ref-format ] && [ -n "\${STUB_GIT_FAIL_REF:-}" ]; then exit 1; fi
  if [ "\$a" = push ]; then echo x >> "\$STUB_GIT_ARGS.calls"; printf '%s\\0' "\$@" > "\$STUB_GIT_ARGS"; exit "\${STUB_GIT_EXIT:-0}"; fi
done
exec $real_git "\$@"
STUB
chmod +x "$work/gitstub/git"
pushorigin=$work/pushorigin.git
pushclone=$work/pushclone
git init -q --bare -b main "$pushorigin"
git init -q -b main "$pushclone"
git -C "$pushclone" -c user.name=test -c user.email=test@example.com commit -q --allow-empty -m seed
git -C "$pushclone" remote add origin "$pushorigin"
git -C "$pushclone" switch -q -c topic
export STUB_GIT_ARGS=$work/git-args
rm -f "$STUB_GIT_ARGS"
out=$(cd "$pushclone" && PATH=$work/gitstub:$PATH "$jpdev" push topic 2>&1) && s=0 || s=$?
expect "push with a branch name runs the push" 0 "" "$out" "$s"
want=$(printf '%s\0' -c credential.helper= -c 'credential.helper=!gh auth git-credential' push -u origin topic | od -An -c)
got=$(od -An -c < "$STUB_GIT_ARGS" 2>/dev/null)
if [ "$want" = "$got" ]; then ok "push runs exactly the gh credential-helper form"; else bad "push runs exactly the gh credential-helper form" "$(tr '\0' ' ' < "$STUB_GIT_ARGS")"; fi
rm -f "$STUB_GIT_ARGS"
out=$(cd "$pushclone" && PATH=$work/gitstub:$PATH "$jpdev" push 2>&1) && s=0 || s=$?
expect "push without a branch pushes the current branch" 0 "" "$out" "$s"
if [ "$(tr '\0' ' ' < "$STUB_GIT_ARGS")" = "-c credential.helper= -c credential.helper=!gh auth git-credential push -u origin topic " ]; then ok "push without a branch names the current branch"; else bad "push without a branch names the current branch" "$(tr '\0' ' ' < "$STUB_GIT_ARGS")"; fi
for flag in --force -f --force-with-lease --force-if-includes -fu +topic; do
  rm -f "$STUB_GIT_ARGS"
  out=$(cd "$pushclone" && PATH=$work/gitstub:$PATH "$jpdev" push "$flag" topic 2>&1) && s=0 || s=$?
  expect "push refuses $flag" 2 'refused: a force push is never made' "$out" "$s"
  if [ -e "$STUB_GIT_ARGS" ]; then bad "push $flag reached git push"; else ok "push $flag did not reach git push"; fi
done
out=$(cd "$pushclone" && PATH=$work/gitstub:$PATH "$jpdev" push topic --force 2>&1) && s=0 || s=$?
expect "push refuses --force after the branch" 2 'refused: a force push is never made' "$out" "$s"
out=$(cd "$pushclone" && PATH=$work/gitstub:$PATH "$jpdev" push -u 2>&1) && s=0 || s=$?
expect "push refuses an option it does not know" 2 'unknown argument -u' "$out" "$s"
out=$(cd "$pushclone" && PATH=$work/gitstub:$PATH "$jpdev" push a b 2>&1) && s=0 || s=$?
expect "push takes one branch" 2 'one branch only' "$out" "$s"
out=$(cd "$pushclone" && PATH=$work/gitstub:$PATH "$jpdev" push 'a..b' 2>&1) && s=0 || s=$?
expect "push refuses a name that is not a branch name" 2 'not a branch name' "$out" "$s"
out=$(cd "$work" && PATH=$work/gitstub:$PATH "$jpdev" push topic 2>&1) && s=0 || s=$?
expect "push outside a clone fails" 2 'not inside a git clone' "$out" "$s"
out=$(cd "$pushclone" && STUB_GIT_EXIT=3 PATH=$work/gitstub:$PATH "$jpdev" push topic 2>&1) && s=0 || s=$?
expect "push returns the exit status of git push" 3 "" "$out" "$s"
out=$(cd "$pushclone" && "$jpdev" push topic 2>&1) && s=0 || s=$?
expect "push pushes to a repository and sets the upstream" 0 "" "$out" "$s"
if [ "$(git -C "$pushorigin" rev-parse refs/heads/topic 2>/dev/null)" = "$(git -C "$pushclone" rev-parse topic)" ] \
  && [ "$(git -C "$pushclone" config branch.topic.remote)" = origin ]; then ok "the branch is on origin with its upstream set"; else bad "the branch is on origin with its upstream set"; fi
unset STUB_GIT_ARGS
# the agent instructions and the docs state the push form
pushform="git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push -u origin BRANCH"
for doc in templates/AGENTS.md templates/CLAUDE.md AGENTS.md CLAUDE.md; do
  if grep -qF -- "$pushform" "$kit/$doc" && grep -qF 'jpdev push' "$kit/$doc"; then ok "$doc states the push form and names jpdev push"; else bad "$doc states the push form and names jpdev push"; fi
done
if grep -qF 'jpdev push' "$kit/docs/adopting.md"; then ok "docs/adopting.md mentions jpdev push"; else bad "docs/adopting.md mentions jpdev push"; fi

# --- jpdev codex (a stub codex first on PATH: the real one is never called)
mkdir -p "$work/codexbin" "$work/codexclone"
cat > "$work/codexbin/codex" <<'STUB'
#!/usr/bin/env bash
printf '%s\0' "$@" > "$STUB_CODEX_ARGS"
pwd > "$STUB_CODEX_CWD"
printf '%s\n' "JPDEV_SCRATCH=$JPDEV_SCRATCH" "JPDEV_LOCK=$JPDEV_LOCK" "GOCACHE=${GOCACHE:-}" \
  "GOFLAGS=${GOFLAGS:-}" "npm_config_cache=${npm_config_cache:-}" "XDG_CACHE_HOME=${XDG_CACHE_HOME:-}" > "$STUB_CODEX_ENV"
timeout 2 cat > "$STUB_CODEX_STDIN"
while [ $# -gt 0 ]; do
  case $1 in -o) printf 'stub final message\n' > "$2" ;; esac
  shift
done
if [ -n "${STUB_CODEX_EDIT:-}" ]; then
  echo "edited by codex" >> "${STUB_CODEX_EDIT_FILE:-file.txt}"
  echo "new file" > created.txt
fi
if [ -n "${STUB_CODEX_MSG:-}" ]; then
  cp "$STUB_CODEX_MSG" msg.txt
  if [ -z "${STUB_CODEX_NO_PR:-}" ]; then printf 'Closes #1.\n\n## What it adds\nA line.\n' > pr.md; fi
fi
if [ -n "${STUB_CODEX_RESOLVE:-}" ]; then printf 'main addition\nbranch addition\n' > "$STUB_CODEX_RESOLVE"; fi
echo "stub transcript line"
echo '{"type":"thread.started","thread_id":"thread-test"}'
echo "stub stderr line" >&2
exit "${STUB_CODEX_EXIT:-0}"
STUB
chmod +x "$work/codexbin/codex"
export STUB_CODEX_ARGS=$work/codex-args STUB_CODEX_CWD=$work/codex-cwd STUB_CODEX_STDIN=$work/codex-stdin STUB_CODEX_ENV=$work/codex-env
oldpath=$PATH
PATH=$work/codexbin:$PATH
printf '# Rules\n' > "$work/codexclone/AGENTS.md"
printf 'Add the flag.\nIt must refuse an unknown value with exit 2.\n\n## Before you write msg.txt\n' > "$work/brief.md"
codex_args() { rm -f "$STUB_CODEX_ARGS" "$STUB_CODEX_CWD" "$STUB_CODEX_STDIN"; }
has_arg() { tr '\0' '\n' < "$STUB_CODEX_ARGS" 2>/dev/null | grep -qxF -- "$1"; }
codex_args
out=$(echo junk | "$jpdev" codex run --no-commit --brief "$work/brief.md" --model model-x --effort high --dir "$work/codexclone" --log "$work/codex.log" 2>/dev/null) && s=0 || s=$?
expect "codex run prints the final message" 0 '^stub final message$' "$out" "$s"
expect "codex run prints the exit code" 0 '^== codex exit 0 ' "$out" "$s"
for a in exec -m model-x 'model_reasoning_effort=high' --sandbox workspace-write 'sandbox_workspace_write.network_access=true' -C "$work/codexclone"; do
  if has_arg "$a"; then ok "codex run passes $a"; else bad "codex run passes $a" "$(tr '\0' ' ' < "$STUB_CODEX_ARGS")"; fi
done
if [ "$(tr '\0' '\n' < "$STUB_CODEX_ARGS" | sed -n '1,7p' | paste -sd' ')" = "exec -m model-x -c model_reasoning_effort=high --sandbox workspace-write" ]; then ok "codex run passes the model and effort as flags and values"; else bad "codex run passes the model and effort as flags and values" "$(tr '\0' ' ' < "$STUB_CODEX_ARGS")"; fi
prompt=$(python3 -I -c 'import sys; a = open(sys.argv[1], "rb").read().split(b"\0"); sys.stdout.write(a[-2].decode())' "$STUB_CODEX_ARGS")
if [ "$(head -n 1 <<< "$prompt")" = "The rules are this repository's AGENTS.md; follow them." ]; then ok "the prompt opens with one line naming AGENTS.md as the rules"; else bad "the prompt opens with one line naming AGENTS.md as the rules" "$prompt"; fi
if [ "$(tail -n +2 <<< "$prompt")" = "$(cat "$work/brief.md")" ]; then ok "the prompt is that line and the brief's text"; else bad "the prompt is that line and the brief's text" "$prompt"; fi
if [ "$(cat "$STUB_CODEX_CWD")" = "$(cd "$work/codexclone" && pwd -P)" ]; then ok "codex runs in the directory given"; else bad "codex runs in the directory given" "$(cat "$STUB_CODEX_CWD")"; fi
if [ -f "$STUB_CODEX_STDIN" ] && [ ! -s "$STUB_CODEX_STDIN" ]; then ok "codex's stdin is /dev/null, whatever jpdev reads"; else bad "codex's stdin is /dev/null, whatever jpdev reads" "$(cat "$STUB_CODEX_STDIN")"; fi
log=$(cat "$work/codex.log")
expect "the transcript (stdout) is in the log" 0 '^stub transcript line$' "$log" 0
expect "the transcript (stderr) is in the log" 0 '^stub stderr line$' "$log" 0
absent "the final message is not part of the transcript" 'stub final message' "$log"
if [ "$(cat "$work/codexclone/.jpdev/output/thread")" = thread-test ]; then ok "codex run records the thread id"; else bad "codex run records the thread id"; fi
codex_args
out=$("$jpdev" codex run --no-commit --brief "$work/brief.md" --model model-x --effort low --dir "$work/codexclone" --resume prior-thread --log "$work/codex-resume.log" 2>&1) && s=0 || s=$?
expect "codex run --resume completes" 0 "codex exit 0" "$out" "$s"
if has_arg resume && has_arg prior-thread; then ok "codex run passes resume and the thread id"; else bad "codex run passes resume and the thread id" "$(tr '\0' ' ' < "$STUB_CODEX_ARGS")"; fi
want_root=$(cd "$work/codexclone" && pwd -P)
out=$(JPDEV_SCRATCH='' JPDEV_LOCK='' GOCACHE='' GOFLAGS='' npm_config_cache='' XDG_CACHE_HOME='' \
  "$jpdev" codex run --no-commit --brief "$work/brief.md" --model model-x --effort low --dir "$work/codexclone" --log "$work/codex-env.log" 2>&1) && s=0 || s=$?
expect "codex run sets clone-local sandbox variables" 0 "codex exit 0" "$out" "$s"
for pair in "JPDEV_SCRATCH=$want_root/.jpdev" "JPDEV_LOCK=$want_root/.jpdev/lock" \
  "GOCACHE=$want_root/.gocache" "GOFLAGS=-mod=readonly" \
  "npm_config_cache=$want_root/.npm-cache" "XDG_CACHE_HOME=$want_root/.xdg-cache"; do
  if grep -qxF "$pair" "$STUB_CODEX_ENV"; then ok "codex receives $pair"; else bad "codex receives $pair" "$(cat "$STUB_CODEX_ENV")"; fi
done
for cache in .jpdev .gocache .npm-cache .xdg-cache; do
  if [ -d "$work/codexclone/$cache" ]; then ok "codex run creates $cache under the clone"; else bad "codex run creates $cache under the clone"; fi
done
out=$(GOCACHE=$work/preset-go-cache "$jpdev" codex run --no-commit --brief "$work/brief.md" --model model-x --effort low --dir "$work/codexclone" --log "$work/codex-preset.log" 2>&1) && s=0 || s=$?
expect "codex run leaves a pre-set GOCACHE alone" 0 "codex exit 0" "$out" "$s"
expect "the pre-set GOCACHE reaches codex" 0 '^GOCACHE=.*/preset-go-cache$' "$(cat "$STUB_CODEX_ENV")" 0
out=$(STUB_CODEX_EXIT=7 "$jpdev" codex run --no-commit --brief "$work/brief.md" --model model-x --effort low --dir "$work/codexclone" --log "$work/codex7.log" 2>/dev/null) && s=0 || s=$?
expect "codex run returns codex's exit code" 7 '^== codex exit 7 ' "$out" "$s"
codex_args
out=$("$jpdev" codex run --no-commit --brief "$work/brief.md" --model model-x --effort medium --dir "$work/codexclone" --sandbox danger-full-access --log "$work/codex-d.log" 2>/dev/null) && s=0 || s=$?
expect "codex run accepts --sandbox danger-full-access" 0 'codex exit 0' "$out" "$s"
if has_arg danger-full-access && ! has_arg 'sandbox_workspace_write.network_access=true'; then ok "danger-full-access is passed without the workspace-write network setting"; else bad "danger-full-access is passed without the workspace-write network setting" "$(tr '\0' ' ' < "$STUB_CODEX_ARGS")"; fi
codex_args
out=$(cd "$work/codexclone" && JPDEV_CODEX_MODEL_DEFAULT=model-d JPDEV_CODEX_SANDBOX=danger-full-access "$jpdev" codex run --no-commit --brief "$work/brief.md" --effort low 2>/dev/null) && s=0 || s=$?
expect "codex run uses the configured default model, sandbox and the current directory" 0 'codex exit 0' "$out" "$s"
if has_arg model-d && has_arg danger-full-access; then ok "the defaults reach codex"; else bad "the defaults reach codex" "$(tr '\0' ' ' < "$STUB_CODEX_ARGS")"; fi
logline=$(grep -E '^== codex exit' <<< "$out")
if [ -f "$(sed -E 's/.*transcript: (.*)\) ==$/\1/' <<< "$logline")" ]; then ok "with no --log the transcript is under the scratch directory"; else bad "with no --log the transcript is under the scratch directory" "$logline"; fi
codex_args
out=$("$jpdev" codex run --brief "$work/brief.md" --effort high --dir "$work/codexclone" 2>&1) && s=0 || s=$?
expect "codex run refuses a run with no model" 2 '--model is needed' "$out" "$s"
out=$("$jpdev" codex run --brief "$work/brief.md" --model m --dir "$work/codexclone" 2>&1) && s=0 || s=$?
expect "codex run refuses a run with no effort" 2 'low, medium or high' "$out" "$s"
out=$("$jpdev" codex run --brief "$work/brief.md" --model m --effort max --dir "$work/codexclone" 2>&1) && s=0 || s=$?
expect "codex run refuses an effort it does not know" 2 'low, medium or high' "$out" "$s"
out=$("$jpdev" codex run --brief "$work/brief.md" --model m --effort low --sandbox read-only --dir "$work/codexclone" 2>&1) && s=0 || s=$?
expect "codex run refuses a sandbox it does not know" 2 'workspace-write or danger-full-access' "$out" "$s"
out=$("$jpdev" codex run --brief "$work/nobrief.md" --model m --effort low --dir "$work/codexclone" 2>&1) && s=0 || s=$?
expect "codex run needs the brief file" 2 '--brief must name a file' "$out" "$s"
mkdir -p "$work/norules"
out=$("$jpdev" codex run --brief "$work/brief.md" --model m --effort low --dir "$work/norules" 2>&1) && s=0 || s=$?
expect "codex run refuses a directory with no AGENTS.md" 2 'holds no AGENTS.md' "$out" "$s"
if [ -e "$STUB_CODEX_ARGS" ]; then bad "a refused run did not start codex"; else ok "a refused run did not start codex"; fi

# worktrees: creation, linked dependencies, shared caches and guarded removal
wtorigin=$work/wtorigin.git
wtseed=$work/wtseed
wtbase=$work/wtbase
wt=$work/wt-topic
git init -q --bare -b main "$wtorigin"
git init -q -b main "$wtseed"
printf '# Rules\n' > "$wtseed/AGENTS.md"
printf '{"version":1,"checks":[{"name":"one","run":"true"}]}\n' > "$wtseed/dev.json"
printf '{"lockfileVersion":3}\n' > "$wtseed/package-lock.json"
printf 'one\n' > "$wtseed/file.txt"
git -C "$wtseed" add .
git -C "$wtseed" -c user.name=test -c user.email=test@example.com commit -q -m seed
git -C "$wtseed" remote add origin "$wtorigin"
git -C "$wtseed" push -q origin main
git clone -q "$wtorigin" "$wtbase"
mkdir -p "$wtbase/node_modules"
out=$("$jpdev" worktree add "$wtbase" topic "$wt" 2>&1) && s=0 || s=$?
expect "worktree add creates the branch worktree" 0 'branch +topic' "$out" "$s"
if [ -L "$wt/node_modules" ]; then ok "worktree add links node_modules from the base"; else bad "worktree add links node_modules from the base"; fi
out=$(JPDEV_SCRATCH='' JPDEV_LOCK='' GOCACHE='' npm_config_cache='' XDG_CACHE_HOME='' \
  "$jpdev" codex run --no-commit --brief "$work/brief.md" --model model-x --effort low --dir "$wt" --worktree "$wtbase" --log "$work/wt-codex.log" 2>&1) && s=0 || s=$?
expect "codex run --worktree completes" 0 'codex exit 0' "$out" "$s"
for pair in "GOCACHE=$wtbase/.jpdev-shared/gocache" "npm_config_cache=$wtbase/.jpdev-shared/npm-cache" \
  "XDG_CACHE_HOME=$wtbase/.jpdev-shared/xdg-cache" "JPDEV_LOCK=$wt/.jpdev/lock"; do
  if grep -qxF "$pair" "$STUB_CODEX_ENV"; then ok "worktree codex receives $pair"; else bad "worktree codex receives $pair" "$(cat "$STUB_CODEX_ENV")"; fi
done
printf 'dirty\n' >> "$wt/file.txt"
out=$("$jpdev" worktree remove "$wt" 2>&1) && s=0 || s=$?
expect "worktree remove refuses a dirty worktree" 2 'refused: .* has uncommitted work' "$out" "$s"
out=$("$jpdev" worktree remove "$wt" --force 2>&1) && s=0 || s=$?
expect "worktree remove --force removes the dirty worktree" 0 '' "$out" "$s"
if [ ! -e "$wt" ]; then ok "the forced worktree removal removed its directory"; else bad "the forced worktree removal removed its directory"; fi
wt_auto=$work/wt-auto
out=$(JPDEV_SCRATCH='' JPDEV_LOCK='' GOCACHE='' npm_config_cache='' XDG_CACHE_HOME='' \
  "$jpdev" codex run --no-commit --brief "$work/brief.md" --model model-x --effort low --dir "$wt_auto" \
  --worktree "$wtbase" --branch auto-topic --log "$work/wt-auto.log" 2>&1) && s=0 || s=$?
expect "codex run --worktree creates a missing worktree" 0 'codex exit 0' "$out" "$s"
if [ "$(git -C "$wt_auto" branch --show-current)" = auto-topic ]; then ok "the Codex worktree uses the requested branch"; else bad "the Codex worktree uses the requested branch"; fi
out=$("$jpdev" worktree list "$wtbase" 2>&1) && s=0 || s=$?
expect "worktree list shows the Codex worktree" 0 'auto-topic' "$out" "$s"
"$jpdev" worktree remove "$wt_auto" --force

# check-brief: the base list, the neutral phrasing, the config extension
printf 'Reject a request with an unexpected value and return the documented error.\nA shackle is a ring.\n\n## Before you write msg.txt\n' > "$work/clean-brief.md"
out=$("$jpdev" codex check-brief "$work/clean-brief.md" 2>&1) && s=0 || s=$?
expect "check-brief accepts a brief with no listed word" 0 'no word of the filter list' "$out" "$s"
printf 'Defend against an attacker who sends a prompt injection.\nIt must stop the EXPLOITATION of the parser.\n\n## Before you write msg.txt\n' > "$work/dirty-brief.md"
out=$("$jpdev" codex check-brief "$work/dirty-brief.md" 2>&1) && s=0 || s=$?
expect "check-brief refuses a brief with a listed word" 1 'refused: .* holds words the content filter trips on' "$out" "$s"
expect "check-brief names the line and the word" 1 'line 1: "attacker"' "$out" "$s"
expect "check-brief matches a phrase" 1 'line 1: "prompt injection": describe the untrusted text' "$out" "$s"
expect "check-brief matches regardless of case and ending" 1 'line 2: "EXPLOITATION"' "$out" "$s"
expect "check-brief suggests the neutral phrasing" 1 'describe the input the code receives and the refusal it must produce' "$out" "$s"
expect "check-brief points at the documented refusal" 1 'describe the documented refusal instead' "$out" "$s"
absent "check-brief does not flag a word that merely contains a listed one" 'shackle' "$out"
n=0
while IFS= read -r line; do
  case $line in '' | '#'*) continue ;; esac
  term=${line%%=>*}; term=${term%"${term##*[![:space:]]}"}
  n=$((n + 1))
  printf 'The change handles %s here.\n' "$term" > "$work/term-brief.md"
  out=$("$jpdev" codex check-brief "$work/term-brief.md" 2>&1) && s=0 || s=$?
  if [ "$s" -ne 1 ]; then bad "check-brief refuses the base-list term '$term'" "$out"; fi
  [ -z "${term_failed:-}" ] || true
done < "$kit/config/codex-words.txt"
if [ "$n" -ge 20 ]; then ok "check-brief refuses each of the $n terms of config/codex-words.txt"; else bad "the base word list holds at least 20 terms" "$n"; fi
printf 'Guard against a prompt\ninjection in the page,\nand a prompt-injection in a tool result, and a Prompt  -  Injection.\nA denial-of-service limit and a denial of\nservice limit.\n' > "$work/wrapped-brief.md"
out=$("$jpdev" codex check-brief "$work/wrapped-brief.md" 2>&1) && s=0 || s=$?
expect "check-brief finds a term wrapped over two lines, reported at its first line" 1 'line 1: "prompt injection"' "$out" "$s"
expect "check-brief finds a hyphenated term" 1 'line 3: "prompt-injection"' "$out" "$s"
expect "check-brief finds a term with mixed spaces and hyphens" 1 'line 3: "Prompt - Injection"' "$out" "$s"
expect "check-brief finds a hyphenated three-word term" 1 'line 4: "denial-of-service"' "$out" "$s"
expect "check-brief finds a three-word term wrapped over two lines" 1 'line 4: "denial of service"' "$out" "$s"
printf 'The prompt and the injection of values are separate words.\n' > "$work/apart-brief.md"
out=$("$jpdev" codex check-brief "$work/apart-brief.md" 2>&1) && s=0 || s=$?
expect "check-brief does not join words that are not adjacent" 0 'no word of the filter list' "$out" "$s"
printf 'extra-term => say it plainly\n' > "$work/extra-words.txt"
printf 'Handle the extra-term case.\n' > "$work/extra-brief.md"
out=$("$jpdev" codex check-brief "$work/extra-brief.md" 2>&1) && s=0 || s=$?
expect "check-brief accepts a term the base list lacks" 0 'no word of the filter list' "$out" "$s"
out=$(JPDEV_CODEX_WORDS=$work/extra-words.txt "$jpdev" codex check-brief "$work/extra-brief.md" 2>&1) && s=0 || s=$?
expect "check-brief refuses a term the config adds, with its phrasing" 1 'line 1: "extra-term": say it plainly' "$out" "$s"
out=$(JPDEV_CODEX_WORDS=$work/extra-words.txt "$jpdev" codex check-brief "$work/dirty-brief.md" 2>&1) && s=0 || s=$?
expect "the config extends the base list and does not replace it" 1 'line 1: "attacker"' "$out" "$s"
out=$("$jpdev" codex check-brief "$work/nobrief.md" 2>&1) && s=0 || s=$?
expect "check-brief needs the file" 2 'give the brief file' "$out" "$s"
printf 'A clean build brief without the required handover heading.\n' > "$work/no-handover-heading.md"
out=$("$jpdev" codex check-brief --build "$work/no-handover-heading.md" 2>&1) && s=0 || s=$?
expect "check-brief --build refuses a missing handover heading" 1 'refused: .* has no line exactly' "$out" "$s"
codex_args
out=$("$jpdev" codex run --no-commit --brief "$work/no-handover-heading.md" --model m --effort low --dir "$work/codexclone" 2>&1) && s=0 || s=$?
expect "codex run requires the handover heading" 1 'refused: .* has no line exactly' "$out" "$s"
if [ -e "$STUB_CODEX_ARGS" ]; then bad "a run refused for the missing heading did not start codex"; else ok "a run refused for the missing heading did not start codex"; fi
out=$("$jpdev" codex check-brief "$work/no-handover-heading.md" 2>"$work/brief-warning.err") && s=0 || s=$?
expect "check-brief without --build accepts a missing handover heading" 0 'no word of the filter list' "$out" "$s"
expect "check-brief without --build warns once about the heading" 0 '^jpdev codex check-brief: warning: .* has no line exactly' "$(cat "$work/brief-warning.err")" 0
if [ "$(wc -l < "$work/brief-warning.err")" -eq 1 ]; then ok "the missing-heading warning is one line"; else bad "the missing-heading warning is one line" "$(cat "$work/brief-warning.err")"; fi
out=$("$jpdev" codex check-brief --build "$kit/templates/codex-brief.md" 2>&1) && s=0 || s=$?
expect "check-brief --build accepts the brief template" 0 'no word of the filter list' "$out" "$s"
codex_args
out=$("$jpdev" codex run --no-commit --brief "$work/dirty-brief.md" --model m --effort low --dir "$work/codexclone" 2>&1) && s=0 || s=$?
expect "codex run refuses a brief with a listed word" 1 'refused: .* holds words the content filter trips on' "$out" "$s"
if [ -e "$STUB_CODEX_ARGS" ]; then bad "a refused brief did not start codex"; else ok "a refused brief did not start codex"; fi
out=$("$jpdev" codex 2>&1) && s=0 || s=$?
expect "codex needs a subcommand" 2 'the subcommands are run, check-brief and brief-template' "$out" "$s"
# the git part: commit, push, pull request, from the msg.txt and pr.md codex wrote
export STUB_GIT_ARGS=$work/git-args
mkdir -p "$work/ghbin"
cat > "$work/ghbin/gh" <<'STUB'
#!/usr/bin/env bash
echo x >> "$STUB_GH_CALLS"
printf '%s\0' "$@" > "$STUB_GH_ARGS"
while [ $# -gt 0 ]; do
  case $1 in --body-file) cp "$2" "$STUB_GH_BODY" ;; esac
  shift
done
echo "https://github.com/Example/repo/pull/1"
STUB
chmod +x "$work/ghbin/gh"
export STUB_GH_CALLS=$work/gh-calls STUB_GH_ARGS=$work/gh-args STUB_GH_BODY=$work/gh-body
export GIT_AUTHOR_NAME=Test GIT_AUTHOR_EMAIL=test@example.com GIT_COMMITTER_NAME=Test GIT_COMMITTER_EMAIL=test@example.com
cxorigin=$work/cxorigin.git
cxrepo=$work/cxrepo
git init -q --bare -b main "$cxorigin"
git init -q -b main "$cxrepo"
printf '# Rules\n' > "$cxrepo/AGENTS.md"
printf 'one\n' > "$cxrepo/file.txt"
printf '{"version":1,"checks":[{"name":"one","run":"true"}],"handover":{"shared_paths":["file.txt"],"boundary_paths":[]}}\n' > "$cxrepo/dev.json"
printf 'msg.txt\npr.md\n' > "$cxrepo/.gitignore"
git -C "$cxrepo" add .gitignore AGENTS.md dev.json file.txt
git -C "$cxrepo" commit -q -m seed
git -C "$cxrepo" remote add origin "$cxorigin"
git -C "$cxrepo" push -q origin main
git -C "$cxrepo" switch -q -c work
printf 'Add the line\n\nExplain why.\n' > "$work/msg-plain.txt"
printf 'Add the line\n\nExplain why.\n\nCo-Authored-By: Codex <noreply@openai.com>\n' > "$work/msg-trailer.txt"
cx_reset() {
  git -C "$cxrepo" reset -q --hard origin/main
  git -C "$cxrepo" clean -q -fdx
  git -C "$cxrepo" switch -q -C work
  rm -f "$STUB_GIT_ARGS" "$STUB_GIT_ARGS.calls" "$STUB_GH_CALLS" "$STUB_GH_ARGS" "$STUB_GH_BODY" "$STUB_CODEX_ARGS"
}
cx_run() { # extra arguments to codex run
  PATH=$work/gitstub:$work/ghbin:$PATH "$jpdev" codex run --brief "$work/brief.md" --model m --effort low --dir "$cxrepo" --repo Example/repo --log "$work/cx.log" "$@" 2>&1
}
cx_calls() { if [ -f "$1" ]; then wc -l < "$1" | tr -d ' '; else echo 0; fi; }
base=$(git -C "$cxrepo" rev-parse HEAD)

cx_reset
out=$(STUB_CODEX_EDIT=1 cx_run --no-commit --small) && s=0 || s=$?
expect "codex run --small refuses a shared path after the run" 2 'refused after the run: file.txt is a shared or boundary path' "$out" "$s"
prompt=$(python3 -I -c 'import sys; a = open(sys.argv[1], "rb").read().split(b"\0"); sys.stdout.write(a[-2].decode())' "$STUB_CODEX_ARGS")
expect "codex run --small prepends its scoped-check line" 0 '^This is a small fix: run only the check-list steps' "$(sed -n '2p' <<< "$prompt")" 0
cx_reset
out=$(JPDEV_SMALL_MAX_LINES=0 STUB_CODEX_EDIT=1 STUB_CODEX_EDIT_FILE=AGENTS.md cx_run --no-commit --small) && s=0 || s=$?
expect "codex run --small refuses a change over the line bound" 2 'changed lines exceeds JPDEV_SMALL_MAX_LINES=0' "$out" "$s"

cx_reset
printf 'untracked and not named\n' > "$cxrepo/stray.txt"
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-plain.txt cx_run) && s=0 || s=$?
expect "codex run commits, pushes and opens the pull request" 0 'committed [0-9a-f]+ on work' "$out" "$s"
if [ "$(git -C "$cxrepo" rev-list --count "$base..HEAD")" = 1 ]; then ok "codex run makes one commit"; else bad "codex run makes one commit"; fi
if [ "$(git -C "$cxrepo" show --name-only --format= HEAD)" = file.txt ]; then ok "the commit holds the tracked change only"; else bad "the commit holds the tracked change only" "$(git -C "$cxrepo" show --name-only --format= HEAD)"; fi
expect "the untracked files left out are listed" 0 'stray.txt' "$out" "$s"
msg=$(git -C "$cxrepo" log -1 --format=%B)
expect "the commit has the subject of msg.txt" 0 '^Add the line$' "$msg" 0
expect "the commit is signed off" 0 '^Signed-off-by: Test <test@example.com>$' "$msg" 0
expect "the commit has the Codex trailer, added" 0 '^Co-Authored-By: Codex <noreply@openai.com>$' "$msg" 0
if [ "$(grep -c '^Co-Authored-By: Codex' <<< "$msg")" = 1 ]; then ok "the Codex trailer appears once"; else bad "the Codex trailer appears once" "$msg"; fi
if [ "$(cx_calls "$STUB_GIT_ARGS.calls")" = 1 ] && [ "$(tr '\0' ' ' < "$STUB_GIT_ARGS")" = "-c credential.helper= -c credential.helper=!gh auth git-credential push -u origin work " ]; then ok "one push, in the credential-helper form"; else bad "one push, in the credential-helper form" "$(tr '\0' ' ' < "$STUB_GIT_ARGS" 2>/dev/null)"; fi
if [ "$(cx_calls "$STUB_GH_CALLS")" = 1 ]; then ok "one gh pr create call"; else bad "one gh pr create call"; fi
if [ "$(tr '\0' ' ' < "$STUB_GH_ARGS")" = "pr create --repo Example/repo --base main --head work --title Add the line --body-file pr.md " ]; then ok "the pull request is made with --repo, --base, the subject and pr.md"; else bad "the pull request is made with --repo, --base, the subject and pr.md" "$(tr '\0' ' ' < "$STUB_GH_ARGS")"; fi
expect "the pull request body is pr.md" 0 '^Closes #1\.$' "$(cat "$STUB_GH_BODY")" 0

cx_reset
out=$(STUB_GIT_EXIT=3 STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-plain.txt cx_run) && s=0 || s=$?
expect "a failed push returns git's status and says the commit is local" 3 'the push failed; the commit [0-9a-f]+ is local' "$out" "$s"
if [ "$(cx_calls "$STUB_GH_CALLS")" = 0 ]; then ok "a failed push opens no pull request"; else bad "a failed push opens no pull request"; fi
cx_reset
out=$(STUB_GIT_FAIL_REF=1 STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-plain.txt cx_run) && s=0 || s=$?
expect "a push that dies before git push still says the commit is local" 2 'the push failed; the commit [0-9a-f]+ is local' "$out" "$s"
if [ "$(git -C "$cxrepo" rev-list --count "$base..HEAD")" = 1 ]; then ok "the commit is kept when the push fails"; else bad "the commit is kept when the push fails"; fi

cx_reset
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-trailer.txt cx_run) && s=0 || s=$?
expect "codex run takes a msg.txt that has the trailer" 0 'committed' "$out" "$s"
msg=$(git -C "$cxrepo" log -1 --format=%B)
if [ "$(grep -c '^Co-Authored-By: Codex' <<< "$msg")" = 1 ]; then ok "a trailer already in msg.txt is not repeated"; else bad "a trailer already in msg.txt is not repeated" "$msg"; fi

cx_reset
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-plain.txt cx_run --add created.txt) && s=0 || s=$?
expect "codex run --add commits a new file named" 0 'committed' "$out" "$s"
if [ "$(git -C "$cxrepo" show --name-only --format= HEAD | sort | paste -sd' ')" = "created.txt file.txt" ]; then ok "--add puts the named file in the commit"; else bad "--add puts the named file in the commit"; fi

cx_reset
for cache in .jpdev .gocache .npm-cache .xdg-cache; do
  mkdir -p "$cxrepo/$cache"
  printf 'cache\n' > "$cxrepo/$cache/file"
done
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-plain.txt cx_run --add .) && s=0 || s=$?
expect "codex run --add . commits while excluding cache directories" 0 'committed' "$out" "$s"
names=$(git -C "$cxrepo" show --name-only --format= HEAD | sort | paste -sd' ')
if [ "$names" = "created.txt file.txt" ]; then ok "--add . commits none of the cache directories"; else bad "--add . commits none of the cache directories" "$names"; fi

cx_reset
mkdir -p "$cxrepo/parent/keep"
printf 'keep\n' > "$cxrepo/parent/keep/file"
for cache in .jpdev .gocache .npm-cache .xdg-cache; do
  mkdir -p "$cxrepo/parent/$cache"
  printf 'cache\n' > "$cxrepo/parent/$cache/file"
done
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-plain.txt cx_run --add parent) && s=0 || s=$?
expect "codex run --add of a containing directory commits while excluding caches" 0 'committed' "$out" "$s"
names=$(git -C "$cxrepo" show --name-only --format= HEAD | sort | paste -sd' ')
if [ "$names" = "file.txt parent/keep/file" ]; then ok "--add of a containing directory commits none of its cache directories"; else bad "--add of a containing directory commits none of its cache directories" "$names"; fi

cx_reset
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-plain.txt cx_run --no-push) && s=0 || s=$?
expect "codex run --no-push commits and stops" 0 'committed' "$out" "$s"
if [ "$(git -C "$cxrepo" rev-list --count "$base..HEAD")" = 1 ] && [ ! -e "$STUB_GIT_ARGS" ] && [ ! -e "$STUB_GH_CALLS" ]; then ok "--no-push: a commit, no push, no pull request"; else bad "--no-push: a commit, no push, no pull request"; fi

cx_reset
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-plain.txt cx_run --no-pr) && s=0 || s=$?
expect "codex run --no-pr pushes and stops" 0 'pushed work' "$out" "$s"
if [ -e "$STUB_GIT_ARGS" ] && [ ! -e "$STUB_GH_CALLS" ]; then ok "--no-pr: a push, no pull request"; else bad "--no-pr: a push, no pull request"; fi

cx_reset
out=$(STUB_CODEX_MSG=$work/msg-plain.txt cx_run) && s=0 || s=$?
expect "with no edits codex run makes no commit and exits 1" 1 'nothing to commit' "$out" "$s"
if [ "$(git -C "$cxrepo" rev-list --count "$base..HEAD")" = 0 ] && [ ! -e "$STUB_GIT_ARGS" ] && [ ! -e "$STUB_GH_CALLS" ]; then ok "no edits: no commit, no push, no pull request"; else bad "no edits: no commit, no push, no pull request"; fi

cx_reset
out=$(STUB_CODEX_EDIT=1 cx_run) && s=0 || s=$?
expect "codex run refuses when codex wrote no msg.txt" 1 'wrote no msg.txt' "$out" "$s"
if [ "$(git -C "$cxrepo" rev-list --count "$base..HEAD")" = 0 ]; then ok "no msg.txt: no commit"; else bad "no msg.txt: no commit"; fi
cx_reset
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_NO_PR=1 STUB_CODEX_MSG=$work/msg-plain.txt cx_run) && s=0 || s=$?
expect "codex run refuses when codex wrote no pr.md" 1 'wrote no pr.md' "$out" "$s"
cx_reset
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_EXIT=4 STUB_CODEX_MSG=$work/msg-plain.txt cx_run) && s=0 || s=$?
expect "codex run does not commit after a failed codex run" 4 'codex exit 4' "$out" "$s"
if [ "$(git -C "$cxrepo" rev-list --count "$base..HEAD")" = 0 ]; then ok "a failed codex run: no commit"; else bad "a failed codex run: no commit"; fi
cx_reset
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-plain.txt cx_run --add msg.txt) && s=0 || s=$?
expect "codex run refuses --add msg.txt" 2 'read, never committed' "$out" "$s"
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-plain.txt cx_run --add .jpdev) && s=0 || s=$?
expect "codex run refuses --add .jpdev" 2 'sandbox cache directory' "$out" "$s"
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-plain.txt cx_run --add .jpdev-shared) && s=0 || s=$?
expect "codex run refuses --add .jpdev-shared" 2 'shared cache directory' "$out" "$s"
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-plain.txt cx_run --add ../outside) && s=0 || s=$?
expect "codex run refuses --add outside the clone" 2 'inside the clone' "$out" "$s"
out=$(STUB_CODEX_EDIT=1 STUB_CODEX_MSG=$work/msg-plain.txt PATH=$work/gitstub:$work/ghbin:$PATH "$jpdev" codex run --brief "$work/brief.md" --model m --effort low --dir "$cxrepo" 2>&1) && s=0 || s=$?
expect "codex run needs --repo to open the pull request" 2 '--repo OWNER/NAME is needed' "$out" "$s"
if [ ! -e "$STUB_CODEX_ARGS" ]; then ok "a run refused for its flags did not start codex"; else bad "a run refused for its flags did not start codex"; fi
git -C "$cxrepo" switch -q main
out=$(STUB_CODEX_EDIT=1 cx_run) && s=0 || s=$?
expect "codex run refuses to commit on main" 2 'make a work branch first' "$out" "$s"
if [ ! -e "$STUB_CODEX_ARGS" ]; then ok "a run refused for the branch did not start codex"; else bad "a run refused for the branch did not start codex"; fi
git -C "$cxrepo" switch -q work
cx_reset
printf 'stale\n' > "$cxrepo/msg.txt"
out=$(STUB_CODEX_EDIT=1 cx_run --no-push) && s=0 || s=$?
expect "a msg.txt left by an earlier run is not used" 1 'wrote no msg.txt' "$out" "$s"

# carry: a clean merge is signed and pushed; a conflict uses the generated Codex brief
mkdir -p "$work/carrybin"
cat > "$work/carrybin/gh" <<'STUB'
#!/usr/bin/env bash
if [ "${1:-}" = pr ] && [ "${2:-}" = view ]; then printf '%s\tmain\n' "$STUB_CARRY_BRANCH"; exit 0; fi
exit 1
STUB
chmod +x "$work/carrybin/gh"
carry_origin=$work/carry-origin.git
carry_seed=$work/carry-seed
carry_base=$work/carry-base
carry_repo=$work/carry-repo
git init -q --bare -b main "$carry_origin"
git init -q -b main "$carry_seed"
printf '# Rules\n' > "$carry_seed/AGENTS.md"
printf 'base\n' > "$carry_seed/file.txt"
git -C "$carry_seed" add .
git -C "$carry_seed" commit -q -m base
git -C "$carry_seed" remote add origin "$carry_origin"
git -C "$carry_seed" push -q origin main
git -C "$carry_seed" switch -q -c feature
printf 'branch\n' > "$carry_seed/branch.txt"
git -C "$carry_seed" add branch.txt
git -C "$carry_seed" commit -q -m branch
git -C "$carry_seed" push -q origin feature
git -C "$carry_seed" switch -q main
printf 'main\n' > "$carry_seed/main.txt"
git -C "$carry_seed" add main.txt
git -C "$carry_seed" commit -q -m main
git -C "$carry_seed" push -q origin main
git clone -q "$carry_origin" "$carry_base"
out=$(STUB_CARRY_BRANCH=feature PATH=$work/carrybin:$work/codexbin:$oldpath "$jpdev" carry --pr 1 --model m --effort low --dir "$carry_repo" --worktree "$carry_base" 2>&1) && s=0 || s=$?
expect "carry without conflicts signs and pushes the merge" 0 'jpdev carry: pushed feature' "$out" "$s"
if [ -d "$carry_repo" ]; then ok "carry can make a worktree for the pull-request branch"; else bad "carry can make a worktree for the pull-request branch"; fi
msg=$(git -C "$carry_repo" log -1 --format=%B)
expect "the clean carry commit is signed off" 0 '^Signed-off-by: Test <test@example.com>$' "$msg" 0
if [ "$(git --git-dir="$carry_origin" rev-parse feature)" = "$(git -C "$carry_repo" rev-parse HEAD)" ]; then ok "the clean carry reaches origin"; else bad "the clean carry reaches origin"; fi

conflict_origin=$work/conflict-origin.git
conflict_seed=$work/conflict-seed
conflict_repo=$work/conflict-repo
git init -q --bare -b main "$conflict_origin"
git init -q -b main "$conflict_seed"
printf '# Rules\n' > "$conflict_seed/AGENTS.md"
printf 'base\n' > "$conflict_seed/conflict.txt"
git -C "$conflict_seed" add .
git -C "$conflict_seed" commit -q -m base
git -C "$conflict_seed" remote add origin "$conflict_origin"
git -C "$conflict_seed" push -q origin main
git -C "$conflict_seed" switch -q -c conflict-work
printf 'branch\n' > "$conflict_seed/conflict.txt"
git -C "$conflict_seed" commit -qam branch
git -C "$conflict_seed" push -q origin conflict-work
git -C "$conflict_seed" switch -q main
printf 'main\n' > "$conflict_seed/conflict.txt"
git -C "$conflict_seed" commit -qam main
git -C "$conflict_seed" push -q origin main
git clone -q --branch conflict-work "$conflict_origin" "$conflict_repo"
codex_args
out=$(STUB_CARRY_BRANCH=conflict-work STUB_CODEX_RESOLVE=conflict.txt STUB_CODEX_MSG=$work/msg-plain.txt \
  PATH=$work/carrybin:$work/codexbin:$oldpath "$jpdev" carry --pr 2 --model m --effort low --dir "$conflict_repo" 2>&1) && s=0 || s=$?
expect "carry with conflicts starts the Codex no-PR path" 0 'jpdev codex run: pushed conflict-work' "$out" "$s"
if grep -qF 'conflict.txt' "$conflict_repo/.jpdev/output/carry-brief.md" && grep -qF "with main's additions" "$conflict_repo/.jpdev/output/carry-brief.md"; then ok "the carry brief names conflicts and the ordering rule"; else bad "the carry brief names conflicts and the ordering rule"; fi
if has_arg exec; then ok "the conflicted carry starts codex"; else bad "the conflicted carry starts codex"; fi

# the brief template
out=$("$jpdev" codex brief-template 2>&1) && s=0 || s=$?
if [ "$out" = "$(cat "$kit/templates/codex-brief.md")" ]; then ok "brief-template prints templates/codex-brief.md"; else bad "brief-template prints templates/codex-brief.md"; fi
expect "the brief template tells codex to write msg.txt" 0 'msg\.txt' "$out" "$s"
expect "the brief template tells codex to write pr.md" 0 'pr\.md' "$out" "$s"
expect "the brief template tells codex not to commit" 0 'do not run .git commit.' "$out" "$s"
out=$("$jpdev" codex check-brief --build "$kit/templates/codex-brief.md" 2>&1) && s=0 || s=$?
expect "the brief template passes check-brief --build" 0 'no word of the filter list' "$out" "$s"
unset STUB_GIT_ARGS STUB_GH_CALLS STUB_GH_ARGS STUB_GH_BODY GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
PATH=$oldpath
unset STUB_CODEX_ARGS STUB_CODEX_CWD STUB_CODEX_STDIN STUB_CODEX_ENV

# --- env
printf 'JPDEV_NODE_RSS_MB=4321\nJPDEV_GO_TIMEOUT_S=99\n' > "$XDG_CONFIG_HOME/jpdev.env.tmp"
mkdir -p "$XDG_CONFIG_HOME/jpdev"; mv "$XDG_CONFIG_HOME/jpdev.env.tmp" "$XDG_CONFIG_HOME/jpdev/env"
out=$(JPDEV_GO_TIMEOUT_S=55 "$jpdev" env 2>&1) && s=0 || s=$?
expect "env reports a config-file value as such" 0 'JPDEV_NODE_RSS_MB +4321 +config file' "$out" "$s"
expect "env lets the environment win over the config file" 0 'JPDEV_GO_TIMEOUT_S +55 +environment' "$out" "$s"
expect "env reports a default as such" 0 'JPDEV_PY_ULIMIT_KB +4000000 +default' "$out" "$s"
expect "env reports the codex sandbox default" 0 'JPDEV_CODEX_SANDBOX +workspace-write +default' "$out" "$s"
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
