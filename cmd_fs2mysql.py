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
    #print "myconf: " + `myconf`

    if opt_tofile:
        if opt_tofile == '-':
            fh = sys.stdout
        else:
            fh = file(opt_tofile, "w")
    else:
        fh = mysql.mysql(**myconf)

    fs2mysql(fh, myfs, limits)

class MyFS:
    class Database:
        Paths = mysql.DatabasePaths
        class Table:
            Paths = mysql.TablePaths
            def __init__(self, database, fname):
                self.paths = self.Paths(join(database.paths.tables, fname))
                self.sql = file(self.paths.init).read()
                self.name = mysql.match_name(self.sql)
                self.database = database

            def __repr__(self):
                return "Table(%s)" % `self.paths.path`

            def rows(self):
                for line in file(self.paths.rows).xreadlines():
                    yield line.strip()

            rows = property(rows)

            def tofile(self, fh):
                print >> fh, "DROP TABLE IF EXISTS `%s`;" % self.name
                print >> fh, "SET @saved_cs_client     = @@character_set_client;"
                print >> fh, "SET character_set_client = utf8;"
                print >> fh, self.sql
                print >> fh, "SET character_set_client = @saved_cs_client;"

                index = None
                for index, row in enumerate(self.rows):
                    if index == 0:
                        print >> fh, "LOCK TABLES `%s` WRITE;" % self.name
                        print >> fh, "/*!40000 ALTER TABLE `%s` DISABLE KEYS */;" % self.name
                        print >> fh, "INSERT INTO `%s` VALUES " % self.name
                    else:
                        fh.write(",\n")
                    fh.write("(%s)" % row)

                if index is not None:
                    print >> fh, ";"
                    print >> fh, "/*!40000 ALTER TABLE `%s` ENABLE KEYS */;" % self.name
                    print >> fh, "UNLOCK TABLES;"

        def __init__(self, myfs, fname):
            self.paths = self.Paths(join(myfs.path, fname))
            self.sql = file(self.paths.init).read()
            self.name = mysql.match_name(self.sql)
            self.myfs = myfs

        def __repr__(self):
            return "Database(%s)" % `self.paths.path`

        def tables(self):
            for fname in os.listdir(self.paths.tables):
                table = self.Table(self, fname)
                if (self.name, table.name) in self.myfs.limits:
                    yield table
        tables = property(tables)

        def tofile(self, fh):
            print >> fh, self.sql,
            print >> fh, "USE `%s`;" % self.name

            for table in self.tables:
                table.tofile(fh)

    def __init__(self, path, limits=[]):
        self.path = path
        self.limits = mysql.DatabaseLimits(limits)

    def __iter__(self):
        for fname in os.listdir(self.path):
            database = self.Database(self, fname)
            if database.name in self.limits:
                yield database

    def tofile(self, fh):
        for database in self:
            database.tofile(fh)

def fs2mysql(fh, myfs, limits=[]):
    MyFS(myfs, limits).tofile(fh)

if __name__ == "__main__":
    main()
