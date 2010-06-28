#!/usr/bin/python
"""
TurnKey Linux Backup and Migration
"""
import os
from cliwrapper import CliWrapper

class CliWrapper(CliWrapper):
    DESCRIPTION = __doc__
    PATH = [ os.path.dirname(__file__) ]
    COMMANDS_USAGE_ORDER = ['init',
                            '',
                            'passphrase', 'escrow',
                            '',
                            'backup', 'list', 'restore', 'restore_rollback',
                            '',
                            'internal']

if __name__ == "__main__":
    CliWrapper.main()
