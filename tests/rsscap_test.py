"""Actual RSS guard/wrapper entrypoints; bounded cooperative process-session probes."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUARD = Path(os.environ.get('RSSCAP_HELPER', ROOT / 'lib/rsscap.sh'))


class SessionCap(unittest.TestCase):
    def run_guard(self, command, memory=24, seconds=6, env=None):
        # Files, not pipes: an escaped child retaining stdout must not delay the
        # parent's wait until it exits naturally and conceal failed cleanup.
        with tempfile.TemporaryFile(mode='w+') as out, tempfile.TemporaryFile(mode='w+') as err:
            result = subprocess.run([str(GUARD), str(memory), str(seconds), '--', *command],
                                    stdout=out, stderr=err, timeout=12, env=env)
            out.seek(0)
            err.seek(0)
            result.stdout, result.stderr = out.read(), err.read()
            return result

    def assert_stopped(self, result, code):
        for line in result.stdout.splitlines():
            if line.startswith('child='):
                pid = int(line.split('=')[1])
                # An orphan can be a zombie until the system reaps it. It must not run.
                state = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)],
                                       capture_output=True, text=True, check=False).stdout.strip()
                stopped = not state or state.startswith('Z')
                if not stopped:
                    # Cleanup even a deliberately broken guard's bounded probe.
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                self.assertTrue(stopped, (pid, state))
        self.assertEqual(result.returncode, code, result.stderr)

    def test_nested_timeout_memory_and_cleanup(self):
        probe = ('import os,time; print("separate="+str(os.getpgrp()!=os.getsid(0)),flush=True); print("child="+str(os.getpid()),flush=True); '
                 'held=bytearray(64*1024*1024); time.sleep(2)')
        result = self.run_guard(['bash', '-c', '"$@"; code=$?; exit "$code"',
                                 'probe', 'timeout', '-k', '1', '5', sys.executable, '-c', probe])
        self.assert_stopped(result, 137)
        self.assertIn('STOPPED for memory', result.stderr)
        self.assertIn('separate=True', result.stdout)

    def test_nested_timeout_wall_limit_and_cleanup(self):
        probe = 'import os,time; print("child="+str(os.getpid()),flush=True); time.sleep(3)'
        result = self.run_guard(['bash', '-c', '"$@"; code=$?; exit "$code"',
                                 'probe', 'timeout', '5', sys.executable, '-c', probe], memory=256, seconds=1)
        self.assert_stopped(result, 124)

    def test_session_survives_its_leader(self):
        probe = ('import os,time; print("child="+str(os.getpid()),flush=True); '
                 'held=bytearray(64*1024*1024); time.sleep(2)')
        result = self.run_guard(['bash', '-c', 'timeout 5 "$@" & exit 7', 'probe', sys.executable, '-c', probe])
        self.assert_stopped(result, 137)

    def test_memory_is_summed_across_groups(self):
        probe = ('import os,time; print("child="+str(os.getpid()),flush=True); '
                 'held=bytearray(16*1024*1024); time.sleep(2)')
        parent = ('import subprocess,sys; children=[subprocess.Popen(["timeout","5",sys.executable,"-c",%r]) '
                  'for _ in range(2)]; [p.wait() for p in children]') % probe
        self.assert_stopped(self.run_guard([sys.executable, '-c', parent], memory=40), 137)

    def test_new_session_is_an_explicit_limit(self):
        # Cooperative guard only: a detached child is outside its accounting. Wait
        # for that child here so even this limitation probe leaves no live process.
        probe = 'import time; held=bytearray(64*1024*1024); time.sleep(1)'
        parent = ('import subprocess,sys; p=subprocess.Popen(["setsid",sys.executable,"-c",%r]); '
                  'raise SystemExit(p.wait())') % probe
        self.assertEqual(self.run_guard([sys.executable, '-c', parent]).returncode, 0)

    def test_status_and_invalid_limits(self):
        self.assertEqual(self.run_guard(['bash', '-c', 'exit 7']).returncode, 7)
        self.assertEqual(self.run_guard(['true'], memory=0).returncode, 2)
        self.assertEqual(self.run_guard(['true'], seconds=-1).returncode, 2)

    def test_signal_cleans_other_process_groups(self):
        with tempfile.TemporaryDirectory(prefix='rsscap-signal-') as folder:
            pidfile = Path(folder) / 'child'
            probe = ('import os,time,pathlib; pathlib.Path(%r).write_text(str(os.getpid())); '
                     'time.sleep(4)') % str(pidfile)
            errfile = tempfile.TemporaryFile(mode='w+')
            self.addCleanup(errfile.close)
            process = subprocess.Popen([str(GUARD), '256', '8', '--', 'bash', '-c', '"$@"; code=$?; exit "$code"', 'probe', 'timeout', '6',
                                        sys.executable, '-c', probe], stdout=subprocess.DEVNULL,
                                       stderr=errfile, text=True)
            try:
                deadline = time.monotonic() + 3
                while not pidfile.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(pidfile.exists(), 'child did not start')
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=8)
                errfile.seek(0)
                stderr = errfile.read()
                result = subprocess.CompletedProcess([], process.returncode,
                                                     'child=' + pidfile.read_text(), stderr)
                self.assert_stopped(result, 143)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=8)

    def test_go_wrapper_keeps_lock_cache_readonly_and_removes_vm_cap(self):
        with tempfile.TemporaryDirectory(prefix='rsscap-wrapper-') as folder:
            env = dict(os.environ, JPDEV_SCRATCH=folder, JPDEV_LOCK=folder + '/heavy.lock',
                       XDG_CONFIG_HOME=folder, JPDEV_GO_ULIMIT_KB='unlimited',
                       JPDEV_STEP_TIMEOUT='5', JPDEV_ROOT=str(ROOT))
            script = '''
                test "$GOFLAGS" = -mod=readonly || exit 90
                case "$GOCACHE" in "$JPDEV_SCRATCH"/gocache/*) ;; *) exit 91;; esac
                test "$(ulimit -v)" = unlimited || exit 92
                if flock -n "$JPDEV_LOCK" true; then exit 93; fi
                exec "$@"
            '''
            probe = ('import os,time; print("child="+str(os.getpid()),flush=True); '
                     'held=bytearray(64*1024*1024); time.sleep(2)')
            command = [str(ROOT / 'lib/wrap.sh'), 'go', '--', 'bash', '-c', script,
                       'probe', sys.executable, '-c', probe]
            result = self.run_guard(command, env=env)
            self.assert_stopped(result, 137)
            unlocked = subprocess.run(['flock', '-n', env['JPDEV_LOCK'], 'true'], check=False)
            self.assertEqual(unlocked.returncode, 0)


if __name__ == '__main__':
    unittest.main()
