#!/usr/bin/python
"""
Map a MySQL dump to a filesystem path.

Options:
    -D --delete              Delete contents of output dir

Supports the following subset of mysqldump(1) options:

    -u --user=USER 
    -p --password=PASS

       --defaults-file=PATH
       --hostname=HOST

"""
import os
from os.path import *

import sys
import getopt

import re
import shutil

from paths import Paths

def _get_name(sql):
    sql = re.sub(r'/\*.*?\*/', "", sql)
    name = sql.split()[2]
    return re.sub(r'`(.*)`', '\\1', name)

def mkdir(path, parents=False):
    if not exists(path):
        if parents:
            os.makedirs(path)
        else:
            os.mkdir(path)

class Database:
    class Paths(Paths):
        files = [ 'init', 'tables' ]

    def __init__(self, outdir, sql):
        name = _get_name(sql)
        self.paths = self.Paths(join(outdir, name))
        mkdir(self.paths.path)

        print >> file(self.paths.init, "w"), sql

class Table:
    class Paths(Paths):
        files = [ 'init', 'rows' ]

    def __init__(self, database, sql):
        name = _get_name(sql)
        self.paths = self.Paths(join(database.paths.tables, name))
        mkdir(self.paths.path, True)

        print >> file(self.paths.init, "w"), sql

        self.rows_fh = file(self.paths.rows, "w")
        self.name = name

    def addrow(self, sql):
        name = _get_name(sql)
        if name != self.name:
            raise Error("row name (%s) != table name (%s)" % (name, self.name))
        print >> self.rows_fh, re.sub(r'.*?VALUES \((.*)\);', '\\1', sql)

def statements(fh):
    statement = ""
    for line in fh.xreadlines():
        statement += line
        if statement.strip().endswith(";"):
            yield statement.strip()
            statement = ""

def mysql2fs(fh, outdir):
    database = None
    table = None

    for statement in statements(fh):
        if statement.startswith("CREATE DATABASE"):
            database = Database(outdir, statement)
        
        elif statement.startswith("CREATE TABLE"):
            table = Table(database, statement)

        elif statement.startswith("INSERT INTO"):
            table.addrow(statement)

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s [-options] path/to/output" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'Du:p:', 
                                       ['delete', 
                                        'user=', 'password=', 'defaults-file=', 'hostname='])
    except getopt.GetoptError, e:
        usage(e)

    opt_delete = False
    conf = {}
    for opt,val in opts:
        if opt in ('-D', "--delete"):
            opt_delete = True
        elif opt in ('-u', '--user'):
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

    outdir = args[0]
    if opt_delete and isdir(outdir):
        shutil.rmtree(outdir)

    mkdir(outdir)

    mysql2fs(file("sql"), outdir)

if __name__ == "__main__":
    main()

