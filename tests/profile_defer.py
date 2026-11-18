#!/usr/lib/tklbam-pypy2/bin/pypy
"""Profile selections are prepared by backup rather than initialization."""
import os
import shutil
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'lib'), os.path.join(ROOT, 'deps', 'lib'),
               '/usr/lib/tklbam/deps/lib']
sys.modules['_init_sys_path'] = types.ModuleType('_init_sys_path')
import cmd_backup
import cmd_init
import hub
import registry
from utils import AttrDict


class DeferredProfileTests(unittest.TestCase):
    def setUp(self):
        self.path = tempfile.mkdtemp()
        self.original_registry = registry.registry
        self.original_backup_registry = cmd_backup.registry
        self.original_update = cmd_backup.update_profile
        self.original_check = cmd_backup.check_profile_eligibility
        cmd_backup.check_profile_eligibility = lambda selected: None
        self.original_environment = os.environ.get('TKLBAM_PROFILE_ID')
        self.reg = registry._Registry(self.path)
        registry.registry = cmd_backup.registry = self.reg

    def tearDown(self):
        registry.registry = self.original_registry
        cmd_backup.registry = self.original_backup_registry
        cmd_backup.update_profile = self.original_update
        cmd_backup.check_profile_eligibility = self.original_check
        if self.original_environment is None:
            os.environ.pop('TKLBAM_PROFILE_ID', None)
        else:
            os.environ['TKLBAM_PROFILE_ID'] = self.original_environment
        shutil.rmtree(self.path)

    def test_first_backup_prepares_selected_empty_profile(self):
        self.reg.pending_profile = 'empty'
        conf = AttrDict(force_profile=None)
        cmd_backup.prepare_backup_profile(conf)
        self.assertEqual('empty', self.reg.profile.profile_id)
        self.assertEqual('empty', conf.force_profile)
        self.assertIsNone(self.reg.pending_profile)

    def test_initialization_links_without_fetching_then_backup_fetches(self):
        calls = []
        class Archive(object):
            profile_id = 'generic'
            timestamp = 100
            def extract(self, path):
                with open(os.path.join(path, 'fixture'), 'w') as stream:
                    stream.write('profile data')
            def remove(self):
                pass
        class Backups(object):
            Error = hub.Error
            @staticmethod
            def get_sub_apikey(key):
                return 'new-subkey'
            def __init__(self, key):
                pass
            def get_credentials(self):
                return {'type': 'iamuser', 'accesskey': 'fixture'}
            def get_new_profile(self, profile, timestamp):
                calls.append((profile, timestamp))
                return Archive()
        previous_backups = hub.Backups
        previous_geteuid = cmd_init.os.geteuid
        previous_args = sys.argv
        self.reg.secret = 'existing-secret'
        self.reg.key = 'existing-key'
        try:
            hub.Backups = Backups
            cmd_init.os.geteuid = lambda: 0
            sys.argv = ['tklbam-init', '--force-profile=generic', 'A' * 20]
            cmd_init.main()
            self.assertEqual([], calls)
            self.assertIsNone(self.reg.profile)
            self.assertEqual('generic', self.reg.pending_profile)
            cmd_backup.prepare_backup_profile(AttrDict(force_profile=None))
            self.assertEqual([('generic', None)], calls)
            self.assertEqual('generic', self.reg.profile.profile_id)
            self.assertIsNone(self.reg.pending_profile)
        finally:
            hub.Backups = previous_backups
            cmd_init.os.geteuid = previous_geteuid
            sys.argv = previous_args

    def test_failed_profile_fetch_preserves_selection_and_existing_profile(self):
        self.reg.profile = 'empty'
        self.reg.pending_profile = 'generic'
        def fail(profile):
            raise RuntimeError('profile unavailable')
        cmd_backup.update_profile = fail
        conf = AttrDict(force_profile=None)
        self.assertRaises(RuntimeError, cmd_backup.prepare_backup_profile, conf)
        self.assertEqual('generic', self.reg.pending_profile)
        self.assertEqual('empty', self.reg.profile.profile_id)
        self.assertIsNone(conf.force_profile)

    def test_simulation_does_not_consume_selection(self):
        self.reg.pending_profile = 'generic'
        calls = []
        cmd_backup.update_profile = calls.append
        conf = AttrDict(force_profile=None)
        cmd_backup.prepare_backup_profile(conf, consume_pending=False)
        self.assertEqual(['generic'], calls)
        self.assertEqual('generic', self.reg.pending_profile)

    def test_explicit_backup_profile_overrides_pending_selection(self):
        self.reg.pending_profile = 'generic'
        calls = []
        cmd_backup.update_profile = calls.append
        conf = AttrDict(force_profile='configured')
        cmd_backup.prepare_backup_profile(conf, 'explicit')
        self.assertEqual(['explicit'], calls)
        self.assertEqual('explicit', conf.force_profile)
        self.assertIsNone(self.reg.pending_profile)

    def test_new_selection_is_not_cleared_while_profile_is_prepared(self):
        self.reg.pending_profile = 'generic'
        def change_selection(profile):
            self.reg.pending_profile = 'newer'
        cmd_backup.update_profile = change_selection
        cmd_backup.prepare_backup_profile(AttrDict(force_profile=None))
        self.assertEqual('newer', self.reg.pending_profile)


if __name__ == '__main__':
    unittest.main()
