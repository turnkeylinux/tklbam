#!/usr/bin/python3
#
# Copyright (c) 2010-2012 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023, 2024 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.

"""
TurnKey GNU/Linux Backup and Migration

Environment variables:

    TKLBAM_CONF         Path to TKLBAM configurations dir
                        Default: $TKLBAM_CONF

    TKLBAM_REGISTRY     Path to TKLBAM registry
                        Default: $TKLBAM_REGISTRY

"""
from os.path import realpath, dirname
from cliwrapper import CliWrapper as CliWrapper_

from string import Template
from typing import Iterable

import conf
import registry


class CliWrapper(CliWrapper_):
    assert __doc__ is not None
    DESCRIPTION = Template(__doc__).substitute(
            TKLBAM_CONF=conf.Conf.DEFAULT_PATH,
            TKLBAM_REGISTRY=registry._Registry.DEFAULT_PATH)

    PATH: Iterable[str] | list[str] = [dirname(realpath(__file__))]
    COMMANDS_USAGE_ORDER = ['init',
                            '',
                            'passphrase', 'escrow',
                            '',
                            'backup', 'list', 'restore', 'restore-rollback',
                            '',
                            'status', 'internal']


if __name__ == "__main__":
    CliWrapper.main()
