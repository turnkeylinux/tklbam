#!/usr/lib/tklbam-pypy2/bin/pypy
"""Exercise backup finalization and simulation without a storage provider."""
import errno
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'lib'), '/usr/lib/tklbam/deps/lib']


def child(mode, path):
    import registry
    from utils import AttrDict
    registry.registry = registry._Registry(os.path.join(path, 'registry'))
    reg = registry.registry
    reg.sub_apikey = 'synthetic-subkey'
    reg.secret = 'synthetic-passphrase'
    reg.key = 'synthetic-keypacket'
    import cmd_backup as command
    command.PATH_LOGFILE = os.path.join(path, 'backup.log')
    command.PATH_PIDLOCK = os.path.join(path, 'backup.pid')
    events = []
    def event(name):
        events.append(name)
        with open(os.path.join(path, 'events'), 'a') as stream:
            stream.write(name + '\n')
    class Hub(object):
        Error = Exception
        def get_credentials(self):
            event('credentials')
            if mode.startswith('simulate'):
                raise AssertionError('simulation contacted Hub credentials')
            return AttrDict(type='iamuser', accesskey='synthetic', secretkey='synthetic', sessiontoken='')
        def new_backup_record(self, *args):
            event('record/create')
            return AttrDict(backup_id=17, address='file://' + os.path.join(path, 'target'))
        def get_backup_record(self, *args):
            event('record/read')
            return reg.hbr
        def set_backup_inprogress(self, backup_id, value):
            event('inprogress/' + str(value))
        def updated_backup(self, address):
            event('updated')
    command.hub_backups = lambda: Hub()
    command.hooks.backup.pre = lambda: None
    command.hooks.backup.inspect = lambda path: None
    command.hooks.backup.post = lambda: None
    source = os.path.join(path, 'source')
    os.mkdir(source)
    with open(os.path.join(source, 'example'), 'w') as stream:
        stream.write('fixture\n')
    if mode.endswith('display'):
        def upload(self, *args, **kwargs):
            os.write(1, '~' * 131072)
            event('uploaded')
        command.duplicity.Duplicity.run = upload
        original_trap = command.UnitedStdTrap
        class CapturedTrap(original_trap):
            def close(self):
                original_trap.close(self)
                with open(os.path.join(path, 'captured'), 'w') as stream:
                    stream.write(self.std.getvalue())
        command.UnitedStdTrap = CapturedTrap
        with open(os.path.join(path, 'ready'), 'w') as stream:
            stream.write('ready')
        while not os.path.exists(os.path.join(path, 'go')):
            time.sleep(.01)
        sys.argv = ['tklbam-backup', '--raw-upload=' + source]
        if mode in ('existing-display', 'resume-display'):
            reg.hbr = AttrDict(backup_id=17, address='file://' + os.path.join(path, 'target'))
        if mode == 'resume-display':
            previous = command.Conf()
            previous.address = reg.hbr.address
            previous.secretfile = reg.path.secret
            reg.backup_resume_conf = previous
            sys.argv.append('--resume')
        else:
            sys.argv.append('--disable-resume')
        if mode == 'custom-display':
            sys.argv.append('--address=file://' + os.path.join(path, 'target'))
    else:
        reg.backup_resume_conf = command.Conf()
        if not os.path.isdir('/TKLBAM'):
            os.mkdir('/TKLBAM')
        with open('/TKLBAM/resume-marker', 'w') as stream:
            stream.write('keep interrupted extract')
        before = {n: open(os.path.join(reg.path, n), 'rb').read()
                  for n in os.listdir(reg.path) if os.path.isfile(os.path.join(reg.path, n))}
        sys.argv = ['tklbam-backup', '--simulate', '--disable-resume', '--force-profile=empty',
                    '--skip-files', '--skip-database', '--skip-packages']
        if mode == 'simulate-raw':
            sys.argv.append('--raw-upload=' + source)
    if mode == 'simulate-uninitialized':
        reg.sub_apikey = None
        reg.secret = None
        reg.key = None
        before = {n: open(os.path.join(reg.path, n), 'rb').read()
                  for n in os.listdir(reg.path) if os.path.isfile(os.path.join(reg.path, n))}
        import cmd_init
        def unexpected_init():
            raise AssertionError('simulation initialized the Hub connection')
        cmd_init.main = unexpected_init
    command.main()
    sys.stdout.flush()
    sys.stderr.flush()
    if mode.startswith('simulate'):
        after = {n: open(os.path.join(reg.path, n), 'rb').read()
                 for n in before if os.path.isfile(os.path.join(reg.path, n))}
        assert before == after, 'simulation changed identity/resume state'
        assert reg.hbr is None, 'simulation allocated a backup record'
        assert not events, events
        assert open('/TKLBAM/resume-marker').read() == 'keep interrupted extract'
    with open(os.path.join(path, 'completed'), 'w') as stream:
        stream.write('complete')


class BackupLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.path = tempfile.mkdtemp(prefix='tklbam-lifecycle-')
    def tearDown(self):
        shutil.rmtree(self.path)
    def run_child(self, mode, disconnect=False):
        master = slave = None
        if mode.endswith('display'):
            master, slave = os.openpty()
        process = subprocess.Popen([sys.executable, __file__, '--child', mode, self.path],
                                   stdout=slave if slave is not None else subprocess.PIPE,
                                   stderr=slave if slave is not None else subprocess.STDOUT,
                                   preexec_fn=os.setsid, close_fds=True)
        if slave is not None:
            os.close(slave)
        deadline = time.time() + 8
        output = ''
        try:
            if master is not None:
                while not os.path.exists(os.path.join(self.path, 'ready')) and process.poll() is None:
                    self.assertLess(time.time(), deadline, 'child never reached backup')
                    time.sleep(.01)
                if disconnect:
                    os.close(master)
                    master = None
                with open(os.path.join(self.path, 'go'), 'w') as stream:
                    stream.write('go')
            while process.poll() is None:
                if time.time() > deadline:
                    self.fail('backup did not finalize after display closed')
                if master is not None:
                    import select
                    if select.select([master], [], [], .01)[0]:
                        try:
                            output += os.read(master, 65536)
                        except OSError as error:
                            if error.errno != errno.EIO:
                                raise
                else:
                    time.sleep(.01)
            if process.stdout:
                output += process.stdout.read()
            self.assertEqual(0, process.returncode, output)
            self.assertTrue(os.path.exists(os.path.join(self.path, 'completed')), output)
            return output
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            if master is not None:
                os.close(master)
    def test_closed_webmin_display_still_finalizes_backup_and_log(self):
        self.run_child('closed-display', disconnect=True)
        events = open(os.path.join(self.path, 'events')).read().splitlines()
        self.assertEqual(['credentials', 'record/create', 'inprogress/True', 'uploaded',
                          'uploaded', 'inprogress/False', 'updated'], events)
        self.assertEqual(262144, open(os.path.join(self.path, 'backup.log')).read().count('~'))
        self.assertEqual(262144, open(os.path.join(self.path, 'captured')).read().count('~'))
    def test_healthy_display_preserves_output_and_finalization(self):
        output = self.run_child('healthy-display')
        self.assertEqual(262144, output.count('~'))
        self.assertIn('TIP: test your backups', output)
    def test_simulation_without_record_preserves_identity_and_resume(self):
        output = self.run_child('simulate')
        self.assertIn('Completed --simulate:', output)
        self.assertIn('Backup Statistics', output)
    def test_raw_simulation_without_record_preserves_identity_and_resume(self):
        output = self.run_child('simulate-raw')
        self.assertIn('Backup Statistics', output)
    def test_simulation_does_not_initialize_an_unlinked_client(self):
        self.assertIn('Backup Statistics', self.run_child('simulate-uninitialized'))
    def test_existing_record_is_reused_for_real_backup(self):
        self.run_child('existing-display')
        events = open(os.path.join(self.path, 'events')).read().splitlines()
        self.assertNotIn('record/create', events)
        self.assertIn('record/read', events)
        self.assertEqual('updated', events[-1])
    def test_explicit_resume_skips_cleanup_and_keeps_record(self):
        self.run_child('resume-display')
        events = open(os.path.join(self.path, 'events')).read().splitlines()
        self.assertNotIn('record/create', events)
        self.assertEqual(1, events.count('uploaded'))
        self.assertEqual('updated', events[-1])
    def test_custom_address_backup_avoids_hub(self):
        self.run_child('custom-display')
        self.assertEqual(['uploaded', 'uploaded'],
                         open(os.path.join(self.path, 'events')).read().splitlines())


class ScheduledBackupTests(unittest.TestCase):
    def setUp(self):
        self.path = tempfile.mkdtemp(prefix='tklbam-scheduled-')

    def tearDown(self):
        shutil.rmtree(self.path)

    def run_child(self, mode, status):
        process = subprocess.Popen([sys.executable, __file__, '--scheduled-child', mode, self.path],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = process.communicate()[0]
        self.assertEqual(status, process.returncode, output)
        with open(os.path.join(self.path, 'events')) as stream:
            return stream.read().splitlines()

    def test_first_scheduled_run_reuses_initialization_and_requests_credentials_once(self):
        events = self.run_child('first', 0)
        self.assertEqual(['scheduled credentials', 'profile', 'record/create',
                          'inprogress/True', 'upload', 'upload', 'inprogress/False', 'updated'],
                         events)

    def test_initialized_run_reuses_the_scoped_token_and_record(self):
        events = self.run_child('repeat', 0)
        self.assertEqual(['scheduled credentials', 'profile', 'record/read',
                          'inprogress/True', 'upload', 'upload', 'inprogress/False',
                          'updated'], events)

    def test_record_id_collision_uses_a_new_destination_and_discards_old_resume(self):
        events = self.run_child('record-collision', 0)
        self.assertEqual(['scheduled credentials', 'profile', 'record/read', 'record/create',
                          'inprogress/True', 'upload', 'upload', 'inprogress/False', 'updated'], events)

    def test_same_stable_record_id_reuses_a_relocated_scoped_record(self):
        events = self.run_child('scoped-record-relocated', 0)
        self.assertEqual(['scheduled credentials', 'profile', 'record/read',
                          'inprogress/True', 'upload', 'upload', 'inprogress/False', 'updated'], events)
        hbr = open(os.path.join(self.path, 'registry', 'hbr')).read().splitlines()
        self.assertIn('record_id=101', hbr)
        self.assertIn('address=file://' + os.path.join(self.path, 'target'), hbr)

    def test_different_stable_record_id_requires_new_record_at_the_same_address(self):
        events = self.run_child('stable-record-collision', 0)
        self.assertEqual(['scheduled credentials', 'profile', 'record/read', 'record/create',
                          'inprogress/True', 'upload', 'upload', 'inprogress/False', 'updated'], events)
        hbr = open(os.path.join(self.path, 'registry', 'hbr')).read().splitlines()
        self.assertIn('record_id=303', hbr)

    def test_legacy_relocation_reuses_the_record_without_a_stable_id(self):
        events = self.run_child('legacy-record-relocated', 0)
        self.assertEqual(['profile', 'manual credentials', 'record/read',
                          'inprogress/True', 'upload', 'upload', 'inprogress/False', 'updated'], events)

    def test_manual_resume_stops_when_the_same_record_has_moved(self):
        events = self.run_child('manual-resume-relocated', 1)
        self.assertEqual(['profile', 'manual credentials', 'record/read'], events)
        self.assertFalse(os.path.exists(os.path.join(self.path, 'registry', 'backup-resume')))

    def test_deleted_record_uses_a_new_destination_and_discards_old_resume(self):
        events = self.run_child('record-missing', 0)
        self.assertEqual(['scheduled credentials', 'profile', 'record/read', 'record/create',
                          'inprogress/True', 'upload', 'upload', 'inprogress/False', 'updated'], events)

    def test_failed_record_lookup_does_not_upload_to_a_cached_destination(self):
        events = self.run_child('record-unavailable', 1)
        self.assertEqual(['scheduled credentials', 'profile', 'record/read'], events)

    def test_scoped_manual_backup_stops_when_the_old_destination_cannot_be_verified(self):
        events = self.run_child('manual-record-unavailable', 1)
        self.assertEqual(['profile', 'manual credentials', 'record/read'], events)

    def test_legacy_manual_backup_can_retry_its_cached_destination(self):
        events = self.run_child('legacy-record-unavailable', 0)
        self.assertEqual(['profile', 'manual credentials', 'record/read',
                          'inprogress/True', 'upload', 'upload', 'inprogress/False', 'updated'], events)

    def test_scheduled_explicit_resume_stops_before_contacting_hub(self):
        self.assertEqual([], self.run_child('scheduled-explicit-resume', 1))
        self.assertTrue(os.path.exists(os.path.join(self.path, 'registry', 'backup-resume')))

    def test_manual_explicit_resume_rejects_a_conflicting_record(self):
        events = self.run_child('manual-explicit-resume', 1)
        self.assertEqual(['profile', 'manual credentials', 'record/read'], events)
        self.assertTrue(os.path.exists(os.path.join(self.path, 'registry', 'backup-resume')))

    def test_dormant_link_makes_no_request_and_leaves_state_uninitialized(self):
        self.assertEqual([], self.run_child('dormant', 0))
        self.assertEqual(['hub-managed-daily'], os.listdir(os.path.join(self.path, 'registry')))

    def test_opt_out_skips_before_profile_and_upload(self):
        self.assertEqual(['scheduled credentials'], self.run_child('disabled', 0))
        directory = os.path.join(self.path, 'registry')
        self.assertFalse(os.path.exists(os.path.join(directory, 'profile')))
        self.assertEqual('empty', open(os.path.join(directory, 'pending-profile')).read().strip())

    def test_old_hub_acknowledgement_failure_does_not_upload(self):
        self.assertEqual(['scheduled credentials'], self.run_child('old-hub', 1))

    def test_relink_does_not_start_a_run_with_the_old_registry(self):
        self.assertEqual([], self.run_child('relinked', 0))
        directory = os.path.join(self.path, 'registry')
        self.assertEqual('previous key', open(os.path.join(directory, 'secret')).read().strip())
        self.assertTrue(open(os.path.join(directory, 'sub_apikey')).read().startswith('tklbam2.' + 'a' * 32))

    def test_unavailable_hub_does_not_fall_back_to_cached_credentials(self):
        self.assertEqual(['scheduled credentials'], self.run_child('unavailable', 1))

    def test_relink_during_credentials_request_does_not_prepare_profile_or_record(self):
        self.assertEqual(['scheduled credentials'], self.run_child('relink-auth', 1))

    def test_relink_during_profile_preparation_does_not_prepare_record(self):
        self.assertEqual(['scheduled credentials', 'profile'], self.run_child('relink-profile', 1))

    def test_relink_during_record_request_does_not_upload_or_save_the_new_record(self):
        self.assertEqual(['scheduled credentials', 'profile', 'record/create'],
                         self.run_child('relink-record', 1))
        self.assertFalse(os.path.exists(os.path.join(self.path, 'registry', 'hbr')))

    def test_relink_during_backup_preparation_does_not_upload(self):
        self.assertEqual(['scheduled credentials', 'profile', 'record/create',
                          'inprogress/True', 'inprogress/False'],
                         self.run_child('relink-upload', 1))


def scheduled_child(mode, path):
    import cmd_backup as command
    import connection
    import hub
    import registry
    from utils import AttrDict

    current = registry._Registry(os.path.join(path, 'registry'))
    registry.registry = command.registry = current
    connection.DEFAULT_REGISTRY = str(current.path)
    command.PATH_LOGFILE = os.path.join(path, 'backup.log')
    command.PATH_PIDLOCK = os.path.join(path, 'backup.pid')
    target = 'file://' + os.path.join(path, 'target')
    old_target = 'file://' + os.path.join(path, 'old-target')
    conflicting_target = 'file://' + os.path.join(path, 'conflicting-target')
    device = 'a' * 32
    token = 'tklbam2.%s.%s' % (device, 'c' * 43)
    if mode.startswith('legacy-'):
        token = 'account-wide-legacy-key'
    manual = mode.startswith(('manual-', 'legacy-'))
    relocated = mode in ('scoped-record-relocated', 'legacy-record-relocated', 'manual-resume-relocated')
    replace_record = mode in ('record-collision', 'record-missing', 'stable-record-collision')
    pending = os.path.join(current.path, 'hub-managed-daily')

    def set_pending(id):
        with open(pending, 'w') as stream:
            stream.write(id + ' managed\n')

    set_pending('b' * 32 if mode == 'relinked' else device)
    events_path = os.path.join(path, 'events')
    with open(events_path, 'w'):
        pass

    def event(name):
        with open(events_path, 'a') as stream:
            stream.write(name + '\n')

    if mode != 'dormant':
        current.sub_apikey = token
        current.secret = 'previous key'
        current.key = 'previous keypacket'
        if mode in ('first', 'disabled'):
            current.pending_profile = 'empty'
        else:
            current.profile = 'empty'
        current._file_str(os.path.join(current.path, 'hub-daily-initialized'), device)
        if mode in ('repeat', 'legacy-record-unavailable'):
            current.hbr = AttrDict(backup_id=17, address=target)
        if relocated or mode in ('record-collision', 'record-missing', 'record-unavailable',
                                 'manual-record-unavailable', 'scheduled-explicit-resume',
                                 'manual-explicit-resume', 'stable-record-collision'):
            address = target if mode == 'stable-record-collision' else old_target
            saved = AttrDict(backup_id=17, address=address)
            if mode in ('scoped-record-relocated', 'manual-resume-relocated', 'stable-record-collision'):
                saved.record_id = 101
            current.hbr = saved
            previous = command.Conf()
            previous.address = address
            previous.secretfile = current.path.secret
            current.backup_resume_conf = previous
        current.credentials = {'type': 'iamuser', 'accesskey': 'legacy-cache',
                               'secretkey': 'legacy-cache', 'sessiontoken': ''}

    def helper():
        raise AssertionError('scheduled backup called the init helper')

    class Hub(hub.Backups):
        def _api(self, method, uri, attrs=None):
            assert (self.subkey, method, uri) == (token, 'GET', 'credentials/')
            if manual:
                assert not attrs
                event('manual credentials')
            else:
                assert attrs == {'scheduled': '1'}
                event('scheduled credentials')
            if mode in ('first', 'disabled'):
                assert current.profile is None and current.pending_profile == 'empty'
            if mode == 'disabled':
                return {'scheduled': 'disabled'}
            if mode == 'unavailable':
                raise hub.APIError(503, 'Unavailable', 'Hub unavailable')
            if mode == 'relink-auth':
                set_pending('b' * 32)
            response = dict(type='iamrole', accesskey='fixture', secretkey='fixture',
                            sessiontoken='fixture', expiration='2030-01-01T00:00:00Z')
            if not manual and mode != 'old-hub':
                response['scheduled'] = 'allowed'
            return response
        def new_backup_record(self, key, *args):
            assert key
            if mode == 'first':
                assert current.profile.profile_id == 'empty' and current.pending_profile is None
            event('record/create')
            if mode == 'relink-record':
                set_pending('b' * 32)
            if replace_record:
                assert current.backup_resume_conf is None
                return AttrDict(backup_id=18, address=target, record_id=303)
            return AttrDict(backup_id=17, address=target)
        def get_backup_record(self, backup_id):
            event('record/read')
            if mode == 'record-missing':
                raise hub.InvalidBackupError('record deleted')
            if mode in ('record-unavailable', 'manual-record-unavailable', 'legacy-record-unavailable'):
                raise hub.APIError(503, 'Unavailable', 'Hub unavailable')
            if mode in ('record-collision', 'manual-explicit-resume'):
                return AttrDict(backup_id=backup_id, address=conflicting_target)
            if mode == 'stable-record-collision':
                return AttrDict(backup_id=backup_id, address=target, record_id=202)
            if relocated:
                moved = AttrDict(backup_id=backup_id, address=target)
                if not mode.startswith('legacy-'):
                    moved.record_id = 101
                return moved
            return current.hbr
        def set_backup_inprogress(self, backup_id, value):
            assert str(backup_id) == ('18' if replace_record else '17')
            event('inprogress/' + str(value))
        def updated_backup(self, address):
            assert address == target
            event('updated')

    connection.hub_token = helper
    hub.Backups = Hub
    prepare_profile = registry._Registry.update_profile
    def profile(self, profile_id=None):
        event('profile')
        if mode == 'relink-profile':
            set_pending('b' * 32)
        return prepare_profile(self, profile_id)
    registry._Registry.update_profile = profile

    def inspect(path):
        if mode == 'relink-upload':
            set_pending('b' * 32)

    command.hooks.backup.pre = lambda: None
    command.hooks.backup.inspect = inspect
    command.hooks.backup.post = lambda: None
    def upload(duplicity, *args, **kwargs):
        assert duplicity.command[-1] == target, duplicity.command
        event('upload')

    command.duplicity.Duplicity.run = upload
    sys.argv = ['tklbam-backup', '--skip-files', '--skip-database', '--skip-packages']
    if not manual:
        sys.argv.append('--scheduled')
    if mode in ('scheduled-explicit-resume', 'manual-explicit-resume', 'manual-resume-relocated'):
        sys.argv.append('--resume')
    command.main()


class CronScheduleTests(unittest.TestCase):
    def setUp(self):
        self.path = tempfile.mkdtemp(prefix='tklbam-cron-')
        self.calls = os.path.join(self.path, 'calls')
        self.env = dict(os.environ, TKLBAM_REGISTRY=self.path, CALLS=self.calls,
                        JITTER='1', PATH=self.path + ':' + os.environ['PATH'])
        for command in ('sleep', 'tklbam-backup'):
            with open(os.path.join(self.path, command), 'w') as stream:
                stream.write('#!/bin/sh\nprintf "%%s %%s\\n" %s "$*" >> "$CALLS"\n' % command)
            os.chmod(os.path.join(self.path, command), 0700)

    def tearDown(self):
        shutil.rmtree(self.path)

    def run_cron(self, path):
        # Set argv[0] to the installed path without modifying the system's cron.
        script = open(os.path.join(ROOT, 'contrib/cron.sh')).read()
        # Point the packaged default at an isolated registry without altering host /var/lib.
        script = script.replace('/var/lib/tklbam', self.path)
        subprocess.check_call(['bash', '-c', script, path], env=self.env)
        return open(self.calls).read().splitlines() if os.path.exists(self.calls) else []

    def enable_managed(self):
        with open(os.path.join(self.path, 'hub-managed-daily'), 'w') as stream:
            stream.write('a' * 32 + ' managed\n')

    def test_pending_daily_does_not_sleep_or_run_backup(self):
        self.enable_managed()
        self.assertEqual([], self.run_cron('/etc/cron.daily/tklbam-backup'))

    def test_initialized_daily_jitters_before_running_backup(self):
        self.enable_managed()
        for filename, value in (('secret', 'secret'), ('key', 'keypacket'),
                                ('hub-daily-initialized', 'a' * 32),
                                ('sub_apikey', 'tklbam2.' + 'a' * 32 + '.' + 'e' * 43)):
            with open(os.path.join(self.path, filename), 'w') as stream:
                stream.write(value + '\n')
        self.assertEqual(['sleep 0', 'tklbam-backup --scheduled --quiet'],
                         self.run_cron('/etc/cron.daily/tklbam-backup'))
        os.unlink(self.calls)
        with open(os.path.join(self.path, 'hub-managed-daily'), 'w') as stream:
            stream.write('b' * 32 + ' managed\n')
        self.assertEqual([], self.run_cron('/etc/cron.daily/tklbam-backup'))

    def test_uninitialized_legacy_cron_does_nothing(self):
        self.assertEqual([], self.run_cron('/etc/cron.daily/tklbam-backup'))

    def test_alternate_stock_copy_keeps_legacy_scheduling(self):
        self.enable_managed()
        os.mkdir(os.path.join(self.path, 'profile'))
        for filename in ('sub_apikey', 'profile/profile_id'):
            with open(os.path.join(self.path, filename), 'w') as stream:
                stream.write('fixture\n')
        self.assertEqual(['sleep 0', 'tklbam-backup --quiet'],
                         self.run_cron('/etc/cron.weekly/tklbam-backup'))


class SinkTests(unittest.TestCase):
    def test_transient_errors_and_partial_writes_preserve_required_data(self):
        from pylib import stdtrap
        original = os.write
        writes = []
        def write(fd, data):
            writes.append(data)
            if len(writes) == 1:
                raise OSError(errno.EAGAIN, 'try again')
            if len(writes) == 2:
                raise OSError(errno.EINTR, 'interrupted')
            return 2 if len(writes) == 3 else len(data)
        try:
            os.write = write
            sink = stdtrap.Sink(123)
            sink.buffer('abcdef')
            self.assertFalse(sink.write())
            self.assertFalse(sink.write())
            self.assertFalse(sink.write())
            self.assertTrue(sink.write())
            self.assertEqual(['abcdef', 'abcdef', 'abcdef', 'cdef'], writes)
            self.assertEqual('', sink.data)
        finally:
            os.write = original

    def test_required_sink_failure_is_reported(self):
        from pylib import stdtrap
        with open('/dev/full', 'w') as stream:
            sink = stdtrap.Sink(stream)
            sink.buffer('required log output')
            self.assertRaises(OSError, sink.write)
            self.assertEqual('required log output', sink.data)

    def test_closed_optional_pipe_is_disabled(self):
        from pylib import stdtrap
        reader, writer = os.pipe()
        os.close(reader)
        try:
            sink = stdtrap.Sink(writer, optional=True)
            sink.buffer('optional display output')
            self.assertTrue(sink.write())
            self.assertTrue(sink.failed)
            sink.buffer('later output')
            self.assertEqual('', sink.data)
        finally:
            os.close(writer)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--child':
        child(sys.argv[2], sys.argv[3])
    elif len(sys.argv) > 1 and sys.argv[1] == '--scheduled-child':
        scheduled_child(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
