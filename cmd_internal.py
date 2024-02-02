#!/usr/bin/python3
#
# Copyright (c) 2010-2012 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
"""
Execute an internal command
"""
from os.path import realpath
import shlex

from cliwrapper import CliWrapper as CliWrapper_

import cmd_internals


class TklbamCliError(Exception):
    pass


class CliWrapper(CliWrapper_):
    DESCRIPTION = __doc__
    PATH = list(cmd_internals.__path__)


main = CliWrapper.main


def _split(string: str) -> list[str]:
    if '|' in string or '>' in string:
        raise TklbamCliError(f'Invalid char in string: {string}')
    elif ' ' in string:
        return shlex.split(string)
    return [string,]


def fmt_internal_command(command: str, *args: list[str] | str) -> list[str]:
    command_, *args_ = _split(command)
    for arg in args:
        if isinstance(arg, list):
            args_ = [*args_, *arg]
        elif isinstance(arg, str):
            args_ = [*args_, *_split(arg)]

    internal_command = [realpath(__file__), command_, *args_]
    return ["python3", *internal_command]


if __name__ == "__main__":
    CliWrapper.main()
