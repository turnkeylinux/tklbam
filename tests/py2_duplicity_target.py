#!/usr/bin/env python

import os
import sys
import unittest

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO


sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "lib")))

from py2_duplicity import Target


class TargetTest(unittest.TestCase):
    def assert_target(self, source, expected_region, expected_address):
        stdout = sys.stdout
        output = StringIO()
        try:
            sys.stdout = output
            target = Target(source, None, None)
        finally:
            sys.stdout = stdout

        self.assertEqual(target.region, expected_region)
        self.assertEqual(target.address, expected_address)
        self.assertEqual(output.getvalue(), "")

    def test_legacy_default_s3_endpoint(self):
        self.assert_target(
            "s3://s3.amazonaws.com/tklbam-us-east-1-example/prefix",
            "us-east-1",
            "s3://tklbam-us-east-1-example/prefix")

    def test_regional_s3_endpoints(self):
        cases = (
            ("s3-eu-west-1.amazonaws.com", "eu-west-1"),
            ("s3.eu-central-1.amazonaws.com", "eu-central-1"),
            ("s3.dualstack.ap-southeast-2.amazonaws.com", "ap-southeast-2"),
        )
        for endpoint, region in cases:
            self.assert_target(
                "s3://%s/tklbam-example/prefix" % endpoint,
                region,
                "s3://tklbam-example/prefix")

    def test_non_s3_targets(self):
        for address in (
                "file:///var/backups/example",
                "rsync://backup.example/path",
                "ssh://backup.example/path",
                "ftp://backup.example/path"):
            self.assert_target(address, "", address)


if __name__ == "__main__":
    unittest.main()
