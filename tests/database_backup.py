#!/usr/bin/env python
"""Database export failures must prevent a successful backup."""
import os
import shutil
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'lib')))

import backup
import mysql
import pgsql
from pylib import executil
from utils import AttrDict


class DatabaseBackupTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.originals = []
        self.profile = AttrDict(path=self.root, profile_id='test')
        self.overrides = AttrDict(fs=[], mydb=[], pgdb=[])
        self.patch(mysql.MysqlService, 'is_running', lambda: False)
        self.patch(pgsql.PgsqlService, 'is_running', lambda: False)

    def tearDown(self):
        for obj, name, value in reversed(self.originals):
            setattr(obj, name, value)
        shutil.rmtree(self.root)

    def patch(self, obj, name, value):
        self.originals.append((obj, name, obj.__dict__[name]))
        if isinstance(obj, (type, types.ClassType)):
            value = staticmethod(value)
        setattr(obj, name, value)

    def create_backup(self, skip_database=False):
        return backup.Backup(self.profile, self.overrides,
                             skip_files=True, skip_packages=True,
                             skip_database=skip_database,
                             verbose=False, extras_root=self.root)

    def assert_export_aborts(self, module, service):
        self.patch(service, 'is_running', lambda: True)

        def fail(*args, **kwargs):
            raise module.Error('database export: No space left on device')

        self.patch(module, 'backup', fail)
        with self.assertRaises(module.Error) as raised:
            self.create_backup()
        self.assertIn('No space left on device', str(raised.exception))
        self.assertFalse(os.path.exists(os.path.join(self.root, 'TKLBAM')))

    def test_postgresql_failure_aborts_backup(self):
        self.assert_export_aborts(pgsql, pgsql.PgsqlService)

    def test_mysql_failure_aborts_backup(self):
        self.assert_export_aborts(mysql, mysql.MysqlService)

    def test_absent_databases_allow_file_backup(self):
        result = self.create_backup()
        self.assertTrue(os.path.isfile(result.extras_paths.backup_conf))

    def test_running_databases_are_exported(self):
        calls = []
        for module, service in [(mysql, mysql.MysqlService),
                                (pgsql, pgsql.PgsqlService)]:
            self.patch(service, 'is_running', lambda: True)
            self.patch(module, 'backup', lambda *args, **kwargs: calls.append(args[0]))
        result = self.create_backup()
        self.assertEqual(calls, [result.extras_paths.myfs, result.extras_paths.pgfs])

    def test_explicit_skip_does_not_export_running_databases(self):
        for module, service in [(mysql, mysql.MysqlService),
                                (pgsql, pgsql.PgsqlService)]:
            self.patch(service, 'is_running', lambda: True)

            def unexpected(*args, **kwargs):
                self.fail('database export requested despite skip_database')

            self.patch(module, 'backup', unexpected)
        self.create_backup(skip_database=True)


class PgDumpPipelineTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.source = os.path.join(self.root, 'source')
        os.mkdir(self.source)
        with open(os.path.join(self.source, 'toc.dat'), 'w') as stream:
            stream.write('dump fixture\n')
        self.original_su = pgsql.su
        self.original_path = os.environ['PATH']
        self.output = os.path.join(self.root, 'dump')
        os.mkdir(self.output)

    def tearDown(self):
        pgsql.su = self.original_su
        os.environ['PATH'] = self.original_path
        shutil.rmtree(self.root)

    def producer(self, status):
        # A complete tar stream followed by an exporter failure reproduces the
        # case where tar succeeds but the database exporter does not.
        pgsql.su = lambda command: '(tar c -C %s toc.dat; exit %d)' % (
            executil.mkarg(self.source), status)

    def test_success_writes_manifest_and_extracts_dump(self):
        self.producer(0)
        pgsql.dumpdb(self.output, 'example')
        with open(os.path.join(self.output, 'example', 'manifest.txt')) as stream:
            self.assertEqual(stream.read(), 'toc.dat\n')
        self.assertTrue(os.path.isfile(os.path.join(self.output, 'example', 'toc.dat')))

    def test_producer_failure_is_not_hidden_by_successful_tar(self):
        self.producer(7)
        with self.assertRaises(executil.ExecError):
            pgsql.dumpdb(self.output, 'example')
        self.assertFalse(os.path.exists(os.path.join(self.output, 'example', 'manifest.txt')))

    def test_failed_export_removes_partial_backup_and_reports_error(self):
        self.producer(7)
        original_list_databases = pgsql.list_databases
        pgsql.list_databases = lambda: ['example']
        try:
            with self.assertRaises(pgsql.Error) as raised:
                pgsql.backup(self.output)
        finally:
            pgsql.list_databases = original_list_databases
        self.assertIn('pgsql backup failed', str(raised.exception))
        self.assertIn('exitcode (7)', str(raised.exception))
        self.assertFalse(os.path.exists(self.output))

    def test_consumer_failure_aborts_dump(self):
        self.producer(0)
        bindir = os.path.join(self.root, 'bin')
        os.mkdir(bindir)
        path = os.path.join(bindir, 'tar')
        with open(path, 'w') as stream:
            stream.write('#!/bin/sh\nif [ "$1" = c ]; then exec /bin/tar "$@"; fi\nexit 9\n')
        os.chmod(path, 0755)
        os.environ['PATH'] = bindir + os.pathsep + self.original_path
        with self.assertRaises(executil.ExecError):
            pgsql.dumpdb(self.output, 'example')
        self.assertFalse(os.path.exists(os.path.join(self.output, 'example', 'manifest.txt')))


if __name__ == '__main__':
    unittest.main()
