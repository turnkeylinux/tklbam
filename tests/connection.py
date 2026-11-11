#!/usr/lib/tklbam-pypy2/bin/pypy
"""Prove credential replacement preserves an existing working backup."""
import os, sys, tempfile, shutil, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'lib'), '/usr/lib/tklbam/deps/lib']
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
    def test_force_command_fetches_profile_only_before_replacement(self):
        import cmd_init
        original_init = connection.initialize
        original_update = registry.update_profile
        arguments = sys.argv
        calls = []
        def initialize(apikey, profile):
            calls.append((apikey, profile))
            registry.registry.sub_apikey = 'validated-new-credential'
        def duplicate(profile):
            raise AssertionError('profile fetched again after credential replacement')
        try:
            connection.initialize = initialize
            registry.update_profile = duplicate
            sys.argv = ['tklbam-init', '--force', '--force-profile=generic', 'A' * 20]
            cmd_init.main()
        finally:
            connection.initialize = original_init
            registry.update_profile = original_update
            sys.argv = arguments
        self.assertEqual([('A' * 20, 'generic')], calls)
        self.assertEqual('validated-new-credential', registry.registry.sub_apikey)

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
    def test_profile_failure_preserves_existing_connection(self):
        class RejectProfile:
            Error = hub.Error
            @staticmethod
            def get_sub_apikey(key): return 'new-subkey'
            def __init__(self, key): pass
            def get_credentials(self): return {'type':'iamuser'}
            def get_new_profile(self, *args): raise hub.APIError(503, 'Unavailable', 'profile unavailable')
        hub.Backups = RejectProfile
        self.assertRaises(hub.Error, connection.initialize, 'explicit-key')
        self.assertEqual(self.before, {n: open(os.path.join(self.path, n)).read() for n in os.listdir(self.path)})

if __name__ == '__main__': unittest.main()
