#!/usr/bin/python
"""
Fix ownership and permissions of files according to delta specification

Options:
    -u --uid-map=<mapspec>     Old to new UID map
    -g --gid-map=<mapspec>     Old to new GID map

    -s --simulate              Print list of fixes, don't apply them
    
    <mapspec> := <key>,<val>[:<key>,<val> ...]
"""

import os
import sys
import getopt
import dirindex

def fixstat(changes, uidmap, gidmap):
    return [ (os.chmod, ('/path/to/foo', 1234)) ]

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s [-options] delta|- [path ...]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def parse_delta(path):
    if path == '-':
        fh = sys.stdin
    else:
        fh = file(path)
    return [ dirindex.Change.parse(line) for line in fh.readlines() ]

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'u:g:sh', 
                                       ['uid-map=', 'gid-map=', 'simulate'])
    except getopt.GetoptError, e:
        usage(e)

    simulate = False
    uidmap = None
    gidmap = None
    for opt, val in opts:
        if opt in ('-u', '--uid-map'):
            uidmap = val
        elif opt in ('-g', '--gid-map'):
            gidmap = val
        elif opt in ('-s', '--simulate'):
            simulate = True
        else:
            usage()

    if len(args) < 1:
        usage()

    delta = args[0]
    paths = args[1:]

    print `(uidmap, gidmap, delta, paths, simulate)`

    def parse_map(line):
        return dict([ map(int, val.split(',', 1)) for val in line.split(':') ])

    if uidmap:
        uidmap = parse_map(uidmap)

    if gidmap:
        gidmap = parse_map(gidmap)

    changes = parse_delta(delta)
    for method, args in fixstat(changes, uidmap, gidmap):
        print method.__name__ + `args`

if __name__=="__main__":
    main()

