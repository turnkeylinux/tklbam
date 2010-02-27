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
import sys
import getopt

from changes import Changes

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s [-options] delta|- [path ...]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def fmt_op(method, *args):
    if method is os.chown:
        path, uid, gid = args
        return "chown %d:%d %s" % (uid, gid, path)
    elif method is os.chmod:
        path, mode = args
        return "chmod %s %s" % (oct(mode), path)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'u:g:svh', 
                                       ['uid-map=', 'gid-map=', 'simulate', 'verbose'])
    except getopt.GetoptError, e:
        usage(e)

    verbose = False
    simulate = False

    uidmap = {}
    gidmap = {}

    def parse_idmap(line):
        return dict([ map(int, val.split(',', 1)) for val in line.split(':') ])

    for opt, val in opts:
        if opt in ('-u', '--uid-map'):
            uidmap = parse_idmap(val)
        elif opt in ('-g', '--gid-map'):
            gidmap = parse_idmap(val)
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

    changes = Changes.fromfile(delta, paths)
    if simulate:
        verbose = True

    for method, args in changes.fixstat(uidmap, gidmap):
        if verbose:
            print fmt_op(method, *args)

        if not simulate:
            method(*args)

if __name__=="__main__":
    main()

