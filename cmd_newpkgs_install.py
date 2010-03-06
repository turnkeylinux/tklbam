#!/usr/bin/python
"""
Install list of new packages that are available in apt-cache.

Options:
    -i --input=PATH         Read a list of packages from a file (- for stdin)
    -v --verbose            Turn on verbosity
    -s --simulate           Don't execute apt-get
"""

import os
import re
import sys
import getopt
import commands

from cmd_newpkgs import DpkgSelections

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s [ -options ] [ package-name ... ]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def parse_input(inputfile):
    packages = []
    
    if inputfile == '-':
        fh = sys.stdin
    else:
        fh = file(inputfile)

    for line in fh.readlines():
        line = re.sub(r'#.*', '', line).strip()
        if not line:
            continue

        packages.append(line)

    return packages

class AptCache(set):
    class Error(Exception):
        pass

    def __init__(self, packages):
        command = "apt-cache show " + " ".join(packages)
        status, output = commands.getstatusoutput(command)
        status = os.WEXITSTATUS(status)
        if status not in (0, 100):
            raise self.Error("execution failed (%d): %s\n%s" % (status, command, output))
        
        cached = [ line.split()[1] 
                   for line in output.split("\n") if
                   line.startswith("Package: ") ]

        set.__init__(self, cached)

def installable(packages):
    selections = DpkgSelections()
    aptcache = AptCache(packages)

    installable = []
    skipped = []
    for package in set(packages):
        if package in selections:
            continue

        if package not in aptcache:
            skipped.append(package)
            continue

        installable.append(package)

    return installable, skipped

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'i:svh', 
                                       ['input=', 'simulate', 'verbose'])
    except getopt.GetoptError, e:
        usage(e)

    opt_input = None
    opt_simulate = False
    opt_verbose = False

    for opt, val in opts:
        if opt in ('-i', '--input'):
            opt_input=val

        elif opt in ('-s', '--simulate'):
            opt_simulate = True

        elif opt in ('-v', '--verbose'):
            opt_verbose = True
        else:
            usage()

    if opt_simulate:
        opt_verbose = True

    if not args and not opt_input:
        usage()

    packages = args
    if opt_input:
        packages += parse_input(opt_input)

    installing, skipping = installable(packages)
    installing.sort()
    skipping.sort()

    command = "apt-get install " + " ".join(installing)
    if opt_verbose:
        print "# SKIPPING: " + " ".join(skipping)
        print command

    if not opt_simulate:
        errno = os.system(command)
        os.exit(errno)

if __name__=="__main__":
    main()
