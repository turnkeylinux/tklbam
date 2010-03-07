#!/usr/bin/python
"""
Map a filesystem created by mysql2fs back to MySQL

Options:
    --tofile=PATH           Write mysqldump output to file (- for STDOUT)
    -v --verbose            Turn on verbosity

Supports the following subset of mysql(1) options:

    -u --user=USER 
    -p --password=PASS

       --defaults-file=PATH
       --host=HOST

"""
import os
from os.path import *

import sys
import getopt

import shutil

import mysql

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s [-options] path/to/myfs [ -?database/table ... ] " % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'u:p:v', 
                                       ['verbose', 'tofile=',
                                        'user=', 'password=', 'defaults-file=', 'host='])
    except getopt.GetoptError, e:
        usage(e)

    opt_verbose = False
    opt_tofile = None
    myconf = {}
    for opt, val in opts:
        if opt in ('-v', '--verbose'):
            opt_verbose = True
        elif opt == '--tofile':
            opt_tofile = val
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

    #print "opt_verbose, opt_tofile = " + `opt_verbose, opt_tofile`
    #print "limits: " + `limits`
    #print "myconf: " + `myconf`

    fs2mysql(myfs)

class MyFS:
    class Database:
        class Table:
            def __init__(self, path):
                self.path = path

            def __str__(self):
                return file(join(self.path, "init")).read()

            def __repr__(self):
                return "Table(%s)" % `self.path`

            def rows(self):
                for line in file(join(self.path, "rows")).xreadlines():
                    yield line

            rows = property(rows)

        def __init__(self, path):
            self.path = path

        def __str__(self):
            return file(join(self.path, "init")).read()

        def __repr__(self):
            return "Database(%s)" % `self.path`

        def tables(self):
            for fname in os.listdir(join(self.path, "tables")):
                yield self.Table(join(self.path, "tables", fname))
        tables = property(tables)

    def __init__(self, path):
        self.path = path

    def __iter__(self):
        for fname in os.listdir(self.path):
            yield self.Database(join(self.path, fname))

def fs2mysql(myfs):
    for database in MyFS(myfs):
        print database
        for table in database.tables:
            print table
            for row in table.rows:
                print row

if __name__ == "__main__":
    main()

