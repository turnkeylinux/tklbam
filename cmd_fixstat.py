#!/usr/bin/python
"""
Fix ownership and permissions of files according to delta specification

Options:
    -u --uid-map=<mapspec>     Old to new UID map
    -g --gid-map=<mapspec>     Old to new GID map

    -v --verbose               Print list of fixes
    -s --simulate              Print list of fixes, don't apply them
    
    <mapspec> := <key>,<val>[:<key>,<val> ...]
"""

import sys
import getopt
import dirindex

from fixstat import fixstat, IdMap

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s [-options] delta|- [path ...]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'u:g:svh', 
                                       ['uid-map=', 'gid-map=', 'simulate', 'verbose'])
    except getopt.GetoptError, e:
        usage(e)

    verbose = False
    simulate = False

    uidmap = IdMap()
    gidmap = IdMap()
    for opt, val in opts:
        if opt in ('-u', '--uid-map'):
            uidmap = IdMap.fromline(val)
        elif opt in ('-g', '--gid-map'):
            gidmap = IdMap.fromline(val)
        elif opt in ('-s', '--simulate'):
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

    for method, args in fixstat(changes, uidmap, gidmap):
        if verbose:
            print method.__name__ + `args`

        if not simulate:
            method(*args)

if __name__=="__main__":
    main()

