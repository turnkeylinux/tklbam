#!/usr/lib/tklbam-pypy2/bin/pypy
"""Exercise filesystem restore with an old archive containing Hub identity."""
import errno
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
from changes import Change, Changes
from rollback import Rollback

INSTANCE_PATHS = (
    '/var/lib/turnkey-mail',
    '/var/lib/turnkey-hub',
    '/var/lib/turnkey-onboarding',
    '/var/lib/inithooks/cache/HUB_ACCOUNT_EMAIL',
    '/var/lib/tklbam/sub_apikey',
    '/var/lib/tklbam/credentials',
    '/var/lib/tklbam/pending-profile',
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
        self.original_docker_runtime = restore.Restore.DOCKER_RUNTIME_PATH
        self.original_docker_hosts = restore.Restore.DOCKER_HOSTS_PATH
        restore.Restore.DOCKER_RUNTIME_PATH = self.path('/etc/turnkey-runtime')
        restore.Restore.DOCKER_HOSTS_PATH = self.path('/etc/hosts')
        self.original_mountinfo = restore.Restore.MOUNTINFO_PATH
        self.original_network_paths = restore.Restore.NETWORK_PATHS
        restore.Restore.MOUNTINFO_PATH = os.path.join(self.base, 'mountinfo')
        restore.Restore.NETWORK_PATHS = tuple(self.path(path) for path in self.original_network_paths)
        self.write(restore.Restore.MOUNTINFO_PATH, '')
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
        restore.Restore.DOCKER_RUNTIME_PATH = self.original_docker_runtime
        restore.Restore.DOCKER_HOSTS_PATH = self.original_docker_hosts
        restore.Restore.MOUNTINFO_PATH = self.original_mountinfo
        restore.Restore.NETWORK_PATHS = self.original_network_paths
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
            if path in ('/var/lib/turnkey-mail', '/var/lib/turnkey-hub', '/var/lib/turnkey-onboarding', '/var/lib/hubdns', '/var/lib/turnkey-docker'):
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

    def test_docker_preserves_hosts_from_old_archive_and_restores_sibling(self):
        self.write(self.path('/etc/turnkey-runtime'), 'docker\n')
        hosts = self.archived('/etc/hosts')
        ordinary = self.archived('/etc/application-setting')
        operation = self.run_restore(limits=[self.target, hosts], rollback=True)
        with open(hosts) as stream:
            self.assertEqual(stream.read(), 'destination:/etc/hosts')
        with open(ordinary) as stream:
            self.assertEqual(stream.read(), 'source:/etc/application-setting')
        self.assertFalse(os.path.exists(str(operation.rollback.paths.originals) + hosts))

    def test_docker_preserves_hosts_deletion_and_permission_changes(self):
        for operation in ('d', 's'):
            self.write(self.path('/etc/turnkey-runtime'), 'docker\n')
            hosts = self.archived('/etc/hosts', operation)
            self.run_restore()
            with open(hosts) as stream:
                self.assertEqual(stream.read(), 'destination:/etc/hosts')
            self.assertEqual(stat.S_IMODE(os.stat(hosts).st_mode), 0600)
            self.changes = []
            self.olist = []

    def test_non_docker_restores_hosts_normally(self):
        self.write(self.path('/etc/turnkey-runtime'), 'proxmox\n')
        hosts = self.archived('/etc/hosts')
        self.run_restore()
        with open(hosts) as stream:
            self.assertEqual(stream.read(), 'source:/etc/hosts')

    def test_missing_runtime_marker_restores_hosts_normally(self):
        hosts = self.archived('/etc/hosts')
        self.run_restore()
        with open(hosts) as stream:
            self.assertEqual(stream.read(), 'source:/etc/hosts')

    def test_network_mounts_are_preserved_without_a_runtime_marker(self):
        hosts = self.archived('/etc/hosts')
        hostname = self.archived('/etc/hostname', 'd')
        resolver = self.archived('/etc/resolv.conf')
        target = self.archived('/run/[resolver] config/resolv.conf', 's')
        os.unlink(resolver)
        os.symlink(target, resolver)
        ordinary = self.archived('/etc/application-setting')
        similar = self.archived('/run/r config/resolv.conf')
        self.write(restore.Restore.MOUNTINFO_PATH, ''.join(
            '10 1 0:1 / %s rw - tmpfs tmpfs rw\n' % path.replace(' ', r'\040')
            for path in (hosts, hostname, target)))

        operation = self.run_restore(rollback=True)

        for path in (hosts, hostname, target):
            with open(path) as stream:
                self.assertEqual(stream.read(), 'destination:' + path[len(self.target):])
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0600)
            self.assertFalse(os.path.exists(str(operation.rollback.paths.originals) + path))
        self.assertEqual(os.readlink(resolver), target)
        with open(ordinary) as stream:
            self.assertEqual(stream.read(), 'source:/etc/application-setting')
        with open(similar) as stream:
            self.assertEqual(stream.read(), 'source:/run/r config/resolv.conf')

    def test_runtime_mount_is_protected_through_symlinked_ancestors(self):
        target = self.path('/run/resolvconf/resolv.conf')
        resolver = self.path('/etc/resolv.conf')
        alias = self.path('/var/run')
        self.write(target, 'destination resolver')
        os.symlink(target, resolver)
        os.makedirs(os.path.dirname(alias))
        os.symlink(self.path('/run'), alias)
        self.archived('/var/run/resolvconf/resolv.conf', destination=False)
        self.archived('/var/run/resolvconf', 'd', destination=False)
        self.changes.insert(0, 'o\t%s\t%d\t%d\n' % (alias, os.getuid(), os.getgid()))
        self.olist.insert(0, alias + '\n')
        ordinary = self.archived('/srv/application/setting')
        self.write(restore.Restore.MOUNTINFO_PATH,
                   '10 1 0:1 / %s rw - tmpfs tmpfs rw\n' % target)

        operation = self.run_restore(rollback=True)

        self.assertEqual(os.readlink(alias), self.path('/run'))
        self.assertEqual(os.readlink(resolver), target)
        with open(target) as stream:
            self.assertEqual(stream.read(), 'destination resolver')
        self.assertFalse(os.path.exists(str(operation.rollback.paths.originals) + alias))
        with open(ordinary) as stream:
            self.assertEqual(stream.read(), 'source:/srv/application/setting')

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

    def test_new_hub_identity_is_preserved_for_all_restore_operations(self):
        overwritten = self.archived('/var/lib/turnkey-hub/state.json')
        deleted = self.archived('/var/lib/turnkey-hub/provision-pending', 'd')
        permissions = self.archived('/var/lib/turnkey-hub/registration.json', 's')
        source_only = self.archived('/var/lib/turnkey-hub/source-only', destination=False)
        old = self.archived('/var/lib/turnkey-mail/state.json')
        operation = self.run_restore(limits=[self.target, source_only], rollback=True)
        for path in (overwritten, deleted, permissions, old):
            with open(path) as stream:
                self.assertEqual(stream.read(), 'destination:' + path[len(self.target):])
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0600)
            self.assertFalse(os.path.exists(str(operation.rollback.paths.originals) + path))
        self.assertFalse(os.path.exists(source_only))

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


class RestoreRollbackTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix='tklbam-restore-rollback-')
        self.rollback = Rollback.create(os.path.join(self.base, 'rollback'))
        self.target = os.path.join(self.base, 'target')
        self.overlay = os.path.join(self.base, 'overlay')
        os.mkdir(self.target)

    def tearDown(self):
        shutil.rmtree(self.base)

    def write(self, path, value):
        with open(path, 'w') as stream:
            stream.write(value)

    def test_interrupted_save_rolls_back_only_saved_files(self):
        first = os.path.join(self.target, 'first')
        second = os.path.join(self.target, 'second')
        created = os.path.join(self.target, 'created')
        self.write(first, 'original first')
        os.chmod(first, 04755)
        self.write(second, 'original second')
        changes = Changes([Change.Deleted(first), Change.Deleted(second),
                           Change.Deleted(created)])
        move = self.rollback._move_to_originals
        def interrupted(path):
            if path == second:
                raise OSError('simulated move failure')
            move(path)
        self.rollback._move_to_originals = interrupted

        self.assertRaises(OSError, self.rollback.save_files, changes, self.overlay)
        self.assertFalse(os.path.exists(first))
        self.write(second, 'edited after interruption')
        self.write(created, 'created after interruption')

        Rollback(self.rollback.paths).rollback()

        for path, expected in ((first, 'original first'),
                               (second, 'edited after interruption'),
                               (created, 'created after interruption')):
            with open(path) as stream:
                self.assertEqual(stream.read(), expected)
        self.assertEqual(stat.S_IMODE(os.stat(first).st_mode), 04755)
        self.assertFalse(os.path.exists(self.rollback.paths))

    def test_cross_device_move_preserves_setid_mode(self):
        source = os.path.join(self.target, 'source')
        dest = os.path.join(self.target, 'dest')
        self.write(source, 'original data')
        os.chmod(source, 06755)
        rename = os.rename
        def cross_device(src, dst):
            if src == source:
                raise OSError(errno.EXDEV, 'simulated cross-device move')
            rename(src, dst)
        os.rename = cross_device
        try:
            self.rollback._move(source, dest)
        finally:
            os.rename = rename

        self.assertFalse(os.path.exists(source))
        self.assertEqual(stat.S_IMODE(os.stat(dest).st_mode), 06755)
        with open(dest) as stream:
            self.assertEqual(stream.read(), 'original data')

    def test_failed_rollback_keeps_originals_for_retry(self):
        path = os.path.join(self.target, 'data')
        self.write(path, 'original data')
        changes = Changes([Change.Deleted(path)])
        move = self.rollback._move_to_originals
        def interrupted(path):
            move(path)
            raise OSError('simulated interruption after moving original')
        self.rollback._move_to_originals = interrupted
        self.assertRaises(OSError, self.rollback.save_files, changes, self.overlay)
        self.write(path, 'created after interruption')

        self.assertRaises(Rollback.Error, self.rollback.rollback)
        self.assertTrue(os.path.exists(self.rollback._original_path(path)))
        with open(path) as stream:
            self.assertEqual(stream.read(), 'created after interruption')

        os.unlink(path)
        Rollback(self.rollback.paths).rollback()
        with open(path) as stream:
            self.assertEqual(stream.read(), 'original data')

    def test_incomplete_legacy_archive_is_retained(self):
        path = os.path.join(self.target, 'data')
        self.write(path, 'original data')
        Changes([Change.Deleted(path)]).tofile(self.rollback.paths.fsdelta)
        self.rollback._move_to_originals(path)

        self.assertRaises(Rollback.Error, self.rollback.rollback)

        with open(self.rollback._original_path(path)) as stream:
            self.assertEqual(stream.read(), 'original data')

    def test_completed_save_rolls_back_parent_and_child_changes(self):
        parent = os.path.join(self.target, 'parent')
        child = os.path.join(parent, 'data')
        os.mkdir(parent)
        self.write(child, 'original data')
        changes = Changes([Change.Deleted('/' + child), Change.Deleted(parent)])
        self.rollback.save_files(changes, self.overlay)
        self.write(parent, 'a file restored in place of the directory')
        accounts = os.path.join(self.base, 'accounts')
        os.mkdir(accounts)
        copy = shutil.copy
        def copy_accounts(source, dest):
            return copy(source, accounts if dest == '/etc' else dest)
        shutil.copy = copy_accounts
        try:
            self.rollback.rollback()
        finally:
            shutil.copy = copy

        with open(child) as stream:
            self.assertEqual(stream.read(), 'original data')
        self.assertFalse(os.path.exists(self.rollback.paths))


if __name__ == '__main__':
    unittest.main()
