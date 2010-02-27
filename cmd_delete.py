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
import dirindex

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s [-options] delta|- [path ...]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def deletelist(changes):
    for change in changes:
        if change.OP != 'd':
            continue

        if not exists(change.path):
            continue

        if not islink(change.path) and isdir(change.path):
            continue

        yield change.path

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

    delta_fh = file(delta) if delta != '-' else sys.stdin
    changes = [ dirindex.Change.parse(line) 
                for line in delta_fh.readlines() ]
    
    if paths:
        pathmap = dirindex.PathMap(paths)
        changes = [ change for change in changes
                    if pathmap.is_included(change.path) ]

    if simulate:
        verbose = True

    for path in deletelist(changes):
        if verbose:
            print "rm " + path

        if not simulate:
            os.remove(path)

if __name__=="__main__":
    main()

