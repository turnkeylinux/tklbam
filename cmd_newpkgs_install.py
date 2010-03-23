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

from pkgman import Installer

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

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

    installer = Installer(packages)

    if opt_verbose:
        if installer.skipping:
            print "# SKIPPING: " + " ".join(installer.skipping)

        if installer.command:
            print installer.command

    if not opt_simulate:
        errno = installer(interactive=False)
        if errno is not None:
            os.exit(errno)

if __name__=="__main__":
    main()
