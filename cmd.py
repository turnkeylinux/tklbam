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

Environment variables:

    TKLBAM_CONF         Path to TKLBAM configurations dir
                        Default: $TKLBAM_CONF

    TKLBAM_REGISTRY     Path to TKLBAM registry
                        Default: $TKLBAM_REGISTRY

"""
from os.path import *
from cliwrapper import CliWrapper

from string import Template

import backup
import registry

class CliWrapper(CliWrapper):
    DESCRIPTION = Template(__doc__).substitute(TKLBAM_CONF=backup.Conf.DEFAULT_PATH,
                                               TKLBAM_REGISTRY=registry._Registry.DEFAULT_PATH)

    PATH = [ dirname(realpath(__file__)) ]
    COMMANDS_USAGE_ORDER = ['init',
                            '',
                            'passphrase', 'escrow',
                            '',
                            'backup', 'list', 'restore', 'restore-rollback',
                            '',
                            'status', 'internal']

if __name__ == "__main__":
    CliWrapper.main()
