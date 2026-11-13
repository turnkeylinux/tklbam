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
    else:
        unittest.main()
