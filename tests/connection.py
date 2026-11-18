#!/usr/lib/tklbam-pypy2/bin/pypy
"""Prove credential replacement preserves an existing working backup."""
import os, sys, tempfile, shutil, types, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'lib'), os.path.join(ROOT, 'deps', 'lib'), '/usr/lib/tklbam/deps/lib']
sys.modules['_init_sys_path'] = types.ModuleType('_init_sys_path')
import connection, registry, hub

class ConnectionTest(unittest.TestCase):
    def setUp(self):
        self.path = tempfile.mkdtemp()
        self.original = registry.registry
        registry.registry = registry._Registry(self.path)
        registry.registry.sub_apikey = 'legacy-subkey'
        registry.registry.secret = 'keep-encryption-key'
        registry.registry.key = 'keep-keypacket'
        registry.registry.credentials = {'type': 'iamuser', 'accesskey': 'keep-cache'}
        self.before = {n: open(os.path.join(self.path, n)).read() for n in os.listdir(self.path)}
        self.Backups = hub.Backups
    def tearDown(self):
        hub.Backups = self.Backups
        registry.registry = self.original
        shutil.rmtree(self.path)
    def test_force_command_defers_selected_profile(self):
        import cmd_init
        original_init = connection.initialize
        original_update = registry.update_profile
        original_geteuid = cmd_init.os.geteuid
        arguments = sys.argv
        calls = []
        def initialize(apikey, fetch_profile=False):
            calls.append((apikey, fetch_profile))
            registry.registry.sub_apikey = 'validated-new-credential'
        def duplicate(profile):
            raise AssertionError('profile fetched again after credential replacement')
        try:
            connection.initialize = initialize
            registry.update_profile = duplicate
            cmd_init.os.geteuid = lambda: 0
            sys.argv = ['tklbam-init', '--force', '--force-profile=generic', 'A' * 20]
            cmd_init.main()
        finally:
            connection.initialize = original_init
            registry.update_profile = original_update
            cmd_init.os.geteuid = original_geteuid
            sys.argv = arguments
        self.assertEqual([('A' * 20, False)], calls)
        self.assertEqual('validated-new-credential', registry.registry.sub_apikey)
        self.assertEqual('generic', registry.registry.pending_profile)

    def test_unprivileged_init_explains_sudo_without_changing_registry(self):
        import cmd_init
        from StringIO import StringIO
        original_geteuid = cmd_init.os.geteuid
        arguments, stderr = sys.argv, sys.stderr
        try:
            cmd_init.os.geteuid = lambda: 1000
            for name, command in [('init', 'tklbam init'), ('tklbam-init', 'tklbam-init')]:
                sys.argv = [name, '--force']
                sys.stderr = StringIO()
                self.assertRaises(SystemExit, cmd_init.main)
                self.assertIn('sudo ' + command, sys.stderr.getvalue())
                self.assertEqual(self.before, {n: open(os.path.join(self.path, n)).read()
                                               for n in os.listdir(self.path)})
        finally:
            cmd_init.os.geteuid = original_geteuid
            sys.argv, sys.stderr = arguments, stderr

    def test_failed_authorization_preserves_existing_connection(self):
        class Reject:
            @staticmethod
            def get_sub_apikey(key): return 'new-subkey'
            def __init__(self, key): pass
            def get_credentials(self): raise hub.Error('AWS account needs setup')
        hub.Backups = Reject
        self.assertRaises(hub.Error, connection.initialize, 'explicit-key')
        self.assertEqual(self.before, {n: open(os.path.join(self.path, n)).read() for n in os.listdir(self.path)})
    def test_successful_force_keeps_encryption_and_history(self):
        class Accept:
            @staticmethod
            def get_sub_apikey(key): return 'new-subkey'
            def __init__(self, key): pass
            def get_credentials(self): return {'type': 'iamuser', 'accesskey': 'new-cache'}
        hub.Backups = Accept
        connection.initialize('explicit-key', fetch_profile=False)
        self.assertEqual('new-subkey', registry.registry.sub_apikey)
        self.assertEqual('keep-encryption-key', registry.registry.secret)
        self.assertEqual('keep-keypacket', registry.registry.key)

    def test_default_initialization_does_not_download_a_profile(self):
        class Accept:
            @staticmethod
            def get_sub_apikey(key): return 'new-subkey'
            def __init__(self, key): pass
            def get_credentials(self): return {'type': 'iamuser', 'accesskey': 'new-cache'}
            def get_new_profile(self, *args): raise AssertionError('profile fetched during initialization')
        hub.Backups = Accept
        connection.initialize('explicit-key')
        self.assertEqual('new-subkey', registry.registry.sub_apikey)
        self.assertIsNone(registry.registry.profile)

    def test_existing_link_without_profile_is_already_initialized(self):
        import cmd_init
        original_update = registry.update_profile
        original_geteuid = cmd_init.os.geteuid
        arguments = sys.argv
        def unexpected(*args):
            raise AssertionError('profile fetched during initialization')
        try:
            registry.update_profile = unexpected
            cmd_init.os.geteuid = lambda: 0
            sys.argv = ['tklbam-init']
            cmd_init.main()
        finally:
            registry.update_profile = original_update
            cmd_init.os.geteuid = original_geteuid
            sys.argv = arguments
        self.assertIsNone(registry.registry.profile)

    def test_solo_profile_selection_is_deferred(self):
        import cmd_init
        original_geteuid = cmd_init.os.geteuid
        arguments = sys.argv
        try:
            cmd_init.os.geteuid = lambda: 0
            sys.argv = ['tklbam-init', '--solo', '--force-profile=empty']
            cmd_init.main()
        finally:
            cmd_init.os.geteuid = original_geteuid
            sys.argv = arguments
        self.assertEqual('empty', registry.registry.pending_profile)
        self.assertIsNone(registry.registry.profile)
        self.assertIsNone(registry.registry.sub_apikey)

    def test_selected_profile_preserves_existing_profile_until_backup(self):
        import cmd_init
        registry.registry.profile = 'empty'
        original_geteuid = cmd_init.os.geteuid
        arguments = sys.argv
        try:
            cmd_init.os.geteuid = lambda: 0
            sys.argv = ['tklbam-init', '--force-profile=generic']
            cmd_init.main()
        finally:
            cmd_init.os.geteuid = original_geteuid
            sys.argv = arguments
        self.assertEqual('empty', registry.registry.profile.profile_id)
        self.assertEqual('generic', registry.registry.pending_profile)

    def test_local_profile_path_is_saved_as_absolute(self):
        import cmd_init
        custom = os.path.join(self.path, 'custom-profile')
        os.mkdir(custom)
        original_geteuid = cmd_init.os.geteuid
        arguments, original_cwd = sys.argv, os.getcwd()
        try:
            os.chdir(self.path)
            cmd_init.os.geteuid = lambda: 0
            sys.argv = ['tklbam-init', '--force-profile=./custom-profile']
            cmd_init.main()
        finally:
            os.chdir(original_cwd)
            cmd_init.os.geteuid = original_geteuid
            sys.argv = arguments
        self.assertEqual(custom, registry.registry.pending_profile)
        self.assertIsNone(registry.registry.profile)

    def test_failed_relink_keeps_existing_profile_selection(self):
        import cmd_init
        registry.registry.pending_profile = 'previous'
        original_init = connection.initialize
        original_geteuid = cmd_init.os.geteuid
        arguments = sys.argv
        def reject(*args, **kwargs):
            raise hub.Error('authorization failed')
        try:
            connection.initialize = reject
            cmd_init.os.geteuid = lambda: 0
            sys.argv = ['tklbam-init', '--force', '--force-profile=generic']
            self.assertRaises(SystemExit, cmd_init.main)
        finally:
            connection.initialize = original_init
            cmd_init.os.geteuid = original_geteuid
            sys.argv = arguments
        self.assertEqual('previous', registry.registry.pending_profile)
        self.assertEqual('legacy-subkey', registry.registry.sub_apikey)
    def test_profile_failure_preserves_existing_connection(self):
        class RejectProfile:
            Error = hub.Error
            @staticmethod
            def get_sub_apikey(key): return 'new-subkey'
            def __init__(self, key): pass
            def get_credentials(self): return {'type':'iamuser'}
            def get_new_profile(self, *args): raise hub.APIError(503, 'Unavailable', 'profile unavailable')
        hub.Backups = RejectProfile
        self.assertRaises(hub.Error, connection.initialize, 'explicit-key', fetch_profile=True)
        self.assertEqual(self.before, {n: open(os.path.join(self.path, n)).read() for n in os.listdir(self.path)})

if __name__ == '__main__': unittest.main()
