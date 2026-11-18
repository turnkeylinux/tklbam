#!/usr/lib/tklbam-pypy2/bin/pypy
"""The Hub plan limit has a stable, actionable command-line result."""
import StringIO
import os
import sys
import types
import unittest
import tempfile
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'lib'), os.path.join(ROOT, 'deps', 'lib'),
               '/usr/lib/tklbam/deps/lib']
sys.modules['_init_sys_path'] = types.ModuleType('_init_sys_path')
import cmd_backup
import hub
import registry
from utils import AttrDict


class HubStub(object):
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def new_backup_record(self, key, profile_id, server_id):
        self.calls.append((key, profile_id, server_id))
        if self.error:
            raise self.error
        return 'record'


class PlanLimitTests(unittest.TestCase):
    def test_plan_limit_is_identified_by_error_name(self):
        client = HubStub(hub.APIError(401, 'BackupRecord.PlanLimitExceeded', 'different description'))
        previous = sys.stderr
        output = StringIO.StringIO()
        sys.stderr = output
        try:
            with self.assertRaises(SystemExit) as raised:
                cmd_backup.create_backup_record(client, 'key', 'profile', 'server')
        finally:
            sys.stderr = previous
        self.assertEqual(raised.exception.code, 12)
        self.assertIn('https://hub.turnkeylinux.org/billing/', output.getvalue())
        self.assertIn('run tklbam-backup again', output.getvalue())

    def test_other_hub_errors_keep_their_original_behavior(self):
        error = hub.APIError(401, 'BackupAccount.InvalidSubKey', 'bad key')
        with self.assertRaises(hub.APIError) as raised:
            cmd_backup.create_backup_record(HubStub(error), 'key', 'profile', None)
        self.assertIs(raised.exception, error)

    def test_success_returns_the_record(self):
        client = HubStub()
        self.assertEqual(cmd_backup.create_backup_record(client, 'key', 'profile', 'server'), 'record')
        self.assertEqual(client.calls, [('key', 'profile', 'server')])

    def test_profile_limit_prevents_download_and_retains_selection(self):
        path = tempfile.mkdtemp()
        saved_registry = cmd_backup.registry
        saved_hub = cmd_backup.hub_backups
        saved_update = cmd_backup.update_profile
        reg = registry._Registry(path)
        reg.pending_profile = 'generic'
        class Client(object):
            def check_profile_eligibility(self, record):
                raise hub.APIError(401, 'BackupRecord.PlanLimitExceeded', 'limit')
        try:
            cmd_backup.registry = reg
            cmd_backup.hub_backups = lambda: Client()
            cmd_backup.update_profile = lambda selected: self.fail('profile downloaded')
            with self.assertRaises(SystemExit) as raised:
                cmd_backup.prepare_backup_profile(AttrDict(force_profile=None))
            self.assertEqual(12, raised.exception.code)
            self.assertEqual('generic', reg.pending_profile)
        finally:
            cmd_backup.registry = saved_registry
            cmd_backup.hub_backups = saved_hub
            cmd_backup.update_profile = saved_update
            shutil.rmtree(path)

    def test_empty_profile_needs_no_hub_check(self):
        cmd_backup.check_profile_eligibility('empty')

    def test_cached_profile_needs_no_hub_check(self):
        path = tempfile.mkdtemp()
        saved_registry = cmd_backup.registry
        saved_hub = cmd_backup.hub_backups
        try:
            reg = registry._Registry(path)
            class Archive(object):
                profile_id = 'generic'
                timestamp = 100
                def extract(self, destination):
                    with open(os.path.join(destination, 'fixture'), 'w') as stream:
                        stream.write('profile')
                def remove(self):
                    pass
            reg.profile = Archive()
            cmd_backup.registry = reg
            cmd_backup.hub_backups = lambda: self.fail('unexpected Hub check')
            cmd_backup.check_profile_eligibility('generic')
        finally:
            cmd_backup.registry = saved_registry
            cmd_backup.hub_backups = saved_hub
            shutil.rmtree(path)

    def test_client_submits_record_identity(self):
        client = hub.Backups('test')
        calls = []
        client._api = lambda method, uri, attrs: calls.append((method, uri, attrs)) or {'allowed': True}
        client.check_profile_eligibility(AttrDict(backup_id=7, record_id=42, address='private'))
        self.assertEqual([('GET', 'profile/eligibility/', {'backup_id': 7, 'record_id': 42})], calls)


if __name__ == '__main__':
    unittest.main()
