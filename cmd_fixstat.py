#!/usr/bin/python
"""
Fix ownership and permissions of files according to delta specification

Options:
    -u --uid-map=<mapspec>     Old to new UID map
    -g --gid-map=<mapspec>     Old to new GID map
    
    <mapspec> := <key>,<val>[:<key>,<val> ...]
"""

import sys
import getopt

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s [-options] delta|- [path ...]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'u:g:h', 
                                       ['uid-map=', 'gid-map='])
    except getopt.GetoptError, e:
        usage(e)

    uidmap = None
    gidmap = None
    for opt, val in opts:
        if opt in ('-u', '--uid-map'):
            uidmap = val
        elif opt in ('-g', '--gid-map'):
            gidmap = val
        else:
            usage()

    if len(args) < 1:
        usage()

    delta = args[0]
    paths = args[1:]

    print `(uidmap, gidmap, delta, paths)`

if __name__=="__main__":
    main()

