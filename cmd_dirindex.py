#!/usr/bin/python
"""
Print a list of files that have changed

Options:
    -i --input=PATH     Read a list of paths frmo a file (- for stdin)

    -c --create         Create index
"""
import re
import sys
import getopt

import dirindex

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s index path1 ... pathN" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def parse_input(inputfile):
    paths = []
    
    if inputfile == '-':
        fh = sys.stdin
    else:
        fh = file(inputfile)

    for line in fh.readlines():
        line = re.sub(r'#.*', '', line).strip()
        if not line:
            continue

        paths.append(line)

    return paths

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
        paths += parse_input(opt_input)

    if opt_create:
        dirindex.create(path_index, paths)
        return

    for change in dirindex.whatchanged(path_index, paths):
        print change.fmt()

if __name__=="__main__":
    main()

