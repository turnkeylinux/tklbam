#!/usr/bin/python
"""
Delete files according to delta

Options:
    -v --verbose               Print list of fixes
    -s --simulate              Print list of fixes, don't apply them
"""

import os
from os.path import *

import sys
import getopt
from changes import Changes

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [-options] delta|- [path ...]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'svh', 
                                       ['simulate', 'verbose'])
    except getopt.GetoptError, e:
        usage(e)

    simulate = False
    verbose = False
    for opt, val in opts:
        if opt in ('-s', '--simulate'):
            simulate = True
        elif opt in ('-v', '--verbose'):
            verbose = True
        else:
            usage()

    if len(args) < 1:
        usage()

    delta = args[0]
    paths = args[1:]

    changes = Changes.fromfile(delta, paths)
    if simulate:
        verbose = True

    for op in changes.deleted():
        if verbose:
            print op

        if not simulate:
            op()

if __name__=="__main__":
    main()

