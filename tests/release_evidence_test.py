"""The release evidence gate over handwritten Actions API fixtures; none of this is live evidence.

Every fixture below is written by hand. The refusal classes of docs/ci-evidence.md each have a test
class here; the module is lib/release_evidence.py unless RELEASE_EVIDENCE_HELPER names a copy (a
scratch mutant, the vendored scripts/dev/release_evidence.py).
"""
import base64
import copy
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
HELPER = Path(os.environ.get('RELEASE_EVIDENCE_HELPER', ROOT / 'lib/release_evidence.py'))
_spec = importlib.util.spec_from_file_location('release_evidence', HELPER)
e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e)

SHA = 'a' * 40
OTHER = 'c' * 40  # another commit: in the tests that say so, one with the same tree
TAG_OBJECT = 't' * 40
REPO = 'example/project'
REPO_ID = 12
NOW = dt.datetime(2026, 10, 25, 12, tzinfo=dt.timezone.utc)
RUNS = 'actions/workflows/9/runs?head_sha=' + SHA + '&per_page=100&page=1'
JOBS = 'actions/runs/100/attempts/1/jobs?per_page=100&page=1'
ARTIFACTS = 'actions/runs/100/artifacts?per_page=100&page=1'

INPUTS = {'.github/ci-evidence.json': '1' * 40, '.github/workflows/ci.yml': '2' * 40,
          'dev.json': '3' * 40, 'pins/companions.json': '4' * 40,
          'scripts/dev/release_evidence.py': '5' * 40}
SOURCE = {'schema': 2, 'repository': REPO, 'repository_id': REPO_ID, 'source': SHA,
          'inputs': INPUTS}
LINUX = {'runner': {'ImageOS': 'ubuntu24', 'ImageVersion': '20261020.1', 'RUNNER_OS': 'Linux',
                    'RUNNER_ARCH': 'X64', 'os_release': 'f' * 64},
         'tools': {'go': 'go version go1.26.5 linux/amd64'}}
MACOS = {'runner': {'ImageOS': 'macos15', 'ImageVersion': '20261019.2', 'RUNNER_OS': 'macOS',
                    'RUNNER_ARCH': 'ARM64'},
         'tools': {'go': 'go version go1.26.5 darwin/arm64'}}

CONFIG = {
    'schema': 2, 'repository': REPO, 'branch': 'main', 'max_age_hours': 48,
    'inputs': ['pins/companions.json'], 'fresh_at_release': ['tag-history'],
    'profiles': {
        'linux': {'platform': {'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64'},
                  'compare': 'release-runner', 'tools': {'go': ['go', 'version']},
                  'pins': {'go': 'go version go1.26.5 linux/amd64'}},
        'macos': {'platform': {'RUNNER_OS': 'macOS', 'RUNNER_ARCH': 'ARM64', 'ImageOS': 'macos15'},
                  'compare': 'pins', 'tools': {'go': ['go', 'version']},
                  'pins': {'go': 'go version go1.26.5 darwin/arm64'}}},
    'workflows': {'ci': {
        'path': '.github/workflows/ci.yml', 'name': 'CI', 'events': ['push', 'workflow_dispatch'],
        'skipped_jobs': ['PR sample'],
        'jobs': {
            'test-linux': {'name': 'test (ubuntu-latest)', 'job_id': 'test',
                           'labels': ['ubuntu-latest'], 'profile': 'linux',
                           'checks': ['unit', 'audit'], 'optional_skips': ['audit']},
            'test-macos': {'name': 'test (macos-latest)', 'job_id': 'test',
                           'labels': ['macos-latest'], 'profile': 'macos', 'checks': ['unit']}}}}}

RUN = {'id': 100, 'run_attempt': 1, 'event': 'push', 'head_branch': 'main', 'head_sha': SHA,
       'workflow_id': 9, 'path': '.github/workflows/ci.yml', 'status': 'completed',
       'conclusion': 'success', 'pull_requests': [], 'created_at': '2026-10-25T10:00:00Z',
       'run_started_at': '2026-10-25T10:00:00Z', 'updated_at': '2026-10-25T10:06:00Z',
       'repository': {'id': REPO_ID, 'full_name': REPO},
       'head_repository': {'id': REPO_ID, 'full_name': REPO}}
HOSTED = {'runner_group_id': 0, 'runner_group_name': 'GitHub Actions'}
JOB_LINUX = dict(HOSTED, id=201, name='test (ubuntu-latest)', run_id=100, run_attempt=1,
                 head_sha=SHA, head_branch='main', workflow_name='CI', status='completed',
                 conclusion='success', labels=['ubuntu-latest'],
                 started_at='2026-10-25T10:00:05Z', completed_at='2026-10-25T10:05:00Z')
JOB_MACOS = dict(JOB_LINUX, id=202, name='test (macos-latest)', labels=['macos-latest'],
                 started_at='2026-10-25T10:00:06Z', completed_at='2026-10-25T10:04:00Z')
JOB_SKIPPED = {'id': 203, 'name': 'PR sample', 'run_id': 100, 'run_attempt': 1, 'head_sha': SHA,
               'head_branch': 'main', 'workflow_name': 'CI', 'status': 'completed',
               'conclusion': 'skipped', 'labels': ['ubuntu-latest'], 'runner_group_id': None,
               'runner_group_name': None, 'started_at': '2026-10-25T10:00:01Z',
               'completed_at': '2026-10-25T10:00:01Z'}
EVIDENCE_LINUX = {'schema': 2, 'repository': REPO, 'repository_id': REPO_ID, 'source': SHA,
                  'inputs': INPUTS, 'workflow': 'ci', 'workflow_path': '.github/workflows/ci.yml',
                  'workflow_name': 'CI', 'job': 'test-linux', 'run_id': 100, 'attempt': 1,
                  'event': 'push', 'ref': 'refs/heads/main', 'runtime': LINUX,
                  'coverage': {'unit': 'PASS', 'audit': 'SKIP'}}
EVIDENCE_MACOS = dict(EVIDENCE_LINUX, job='test-macos', runtime=MACOS, coverage={'unit': 'PASS'})
ORIGIN = {'id': 100, 'head_sha': SHA, 'head_branch': 'main', 'repository_id': REPO_ID,
          'head_repository_id': REPO_ID}
ARTIFACT_LINUX = {'id': 301, 'name': 'ci-evidence-ci-test-linux-1', 'expired': False,
                  'created_at': '2026-10-25T10:04:59Z', 'workflow_run': ORIGIN}
ARTIFACT_MACOS = dict(ARTIFACT_LINUX, id=302, name='ci-evidence-ci-test-macos-1',
                      created_at='2026-10-25T10:03:58Z')


def zipped(payload, extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('evidence.json', json.dumps(payload))
        if extra:
            archive.writestr(extra, 'another entry')
    return output.getvalue()


def world():
    """The accepted case: one push run of CI at SHA, both legs, the PR-only job skipped."""
    data = {
        '': {'id': REPO_ID, 'full_name': REPO, 'default_branch': 'main'},
        'git/ref/tags/v1.2.3': {'ref': 'refs/tags/v1.2.3',
                                'object': {'type': 'tag', 'sha': TAG_OBJECT}},
        'git/tags/' + TAG_OBJECT: {'object': {'type': 'commit', 'sha': SHA}},
        'actions/workflows/ci.yml': {'id': 9, 'name': 'CI', 'path': '.github/workflows/ci.yml',
                                     'state': 'active'},
        RUNS: {'total_count': 1, 'workflow_runs': [RUN]},
        'actions/runs/100': RUN,
        JOBS: {'total_count': 3, 'jobs': [JOB_LINUX, JOB_MACOS, JOB_SKIPPED]},
        ARTIFACTS: {'total_count': 2, 'artifacts': [ARTIFACT_LINUX, ARTIFACT_MACOS]},
    }
    # Through JSON, so that no two answers share an object: each read is the API's own copy.
    data = json.loads(json.dumps(data))
    for artifact, payload in ((data[ARTIFACTS]['artifacts'][0], EVIDENCE_LINUX),
                              (data[ARTIFACTS]['artifacts'][1], EVIDENCE_MACOS)):
        pack(data, artifact, copy.deepcopy(payload))
    return data


def pack(data, artifact, payload, extra=None):
    raw = zipped(payload, extra)
    data['actions/artifacts/%d/zip' % artifact['id']] = raw
    artifact.update(size_in_bytes=len(raw), digest='sha256:' + hashlib.sha256(raw).hexdigest())


class FakeAPI(e.API):
    def __init__(self, responses):
        super().__init__(REPO)
        self.responses = responses
        self.calls = []

    def get(self, suffix, binary=False):
        self.calls.append(suffix)
        if suffix not in self.responses:
            raise e.Refusal('api-unavailable', 'no fixture for ' + suffix)
        value = self.responses[suffix]
        if isinstance(value, Exception):
            raise value
        if callable(value):
            value = value()
        return copy.deepcopy(value)


class Gate(unittest.TestCase):
    """Drives decide() with the release runner's own resolution fixed to LINUX."""

    def setUp(self):
        self.data = world()
        self.config = copy.deepcopy(CONFIG)
        self.here = copy.deepcopy(LINUX)
        resolve = patch.object(e, 'runtime', side_effect=lambda profile: copy.deepcopy(self.here))
        resolve.start()
        self.addCleanup(resolve.stop)
        self.api = None

    def decide(self, tag='v1.2.3'):
        self.api = FakeAPI(self.data)
        record = {'workflows': {}}
        e.decide(self.api, self.config, copy.deepcopy(SOURCE), tag, NOW, record)
        self.record = record
        if record['decision'] == 'reuse':
            self.assertIsNone(record['refusal'])
            return 'reuse'
        self.assertEqual(record['decision'], 'refuse')
        return record['refusal']['code']

    def refuses(self, code, change=None):
        if change:
            change()
        self.assertEqual(self.decide(), code)

    # The fixture's parts, by name.
    @property
    def selected(self):
        return self.data['actions/runs/100']

    @property
    def listed(self):
        return self.data[RUNS]['workflow_runs']

    @property
    def jobs(self):
        return self.data[JOBS]['jobs']

    @property
    def artifacts(self):
        return self.data[ARTIFACTS]['artifacts']

    def both_runs(self, **changes):
        for run in [self.selected] + [run for run in self.listed if run['id'] == 100]:
            run.update(copy.deepcopy(changes))

    def evidence(self, index, change, extra=None):
        artifact = self.artifacts[index]
        raw = self.data['actions/artifacts/%d/zip' % artifact['id']]
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            payload = json.loads(archive.read('evidence.json'))
        change(payload)
        pack(self.data, artifact, payload, extra)

    def add_run(self, run):
        self.data[RUNS]['workflow_runs'].append(run)
        self.data[RUNS]['total_count'] = len(self.data[RUNS]['workflow_runs'])

    def set_jobs(self, jobs):
        self.data[JOBS] = {'total_count': len(jobs), 'jobs': jobs}

    def set_artifacts(self, artifacts):
        self.data[ARTIFACTS] = {'total_count': len(artifacts), 'artifacts': artifacts}


class Accepted(Gate):
    def test_exact_commit_evidence_is_reused_and_recorded(self):
        self.assertEqual(self.decide(), 'reuse')
        ci = self.record['workflows']['ci']
        self.assertEqual((ci['workflow_id'], ci['path'], ci['name']), (9, '.github/workflows/ci.yml', 'CI'))
        self.assertEqual((ci['run_id'], ci['attempt'], ci['event'], ci['conclusion']),
                         (100, 1, 'push', 'success'))
        self.assertEqual(self.record['tag_object'], TAG_OBJECT)
        self.assertEqual(sorted(ci['jobs']), ['test-linux', 'test-macos'])
        self.assertEqual(ci['jobs']['test-linux']['artifact']['name'], 'ci-evidence-ci-test-linux-1')
        self.assertEqual(ci['jobs']['test-macos']['runtime'], MACOS)
        self.assertEqual(ci['jobs']['test-linux']['coverage'], {'unit': 'PASS', 'audit': 'SKIP'})
        self.assertEqual(ci['skipped_jobs'], {'PR sample': 'skipped'})
        self.assertEqual(ci['age_hours'], 2.0)
        self.assertEqual(ci['applicable'], 1)
        self.assertEqual((ci['runs_at_commit'], ci['referenced_workflows']), (1, []))

    def test_a_dispatch_on_main_is_trusted_when_configured(self):
        self.both_runs(event='workflow_dispatch')
        self.evidence(0, lambda payload: payload.update(event='workflow_dispatch'))
        self.evidence(1, lambda payload: payload.update(event='workflow_dispatch'))
        self.assertEqual(self.decide(), 'reuse')
        self.config['workflows']['ci']['events'] = ['push']
        self.assertEqual(self.decide(), 'run-missing')

    def test_older_failures_and_newer_green_runs_of_other_triggers_do_not_block(self):
        self.add_run(dict(RUN, id=90, conclusion='failure', created_at='2026-10-25T09:00:00Z',
                          run_started_at='2026-10-25T09:00:00Z'))
        self.add_run(dict(RUN, id=91, event='schedule', conclusion='cancelled',
                          created_at='2026-10-25T09:30:00Z', run_started_at='2026-10-25T09:30:00Z'))
        self.add_run(dict(RUN, id=110, event='pull_request', head_branch='feature',
                          created_at='2026-10-25T11:00:00Z', run_started_at='2026-10-25T11:00:00Z'))
        self.add_run(dict(RUN, id=111, event='schedule', created_at='2026-10-25T11:10:00Z',
                          run_started_at='2026-10-25T11:10:00Z'))
        self.assertEqual(self.decide(), 'reuse')
        self.assertEqual(self.record['workflows']['ci']['run_id'], 100)
        self.assertEqual((self.record['workflows']['ci']['runs_at_commit'],
                          self.record['workflows']['ci']['applicable']), (5, 2))


class WrongCommit(Gate):
    def test_a_run_at_another_commit(self):
        self.refuses('run-sha', lambda: self.both_runs(head_sha=OTHER))

    def test_evidence_recorded_at_another_commit(self):
        self.refuses('evidence-identity', lambda: self.evidence(0, lambda p: p.update(source=OTHER)))

    def test_a_job_or_artifact_at_another_commit(self):
        self.refuses('job-identity', lambda: self.jobs[1].update(head_sha=OTHER))
        self.data = world()
        self.refuses('artifact-run', lambda: self.artifacts[0]['workflow_run'].update(head_sha=OTHER))


class TreeEquivalentCommit(Gate):
    def test_only_a_tree_equivalent_commit_ran(self):
        # The other commit's run is not listed for SHA: no evidence at the exact commit.
        self.data[RUNS] = {'total_count': 0, 'workflow_runs': []}
        self.data['actions/workflows/9/runs?head_sha=' + OTHER + '&per_page=100&page=1'] = {
            'total_count': 1, 'workflow_runs': [dict(RUN, head_sha=OTHER)]}
        self.refuses('run-missing')
        self.assertFalse([call for call in self.api.calls if OTHER in call])

    def test_a_listing_that_returns_the_other_commit(self):
        self.data[RUNS]['workflow_runs'][0] = dict(RUN, head_sha=OTHER)
        self.refuses('run-sha')


class WrongRepository(Gate):
    def test_run_repository_or_fork_head(self):
        self.refuses('run-repository', lambda: self.both_runs(repository={'id': 13, 'full_name': REPO}))
        self.data = world()
        self.refuses('run-repository', lambda: self.both_runs(
            head_repository={'id': 77, 'full_name': 'fork/project'}))

    def test_the_api_answers_for_another_repository(self):
        self.refuses('repository-identity', lambda: self.data[''].update(id=13))

    def test_artifact_or_evidence_of_another_repository(self):
        self.refuses('artifact-run', lambda: self.artifacts[1]['workflow_run'].update(repository_id=13))
        self.data = world()
        self.refuses('evidence-identity', lambda: self.evidence(0, lambda p: p.update(repository_id=13)))

    def test_the_trusted_branch_is_the_default_branch(self):
        self.refuses('branch-default', lambda: self.data[''].update(default_branch='trunk'))


class WrongEvent(Gate):
    def test_a_pull_request_head_run(self):
        self.data[RUNS]['workflow_runs'][0] = dict(RUN, event='pull_request', head_branch='feature')
        self.refuses('run-missing')

    def test_a_synthetic_merge_run(self):
        # A pull request from a fork's main: the event, not the branch name, excludes it.
        self.data[RUNS]['workflow_runs'][0] = dict(RUN, event='pull_request', head_branch='main',
                                                   head_repository={'id': 77, 'full_name': 'fork/project'})
        self.refuses('run-missing')
        self.data = world()
        self.data[RUNS]['workflow_runs'][0] = dict(RUN, event='merge_group',
                                                   head_branch='gh-readonly-queue/main/pr-7-' + SHA)
        self.refuses('run-missing')

    def test_a_push_to_another_branch(self):
        self.data[RUNS]['workflow_runs'][0] = dict(RUN, head_branch='release-candidate')
        self.refuses('run-missing')

    def test_a_job_of_another_branch(self):
        self.refuses('job-identity', lambda: self.jobs[0].update(head_branch='feature'))
        self.assertIn('test (ubuntu-latest)', self.record['refusal']['detail'])

    def test_a_main_run_that_belongs_to_a_pull_request(self):
        self.refuses('run-trigger', lambda: self.both_runs(pull_requests=[{'number': 7}]))

    def test_evidence_recorded_for_another_event_or_ref(self):
        self.refuses('evidence-identity', lambda: self.evidence(0, lambda p: p.update(event='pull_request')))
        self.data = world()
        self.refuses('evidence-identity', lambda: self.evidence(1, lambda p: p.update(ref='refs/pull/7/merge')))


class WrongWorkflow(Gate):
    def test_the_workflow_resolves_to_another_file_name_or_state(self):
        for change in ({'path': '.github/workflows/other.yml'}, {'name': 'Other CI'},
                       {'state': 'disabled_manually'}):
            with self.subTest(change=change):
                self.data = world()
                self.refuses('workflow-identity', lambda: self.data['actions/workflows/ci.yml'].update(change))

    def test_a_run_of_another_workflow_with_the_same_job_names(self):
        self.refuses('run-workflow', lambda: self.both_runs(workflow_id=10, path='.github/workflows/other.yml'))
        self.data = world()
        self.refuses('job-identity', lambda: [job.update(workflow_name='Other CI') for job in self.jobs])

    def test_another_workflow_ran_and_this_one_did_not(self):
        self.data[RUNS] = {'total_count': 0, 'workflow_runs': []}
        self.data['actions/workflows/10/runs?head_sha=' + SHA + '&per_page=100&page=1'] = {
            'total_count': 1, 'workflow_runs': [dict(RUN, id=500, workflow_id=10,
                                                     path='.github/workflows/other.yml')]}
        self.refuses('run-missing')
        self.assertFalse([call for call in self.api.calls if 'workflows/10' in call or 'runs/500' in call])

    def test_evidence_recorded_by_another_workflow(self):
        self.refuses('evidence-identity', lambda: self.evidence(0, lambda p: p.update(
            workflow_path='.github/workflows/other.yml')))


class MutableStatusName(Gate):
    def test_a_green_status_or_check_named_like_a_job_is_not_evidence(self):
        self.data[RUNS] = {'total_count': 0, 'workflow_runs': []}
        self.data['commits/' + SHA + '/status'] = {'state': 'success', 'statuses': [
            {'context': 'test (ubuntu-latest)', 'state': 'success'},
            {'context': 'test (macos-latest)', 'state': 'success'}]}
        self.data['commits/' + SHA + '/check-runs'] = {'total_count': 2, 'check_runs': [
            {'name': 'test (ubuntu-latest)', 'conclusion': 'success'},
            {'name': 'test (macos-latest)', 'conclusion': 'success'}]}
        self.refuses('run-missing')
        self.assertFalse([call for call in self.api.calls if call.startswith('commits/')])


class MissingJobOrLeg(Gate):
    def test_a_missing_matrix_leg_or_an_unexpected_or_repeated_job(self):
        for jobs in ([JOB_LINUX, JOB_SKIPPED],
                     [JOB_LINUX, JOB_MACOS, JOB_SKIPPED, dict(JOB_LINUX, id=204, name='test (windows-latest)')],
                     [JOB_LINUX, JOB_MACOS, JOB_SKIPPED, dict(JOB_LINUX, id=204)]):
            with self.subTest(names=[job['name'] for job in jobs]):
                self.data = world()
                self.refuses('job-coverage', lambda: self.set_jobs(copy.deepcopy(jobs)))

    def test_a_missing_or_repeated_artifact_of_a_leg(self):
        self.refuses('artifact-coverage', lambda: self.set_artifacts([self.artifacts[0]]))
        self.data = world()
        self.refuses('artifact-coverage', lambda: self.set_artifacts(
            self.artifacts + [dict(self.artifacts[1], id=303)]))

    def test_an_artifact_of_another_attempt_only(self):
        self.refuses('artifact-coverage', lambda: self.artifacts[1].update(name='ci-evidence-ci-test-macos-2'))

    def test_a_check_missing_from_a_leg(self):
        self.refuses('check-coverage', lambda: self.evidence(0, lambda p: p.update(coverage={'audit': 'SKIP'})))
        self.data = world()
        self.refuses('check-coverage', lambda: self.evidence(1, lambda p: p['coverage'].update(extra='PASS')))


class UnexpectedSkip(Gate):
    def test_a_required_leg_skipped(self):
        self.refuses('job-skipped', lambda: self.jobs[1].update(conclusion='skipped'))

    def test_a_pull_request_only_job_that_ran(self):
        self.refuses('job-not-skipped', lambda: self.jobs[2].update(conclusion='success'))

    def test_a_required_check_skipped_failed_or_not_run(self):
        for status in ('SKIP', 'FAIL', 'NOT RUN'):
            with self.subTest(status=status):
                self.data = world()
                self.refuses('check-result', lambda: self.evidence(0, lambda p: p['coverage'].update(unit=status)))

    def test_a_permitted_skip_is_only_a_skip(self):
        self.refuses('check-result', lambda: self.evidence(0, lambda p: p['coverage'].update(audit='FAIL')))


class NewerAttempt(Gate):
    def newer(self, **changes):
        self.add_run(dict(dict(RUN, id=101, event='workflow_dispatch', created_at='2026-10-25T11:00:00Z',
                               run_started_at='2026-10-25T11:00:00Z'), **changes))

    def test_a_newer_failed_or_cancelled_run(self):
        for conclusion in ('failure', 'cancelled', 'timed_out', 'action_required'):
            with self.subTest(conclusion=conclusion):
                self.data = world()
                self.newer(conclusion=conclusion)
                self.data['actions/runs/101'] = dict(RUN, id=101, event='workflow_dispatch',
                                                     created_at='2026-10-25T11:00:00Z',
                                                     run_started_at='2026-10-25T11:00:00Z',
                                                     conclusion=conclusion)
                self.refuses('run-result')
                self.assertEqual(self.record['workflows']['ci']['run_id'], 101)

    def test_a_running_or_queued_run_newer_or_older(self):
        for status, started in (('in_progress', '2026-10-25T11:00:00Z'), ('queued', '2026-10-25T11:00:00Z'),
                                ('in_progress', '2026-10-25T09:00:00Z')):
            with self.subTest(status=status, started=started):
                self.data = world()
                self.newer(status=status, conclusion=None, run_started_at=started)
                self.data['actions/runs/101'] = self.listed[-1]
                self.refuses('run-unfinished')

    def test_a_newer_failed_or_running_run_of_another_trigger(self):
        for event in ('schedule', 'workflow_run', 'repository_dispatch'):
            for status, conclusion, code in (('completed', 'failure', 'run-newer-failed'),
                                             ('in_progress', None, 'run-unfinished')):
                with self.subTest(event=event, status=status):
                    self.data = world()
                    self.add_run(dict(RUN, id=120, event=event, status=status, conclusion=conclusion,
                                      created_at='2026-10-25T11:00:00Z',
                                      run_started_at='2026-10-25T11:00:00Z'))
                    self.refuses(code)
                    self.assertIn('120', self.record['refusal']['detail'])

    def test_runs_from_outside_the_trusted_branch_do_not_block(self):
        fork = {'id': 77, 'full_name': 'fork/project'}
        cases = {
            'a newer failed fork pull request run': dict(event='pull_request', head_branch='main',
                                                         head_repository=fork, conclusion='failure'),
            'a fork pull request run awaiting approval': dict(event='pull_request', head_branch='feature',
                                                              head_repository=fork, status='action_required',
                                                              conclusion=None, run_started_at=None),
            'a newer failed run on another branch': dict(event='push', head_branch='release-candidate',
                                                         conclusion='failure'),
            'a newer failed pull_request_target run': dict(event='pull_request_target', conclusion='failure'),
            'a newer failed merge queue run': dict(event='merge_group', conclusion='failure'),
            'a newer failed run from another head repository': dict(event='schedule', head_repository=fork,
                                                                    conclusion='failure'),
        }
        for name, changes in cases.items():
            with self.subTest(case=name):
                self.data = world()
                self.add_run(dict(dict(RUN, id=121, created_at='2026-10-25T11:00:00Z',
                                       run_started_at='2026-10-25T11:00:00Z'), **changes))
                self.assertEqual(self.decide(), 'reuse')
                self.assertEqual(self.record['workflows']['ci']['run_id'], 100)

    def test_a_lower_id_run_rerun_later_that_failed(self):
        self.add_run(dict(RUN, id=95, event='schedule', conclusion='failure',
                          created_at='2026-10-25T09:00:00Z', run_started_at='2026-10-25T11:00:00Z'))
        self.refuses('run-newer-failed')
        self.assertIn('95', self.record['refusal']['detail'])

    def test_a_higher_id_run_that_started_before_the_selected_attempt(self):
        self.both_runs(run_started_at='2026-10-25T11:30:00Z')
        self.add_run(dict(RUN, id=130, event='schedule', conclusion='failure',
                          created_at='2026-10-25T11:00:00Z', run_started_at='2026-10-25T11:00:00Z'))
        self.assertEqual(self.decide(), 'reuse')

    def test_the_selected_run_has_a_newer_failed_attempt(self):
        self.refuses('run-result', lambda: self.both_runs(run_attempt=2, conclusion='failure',
                                                          run_started_at='2026-10-25T11:30:00Z'))

    def test_an_older_run_rerun_after_the_newest_and_failed(self):
        self.add_run(dict(RUN, id=90, run_attempt=2, conclusion='failure',
                          created_at='2026-10-25T09:00:00Z', run_started_at='2026-10-25T11:30:00Z'))
        self.data['actions/runs/90'] = self.listed[-1]
        self.refuses('run-result')
        self.assertEqual(self.record['workflows']['ci']['run_id'], 90)

    def test_the_attempt_read_is_not_the_attempt_listed(self):
        self.refuses('run-race', lambda: self.selected.update(run_attempt=2))

    def test_a_partial_rerun(self):
        def rerun():
            self.both_runs(run_attempt=2, run_started_at='2026-10-25T11:00:00Z')
            self.data['actions/runs/100/attempts/2/jobs?per_page=100&page=1'] = {
                'total_count': 3, 'jobs': [dict(JOB_LINUX, run_attempt=2), JOB_MACOS,
                                           dict(JOB_SKIPPED, run_attempt=2)]}
        self.refuses('job-identity', rerun)

    def test_a_new_attempt_during_collection(self):
        reads = []
        def run():
            reads.append(1)
            return dict(RUN, run_attempt=1 if len(reads) == 1 else 2)
        self.data['actions/runs/100'] = run
        self.refuses('attempt-changed')

    def test_a_newer_run_during_collection(self):
        lists = []
        def listing():
            lists.append(1)
            runs = [RUN] + ([dict(RUN, id=101, status='in_progress', conclusion=None,
                                  run_started_at='2026-10-25T11:59:00Z')] if len(lists) >= 2 else [])
            return {'total_count': len(runs), 'workflow_runs': runs}
        self.data[RUNS] = listing
        self.refuses('run-unfinished')
        self.assertEqual(len(lists), 2)

    def test_a_newer_run_after_every_workflow_was_collected(self):
        lists = []
        def listing():
            lists.append(1)
            runs = [RUN] + ([dict(RUN, id=101, conclusion='failure', run_started_at='2026-10-25T11:59:00Z')]
                            if len(lists) >= 3 else [])
            return {'total_count': len(runs), 'workflow_runs': runs}
        self.data[RUNS] = listing
        self.refuses('final-latest-changed')

    def test_a_listing_that_changes_its_answer_during_collection(self):
        lists = []
        def listing():
            lists.append(1)
            run = dict(RUN, run_attempt=1 if len(lists) == 1 else 2)
            return {'total_count': 1, 'workflow_runs': [run]}
        self.data[RUNS] = listing
        self.refuses('latest-changed')


class ChangedInputs(Gate):
    def test_a_workflow_manifest_or_pin_file_identity_that_differs(self):
        for path in ('.github/workflows/ci.yml', 'dev.json', 'pins/companions.json'):
            with self.subTest(path=path):
                self.data = world()
                self.refuses('input-identity', lambda: self.evidence(0, lambda p: p['inputs'].update({path: '9' * 40})))
                self.assertIn(path, self.record['refusal']['detail'])

    def test_an_input_missing_from_the_evidence(self):
        self.refuses('input-identity', lambda: self.evidence(1, lambda p: p['inputs'].pop('dev.json')))

    def test_a_pinned_toolchain_that_differs(self):
        self.refuses('runtime-identity', lambda: self.evidence(1, lambda p: p['runtime']['tools'].update(
            go='go version go1.26.4 darwin/arm64')))
        self.assertIn('pinned', self.record['refusal']['detail'])
        self.data = world()
        self.here['tools']['go'] = 'go version go1.26.4 linux/amd64'
        self.refuses('runtime-identity', lambda: self.evidence(0, lambda p: p['runtime']['tools'].update(
            go='go version go1.26.4 linux/amd64')))

    def test_an_image_or_platform_that_differs(self):
        self.here['runner']['ImageVersion'] = '20261026.1'
        self.refuses('runtime-identity')
        self.assertIn('ImageVersion', self.record['refusal']['detail'])
        self.here = copy.deepcopy(LINUX)
        self.data = world()
        self.refuses('runtime-identity', lambda: self.evidence(1, lambda p: p['runtime']['runner'].update(ImageOS='macos14')))
        self.data = world()
        self.refuses('runtime-identity', lambda: self.evidence(1, lambda p: p['runtime']['runner'].update(RUNNER_ARCH='X64')))

    def test_a_runtime_record_that_is_missing_or_has_another_tool_set(self):
        self.refuses('runtime-identity', lambda: self.evidence(0, lambda p: p.pop('runtime')))
        self.data = world()
        self.refuses('runtime-identity', lambda: self.evidence(1, lambda p: p['runtime']['tools'].update(cc='clang')))

    def test_unexpected_members_in_the_evidence(self):
        self.refuses('evidence-identity', lambda: self.evidence(0, lambda p: p.update(green=True)))


class UnavailableEvidence(Gate):
    def test_an_api_error(self):
        for key in ('', 'actions/workflows/ci.yml', JOBS, 'actions/artifacts/302/zip'):
            with self.subTest(key=key):
                self.data = world()
                self.refuses('api-unavailable', lambda: self.data.update({key: e.Refusal('api-unavailable', 'HTTP 502')}))

    def test_a_truncated_listing(self):
        self.refuses('pagination-partial', lambda: self.data.update({JOBS: {'total_count': 4, 'jobs': self.jobs}}))
        self.data = world()
        self.refuses('pagination-cap', lambda: self.data[RUNS].update(total_count=1000))

    def test_expired_oversized_or_mismatched_artifacts(self):
        for change, code in (({'expired': True}, 'artifact-expired'),
                             ({'size_in_bytes': 1024 * 1024 + 1}, 'artifact-size'),
                             ({'created_at': '2026-10-25T10:05:01Z'}, 'artifact-interval'),
                             ({'digest': 'sha256:' + '0' * 64}, 'artifact-digest'),
                             ({'workflow_run': dict(ORIGIN, id=99)}, 'artifact-run')):
            with self.subTest(code=code):
                self.data = world()
                self.refuses(code, lambda: self.artifacts[0].update(change))

    def test_an_archive_with_another_entry(self):
        self.refuses('artifact-entries', lambda: self.evidence(0, lambda p: None, extra='../escape'))

    def test_malformed_answers(self):
        self.refuses('unavailable-or-malformed', lambda: self.selected.pop("status"))
        self.data = world()
        self.data['actions/artifacts/301/zip'] = b'not a zip archive'
        self.artifacts[0].update(size_in_bytes=17, digest='sha256:' + hashlib.sha256(b'not a zip archive').hexdigest())
        self.refuses('unavailable-or-malformed')
        self.data = world()
        self.refuses('unavailable-or-malformed', lambda: self.data.update({'': []}))

    def raw_evidence(self, index, text, compression=zipfile.ZIP_DEFLATED):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', compression) as archive:
            archive.writestr('evidence.json', text)
        self.raw_archive(index, output.getvalue())

    def raw_archive(self, index, raw):
        artifact = self.artifacts[index]
        self.data['actions/artifacts/%d/zip' % artifact['id']] = raw
        artifact.update(size_in_bytes=len(raw), digest='sha256:' + hashlib.sha256(raw).hexdigest())

    def malformed(self, detail):
        self.refuses('unavailable-or-malformed')
        self.assertIn(detail, self.record['refusal']['detail'])

    def test_an_unsupported_compression_method(self):
        # The compression method of the local header (offset 8) and of the central directory entry
        # (offset 10 from its signature), set by hand to 99.
        method = bytearray(zipped(EVIDENCE_LINUX))
        local, central = method.index(b'PK\x03\x04'), method.index(b'PK\x01\x02')
        method[local + 8:local + 10] = (99).to_bytes(2, 'little')
        method[central + 10:central + 12] = (99).to_bytes(2, 'little')
        self.raw_archive(0, bytes(method))
        self.malformed('a compression other than stored or deflated')
        self.data = world()
        self.raw_evidence(0, json.dumps(EVIDENCE_LINUX), zipfile.ZIP_BZIP2)
        self.malformed('a compression other than stored or deflated')

    def test_json_that_does_not_parse_or_is_not_an_object(self):
        self.raw_evidence(0, '{"schema": 2, ')
        self.malformed('JSONDecodeError')
        self.data = world()
        self.raw_evidence(0, b'\xff\xfe{}')
        self.refuses('unavailable-or-malformed')
        self.data = world()
        self.raw_evidence(0, '[1]')
        self.malformed('evidence.json is not an object')

    def test_json_nested_deeper_than_the_bound(self):
        for depth in (17, 100000):
            with self.subTest(depth=depth):
                self.data = world()
                self.raw_evidence(0, '[' * depth + ']' * depth)
                self.malformed('nesting deeper than 16')
        # At the bound, and brackets inside a string, are not nesting: those refuse later.
        self.data = world()
        self.raw_evidence(0, '{"a": ' + '[' * 15 + ']' * 15 + '}')
        self.refuses('evidence-identity')
        self.data = world()
        self.raw_evidence(0, json.dumps(dict(EVIDENCE_LINUX, note='[' * 100 + '\\"{')))
        self.refuses('evidence-identity')
        self.assertIn('unexpected members', self.record['refusal']['detail'])

    def test_evidence_over_the_size_bound(self):
        text = '{"pad": "' + 'x' * (256 * 1024 - 10) + '"}'
        self.assertEqual(len(text), 256 * 1024 + 1)
        self.raw_evidence(0, text)
        self.malformed('declared over 262144 bytes')
        self.data = world()
        at_bound = '{"pad": "' + 'x' * (256 * 1024 - 11) + '"}'
        self.assertEqual(len(at_bound), 256 * 1024)
        self.raw_evidence(0, at_bound)
        self.refuses('evidence-identity')

    def test_stale_or_future_evidence(self):
        for started in ('2026-10-23T11:59:59Z', '2026-10-25T12:00:01Z'):
            with self.subTest(started=started):
                self.data = world()
                self.refuses('run-age', lambda: self.both_runs(run_started_at=started))
        self.data = world()
        self.config['max_age_hours'] = 1
        self.refuses('run-age')

    def test_a_job_on_another_runner(self):
        self.refuses('job-runner', lambda: self.jobs[0].update(runner_group_id=2, runner_group_name='Default'))
        self.data = world()
        self.refuses('job-runner', lambda: self.jobs[1].update(labels=['self-hosted', 'macos-latest']))


class TagMovement(Gate):
    def test_the_tag_names_another_commit(self):
        self.refuses('tag-commit', lambda: self.data['git/tags/' + TAG_OBJECT]['object'].update(sha=OTHER))
        self.data = world()
        self.refuses('tag-commit', lambda: self.data['git/tags/' + TAG_OBJECT]['object'].update(type='tree'))

    def test_a_lightweight_tag(self):
        self.refuses('tag-annotated', lambda: self.data['git/ref/tags/v1.2.3']['object'].update(type='commit', sha=SHA))

    def test_the_tag_moves_during_collection(self):
        reads = []
        def reference():
            reads.append(1)
            return {'ref': 'refs/tags/v1.2.3',
                    'object': {'type': 'tag', 'sha': TAG_OBJECT if len(reads) == 1 else 'u' * 40}}
        self.data['git/ref/tags/v1.2.3'] = reference
        self.data['git/tags/' + 'u' * 40] = {'object': {'type': 'commit', 'sha': SHA}}
        self.refuses('tag-changed')

    def test_tag_grammar(self):
        for tag in ('v01.2.3', 'v1.2.3-rc.1', '1.2.3', ''):
            with self.subTest(tag=tag):
                self.assertEqual(self.decide(tag), 'tag-syntax')


class Pagination(unittest.TestCase):
    def outcome(self, responses):
        try:
            return FakeAPI(responses).pages('list', 'items')
        except e.Refusal as error:
            return error.code

    def test_two_full_reads(self):
        rows = [{'id': i} for i in range(101)]
        self.assertEqual(self.outcome({'list?per_page=100&page=1': {'total_count': 101, 'items': rows[:100]},
                                       'list?per_page=100&page=2': {'total_count': 101, 'items': rows[100:]}}), rows)

    def test_refusals(self):
        second = {'total_count': 2, 'items': [{'id': 2}]}
        for code, first in (('pagination-cap', {'total_count': 1000, 'items': []}),
                            ('pagination-shape', {'total_count': 1, 'items': None}),
                            ('pagination-shape', {'total_count': 101, 'items': [{'id': i} for i in range(101)]}),
                            ('pagination-count', {'total_count': 0, 'items': [{'id': 1}]}),
                            ('pagination-partial', {'total_count': 2, 'items': [{'id': 1}]}),
                            ('pagination-duplicate', {'total_count': 2, 'items': [{'id': 1}, {'id': 1}]})):
            with self.subTest(code=code):
                self.assertEqual(self.outcome({'list?per_page=100&page=1': first,
                                               'list?per_page=100&page=2': second}), code)
        self.assertEqual(self.outcome({
            'list?per_page=100&page=1': {'total_count': 101, 'items': [{'id': i} for i in range(100)]},
            'list?per_page=100&page=2': {'total_count': 102, 'items': [{'id': 100}]}}), 'pagination-changed')


class Configuration(unittest.TestCase):
    def outcome(self, config):
        try:
            e.check_config(config)
            return 'valid'
        except e.Refusal as error:
            return error.code

    def test_the_kits_configuration_and_the_template_are_valid(self):
        for path in ('.github/ci-evidence.json', 'templates/ci-evidence.json'):
            with self.subTest(path=path):
                self.assertEqual(self.outcome(json.loads((ROOT / path).read_text())), 'valid')
        self.assertEqual(self.outcome(copy.deepcopy(CONFIG)), 'valid')

    def test_every_required_member_is_required(self):
        def members(config):
            yield config, ['schema', 'repository', 'branch', 'max_age_hours', 'inputs', 'profiles', 'workflows']
            for profile in config['profiles'].values():
                yield profile, ['platform', 'compare', 'tools']
                yield profile['platform'], ['RUNNER_OS', 'RUNNER_ARCH']
            for workflow in config['workflows'].values():
                yield workflow, ['path', 'name', 'events', 'jobs']
                for job in workflow['jobs'].values():
                    yield job, ['name', 'job_id', 'labels', 'profile', 'checks']
        count = 0
        for index, (_, names) in enumerate(members(copy.deepcopy(CONFIG))):
            for name in names:
                config = copy.deepcopy(CONFIG)
                target = list(members(config))[index][0]
                target.pop(name)
                with self.subTest(member=name, at=index):
                    self.assertEqual(self.outcome(config), 'config-invalid')
                count += 1
        self.assertGreater(count, 20)

    def test_invalid_values(self):
        def at(change):
            config = copy.deepcopy(CONFIG)
            change(config)
            return self.outcome(config)
        linux = lambda c: c['profiles']['linux']
        job = lambda c: c['workflows']['ci']['jobs']['test-linux']
        cases = {
            'schema 1': lambda c: c.update(schema=1),
            'unknown member': lambda c: c.update(green=True),
            'age over the limit': lambda c: c.update(max_age_hours=49),
            'age zero': lambda c: c.update(max_age_hours=0),
            'repository grammar': lambda c: c.update(repository='project'),
            'input path escapes': lambda c: c.update(inputs=['../outside']),
            'input repeated': lambda c: c.update(inputs=['dev.json', 'dev.json']),
            'compare unknown': lambda c: linux(c).update(compare='trust'),
            'pin of no tool': lambda c: linux(c).update(pins={'cc': 'clang'}),
            'pins mode without every pin': lambda c: c['profiles']['macos'].update(tools={'go': ['go', 'version'], 'cc': ['cc', '--version']}),
            'pins mode with no tool': lambda c: c['profiles']['macos'].update(tools={}, pins={}),
            'empty tool command': lambda c: linux(c)['tools'].update(go=[]),
            'untrusted event': lambda c: c['workflows']['ci'].update(events=['push', 'pull_request']),
            'no event': lambda c: c['workflows']['ci'].update(events=[]),
            'workflow outside .github/workflows': lambda c: c['workflows']['ci'].update(path='ci.yml'),
            'no jobs': lambda c: c['workflows']['ci'].update(jobs={}),
            'unknown profile': lambda c: job(c).update(profile='windows'),
            'no labels': lambda c: job(c).update(labels=[]),
            'optional skip of no check': lambda c: job(c).update(optional_skips=['lint']),
            'setup not a boolean': lambda c: job(c).update(setup='yes'),
            'job name repeated': lambda c: c['workflows']['ci'].update(skipped_jobs=['test (ubuntu-latest)']),
            'artifact-unsafe job key': lambda c: c['workflows']['ci']['jobs'].update({'a b': job(c)}),
            'comment not text': lambda c: c.update({'$comment': 3}),
            'comment where names are free': lambda c: c['profiles'].update({'$comment': 'no'}),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                self.assertEqual(at(change), 'config-invalid')

    def test_optional_members_and_comments_are_accepted(self):
        config = copy.deepcopy(CONFIG)
        config.pop('fresh_at_release')
        config['workflows']['ci'].pop('skipped_jobs')
        config['profiles']['linux'].pop('pins')
        config['$comment'] = ['a', 'b']
        config['workflows']['ci']['jobs']['test-linux']['$comment'] = 'a leg'
        self.assertEqual(self.outcome(config), 'valid')


class KitAdoption(unittest.TestCase):
    """The kit's own configuration, CI capture steps and release step agree."""

    def test_ci_captures_every_configured_job_under_the_name_verify_reads(self):
        config = json.loads((ROOT / '.github/ci-evidence.json').read_text())
        ci = (ROOT / '.github/workflows/ci.yml').read_text()
        for key, workflow in config['workflows'].items():
            self.assertIn('name: ' + workflow['name'] + '\n', ci)
            for job_key, spec in workflow['jobs'].items():
                with self.subTest(job=job_key):
                    self.assertIn('\n  %s:\n    name: %s\n' % (spec['job_id'], spec['name']), ci)
                    self.assertIn('python3 scripts/dev/release_evidence.py capture --workflow %s --job %s '
                                  % (key, job_key), ci)
                    self.assertIn('name: ci-evidence-%s-%s-${{ github.run_attempt }}' % (key, job_key), ci)

    def test_the_release_takes_the_evidence_and_does_not_call_ci_again(self):
        release = (ROOT / '.github/workflows/release.yml').read_text()
        self.assertIn('run: python3 scripts/dev/release_evidence.py verify --output', release)
        self.assertNotIn('uses: ./.github/workflows/ci.yml', release)
        self.assertIn('scripts/dev/release_evidence.py line 2', release)
        # The decision record is kept on a refusal too: the upload runs unless the run was cancelled.
        self.assertIn('verify --output "${{ runner.temp }}/release-evidence.json"', release)
        self.assertIn('      - name: Keep the decision record\n'
                      '        if: ${{ !cancelled() }}\n'
                      '        uses: actions/upload-artifact@', release)
        self.assertIn('          path: ${{ runner.temp }}/release-evidence.json\n'
                      '          if-no-files-found: error\n', release)
        self.assertIn('cmp -s lib/release_evidence.py <(sed 2d scripts/dev/release_evidence.py)', release)


class Boundaries(unittest.TestCase):
    def outcome(self, call):
        try:
            call()
            return 'accepted'
        except e.Refusal as error:
            return error.code

    def test_commands_and_timestamps(self):
        self.assertEqual(self.outcome(lambda: e.command([sys.executable, '-c', 'raise SystemExit(7)'], 'api-unavailable')),
                         'api-unavailable')
        self.assertEqual(self.outcome(lambda: e.command([sys.executable, '-c', 'print("large")'], 'x', limit=1)),
                         'response-size')
        self.assertEqual(self.outcome(lambda: e.command(['release-evidence-test-no-such-program'], 'tool-identity')),
                         'tool-identity')
        self.assertEqual(self.outcome(lambda: e.timestamp(1)), 'timestamp')
        self.assertEqual(self.outcome(lambda: e.timestamp('2026-10-25T10:00:00')), 'timestamp')

    def test_runtime_identity_on_this_runner(self):
        profile = {'platform': {'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64'}, 'compare': 'release-runner',
                   'tools': {'empty': [sys.executable, '-c', 'pass']}}
        env = {'ImageOS': 'ubuntu24', 'ImageVersion': '1', 'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64'}
        with patch.dict(os.environ, env):
            self.assertEqual(self.outcome(lambda: e.runtime(profile)), 'tool-identity')
        with patch.dict(os.environ, dict(env, RUNNER_ARCH='ARM64')):
            self.assertEqual(self.outcome(lambda: e.runtime(profile)), 'runner-platform')
        with patch.dict(os.environ, dict(env, ImageVersion='')):
            self.assertEqual(self.outcome(lambda: e.runtime(profile)), 'runner-identity')

    def test_repeated_checks(self):
        self.assertEqual(self.outcome(lambda: e.required_checks({'checks': ['unit', 'unit']})), 'check-config')


class RealCLI(unittest.TestCase):
    """The public command, as the workflows run it: a fixture repository, a fake gh on PATH."""

    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory(prefix='release-evidence-')
        cls.addClassCleanup(scratch.cleanup)
        cls.root = Path(scratch.name) / 'repo'
        (cls.root / '.github/workflows').mkdir(parents=True)
        bin_dir = Path(scratch.name) / 'bin'
        bin_dir.mkdir()
        cls.fixture_api = Path(scratch.name) / 'api.json'
        (cls.root / 'release_evidence.py').write_bytes(HELPER.read_bytes())
        cls.config = {
            'schema': 2, 'repository': REPO, 'branch': 'main', 'max_age_hours': 48, 'inputs': [],
            'profiles': {'kit': {'platform': {'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64'},
                                 'compare': 'release-runner',
                                 'tools': {'fixture': ['release-evidence-fixture-tool']}}},
            'workflows': {'ci': {'path': '.github/workflows/ci.yml', 'name': 'CI', 'events': ['push'],
                                 'jobs': {'test': {'name': 'tests', 'job_id': 'test',
                                                   'labels': ['ubuntu-latest'], 'profile': 'kit',
                                                   'checks': ['unit', 'audit'],
                                                   'optional_skips': ['audit']}}}}}
        (cls.root / '.github/ci-evidence.json').write_text(json.dumps(cls.config, indent=2) + '\n')
        (cls.root / '.github/workflows/ci.yml').write_text('name: CI\non: push\njobs:\n  test: {}\n')
        (cls.root / 'dev.json').write_text('{"version": 1, "checks": [{"name": "unit"}, {"name": "audit"}]}\n')
        tool = bin_dir / 'release-evidence-fixture-tool'
        tool.write_text('#!/bin/sh\necho "fixture-tool 1.0"\n')
        tool.chmod(0o755)
        gh = bin_dir / 'gh'
        gh.write_text('#!' + sys.executable + ' -I\n'
                      'import base64, json, os, sys\n'
                      'data = json.load(open(os.environ["FIXTURE_API"]))\n'
                      'path, base = sys.argv[-1], "repos/' + REPO + '"\n'
                      'key = "" if path == base else path[len(base) + 1:]\n'
                      'if not path.startswith(base) or key not in data:\n'
                      '    sys.exit(1)\n'
                      'value = data[key]\n'
                      'if isinstance(value, dict) and "_binary" in value:\n'
                      '    sys.stdout.buffer.write(base64.b64decode(value["_binary"]))\n'
                      'else:\n'
                      '    print(json.dumps(value))\n')
        gh.chmod(0o755)
        git_env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        for argv in (['git', 'init', '-q', '-b', 'main'], ['git', 'add', '.'],
                     ['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                      'commit', '-qm', 'fixture']):
            subprocess.run(argv, cwd=cls.root, check=True, env=git_env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=cls.root, text=True,
                                          stdin=subprocess.DEVNULL).strip()
        paths = ['.github/ci-evidence.json', '.github/workflows/ci.yml', 'dev.json', 'release_evidence.py']
        ids = subprocess.check_output(['git', 'rev-parse'] + [cls.sha + ':' + path for path in paths],
                                      cwd=cls.root, text=True, stdin=subprocess.DEVNULL).split()
        cls.inputs = dict(zip(paths, ids))
        cls.env = dict(git_env, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'],
                       FIXTURE_API=str(cls.fixture_api), GITHUB_SHA=cls.sha,
                       GITHUB_REPOSITORY=REPO, GITHUB_REPOSITORY_ID=str(REPO_ID), ImageOS='ubuntu24',
                       ImageVersion='20261020.1', RUNNER_OS='Linux', RUNNER_ARCH='X64',
                       RELEASE_TAG='v1.2.3')
        cls.capture_env = {'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'push',
                           'GITHUB_JOB': 'test', 'GITHUB_RUN_ID': '100', 'GITHUB_RUN_ATTEMPT': '1',
                           'GITHUB_WORKFLOW_REF': REPO + '/.github/workflows/ci.yml@refs/heads/main',
                           'GITHUB_WORKFLOW_SHA': cls.sha}
        cls.runtime = {'runner': {'ImageOS': 'ubuntu24', 'ImageVersion': '20261020.1',
                                  'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64',
                                  'os_release': hashlib.sha256(Path('/etc/os-release').read_bytes()).hexdigest()},
                       'tools': {'fixture': 'fixture-tool 1.0'}}

    def world(self, payload=None):
        now = dt.datetime.now(dt.timezone.utc)
        def iso(seconds):
            return (now + dt.timedelta(seconds=seconds)).isoformat().replace('+00:00', 'Z')
        run = dict(RUN, head_sha=self.sha, created_at=iso(-600), run_started_at=iso(-600),
                   updated_at=iso(-300))
        job = dict(JOB_LINUX, name='tests', head_sha=self.sha, started_at=iso(-590), completed_at=iso(-300))
        payload = payload or {'schema': 2, 'repository': REPO, 'repository_id': REPO_ID,
                              'source': self.sha, 'inputs': self.inputs, 'workflow': 'ci',
                              'workflow_path': '.github/workflows/ci.yml', 'workflow_name': 'CI',
                              'job': 'test', 'run_id': 100, 'attempt': 1, 'event': 'push',
                              'ref': 'refs/heads/main', 'runtime': self.runtime,
                              'coverage': {'unit': 'PASS', 'audit': 'SKIP'}}
        artifact = dict(ARTIFACT_LINUX, name='ci-evidence-ci-test-1', created_at=iso(-301),
                        workflow_run=dict(ORIGIN, head_sha=self.sha))
        data = {'': {'id': REPO_ID, 'full_name': REPO, 'default_branch': 'main'},
                'git/ref/tags/v1.2.3': {'ref': 'refs/tags/v1.2.3', 'object': {'type': 'tag', 'sha': TAG_OBJECT}},
                'git/tags/' + TAG_OBJECT: {'object': {'type': 'commit', 'sha': self.sha}},
                'actions/workflows/ci.yml': {'id': 9, 'name': 'CI', 'path': '.github/workflows/ci.yml', 'state': 'active'},
                'actions/workflows/9/runs?head_sha=%s&per_page=100&page=1' % self.sha:
                    {'total_count': 1, 'workflow_runs': [run]},
                'actions/runs/100': run,
                JOBS: {'total_count': 1, 'jobs': [job]},
                ARTIFACTS: {'total_count': 1, 'artifacts': [artifact]}}
        pack(data, artifact, payload)
        return data

    def cli(self, data, mode='verify', extra=(), env=None):
        self.fixture_api.write_text(json.dumps({
            key: {'_binary': base64.b64encode(value).decode()} if isinstance(value, bytes) else value
            for key, value in data.items()}))
        return subprocess.run([sys.executable, str(self.root / 'release_evidence.py'), mode, *extra],
                              cwd=self.root, env=dict(self.env, **(env or {})), text=True,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=60)

    def record(self, name):
        path = Path(self.root.parent) / name
        return path, ['--output', str(path)]

    def test_verify_reuse_writes_the_record(self):
        path, extra = self.record('reuse.json')
        result = self.cli(self.world(), extra=extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(path.read_text())
        self.assertEqual(json.loads(result.stdout), record)
        self.assertEqual((record['decision'], record['refusal'], record['source']), ('reuse', None, self.sha))
        self.assertEqual(record['inputs'], self.inputs)
        self.assertEqual(record['workflows']['ci']['jobs']['test']['coverage'], {'unit': 'PASS', 'audit': 'SKIP'})
        self.assertIn('release-evidence: reuse: ci run 100 attempt 1', result.stderr)

    def test_verify_refusal_writes_the_record_and_fails(self):
        data = self.world()
        data['actions/runs/100']['conclusion'] = 'failure'
        path, extra = self.record('refuse.json')
        result = self.cli(data, extra=extra)
        self.assertEqual(result.returncode, 1)
        record = json.loads(path.read_text())
        self.assertEqual((record['decision'], record['refusal']['code']), ('refuse', 'run-result'))
        self.assertEqual(record['workflows']['ci']['run_id'], 100)
        self.assertIn('release-evidence: refuse: run-result', result.stderr)

    def test_verify_refuses_empty_missing_or_oversized_answers(self):
        for name, change in (('empty', lambda d: d.update({'actions/workflows/ci.yml': {}})),
                             ('missing', lambda d: d.pop(JOBS)),
                             ('oversized', lambda d: d['actions/runs/100/artifacts?per_page=100&page=1']['artifacts'][0].update(size_in_bytes=2 << 20))):
            with self.subTest(case=name):
                data = self.world()
                change(data)
                path, extra = self.record(name + '.json')
                result = self.cli(data, extra=extra)
                self.assertEqual(result.returncode, 1)
                record = json.loads(path.read_text())
                self.assertEqual(record['decision'], 'refuse')
                self.assertIn(record['refusal']['code'], {'unavailable-or-malformed', 'api-unavailable', 'artifact-size'})

    def test_verify_refuses_another_context(self):
        for env, code in (({'GITHUB_SHA': 'invalid'}, 'source-sha'), ({'GITHUB_SHA': OTHER}, 'checkout-sha'),
                          ({'GITHUB_REPOSITORY': 'other/project'}, 'context-repository'),
                          ({'GITHUB_REPOSITORY_ID': '0'}, 'context-repository-id'),
                          ({'RELEASE_TAG': 'v01.2.3'}, 'tag-syntax'),
                          ({'ImageVersion': '20261026.1'}, 'runtime-identity')):
            with self.subTest(code=code):
                path, extra = self.record('context.json')
                result = self.cli(self.world(), extra=extra, env=env)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(path.read_text())['refusal']['code'], code)

    def test_verify_refuses_a_changed_checkout(self):
        config = self.root / '.github/ci-evidence.json'
        original = config.read_bytes()
        self.addCleanup(config.write_bytes, original)
        config.write_bytes(original.replace(b'"max_age_hours": 48', b'"max_age_hours": 47'))
        path, extra = self.record('changed.json')
        result = self.cli(self.world(), extra=extra)
        self.assertEqual(json.loads(path.read_text())['refusal']['code'], 'checkout-changed')
        self.assertEqual(result.returncode, 1)

    def test_verify_refuses_a_helper_that_is_not_the_committed_one(self):
        helper = self.root / 'release_evidence.py'
        original = helper.read_bytes()
        def git(*args):
            subprocess.run(['git', *args], cwd=self.root, env=self.env, check=True,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        git('update-index', '--skip-worktree', 'release_evidence.py')
        self.addCleanup(git, 'update-index', '--no-skip-worktree', 'release_evidence.py')
        self.addCleanup(helper.write_bytes, original)
        helper.write_bytes(original + b'\n# not the bytes the commit holds\n')
        path, extra = self.record('helper.json')
        result = self.cli(self.world(), extra=extra)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(path.read_text())['refusal']['code'], 'helper-source')

    def test_capture_writes_the_evidence_verify_takes(self):
        log = self.root.parent / 'checks.log'
        log.write_text('== check summary (dev.json) ==\nPASS     unit 1s\nSKIP     audit needs AUDIT\n'
                       '== 1 passed, 0 failed, 1 skipped, 0 not run ==\n')
        output = self.root.parent / 'evidence.json'
        result = self.cli({}, 'capture', ['--workflow', 'ci', '--job', 'test', '--check-log', str(log),
                                          '--output', str(output)], self.capture_env)
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = json.loads(output.read_text())
        self.assertEqual(captured['inputs'], self.inputs)
        self.assertEqual(captured['runtime'], self.runtime)
        self.assertEqual((captured['ref'], captured['job'], captured['run_id'], captured['attempt']),
                         ('refs/heads/main', 'test', 100, 1))
        self.assertEqual(captured['coverage'], {'unit': 'PASS', 'audit': 'SKIP'})
        # Round trip: what capture wrote is what verify takes.
        path, extra = self.record('round-trip.json')
        result = self.cli(self.world(captured), extra=extra)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_capture_refusals(self):
        log = self.root.parent / 'producer.log'
        extra = ['--workflow', 'ci', '--job', 'test', '--check-log', str(log),
                 '--output', str(self.root.parent / 'refused.json')]
        log.write_text('PASS unit 1s\nSKIP audit needs AUDIT\n')
        for env, code in (({'GITHUB_REF': 'refs/tags/v1.2.3'}, 'capture-ref'),
                          ({'GITHUB_REF': 'refs/heads/feature'}, 'capture-ref'),
                          ({'GITHUB_EVENT_NAME': 'pull_request'}, 'capture-event'),
                          ({'GITHUB_JOB': 'other'}, 'capture-job'),
                          ({'GITHUB_WORKFLOW_REF': REPO + '/.github/workflows/other.yml@refs/heads/main'}, 'capture-workflow'),
                          ({'GITHUB_WORKFLOW_SHA': OTHER}, 'capture-workflow'),
                          ({'RUNNER_ARCH': 'ARM64'}, 'runner-platform'),
                          ({'ImageOS': ''}, 'runner-identity')):
            with self.subTest(code=code, env=env):
                result = self.cli({}, 'capture', extra, dict(self.capture_env, **env))
                self.assertEqual(result.returncode, 1)
                self.assertIn('capture refused: ' + code, result.stderr)
        for text, code in (('infrastructure failure: log unavailable\nPASS unit 1s\nSKIP audit x\n', 'check-infrastructure'),
                           ('PASS unit 1s\nPASS unit 1s\nSKIP audit x\n', 'check-duplicate'),
                           ('SKIP unit needs ENV\nSKIP audit x\n', 'check-result'),
                           ('PASS unit 1s\n', 'check-coverage')):
            with self.subTest(code=code):
                log.write_text(text)
                result = self.cli({}, 'capture', extra, self.capture_env)
                self.assertEqual(result.returncode, 1)
                self.assertIn('capture refused: ' + code, result.stderr)


if __name__ == '__main__':
    unittest.main()
