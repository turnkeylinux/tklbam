#!/usr/bin/env python
"""Verify real profile signatures without executing the LDAP fixture hook."""
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, 'tests', 'fixtures', 'profile-hooks')
KEYRING = os.path.join(ROOT, 'share', 'profile-keyring.gpg')

# Isolate hook dispatch from registry initialization and appliance dependencies.
class Registry(object):
    profile = None

registry = Registry()
registry_module = types.ModuleType('registry')
registry_module.registry = registry
sys.modules['registry'] = registry_module
conf_module = types.ModuleType('conf')
class Conf(object):
    DEFAULT_PATH = '/etc/tklbam'
conf_module.Conf = Conf
sys.modules['conf'] = conf_module
pylib = types.ModuleType('pylib')
class ExecError(Exception):
    exitcode = 7
class Executil(object):
    ExecError = ExecError
    calls = []
    @classmethod
    def system(cls, path, *args):
        cls.calls.append((path, args))
pylib.executil = Executil
sys.modules['pylib'] = pylib
if sys.version_info[0] == 2:
    import imp
    hooks = imp.load_source('profile_hooks_under_test', os.path.join(ROOT, 'lib', 'hooks.py'))
else:
    import importlib.util
    spec = importlib.util.spec_from_file_location('profile_hooks_under_test', os.path.join(ROOT, 'lib', 'hooks.py'))
    hooks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hooks)

class ProfileHooksTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix='tklbam-profile-hooks-')
        self.profile = os.path.join(self.base, 'profile')
        self.local = os.path.join(self.base, 'local')
        os.makedirs(os.path.join(self.profile, 'hooks.d'))
        os.makedirs(self.local)
        registry.profile = self.profile
        Executil.calls = []
        self.dispatch = hooks.Hooks('backup')
        self.dispatch.LOCAL_HOOKS = self.local
        self.dispatch.PROFILE_KEYRING = KEYRING
        self.original_popen = hooks.subprocess.Popen

    def tearDown(self):
        hooks.subprocess.Popen = self.original_popen
        registry.profile = None
        shutil.rmtree(self.base)

    def signed_hook(self, name='migrate-slapd'):
        target = os.path.join(self.profile, 'hooks.d', name)
        for suffix in ('', '.sig'):
            shutil.copyfile(os.path.join(FIXTURES, 'migrate-slapd' + suffix), target + suffix)
        os.chmod(target, 0o755)
        return target

    def local_hook(self):
        target = os.path.join(self.local, 'local-hook')
        with open(target, 'w') as stream:
            stream.write('#!/bin/sh\nexit 0\n')
        os.chmod(target, 0o755)
        return target

    def assert_stage_failure(self, text):
        with self.assertRaises(hooks.HookError) as error:
            self.dispatch.pre()
        self.assertIn(text, str(error.exception))
        self.assertEqual(Executil.calls, [])

    def test_actual_official_legacy_hook_validates_once_before_local_then_profile(self):
        profile = self.signed_hook()
        local = self.local_hook()
        commands = []
        def recording_popen(args, **kwargs):
            commands.append(args)
            return self.original_popen(args, **kwargs)
        hooks.subprocess.Popen = recording_popen
        self.dispatch.pre()
        self.assertEqual(Executil.calls, [(local, ('backup', 'pre')), (profile, ('backup', 'pre'))])
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][-3:], ['--', profile + '.sig', profile])
        self.assertIn('--homedir', commands[0])
        self.assertEqual(commands[0][commands[0].index('--keyring') + 1], KEYRING)

    def test_missing_ring_fails_before_local_effects(self):
        self.signed_hook()
        self.local_hook()
        self.dispatch.PROFILE_KEYRING = os.path.join(self.base, 'missing.gpg')
        self.assert_stage_failure('keyring is missing or unreadable')

    def test_unavailable_verifier_fails_before_local_effects(self):
        self.signed_hook()
        self.local_hook()
        def missing_popen(*args, **kwargs):
            raise OSError('gpgv unavailable')
        hooks.subprocess.Popen = missing_popen
        self.assert_stage_failure('reinstall tklbam and gpgv')

    def test_missing_signature_fails_before_local_effects(self):
        profile = self.signed_hook()
        os.unlink(profile + '.sig')
        self.local_hook()
        self.assert_stage_failure('Missing signature')

    def test_wrong_packaged_key_does_not_authorize_official_hook(self):
        self.signed_hook()
        self.local_hook()
        self.dispatch.PROFILE_KEYRING = os.path.join(FIXTURES, 'unrelated-keyring.gpg')
        self.assert_stage_failure('Signature verification failed')

    def test_tampered_hook_fails_before_local_effects(self):
        profile = self.signed_hook()
        with open(profile, 'a') as stream:
            stream.write('\n# changed after signature\n')
        self.local_hook()
        self.assert_stage_failure('Signature verification failed')

    def test_later_invalid_profile_hook_prevents_all_effects(self):
        self.signed_hook('first-valid')
        invalid = self.signed_hook('later-invalid')
        os.unlink(invalid + '.sig')
        self.local_hook()
        self.assert_stage_failure('Missing signature')

    def test_root_default_keyring_cannot_add_profile_trust(self):
        self.signed_hook()
        ambient = os.path.join(self.base, 'ambient')
        os.makedirs(ambient)
        shutil.copyfile(KEYRING, os.path.join(ambient, 'trustedkeys.gpg'))
        old = os.environ.get('GNUPGHOME')
        os.environ['GNUPGHOME'] = ambient
        self.dispatch.PROFILE_KEYRING = os.path.join(FIXTURES, 'unrelated-keyring.gpg')
        try:
            self.assert_stage_failure('Signature verification failed')
        finally:
            if old is None:
                del os.environ['GNUPGHOME']
            else:
                os.environ['GNUPGHOME'] = old

    def test_no_profile_hooks_requires_no_keyring_or_gpg_and_preserves_local_contract(self):
        local = self.local_hook()
        self.dispatch.PROFILE_KEYRING = '/does-not-exist'
        def forbidden_popen(*args, **kwargs):
            raise AssertionError('No GPG work for a profile without executable hooks')
        hooks.subprocess.Popen = forbidden_popen
        self.dispatch.pre()
        self.assertEqual(Executil.calls, [(local, ('backup', 'pre'))])
        registry.profile = None
        self.dispatch.post()
        self.assertEqual(Executil.calls[-1], (local, ('backup', 'post')))

    def test_unexecutable_unsigned_profile_file_is_not_a_hook(self):
        path = os.path.join(self.profile, 'hooks.d', 'notes')
        with open(path, 'w') as stream:
            stream.write('not a hook')
        os.chmod(path, 0o644)
        self.dispatch.PROFILE_KEYRING = '/does-not-exist'
        self.dispatch.pre()
        self.assertEqual(Executil.calls, [])

    def test_executable_directory_is_not_a_hook(self):
        os.mkdir(os.path.join(self.profile, 'hooks.d', 'directory'))
        self.dispatch.PROFILE_KEYRING = '/does-not-exist'
        self.dispatch.pre()
        self.assertEqual(Executil.calls, [])

    def test_failed_inspect_restores_working_directory(self):
        self.signed_hook()
        self.dispatch.PROFILE_KEYRING = '/does-not-exist'
        current = os.getcwd()
        with self.assertRaises(hooks.HookError):
            self.dispatch.inspect(self.base)
        self.assertEqual(os.getcwd(), current)
        self.assertEqual(Executil.calls, [])

    def test_inspect_and_restore_stages_validate_and_dispatch(self):
        path = self.signed_hook()
        self.dispatch.name = 'restore'
        current = os.getcwd()
        self.dispatch.inspect(self.base)
        self.assertEqual(os.getcwd(), current)
        self.dispatch.post()
        self.assertEqual(Executil.calls, [(path, ('restore', 'inspect')), (path, ('restore', 'post'))])

if __name__ == '__main__':
    unittest.main()
