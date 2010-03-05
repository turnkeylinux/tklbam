#!/usr/bin/python
"""Print list of new packages"""
import os
import sys
import commands

import re

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s base-selections [ selections ]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

class Error(Exception):
    pass

class DpkgSelections(set):
    @staticmethod
    def _parse(buf):
        for line in buf.strip().split('\n'):
            package, state = re.split(r'\t+', line)
            if state in ('deinstall', 'purge'):
                continue
            yield package

    @staticmethod
    def _dpkg_get_selections():
        cmd = "dpkg --get-selections"
        errno, output = commands.getstatusoutput(cmd)
        if errno:
            raise Error("command failed (%d): %s" % (errno, cmd))

        return output

    def __init__(self, arg=None):
        """If arg is not provided we get selections from dpkg.
           arg can be a filename, a string."""

        if arg:
            if os.path.exists(arg):
                buf = file(arg).read()
            else:
                buf = arg
        else:
            buf = self._dpkg_get_selections()

        set.__init__(self, self._parse(buf))

def main():
    args = sys.argv[1:]
    if len(args) not in (1, 2):
        usage()

    base_selections = DpkgSelections(args[0])
    try:
        selections = DpkgSelections(args[1])
    except:
        selections = DpkgSelections()

    for package in (selections - base_selections):
        print package
        
if __name__=="__main__":
    main()
