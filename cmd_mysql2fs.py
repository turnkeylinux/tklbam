#!/usr/bin/python
"""
Map a MySQL dump to a filesystem path.

Supports the following subset of mysqldump(1) options:
        -u --user=USER 
        -p --password=PASS

           --defaults-file=PATH
           --hostname=HOST

"""
import sys
import getopt

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s [-options] path/to/output" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'u:p:', 
                                       ['user=', 'password=', 'defaults-file=', 'hostname='])
    except getopt.GetoptError, e:
        usage(e)

    conf = {}
    for opt,val in opts:
        if opt in ('-u', '--user'):
            conf['user'] = val
        elif opt in ('-p', '--password'):
            conf['password'] = val
        elif opt == "--defaults-file":
            conf['defaults-file'] = val
        elif opt == "--hostname":
            conf['hostname'] = val
        else:
            usage()

    if not args:
        usage()

    output = args[0]
    print `conf`
    print `output`

if __name__ == "__main__":
    main()
