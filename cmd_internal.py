#!/usr/bin/python
"""
Execute an internal command
"""
import os
import re
import sys
import imp

class _InternalCommands(dict):
    @staticmethod
    def _list_commands(paths):
        commands = set()
        for path in paths:
            for file in os.listdir(path):
                m = re.match(r'^cmd_(.*)\.py[co]?$', file)
                if not m:
                    continue
                command = m.group(1)
                commands.add(command)

        return commands

    @staticmethod
    def _get_internals_module(name, module_path):
        modname = "cmd_" + name
        args = imp.find_module(modname, module_path)
        return imp.load_module(modname, *args)

    def __init__(self):
        import cmd_internals as m

        for command in self._list_commands(m.__path__):
            self[command] = self._get_internals_module(command, m.__path__)

COMMANDS = _InternalCommands()

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s <command> [arguments]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()

    print >> sys.stderr, "\nCommands: \n"

    command_names = COMMANDS.keys()
    command_names.sort()

    for command in command_names:
        command_shortdesc = COMMANDS[command].__doc__.strip().split('\n')[0]
        print >> sys.stderr, "    %-16s %s" % (command, command_shortdesc)

    sys.exit(1)

def main():
    args = sys.argv[1:]
    if not args:
        usage()

    command = args[0]
    if command not in COMMANDS:
        usage("no such command")

    sys.argv = args
    COMMANDS[command].main()

if __name__ == "__main__":
    main()
