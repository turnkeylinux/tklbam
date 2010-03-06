#!/usr/bin/python
"""
Map a MySQL dump to a filesystem path.

Options:
    -D --delete             Delete contents of output dir
    --fromfile=PATH         Read mysqldump output from file (- for STDIN)
                            Requires: --all-databases --skip-extended-insert

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

def mkdir(path, parents=False):
    if not exists(path):
        if parents:
            os.makedirs(path)
        else:
            os.mkdir(path)

class Database:
    class Paths(Paths):
        files = [ 'init', 'tables' ]

    def __init__(self, outdir, name, sql):
        self.paths = self.Paths(join(outdir, name))
        mkdir(self.paths.path)

        print >> file(self.paths.init, "w"), sql
        self.name = name

class Table:
    class Paths(Paths):
        files = [ 'init', 'rows' ]

    def __init__(self, database, name, sql):
        self.paths = self.Paths(join(database.paths.tables, name))
        mkdir(self.paths.path, True)

        print >> file(self.paths.init, "w"), sql

        self.rows_fh = file(self.paths.rows, "w")
        self.name = name

    def addrow(self, sql):
        print >> self.rows_fh, re.sub(r'.*?VALUES \((.*)\);', '\\1', sql)

def statements(fh):
    statement = ""
    for line in fh.xreadlines():
        statement += line
        if statement.strip().endswith(";"):
            yield statement.strip()
            statement = ""

class DatabaseLimits:
    def __init__(self, limits):
        self.default = True
        self.databases = []

        d = {}
        for limit in limits:
            if limit[0] == '-':
                limit = limit[1:]
                sign = False
            else:
                sign = True
                self.default = False

            if '/' in limit:
                database, table = limit.split('/')
                d[(database, table)] = sign
            else:
                database = limit
                d[database] = sign

            self.databases.append(database)

        self.d = d

    def __contains__(self, val):
        """Tests if <val> is within the defined Database limits

        <val> can be:

            1) a (database, table) tuple
            2) a database string
            3) database/table

        """
        if '/' in val:
            database, table = val.split('/')
            val = (database, table)

        if isinstance(val, type(())):
            database, table = val
            if (database, table) in self.d:
                return self.d[(database, table)]

            if database in self.d:
                return self.d[database]

            return self.default

        else:
            database = val
            if database in self.databases:
                return True
            
            return self.default

def mysql2fs(fh, outdir, limits=[]):
    database = None
    table = None

    limits = DatabaseLimits(limits)

    def match_name(sql):
        sql = re.sub(r'/\*.*?\*/', "", sql)
        name = sql.split()[2]
        return re.sub(r'`(.*)`', '\\1', name)

    for statement in statements(fh):
        if statement.startswith("CREATE DATABASE"):
            database_name = match_name(statement)

            if database_name in limits:
                database = Database(outdir, database_name, statement)
            else:
                database = None
        
        elif statement.startswith("CREATE TABLE"):
            if not database:
                continue

            table_name = match_name(statement)
            if (database.name, table_name) in limits:
                table = Table(database, table_name, statement)
            else:
                table = None

        elif statement.startswith("INSERT INTO"):
            if not table:
                continue

            assert match_name(statement) == table.name
            table.addrow(statement)

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s [-options] path/to/output [ -?database/table ... ] " % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'Du:p:', 
                                       ['delete', 'fromfile=',
                                        'user=', 'password=', 'defaults-file=', 'hostname='])
    except getopt.GetoptError, e:
        usage(e)

    opt_fromfile = None
    opt_delete = False
    conf = {}
    for opt, val in opts:
        if opt == '--fromfile':
            opt_fromfile = val
        elif opt in ('-D', "--delete"):
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
    limits = args[1:]

    if opt_delete and isdir(outdir):
        shutil.rmtree(outdir)

    mkdir(outdir)
    if opt_fromfile:
        mysql_fh = file(opt_fromfile)

    mysql2fs(mysql_fh, outdir, limits)

if __name__ == "__main__":
    main()

