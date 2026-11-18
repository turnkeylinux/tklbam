#!/usr/lib/tklbam-pypy2/bin/pypy
"""The Hub plan limit has a stable, actionable command-line result."""
import StringIO
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'lib'), os.path.join(ROOT, 'deps', 'lib'),
               '/usr/lib/tklbam/deps/lib']
sys.modules['_init_sys_path'] = types.ModuleType('_init_sys_path')
import cmd_backup
import hub


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


if __name__ == '__main__':
    unittest.main()
