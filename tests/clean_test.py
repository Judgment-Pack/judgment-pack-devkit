#!/usr/bin/env python3
"""Hand-built disposal fixtures. All deletions are confined to this run's temporary root."""
import contextlib
import importlib.util
import io
import hashlib
import stat
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

KIT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('JPDEV_CLEAN_SOURCE', KIT / 'lib/clean.py'))
spec = importlib.util.spec_from_file_location('clean', SOURCE)
clean = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clean)


class Cleanup(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='clean-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / 'session'
        clean.initialize(str(self.root), 'session-test')
        self.outside = self.home / 'outside'
        self.outside.mkdir()
        (self.outside / 'keep').write_text('operator evidence')
        self.rootctx = clean.directory(str(self.root))
        self.fd = self.rootctx.__enter__()
        self.addCleanup(self.rootctx.__exit__, None, None, None)
        self.owner = clean.Root(str(self.root), self.fd)
        self.addCleanup(os.close, self.owner.meta)
        self.roots = [str(self.root)]

    def git(self, *args, cwd=None):
        env = {**os.environ, 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_SYSTEM': os.devnull,
               'GIT_AUTHOR_NAME': 'Fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
               'GIT_COMMITTER_NAME': 'Fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'}
        result = subprocess.run(['git', *args], cwd=cwd or self.root, env=env,
                                text=True, capture_output=True, check=True)
        return result.stdout.strip()

    def candidate(self, kind='review', path='old', base=None, removed=None):
        folder = self.root / path
        folder.mkdir(parents=True, exist_ok=True)
        if not (folder / '.git').exists():
            (folder / 'report').write_text('session-created evidence')
        args = clean.parser().parse_args(['seal', '--root', str(self.root), '--session', 'session-test',
                                         '--path', path, '--kind', kind])
        args.base, args.removed_worktree = base, removed
        clean.seal(self.owner, args)
        record = next(r for _, r in self.owner.records() if r['path'] == path)
        return folder, record

    def remove(self, record, processes=lambda paths: None):
        clean.remove(self.owner, record, self.roots, 0, processes)

    def refused(self, record, reason, processes=lambda paths: None):
        with self.assertRaisesRegex((clean.Refusal, OSError), reason):
            self.remove(record, processes)
        self.assertTrue((self.root / record['path']).exists())
        self.assertEqual((self.outside / 'keep').read_text(), 'operator evidence')

    def repository(self, branch=True, review=False):
        base = self.root / 'base'
        remote = self.root / 'origin.git'
        self.git('init', '--bare', str(remote))
        self.git('init', '-b', 'main', str(base))
        (base / 'file').write_text('published')
        self.git('add', '.', cwd=base)
        self.git('commit', '-qm', 'published fixture', cwd=base)
        self.git('remote', 'add', 'origin', str(remote), cwd=base)
        self.git('push', '-qu', 'origin', 'main', cwd=base)
        folder = self.root / 'old'
        if review:
            self.git('clone', str(remote), str(folder))
            self.git('checkout', '--detach', 'origin/main', cwd=folder)
        elif branch:
            self.git('worktree', 'add', '-b', 'topic', str(folder), cwd=base)
            self.git('push', '-qu', 'origin', 'topic', cwd=folder)
        else:
            self.git('worktree', 'add', '--detach', str(folder), cwd=base)
        return folder, base, remote

    @contextlib.contextmanager
    def pr(self, state='MERGED'):
        original = clean.run
        def command(args, cwd):
            if args[0] == 'gh':
                return json.dumps([{'state': state, 'headRefName': 'topic',
                                    'headRefOid': self.git('rev-parse', 'HEAD', cwd=cwd)}])
            return original(args, cwd)
        with patch.object(clean, 'run', command):
            yield

    def test_safe_classes(self):
        for kind in ('review', 'transcript'):
            with self.subTest(kind=kind):
                folder, record = self.candidate(kind, path=kind)
                self.remove(record)
                self.assertFalse(folder.exists())
        folder, base, _ = self.repository(branch=False)
        _, record = self.candidate('worktree')
        self.remove(record)
        self.assertFalse(folder.exists())
        # Stale Git admin entries are harmless; live worktree directories determine cache use.
        for kind in ('scratch', 'cache'):
            candidate, record = self.candidate(kind, path=kind, base=str(base), removed=str(folder))
            self.remove(record)
            self.assertFalse(candidate.exists())

    def test_closed_and_merged_pr(self):
        self.repository()
        _, record = self.candidate('worktree')
        with self.pr('CLOSED'):
            clean.inspect(self.owner, record, self.roots, 0, lambda paths: None)
        with self.pr():
            self.remove(record)
        self.assertFalse((self.root / 'old').exists())

    def test_review_clone(self):
        self.repository(review=True)
        folder, record = self.candidate('review')
        self.remove(record)
        self.assertFalse(folder.exists())

    def test_attached_review_clone(self):
        folder, _, _ = self.repository(review=True)
        self.git('checkout', '-b', 'topic', '--track', 'origin/main', cwd=folder)
        _, record = self.candidate('review')
        with self.pr():
            self.remove(record)
        self.assertFalse(folder.exists())

    def test_review_base_with_worktrees(self):
        _, base, _ = self.repository(branch=False)
        self.git('checkout', '--detach', cwd=base)
        _, record = self.candidate('review', path='base')
        self.refused(record, 'base still has registered worktrees')

    def test_dry_run_and_absent_root(self):
        folder, record = self.candidate()
        with patch.object(clean, 'process_check', lambda paths: None), contextlib.redirect_stdout(io.StringIO()) as output:
            # Defaults bind at definition, so replace only the live evidence seam here.
            with patch.object(clean, 'inspect', lambda *a: (record['inventory'], None)):
                self.assertEqual(clean.main(['--root', str(self.root), '--older-than', '0s']), 0)
        self.assertTrue(folder.exists())
        self.assertIn('"bytes":', output.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(clean.main([]), 0)
            self.assertEqual(clean.main(['--root', str(self.home / 'absent'), '--yes']), 0)

    def test_age(self):
        _, record = self.candidate()
        with self.assertRaisesRegex(clean.Refusal, 'younger'):
            clean.remove(self.owner, record, self.roots, 86400, lambda paths: None)

    def test_unmarked_and_other_session(self):
        unmarked = self.home / 'unmarked'
        unmarked.mkdir()
        (unmarked / 'historical').write_text('not disposable')
        with self.assertRaisesRegex(clean.Refusal, 'empty'):
            clean.initialize(str(unmarked), 'session-test')
        _, record = self.candidate()
        record['session'] = 'another-session'
        clean.write_json(self.owner.meta, hashlib.sha256(record['path'].encode()).hexdigest() + '.json', record)
        self.refused(record, 'ownership')

    def test_unknown_ignored_untracked_content(self):
        self.repository(branch=False)
        folder, record = self.candidate('worktree')
        self.git('config', 'core.excludesFile', str(folder / 'ignore'), cwd=folder)
        for filename in ('untracked', 'ignored'):
            with self.subTest(filename=filename):
                (folder / 'ignore').write_text('ignored\n')
                (folder / filename).write_text('new evidence')
                self.refused(record, 'disposal evidence')
                (folder / filename).unlink()
                (folder / 'ignore').unlink()
        # Explicit disposal seal allows the known untracked/ignored evidence.
        (folder / 'untracked').write_text('explicitly disposable')
        (folder / '.gitignore').write_text('ignored\n')
        (folder / 'ignored').write_text('explicitly disposable')
        _, record = self.candidate('worktree')
        self.remove(record)
        self.assertFalse(folder.exists())

    def test_tracked_change(self):
        folder, _, _ = self.repository(branch=False)
        (folder / 'file').write_text('changed')
        _, record = self.candidate('worktree')
        self.refused(record, 'tracked changes')

    def test_unpublished_other_ref(self):
        folder, base, _ = self.repository(branch=False)
        self.git('checkout', '-b', 'private', cwd=base)
        (base / 'secret').write_text('unpublished')
        self.git('add', '.', cwd=base)
        self.git('commit', '-qm', 'private fixture', cwd=base)
        # HEAD in the candidate is published; the unpublished commit survives only in another ref.
        _, record = self.candidate('worktree')
        self.refused(record, 'unpublished')
        self.assertTrue(folder.exists())

    def test_missing_upstream_and_open_pr(self):
        folder, _, _ = self.repository()
        self.git('branch', '--unset-upstream', cwd=folder)
        _, record = self.candidate('worktree')
        with self.pr():
            self.refused(record, 'upstream')
        self.git('branch', '--set-upstream-to=origin/topic', cwd=folder)
        with self.pr('OPEN'):
            self.refused(record, 'PR is not verified')

    def test_unavailable_git_remote_pr(self):
        self.repository()
        _, record = self.candidate('worktree')
        original = clean.run
        for target in ('git', 'ls-remote', 'gh'):
            def command(args, cwd):
                if args[0] == target or target in args:
                    raise clean.Refusal('verification unavailable fixture')
                if args[0] == 'gh':
                    return '[]'
                return original(args, cwd)
            with self.subTest(target=target), patch.object(clean, 'run', command):
                self.refused(record, 'verification unavailable')

    def test_keep_and_protected_parent(self):
        _, record = self.candidate(path='parent/old')
        for keep in ('parent', 'parent/old/report'):
            (self.root / '.jpdev-clean-keep').write_text(keep + '\n')
            self.refused(record, 'operator keep')
        (self.root / '.jpdev-clean-keep').unlink()
        self.roots.append(str(self.root / 'parent/old/protected'))
        self.refused(record, 'protected')

    def test_live_checkout(self):
        folder, record = self.candidate()
        with patch.object(clean.os, 'getcwd', lambda: str(folder)):
            self.refused(record, 'protected')

    def test_symlink(self):
        folder, _ = self.candidate()
        (folder / 'link').symlink_to(self.outside, target_is_directory=True)
        with self.assertRaisesRegex(clean.Refusal, 'symlink'):
            self.candidate()
        # A sealed path replaced by a link cannot redirect removal.
        (folder / 'link').unlink()
        _, record = self.candidate()
        folder.rename(self.root / 'saved')
        folder.symlink_to(self.outside, target_is_directory=True)
        with self.assertRaises((clean.Refusal, OSError)):
            self.remove(record)
        self.assertEqual((self.outside / 'keep').read_text(), 'operator evidence')

    def test_escape(self):
        for path in ('../outside', '/outside', 'old/../outside', '.jpdev-clean', 'old//x', ''):
            with self.subTest(path=path), self.assertRaises(clean.Refusal):
                clean.relative(path)

    def test_nested_worktree(self):
        folder, base, _ = self.repository(branch=False)
        _, record = self.candidate('worktree')
        self.git('worktree', 'add', '--detach', str(folder / 'nested'), cwd=base)
        expected = dict(record['inventory'])
        for path in sorted((folder / 'nested').rglob('*')) + [folder / 'nested']:
            st = path.lstat()
            value = [st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns]
            if stat.S_ISREG(st.st_mode):
                value.append(hashlib.sha256(path.read_bytes()).hexdigest())
            expected[str(path.relative_to(folder))] = value
        # This hand-built seal inventory attests even the nested fixture, which remains protected.
        record['inventory'] = expected
        clean.write_json(self.owner.meta, hashlib.sha256(record['path'].encode()).hexdigest() + '.json', record)
        self.refused(record, 'nested repository')
        self.assertTrue((folder / 'nested/file').exists())

    def test_root_replaced(self):
        _, record = self.candidate()
        self.root.rename(self.home / 'saved')
        self.root.mkdir()
        (self.home / 'saved' / clean.META).rename(self.root / clean.META)
        (self.root / 'old').mkdir()
        (self.root / 'old/report').write_text('replacement evidence')
        with self.assertRaisesRegex(clean.Refusal, 'root replaced'):
            self.remove(record)
        self.assertTrue((self.root / 'old/report').exists())
        self.assertTrue((self.home / 'saved/old/report').exists())

    def test_candidate_replaced(self):
        folder, _ = self.candidate()
        (folder / 'report').unlink()
        args = clean.parser().parse_args(['seal', '--root', str(self.root), '--session', 'session-test',
                                         '--path', 'old', '--kind', 'review'])
        clean.seal(self.owner, args)
        record = next(r for _, r in self.owner.records())
        folder.rename(self.root / 'saved')
        folder.mkdir()
        self.refused(record, 'candidate replaced')

    def test_changed_during_quarantine(self):
        folder, record = self.candidate()
        rename = clean.os.rename
        def changed(src, dst, **kwargs):
            rename(src, dst, **kwargs)
            if dst.startswith('.jpdev-clean-removing-'):
                with open(self.root / dst / 'report', 'w') as stream:
                    stream.write('concurrent evidence')
        with patch.object(clean.os, 'rename', changed):
            self.refused(record, 'content changed during quarantine')
        self.assertEqual((folder / 'report').read_text(), 'concurrent evidence')

    def test_live_pid_and_unknown_process_evidence(self):
        folder, record = self.candidate()
        proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], cwd=folder)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.terminate)
        # Keep real /proc data while substituting only initial-namespace visibility evidence.
        readlink = os.readlink
        def host(path, *args, **kwargs):
            if path in ('/proc/self/ns/pid', '/proc/1/ns/pid'):
                return 'pid:[4026531836]'
            if path == '/proc/self/ns/mnt':
                return readlink('/proc/1/ns/mnt')
            return readlink(path, *args, **kwargs)
        with patch.object(clean.os, 'readlink', host):
            self.refused(record, 'live PID ' + str(proc.pid), clean.process_check)
        with patch.object(clean.os, 'readlink', side_effect=PermissionError('fixture')):
            self.refused(record, 'process visibility unavailable', clean.process_check)
        with patch.object(clean.os, 'readlink', return_value='pid:[nested]'):
            self.refused(record, 'process visibility incomplete', clean.process_check)

    def test_cache_live_users_and_scratch_owner(self):
        folder, base, _ = self.repository(branch=False)
        _, record = self.candidate('cache', path='cache', base=str(base))
        self.refused(record, 'worktree users')
        _, record = self.candidate('scratch', path='scratch', base=str(base), removed=str(folder))
        self.refused(record, 'not removed')
        self.git('init', '-b', 'main', str(self.outside))
        _, record = self.candidate('cache', path='bad-cache', base=str(self.outside))
        self.refused(record, 'outside authorized roots')

    def test_transcript_file(self):
        log = self.root / 'transcript.log'
        log.write_text('session transcript')
        args = clean.parser().parse_args(['seal', '--root', str(self.root), '--session', 'session-test',
                                         '--path', 'transcript.log', '--kind', 'transcript'])
        clean.seal(self.owner, args)
        record = next(r for _, r in self.owner.records())
        self.remove(record)
        self.assertFalse(log.exists())

    def test_main_removal_and_error_status(self):
        folder, record = self.candidate()
        inspect, remove = clean.inspect, clean.remove
        def inspect_fixture(*args):
            return inspect(*args[:4], processes=lambda paths: None)
        def remove_fixture(*args):
            return remove(*args, processes=lambda paths: None)
        with patch.object(clean, 'inspect', inspect_fixture), patch.object(clean, 'remove', remove_fixture):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(clean.main(['--root', str(self.root), '--older-than', '0s', '--yes']), 0)
            self.assertFalse(folder.exists())
            self.assertIn('"outcome": "removed"', output.getvalue())
            self.assertIn('"removed": 1', output.getvalue())
            folder, record = self.candidate()
            with patch.object(clean.os, 'unlink', side_effect=PermissionError('fixture denied')):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(clean.main(['--root', str(self.root), '--older-than', '0s', '--yes']), 1)
            self.assertTrue(folder.exists())
            self.assertIn('fixture denied', output.getvalue())

    def test_parent_symlink_after_inspection(self):
        folder, record = self.candidate(path='parent/old')
        original = clean.inspect
        def replace(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.root / 'parent').rename(self.root / 'saved-parent')
            (self.root / 'parent').symlink_to(self.outside, target_is_directory=True)
            return result
        with patch.object(clean, 'inspect', replace):
            with self.assertRaises(OSError):
                self.remove(record)
        self.assertTrue((self.root / 'saved-parent/old/report').exists())
        self.assertTrue((self.outside / 'keep').exists())

    def test_changed_while_erasing(self):
        folder, record = self.candidate()
        original = clean.erase
        def replace(fd, expected, prefix='', before_unlink=None):
            os.rename('report', str(self.root / 'rescued-report'), src_dir_fd=fd)
            return original(fd, expected, prefix, before_unlink)
        with patch.object(clean, 'erase', replace):
            self.refused(record, 'directory changed during removal')
        self.assertTrue((self.root / 'rescued-report').exists())
        self.assertTrue(folder.exists())

    def test_process_starts_during_quarantine(self):
        folder, record = self.candidate()
        calls = []
        def processes(paths):
            calls.append(paths)
            if any('.jpdev-clean-removing-' in path for path in paths):
                raise clean.Refusal('live PID fixture-after-inspection')
        self.refused(record, 'live PID fixture-after-inspection', processes)
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue((folder / 'report').exists())

    def test_git_changes_during_quarantine(self):
        folder, base, _ = self.repository(branch=False)
        _, record = self.candidate('worktree')
        rename = clean.os.rename
        def changed(src, dst, **kwargs):
            rename(src, dst, **kwargs)
            if dst.startswith('.jpdev-clean-removing-'):
                self.git('checkout', '-b', 'private', cwd=base)
                (base / 'private').write_text('concurrent private commit')
                self.git('add', '.', cwd=base)
                self.git('commit', '-qm', 'concurrent fixture', cwd=base)
        with patch.object(clean.os, 'rename', changed):
            self.refused(record, 'unpublished')
        self.assertTrue((folder / 'file').exists())

    def test_root_and_parent_symlink(self):
        folder, record = self.candidate()
        link = self.home / 'linked-root'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            with clean.directory(str(link)) as fd:
                alias = clean.Root(str(link), fd)
                try:
                    clean.remove(alias, record, [str(link)], 0, lambda paths: None)
                finally:
                    os.close(alias.meta)
        self.assertTrue((folder / 'report').exists())

    def test_invalid_duration_and_inventory(self):
        for text in ('', '-1d', '2', '1.5h', 'forever'):
            with self.subTest(text=text), self.assertRaises(Exception):
                clean.duration(text)
        self.assertEqual(clean.duration('2h'), 7200)
        folder, _ = self.candidate()
        os.mkfifo(str(folder / 'fifo'))
        with self.assertRaisesRegex(clean.Refusal, 'special file'):
            self.candidate()

    def test_staged_change(self):
        folder, _, _ = self.repository(branch=False)
        (folder / 'file').write_text('staged change')
        self.git('add', 'file', cwd=folder)
        (folder / 'file').write_text('published')
        _, record = self.candidate('worktree')
        self.refused(record, 'tracked')

    def test_upstream_not_containing_head(self):
        folder, base, _ = self.repository()
        (folder / 'file').write_text('new published commit')
        self.git('add', 'file', cwd=folder)
        self.git('commit', '-qm', 'published topic', cwd=folder)
        self.git('push', '-q', 'origin', 'topic', cwd=folder)
        self.git('branch', '--set-upstream-to=origin/main', cwd=folder)
        _, record = self.candidate('worktree')
        with self.pr():
            self.refused(record, 'upstream does not contain')

    def test_missing_worktree_registration_outside_roots(self):
        folder, base, _ = self.repository(branch=False)
        absent = self.outside / 'absent-worktree'
        self.git('worktree', 'move', str(folder), str(absent), cwd=base)
        self.git('worktree', 'remove', str(absent), cwd=base)
        # Register a worktree outside the authorized root, then remove only its fixture files.
        self.git('worktree', 'add', '--detach', str(absent), cwd=base)
        import shutil
        shutil.rmtree(str(absent))
        _, record = self.candidate('cache', path='cache', base=str(base))
        self.refused(record, 'worktree evidence outside')

    def test_git_evidence_outside_roots(self):
        folder, base, _ = self.repository(branch=False)
        moved = self.outside / 'base'
        self.git('worktree', 'move', str(folder), str(self.root / 'moving'), cwd=base)
        # Narrow authorization to just the worktree's parent; Git metadata remains outside it.
        self.roots = [str(self.root / 'moving')]
        (self.root / 'moving').rename(folder)
        _, record = self.candidate('worktree')
        self.refused(record, 'outside authorized roots')
        self.assertFalse(moved.exists())

    def test_root_permissions_changed(self):
        _, record = self.candidate()
        self.root.chmod(0o777)
        self.addCleanup(self.root.chmod, 0o700)
        self.refused(record, 'root ownership or permissions changed')

    def test_disposal_metadata_changed(self):
        _, record = self.candidate()
        (self.root / clean.META).rename(self.root / 'saved-metadata')
        (self.root / clean.META).mkdir()
        self.refused(record, 'ownership directory replaced')

    def test_parent_replaced_during_quarantine(self):
        _, record = self.candidate(path='parent/old')
        rename = clean.os.rename
        def changed(src, dst, **kwargs):
            rename(src, dst, **kwargs)
            if dst.startswith('.jpdev-clean-removing-'):
                (self.root / 'parent').rename(self.root / 'saved-parent')
                (self.root / 'parent').mkdir()
        with patch.object(clean.os, 'rename', changed):
            with self.assertRaisesRegex(clean.Refusal, 'parent replaced'):
                self.remove(record)
        self.assertTrue((self.root / 'saved-parent/old/report').exists())

    def test_file_replaced_during_erase(self):
        folder, record = self.candidate()
        original = clean.erase
        def changed(fd, expected, prefix='', before_unlink=None):
            def race():
                with open('/proc/self/fd/' + str(fd) + '/report', 'w') as stream:
                    stream.write('new concurrent content')
            return original(fd, expected, prefix, race)
        with patch.object(clean, 'erase', changed):
            self.refused(record, 'file replaced during removal')
        self.assertEqual((folder / 'report').read_text(), 'new concurrent content')

    def test_unverified_upstream_remote(self):
        folder, _, remote = self.repository()
        self.git('remote', 'add', 'unverified', str(remote), cwd=folder)
        self.git('config', 'branch.topic.remote', 'unverified', cwd=folder)
        self.git('fetch', '-q', 'unverified', cwd=folder)
        _, record = self.candidate('worktree')
        with self.pr():
            self.refused(record, 'upstream publication unavailable')

    def test_special_file_cleanup(self):
        folder, record = self.candidate()
        fifo = folder / 'fifo'
        os.mkfifo(str(fifo))
        st = fifo.lstat()
        record['inventory']['fifo'] = [st.st_dev, st.st_ino, st.st_mode, st.st_size,
                                       st.st_mtime_ns, st.st_ctime_ns,
                                       hashlib.sha256(b'').hexdigest()]
        clean.write_json(self.owner.meta, hashlib.sha256(record['path'].encode()).hexdigest() + '.json', record)
        self.refused(record, 'special file')
        self.assertTrue(fifo.exists())

    def test_lock_and_absent_seal(self):
        folder, record = self.candidate()
        inspect, remove = clean.inspect, clean.remove
        clean.fcntl.flock(self.owner.meta, clean.fcntl.LOCK_EX | clean.fcntl.LOCK_NB)
        with patch.object(clean, 'inspect', lambda *args: inspect(*args[:4], processes=lambda paths: None)), \
             patch.object(clean, 'remove', lambda *args: remove(*args, processes=lambda paths: None)):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(clean.main(['--root', str(self.root), '--older-than', '0s', '--yes']), 1)
        self.assertTrue(folder.exists())
        with self.assertRaises(clean.Refusal), contextlib.redirect_stdout(io.StringIO()):
            clean.main(['seal', '--root', str(self.home / 'absent'), '--session', 'session-test',
                        '--path', 'old', '--kind', 'review'])

    def test_host_mount_visibility(self):
        _, record = self.candidate()
        original = os.readlink
        def isolated(path, *args, **kwargs):
            if path in ('/proc/self/ns/pid', '/proc/1/ns/pid'):
                return 'pid:[4026531836]'
            if path == '/proc/self/ns/mnt':
                return 'mnt:[isolated]'
            return original(path, *args, **kwargs)
        def processes(paths):
            with patch.object(clean.os, 'readlink', isolated), patch.object(clean.os, 'listdir', return_value=[]):
                clean.process_check(paths)
        self.refused(record, 'host mount/root view required', processes)

    def test_parent_escape_removal(self):
        st = (self.outside / 'keep').lstat()
        record = {'version': 1, 'session': 'session-test', 'path': '../outside', 'kind': 'review',
                  'identity': [self.outside.stat().st_dev, self.outside.stat().st_ino], 'sealed': 0,
                  'inventory': {'keep': [st.st_dev, st.st_ino, st.st_mode, st.st_size,
                                         st.st_mtime_ns, st.st_ctime_ns,
                                         hashlib.sha256(b'operator evidence').hexdigest()]}}
        clean.write_json(self.owner.meta, hashlib.sha256(record['path'].encode()).hexdigest() + '.json', record)
        with self.assertRaisesRegex(clean.Refusal, 'invalid or protected relative path'):
            self.remove(record)
        self.assertTrue((self.outside / 'keep').exists())

    def test_base_checkout(self):
        folder, base, _ = self.repository(branch=False)
        self.git('worktree', 'remove', str(folder), cwd=base)
        self.git('checkout', '--detach', cwd=base)
        _, record = self.candidate('worktree', path='base')
        self.refused(record, 'live base checkout is protected')
        self.assertTrue((base / 'file').exists())

    def test_changed_seal_during_quarantine(self):
        folder, record = self.candidate()
        rename = clean.os.rename
        def changed(src, dst, **kwargs):
            rename(src, dst, **kwargs)
            if dst.startswith('.jpdev-clean-removing-'):
                replacement = dict(record)
                replacement['sealed'] += 1
                clean.write_json(self.owner.meta, hashlib.sha256(record['path'].encode()).hexdigest() + '.json', replacement)
        with patch.object(clean.os, 'rename', changed):
            self.refused(record, 'disposal seal changed')
        self.assertTrue((folder / 'report').exists())

    def test_changed_metadata_permissions(self):
        _, record = self.candidate()
        metadata = self.root / clean.META
        metadata.chmod(0o777)
        self.addCleanup(metadata.chmod, 0o700)
        self.refused(record, 'ownership directory permissions changed')

    def test_git_changes_during_erase(self):
        folder, base, _ = self.repository(branch=False)
        _, record = self.candidate('worktree')
        original = clean.erase
        def changed(fd, expected, prefix='', before_unlink=None):
            self.git('checkout', '-b', 'private', cwd=base)
            (base / 'secret').write_text('new private evidence')
            self.git('add', '.', cwd=base)
            self.git('commit', '-qm', 'concurrent fixture', cwd=base)
            return original(fd, expected, prefix, before_unlink)
        with patch.object(clean, 'erase', changed):
            self.refused(record, 'Git state changed during removal')
        self.assertTrue((folder / 'file').exists())

    def test_mount_crossing(self):
        folder, record = self.candidate()
        original = open
        def mounts(path, *args, **kwargs):
            if path == '/proc/self/mountinfo':
                return io.StringIO('20 1 0:1 / ' + str(folder / 'report') + ' rw - fixture fixture rw\n')
            return original(path, *args, **kwargs)
        with patch('builtins.open', mounts):
            self.refused(record, 'mounted content')
        self.assertTrue((folder / 'report').exists())

    def test_disappearing_ownership_record(self):
        folder, _ = self.candidate()
        original = clean.Root.records
        def disappear(root):
            for name, record in original(root):
                raise FileNotFoundError('concurrent ownership evidence removal')
                yield name, record
        with patch.object(clean.Root, 'records', disappear), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(clean.main(['--root', str(self.root), '--yes']), 1)
        self.assertIn('ownership evidence disappeared', output.getvalue())
        self.assertTrue((folder / 'report').exists())

    def test_candidate_ownership_changed(self):
        _, record = self.candidate()
        original = clean.os.stat
        def other_owner(path, *args, **kwargs):
            st = original(path, *args, **kwargs)
            if path == 'old':
                fields = {name: getattr(st, name) for name in dir(st) if name.startswith('st_')}
                fields['st_uid'] = os.getuid() + 1
                return SimpleNamespace(**fields)
            return st
        with patch.object(clean.os, 'stat', other_owner):
            self.refused(record, 'candidate ownership changed')

    def test_unlink_failure(self):
        _, record = self.candidate()
        with patch.object(clean.os, 'unlink', side_effect=PermissionError('removal denied')):
            self.refused(record, 'removal denied')


if __name__ == '__main__':
    unittest.main()
