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

import os
from os.path import *

import sys
import getopt
import dirindex

class IdMap(dict):
    """
    Implements mapping of ids with transparent fallback.
    If no mapping exists, the original id is returned.
    """
    @classmethod
    def fromline(cls, line):
        d = ([ map(int, val.split(',', 1)) for val in line.split(':') ])
        return cls(d)

    def __getitem__(self, key):
        if key in self:
            return dict.__getitem__(self, key)
        return key

def fixstat(changes, uidmap, gidmap):
    for change in changes:
        if not exists(change.path):
            continue

        if change.OP == 'd':
            continue
        
        if change.OP == 'o' and \
           (change.uid == 0 or change.uid not in uidmap) and \
           (change.gid == 0 or change.gid not in gidmap):
            continue

        st = os.lstat(change.path)
        if change.OP in ('s', 'o'):
            if st.st_uid != uidmap[change.uid] or \
               st.st_gid != gidmap[change.gid]:
                yield os.chown, (change.path, 
                                 uidmap[change.uid], gidmap[change.gid])

        if change.OP == 's':
            if st.st_mode != change.mode:
                yield os.chmod, (change.path, change.mode)

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

    changes = parse_delta(delta)
    
    if paths:
        pathmap = dirindex.PathMap(paths)
        changes = [ change for change in parse_delta(delta) 
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

