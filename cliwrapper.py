import os
import re
import sys
import imp

class _Commands(dict):
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
    def _get_internals_module(name, path):
        modname = "cmd_" + name
        args = imp.find_module(modname, path)
        return imp.load_module(modname, *args)

    def __init__(self, path):
        for command in self._list_commands(path):
            self[command] = self._get_internals_module(command, path)

class CliWrapper:
    DESCRIPTION = ""
    PATH = None
    COMMANDS_USAGE_ORDER = []

    @classmethod
    def _usage(cls, commands, e=None):
        if e:
            print >> sys.stderr, "error: " + str(e)

        print >> sys.stderr, "Syntax: %s <command> [arguments]" % sys.argv[0]
        print >> sys.stderr, cls.DESCRIPTION.strip()

        print >> sys.stderr, "\nCommands: \n"

        command_names = commands.keys()
        command_names.sort()

        maxlen = max([ len(name) for name in command_names ]) + 2
        tpl = "    %%-%ds %%s" % (maxlen)

        def shortdesc(command):
            return commands[command].__doc__.strip().split('\n')[0]

        for command in cls.COMMANDS_USAGE_ORDER:
            if command == '':
                print >> sys.stderr
            else:
                print >> sys.stderr, tpl % (command, shortdesc(command))

        for command in set(commands.keys()) - set(cls.COMMANDS_USAGE_ORDER):
                print >> sys.stderr, tpl % (command, shortdesc(command))

        sys.exit(1)

    @classmethod
    def main(cls):
        commands = _Commands(cls.PATH)

        args = sys.argv[1:]
        if not args:
            cls._usage(commands)

        command = args[0]
        if command not in commands:
            cls._usage(commands, "no such command")

        sys.argv = args
        commands[command].main()
