#!/usr/bin/env python3
"""Explicit session disposal seals and conservative, descriptor-relative cleanup (Linux)."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import subprocess
import sys
import time
import uuid

META = '.jpdev-clean'
KINDS = ('worktree', 'review', 'scratch', 'transcript', 'cache')
FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class Refusal(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Refusal(reason)


def relative(path):
    parts = PurePosixPath(path).parts
    require(isinstance(path, str) and path and not path.startswith('/') and
            all(p not in ('.', '..', META, '.jpdev-clean-keep') for p in parts) and
            '/'.join(parts) == path, 'invalid or protected relative path')
    return parts


def identity(st):
    return [st.st_dev, st.st_ino]


def stamp(st):
    return [st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


@contextlib.contextmanager
def directory(path):
    """Open every component without resolving symlinks, including ancestors of roots."""
    path = os.path.abspath(path)
    fd = os.open('/', FLAGS)
    try:
        for component in path.split('/')[1:]:
            new = os.open(component, FLAGS, dir_fd=fd)
            os.close(fd)
            fd = new
        yield fd
    finally:
        os.close(fd)


@contextlib.contextmanager
def descend(fd, parts):
    child = os.dup(fd)
    try:
        for part in parts:
            new = os.open(part, FLAGS, dir_fd=child)
            os.close(child)
            child = new
        yield child
    finally:
        os.close(child)


def read_json(fd, name):
    source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(source) as stream:
        st = os.fstat(stream.fileno())
        require(stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and
                not st.st_mode & 0o022 and st.st_size <= 16 * 1024 * 1024,
                'unsafe ownership record')
        value = json.load(stream)
        require(isinstance(value, dict), 'ownership record must be an object')
        return value


def write_json(fd, name, value):
    temp = '.new-' + uuid.uuid4().hex
    source = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    with os.fdopen(source, 'w') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.rename(temp, name, src_dir_fd=fd, dst_dir_fd=fd)


def file_snapshot(fd, name):
    before = os.stat(name, dir_fd=fd, follow_symlinks=False)
    require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid(), 'file ownership/type unavailable')
    source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(source, 'rb') as stream:
        require(stamp(os.fstat(stream.fileno())) == stamp(before), 'file replaced: ' + name)
        hasher = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
        require(stamp(os.fstat(stream.fileno())) == stamp(before), 'file changed: ' + name)
    require(stamp(os.stat(name, dir_fd=fd, follow_symlinks=False)) == stamp(before), 'file replaced: ' + name)
    return stamp(before) + [hasher.hexdigest()]


def inventory(fd, prefix=''):
    """Never follow symlinks or mounts; reject special files and nested repositories."""
    result = {}
    device = os.fstat(fd).st_dev
    for name in sorted(os.listdir(fd)):
        key = prefix + name
        before = os.stat(name, dir_fd=fd, follow_symlinks=False)
        require(before.st_uid == os.getuid(), 'content ownership unavailable: ' + key)
        require(before.st_dev == device, 'nested mount: ' + key)
        require(not stat.S_ISLNK(before.st_mode), 'symlink: ' + key)
        require(stat.S_ISREG(before.st_mode) or stat.S_ISDIR(before.st_mode), 'special file: ' + key)
        if stat.S_ISDIR(before.st_mode):
            require(name != '.git' or not prefix, 'nested repository: ' + key)
            with descend(fd, (name,)) as child:
                result[key] = stamp(before)
                result.update(inventory(child, key + '/'))
        else:
            require(name != '.git' or not prefix, 'nested repository: ' + key)
            result[key] = file_snapshot(fd, name)
        require(stamp(os.stat(name, dir_fd=fd, follow_symlinks=False)) == stamp(before), 'content changed: ' + key)
    return result


def run(args, cwd):
    try:
        completed = subprocess.run(args, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                                   text=True, timeout=30, env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0',
                                                            'GIT_TERMINAL_PROMPT': '0'})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refusal('verification unavailable: ' + args[0]) from exc
    require(completed.returncode == 0, 'verification failed: ' + ' '.join(args[:3]))
    return completed.stdout.strip()


def within(path, roots):
    if not isinstance(path, str) or not os.path.isabs(path) or os.path.normpath(path) != path:
        return False
    return any(path == root or path.startswith(root + os.sep) for root in roots)


def mount_check(path):
    require(sys.platform == 'linux', 'mount verification requires Linux procfs')
    with open('/proc/self/mountinfo') as stream:
        for line in stream:
            fields = line.split()
            require(len(fields) >= 6, 'mount evidence unavailable')
            mountpoint = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields[4])
            require(not within(mountpoint, [path]), 'mounted content: ' + mountpoint)


def process_check(paths):
    """A namespaced or unreadable /proc is insufficient evidence of host inactivity."""
    require(sys.platform == 'linux', 'complete process verification requires Linux procfs')
    try:
        # Linux's initial PID namespace inode. A nested namespace can hide processes holding files.
        require(os.readlink('/proc/self/ns/pid') == 'pid:[4026531836]' and
                os.readlink('/proc/1/ns/pid') == 'pid:[4026531836]',
                'process visibility incomplete: initial host PID namespace required')
        require(os.readlink('/proc/self/ns/mnt') == os.readlink('/proc/1/ns/mnt') and
                identity(os.stat('/')) == identity(os.stat('/proc/1/root')),
                'process visibility incomplete: host mount/root view required')
        for pid in os.listdir('/proc'):
            if not pid.isdigit() or int(pid) == os.getpid():
                continue
            try:
                with open('/proc/' + pid + '/stat') as stream:
                    flags = int(stream.read().rsplit(')', 1)[1].split()[6])
                if flags & 0x00200000:  # PF_KTHREAD has no userspace cwd/executable.
                    continue
                require(os.readlink('/proc/' + pid + '/ns/mnt') == os.readlink('/proc/self/ns/mnt') and
                        identity(os.stat('/proc/' + pid + '/root')) == identity(os.stat('/')),
                        'process visibility incomplete for PID ' + pid)
                links = [os.readlink('/proc/' + pid + '/' + item) for item in ('cwd', 'root', 'exe')]
                for name in os.listdir('/proc/' + pid + '/fd'):
                    try:
                        links.append(os.readlink('/proc/' + pid + '/fd/' + name))
                    except FileNotFoundError:
                        continue
                with open('/proc/' + pid + '/cmdline', 'rb') as stream:
                    argv = [p.decode(errors='surrogateescape') for p in stream.read().split(b'\0') if p]
                    links.extend(os.path.abspath(os.path.join(links[0], p.split('=', 1)[-1])) for p in argv)
                with open('/proc/' + pid + '/maps') as stream:
                    links.extend(line.split(None, 5)[5].strip() for line in stream if len(line.split(None, 5)) == 6 and line.split(None, 5)[5].startswith('/'))
                with open('/proc/' + pid + '/environ', 'rb') as stream:
                    for item in stream.read().split(b'\0'):
                        key, _, value = item.partition(b'=')
                        if key in (b'TMPDIR', b'JPDEV_SCRATCH', b'GOCACHE', b'GOMODCACHE', b'npm_config_cache', b'XDG_CACHE_HOME') and value:
                            links.append(os.path.abspath(os.path.join(links[0], value.decode(errors='surrogateescape'))))
                for link in links:
                    if link.endswith(' (deleted)'):
                        link = link[:-10]
                    require(not within(link, paths), 'live PID ' + pid + ': ' + link)
            except FileNotFoundError:
                # A process may exit, but a kernel thread without an exe is still present.
                require(not os.path.exists('/proc/' + pid), 'process evidence unavailable for PID ' + pid)
    except OSError as exc:
        raise Refusal('process visibility unavailable: ' + str(exc)) from exc


def keep_check(rootfd, path):
    try:
        source = os.open('.jpdev-clean-keep', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=rootfd)
    except FileNotFoundError:
        return
    with os.fdopen(source) as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'invalid keep file')
        for line in stream:
            entry = line.strip()
            if not entry or entry.startswith('#'):
                continue
            relative(entry)
            require(not (path == entry or path.startswith(entry + '/') or entry.startswith(path + '/')),
                    'operator keep: ' + entry)


def git_layout(path, roots):
    # Validate Git's indirection before invoking Git, which would otherwise discover metadata
    # beyond the authorized roots. Explicit arguments keep later Git calls on this evidence.
    with directory(path) as fd:
        marker = os.stat('.git', dir_fd=fd, follow_symlinks=False)
        if stat.S_ISDIR(marker.st_mode):
            gitdir = path + '/.git'
        else:
            require(stat.S_ISREG(marker.st_mode), 'invalid Git marker')
            source = os.open('.git', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(source) as stream:
                require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'invalid Git marker')
                pointer = stream.read(4096).strip()
            require(pointer.startswith('gitdir: ') and '\n' not in pointer, 'invalid Git marker')
            gitdir = os.path.abspath(os.path.join(path, pointer[8:]))
    require(within(gitdir, roots), 'Git evidence outside authorized roots')
    with directory(gitdir) as fd:
        try:
            source = os.open('commondir', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except FileNotFoundError:
            common = gitdir
        else:
            with os.fdopen(source) as stream:
                require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'invalid Git common directory marker')
                common = os.path.abspath(os.path.join(gitdir, stream.read(4096).strip()))
    require(within(common, roots), 'Git evidence outside authorized roots')
    with directory(common):
        pass
    return common, gitdir


def git_metadata(gitdir):
    result = {}
    with directory(gitdir) as fd:
        for name in ('HEAD', 'index', 'commondir'):
            try:
                result[name] = file_snapshot(fd, name)
            except FileNotFoundError:
                result[name] = None
    return result


def git_check(path, roots, kind):
    common, gitdir = git_layout(path, roots)
    require(common != gitdir or kind == 'review', 'live base checkout is protected')
    def gitrun(args):
        return run(['git', '--git-dir=' + gitdir, '--work-tree=' + path,
                    '-c', 'core.fsmonitor=false', *args], path)
    worktrees = gitrun(['worktree', 'list', '--porcelain', '-z']).split('\0')
    for item in worktrees:
        if item.startswith('worktree '):
            other = item[9:]
            require(common != gitdir or other == path, 'base still has registered worktrees')
            require(not (other != path and other.startswith(path + '/')), 'nested worktree: ' + other)
    require(not gitrun(['diff', '--name-only', 'HEAD', '--']), 'tracked changes')
    require(not gitrun(['diff', '--cached', '--name-only', '--']), 'tracked index changes')
    # The explicit inventory seal is the disposal evidence for untracked and ignored files.
    gitrun(['status', '--porcelain=v1', '--untracked-files=all', '--ignored'])
    remote = gitrun(['ls-remote', '--refs', 'origin'])
    published = dict(line.split('\t')[::-1] for line in remote.splitlines())
    require(published, 'remote publication evidence unavailable')
    commits = sorted(set(published.values()))
    require(not gitrun(['rev-list', '--all', 'HEAD', '--not', *commits]),
            'unpublished commits (including other refs)')
    branch = gitrun(['branch', '--show-current'])
    head = gitrun(['rev-parse', 'HEAD'])
    if branch:
        upstream = gitrun(['for-each-ref', '--format=%(upstream:remotename) %(upstream:remoteref)',
                        'refs/heads/' + branch]).split()
        require(len(upstream) == 2 and upstream[0] == 'origin' and upstream[1] in published,
                'upstream publication unavailable')
        require(gitrun(['merge-base', head, published[upstream[1]]]) == head,
                'upstream does not contain HEAD')
        try:
            prs = json.loads(run(['gh', 'pr', 'list', '--state', 'all', '--head', branch,
                                  '--json', 'state,headRefOid,headRefName', '--limit', '100',
                                  '--repo', gitrun(['remote', 'get-url', 'origin'])], path))
        except (ValueError, TypeError) as exc:
            raise Refusal('PR evidence unavailable') from exc
        require(isinstance(prs, list) and any(isinstance(pr, dict) and
                pr.get('state') in ('MERGED', 'CLOSED') and pr.get('headRefName') == branch and
                pr.get('headRefOid') == head for pr in prs), 'PR is not verified merged or closed')
    return {'common': common, 'gitdir': gitdir, 'head': head, 'remote': remote, 'branch': branch,
            'refs': gitrun(['for-each-ref', '--format=%(refname) %(objectname)']),
            'metadata': git_metadata(gitdir)}


class Root:
    def __init__(self, path, fd):
        self.path, self.fd = path, fd
        self.identity = identity(os.fstat(fd))
        require(os.fstat(fd).st_uid == os.getuid() and not os.fstat(fd).st_mode & 0o022, 'unsafe root ownership or permissions')
        self.meta = os.open(META, FLAGS, dir_fd=fd)
        require(os.fstat(self.meta).st_uid == os.getuid() and not os.fstat(self.meta).st_mode & 0o022, 'unsafe ownership directory permissions')
        self.meta_identity = identity(os.fstat(self.meta))
        self.owner = read_json(self.meta, 'owner.json')
        require(self.owner.get('version') == 1 and self.owner.get('root') == self.identity and
                isinstance(self.owner.get('session'), str), 'root ownership unavailable')

    def recheck(self):
        with directory(self.path) as now:
            require(identity(os.fstat(now)) == self.identity, 'root replaced')
            require(os.fstat(now).st_uid == os.getuid() and not os.fstat(now).st_mode & 0o022, 'root ownership or permissions changed')
            with descend(now, (META,)) as meta:
                require(identity(os.fstat(meta)) == self.meta_identity, 'ownership directory replaced')
                require(os.fstat(meta).st_uid == os.getuid() and not os.fstat(meta).st_mode & 0o022, 'ownership directory permissions changed')
            require(read_json(self.meta, 'owner.json') == self.owner, 'ownership changed')

    def records(self):
        for name in sorted(os.listdir(self.meta)):
            if re.fullmatch(r'[a-f0-9]{64}\.json', name):
                yield name, read_json(self.meta, name)


def inspect(root, record, roots, age, processes=process_check):
    root.recheck()
    path = record.get('path')
    parts = relative(path)
    require(record.get('version') == 1 and record.get('session') == root.owner['session'] and
            record.get('kind') in KINDS, 'ownership/disposal record unavailable')
    seal_name = hashlib.sha256(path.encode()).hexdigest() + '.json'
    require(read_json(root.meta, seal_name) == record, 'disposal seal changed')
    keep_check(root.fd, path)
    full = root.path + '/' + path
    mount_check(full)
    require(not within(os.getcwd(), [full]) and full != os.path.expanduser('~') and
            not any(r == full or r.startswith(full + '/') for r in roots), 'protected live checkout or root')
    with descend(root.fd, parts[:-1]) as parent:
        st = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        require(identity(st) == record.get('identity'), 'candidate replaced')
        require(st.st_uid == os.getuid(), 'candidate ownership changed')
        require(stat.S_ISDIR(st.st_mode) or (record['kind'] == 'transcript' and stat.S_ISREG(st.st_mode)), 'candidate must be a real directory or transcript file')
        if stat.S_ISDIR(st.st_mode):
            with descend(parent, parts[-1:]) as child:
                contents = inventory(child)
        else:
            contents = {'': file_snapshot(parent, parts[-1])}
    require(contents == record.get('inventory'), 'content changed or lacks explicit disposal evidence')
    newest = max([record.get('sealed', time.time()), st.st_mtime] + [v[4] / 1e9 for v in contents.values()])
    require(time.time() - newest >= age, 'younger than age threshold')
    # A repository marker is allowed only at the candidate root, and only for Git-aware classes.
    is_git = '.git' in contents
    git = None
    if record['kind'] in ('worktree', 'review') and is_git:
        git = git_check(full, roots, record['kind'])
    else:
        require(not any(PurePosixPath(p).name == '.git' for p in contents), 'nested worktree or repository')
        require(record['kind'] != 'worktree', 'worktree evidence missing')
    if record['kind'] in ('scratch', 'cache'):
        base = record.get('base')
        require(isinstance(base, str) and within(base, roots), 'base evidence outside authorized roots or missing')
        with directory(base):
            pass
        common, gitdir = git_layout(base, roots)
        require(common == gitdir, 'base must be the main checkout')
        lines = run(['git', '--git-dir=' + gitdir, '--work-tree=' + base,
                     'worktree', 'list', '--porcelain'], base).splitlines()
        users = []
        for line in lines:
            if not line.startswith('worktree '):
                continue
            user = line[9:]
            require(within(user, roots), 'worktree evidence outside authorized roots')
            try:
                with directory(user):
                    pass
                users.append(user)
            except FileNotFoundError:
                # Absence is established only under an authorized, traversable parent.
                require(within(user, roots), 'missing worktree evidence outside authorized roots')
                with directory(os.path.dirname(user)):
                    pass
        if record['kind'] == 'cache':
            require(users == [base], 'base still has worktree users')
        else:
            removed = record.get('removed')
            require(isinstance(removed, str) and within(removed, roots), 'associated worktree path unavailable')
            with directory(os.path.dirname(removed)) as removed_parent:
                try:
                    os.stat(os.path.basename(removed), dir_fd=removed_parent, follow_symlinks=False)
                    absent = False
                except FileNotFoundError:
                    absent = True
            require(absent and removed not in users, 'associated worktree is not removed')
    processes([full] + ([git['gitdir']] if git else []))
    return contents, git


def erase(fd, expected, prefix='', before_unlink=None):
    require(sorted(os.listdir(fd)) == sorted(p[len(prefix):] for p in expected
            if p.startswith(prefix) and '/' not in p[len(prefix):]), 'directory changed during removal')
    for name in sorted(os.listdir(fd)):
        key = prefix + name
        before = os.stat(name, dir_fd=fd, follow_symlinks=False)
        require(stamp(before) == expected[key][:6], 'entry changed during removal: ' + key)
        if stat.S_ISDIR(before.st_mode):
            with descend(fd, (name,)) as child:
                erase(child, expected, key + '/', before_unlink)
            require(identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) == identity(before), 'directory replaced during removal')
            if before_unlink:
                before_unlink()
            os.rmdir(name, dir_fd=fd)
        else:
            if before_unlink:
                before_unlink()
            require(stamp(os.stat(name, dir_fd=fd, follow_symlinks=False)) == expected[key][:6], 'file replaced during removal')
            os.unlink(name, dir_fd=fd)


def remove(root, record, roots, age, processes=process_check):
    contents, git = inspect(root, record, roots, age, processes)
    parts = relative(record['path'])
    token = '.jpdev-clean-removing-' + uuid.uuid4().hex
    with descend(root.fd, parts[:-1]) as parent:
        root.recheck()
        # Move into a private sibling name, then verify the moved inode and complete inventory.
        os.rename(parts[-1], token, src_dir_fd=parent, dst_dir_fd=parent)
        moved = root.path + '/' + '/'.join((*parts[:-1], token))
        try:
            mount_check(moved)
            st = os.stat(token, dir_fd=parent, follow_symlinks=False)
            require(identity(st) == record['identity'], 'candidate replaced during quarantine')
            if stat.S_ISREG(st.st_mode):
                moved_file = file_snapshot(parent, token)
                require(moved_file[:5] + moved_file[6:] == contents[''][:5] + contents[''][6:], 'content changed during quarantine')
                root.recheck()
                require(read_json(root.meta, hashlib.sha256(record['path'].encode()).hexdigest() + '.json') == record, 'disposal seal changed')
                keep_check(root.fd, record['path'])
                processes([moved, root.path + '/' + record['path']])
                with descend(root.fd, parts[:-1]) as current_parent:
                    require(identity(os.fstat(current_parent)) == identity(os.fstat(parent)), 'parent replaced')
                require(file_snapshot(parent, token) == moved_file, 'file replaced during removal')
                os.unlink(token, dir_fd=parent)
                return
            with descend(parent, (token,)) as child:
                require(inventory(child) == contents, 'content changed during quarantine')
                if git:
                    expected_git = {key: (moved + val[len(root.path + '/' + record['path']):]
                                          if key in ('common', 'gitdir') and
                                          within(val, [root.path + '/' + record['path']]) else val)
                                    for key, val in git.items()}
                    after = git_check(moved, roots, record['kind'])
                    require(after == expected_git, 'Git state changed during quarantine')
                keep_check(root.fd, record['path'])
                root.recheck()
                def check():
                    root.recheck()
                    mount_check(moved)
                    if git and not within(after['gitdir'], [moved]):
                        require(git_metadata(after['gitdir']) == after['metadata'] and
                                run(['git', '--git-dir=' + after['gitdir'], 'for-each-ref',
                                     '--format=%(refname) %(objectname)'], root.path) == after['refs'],
                                'Git state changed during removal')
                    require(read_json(root.meta, hashlib.sha256(record['path'].encode()).hexdigest() + '.json') == record, 'disposal seal changed')
                    keep_check(root.fd, record['path'])
                    with descend(root.fd, parts[:-1]) as current_parent:
                        require(identity(os.fstat(current_parent)) == identity(os.fstat(parent)), 'parent replaced')
                    processes([moved, root.path + '/' + record['path']] + ([git['gitdir']] if git else []))
                check()
                erase(child, contents, before_unlink=check)
            require(identity(os.stat(token, dir_fd=parent, follow_symlinks=False)) == record['identity'], 'quarantine replaced')
            os.rmdir(token, dir_fd=parent)
        except BaseException:
            if not os.path.lexists(root.path + '/' + record['path']):
                os.rename(token, parts[-1], src_dir_fd=parent, dst_dir_fd=parent)
            raise
    # Git administration is deliberately retained: pruning can touch unrelated worktrees.


def duration(text):
    match = re.fullmatch(r'(\d+)([smhdw])', text)
    if not match:
        raise argparse.ArgumentTypeError('duration must be an integer followed by s, m, h, d or w')
    return int(match[1]) * dict(s=1, m=60, h=3600, d=86400, w=604800)[match[2]]


def initialize(path, session):
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{7,79}', session), 'session token must be 8..80 letters, digits, underscores or hyphens')
    if not os.path.exists(path):
        os.mkdir(path, 0o700)
    with directory(path) as fd:
        require(not os.listdir(fd), 'init requires an empty session-created root')
        require(os.fstat(fd).st_uid == os.getuid() and not os.fstat(fd).st_mode & 0o022, 'unsafe root ownership or permissions')
        os.mkdir(META, 0o700, dir_fd=fd)
        with descend(fd, (META,)) as meta:
            write_json(meta, 'owner.json', {'version': 1, 'session': session, 'root': identity(os.fstat(fd))})


def seal(root, args):
    require(root.owner['session'] == args.session, 'session ownership mismatch')
    parts = relative(args.path)
    mount_check(root.path + '/' + args.path)
    keep_check(root.fd, args.path)
    with descend(root.fd, parts[:-1]) as parent:
        st = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if args.kind == 'transcript' and stat.S_ISREG(st.st_mode):
            contents = {'': file_snapshot(parent, parts[-1])}
        else:
            with descend(parent, parts[-1:]) as child:
                contents = inventory(child)
        ident = identity(st)
    for _, existing in root.records():
        old = existing['path']
        require(not (old != args.path and (old.startswith(args.path + '/') or args.path.startswith(old + '/'))),
                'overlapping disposal records')
    value = {'version': 1, 'session': args.session, 'path': args.path, 'kind': args.kind,
             'identity': ident, 'inventory': contents, 'sealed': time.time()}
    if args.base:
        value['base'] = os.path.abspath(args.base)
    if args.removed_worktree:
        value['removed'] = os.path.abspath(args.removed_worktree)
    write_json(root.meta, hashlib.sha256(args.path.encode()).hexdigest() + '.json', value)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('action', nargs='?', choices=('init', 'seal'))
    result.add_argument('--root', action='append', default=[], help='explicit root; repeat to authorize Git evidence roots')
    result.add_argument('--older-than', type=duration, default=7 * 86400, metavar='DURATION')
    result.add_argument('--yes', action='store_true', help='remove verified candidates (default: dry run)')
    result.add_argument('--session')
    result.add_argument('--path')
    result.add_argument('--kind', choices=KINDS)
    result.add_argument('--base')
    result.add_argument('--removed-worktree')
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    roots = list(dict.fromkeys(os.path.abspath(p) for p in args.root))
    if args.action:
        require(len(roots) == 1 and args.session and not args.yes, 'init/seal require one root and a session, without --yes')
        if args.action == 'init':
            initialize(roots[0], args.session)
            print('initialized session cleanup root')
            return 0
        require(args.path and args.kind, 'seal requires --path and --kind')
    else:
        require(not any((args.session, args.path, args.kind, args.base, args.removed_worktree)), 'seal options require seal action')
    total = size = removed = refused = 0
    for path in roots:
        try:
            with directory(path) as fd:
                try:
                    root = Root(path, fd)
                except FileNotFoundError:
                    if args.action:
                        raise Refusal('root has no session ownership record')
                    print(json.dumps({'root': path, 'outcome': 'refused', 'reason': 'unmarked root; no ownership/disposal evidence'}))
                    refused += 1
                    continue
                try:
                    fcntl.flock(root.meta, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    if args.action:
                        seal(root, args)
                        print('sealed explicit session disposal inventory')
                        return 0
                    records = list(root.records())
                    for name, record in records:
                        try:
                            contents, _ = inspect(root, record, roots, args.older_than)
                            bytes_used = sum(v[3] for v in contents.values() if stat.S_ISREG(v[2]))
                            total += 1
                            size += bytes_used
                            print(json.dumps({'root': path, 'path': record['path'], 'bytes': bytes_used,
                                              'reason': 'sealed ' + record['kind'], 'outcome': 'candidate'}), flush=True)
                            if args.yes:
                                remove(root, record, roots, args.older_than)
                                os.unlink(name, dir_fd=root.meta)
                                removed += 1
                                print(json.dumps({'root': path, 'path': record['path'], 'outcome': 'removed'}), flush=True)
                        except (Refusal, OSError, ValueError, KeyError, TypeError) as exc:
                            refused += 1
                            print(json.dumps({'root': path, 'path': record.get('path'), 'outcome': 'refused', 'reason': str(exc)}), flush=True)
                    # Show unmarked top-level state without recursively discovering or claiming it.
                    covered = {r['path'].split('/')[0] for _, r in records}
                    for entry in sorted(set(os.listdir(fd)) - covered - {META, '.jpdev-clean-keep'}):
                        refused += 1
                        print(json.dumps({'root': path, 'path': entry, 'outcome': 'refused', 'reason': 'no explicit disposal seal'}))
                finally:
                    os.close(root.meta)
        except FileNotFoundError:
            if args.action:
                raise Refusal('session root or ownership evidence is absent')
            try:
                with directory(path):
                    pass
            except FileNotFoundError:
                print(json.dumps({'root': path, 'outcome': 'absent'}))
            else:
                refused += 1
                print(json.dumps({'root': path, 'outcome': 'refused', 'reason': 'ownership evidence disappeared'}))
        except (Refusal, OSError, ValueError, KeyError, TypeError) as exc:
            if args.action:
                raise Refusal(str(exc)) from exc
            refused += 1
            print(json.dumps({'root': path, 'outcome': 'refused', 'reason': str(exc)}))
    print(json.dumps({'candidates': total, 'bytes': size, 'removed': removed, 'refused': refused,
                      'mode': 'remove' if args.yes else 'dry-run'}))
    return 1 if refused else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Refusal, OSError, ValueError, KeyError, TypeError) as error:
        print('jpdev clean: refused: ' + str(error), file=sys.stderr)
        sys.exit(2)
