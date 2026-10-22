#!/usr/bin/env bash
# from judgment-pack-devkit v0.5.0 (templates/check.sh)
# scripts/dev/check.sh [--setup] [--only a,b] [--skip a,b] [--all] [--manifest FILE]
# Runs the checks of dev.json in order and prints one summary block; exit status = failures.
# Stops at the first failure unless --all. --setup runs the manifest's setup steps instead.
# A step whose requires_env variable is empty is skipped, and said to be; when CI is set that is a
# failure unless the step is marked optional: true. Standard library python3 only. jpdev sets JPDEV_WRAP to add its caps around each step.
root=${JPDEV_ROOT:-$(cd "$(dirname "$0")" && git rev-parse --show-toplevel)} || exit 2
exec python3 -I - "$root" "$@" <<'PY'
import json, os, re, shutil, signal, subprocess, sys, time
from pathlib import Path
root, args = sys.argv[1], sys.argv[2:]
opt = {'only': set(), 'skip': set(), 'all': False, 'setup': False, 'manifest': root + '/dev.json'}
while args:
    a = args.pop(0)
    if a in ('--only', '--skip'): opt[a[2:]] = set(args.pop(0).split(','))
    elif a == '--manifest': opt['manifest'] = args.pop(0)
    elif a in ('--all', '--setup'): opt[a[2:]] = True
    else: sys.exit('check.sh: unknown argument ' + a)
m = json.load(open(opt['manifest'], encoding='utf-8'))
python = m.get('toolchains', {}).get('python', {})
venv = python.get('venv')
run_env = dict(os.environ)
if venv is not None:
    root_path, path = Path(root).resolve(), Path(venv)
    target = (root_path / path).resolve()
    if (not venv or path.is_absolute() or '..' in path.parts or target == root_path
            or root_path not in target.parents):
        print('check.sh: venv must be a relative child path of the clone', file=sys.stderr)
        sys.exit(2)
    interpreter = target / 'bin' / 'python3'
    if not interpreter.is_file():
        version = python.get('version')
        creator = None
        if version:
            candidate = shutil.which('python' + version)
            def reports_version(path):
                probe = subprocess.run([path, '-c', 'import sys; print("%d.%d" % sys.version_info[:2])'],
                                       text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                return probe.returncode == 0 and probe.stdout.strip() == version
            if candidate and reports_version(candidate): creator = candidate
            if not creator:
                def version_key(path):
                    return tuple(int(part) if part.isdigit() else part for part in path.parent.parent.name.split('.'))
                candidates = sorted((path for path in Path.home().glob('.pyenv/versions/' + version + '.*/bin/python3')
                                     if reports_version(str(path))), key=version_key)
                if candidates: creator = str(candidates[-1])
            if not creator:
                print('check.sh: python %s is not installed (python%s on PATH, or a pyenv version)' %
                      (version, version), file=sys.stderr)
                sys.exit(2)
        else:
            creator = sys.executable
        made = subprocess.run([creator, '-m', 'venv', str(target)])
        if made.returncode:
            print('check.sh: could not make the virtual environment %s with %s' % (venv, creator), file=sys.stderr)
            sys.exit(2)
    run_env['PATH'] = str(target / 'bin') + os.pathsep + run_env.get('PATH', '')
steps = m.get('setup', []) if opt['setup'] else m['checks'] + ([dict(name='parity', **m['parity'])] if 'parity' in m else [])
unknown = (opt['only'] | opt['skip']) - set(s['name'] for s in steps)
if unknown: print('check.sh: no step named ' + ', '.join(sorted(unknown)), file=sys.stderr); sys.exit(2)
wrap, logdir, rows, failed = os.environ.get('JPDEV_WRAP'), os.environ.get('JPDEV_LOGDIR'), [], 0
for c in steps:
    n = c['name']
    if (opt['only'] and n not in opt['only']) or n in opt['skip']: continue
    if failed and not opt['all']: rows.append((n, 'NOT RUN', '', [])); continue
    if c.get('requires_env') and not os.environ.get(c['requires_env']):
        # A skip is a failure under CI (CI is set) unless the step says optional: true.
        if os.environ.get('CI') and not c.get('optional'): failed += 1; rows.append((n, 'FAIL', 'needs %s, which CI must set (or mark the step optional)' % c['requires_env'], []))
        else: rows.append((n, 'SKIP', 'needs ' + c['requires_env'], []))
        continue
    cmd = ['bash', '-c', c['run']]
    if wrap: cmd = [wrap, c.get('toolchain', 'shell'), '--'] + cmd
    tmo = c.get('timeout', 1200)
    t0 = time.time(); print('check: running ' + n, file=sys.stderr, flush=True)
    step_env = dict(run_env, JPDEV_STEP_TIMEOUT=str(tmo))
    p = subprocess.Popen(cmd, cwd=os.path.join(root, c.get('cwd', '.')), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, errors='replace', start_new_session=True, env=step_env)
    try: out, _ = p.communicate(timeout=None if wrap else tmo)
    except subprocess.TimeoutExpired: os.killpg(p.pid, signal.SIGKILL); out = p.communicate()[0] + '\ncheck: stopped for time\n'
    lines, took = out.splitlines(), '%ds' % (time.time() - t0)
    if c.get('toolchain') == 'python' or re.search(r'(^|[^A-Za-z0-9_])python3([^A-Za-z0-9_]|$)', c['run']):
        executable = str(Path(root, venv, 'bin', 'python3')) if venv else shutil.which('python3', path=step_env.get('PATH'))
        if executable:
            found = subprocess.run([executable, '--version'], text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=step_env).stdout.strip()
            took += ', python %s (%s)' % (executable, found)
    if logdir: os.makedirs(logdir, exist_ok=True); open('%s/%s.log' % (logdir, n), 'w').write(out)
    hit = [l.strip() for l in lines if c.get('summary') and re.search(c['summary'], l)]
    note = ['    ' + l for l in (hit if len(hit) <= 3 else ['%d lines matched; last: %s' % (len(hit), hit[-1])])]
    if p.returncode == 0: rows.append((n, 'PASS', took, note)); continue
    failed += 1
    rows.append((n, 'FAIL', '%s, exit %d' % (took, p.returncode), note + ['    --'] + ['    ' + l for l in lines[:40]] + (['    ... %d more lines' % (len(lines) - 40)] if len(lines) > 40 else [])))
print('== %s summary (%s) ==' % ('setup' if opt['setup'] else 'check', os.path.basename(opt['manifest'])))
if not opt['setup'] and 'handover' in m:
    h = m['handover']
    print('handover: boundary %d paths, shared %d paths; see AGENTS.md "Before you hand over"' %
          (len(h.get('boundary_paths', [])), len(h.get('shared_paths', []))))
for n, s, head, extra in rows: print('\n'.join(['%-8s %-24s %s' % (s, n, head)] + extra))
print('== %d passed, %d failed, %d skipped, %d not run ==' % tuple(sum(1 for r in rows if r[1] == k) for k in ('PASS', 'FAIL', 'SKIP', 'NOT RUN')))
sys.exit(min(failed, 255))
PY
