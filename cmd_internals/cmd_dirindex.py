#!/usr/bin/python
"""
Print a list of files that have changed

Options:
    -i --input=PATH     Read a list of paths from a file (- for stdin)

    -c --create         Create index
"""
import sys
import getopt

import dirindex
import changes

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [-options] index path1 ... pathN" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'i:ch', 
                                       ['create', 'input='])
    except getopt.GetoptError, e:
        usage(e)

    opt_create = False
    opt_input = None

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        elif opt in ('-c', '--create'):
            opt_create = True

        elif opt in ('-i', '--input'):
            opt_input = val

    if not args or (not opt_input and len(args) < 2):
        usage()

    path_index = args[0]
    paths = args[1:]
    
    if opt_input:
        fh = file(opt_input) if opt_input != '-' else sys.stdin
        paths = dirindex.read_paths(fh) + paths

    if opt_create:
        dirindex.create(path_index, paths)
        return

    for change in changes.whatchanged(path_index, paths):
        print change

if __name__=="__main__":
    main()
