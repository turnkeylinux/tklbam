#!/usr/lib/tklbam-pypy2/bin/pypy
"""Exercise filesystem restore with an old archive containing Hub identity."""
import os
import re
import pipes
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'lib'), '/usr/lib/tklbam/deps/lib']
import restore

INSTANCE_PATHS = (
    '/var/lib/turnkey-mail',
    '/var/lib/turnkey-onboarding',
    '/var/lib/inithooks/cache/HUB_ACCOUNT_EMAIL',
    '/var/lib/tklbam/sub_apikey',
    '/var/lib/tklbam/credentials',
    '/var/lib/hubdns',
    '/etc/turnkey-runtime',
    '/etc/turnkey-build.json',
    '/var/lib/turnkey-docker',
)


class RestoreIdentityTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix='tklbam-restore-identity-')
        self.target = os.path.join(self.base, 'target')
        self.archive = os.path.join(self.base, 'archive')
        os.makedirs(os.path.join(self.archive, 'TKLBAM', 'etc'))
        for name in ('passwd', 'group'):
            shutil.copyfile('/etc/' + name, os.path.join(self.archive, 'TKLBAM', 'etc', name))
        self.original_paths = getattr(restore.Restore, 'INSTANCE_PATHS', None)
        restore.Restore.INSTANCE_PATHS = tuple(self.path(path) for path in INSTANCE_PATHS)
        self.original_pattern = restore.Restore.INSTANCE_FILE_PATTERN
        restore.Restore.INSTANCE_FILE_PATTERN = '^' + re.escape(self.target) + self.original_pattern[1:]
        self.original_file_directory = getattr(restore.Restore, 'INSTANCE_FILE_DIRECTORY', None)
        restore.Restore.INSTANCE_FILE_DIRECTORY = self.path('/etc/postfix')
        self.original_open = getattr(restore, 'open', None)
        def target_open(path, *args):
            if path in ('/etc/passwd', '/etc/group'):
                path = self.path(path)
            return open(path, *args)
        restore.open = target_open
        for name in ('passwd', 'group'):
            self.write(self.path('/etc/' + name), '')
        self.changes = []
        self.olist = []

    def tearDown(self):
        if self.original_paths is None:
            del restore.Restore.INSTANCE_PATHS
        else:
            restore.Restore.INSTANCE_PATHS = self.original_paths
        restore.Restore.INSTANCE_FILE_PATTERN = self.original_pattern
        if self.original_file_directory is None:
            del restore.Restore.INSTANCE_FILE_DIRECTORY
        else:
            restore.Restore.INSTANCE_FILE_DIRECTORY = self.original_file_directory
        if self.original_open is None:
            del restore.open
        else:
            restore.open = self.original_open
        shutil.rmtree(self.base)

    def path(self, path):
        return self.target + path

    def write(self, path, value):
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path, 'w') as stream:
            stream.write(value)

    def archived(self, relative, op='o', destination=True):
        path = self.path(relative)
        if destination:
            self.write(path, 'destination:' + relative)
            os.chmod(path, 0600)
        if op == 'o':
            self.write(self.archive + path, 'source:' + relative)
            self.changes.append('o\t%s\t%d\t%d\n' % (path, os.getuid(), os.getgid()))
            self.olist.append(path + '\n')
        elif op == 'd':
            self.changes.append('d\t%s\n' % path)
        else:
            self.changes.append('s\t%s\t%d\t%d\t0100644\n' % (path, os.getuid(), os.getgid()))
        return path

    def run_restore(self, limits=[], rollback=False, simulate=False):
        self.write(os.path.join(self.archive, 'TKLBAM', 'fsdelta'), ''.join(self.changes))
        self.write(os.path.join(self.archive, 'TKLBAM', 'fsdelta-olist'), ''.join(self.olist))
        operation = restore.Restore(self.archive, limits=limits, rollback=False, simulate=simulate)
        if rollback:
            operation.rollback = restore.Rollback.create(os.path.join(self.base, 'rollback'))
        operation.files()
        return operation

    def test_old_archive_preserves_identity_and_restores_ordinary_data(self):
        protected = []
        for path in INSTANCE_PATHS:
            if path in ('/var/lib/turnkey-mail', '/var/lib/turnkey-onboarding', '/var/lib/hubdns', '/var/lib/turnkey-docker'):
                path += '/state'
            protected.append(self.archived(path))
        ordinary = self.archived('/srv/application/data')
        crypto = self.archived('/var/lib/tklbam/key')
        profile = self.archived('/var/lib/tklbam/profile/profile_id')
        self.run_restore()
        for path in protected:
            with open(path) as stream:
                self.assertEqual(stream.read(), 'destination:' + path[len(self.target):])
        for path in (ordinary, crypto, profile):
            with open(path) as stream:
                self.assertEqual(stream.read(), 'source:' + path[len(self.target):])

    def test_builtin_paths_cover_hub_identity(self):
        self.assertEqual(self.original_paths, INSTANCE_PATHS)

    def test_generated_smtp_files_are_protected_but_user_mail_config_restores(self):
        protected = []
        for suffix in ('sasl', 'sasl.db', 'sender', 'headers'):
            path = '/etc/postfix/turnkey-mail-0123456789abcdef.' + suffix
            protected.append(self.archived(path))
        deleted = self.archived('/etc/postfix/turnkey-mail-aaaaaaaaaaaaaaaa.sasl', 'd')
        permissions = self.archived('/etc/postfix/turnkey-mail-bbbbbbbbbbbbbbbb.sasl.db', 's')
        source_only = self.archived('/etc/postfix/turnkey-mail-cccccccccccccccc.sasl', destination=False)
        ordinary = [self.archived('/etc/postfix/main.cf'),
                    self.archived('/etc/postfix/turnkey-mail-custom.sasl'),
                    self.archived('/etc/postfix/turnkey-mail-0123456789abcdef.sasl.backup')]
        self.run_restore()
        for path in protected + [deleted]:
            with open(path) as stream:
                self.assertEqual(stream.read(), 'destination:' + path[len(self.target):])
        self.assertEqual(stat.S_IMODE(os.stat(permissions).st_mode), 0600)
        self.assertFalse(os.path.exists(source_only))
        for path in ordinary:
            with open(path) as stream:
                self.assertEqual(stream.read(), 'source:' + path[len(self.target):])

    def test_identity_deletions_permissions_and_explicit_includes_are_filtered(self):
        deleted = self.archived('/var/lib/turnkey-mail/deleted', 'd')
        permissions = self.archived('/var/lib/turnkey-onboarding/permissions', 's')
        missing = self.archived('/var/lib/hubdns/source-only', destination=False)
        ordinary = self.archived('/srv/application/removed', 'd')
        self.run_restore(limits=[self.target, missing])
        self.assertTrue(os.path.exists(deleted))
        self.assertEqual(stat.S_IMODE(os.stat(permissions).st_mode), 0600)
        self.assertFalse(os.path.exists(missing))
        self.assertFalse(os.path.exists(ordinary))

    def test_rollback_never_moves_destination_identity(self):
        protected = self.archived('/var/lib/tklbam/sub_apikey')
        ordinary = self.archived('/srv/application/data')
        operation = self.run_restore(rollback=True)
        with open(protected) as stream:
            self.assertTrue(stream.read().startswith('destination:'))
        self.assertFalse(os.path.exists(str(operation.rollback.paths.originals) + protected))
        self.assertTrue(os.path.exists(str(operation.rollback.paths.originals) + ordinary))

    def test_ancestor_deletion_cannot_move_identity_into_rollback(self):
        email = self.archived('/var/lib/inithooks/cache/HUB_ACCOUNT_EMAIL')
        ordinary = self.archived('/var/lib/inithooks/cache/application-setting')
        ancestor = self.path('/var/lib/inithooks/cache')
        self.changes.insert(0, 'd\t%s\n' % ancestor)
        operation = self.run_restore(rollback=True)
        with open(email) as stream:
            self.assertEqual(stream.read(), 'destination:/var/lib/inithooks/cache/HUB_ACCOUNT_EMAIL')
        with open(ordinary) as stream:
            self.assertEqual(stream.read(), 'source:/var/lib/inithooks/cache/application-setting')
        self.assertFalse(os.path.exists(str(operation.rollback.paths.originals) + email))

    def test_ancestor_overlay_and_metadata_preserve_identity_and_restore_sibling(self):
        email = self.archived('/var/lib/inithooks/cache/HUB_ACCOUNT_EMAIL')
        ordinary = self.archived('/var/lib/inithooks/cache/application-setting')
        ancestor = self.path('/var/lib/inithooks/cache')
        os.chmod(ancestor, 0700)
        self.changes += ['o\t%s\t%d\t%d\n' % (ancestor, os.getuid(), os.getgid()),
                         's\t%s\t%d\t%d\t040777\n' % (ancestor, os.getuid(), os.getgid())]
        self.olist.insert(0, ancestor + '\n')
        self.run_restore()
        with open(email) as stream:
            self.assertEqual(stream.read(), 'destination:/var/lib/inithooks/cache/HUB_ACCOUNT_EMAIL')
        self.assertEqual(stat.S_IMODE(os.stat(ancestor).st_mode), 0700)
        with open(ordinary) as stream:
            self.assertEqual(stream.read(), 'source:/var/lib/inithooks/cache/application-setting')

    def test_ancestor_replacement_cannot_move_identity_into_rollback(self):
        email = self.archived('/var/lib/inithooks/cache/HUB_ACCOUNT_EMAIL')
        ancestor = self.path('/var/lib/inithooks/cache')
        shutil.rmtree(self.archive + ancestor)
        self.write(self.archive + ancestor, 'source replacement file')
        self.changes = ['o\t%s\t%d\t%d\n' % (ancestor, os.getuid(), os.getgid())]
        self.olist = [ancestor + '\n']
        self.run_restore(rollback=True)
        with open(email) as stream:
            self.assertEqual(stream.read(), 'destination:/var/lib/inithooks/cache/HUB_ACCOUNT_EMAIL')

    def test_aliases_cannot_overlay_delete_or_change_identity_permissions(self):
        overwritten = self.archived('/var/lib/../lib/turnkey-mail/overwritten')
        deleted = self.archived('/var/lib/../lib/turnkey-mail/deleted', 'd')
        permissions = self.archived('/var/lib/../lib/turnkey-mail/permissions', 's')
        self.run_restore()
        for path in (overwritten, deleted):
            with open(path) as stream:
                self.assertEqual(stream.read(), 'destination:' + path[len(self.target):])
        self.assertEqual(stat.S_IMODE(os.stat(permissions).st_mode), 0600)

    def test_postfix_ancestor_metadata_preserves_maps_and_restores_main_cf(self):
        credentials = self.archived('/etc/postfix/turnkey-mail-0123456789abcdef.sasl')
        main = self.archived('/etc/postfix/main.cf')
        ancestor = self.path('/etc/postfix')
        os.chmod(ancestor, 0700)
        self.changes.append('s\t%s\t%d\t%d\t040777\n' % (ancestor, os.getuid(), os.getgid()))
        self.run_restore()
        self.assertEqual(stat.S_IMODE(os.stat(ancestor).st_mode), 0700)
        with open(credentials) as stream:
            self.assertEqual(stream.read(), 'destination:/etc/postfix/turnkey-mail-0123456789abcdef.sasl')
        with open(main) as stream:
            self.assertEqual(stream.read(), 'source:/etc/postfix/main.cf')

    def test_simulation_does_not_mutate_ancestor_or_aliased_identity(self):
        email = self.archived('/var/lib/inithooks/cache/HUB_ACCOUNT_EMAIL')
        alias = self.archived('/var/lib/../lib/turnkey-mail/state.json', 'd')
        ancestor = self.path('/var/lib/inithooks/cache')
        os.chmod(ancestor, 0700)
        self.changes += ['d\t%s\n' % ancestor,
                         's\t%s\t%d\t%d\t040777\n' % (ancestor, os.getuid(), os.getgid())]
        self.run_restore(simulate=True)
        self.assertEqual(stat.S_IMODE(os.stat(ancestor).st_mode), 0700)
        for path in (email, alias):
            with open(path) as stream:
                self.assertEqual(stream.read(), 'destination:' + path[len(self.target):])

    def test_simulation_preserves_all_bytes(self):
        protected = self.archived('/var/lib/tklbam/sub_apikey')
        ordinary = self.archived('/srv/application/data')
        self.run_restore(simulate=True)
        for path in (protected, ordinary):
            with open(path) as stream:
                self.assertTrue(stream.read().startswith('destination:'))

    def test_cli_simulation_signal_overrides_environment_before_every_hook(self):
        hooks = os.path.join(self.base, 'hooks')
        os.mkdir(hooks)
        events = os.path.join(self.base, 'hook-events')
        configuration = os.path.join(self.base, 'destination-configuration')
        hook = os.path.join(hooks, 'observe-restore')
        self.write(hook, '#!/bin/sh\n'
                   'printf "%s:%s:%s\\n" "$1" "$2" "$TKLBAM_RESTORE_SIMULATE" >> ' + pipes.quote(events) + '\n'
                   'if [ "$1:$2:$TKLBAM_RESTORE_SIMULATE" = restore:post:no ]; then\n'
                   '  printf reconciled > ' + pipes.quote(configuration) + '\nfi\n')
        os.chmod(hook, 0700)
        self.write(os.path.join(self.archive, 'TKLBAM', 'fsdelta'), '')
        self.write(os.path.join(self.archive, 'TKLBAM', 'fsdelta-olist'), '')
        # Load the checkout entrypoint without its installed-library path reset.
        command = ('import sys, types; sys.path[:0] = %r; '
                   'sys.modules["_init_sys_path"] = types.ModuleType("_init_sys_path"); '
                   'import cmd_restore; cmd_restore.main()') % [os.path.join(ROOT, 'lib'), '/usr/lib/tklbam/deps/lib']
        env = os.environ.copy()
        env.update(TKLBAM_REGISTRY=os.path.join(self.base, 'registry'),
                   TKLBAM_CONF=os.path.join(self.base, 'conf'), TKLBAM_HOOKS=hooks)
        for simulate in (True, False):
            self.write(events, '')
            self.write(configuration, 'destination configuration')
            env['TKLBAM_RESTORE_SIMULATE'] = 'no' if simulate else 'yes'
            args = [sys.executable, '-c', command, self.archive, '--skip-files',
                    '--skip-database', '--skip-packages', '--no-rollback',
                    '--logfile=' + os.path.join(self.base, 'restore.log')]
            if simulate:
                args.append('--simulate')
            subprocess.check_call(args, env=env)
            signal = 'yes' if simulate else 'no'
            with open(events) as stream:
                self.assertEqual(stream.read().splitlines(),
                                 ['restore:%s:%s' % (stage, signal) for stage in ('pre', 'inspect', 'post')])
            with open(configuration) as stream:
                self.assertEqual(stream.read(), 'destination configuration' if simulate else 'reconciled')


if __name__ == '__main__':
    unittest.main()
