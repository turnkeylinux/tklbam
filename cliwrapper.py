#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
import os
import re
import sys
import imp

from typing import Optional
from types import ModuleType

class _Commands(dict):
    @staticmethod
    def _list_commands(paths: list[str]):
        commands = set()
        for path in paths:
            for file in os.listdir(path):
                m = re.match(r'^cmd_(.*)\.py[co]?$', file)
                if not m:
                    continue
                command = m.group(1).replace("_", "-")
                commands.add(command)

        return commands

    @staticmethod
    def _get_internals_module(name: str, path: list[str]) -> ModuleType:
        modname = "cmd_" + name.replace("-", "_")
        file, pathname, description = imp.find_module(modname, path)
        return imp.load_module(modname, file, pathname, description)  # type: ignore[arg-type]
        # error: Argument 2 to "load_module" has incompatible type "IO[Any]"; expected "Optional[_FileLike]"

    def __init__(self, path: str):
        for command in self._list_commands([path]):
            self[command] = self._get_internals_module(command, [path])

class CliWrapper:
    DESCRIPTION = ""
    PATH: Optional[list[str]] = None
    COMMANDS_USAGE_ORDER: list[str] = []

    @classmethod
    def _usage(cls, commands: dict[str, str], e: Optional[str] = None) -> None:
        if e:
            print("error: " + str(e), file=sys.stderr)

        print("Usage: %s <command> [arguments]" % sys.argv[0], file=sys.stderr)
        print(cls.DESCRIPTION.strip(), file=sys.stderr)

        print("\nCommands: \n", file=sys.stderr)

        command_names = list(commands.keys())
        command_names.sort()

        maxlen = max([ len(name) for name in command_names ]) + 2
        tpl = "    %%-%ds %%s" % (maxlen)

        def shortdesc(command):
            return commands[command].__doc__.strip().split('\n')[0]

        for command in cls.COMMANDS_USAGE_ORDER:
            if command == '':
                print(file=sys.stderr)
            else:
                print(tpl % (command, shortdesc(command)), file=sys.stderr)

        for command in set(commands.keys()) - set(cls.COMMANDS_USAGE_ORDER):
                print(tpl % (command, shortdesc(command)), file=sys.stderr)

        sys.exit(1)

    @classmethod
    def main(cls) -> None:
        commands = _Commands(cls.PATH)  # type: ignore[arg-type]
        # error: Argument 1 to "_Commands" has incompatible type "None"; expected "str"

        if os.geteuid() != 0:
            cls._usage(commands, 'Must run as root, rerun with sudo')

        args = sys.argv[1:]
        if not args:
            cls._usage(commands)

        command = args[0]
        if command not in commands:
            cls._usage(commands, f"no such command: {command}")

        sys.argv = args
        commands[command].main()
