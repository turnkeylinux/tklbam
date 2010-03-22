#!/usr/bin/python
"""
Map a filesystem created by mysql2fs back to MySQL

Options:
    --tofile=PATH           Write mysqldump output to file (- for STDOUT)
    -v --verbose            Turn on verbosity

    --skip-extended-insert  Skip extended insert (useful in debugging)

Supports the following subset of mysql(1) options:

    -u --user=USER 
    -p --password=PASS

       --defaults-file=PATH
       --host=HOST

"""
import sys
import getopt

import mysql

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [-options] path/to/myfs [ -?database/table ... ] " % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'u:p:v', 
                                       ['verbose', 'tofile=',
                                        'skip-extended-insert',
                                        'user=', 'password=', 'defaults-file=', 'host='])
    except getopt.GetoptError, e:
        usage(e)

    opt_verbose = False
    opt_tofile = None
    opt_skip_extended_insert = False
    myconf = {}
    for opt, val in opts:
        if opt in ('-v', '--verbose'):
            opt_verbose = True
        elif opt == '--tofile':
            opt_tofile = val
        elif opt == '--skip-extended-insert':
            opt_skip_extended_insert = True
        elif opt in ('-u', '--user'):
            myconf['user'] = val
        elif opt in ('-p', '--password'):
            myconf['password'] = val
        elif opt == "--defaults-file":
            myconf['defaults_file'] = val
        elif opt == "--host":
            myconf['host'] = val
        else:
            usage()

    if not args:
        usage()

    myfs = args[0]
    limits = args[1:]

    if opt_tofile:
        if opt_tofile == '-':
            fh = sys.stdout
        else:
            fh = file(opt_tofile, "w")
    else:
        fh = mysql.mysql(**myconf)

    callback = None
    if opt_verbose:
        print "destination: " + fh.name
        callback = mysql.cb_print()

    if opt_verbose:
        pass

    mysql.fs2mysql(fh, myfs, limits, callback, opt_skip_extended_insert)

if __name__ == "__main__":
    main()
