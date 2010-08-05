import os

from subprocess import *

class Error(Exception):
    pass

class Command:
    def __init__(self, opts, *args):
        if not args:
            raise Error("no arguments!")

        opts += [ ('archive-dir', '/var/cache/duplicity') ]

        opts = [ "--%s=%s" % (key, val) for key, val in opts ]
        self.command = ["duplicity"] + opts + list(args)

    def run(self, passphrase):
        os.environ['PASSPHRASE'] = passphrase
        child = Popen(self.command)
        del os.environ['PASSPHRASE']

        exitcode = child.wait()
        if exitcode != 0:
            raise Error("non-zero exitcode (%d) from backup command: %s" % (exitcode, str(self)))
        
    def __str__(self):
        return " ".join(self.command)
