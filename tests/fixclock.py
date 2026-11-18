#!/usr/bin/python3
"""Check clock handling before TKLBAM operations."""
import contextlib
import io
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch

HOOK = Path(__file__).resolve().parents[1] / 'contrib/fixclock-hook'


class FixclockTest(unittest.TestCase):
    def test_container_skips_clock_update_silently(self):
        for op in ('restore', 'backup'):
            with self.subTest(op=op):
                stdout, stderr = io.StringIO(), io.StringIO()
                detected = subprocess.CompletedProcess([], 0, 'podman\n', '')
                with patch.object(sys, 'argv', [str(HOOK), op, 'pre']), \
                     patch('shutil.which', return_value='/usr/bin/test'), \
                     patch('subprocess.run', return_value=detected) as run, \
                     contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    runpy.run_path(str(HOOK), run_name='__main__')
                self.assertEqual(run.call_count, 1)
                self.assertEqual(stdout.getvalue(), '')
                self.assertEqual(stderr.getvalue(), '')

    def test_clock_failure_on_host_is_fatal(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        results = [subprocess.CompletedProcess([], 1, '', ''),
                   subprocess.CompletedProcess([], 1, '', 'clock error')]
        with patch.object(sys, 'argv', [str(HOOK), 'restore', 'pre']), \
             patch('shutil.which', return_value='/usr/bin/test'), \
             patch('subprocess.run', side_effect=results), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as exc:
                runpy.run_path(str(HOOK), run_name='__main__')
        self.assertEqual(exc.exception.code, 1)
        self.assertIn('FIXCLOCK HOOK FAILED', stderr.getvalue())
        self.assertIn('clock error', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
