import os
from os.path import *

import re
from paths import Paths

def mkdir(path, parents=False):
    if not exists(path):
        if parents:
            os.makedirs(path)
        else:
            os.mkdir(path)

def mysqldump(defaults_file=None, **conf):
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

    opts = []

    if defaults_file:
        opts.append("defaults-file=" + defaults_file)

    opts += [ "all-databases", "skip-extended-insert", "single-transaction", 
              "compact", "quick" ]

    for opt, val in conf.items():
        opts.append(opt.replace("_", "-") + "=" + val)

    command = "mysqldump " + " ".join([ "--" + opt for opt in opts ])
    return os.popen(command)

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
            mkdir(self.paths.path)

            print >> file(self.paths.init, "w"), sql
            self.name = name

    class Table(MyFS.Table):
        def __init__(self, database, name, sql):
            self.paths = self.Paths(join(database.paths.tables, name))
            mkdir(self.paths.path, True)

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
            self.sql = file(self.paths.init).read()
            self.name = _match_name(self.sql)
            self.myfs = myfs

        def __repr__(self):
            return "Database(%s)" % `self.paths.path`

        def tables(self):
            for fname in os.listdir(self.paths.tables):
                table = self.myfs.Table(self, fname)
                if (self.name, table.name) in self.myfs.limits:
                    yield table
        tables = property(tables)

        def tofile(self, fh):
            print >> fh, self.sql,
            print >> fh, "USE `%s`;" % self.name

            for table in self.tables:
                table.tofile(fh)

    class Table(MyFS.Table):
        def __init__(self, database, fname):
            self.paths = self.Paths(join(database.paths.tables, fname))
            self.sql = file(self.paths.init).read()
            self.name = _match_name(self.sql)
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

    def __init__(self, path, limits=[]):
        self.path = path
        self.limits = self.Limits(limits)

    def __iter__(self):
        for fname in os.listdir(self.path):
            database = self.Database(self, fname)
            if database.name in self.limits:
                yield database

    def tofile(self, fh):
        for database in self:
            database.tofile(fh)

def fs2mysql(fh, myfs, limits=[]):
    MyFS_Reader(myfs, limits).tofile(fh)