"""Scheduled backups send failures by default and success reports only by choice."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] / 'contrib/cron.sh').read_text()

class ScheduledMailTests(unittest.TestCase):
    def test_success_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'profile').mkdir()
            (root / 'profile/profile_id').write_text('profile')
            (root / 'sub_apikey').write_text('key')
            command = root / 'tklbam-backup'
            command.write_text('#!/bin/sh\necho summary\nexit "$STATUS"\n')
            command.chmod(0o755)
            flag = root / 'email-success'
            script = SCRIPT.replace('/etc/tklbam/email-success', str(flag))
            env = dict(os.environ, TKLBAM_REGISTRY=directory, JITTER='0', PATH=directory + ':' + os.environ['PATH'])
            def run(status):
                return subprocess.run(['bash', '-c', script, '/etc/cron.weekly/tklbam-backup'],
                                      env=dict(env, STATUS=str(status)), capture_output=True, text=True)
            result = run(0)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
            result = run(7)
            self.assertEqual(result.returncode, 7)
            self.assertIn('Scheduled backup failed', result.stderr)
            self.assertIn('summary', result.stderr)
            flag.touch()
            result = run(0)
            self.assertEqual(result.stdout, 'summary\n')
            self.assertEqual(result.returncode, 0)
            result = run(7)
            self.assertEqual(result.returncode, 7)
            self.assertIn('Scheduled backup failed', result.stderr)

if __name__ == '__main__':
    unittest.main()
