#!/usr/bin/python
# 
# Copyright (c) 2010 Liraz Siri <liraz@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
# 
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
"""
TurnKey Linux Backup and Migration
"""
from os.path import *
from cliwrapper import CliWrapper

class CliWrapper(CliWrapper):
    DESCRIPTION = __doc__
    PATH = [ dirname(realpath(__file__)) ]
    
    COMMANDS_USAGE_ORDER = ['init',
                            '',
                            'passphrase', 'escrow',
                            '',
                            'backup', 'list', 'restore', 'restore_rollback']

if __name__ == "__main__":
    CliWrapper.main()
