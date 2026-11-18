#!/usr/lib/tklbam-pypy2/bin/pypy
"""Prove credential replacement preserves an existing working backup."""
import os, sys, tempfile, shutil, unittest
import stat
import hashlib
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
        original_geteuid = cmd_init.os.geteuid
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
            cmd_init.os.geteuid = lambda: 0
            sys.argv = ['tklbam-init', '--force', '--force-profile=generic', 'A' * 20]
            cmd_init.main()
        finally:
            connection.initialize = original_init
            registry.update_profile = original_update
            cmd_init.os.geteuid = original_geteuid
            sys.argv = arguments
        self.assertEqual([('A' * 20, 'generic')], calls)
        self.assertEqual('validated-new-credential', registry.registry.sub_apikey)

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


class ScheduledCredentialsTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.credentials = dict(type='iamrole', accesskey='fixture', secretkey='fixture',
                                sessiontoken='fixture', expiration='2030-01-01T00:00:00Z')
        self.backups = hub.Backups('fixture')
        self.response = self.credentials.copy()

        def request(method, uri, attrs=None):
            self.calls.append((method, uri, attrs))
            return self.response.copy()
        self.backups._api = request

    def test_manual_credentials_keep_the_original_request_shape(self):
        self.assertEqual('iamrole', self.backups.get_credentials().type)
        self.assertEqual([('GET', 'credentials/', None)], self.calls)

    def test_scheduled_iam_credentials_require_one_explicit_authorization(self):
        self.response['scheduled'] = 'allowed'
        self.assertEqual(self.credentials, self.backups.get_credentials(scheduled=True))
        self.assertEqual([('GET', 'credentials/', {'scheduled': '1'})], self.calls)

    def test_disabled_schedule_skips_without_parsing_credentials(self):
        self.response = {'scheduled': 'disabled'}
        self.assertRaises(hub.ScheduleDisabled, self.backups.get_credentials, scheduled=True)
        self.assertEqual([('GET', 'credentials/', {'scheduled': '1'})], self.calls)

    def test_old_hub_response_cannot_authorize_a_scheduled_run(self):
        self.assertRaises(hub.Error, self.backups.get_credentials, scheduled=True)
        self.assertEqual([('GET', 'credentials/', {'scheduled': '1'})], self.calls)

    def test_only_scheduled_iam_credentials_are_accepted(self):
        self.response = {'scheduled': 'allowed', 'type': 'devpay'}
        self.assertRaises(hub.Error, self.backups.get_credentials, scheduled=True)
        self.response = {'scheduled': 'allowed', 'type': 'iamrole'}
        self.assertRaises(hub.Error, self.backups.get_credentials, scheduled=True)


class DailyInitializationTest(unittest.TestCase):
    def setUp(self):
        import cmd_init
        path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, path)
        self.calls = []
        self.device = 'a' * 32
        self.token = 'tklbam2.' + self.device + '.' + 'b' * 43
        self.current = registry._Registry(os.path.join(path, 'registry'))
        self.marker = os.path.join(self.current.path, 'hub-managed-daily')
        self.ready = os.path.join(self.current.path, 'hub-daily-initialized')
        cron_directory = os.path.join(path, 'cron.daily')
        os.mkdir(cron_directory)
        self.cron = os.path.join(cron_directory, 'tklbam-backup')
        self.reference = os.path.join(path, 'reference')
        shutil.copyfile(os.path.join(ROOT, 'contrib/cron.sh'), self.reference)
        shutil.copyfile(self.reference, self.cron)
        os.chmod(self.cron, 0644)
        self.current._file_str(self.marker, self.device + ' managed')
        self.replace(connection, 'DAILY_CRON', self.cron)
        self.replace(connection, 'CRON_REFERENCE', self.reference)
        self.replace(connection, 'DEFAULT_REGISTRY', str(self.current.path))
        self.replace(registry, 'registry', self.current)
        self.replace(cmd_init.os, 'geteuid', lambda: 0)

        def helper():
            self.calls.append('helper')
            return self.token
        self.replace(connection, 'hub_token', helper)

        fixture = self
        class Backups(hub.Backups):
            @staticmethod
            def get_sub_apikey(key):
                fixture.calls.append('legacy helper')
                return 'legacy'

            def get_credentials(self):
                fixture.calls.append(self.subkey)
                return hub.Credentials.IAMRole('key', 'secret', 'token', '2030-01-01T00:00:00Z')
        self.replace(hub, 'Backups', Backups)
        self.main = cmd_init.main

    def replace(self, module, name, value):
        self.addCleanup(setattr, module, name, getattr(module, name))
        setattr(module, name, value)

    def initialize(self, *args):
        original = sys.argv
        try:
            sys.argv = ['tklbam-init'] + list(args)
            self.main()
        finally:
            sys.argv = original

    def test_successful_init_activates_and_retry_makes_no_request(self):
        self.initialize('--force-profile=empty')
        self.assertEqual(['helper', self.token], self.calls)
        self.assertEqual(self.token, connection.initialized_daily(self.current))
        self.assertEqual(0744, stat.S_IMODE(os.stat(self.cron).st_mode))
        self.assertTrue(self.current.secret and self.current.profile)

        self.initialize()
        self.assertEqual(['helper', self.token], self.calls)

    def test_failed_credentials_leave_a_dormant_job(self):
        def reject(backups):
            raise hub.Error('AWS account needs setup')
        self.replace(hub.Backups, 'get_credentials', reject)
        self.assertRaises(SystemExit, self.initialize, '--force-profile=empty')
        self.assertFalse(os.path.exists(self.ready))
        self.assertEqual(0644, stat.S_IMODE(os.stat(self.cron).st_mode))

    def test_relink_during_init_credentials_leaves_a_dormant_job(self):
        original = hub.Backups.get_credentials
        def relink(backups):
            self.current._file_str(self.marker, 'c' * 32 + ' managed')
            return original(backups)
        self.replace(hub.Backups, 'get_credentials', relink)
        self.initialize('--force-profile=empty')
        self.assertIsNone(connection.initialized_daily(self.current))
        self.assertEqual(0644, stat.S_IMODE(os.stat(self.cron).st_mode))

    def test_solo_disables_the_job_and_clears_scheduled_readiness(self):
        self.initialize('--force-profile=empty')
        self.initialize('--solo')
        self.assertFalse(os.path.exists(self.ready))
        self.assertEqual(0644, stat.S_IMODE(os.stat(self.cron).st_mode))

    def test_legacy_initialization_leaves_managed_schedule_disabled(self):
        self.initialize('--force-profile=empty')
        self.initialize('--force', 'A' * 20)
        self.assertFalse(os.path.exists(self.ready))
        self.assertEqual(0644, stat.S_IMODE(os.stat(self.cron).st_mode))

    def test_solo_preserves_administrator_owned_executable_mode(self):
        self.current._file_str(self.marker, self.device + ' local')
        os.chmod(self.cron, 0755)
        self.initialize('--force-profile=empty')
        self.initialize('--solo')
        self.assertFalse(os.path.exists(self.ready))
        self.assertEqual(0755, stat.S_IMODE(os.stat(self.cron).st_mode))

    def test_edited_job_stays_under_local_control(self):
        with open(self.cron, 'a') as stream:
            stream.write('# Admin edit\n')
        self.initialize('--force-profile=empty')
        self.assertFalse(os.path.exists(self.ready))
        self.assertEqual(0644, stat.S_IMODE(os.stat(self.cron).st_mode))

    def test_existing_alternate_job_prevents_daily_activation(self):
        cron_dir = os.path.join(os.path.dirname(os.path.dirname(self.cron)), 'cron.weekly')
        os.mkdir(cron_dir)
        with open(os.path.join(cron_dir, 'tklbam-backup'), 'w'):
            pass
        os.chmod(os.path.join(cron_dir, 'tklbam-backup'), 0755)
        self.initialize('--force-profile=empty')
        self.assertFalse(os.path.exists(self.ready))
        self.assertEqual(0644, stat.S_IMODE(os.stat(self.cron).st_mode))


    def credential_process(self, callback):
        from cmd_internals import cmd_stsagent
        from StringIO import StringIO
        self.replace(cmd_stsagent, 'registry', self.current)
        self.replace(cmd_stsagent, 'get_credentials', callback)
        self.replace(sys, 'argv', ['stsagent', '--json'])
        self.replace(sys, 'stdout', StringIO())
        name = 'TKLBAM_SCHEDULED_TOKEN_SHA256'
        self.addCleanup(os.environ.pop, name, None)
        os.environ[name] = hashlib.sha256(self.token).hexdigest()
        return cmd_stsagent.main

    def test_credential_process_keeps_unmarked_request_for_same_grant(self):
        self.initialize('--force-profile=empty')
        run = self.credential_process(lambda backups: backups.get_credentials())
        run()
        self.assertEqual(['helper', self.token, self.token], self.calls)

    def test_credential_process_rejects_a_replacement_token_before_requesting(self):
        self.initialize('--force-profile=empty')
        run = self.credential_process(lambda backups: self.fail('credential request made after relink'))
        self.current.sub_apikey = self.token[:-1] + 'c'
        self.assertRaises(SystemExit, run)

    def test_credential_process_withholds_credentials_after_a_relink(self):
        self.initialize('--force-profile=empty')
        def relink(backups):
            credentials = backups.get_credentials()
            self.current._file_str(self.marker, 'c' * 32 + ' managed')
            return credentials
        run = self.credential_process(relink)
        self.assertRaises(SystemExit, run)
        self.assertEqual('', sys.stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
