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
import re
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
        resolve = patch.object(e, 'runtime', side_effect=lambda profile, variant=None: copy.deepcopy(self.here))
        resolve.start()
        self.addCleanup(resolve.stop)
        self.api = None

    def decide(self, tag='v1.2.3', mode='publication'):
        self.api = FakeAPI(self.data)
        record = {'workflows': {}, 'mode': mode}
        e.decide(self.api, self.config, copy.deepcopy(SOURCE), tag, NOW, record)
        self.record = record
        if record['decision'] == 'revalidate':
            # Only a publication revalidates, with no refusal and the drift recorded.
            self.assertIsNone(record['refusal'])
            self.assertEqual(mode, 'publication')
            self.assertEqual(set(record['revalidation']), {'reason', 'jobs', 'differences'})
            return record['decision']
        self.assertNotIn('revalidation', record)
        if record['decision'] in ('reuse', 'validated'):
            self.assertIsNone(record['refusal'])
            # Only a publication reuses; only a validation-only run is validated.
            self.assertEqual(record['decision'], {'publication': 'reuse'}.get(mode, 'validated'))
            return record['decision']
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
        self.assertEqual(self.api.calls.count('git/ref/tags/v1.2.3'), 2)
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
        self.refuses('runtime-identity', lambda: self.evidence(0, lambda p: p.update(runtime=None)))
        self.assertIn('no runtime record', self.record['refusal']['detail'])
        # The runtime identity is the job's last check: a missing member is the evidence's shape.
        self.data = world()
        self.refuses('evidence-identity', lambda: self.evidence(0, lambda p: p.pop('runtime')))
        self.data = world()
        self.refuses('runtime-identity', lambda: self.evidence(1, lambda p: p['runtime']['tools'].update(cc='clang')))

    def test_unexpected_members_in_the_evidence(self):
        self.refuses('evidence-identity', lambda: self.evidence(0, lambda p: p.update(green=True)))


class Revalidation(Gate):
    """The opt-in route: a publication whose one refusal is the release runner's drift decides
    revalidate, after every other check of verify; no other refusal is turned."""

    def setUp(self):
        super().setUp()
        self.config['revalidation'] = {'allowed': True}

    def roll(self, **tools):
        """The release runner drew a newer hosted image under the same label."""
        self.here['runner']['ImageVersion'] = '20261027.2'
        self.here['tools'].update(tools)

    def test_a_rolled_image_is_revalidated_with_the_drift_recorded(self):
        self.roll()
        self.assertEqual(self.decide(), 'revalidate')
        # Both sides of the drift, and only the differing key: the evidence's value and this runner's.
        self.assertEqual(self.record['revalidation'], {
            'reason': "test-linux: differs from this runner in ['ImageVersion']", 'jobs': ['test-linux'],
            'differences': [{'workflow': 'ci', 'job': 'test-linux',
                             'runner': {'ImageVersion': {'recorded': '20261020.1', 'release_runner': '20261027.2'}},
                             'tools': {}}]})
        # Every other check ran: every leg's evidence is recorded, the tag read before and after.
        ci = self.record['workflows']['ci']
        self.assertEqual(sorted(ci['jobs']), ['test-linux', 'test-macos'])
        self.assertEqual(ci['jobs']['test-linux']['runtime'], LINUX)
        self.assertEqual(self.record['tag_object'], TAG_OBJECT)
        self.assertEqual(self.api.calls.count('git/ref/tags/v1.2.3'), 2)

    def test_two_drifting_legs_are_each_recorded_with_their_own_values(self):
        self.config['workflows']['ci']['jobs']['lint-linux'] = {
            'name': 'lint (ubuntu-latest)', 'job_id': 'lint', 'labels': ['ubuntu-latest'], 'profile': 'linux',
            'checks': ['unit']}
        older = copy.deepcopy(LINUX)
        older['runner']['ImageVersion'] = '20261013.4'
        self.set_jobs(self.jobs + [dict(JOB_LINUX, id=204, name='lint (ubuntu-latest)')])
        artifact = dict(ARTIFACT_LINUX, id=304, name='ci-evidence-ci-lint-linux-1')
        self.set_artifacts(self.artifacts + [artifact])
        pack(self.data, self.artifacts[-1], dict(EVIDENCE_LINUX, job='lint-linux', runtime=older,
                                                 coverage={'unit': 'PASS'}))
        self.roll()
        self.assertEqual(self.decide(), 'revalidate')
        self.assertEqual(self.record['revalidation'], {
            'reason': "test-linux: differs from this runner in ['ImageVersion']; "
                      "lint-linux: differs from this runner in ['ImageVersion']",
            'jobs': ['test-linux', 'lint-linux'],
            'differences': [
                {'workflow': 'ci', 'job': 'test-linux', 'tools': {},
                 'runner': {'ImageVersion': {'recorded': '20261020.1', 'release_runner': '20261027.2'}}},
                {'workflow': 'ci', 'job': 'lint-linux', 'tools': {},
                 'runner': {'ImageVersion': {'recorded': '20261013.4', 'release_runner': '20261027.2'}}}]})

    def test_the_jobs_are_every_release_runner_leg(self):
        linux = self.config['workflows']['ci']['jobs']['test-linux']
        self.config['workflows']['nightly'] = {
            'path': '.github/workflows/ci.yml', 'name': 'CI', 'events': ['push'],
            'skipped_jobs': ['PR sample'],
            'jobs': {'test-linux': linux, 'test-macos': self.config['workflows']['ci']['jobs']['test-macos']}}
        self.assertEqual(e.runner_bound_jobs(self.config), ['test-linux'])
        self.config['workflows']['ci']['jobs']['lint'] = dict(linux, name='lint')
        self.assertEqual(e.runner_bound_jobs(self.config), ['test-linux', 'lint'])

    def test_a_tool_that_moved_with_the_image_is_revalidated(self):
        self.config['profiles']['linux'].pop('pins')
        self.roll(go='go version go1.26.6 linux/amd64')
        self.assertEqual(self.decide(), 'revalidate')
        self.assertIn("['ImageVersion', 'go']", self.record['revalidation']['reason'])
        self.assertEqual(self.record['revalidation']['differences'], [{
            'workflow': 'ci', 'job': 'test-linux',
            'runner': {'ImageVersion': {'recorded': '20261020.1', 'release_runner': '20261027.2'}},
            'tools': {'go': {'recorded': 'go version go1.26.5 linux/amd64',
                             'release_runner': 'go version go1.26.6 linux/amd64'}}}])

    def test_the_drift_refuses_without_the_opt_in(self):
        for revalidation in (None, {'allowed': False}):
            with self.subTest(revalidation=revalidation):
                self.setUp()
                if revalidation is None:
                    self.config.pop('revalidation')
                else:
                    self.config['revalidation'] = revalidation
                self.roll()
                self.refuses('runtime-identity')
                self.assertIn("test-linux: differs from this runner in ['ImageVersion']",
                              self.record['refusal']['detail'])

    def test_a_validation_run_never_revalidates(self):
        self.roll()
        self.assertEqual(self.decide(None, 'validation-only'), 'runtime-identity')
        self.assertIn('ImageVersion', self.record['refusal']['detail'])
        for mode in (None, 'reuse', 'revalidate'):
            with self.subTest(mode=mode):
                self.assertEqual(self.decide('v1.2.3', mode), 'mode-unknown')

    def test_a_pin_that_does_not_match_refuses(self):
        self.roll()
        # A leg held to pins.
        self.refuses('runtime-identity', lambda: self.evidence(1, lambda p: p['runtime']['tools'].update(
            go='go version go1.26.4 darwin/arm64')))
        self.assertIn('pinned', self.record['refusal']['detail'])
        # A release-runner leg's own pin, in the evidence or on this runner.
        self.data = world()
        self.refuses('runtime-identity', lambda: self.evidence(0, lambda p: p['runtime']['tools'].update(
            go='go version go1.26.4 linux/amd64')))
        self.assertIn('pinned', self.record['refusal']['detail'])
        self.data = world()
        self.roll(go='go version go1.26.6 linux/amd64')
        self.refuses('runtime-identity')
        self.assertIn('pinned', self.record['refusal']['detail'])

    def test_a_runtime_record_of_another_shape_refuses(self):
        self.roll()
        for change in (lambda p: p['runtime']['runner'].update(green='true'),
                       lambda p: p['runtime']['runner'].pop('os_release'),
                       lambda p: p['runtime']['runner'].update(ImageVersion=20261020),
                       lambda p: p['runtime']['runner'].update(RUNNER_OS='macOS'),
                       lambda p: p['runtime']['tools'].update(cc='clang'),
                       lambda p: p.update(runtime=None)):
            with self.subTest(change=change):
                self.data = world()
                self.refuses('runtime-identity', lambda: self.evidence(0, change))
                self.assertNotIn('differs from this runner', self.record['refusal']['detail'])

    def test_every_other_refusal_wins_over_the_drift(self):
        cases = {
            'run-result': lambda: self.both_runs(conclusion='failure'),
            'run-age': lambda: self.both_runs(run_started_at='2026-10-23T11:59:59Z'),
            'job-runner': lambda: self.jobs[0].update(runner_group_id=2, runner_group_name='Default'),
            'artifact-digest': lambda: self.artifacts[0].update(digest='sha256:' + '0' * 64),
            'input-identity': lambda: self.evidence(0, lambda p: p['inputs'].update({'dev.json': '9' * 40})),
            'check-coverage': lambda: self.evidence(0, lambda p: p.update(coverage={'audit': 'SKIP'})),
            'check-result': lambda: self.evidence(0, lambda p: p['coverage'].update(unit='FAIL')),
            'evidence-identity': lambda: self.evidence(0, lambda p: p.update(green=True)),
            'tag-commit': lambda: self.data['git/tags/' + TAG_OBJECT]['object'].update(sha=OTHER),
        }
        for code, change in cases.items():
            with self.subTest(code=code):
                self.setUp()
                self.roll()
                self.refuses(code, change)

    def test_a_check_failure_wins_over_a_runtime_refusal_of_the_same_job(self):
        def both(p):
            p['coverage'].update(unit='FAIL')
            p['runtime']['tools'].update(go='go version go1.26.4 linux/amd64')
        self.refuses('check-result', lambda: self.evidence(0, both))

    def test_a_newer_failed_or_cancelled_applicable_attempt_wins_over_the_drift(self):
        for conclusion in ('failure', 'cancelled'):
            # Listed from the start: the newer attempt is the selected one, and it did not succeed.
            with self.subTest(conclusion=conclusion, when='listed'):
                self.setUp()
                self.roll()
                newer = dict(RUN, id=101, event='workflow_dispatch', conclusion=conclusion,
                             created_at='2026-10-25T11:00:00Z', run_started_at='2026-10-25T11:00:00Z')
                self.add_run(newer)
                self.data['actions/runs/101'] = newer
                self.refuses('run-result')
            # Appearing while the evidence is read, or after every workflow was read.
            for listing_from, code in ((2, 'latest-changed'), (3, 'final-latest-changed')):
                with self.subTest(conclusion=conclusion, when=code):
                    self.setUp()
                    self.roll()
                    lists = []
                    def listing(listing_from=listing_from, conclusion=conclusion):
                        lists.append(1)
                        runs = [RUN] + ([dict(RUN, id=101, event='workflow_dispatch', conclusion=conclusion,
                                              run_started_at='2026-10-25T11:59:00Z')]
                                        if len(lists) >= listing_from else [])
                        return {'total_count': len(runs), 'workflow_runs': runs}
                    self.data[RUNS] = listing
                    self.refuses(code)

    def test_a_new_attempt_or_a_moved_tag_wins_over_the_drift(self):
        self.roll()
        reads = []
        def run():
            reads.append(1)
            return dict(RUN, run_attempt=1 if len(reads) == 1 else 2)
        self.data['actions/runs/100'] = run
        self.refuses('attempt-changed')
        self.setUp()
        self.roll()
        tags = []
        def reference():
            tags.append(1)
            return {'ref': 'refs/tags/v1.2.3',
                    'object': {'type': 'tag', 'sha': TAG_OBJECT if len(tags) == 1 else 'u' * 40}}
        self.data['git/ref/tags/v1.2.3'] = reference
        self.data['git/tags/' + 'u' * 40] = {'object': {'type': 'commit', 'sha': SHA}}
        self.refuses('tag-changed')


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


class TagGrammar(Gate):
    """The configured tag rule: vMAJOR.MINOR.PATCH, with a SemVer prerelease only where allowed."""

    PRERELEASES = ('v1.2.3-alpha.1', 'v1.2.3-0', 'v1.2.3-rc.1-x', 'v1.2.3-x.7.z-92', 'v1.2.3-0a')
    REFUSED = ('v1.2.3-', 'v1.2.3-01', 'v1.2.3-alpha.01', 'v1.2.3-alpha..1', 'v1.2.3-alpha.',
               'v1.2.3+build', 'v1.2.3-alpha+build', 'v1.2.3-alpha_1', 'v1.2.3-\u00e9',
               'v1.2.3-alpha\n', 'v01.2.3-alpha', 'v1.2-alpha', '1.2.3-alpha')

    def tag(self, name, sha=SHA, kind='tag'):
        """An annotated tag (kind tag) or a lightweight one (kind commit) naming sha."""
        quoted = e.quote(name, safe='')
        obj = 'o%039d' % len(self.data)
        self.data['git/ref/tags/' + quoted] = {'ref': 'refs/tags/' + name,
                                               'object': {'type': kind, 'sha': obj if kind == 'tag' else sha}}
        self.data['git/tags/' + obj] = {'object': {'type': 'commit', 'sha': sha}}

    def test_the_default_refuses_a_prerelease(self):
        for name in self.PRERELEASES:
            with self.subTest(tag=name):
                self.tag(name)
                self.assertEqual(self.decide(name), 'tag-syntax')
        self.config['tag'] = {'prerelease': False}
        self.assertEqual(self.decide('v1.2.3-alpha.1'), 'tag-syntax')
        self.assertEqual(self.decide(), 'reuse')

    def test_a_prerelease_is_taken_where_allowed(self):
        self.config['tag'] = {'prerelease': True}
        for name in self.PRERELEASES + ('v1.2.3',):
            with self.subTest(tag=name):
                self.tag(name)
                self.assertEqual(self.decide(name), 'reuse')
                self.assertEqual(self.api.calls.count('git/ref/tags/' + e.quote(name, safe='')), 2)

    def test_only_the_prerelease_grammar_is_allowed(self):
        self.config['tag'] = {'prerelease': True}
        for name in self.REFUSED:
            with self.subTest(tag=name):
                self.tag(name)
                self.assertEqual(self.decide(name), 'tag-syntax')

    def test_a_prerelease_stays_bound_to_the_exact_commit_and_annotated(self):
        self.config['tag'] = {'prerelease': True}
        self.tag('v1.2.3-alpha.1', sha=OTHER)
        self.assertEqual(self.decide('v1.2.3-alpha.1'), 'tag-commit')
        self.tag('v1.2.3-alpha.2', kind='commit')
        self.assertEqual(self.decide('v1.2.3-alpha.2'), 'tag-annotated')


class DispatchValidation(Gate):
    """A workflow_dispatch run: refused by default, or validation-only of the branch tip."""

    def mode(self, env, dispatch=None):
        config = copy.deepcopy(CONFIG)
        if dispatch:
            config['dispatch'] = {'validates': dispatch}
        with patch.dict(os.environ, env):
            try:
                return e.release_mode(config)
            except e.Refusal as error:
                return error.code

    def test_the_run_decides_its_mode(self):
        dispatch = {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': 'refs/heads/main'}
        cases = (({'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/tags/v1.2.3'}, None, 'publication'),
                 ({'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/tags/v1.2.3'}, 'branch-tip', 'publication'),
                 (dispatch, None, 'dispatch-not-gated'),
                 (dispatch, 'none', 'dispatch-not-gated'),
                 (dispatch, 'branch-tip', 'validation-only'),
                 (dict(dispatch, GITHUB_REF='refs/heads/feature'), 'branch-tip', 'dispatch-ref'),
                 (dict(dispatch, GITHUB_REF='refs/tags/v1.2.3'), 'branch-tip', 'dispatch-ref'))
        for env, validates, outcome in cases:
            with self.subTest(env=env, validates=validates):
                self.assertEqual(self.mode(env, validates), outcome)

    def test_a_validation_run_is_validated_and_reads_no_tag(self):
        for name in ('git/ref/tags/v1.2.3', 'git/tags/' + TAG_OBJECT):
            self.data.pop(name)
        self.assertEqual(self.decide(None, 'validation-only'), 'validated')
        self.assertNotIn('tag_object', self.record)
        self.assertFalse([call for call in self.api.calls if call.startswith('git/')])
        self.assertEqual(self.record['workflows']['ci']['run_id'], 100)
        # The publication path still reads the tag: without it, nothing is reused.
        self.assertEqual(self.decide('v1.2.3', 'publication'), 'api-unavailable')

    def test_a_validation_run_is_never_a_publication_decision(self):
        # Even with a tag that would pass at the commit, validation-only is not reuse.
        self.assertEqual(self.decide('v1.2.3', 'validation-only'), 'validated')
        for mode in (None, '', 'reuse', 'validated'):
            with self.subTest(mode=mode):
                self.assertEqual(self.decide('v1.2.3', mode), 'mode-unknown')

    def test_a_validation_run_is_held_to_the_same_evidence(self):
        self.both_runs(conclusion='failure')
        self.assertEqual(self.decide(None, 'validation-only'), 'run-result')
        self.setUp()
        self.evidence(0, lambda payload: payload.update(source=OTHER))
        self.assertEqual(self.decide(None, 'validation-only'), 'evidence-identity')
        self.setUp()
        self.data['']['default_branch'] = 'trunk'
        self.assertEqual(self.decide(None, 'validation-only'), 'branch-default')


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
            'tag rule not an object': lambda c: c.update(tag='v*'),
            'tag rule without prerelease': lambda c: c.update(tag={}),
            'tag prerelease not a boolean': lambda c: c.update(tag={'prerelease': 'yes'}),
            'tag rule with a pattern': lambda c: c.update(tag={'prerelease': True, 'pattern': '.*'}),
            'dispatch not an object': lambda c: c.update(dispatch='branch-tip'),
            'dispatch without validates': lambda c: c.update(dispatch={}),
            'dispatch validates the tag': lambda c: c.update(dispatch={'validates': 'tag'}),
            'revalidation not an object': lambda c: c.update(revalidation=True),
            'revalidation without allowed': lambda c: c.update(revalidation={}),
            'revalidation allowed as text': lambda c: c.update(revalidation={'allowed': 'true'}),
            'revalidation allowed as a number': lambda c: c.update(revalidation={'allowed': 1}),
            'revalidation allowed null': lambda c: c.update(revalidation={'allowed': None}),
            'revalidation with another member': lambda c: c.update(revalidation={'allowed': True, 'codes': ['run-age']}),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                self.assertEqual(at(change), 'config-invalid')
        config = copy.deepcopy(CONFIG)
        config['revalidation'] = {'allowed': 'true'}
        with self.assertRaises(e.Refusal) as refused:
            e.check_config(config)
        self.assertTrue(refused.exception.detail.startswith('config.revalidation'), refused.exception.detail)

    def test_optional_members_and_comments_are_accepted(self):
        config = copy.deepcopy(CONFIG)
        config.pop('fresh_at_release')
        config['workflows']['ci'].pop('skipped_jobs')
        config['profiles']['linux'].pop('pins')
        config['$comment'] = ['a', 'b']
        config['workflows']['ci']['jobs']['test-linux']['$comment'] = 'a leg'
        self.assertEqual(self.outcome(config), 'valid')
        for tag, dispatch in (({'prerelease': True}, {'validates': 'branch-tip'}),
                              ({'prerelease': False, '$comment': 'x'}, {'validates': 'none', '$comment': 'y'})):
            with self.subTest(tag=tag, dispatch=dispatch):
                self.assertEqual(self.outcome(dict(config, tag=tag, dispatch=dispatch)), 'valid')
        for revalidation in ({'allowed': True}, {'allowed': False, '$comment': ['z']}):
            with self.subTest(revalidation=revalidation):
                self.assertEqual(self.outcome(dict(config, revalidation=revalidation)), 'valid')

    def test_revalidation_is_off_unless_allowed(self):
        config = copy.deepcopy(CONFIG)
        self.assertFalse(e.revalidation_allowed(config))
        self.assertFalse(e.revalidation_allowed(dict(config, revalidation={'allowed': False})))
        self.assertTrue(e.revalidation_allowed(dict(config, revalidation={'allowed': True})))
        template = json.loads((ROOT / 'templates/ci-evidence.json').read_text())
        self.assertEqual(template['revalidation']['allowed'], False)


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

    def test_the_publication_path_takes_reuse_or_a_passed_revalidation(self):
        release = (ROOT / '.github/workflows/release.yml').read_text()
        self.assertIn('      - name: Reuse exact-commit main CI evidence, or refuse\n        id: gate\n', release)
        self.assertIn('    outputs:\n      # reuse, revalidate, refuse or validated; reuse is a publication decision, '
                      'and revalidate is\n      # one only with the success of the revalidate job.\n'
                      '      decision: ${{ steps.gate.outputs.decision }}\n', release)
        # The package job, which every publishing job needs, begins with the decision.
        package = release[release.index('\n  package:\n'):release.index('\n  attest-and-draft:\n')]
        self.assertIn('      - verify\n      - revalidate\n', package)
        steps = package[package.index('    steps:\n'):]
        head = '    steps:\n      # Only a publication decision'
        self.assertTrue(steps.startswith(head), steps[:200])
        self.assertIn('          DECISION: ${{ needs.verify.outputs.decision }}\n', steps)
        self.assertIn('          REVALIDATED: ${{ needs.revalidate.result }}\n', steps)
        script = steps[steps.index('        run: |\n') + len('        run: |\n'):steps.index('\n\n')]
        script = '\n'.join(line[10:] for line in script.splitlines())
        cases = [(('reuse', 'skipped'), 0), (('revalidate', 'success'), 0)]
        cases += [((decision, result), 1)
                  for decision in ('reuse', 'revalidate', 'validated', 'refuse', '', 'reuse ', 'revalidate ')
                  for result in ('skipped', 'success', 'failure', 'cancelled', '')
                  if (decision, result) not in (('reuse', 'skipped'), ('revalidate', 'success'))]
        for (decision, result), status in cases:
            with self.subTest(decision=decision, revalidated=result):
                outcome = subprocess.run(['bash', '-c', script],
                                         env={'DECISION': decision, 'REVALIDATED': result, 'PATH': os.environ['PATH']},
                                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, timeout=30)
                self.assertEqual(outcome.returncode, status, outcome.stderr)

    # The fresh job, exactly as it must be: no continue-on-error on the job or a step, no shell
    # option or command that keeps a failed check list from failing its step, and nothing but the
    # setup steps and the whole list, run strictly. The checkout line is the one the workflow pins.
    REVALIDATE_JOB = """  revalidate:
    name: Check list on the release runner
    needs: verify
    if: ${{ needs.verify.outputs.decision == 'revalidate' }}
    runs-on: ubuntu-latest
    timeout-minutes: 20
    permissions:
      contents: read
    steps:
      # The whole history, as main CI checks it out.
      - uses: CHECKOUT
        with:
          fetch-depth: 0
          persist-credentials: false
          ref: ${{ github.sha }}
      - name: Run the setup steps of dev.json
        run: scripts/dev/check.sh --setup --strict
      - name: Run every check of dev.json
        run: |
          echo "Release runner image: ${ImageOS:-unknown} ${ImageVersion:-unknown}"
          scripts/dev/check.sh --all --strict
"""

    def test_a_revalidate_decision_runs_the_whole_check_list_on_a_release_runner(self):
        release = (ROOT / '.github/workflows/release.yml').read_text()
        config = json.loads((ROOT / '.github/ci-evidence.json').read_text())
        self.assertIs(config['revalidation']['allowed'], True)
        begin = release.index('\n  revalidate:\n') + 1
        job = release[begin:release.index('\n\n', begin) + 1]
        checkout = re.search(r'\n      - uses: (actions/checkout@[0-9a-f]{40} # v\S+)\n', release).group(1)
        self.assertEqual(job, self.REVALIDATE_JOB.replace('CHECKOUT', checkout))
        # Nothing in the release workflow is allowed to fail, and no default changes the steps' shell
        # (bash -e, which ends the step at the failing command).
        self.assertNotIn('continue-on-error', release)
        self.assertIsNone(re.search(r'^\s*(defaults|shell):', job, re.M))
        self.assertIsNone(re.search(r'^defaults:', release, re.M))
        # The package job reads the fresh job's own result, as the kit reads it.
        self.assertIn('          REVALIDATED: ${{ needs.revalidate.result }}\n', release)
        # Every check of dev.json is one the two CI jobs run between them, and the CI jobs run nothing
        # outside the list: their commands are check.sh and the capture, their actions the checkout
        # and the upload.
        manifest = json.loads((ROOT / 'dev.json').read_text())
        covered = [check for spec in config['workflows']['ci']['jobs'].values() for check in spec['checks']]
        self.assertEqual(sorted(covered), sorted(row['name'] for row in manifest['checks']))
        self.assertNotIn('setup', manifest)
        ci = (ROOT / '.github/workflows/ci.yml').read_text()
        commands, blocks = [], re.findall(r'\n        run: (\|\n(?:          .*\n)+|.*\n)', ci)
        self.assertEqual(len(blocks), len(re.findall(r'^\s+(?:- )?run:', ci, re.M)))
        for block in blocks:
            lines = block[2:].splitlines() if block.startswith('|\n') else [block]
            commands += [line.strip() for line in lines if line.strip()]
        allowed = ('set -o pipefail', 'if [ "$EVENT" = pull_request ]; then', 'else', 'fi',
                   'scripts/dev/check.sh ', 'python3 scripts/dev/release_evidence.py capture ')
        self.assertGreaterEqual(len(commands), 10)
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(command.startswith(allowed), command)
        self.assertEqual(sorted(set(re.findall(r'uses: ([a-z-]+/[a-z-]+)@', ci))),
                         ['actions/checkout', 'actions/upload-artifact'])
        # Each job after the gate runs only when every job it needs succeeded (revalidate: or was
        # skipped); none takes a skipped or failed job for a passed one.
        conditions = {
            'package': "    if: ${{ !cancelled() && needs.admit.result == 'success' && needs.verify.result == "
                       "'success' && (needs.revalidate.result == 'success' || needs.revalidate.result == "
                       "'skipped') }}\n",
            'attest-and-draft': "    if: ${{ !cancelled() && needs.package.result == 'success' }}\n",
            'publish': "    if: ${{ !cancelled() && needs.package.result == 'success' && "
                       "needs.attest-and-draft.result == 'success' }}\n"}
        for name, condition in conditions.items():
            with self.subTest(job=name):
                begin = release.index('\n  %s:\n' % name)
                block = release[begin:release.index('\n    steps:\n', begin)]
                self.assertIn(condition, block)


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


def fake_gh(bin_dir):
    """A gh on PATH that answers this repository's API reads from the FIXTURE_API file."""
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


def write_api(path, data):
    path.write_text(json.dumps({
        key: {'_binary': base64.b64encode(value).decode()} if isinstance(value, bytes) else value
        for key, value in data.items()}))


def cli_world(sha, payload):
    """The API answers for one push run of CI at sha, one job (tests) and its evidence, ten minutes
    old, and the annotated tag v1.2.3 naming sha."""
    now = dt.datetime.now(dt.timezone.utc)

    def iso(seconds):
        return (now + dt.timedelta(seconds=seconds)).isoformat().replace('+00:00', 'Z')
    run = dict(RUN, head_sha=sha, created_at=iso(-600), run_started_at=iso(-600), updated_at=iso(-300))
    job = dict(JOB_LINUX, name='tests', head_sha=sha, started_at=iso(-590), completed_at=iso(-300))
    artifact = dict(ARTIFACT_LINUX, name='ci-evidence-ci-test-1', created_at=iso(-301),
                    workflow_run=dict(ORIGIN, head_sha=sha))
    data = {'': {'id': REPO_ID, 'full_name': REPO, 'default_branch': 'main'},
            'git/ref/tags/v1.2.3': {'ref': 'refs/tags/v1.2.3', 'object': {'type': 'tag', 'sha': TAG_OBJECT}},
            'git/tags/' + TAG_OBJECT: {'object': {'type': 'commit', 'sha': sha}},
            'actions/workflows/ci.yml': {'id': 9, 'name': 'CI', 'path': '.github/workflows/ci.yml', 'state': 'active'},
            'actions/workflows/9/runs?head_sha=%s&per_page=100&page=1' % sha:
                {'total_count': 1, 'workflow_runs': [run]},
            'actions/runs/100': run,
            JOBS: {'total_count': 1, 'jobs': [job]},
            ARTIFACTS: {'total_count': 1, 'artifacts': [artifact]}}
    pack(data, artifact, payload)
    return data


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
        (cls.root / '.github/ci-evidence-dispatch.json').write_text(json.dumps(
            dict(cls.config, dispatch={'validates': 'branch-tip'}), indent=2) + '\n')
        (cls.root / '.github/ci-evidence-revalidate.json').write_text(json.dumps(
            dict(cls.config, revalidation={'allowed': True}, dispatch={'validates': 'branch-tip'}),
            indent=2) + '\n')
        (cls.root / '.github/workflows/ci.yml').write_text('name: CI\non: push\njobs:\n  test: {}\n')
        (cls.root / 'dev.json').write_text('{"version": 1, "checks": [{"name": "unit"}, {"name": "audit"}]}\n')
        tool = bin_dir / 'release-evidence-fixture-tool'
        tool.write_text('#!/bin/sh\necho "fixture-tool 1.0"\n')
        tool.chmod(0o755)
        fake_gh(bin_dir)
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
        paths[0] = '.github/ci-evidence-dispatch.json'
        ids = subprocess.check_output(['git', 'rev-parse'] + [cls.sha + ':' + path for path in paths],
                                      cwd=cls.root, text=True, stdin=subprocess.DEVNULL).split()
        cls.dispatch_inputs = dict(zip(paths, ids))
        paths[0] = '.github/ci-evidence-revalidate.json'
        ids = subprocess.check_output(['git', 'rev-parse'] + [cls.sha + ':' + path for path in paths],
                                      cwd=cls.root, text=True, stdin=subprocess.DEVNULL).split()
        cls.revalidate_inputs = dict(zip(paths, ids))
        cls.outputs = Path(scratch.name) / 'step-outputs'
        cls.env = dict(git_env, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'],
                       FIXTURE_API=str(cls.fixture_api), GITHUB_SHA=cls.sha,
                       GITHUB_REPOSITORY=REPO, GITHUB_REPOSITORY_ID=str(REPO_ID), ImageOS='ubuntu24',
                       ImageVersion='20261020.1', RUNNER_OS='Linux', RUNNER_ARCH='X64',
                       RELEASE_TAG='v1.2.3', GITHUB_EVENT_NAME='push', GITHUB_REF='refs/tags/v1.2.3',
                       GITHUB_OUTPUT=str(cls.outputs))
        cls.capture_env = {'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'push',
                           'GITHUB_JOB': 'test', 'GITHUB_RUN_ID': '100', 'GITHUB_RUN_ATTEMPT': '1',
                           'GITHUB_WORKFLOW_REF': REPO + '/.github/workflows/ci.yml@refs/heads/main',
                           'GITHUB_WORKFLOW_SHA': cls.sha}
        cls.runtime = {'runner': {'ImageOS': 'ubuntu24', 'ImageVersion': '20261020.1',
                                  'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64',
                                  'os_release': hashlib.sha256(Path('/etc/os-release').read_bytes()).hexdigest()},
                       'tools': {'fixture': 'fixture-tool 1.0'}}

    def world_payload(self):
        return {'schema': 2, 'repository': REPO, 'repository_id': REPO_ID,
                'source': self.sha, 'inputs': self.inputs, 'workflow': 'ci',
                'workflow_path': '.github/workflows/ci.yml', 'workflow_name': 'CI',
                'job': 'test', 'run_id': 100, 'attempt': 1, 'event': 'push',
                'ref': 'refs/heads/main', 'runtime': self.runtime,
                'coverage': {'unit': 'PASS', 'audit': 'SKIP'}}

    def world(self, payload=None):
        return cli_world(self.sha, payload or self.world_payload())

    def cli(self, data, mode='verify', extra=(), env=None):
        self.outputs.write_text('')
        write_api(self.fixture_api, data)
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

    def test_verify_writes_the_decision_and_mode_as_step_outputs(self):
        path, extra = self.record('outputs.json')
        result = self.cli(self.world(), extra=extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.outputs.read_text(), 'decision=reuse\nmode=publication\n')
        record = json.loads(path.read_text())
        self.assertEqual((record['mode'], record['event'], record['tag'], record['tag_prerelease'],
                          record['dispatch'], record['revalidation_allowed'], record['revalidation']),
                         ('publication', 'push', 'v1.2.3', False, 'none', False, None))
        data = self.world()
        data['actions/runs/100']['conclusion'] = 'failure'
        self.assertEqual(self.cli(data, extra=extra).returncode, 1)
        self.assertEqual(self.outputs.read_text(), 'decision=refuse\nmode=publication\n')

    def test_a_dispatch_run_does_not_use_the_gate_by_default(self):
        path, extra = self.record('dispatch.json')
        result = self.cli(self.world(), extra=extra, env={'GITHUB_EVENT_NAME': 'workflow_dispatch',
                                                          'GITHUB_REF': 'refs/heads/main'})
        self.assertEqual(result.returncode, 1)
        record = json.loads(path.read_text())
        self.assertEqual((record['decision'], record['refusal']['code'], record['mode']),
                         ('refuse', 'dispatch-not-gated', None))
        self.assertEqual(self.outputs.read_text(), 'decision=refuse\nmode=\n')

    def test_a_dispatch_validation_run_validates_the_tip_and_is_never_a_publication(self):
        def world():
            data = self.world(dict(self.world_payload(), inputs=self.dispatch_inputs))
            data.pop('git/ref/tags/v1.2.3')
            data.pop('git/tags/' + TAG_OBJECT)
            return data
        dispatch = {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': 'refs/heads/main',
                    'RELEASE_TAG': 'main'}
        path, extra = self.record('validation.json')
        extra = extra + ['--config', '.github/ci-evidence-dispatch.json']
        result = self.cli(world(), extra=extra, env=dispatch)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(path.read_text())
        self.assertEqual((record['decision'], record['mode'], record['tag'], record['source'], record['dispatch']),
                         ('validated', 'validation-only', None, self.sha, 'branch-tip'))
        self.assertNotIn('tag_object', record)
        self.assertEqual(self.outputs.read_text(), 'decision=validated\nmode=validation-only\n')
        self.assertIn('release-evidence: validated, validation-only and never a publication decision', result.stderr)
        for env, code in (({'GITHUB_REF': 'refs/heads/feature'}, 'dispatch-ref'),
                          ({'GITHUB_SHA': OTHER}, 'checkout-sha')):
            with self.subTest(code=code):
                result = self.cli(world(), extra=extra, env=dict(dispatch, **env))
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(path.read_text())['refusal']['code'], code)
        # A tag push under the same configuration is a publication: it reads the tag, and without
        # one it refuses.
        result = self.cli(world(), extra=extra)
        self.assertEqual(result.returncode, 1)
        record = json.loads(path.read_text())
        self.assertEqual((record['mode'], record['refusal']['code']), ('publication', 'api-unavailable'))
        self.assertEqual(self.outputs.read_text(), 'decision=refuse\nmode=publication\n')

    def test_verify_revalidates_a_rolled_image_where_allowed(self):
        path, extra = self.record('revalidate.json')
        extra = extra + ['--config', '.github/ci-evidence-revalidate.json']
        rolled = {'ImageVersion': '20261027.2'}
        world = lambda: self.world(dict(self.world_payload(), inputs=self.revalidate_inputs))
        result = self.cli(world(), extra=extra, env=rolled)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(path.read_text())
        self.assertEqual(json.loads(result.stdout), record)
        self.assertEqual((record['decision'], record['refusal'], record['mode'], record['revalidation_allowed']),
                         ('revalidate', None, 'publication', True))
        self.assertEqual(record['revalidation'], {
            'reason': "test: differs from this runner in ['ImageVersion']", 'jobs': ['test'],
            'differences': [{'workflow': 'ci', 'job': 'test',
                             'runner': {'ImageVersion': {'recorded': '20261020.1', 'release_runner': '20261027.2'}},
                             'tools': {}}]})
        self.assertEqual(record['workflows']['ci']['jobs']['test']['runtime'], self.runtime)
        self.assertEqual(self.outputs.read_text(), 'decision=revalidate\nmode=publication\n')
        self.assertIn("release-evidence: revalidate: test: differs from this runner in "
                      "['ImageVersion']", result.stderr)
        # The same image, under the same configuration: reuse.
        result = self.cli(world(), extra=extra)
        self.assertEqual((result.returncode, self.outputs.read_text()), (0, 'decision=reuse\nmode=publication\n'))
        self.assertIsNone(json.loads(path.read_text())['revalidation'])
        # A dispatch validation run of the same commit on the rolled image: refused.
        dispatch = dict(rolled, GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REF='refs/heads/main')
        result = self.cli(world(), extra=extra, env=dispatch)
        self.assertEqual(result.returncode, 1)
        record = json.loads(path.read_text())
        self.assertEqual((record['decision'], record['refusal']['code'], record['mode'], record['revalidation']),
                         ('refuse', 'runtime-identity', 'validation-only', None))
        self.assertEqual(self.outputs.read_text(), 'decision=refuse\nmode=validation-only\n')
        # Another refusal beside the rolled image: refused with its own code.
        data = world()
        data['actions/runs/100']['conclusion'] = 'failure'
        result = self.cli(data, extra=extra, env=rolled)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(path.read_text())['refusal']['code'], 'run-result')
        self.assertEqual(self.outputs.read_text(), 'decision=refuse\nmode=publication\n')

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


# --- the runner identity policy (devkit #59): a reported image identity, not a pinned VM image ----

MANIFEST_BYTES = (ROOT / 'templates/runner-identity.json').read_bytes()
MANIFEST_SHA = hashlib.sha256(MANIFEST_BYTES).hexdigest()
CHECKOUT = 'actions/checkout@' + '3' * 40
UPLOAD = 'actions/upload-artifact@' + '4' * 40
IDENTITY_RECORD = {'manifest': '.github/runner-identity.json', 'sha256': MANIFEST_SHA, 'revision': '1',
                   'kind': 'reported'}


def identity_config(config):
    """CONFIG under the policy: the manifest pinned, each profile with its variant and image name."""
    config = copy.deepcopy(config)
    config['identity'] = {'manifest': '.github/runner-identity.json', 'sha256': MANIFEST_SHA}
    config['profiles']['linux']['variant'] = 'linux-x64'
    config['profiles']['linux']['platform']['ImageOS'] = 'ubuntu24'
    config['profiles']['macos']['variant'] = 'macos-arm64'
    return config


class Identity(Gate):
    """decide() under the identity policy; the context at the commit is a fixture here (the
    manifest's own bytes, the actions the workflow names), read from git in IdentityAtCommit."""

    def setUp(self):
        super().setUp()
        self.config = identity_config(self.config)
        self.actions = {'ci': [CHECKOUT, UPLOAD]}
        variants = e.parse_identity_manifest(MANIFEST_BYTES)['variants']
        for name, target in (('identity_context', lambda config, sha: {
                                 'record': dict(IDENTITY_RECORD), 'variants': copy.deepcopy(variants),
                                 'actions': copy.deepcopy(self.actions)}),
                             ('release_workflow_actions', lambda source: {
                                 'path': '.github/workflows/release.yml', 'actions': [CHECKOUT]})):
            patcher = patch.object(e, name, side_effect=target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.evidence(0, lambda payload: payload.update(
            identity=dict(IDENTITY_RECORD, variant='linux-x64', actions=[CHECKOUT, UPLOAD])))
        self.evidence(1, lambda payload: (payload.update(
            identity=dict(IDENTITY_RECORD, variant='macos-arm64', actions=[CHECKOUT, UPLOAD])),
            payload['runtime']['runner'].update(os_release='e' * 64)))

    def runner(self, index, **changes):
        self.evidence(index, lambda payload: payload['runtime']['runner'].update(changes))

    def add_macos_leg(self, image_version):
        """A second macOS leg of the same profile and variant, reporting image_version."""
        self.config['workflows']['ci']['jobs']['lint-macos'] = {
            'name': 'lint (macos-latest)', 'job_id': 'lint', 'labels': ['macos-latest'],
            'profile': 'macos', 'checks': ['unit']}
        self.set_jobs(self.jobs + [dict(JOB_MACOS, id=204, name='lint (macos-latest)')])
        artifact = dict(ARTIFACT_MACOS, id=304, name='ci-evidence-ci-lint-macos-1')
        self.set_artifacts(self.artifacts + [artifact])
        payload = copy.deepcopy(EVIDENCE_MACOS)
        payload.update(job='lint-macos', identity=dict(IDENTITY_RECORD, variant='macos-arm64',
                                                       actions=[CHECKOUT, UPLOAD]))
        payload['runtime']['runner'].update(os_release='e' * 64, ImageVersion=image_version)
        pack(self.data, self.artifacts[-1], payload)

    def test_a_reported_identity_is_reused_and_recorded_per_variant_and_profile(self):
        self.assertEqual(self.decide(), 'reuse')
        identity = self.record['identity']
        self.assertEqual({key: identity[key] for key in IDENTITY_RECORD}, IDENTITY_RECORD)
        self.assertEqual(identity['statement'], 'a reported hosted-runner image identity, not a pinned VM image')
        self.assertEqual(identity['release_workflow']['actions'], [CHECKOUT])
        # Linux and macOS report different identities: they are never compared with each other.
        self.assertEqual(sorted(identity['groups']), ['linux-x64/linux', 'macos-arm64/macos'])
        self.assertEqual(identity['groups']['macos-arm64/macos']['jobs'], ['ci/test-macos'])
        self.assertEqual(identity['groups']['linux-x64/linux']['runtime'], LINUX)
        self.add_macos_leg('20261019.2')
        self.assertEqual(self.decide(), 'reuse')
        self.assertEqual(self.record['identity']['groups']['macos-arm64/macos']['jobs'],
                         ['ci/test-macos', 'ci/lint-macos'])

    def test_a_missing_identity_refuses(self):
        cases = [
            (0, lambda payload: payload.pop('identity')),
            (1, lambda payload: payload['identity'].pop('actions')),
            (0, lambda payload: payload['runtime']['runner'].pop('os_release')),
            (1, lambda payload: payload['runtime']['runner'].pop('os_release')),
            (0, lambda payload: payload['runtime']['runner'].update(ImageVersion='')),
            (1, lambda payload: payload['runtime']['runner'].pop('ImageOS')),
            (0, lambda payload: payload['runtime'].update(tools={})),
            (0, lambda payload: payload.pop('runtime')),
        ]
        for index, change in cases:
            with self.subTest(index=index):
                self.setUp()
                self.evidence(index, change)
                self.assertEqual(self.decide(), 'identity-missing')

    def test_an_unexpected_identity_refuses_and_is_never_revalidated(self):
        self.config['revalidation'] = {'allowed': True}
        cases = [
            (0, lambda payload: payload['runtime']['runner'].update(ImageOS='ubuntu26')),
            (1, lambda payload: payload['runtime']['runner'].update(ImageOS='macos14')),
            (0, lambda payload: payload['runtime']['runner'].update(ImageVersion='latest')),
            (0, lambda payload: payload['runtime']['runner'].update(ImageVersion='20261020.*')),
            (0, lambda payload: payload['runtime']['runner'].update(RUNNER_ARCH='ARM64')),
            (1, lambda payload: payload['runtime']['runner'].update(os_release='not a digest')),
            (0, lambda payload: payload['runtime']['runner'].update(ImageName='ubuntu-24.04')),
            (0, lambda payload: payload['identity'].update(revision='2')),
            (0, lambda payload: payload['identity'].update(sha256='0' * 64)),
            (0, lambda payload: payload['identity'].update(kind='pinned')),
            (1, lambda payload: payload['identity'].update(variant='macos-x64')),
            (0, lambda payload: payload['identity'].update(actions=[CHECKOUT])),
        ]
        for index, change in cases:
            with self.subTest(index=index):
                self.setUp()
                self.config['revalidation'] = {'allowed': True}
                self.evidence(index, change)
                self.assertEqual(self.decide(), 'identity-unexpected')
                self.assertIsNone(self.record['revalidation'] if 'revalidation' in self.record else None)

    def test_a_changed_identity_refuses_or_takes_the_fresh_route(self):
        # The release runner reports another image version or OS release than the CI job did: the
        # identity changed. It refuses (runtime-identity), or, where the configuration allows it,
        # takes the existing fresh route on the release runner.
        for change in ({'ImageVersion': '20261026.180.1'}, {'os_release': 'd' * 64}):
            with self.subTest(change=change):
                self.setUp()
                self.here['runner'].update(change)
                self.assertEqual(self.decide(), 'runtime-identity')
                self.config['revalidation'] = {'allowed': True}
                self.assertEqual(self.decide(), 'revalidate')
                self.assertEqual(self.record['revalidation']['jobs'], ['test-linux'])

    def test_legs_of_one_variant_and_profile_that_report_different_identities_refuse(self):
        # Two macOS legs, which the release runner cannot resolve, ran on different images: the
        # recorded versions are not normalized, and the image roll is not revalidated on Linux.
        self.config['revalidation'] = {'allowed': True}
        self.add_macos_leg('20261026.3')
        self.assertEqual(self.decide(), 'identity-changed')
        self.assertIn('20261019.2', self.record['refusal']['detail'])
        self.assertIn('20261026.3', self.record['refusal']['detail'])

    def test_an_identity_refusal_wins_over_a_drift(self):
        self.config['revalidation'] = {'allowed': True}
        self.here['runner']['ImageVersion'] = '20261026.180.1'
        self.runner(0, ImageOS='ubuntu26')
        self.assertEqual(self.decide(), 'identity-unexpected')

    def test_incomplete_evidence_refuses(self):
        self.set_jobs([job for job in self.jobs if job['name'] != 'test (macos-latest)'])
        self.assertEqual(self.decide(), 'job-coverage')
        self.setUp()
        self.set_artifacts(self.artifacts[:1])
        self.assertEqual(self.decide(), 'artifact-coverage')
        self.setUp()
        self.evidence(0, lambda payload: payload['coverage'].pop('unit'))
        self.assertEqual(self.decide(), 'check-coverage')

    def test_evidence_with_an_identity_is_refused_where_no_policy_is_configured(self):
        self.config = copy.deepcopy(CONFIG)
        self.assertEqual(self.decide(), 'evidence-identity')


def outcome_of(call):
    """'accepted', a refusal as 'code: detail', or the name of any other exception."""
    try:
        call()
        return 'accepted'
    except e.Refusal as error:
        return error.code + ': ' + error.detail
    except Exception as error:  # a broken safeguard fails its assertion, not the test run
        return type(error).__name__


class IdentityConfiguration(unittest.TestCase):
    def outcome(self, config):
        return outcome_of(lambda: e.check_config(config))

    def test_the_policy_needs_a_variant_an_image_name_and_a_tool_for_every_profile(self):
        config = identity_config(CONFIG)
        self.assertEqual(self.outcome(config), 'accepted')
        for change, where in (
                (lambda c: c['profiles']['macos'].pop('variant'), 'config.profiles.macos.variant'),
                (lambda c: c['profiles']['linux']['platform'].pop('ImageOS'), 'config.profiles.linux.platform.ImageOS'),
                (lambda c: c['profiles']['linux'].update(tools={}, pins={}), 'config.profiles.linux.tools'),
                (lambda c: c['identity'].update(sha256='ABC'), 'config.identity.sha256'),
                (lambda c: c['identity'].update(manifest='../manifest.json'), 'config.identity.manifest'),
                (lambda c: c['identity'].update(revision='1'), 'config.identity'),
                (lambda c: c.update(identity=[]), 'config.identity')):
            with self.subTest(where=where):
                changed = copy.deepcopy(config)
                change(changed)
                self.assertTrue(self.outcome(changed).startswith('config-invalid: ' + where), self.outcome(changed))
        plain = copy.deepcopy(CONFIG)
        plain['profiles']['linux']['variant'] = 'linux-x64'
        self.assertTrue(self.outcome(plain).startswith('config-invalid: config.profiles.linux.variant'))


class IdentityManifest(unittest.TestCase):
    def outcome(self, raw):
        return outcome_of(lambda: e.parse_identity_manifest(raw))

    def test_the_template_is_the_revision_the_gate_ships(self):
        manifest = e.parse_identity_manifest(MANIFEST_BYTES)
        self.assertEqual((manifest['manifestVersion'], manifest['identity']), (1, 'reported'))
        self.assertEqual(e.IDENTITY_REVISIONS[manifest['revision']], MANIFEST_SHA)
        self.assertEqual(sorted(manifest['variants']),
                         ['linux-arm64', 'linux-x64', 'macos-arm64', 'macos-x64', 'windows-x64'])
        # It says what it is: a reported identity, not a pinned VM image.
        self.assertIn('not a pinned VM image', ' '.join(manifest['$comment']))

    def test_refused_manifests(self):
        base = json.loads(MANIFEST_BYTES)
        cases = [
            (lambda m: m.update(manifestVersion=2), 'manifest.manifestVersion'),
            (lambda m: m.update(manifestVersion='1'), 'manifest.manifestVersion'),
            (lambda m: m.update(identity='pinned'), 'manifest.identity'),
            (lambda m: m.update(runner=['ImageOS', 'RUNNER_OS']), 'manifest.runner'),
            (lambda m: m.update(actions='tag'), 'manifest.actions'),
            (lambda m: m.update(revision='a b'), 'manifest.revision'),
            (lambda m: m.update(images={}), 'manifest:'),
            (lambda m: m.pop('variants'), 'manifest:'),
            (lambda m: m.update(variants={}), 'manifest.variants'),
            (lambda m: m['variants']['linux-x64'].update(RUNNER_OS='Plan9'), 'manifest.variants.linux-x64.RUNNER_OS'),
            (lambda m: m['variants']['linux-x64'].update(RUNNER_ARCH='riscv'), 'manifest.variants.linux-x64.RUNNER_ARCH'),
            (lambda m: m['variants']['linux-x64'].update(os_release='etc/os-release'), 'manifest.variants.linux-x64.os_release'),
            (lambda m: m['variants']['linux-x64'].update(imageVersion='20261020.1'), 'manifest.variants.linux-x64:'),
            (lambda m: m['variants'].update({'linux x64': m['variants']['linux-x64']}), 'manifest.variants.linux x64'),
        ]
        for change, where in cases:
            with self.subTest(where=where):
                manifest = copy.deepcopy(base)
                change(manifest)
                self.assertTrue(self.outcome(json.dumps(manifest).encode()).startswith('identity-config: ' + where),
                                self.outcome(json.dumps(manifest).encode()))
        repeated = MANIFEST_BYTES.replace(b'"revision": "1",', b'"revision": "1",\n  "revision": "2",')
        self.assertEqual(self.outcome(repeated), 'identity-config: a member is repeated')
        self.assertEqual(self.outcome(b'{"manifestVersion": 1'), 'identity-config: the manifest is not JSON')
        self.assertEqual(self.outcome(b'\xff'), 'identity-config: the manifest is not JSON')
        self.assertTrue(self.outcome(b' ' * (64 * 1024) + b'{}').startswith('identity-config: the manifest is over'))


def git_fixture(root, files):
    """A repository at root with files committed; its commit id."""
    git_env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
    for argv in (['git', 'init', '-q', '-b', 'main'], ['git', 'add', '.'],
                 ['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                  'commit', '-qm', 'fixture']):
        subprocess.run(argv, cwd=root, check=True, env=git_env, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True,
                                   stdin=subprocess.DEVNULL).strip()


class IdentityAtCommit(unittest.TestCase):
    """identity_context and the actions reader over a real fixture repository."""

    CI = ('name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n'
          '      # uses: a comment is not an action\n'
          '      - uses: %s # v7.0.1\n'
          '      - name: Set up\n        uses: ./.github/actions/setup\n'
          '      - uses: "docker://alpine@sha256:%s"\n'
          '  call:\n    uses: ./.github/workflows/reusable.yml\n' % (CHECKOUT, '9' * 64))
    SETUP = ('name: setup\nruns:\n  using: composite\n  steps:\n'
             "    - uses: 'actions/setup-go@%s'\n" % ('5' * 40))
    REUSABLE = 'on: workflow_call\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: %s\n' % UPLOAD

    def repository(self, **changes):
        files = {'.github/runner-identity.json': MANIFEST_BYTES, '.github/workflows/ci.yml': self.CI,
                 '.github/actions/setup/action.yml': self.SETUP,
                 '.github/workflows/reusable.yml': self.REUSABLE}
        files.update(changes)
        scratch = tempfile.TemporaryDirectory(prefix='release-evidence-identity-')
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name)
        sha = git_fixture(root, files)
        cwd = os.getcwd()
        os.chdir(root)
        self.addCleanup(os.chdir, cwd)
        return sha

    def outcome(self, call):
        return outcome_of(call)

    def test_the_context_at_the_commit(self):
        sha = self.repository()
        context = e.identity_context(identity_config(CONFIG), sha)
        self.assertEqual(context['record'], IDENTITY_RECORD)
        self.assertEqual(context['actions']['ci'], sorted([
            CHECKOUT, UPLOAD, 'actions/setup-go@' + '5' * 40, 'docker://alpine@sha256:' + '9' * 64,
            './.github/actions/setup', './.github/workflows/reusable.yml']))
        self.assertEqual(context['variants']['linux-x64']['os_release'], '/etc/os-release')

    def test_an_unpinned_or_unreadable_action_refuses(self):
        for text in ('      - uses: actions/checkout@v4\n', '      - uses: actions/checkout@main\n',
                     '      - uses: actions/checkout@%s\n' % ('3' * 39),
                     '      - uses: ${{ matrix.action }}\n', '      - uses: "${{ matrix.action }}"\n',
                     '      - uses: docker://alpine:3\n', '      - {uses: %s}\n' % CHECKOUT,
                     '      - uses: ./missing\n', '      - uses: ../outside\n'):
            with self.subTest(text=text):
                sha = self.repository(**{'.github/workflows/ci.yml': self.CI + '  more:\n    steps:\n' + text})
                self.assertTrue(self.outcome(lambda: e.identity_context(identity_config(CONFIG), sha))
                                .startswith('identity-unexpected: '))
        sha = self.repository(**{'.github/actions/setup/action.yml': self.SETUP.replace("@" + '5' * 40, '@v5')})
        self.assertTrue(self.outcome(lambda: e.identity_context(identity_config(CONFIG), sha))
                        .startswith('identity-unexpected: .github/actions/setup/action.yml names actions/setup-go@v5'))

    def test_a_manifest_that_is_not_the_pinned_shipped_revision_refuses(self):
        edited = MANIFEST_BYTES.replace(b'"macos-x64": {', b'"macos-intel": {')
        sha = self.repository(**{'.github/runner-identity.json': edited})
        self.assertTrue(self.outcome(lambda: e.identity_context(identity_config(CONFIG), sha))
                        .startswith('identity-config: .github/runner-identity.json is not the manifest'))
        config = identity_config(CONFIG)
        config['identity']['sha256'] = hashlib.sha256(edited).hexdigest()
        self.assertTrue(self.outcome(lambda: e.identity_context(config, sha))
                        .startswith('identity-config: revision 1 with these bytes is not'))

    def test_a_profile_whose_platform_is_not_its_variant_refuses(self):
        sha = self.repository()
        config = identity_config(CONFIG)
        config['profiles']['macos']['variant'] = 'linux-arm64'
        self.assertEqual(self.outcome(lambda: e.identity_context(config, sha)),
                         'identity-config: macos: its platform is not the variant linux-arm64')
        config['profiles']['macos']['variant'] = 'solaris'
        self.assertEqual(self.outcome(lambda: e.identity_context(config, sha)),
                         'identity-config: macos names no variant of the manifest')

    def test_this_runner_under_the_policy(self):
        variant = {'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64', 'os_release': str(Path(__file__))}
        profile = {'platform': {'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64', 'ImageOS': 'ubuntu24'},
                   'compare': 'release-runner', 'tools': {'python': [sys.executable, '--version']}}
        env = {'ImageOS': 'ubuntu24', 'ImageVersion': '20261020.1', 'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64'}
        with patch.dict(os.environ, env):
            found = e.runtime(profile, variant)
        self.assertEqual(found['runner']['os_release'], hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        with patch.dict(os.environ, dict(env, ImageVersion='latest')):
            self.assertEqual(self.outcome(lambda: e.runtime(profile, variant)),
                             "identity-unexpected: ImageVersion 'latest' is not a reported image version")
        with patch.dict(os.environ, dict(env, ImageOS='ubuntu26')):
            self.assertTrue(self.outcome(lambda: e.runtime(profile, variant)).startswith('runner-platform: '))
        with patch.dict(os.environ, env):
            missing = dict(variant, os_release=str(Path(__file__).with_name('no-such-os-release')))
            self.assertTrue(self.outcome(lambda: e.runtime(profile, missing)).startswith('identity-missing: '))
            found = e.runtime(profile, dict(variant, os_release=None))
        self.assertNotIn('os_release', found['runner'])


class IdentityCLI(unittest.TestCase):
    """capture and verify under the policy, as the workflows run them, over a fixture repository
    whose evidence is what capture wrote."""

    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='release-evidence-cli-')
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        root = self.scratch / 'repo'
        config = {
            'schema': 2, 'repository': REPO, 'branch': 'main', 'max_age_hours': 48, 'inputs': [],
            'identity': {'manifest': '.github/runner-identity.json', 'sha256': MANIFEST_SHA},
            'profiles': {'kit': {'platform': {'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64', 'ImageOS': 'ubuntu24'},
                                 'variant': 'linux-x64', 'compare': 'release-runner',
                                 'tools': {'python': [sys.executable, '--version']}}},
            'workflows': {'ci': {'path': '.github/workflows/ci.yml', 'name': 'CI', 'events': ['push'],
                                 'jobs': {'test': {'name': 'tests', 'job_id': 'test',
                                                   'labels': ['ubuntu-latest'], 'profile': 'kit',
                                                   'checks': ['unit']}}}}}
        self.release = 'name: Release\non: push\njobs:\n  verify:\n    steps:\n      - uses: %s\n' % CHECKOUT
        files = {'.github/ci-evidence.json': json.dumps(config, indent=2) + '\n',
                 '.github/runner-identity.json': MANIFEST_BYTES,
                 '.github/workflows/ci.yml': 'name: CI\non: push\njobs:\n  test:\n    steps:\n'
                                             '      - uses: %s\n      - uses: %s\n' % (CHECKOUT, UPLOAD),
                 '.github/workflows/release.yml': self.release,
                 'dev.json': '{"version": 1, "checks": [{"name": "unit"}]}\n',
                 'release_evidence.py': HELPER.read_bytes()}
        self.root = root
        root.mkdir()
        self.sha = git_fixture(root, files)
        self.os_release = hashlib.sha256(Path('/etc/os-release').read_bytes()).hexdigest()
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GITHUB_SHA=self.sha,
                        GITHUB_REPOSITORY=REPO, GITHUB_REPOSITORY_ID=str(REPO_ID), ImageOS='ubuntu24',
                        ImageVersion='20261020.1', RUNNER_OS='Linux', RUNNER_ARCH='X64',
                        GITHUB_REF='refs/heads/main', GITHUB_EVENT_NAME='push', GITHUB_JOB='test',
                        GITHUB_RUN_ID='100', GITHUB_RUN_ATTEMPT='1',
                        GITHUB_WORKFLOW_REF=REPO + '/.github/workflows/ci.yml@refs/heads/main',
                        GITHUB_WORKFLOW_SHA=self.sha)
        self.env.pop('GITHUB_OUTPUT', None)

    def capture(self, log_text='PASS     unit 1s\n', **env):
        log = self.scratch / 'checks.log'
        log.write_text(log_text)
        output = self.scratch / 'evidence.json'
        result = subprocess.run([sys.executable, str(self.root / 'release_evidence.py'), 'capture', '--workflow',
                                 'ci', '--job', 'test', '--check-log', str(log), '--output', str(output)],
                                cwd=self.root, env=dict(self.env, **env), text=True, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        return result, output

    def test_capture_records_the_reported_identity(self):
        result, output = self.capture()
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = json.loads(output.read_text())
        self.assertEqual(captured['identity'], dict(IDENTITY_RECORD, variant='linux-x64',
                                                    actions=sorted([CHECKOUT, UPLOAD])))
        self.assertEqual(captured['runtime']['runner'], {
            'ImageOS': 'ubuntu24', 'ImageVersion': '20261020.1', 'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64',
            'os_release': self.os_release})
        self.assertIn('.github/runner-identity.json', captured['inputs'])
        # What capture wrote is what the release takes, on a runner that reports the same identity.
        result, record = self.verify(captured)
        self.assertEqual((result.returncode, record['decision']), (0, 'reuse'), result.stderr)
        self.assertEqual(record['identity']['release_workflow'],
                         {'path': '.github/workflows/release.yml', 'actions': [CHECKOUT]})
        self.assertEqual(record['identity']['groups']['linux-x64/kit']['runtime'], captured['runtime'])
        # The hosted image rolled before the release: the identity changed, and the release refuses.
        result, record = self.verify(captured, ImageVersion='20261026.180.1')
        self.assertEqual((result.returncode, record['decision'], (record['refusal'] or {}).get('code')),
                         (1, 'refuse', 'runtime-identity'))
        # The release workflow names an action by tag: refused.
        (self.root / '.github/workflows/release.yml').write_text(self.release + '      - uses: actions/cache@v4\n')
        subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit',
                        '-qam', 'tag-pinned action'], cwd=self.root, env=self.env, check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.root, text=True).strip()
        result, record = self.verify(dict(captured, source=sha), GITHUB_SHA=sha)
        refusal = record['refusal'] or {}
        self.assertEqual((record['decision'], refusal.get('code')), ('refuse', 'identity-unexpected'))
        self.assertIn('actions/cache@v4', refusal.get('detail'))

    def verify(self, payload, **env):
        bin_dir = self.scratch / 'bin'
        bin_dir.mkdir(exist_ok=True)
        fake_gh(bin_dir)
        api = self.scratch / 'api.json'
        sha = env.get('GITHUB_SHA', self.sha)
        write_api(api, cli_world(sha, payload))
        output = self.scratch / 'release-evidence.json'
        result = subprocess.run([sys.executable, str(self.root / 'release_evidence.py'), 'verify', '--output',
                                 str(output)], cwd=self.root, text=True, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
                                env=dict(self.env, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'],
                                         FIXTURE_API=str(api), RELEASE_TAG='v1.2.3',
                                         GITHUB_REF='refs/tags/v1.2.3',
                                         GITHUB_WORKFLOW_REF=REPO + '/.github/workflows/release.yml@refs/tags/v1.2.3',
                                         GITHUB_WORKFLOW_SHA=sha, **env))
        return result, json.loads(output.read_text())

    def test_capture_refuses_an_unexpected_identity(self):
        for env, code in (({'ImageVersion': 'latest'}, 'identity-unexpected'),
                          ({'ImageOS': 'ubuntu26'}, 'runner-platform'),
                          ({'ImageVersion': ''}, 'runner-identity')):
            with self.subTest(env=env):
                result, _ = self.capture(**env)
                self.assertEqual(result.returncode, 1)
                self.assertIn('capture refused: ' + code, result.stderr)


# --- pull-request-to-branch reuse (devkit #60): tree equality alone never qualifies a result ------

BASE = 'e' * 40      # the branch commit the pull request was tested on, and the commit's first parent
HEAD = 'b' * 40      # the pull request's head
MERGE = 'd' * 40     # the merge commit its run checked out
TREE = '7' * 40      # the commit's tree, and the merge commit's
GOFLAGS = hashlib.sha256(b'-count=1').hexdigest()
PULL = {'number': 7, 'state': 'closed', 'merged_at': '2026-10-25T09:55:00Z', 'merge_commit_sha': SHA,
        'head': {'sha': HEAD, 'ref': 'feature', 'repo': {'id': REPO_ID}},
        'base': {'ref': 'main', 'repo': {'id': REPO_ID}}}
PR_RUNS = 'actions/workflows/9/runs?head_sha=' + HEAD + '&per_page=100&page=1'
PR_JOBS = 'actions/runs/50/attempts/1/jobs?per_page=100&page=1'
PR_ARTIFACTS = 'actions/runs/50/artifacts?per_page=100&page=1'
PR_ASSOCIATION = {'number': 7, 'head': {'ref': 'feature', 'sha': HEAD, 'repo': {'id': REPO_ID}},
                  'base': {'ref': 'main', 'sha': BASE, 'repo': {'id': REPO_ID}}}
HEAD_PULLS = 'pulls?head=example:feature&state=all&per_page=100&page=1'
TIMELINE = 'issues/7/timeline?per_page=100&page=1'
PR_RUN = dict(RUN, id=50, event='pull_request', head_branch='feature', head_sha=HEAD,
              pull_requests=[PR_ASSOCIATION], created_at='2026-10-25T09:00:00Z',
              run_started_at='2026-10-25T09:00:00Z', updated_at='2026-10-25T09:05:00Z')
PR_JOB = dict(JOB_LINUX, id=151, run_id=50, head_sha=HEAD, head_branch='feature',
              started_at='2026-10-25T09:00:05Z', completed_at='2026-10-25T09:04:00Z')
PR_ORIGIN = dict(ORIGIN, id=50, head_sha=HEAD, head_branch='feature')
PR_ARTIFACT = dict(ARTIFACT_LINUX, id=351, created_at='2026-10-25T09:03:59Z', workflow_run=PR_ORIGIN)
PR_EVIDENCE = dict(EVIDENCE_LINUX, source=MERGE, run_id=50, event='pull_request', ref='refs/pull/7/merge',
                   coverage={'unit': 'PASS'},
                   pull_request={'number': 7, 'base': BASE, 'head': HEAD, 'tree': TREE},
                   environment={'GOFLAGS': GOFLAGS})


class ReuseFixtures(Gate):
    """A branch run whose Linux job took `unit` from the merged pull request's run."""

    def setUp(self):
        super().setUp()
        self.config['workflows']['ci']['pull_request_reuse'] = {'checks': ['unit'], 'environment': ['GOFLAGS']}
        e.check_config(self.config)
        data = json.loads(json.dumps({
            'git/commits/' + SHA: {'sha': SHA, 'tree': {'sha': TREE}, 'parents': [{'sha': BASE}]},
            'git/commits/' + MERGE: {'sha': MERGE, 'tree': {'sha': TREE}, 'parents': [{'sha': BASE}, {'sha': HEAD}]},
            'commits/%s/pulls?per_page=100' % SHA: [PULL],
            HEAD_PULLS: [PULL],
            TIMELINE: [{'event': 'committed'}, {'event': 'reviewed'}, {'event': 'merged'}],
            PR_RUNS: {'total_count': 1, 'workflow_runs': [PR_RUN]},
            'actions/runs/50': PR_RUN,
            PR_JOBS: {'total_count': 1, 'jobs': [PR_JOB]},
            PR_ARTIFACTS: {'total_count': 1, 'artifacts': [PR_ARTIFACT]}}))
        self.data.update(data)
        pack(self.data, self.data[PR_ARTIFACTS]['artifacts'][0], copy.deepcopy(PR_EVIDENCE))
        artifact = self.data[PR_ARTIFACTS]['artifacts'][0]
        self.reused = {'pull_request': 7, 'head': HEAD, 'merge': MERGE, 'base': BASE, 'tree': TREE, 'run_id': 50,
                       'attempt': 1, 'job_id': 151,
                       'artifact': {'id': 351, 'name': 'ci-evidence-ci-test-linux-1', 'digest': artifact['digest']},
                       'checks': ['unit']}
        self.evidence(0, lambda payload: payload.update(
            coverage={'unit': 'REUSED', 'audit': 'SKIP'}, environment={'GOFLAGS': GOFLAGS},
            reused=copy.deepcopy(self.reused)))
        self.evidence(1, lambda payload: payload.update(environment={'GOFLAGS': GOFLAGS}, reused=None))

    def pr_evidence(self, change):
        artifact = self.data[PR_ARTIFACTS]['artifacts'][0]
        payload = copy.deepcopy(PR_EVIDENCE)
        change(payload)
        pack(self.data, artifact, payload)
        # The branch job recorded the artifact it read: the same bytes.
        self.evidence(0, lambda main: main['reused']['artifact'].update(digest=artifact['digest']))

    def pr_runs(self, *runs):
        self.data[PR_RUNS] = {'total_count': len(runs), 'workflow_runs': list(runs)}

    def foreign_run(self):
        """Review probe P1: the merged pull request's own run 50 failed; run 60, newer and green, at
        the same head and head branch, belongs to pull request 8 into another base, whose workflow
        file wrote pull request 7's record. The branch job's record names run 60."""
        own = dict(PR_RUN, conclusion='failure')
        foreign = dict(PR_RUN, id=60, created_at='2026-10-25T09:20:00Z', run_started_at='2026-10-25T09:20:00Z',
                       updated_at='2026-10-25T09:25:00Z',
                       pull_requests=[dict(PR_ASSOCIATION, number=8, base={'ref': 'evil', 'sha': BASE,
                                                                           'repo': {'id': REPO_ID}})])
        self.pr_runs(own, foreign)
        self.data['actions/runs/50'] = own
        self.data['actions/runs/60'] = foreign
        self.data[HEAD_PULLS] = [PULL, dict(PULL, number=8, state='open', merged_at=None, merge_commit_sha=None,
                                           base=dict(PULL['base'], ref='evil'))]
        self.data['actions/runs/60/attempts/1/jobs?per_page=100&page=1'] = {
            'total_count': 1, 'jobs': [dict(PR_JOB, id=161, run_id=60, started_at='2026-10-25T09:20:05Z',
                                            completed_at='2026-10-25T09:24:00Z')]}
        artifact = dict(PR_ARTIFACT, id=361, created_at='2026-10-25T09:23:59Z', workflow_run=dict(PR_ORIGIN, id=60))
        self.data['actions/runs/60/artifacts?per_page=100&page=1'] = {'total_count': 1, 'artifacts': [artifact]}
        pack(self.data, artifact, dict(PR_EVIDENCE, run_id=60))
        self.evidence(0, lambda payload: payload['reused'].update(
            run_id=60, job_id=161, artifact={'id': 361, 'name': 'ci-evidence-ci-test-linux-1',
                                             'digest': artifact['digest']}))


class PullRequestReuse(ReuseFixtures):
    """The release: the branch job's reuse is admitted again, or refused."""

    def test_a_reused_check_is_admitted_again_and_recorded(self):
        self.assertEqual(self.decide(), 'reuse')
        jobs = self.record['workflows']['ci']['jobs']
        self.assertEqual(jobs['test-linux']['coverage'], {'unit': 'REUSED', 'audit': 'SKIP'})
        self.assertEqual(jobs['test-linux']['reused'], dict(self.reused, run_started_at='2026-10-25T09:00:00Z'))
        self.assertIsNone(jobs['test-macos']['reused'])
        # The pull request's run is read again at the release, whole, and its selection twice.
        self.assertEqual(self.api.calls.count(PR_RUNS), 2)
        self.assertIn('actions/artifacts/351/zip', self.api.calls)

    def test_tree_equality_alone_never_qualifies(self):
        # The same tree, tested on another base: the base relationship differs, even where the branch
        # job's record names that base.
        self.pr_evidence(lambda payload: payload['pull_request'].update(base='f' * 40))
        self.data['git/commits/' + MERGE]['parents'][0]['sha'] = 'f' * 40
        self.assertEqual(self.decide(), 'reuse-base')
        self.evidence(0, lambda payload: payload['reused'].update(base='f' * 40))
        self.assertEqual(self.decide(), 'reuse-base')
        # The same tree claimed by a merge commit that is not this pull request's.
        self.setUp()
        self.data['git/commits/' + MERGE]['parents'][1]['sha'] = OTHER
        self.assertEqual(self.decide(), 'reuse-evidence')
        self.setUp()
        self.data['git/commits/' + MERGE]['tree']['sha'] = '8' * 40
        self.assertEqual(self.decide(), 'reuse-evidence')
        # Another tree.
        self.setUp()
        self.pr_evidence(lambda payload: payload['pull_request'].update(tree='8' * 40))
        self.data['git/commits/' + MERGE]['tree']['sha'] = '8' * 40
        self.evidence(0, lambda payload: payload['reused'].update(tree='8' * 40))
        self.assertEqual(self.decide(), 'reuse-tree')

    def test_a_run_of_another_pull_request_on_the_head_branch_is_refused(self):
        # Review probe P1: refused, though the record the foreign run wrote is pull request 7's.
        self.foreign_run()
        self.assertEqual(self.decide(), 'reuse-pull-request')
        self.assertIn('other pull requests [8]', self.record['refusal']['detail'])
        # The listing alone shows no other pull request: the run's own association still refuses.
        self.data[HEAD_PULLS] = [PULL]
        self.assertEqual(self.decide(), 'reuse-pull-request')
        self.assertIn('run 60 is associated with', self.record['refusal']['detail'])
        # Control: the merged pull request's own failed run alone is refused as a failure.
        self.setUp()
        self.pr_runs(dict(PR_RUN, conclusion='failure'))
        self.assertEqual(self.decide(), 'reuse-result')

    def test_the_run_is_bound_to_the_merged_pull_request_and_its_base(self):
        for association in ([], [dict(PR_ASSOCIATION, number=8)],
                            [dict(PR_ASSOCIATION, base=dict(PR_ASSOCIATION['base'], ref='evil'))],
                            [dict(PR_ASSOCIATION, base=dict(PR_ASSOCIATION['base'], repo={'id': 99}))],
                            [PR_ASSOCIATION, dict(PR_ASSOCIATION, number=8)], [{'number': 7}]):
            with self.subTest(association=association):
                self.setUp()
                self.pr_runs(dict(PR_RUN, pull_requests=association))
                self.data['actions/runs/50'] = dict(PR_RUN, pull_requests=association)
                self.assertEqual(self.decide(), 'reuse-pull-request')

    def test_another_pull_request_of_the_head_branch_or_a_changed_base_refuses(self):
        for change in (lambda: self.data[HEAD_PULLS].append(dict(PULL, number=3, state='closed', merged_at=None)),
                       lambda: self.data[HEAD_PULLS].clear(),
                       lambda: self.data[TIMELINE].append({'event': 'base_ref_changed'}),
                       lambda: self.data.pop(HEAD_PULLS),
                       lambda: self.data.pop(TIMELINE),
                       lambda: self.data.update({TIMELINE: {'not': 'a list'}}),
                       lambda: self.data.update({TIMELINE: [{'event': 'committed'}] * 100})):
            with self.subTest():
                self.setUp()
                change()
                self.assertEqual(self.decide(), 'reuse-pull-request')

    def test_the_pull_request_job_runner_and_the_merge_commit_parent_order(self):
        for job, code in ((dict(PR_JOB, labels=['self-hosted']), 'reuse-job'),
                          (dict(PR_JOB, runner_group_id=3, runner_group_name='private'), 'reuse-job')):
            with self.subTest(code=code, job=job['labels']):
                self.setUp()
                self.data[PR_JOBS] = {'total_count': 1, 'jobs': [job]}
                self.assertEqual(self.decide(), code)
        self.setUp()
        self.data['git/commits/' + MERGE]['parents'] = [{'sha': HEAD}, {'sha': BASE}]
        self.assertEqual(self.decide(), 'reuse-evidence')

    def test_the_trusted_pull_request_relationship(self):
        for change in (lambda: self.data['commits/%s/pulls?per_page=100' % SHA].clear(),
                       lambda: self.data['commits/%s/pulls?per_page=100' % SHA][0].update(merge_commit_sha=OTHER),
                       lambda: self.data['commits/%s/pulls?per_page=100' % SHA][0].update(merged_at=None),
                       lambda: self.data['commits/%s/pulls?per_page=100' % SHA].append(dict(PULL, number=8)),
                       lambda: self.data['commits/%s/pulls?per_page=100' % SHA][0]['base'].update(ref='release'),
                       lambda: self.data['commits/%s/pulls?per_page=100' % SHA][0]['head'].update(repo={'id': 99}),
                       lambda: self.data['commits/%s/pulls?per_page=100' % SHA][0]['base'].update(repo={'id': 99}),
                       lambda: self.data['commits/%s/pulls?per_page=100' % SHA][0]['head'].update(repo=None)):
            with self.subTest():
                self.setUp()
                change()
                self.assertEqual(self.decide(), 'reuse-pull-request')

    def test_the_pull_request_event_and_ref(self):
        for change, code in ((lambda payload: payload.update(ref='refs/pull/8/merge'), 'reuse-evidence'),
                             (lambda payload: payload.update(event='push'), 'reuse-evidence'),
                             (lambda payload: payload['pull_request'].update(number=8), 'reuse-evidence'),
                             (lambda payload: payload.update(job='test-macos'), 'reuse-evidence'),
                             (lambda payload: payload.update(extra='member'), 'reuse-evidence')):
            with self.subTest(code=code):
                self.setUp()
                self.pr_evidence(change)
                self.assertEqual(self.decide(), code)
        for change in (dict(event='push', head_branch='main'), dict(event='pull_request_target'),
                       dict(head_branch='other'), dict(head_repository={'id': 99, 'full_name': 'fork/project'})):
            with self.subTest(change=change):
                self.setUp()
                self.pr_runs(dict(PR_RUN, **change))
                self.assertEqual(self.decide(), 'reuse-run-missing')

    def test_only_a_first_attempt_push_reuses(self):
        self.both_runs(event='workflow_dispatch')
        self.evidence(0, lambda payload: payload.update(event='workflow_dispatch'))
        self.evidence(1, lambda payload: payload.update(event='workflow_dispatch'))
        self.assertEqual(self.decide(), 'reuse-event')

    def test_changed_inputs_tools_images_or_environment(self):
        for change, code in (
                (lambda payload: payload['inputs'].update({'dev.json': '9' * 40}), 'reuse-inputs'),
                (lambda payload: payload['runtime']['runner'].update(ImageVersion='20261026.180.1'), 'reuse-runtime'),
                (lambda payload: payload['runtime']['tools'].update(go='go version go1.26.4 linux/amd64'),
                 'reuse-runtime'),
                (lambda payload: payload['runtime']['runner'].update(os_release='d' * 64), 'reuse-runtime'),
                (lambda payload: payload.update(environment={'GOFLAGS': None}), 'reuse-environment'),
                (lambda payload: payload.update(environment={}), 'reuse-evidence')):
            with self.subTest(code=code):
                self.setUp()
                self.pr_evidence(change)
                self.assertEqual(self.decide(), code)

    def test_scope_limited_evidence_covers_only_what_it_passed(self):
        for change, code in (
                # Not run by the pull request's scoped selection: it covers nothing.
                (lambda payload: payload.update(coverage={}), 'reuse-coverage'),
                (lambda payload: payload.update(coverage={'unit': 'FAIL'}), 'reuse-coverage'),
                (lambda payload: payload.update(coverage={'unit': 'NOT RUN'}), 'reuse-coverage'),
                (lambda payload: payload.update(coverage={'unit': 'SKIP'}), 'reuse-coverage'),
                (lambda payload: payload.update(coverage={'unit': 'PASS', 'lint': 'PASS'}), 'reuse-coverage')):
            with self.subTest(code=code):
                self.setUp()
                self.pr_evidence(change)
                self.assertEqual(self.decide(), code)
        # A check the configuration does not let a pull request cover.
        self.setUp()
        self.evidence(0, lambda payload: (payload['reused'].update(checks=['unit', 'audit']),
                                          payload.update(coverage={'unit': 'REUSED', 'audit': 'REUSED'})))
        self.assertEqual(self.decide(), 'reuse-coverage')
        self.assertIn('the reused record or its checks', self.record['refusal']['detail'])
        # A permitted skip in the pull request run covers nothing, even where the check may be reused.
        self.setUp()
        self.config['workflows']['ci']['pull_request_reuse']['checks'] = ['unit', 'audit']
        self.pr_evidence(lambda payload: payload.update(coverage={'unit': 'PASS', 'audit': 'SKIP'}))
        self.evidence(0, lambda payload: (payload['reused'].update(checks=['unit', 'audit']),
                                          payload.update(coverage={'unit': 'REUSED', 'audit': 'REUSED'})))
        self.assertEqual(self.decide(), 'reuse-coverage')
        self.assertIn("['audit'] were not passed", self.record['refusal']['detail'])
        # REUSED for a check the job did not record as reused, or a reused check missing.
        self.setUp()
        self.evidence(1, lambda payload: payload.update(coverage={'unit': 'REUSED'}))
        self.assertEqual(self.decide(), 'check-result')
        self.setUp()
        self.evidence(0, lambda payload: payload.update(coverage={'audit': 'SKIP'}))
        self.assertEqual(self.decide(), 'check-coverage')

    def test_unexpected_skips_and_failed_cancelled_or_incomplete_attempts(self):
        for job in (dict(PR_JOB, conclusion='skipped'), dict(PR_JOB, conclusion='failure'),
                    dict(PR_JOB, status='in_progress', conclusion=None)):
            with self.subTest(job=job['conclusion']):
                self.setUp()
                self.data[PR_JOBS] = {'total_count': 1, 'jobs': [job]}
                self.assertEqual(self.decide(), 'reuse-result')
        self.setUp()
        self.data[PR_JOBS] = {'total_count': 0, 'jobs': []}
        self.assertEqual(self.decide(), 'reuse-job')
        for conclusion in ('failure', 'cancelled'):
            with self.subTest(conclusion=conclusion):
                self.setUp()
                self.pr_runs(dict(PR_RUN, conclusion=conclusion))
                self.data['actions/runs/50'] = dict(PR_RUN, conclusion=conclusion)
                self.assertEqual(self.decide(), 'reuse-result')
        self.setUp()
        self.pr_runs(dict(PR_RUN, status='in_progress', conclusion=None))
        self.assertEqual(self.decide(), 'reuse-unfinished')

    def test_a_newer_attempt_is_never_searched_past(self):
        # An older green run beside a newer failed one: the newer is selected, and refuses.
        older = dict(PR_RUN, id=49, created_at='2026-10-25T08:00:00Z', run_started_at='2026-10-25T08:00:00Z')
        newer = dict(PR_RUN, id=52, conclusion='failure', created_at='2026-10-25T09:30:00Z',
                     run_started_at='2026-10-25T09:30:00Z')
        self.pr_runs(older, PR_RUN, newer)
        self.assertEqual(self.decide(), 'reuse-result')
        # A newer successful attempt that is not the one the branch job reused: incompatible.
        self.setUp()
        rerun = dict(PR_RUN, run_attempt=2, run_started_at='2026-10-25T09:40:00Z')
        self.pr_runs(rerun)
        self.data['actions/runs/50'] = rerun
        self.data['actions/runs/50/attempts/2/jobs?per_page=100&page=1'] = {
            'total_count': 1, 'jobs': [dict(PR_JOB, run_attempt=2)]}
        artifact = dict(PR_ARTIFACT, id=352, name='ci-evidence-ci-test-linux-2')
        self.data[PR_ARTIFACTS] = {'total_count': 2, 'artifacts': [self.data[PR_ARTIFACTS]['artifacts'][0], artifact]}
        pack(self.data, self.data[PR_ARTIFACTS]['artifacts'][1], dict(PR_EVIDENCE, attempt=2))
        self.assertEqual(self.decide(), 'reuse-changed')
        # The attempt moves while the release reads it.
        self.setUp()
        moved = iter([PR_RUN, dict(PR_RUN, run_attempt=2)])
        self.data['actions/runs/50'] = lambda: next(moved)
        self.assertEqual(self.decide(), 'reuse-race')

    def test_stale_or_inaccessible_evidence(self):
        self.pr_runs(dict(PR_RUN, run_started_at='2026-10-23T11:00:00Z'))
        self.data['actions/runs/50'] = dict(PR_RUN, run_started_at='2026-10-23T11:00:00Z')
        self.assertEqual(self.decide(), 'reuse-age')
        for change in (lambda: self.data[PR_ARTIFACTS]['artifacts'][0].update(expired=True),
                       lambda: self.data.pop('actions/artifacts/351/zip'),
                       lambda: self.data.pop('commits/%s/pulls?per_page=100' % SHA),
                       lambda: self.data.pop('git/commits/' + MERGE),
                       lambda: self.data[PR_RUNS].update(total_count=2)):
            with self.subTest():
                self.setUp()
                change()
                self.assertEqual(self.decide(), 'reuse-unavailable')
        self.setUp()
        self.data[PR_ARTIFACTS] = {'total_count': 0, 'artifacts': []}
        self.assertEqual(self.decide(), 'reuse-artifact')

    def test_a_reuse_refusal_wins_over_a_drift(self):
        self.config['revalidation'] = {'allowed': True}
        self.here['runner']['ImageVersion'] = '20261026.180.1'
        self.data.pop('actions/artifacts/351/zip')
        self.assertEqual(self.decide(), 'reuse-unavailable')

    def test_branch_reuse_records_are_held_to_their_shape(self):
        for change, code in (
                (lambda payload: payload.pop('reused'), 'evidence-identity'),
                (lambda payload: payload.pop('environment'), 'evidence-identity'),
                (lambda payload: payload.update(environment={'GOFLAGS': 'x'}), 'evidence-identity'),
                (lambda payload: payload['reused'].pop('merge'), 'reuse-coverage'),
                (lambda payload: payload['reused'].update(checks=[]), 'reuse-coverage'),
                (lambda payload: payload['reused'].update(run_id=49), 'reuse-changed'),
                (lambda payload: payload['reused']['artifact'].update(digest='sha256:' + '0' * 64), 'reuse-changed')):
            with self.subTest(code=code):
                self.setUp()
                self.evidence(0, change)
                self.assertEqual(self.decide(), code)

    def test_without_the_member_nothing_of_a_pull_request_is_read_or_taken(self):
        self.config['workflows']['ci'].pop('pull_request_reuse')
        self.assertEqual(self.decide(), 'check-result')
        self.evidence(0, lambda payload: payload.update(coverage={'unit': 'PASS', 'audit': 'SKIP'}))
        self.assertEqual(self.decide(), 'evidence-identity')
        self.data = world()
        self.assertEqual(self.decide(), 'reuse')
        self.assertFalse([call for call in self.api.calls if call.startswith(('commits/', 'git/commits/'))])


class ReusePlan(ReuseFixtures):
    """The branch job's reuse step, before its checks, over the same fixtures."""

    ENV = {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main', 'GITHUB_JOB': 'test',
           'GITHUB_RUN_ID': '100', 'GITHUB_RUN_ATTEMPT': '1',
           'GITHUB_WORKFLOW_REF': REPO + '/.github/workflows/ci.yml@refs/heads/main', 'GITHUB_WORKFLOW_SHA': SHA,
           'GOFLAGS': '-count=1'}

    def plan(self, job='test-linux', **env):
        self.api = FakeAPI(self.data)
        with patch.dict(os.environ, dict(self.ENV, **env)):
            self.record = e.plan(self.api, self.config, copy.deepcopy(SOURCE), 'ci', job, NOW)
        refusal = self.record['refusal']
        return self.record['decision'] if refusal is None else refusal['code']

    def test_a_plan_reuses_what_the_pull_request_run_passed(self):
        self.assertEqual(self.plan(), 'reuse')
        self.assertEqual((self.record['covered'], self.record['reused']), (['unit'], self.reused))
        self.assertEqual(self.record['attempt'], 1)

    def test_a_plan_never_takes_another_pull_requests_run(self):
        # Review probe P1 at the plan: fresh, and the job runs its whole list.
        self.foreign_run()
        self.assertEqual(self.plan(), 'reuse-pull-request')
        self.data[HEAD_PULLS] = [PULL]
        self.assertEqual(self.plan(), 'reuse-pull-request')
        self.assertEqual((self.record['decision'], self.record['covered']), ('fresh', []))

    def test_a_plan_never_reuses_on_tree_equality_alone(self):
        self.pr_evidence(lambda payload: payload['pull_request'].update(base='f' * 40))
        self.data['git/commits/' + MERGE]['parents'][0]['sha'] = 'f' * 40
        self.assertEqual(self.plan(), 'reuse-base')
        self.setUp()
        self.pr_evidence(lambda payload: payload['pull_request'].update(tree='8' * 40))
        self.data['git/commits/' + MERGE]['tree']['sha'] = '8' * 40
        self.assertEqual(self.plan(), 'reuse-tree')

    def test_a_plan_is_fresh_on_the_fresh_route_or_any_refusal(self):
        self.assertEqual(self.plan(GITHUB_EVENT_NAME='workflow_dispatch'), 'reuse-event')
        self.assertEqual(self.plan(GITHUB_RUN_ATTEMPT='2'), 'reuse-event')
        self.assertEqual(self.plan(GOFLAGS='-count=2'), 'reuse-environment')
        self.assertEqual(self.plan(job='test-macos'), 'reuse-job')
        self.here['runner']['ImageVersion'] = '20261026.180.1'
        self.assertEqual(self.plan(), 'reuse-runtime')
        self.setUp()
        self.pr_evidence(lambda payload: payload.update(coverage={'audit': 'SKIP'}))
        self.assertEqual(self.plan(), 'reuse-coverage')
        self.setUp()
        self.config['workflows']['ci'].pop('pull_request_reuse')
        self.assertEqual(self.plan(), 'reuse-off')
        for code in ('reuse-event', 'reuse-off'):
            self.assertEqual((self.record['decision'], self.record['covered'], self.record['reused']),
                             ('fresh', [], None))


class ReuseUnderIdentity(ReuseFixtures):
    """Reuse where the repository also holds its evidence to the runner identity policy: the pull
    request job's identity record must be the commit's, beside its runtime."""

    def setUp(self):
        super().setUp()
        reuse = self.config['workflows']['ci']['pull_request_reuse']
        self.config = identity_config(self.config)
        self.config['workflows']['ci']['pull_request_reuse'] = reuse
        variants = e.parse_identity_manifest(MANIFEST_BYTES)['variants']
        for name, target in (('identity_context', lambda config, sha: {
                                 'record': dict(IDENTITY_RECORD), 'variants': copy.deepcopy(variants),
                                 'actions': {'ci': [CHECKOUT, UPLOAD]}}),
                             ('release_workflow_actions', lambda source: {
                                 'path': '.github/workflows/release.yml', 'actions': [CHECKOUT]})):
            patcher = patch.object(e, name, side_effect=target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.linux = dict(IDENTITY_RECORD, variant='linux-x64', actions=[CHECKOUT, UPLOAD])
        self.pr_evidence(lambda payload: None)
        self.evidence(0, lambda payload: payload.update(identity=copy.deepcopy(self.linux)))
        self.evidence(1, lambda payload: (payload.update(
            identity=dict(IDENTITY_RECORD, variant='macos-arm64', actions=[CHECKOUT, UPLOAD])),
            payload['runtime']['runner'].update(os_release='e' * 64)))

    def pr_evidence(self, change):
        super().pr_evidence(lambda payload: (payload.update(identity=copy.deepcopy(self.linux)), change(payload)))

    def test_the_pull_request_identity_is_the_commits(self):
        self.assertEqual(self.decide(), 'reuse')
        for change in (lambda payload: payload.pop('identity'),
                       lambda payload: payload['identity'].update(actions=[CHECKOUT]),
                       lambda payload: payload['identity'].update(revision='2')):
            with self.subTest():
                self.setUp()
                self.pr_evidence(change)
                self.assertEqual(self.decide(), 'reuse-runtime')


class ReuseCLI(unittest.TestCase):
    """capture on the pull request, reuse and capture on the branch, verify at the release: the
    public command end to end over one fixture repository (a squash merge of a pull request) and a
    stand-in gh. What each step wrote is what the next one takes."""

    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory(prefix='release-evidence-reuse-')
        cls.addClassCleanup(scratch.cleanup)
        cls.scratch = Path(scratch.name)
        cls.root = cls.scratch / 'repo'
        cls.root.mkdir()
        config = {
            'schema': 2, 'repository': REPO, 'branch': 'main', 'max_age_hours': 48, 'inputs': [],
            'profiles': {'kit': {'platform': {'RUNNER_OS': 'Linux', 'RUNNER_ARCH': 'X64'},
                                 'compare': 'release-runner', 'tools': {'python': [sys.executable, '--version']}}},
            'workflows': {'ci': {'path': '.github/workflows/ci.yml', 'name': 'CI',
                                 'events': ['push', 'workflow_dispatch'],
                                 'pull_request_reuse': {'checks': ['unit'], 'environment': ['GOFLAGS']},
                                 'jobs': {'test': {'name': 'tests', 'job_id': 'test', 'labels': ['ubuntu-latest'],
                                                   'profile': 'kit', 'checks': ['unit', 'lint']}}}}}
        cls.base = git_fixture(cls.root, {
            '.github/ci-evidence.json': json.dumps(config, indent=2) + '\n',
            '.github/workflows/ci.yml': 'name: CI\non: [push, pull_request]\njobs:\n  test: {}\n',
            'dev.json': '{"version": 1, "checks": [{"name": "unit"}, {"name": "lint"}]}\n',
            'release_evidence.py': HELPER.read_bytes(), 'src.txt': 'one\n'})
        cls.git_env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                           GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                           GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        cls.git('checkout', '-q', '-b', 'feature')
        (cls.root / 'src.txt').write_text('two\n')
        cls.git('commit', '-qam', 'the pull request')
        cls.head = cls.git('rev-parse', 'HEAD')
        # The merge commit a pull_request run checks out: the head merged onto the base.
        cls.git('checkout', '-q', '--detach', cls.base)
        cls.git('merge', '-q', '--no-ff', '-m', 'merge', cls.head)
        cls.merge = cls.git('rev-parse', 'HEAD')
        # The squash merge that lands on main: one parent, the base, and the same tree.
        cls.git('checkout', '-q', 'main')
        cls.git('merge', '-q', '--squash', cls.head)
        cls.git('commit', '-qm', 'squash')
        cls.sha = cls.git('rev-parse', 'HEAD')
        cls.tree = cls.git('rev-parse', cls.sha + '^{tree}')
        assert cls.tree == cls.git('rev-parse', cls.merge + '^{tree}')
        cls.bin = cls.scratch / 'bin'
        cls.bin.mkdir()
        fake_gh(cls.bin)
        cls.manifest_digest = hashlib.sha256((cls.root / 'dev.json').read_bytes()).hexdigest()

    def env_line(self, goflags=GOFLAGS, manifest=None):
        """The line check.sh prints under JPDEV_BIND_ENV=GOFLAGS, as the checks step ran."""
        return 'environment: manifest=%s GOFLAGS=%s\n' % (manifest or self.manifest_digest, goflags)

    @classmethod
    def git(cls, *args):
        return subprocess.run(['git', *args], cwd=cls.root, env=cls.git_env, check=True, text=True,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL).stdout.strip()

    def run_helper(self, at, mode, extra, env, data=None):
        self.git('checkout', '-q', '--detach', at)
        api = self.scratch / 'api.json'
        write_api(api, data or {})
        outputs = self.scratch / 'outputs'
        outputs.write_text('')
        environment = dict(self.git_env, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                           FIXTURE_API=str(api), GITHUB_OUTPUT=str(outputs), GITHUB_SHA=at,
                           GITHUB_REPOSITORY=REPO, GITHUB_REPOSITORY_ID=str(REPO_ID), ImageOS='ubuntu24',
                           ImageVersion='20261020.1', RUNNER_OS='Linux', RUNNER_ARCH='X64', GITHUB_JOB='test',
                           GITHUB_RUN_ATTEMPT='1', GOFLAGS='-count=1')
        environment.update(env)
        result = subprocess.run([sys.executable, str(self.root / 'release_evidence.py'), mode, *extra],
                                cwd=self.root, env=environment, text=True, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        return result, outputs.read_text()

    def pr_env(self, **env):
        return dict({'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_REF': 'refs/pull/7/merge', 'GITHUB_BASE_REF': 'main',
                     'GITHUB_RUN_ID': '50',
                     'GITHUB_WORKFLOW_REF': REPO + '/.github/workflows/ci.yml@refs/pull/7/merge',
                     'GITHUB_WORKFLOW_SHA': self.merge}, **env)

    def push_env(self, **env):
        return dict({'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main', 'GITHUB_RUN_ID': '100',
                     'GITHUB_WORKFLOW_REF': REPO + '/.github/workflows/ci.yml@refs/heads/main',
                     'GITHUB_WORKFLOW_SHA': self.sha}, **env)

    def log(self, name, text):
        """A check log; one without an environment: line gets the checks step's usual one."""
        path = self.scratch / name
        path.write_text(text if 'environment:' in text or 'NO-ENVIRONMENT' in text else self.env_line() + text)
        return str(path)

    def capture_pr(self, text='PASS     unit 1s\n', at=None, **env):
        output = self.scratch / 'pr-evidence.json'
        result, _ = self.run_helper(at or self.merge, 'capture', ['--workflow', 'ci', '--job', 'test', '--check-log',
                                                                  self.log('pr.log', text), '--output', str(output)],
                                    self.pr_env(**env))
        return result, output

    def pr_world(self, pr_evidence):
        now = dt.datetime.now(dt.timezone.utc)

        def iso(seconds):
            return (now + dt.timedelta(seconds=seconds)).isoformat().replace('+00:00', 'Z')
        run = dict(PR_RUN, head_sha=self.head, created_at=iso(-1200), run_started_at=iso(-1200), updated_at=iso(-900))
        job = dict(PR_JOB, name='tests', head_sha=self.head, started_at=iso(-1190), completed_at=iso(-900))
        artifact = dict(PR_ARTIFACT, name='ci-evidence-ci-test-1', created_at=iso(-901),
                        workflow_run=dict(PR_ORIGIN, head_sha=self.head))
        data = {'git/commits/' + self.sha: {'sha': self.sha, 'tree': {'sha': self.tree}, 'parents': [{'sha': self.base}]},
                'git/commits/' + self.merge: {'sha': self.merge, 'tree': {'sha': self.tree},
                                              'parents': [{'sha': self.base}, {'sha': self.head}]},
                HEAD_PULLS: [dict(PULL, merge_commit_sha=self.sha, head=dict(PULL['head'], sha=self.head))],
                TIMELINE: [],
                'commits/%s/pulls?per_page=100' % self.sha: [dict(PULL, merge_commit_sha=self.sha,
                                                                  head=dict(PULL['head'], sha=self.head))],
                'actions/workflows/ci.yml': {'id': 9, 'name': 'CI', 'path': '.github/workflows/ci.yml', 'state': 'active'},
                'actions/workflows/9/runs?head_sha=%s&per_page=100&page=1' % self.head:
                    {'total_count': 1, 'workflow_runs': [run]},
                'actions/runs/50': run, PR_JOBS: {'total_count': 1, 'jobs': [job]},
                PR_ARTIFACTS: {'total_count': 1, 'artifacts': [artifact]}}
        pack(data, artifact, pr_evidence)
        return data

    def test_end_to_end(self):
        result, output = self.capture_pr()
        self.assertEqual(result.returncode, 0, result.stderr)
        pr_evidence = json.loads(output.read_text())
        self.assertEqual((pr_evidence['source'], pr_evidence['event'], pr_evidence['ref']),
                         (self.merge, 'pull_request', 'refs/pull/7/merge'))
        self.assertEqual(pr_evidence['pull_request'], {'number': 7, 'base': self.base, 'head': self.head,
                                                       'tree': self.tree})
        self.assertEqual(pr_evidence['coverage'], {'unit': 'PASS'})
        self.assertEqual(pr_evidence['environment'], {'GOFLAGS': GOFLAGS})

        world = self.pr_world(pr_evidence)
        plan_path = self.scratch / 'plan.json'
        result, outputs = self.run_helper(self.sha, 'reuse', ['--workflow', 'ci', '--job', 'test', '--output',
                                                              str(plan_path)], self.push_env(), world)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(plan_path.read_text())
        self.assertEqual((plan['decision'], plan['covered']), ('reuse', ['unit']), plan['refusal'])
        self.assertEqual(outputs, 'decision=reuse\ncovered=unit\n')
        self.assertIn('release-evidence: reuse: unit from pull request 7 run 50 attempt 1', result.stderr)

        output = self.scratch / 'evidence.json'
        result, _ = self.run_helper(self.sha, 'capture', ['--workflow', 'ci', '--job', 'test', '--check-log',
                                                          self.log('main.log', 'PASS     lint 1s\n'), '--reuse-plan',
                                                          str(plan_path), '--output', str(output)],
                                    self.push_env(), world)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(output.read_text())
        self.assertEqual(evidence['coverage'], {'unit': 'REUSED', 'lint': 'PASS'})
        self.assertEqual(evidence['reused'], plan['reused'])

        data = dict(world, **cli_world(self.sha, evidence))
        record_path = self.scratch / 'release-evidence.json'
        result, outputs = self.run_helper(self.sha, 'verify', ['--output', str(record_path)],
                                          {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/tags/v1.2.3',
                                           'RELEASE_TAG': 'v1.2.3'}, data)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(record_path.read_text())
        self.assertEqual(record['decision'], 'reuse')
        self.assertEqual(record['workflows']['ci']['jobs']['test']['reused']['run_id'], 50)

        # The release refuses once the pull request run moved on to a newer attempt that failed.
        runs = 'actions/workflows/9/runs?head_sha=%s&per_page=100&page=1' % self.head
        newer = dict(data[runs]['workflow_runs'][0], run_attempt=2, conclusion='failure',
                     run_started_at=dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z'))
        result, _ = self.run_helper(self.sha, 'verify', ['--output', str(record_path)],
                                    {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/tags/v1.2.3',
                                     'RELEASE_TAG': 'v1.2.3'}, dict(data, **{runs: {'total_count': 1,
                                                                                    'workflow_runs': [newer]}}))
        self.assertEqual((result.returncode, (json.loads(record_path.read_text())['refusal'] or {}).get('code')),
                         (1, 'reuse-result'))

    def test_the_environment_bound_is_the_checks_steps(self):
        # The capture step runs with GOFLAGS=-count=1; the checks step ran with -short. What is
        # recorded is the checks step's, from check.sh's environment: line.
        short = hashlib.sha256(b'-count=1 -short').hexdigest()
        result, output = self.capture_pr(self.env_line(goflags=short) + 'PASS     unit 1s\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(output.read_text())['environment'], {'GOFLAGS': short})
        unset = self.env_line(goflags='unset') + 'PASS     unit 1s\n'
        result, output = self.capture_pr(unset)
        self.assertEqual(json.loads(output.read_text())['environment'], {'GOFLAGS': None})
        for text in ('NO-ENVIRONMENT\nPASS     unit 1s\n',
                     self.env_line(manifest='0' * 64) + 'PASS     unit 1s\n',
                     'environment: manifest=%s\nPASS     unit 1s\n' % self.manifest_digest,
                     'environment: manifest=%s GOFLAGS=%s NODE_OPTIONS=unset\nPASS     unit 1s\n' % (
                         self.manifest_digest, GOFLAGS),
                     self.env_line(goflags='-short') + 'PASS     unit 1s\n',
                     self.env_line() + self.env_line(goflags=short) + 'PASS     unit 1s\n'):
            with self.subTest(text=text.splitlines()[0]):
                result, _ = self.capture_pr(text)
                self.assertEqual(result.returncode, 1)
                self.assertIn('capture refused: check-environment', result.stderr)
        # Two logs of one job (setup and checks) that ran with different environments.
        output = self.scratch / 'two.json'
        result, _ = self.run_helper(self.merge, 'capture', [
            '--workflow', 'ci', '--job', 'test', '--check-log', self.log('a.log', 'PASS     unit 1s\n'),
            '--check-log', self.log('b.log', self.env_line(goflags=short)), '--output', str(output)], self.pr_env())
        self.assertIn('capture refused: check-environment', result.stderr)

    def test_check_sh_prints_the_line_the_gate_reads(self):
        manifest = '{"version": 1, "checks": [{"name": "unit", "run": "true"}]}\n'
        scratch = tempfile.TemporaryDirectory(prefix='release-evidence-check-')
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name)
        sha = git_fixture(root, {'dev.json': manifest})
        env = dict(os.environ, JPDEV_ROOT=str(root), JPDEV_BIND_ENV='GOFLAGS', GOFLAGS='-count=1')
        env.pop('NODE_OPTIONS', None)
        out = subprocess.run([str(ROOT / 'templates/check.sh')], env=env, text=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60).stdout
        log = root.parent / (root.name + '.log')
        self.addCleanup(lambda: log.unlink(missing_ok=True))
        log.write_text(out)
        workflow = {'pull_request_reuse': {'checks': ['unit'], 'environment': ['GOFLAGS']}}
        def read():
            try:
                return e.log_environment(workflow, [('check', str(log))], sha)
            except e.Refusal as error:
                return error.code
        cwd = os.getcwd()
        os.chdir(root)
        try:
            self.assertEqual(read(), {'GOFLAGS': GOFLAGS})
            env['GOFLAGS'] = '-short'
            out = subprocess.run([str(ROOT / 'templates/check.sh')], env=env, text=True, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60).stdout
            log.write_text(out)
            self.assertEqual(read(), {'GOFLAGS': hashlib.sha256(b'-short').hexdigest()})
            env.pop('JPDEV_BIND_ENV')
            log.write_text(subprocess.run([str(ROOT / 'templates/check.sh')], env=env, text=True,
                                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL, timeout=60).stdout)
            self.assertEqual(outcome_of(lambda: e.log_environment(workflow, [('check', str(log))], sha)),
                             'check-environment: %s has 0 environment: lines' % log)
        finally:
            os.chdir(cwd)

    def test_the_fresh_route_plans_no_reuse(self):
        plan_path = self.scratch / 'fresh.json'
        for env in ({'GITHUB_EVENT_NAME': 'workflow_dispatch'}, {'GITHUB_RUN_ATTEMPT': '2'}):
            with self.subTest(env=env):
                result, outputs = self.run_helper(self.sha, 'reuse', ['--workflow', 'ci', '--job', 'test', '--output',
                                                                      str(plan_path)], self.push_env(**env))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(outputs, 'decision=fresh\ncovered=\n')
                self.assertEqual(json.loads(plan_path.read_text())['refusal']['code'], 'reuse-event')

    def test_pull_request_capture_refusals(self):
        for env, text, at, code in (
                ({'GITHUB_BASE_REF': 'release'}, None, None, 'capture-ref'),
                ({'GITHUB_REF': 'refs/heads/feature'}, None, None, 'capture-ref'),
                ({'GITHUB_WORKFLOW_SHA': 'f' * 40}, None, None, 'capture-workflow'),
                ({}, 'FAIL     unit 1s\n', None, 'check-result'),
                ({}, 'PASS     deploy 1s\n', None, 'check-coverage'),
                ({}, 'NOT RUN  unit\n', None, 'check-result')):
            with self.subTest(code=code, env=env):
                result, _ = self.capture_pr(text or 'PASS     unit 1s\n', at, **env)
                self.assertEqual(result.returncode, 1)
                self.assertIn('capture refused: ' + code, result.stderr)
        # A checkout of the head itself, not the merge commit: no base relationship to record.
        result, _ = self.capture_pr(at=self.head, GITHUB_WORKFLOW_SHA=self.head)
        self.assertIn('capture refused: capture-merge', result.stderr)

    def test_branch_capture_takes_only_its_own_plan(self):
        plan = {'schema': 1, 'decision': 'reuse', 'source': self.sha, 'workflow': 'ci', 'job': 'test',
                'attempt': 1, 'covered': ['unit'],
                'reused': {'pull_request': 7, 'head': self.head, 'merge': self.merge, 'base': self.base,
                           'tree': self.tree, 'run_id': 50, 'attempt': 1, 'job_id': 151,
                           'artifact': {'id': 351, 'name': 'ci-evidence-ci-test-1', 'digest': 'sha256:' + '0' * 64},
                           'checks': ['unit']}}
        for change, text, code in ((dict(job='other'), 'PASS     lint 1s\n', 'capture-plan'),
                                   (dict(attempt=2), 'PASS     lint 1s\n', 'capture-plan'),
                                   (dict(source=self.base), 'PASS     lint 1s\n', 'capture-plan'),
                                   ({}, 'PASS     lint 1s\nPASS     unit 1s\n', 'check-coverage')):
            with self.subTest(code=code, change=change):
                path = self.scratch / 'plan.json'
                path.write_text(json.dumps(dict(plan, **change)))
                result, _ = self.run_helper(self.sha, 'capture', ['--workflow', 'ci', '--job', 'test', '--check-log',
                                                                  self.log('main.log', text), '--reuse-plan', str(path),
                                                                  '--output', str(self.scratch / 'e.json')],
                                            self.push_env())
                self.assertEqual(result.returncode, 1)
                self.assertIn('capture refused: ' + code, result.stderr)


if __name__ == '__main__':
    unittest.main()
