import sys

import os
from os.path import *

import re
from paths import Paths

from string import Template
from subprocess import Popen, PIPE

class Error(Exception):
    pass

def _mysql_opts(opts=[], defaults_file=None, **conf):
    def isreadable(path):
        try:
            file(path)
            return True
        except:
            return False

    if not defaults_file:
        debian_cnf = "/etc/mysql/debian.cnf"
        if isreadable(debian_cnf):
            defaults_file = debian_cnf

    if defaults_file:
        opts.insert(0, "defaults-file=" + defaults_file)

    for opt, val in conf.items():
        opts.append(opt.replace("_", "-") + "=" + val)

    return " ".join([ "--" + opt for opt in opts ])

def mysqldump(**conf):
    opts = [ "all-databases", "skip-extended-insert", "single-transaction", 
             "compact", "quick" ]

    command = "mysqldump " + _mysql_opts(opts, **conf)
    popen = Popen(command, shell=True, stderr=PIPE, stdout=PIPE)

    firstline = popen.stdout.readline()
    if not firstline:
        returncode = popen.wait()
        raise Error("mysqldump error (%d): %s" % (returncode, popen.stderr.read()))

    return popen.stdout

def mysql(**conf):
    command = "mysql " + _mysql_opts(**conf)

    popen = Popen(command, shell=True, stdin=PIPE, stderr=PIPE, stdout=PIPE)
    popen.stdin.close()
    returncode = popen.wait()
    if returncode != 0:
        raise Error("mysql error (%d): %s" % (returncode, popen.stderr.read()))

    return os.popen(command, "w")

class MyFS:
    class Limits:
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


    class Database:
        class Paths(Paths):
            files = [ 'init', 'tables' ]

    class Table:
        class Paths(Paths):
            files = [ 'init', 'rows' ]

def _match_name(sql):
    sql = re.sub(r'/\*.*?\*/', "", sql)
    name = sql.split(None, 3)[2]
    return re.sub(r'`(.*)`', '\\1', name)

class MyFS_Writer(MyFS):
    class Database(MyFS.Database):
        def __init__(self, outdir, name, sql):
            self.paths = self.Paths(join(outdir, name))
            if not exists(self.paths):
                os.mkdir(self.paths)

            print >> file(self.paths.init, "w"), sql
            self.name = name

    class Table(MyFS.Table):
        def __init__(self, database, name, sql):
            self.paths = self.Paths(join(database.paths.tables, name))
            if not exists(self.paths):
                os.makedirs(self.paths)

            print >> file(self.paths.init, "w"), sql

            self.rows_fh = file(self.paths.rows, "w")
            self.name = name
            self.database = database

        def addrow(self, sql):
            print >> self.rows_fh, re.sub(r'.*?VALUES \((.*)\);', '\\1', sql)

    def __init__(self, outdir, limits=[]):
        self.limits = self.Limits(limits)
        self.outdir = outdir

    @staticmethod
    def _parse(fh):
        statement = ""
        for line in fh.xreadlines():
            statement += line
            if statement.strip().endswith(";"):
                yield statement.strip()
                statement = ""

    def fromfile(self, fh, callback=None):
        database = None
        table = None

        for statement in self._parse(fh):
            if statement.startswith("CREATE DATABASE"):
                database_name = _match_name(statement)

                if database_name in self.limits:
                    database = self.Database(self.outdir, database_name, statement)
                    if callback:
                        callback(database)
                else:
                    database = None
            
            elif statement.startswith("CREATE TABLE"):
                if not database:
                    continue

                table_name = _match_name(statement)
                if (database.name, table_name) in self.limits:
                    table = self.Table(database, table_name, statement)
                    if callback:
                        callback(table)
                else:
                    table = None

            elif statement.startswith("INSERT INTO"):
                if not database or not table:
                    continue

                assert _match_name(statement) == table.name
                table.addrow(statement)

def mysql2fs(fh, outdir, limits=[], callback=None):
    MyFS_Writer(outdir, limits).fromfile(fh, callback)

class MyFS_Reader(MyFS):
    class Database(MyFS.Database):
        def __init__(self, myfs, fname):
            self.paths = self.Paths(join(myfs.path, fname))
            self.sql_init = file(self.paths.init).read()
            self.name = _match_name(self.sql_init)
            self.myfs = myfs

        def __repr__(self):
            return "Database(%s)" % `self.paths.path`

        def tables(self):
            if not exists(self.paths.tables):
                return

            for fname in os.listdir(self.paths.tables):
                table = self.myfs.Table(self, fname)
                if (self.name, table.name) in self.myfs.limits:
                    yield table
        tables = property(tables)

        def tofile(self, fh, callback=None):
            if callback:
                callback(self)

            if self.myfs.add_drop_database:
                print >> fh, "/*!40000 DROP DATABASE IF EXISTS `%s`*/;" % self.name
            print >> fh, self.sql_init,
            print >> fh, "USE `%s`;" % self.name

            for table in self.tables:
                if callback:
                    callback(table)
                table.tofile(fh)

    class Table(MyFS.Table):
        TPL_CREATE = """\
DROP TABLE IF EXISTS `$name`;
SET @saved_cs_client     = @@character_set_client;
SET character_set_client = utf8;
$init
SET character_set_client = @saved_cs_client;
"""

        TPL_INSERT_PRE = """\
LOCK TABLES `$name` WRITE;
/*!40000 ALTER TABLE `$name` DISABLE KEYS */;
"""

        TPL_INSERT_POST = """\
/*!40000 ALTER TABLE `$name` ENABLE KEYS */;
UNLOCK TABLES;
"""

        def __init__(self, database, fname):
            self.paths = self.Paths(join(database.paths.tables, fname))
            self.sql_init = file(self.paths.init).read()
            self.name = _match_name(self.sql_init)
            self.database = database

        def __repr__(self):
            return "Table(%s)" % `self.paths.path`

        def rows(self):
            for line in file(self.paths.rows).xreadlines():
                yield line.strip()

        rows = property(rows)

        def tofile(self, fh):
            skip_extended_insert = self.database.myfs.skip_extended_insert

            tpl = Template(self.TPL_CREATE)
            print >> fh, tpl.substitute(name=self.name, init=self.sql_init)

            index = None
            for index, row in enumerate(self.rows):
                if index == 0:
                    tpl = Template(self.TPL_INSERT_PRE)
                    print >> fh, tpl.substitute(name=self.name)

                if skip_extended_insert:
                    print >> fh, "INSERT INTO `%s` VALUES (%s);" % (self.name, row)

                else:
                    if index == 0:
                        print >> fh, "INSERT INTO `%s` VALUES" % self.name
                    else:
                        fh.write(",\n")
                    fh.write("(%s)" % row)

            if index is not None:
                if not skip_extended_insert:
                    print >> fh, ";"

                tpl = Template(self.TPL_INSERT_POST)
                print >> fh, tpl.substitute(name=self.name)

    def __init__(self, path, limits=[], 
                 skip_extended_insert=False,
                 add_drop_database=False):
        self.path = path
        self.limits = self.Limits(limits)
        self.skip_extended_insert = skip_extended_insert
        self.add_drop_database = add_drop_database

    def __iter__(self):
        for fname in os.listdir(self.path):
            database = self.Database(self, fname)
            if database.name in self.limits:
                yield database

    def tofile(self, fh, callback=None):
        for database in self:
            database.tofile(fh, callback)

def fs2mysql(fh, myfs, limits=[], callback=None, skip_extended_insert=False, add_drop_database=False):

    MyFS_Reader(myfs, limits, skip_extended_insert, add_drop_database).tofile(fh, callback)

def cb_print(fh=None):
    if not fh:
        fh = sys.stdout

    def func(val):
        if isinstance(val, MyFS.Database):
            database = val
            print >> fh, "database: " + database.name
        elif isinstance(val, MyFS.Table):
            table = val
            print >> fh, "table: " + join(table.database.name, table.name)

    return func
