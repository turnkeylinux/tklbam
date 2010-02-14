#!/usr/bin/python
"""Print a list of files that have changed

Options:
    --create    create index

"""
import sys
import getopt
import dirindex 

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s index path1 ... pathN" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def fatal(s):
    print >> sys.stderr, "error: " + str(s)
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'c:h', 
                                       ['create'])
    except getopt.GetoptError, e:
        usage(e)

    opt_create = False

    for opt, val in opts:
        if opt == '-h':
            usage()

        elif opt in ('-c', '--create'):
            opt_create = True

    if len(args) < 2:
        usage()

    path_index = args[0]
    paths = args[1:]

    if opt_create:
        dirindex.create(path_index, paths)
    else:
        for path in dirindex.compare(path_index, paths):
            print path

if __name__=="__main__":
    main()

