#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
import sys

import os
from os.path import *

import signal
import time

import re
from paths import Paths as _Paths

import shutil
from string import Template
from subprocess import Popen, PIPE

from dblimits import DBLimits
import executil

import stat
from command import Command

class Error(Exception):
    pass

PATH_DEBIAN_CNF = "/etc/mysql/debian.cnf"

def _mysql_opts(opts=[], defaults_file=None, **conf):
    def isreadable(path):
        try:
            file(path)
            return True
        except:
            return False

    if not defaults_file:
        if isreadable(PATH_DEBIAN_CNF):
            defaults_file = PATH_DEBIAN_CNF

    if defaults_file:
        opts.insert(0, "defaults-file=" + defaults_file)

    for opt, val in list(conf.items()):
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
    class Database:
        class Paths(_Paths):
            files = [ 'init', 'tables', 'views' ]

    class Table:
        class Paths(_Paths):
            files = [ 'init', 'triggers', 'rows' ]

    class View:
        class Paths(_Paths):
            files = [ 'pre', 'post' ]

def _match_name(sql):
    m = re.search(r'`(.*?)`', sql)
    if m:
        return m.group(1)
    
def _parse_statements(fh, delimiter=';'):
    statement = ""
    for line in fh:
        if line.startswith("--"):
            continue
        if not line.strip():
            continue
        if line.startswith("DELIMITER"):
            delimiter = line.split()[1]
            continue
        statement += line
        if statement.strip().endswith(delimiter):
            yield statement.strip()
            statement = ""

class MyFS_Writer(MyFS):
    class Database(MyFS.Database):
        class View(MyFS.View):
            def __init__(self, views_path, name):
                paths = self.Paths(join(views_path, name))
                if not exists(paths):
                    os.makedirs(paths)
                self.paths = paths

        def __init__(self, outdir, name, sql):
            self.paths = self.Paths(join(outdir, name))
            if not exists(self.paths):
                os.mkdir(self.paths)

            print(sql, file=file(self.paths.init, "w"))
            self.name = name

        def add_view_pre(self, name, sql):
            view = self.View(self.paths.views, name)
            print(sql, file=file(view.paths.pre, "w"))

        def add_view_post(self, name, sql):
            view = self.View(self.paths.views, name)
            print(sql, file=file(view.paths.post, "w"))

    class Table(MyFS.Table):
        def __init__(self, database, name, sql):
            self.paths = self.Paths(join(database.paths.tables, name))
            if not exists(self.paths):
                os.makedirs(self.paths)

            print(sql, file=file(self.paths.init, "w"))
            if exists(self.paths.triggers):
                os.remove(self.paths.triggers)

            self.rows_fh = file(self.paths.rows, "w")
            self.name = name
            self.database = database

        def add_row(self, sql):
            print(re.sub(r'.*?VALUES \((.*)\);', '\\1', sql), file=self.rows_fh)

        def add_trigger(self, sql):
            print(sql + "\n", file=file(self.paths.triggers, "a"))

    def __init__(self, outdir, limits=[]):
        self.limits = DBLimits(limits)
        self.outdir = outdir

    def fromfile(self, fh, callback=None):
        databases = {}
        database = None
        table = None

        for statement in _parse_statements(fh):
            if statement.startswith("CREATE DATABASE"):
                database_name = _match_name(statement)

                if database_name in self.limits:
                    database = self.Database(self.outdir, database_name, statement)
                    if callback:
                        callback(database)

                    databases[database.name] = database
                else:
                    database = None

            elif statement.startswith("USE "):
                database_name = _match_name(statement)

                database = databases.get(database_name)
                if not database:
                    continue

                table = None

            if not database:
                continue

            m = re.match(r'^/\*!50001 CREATE.* VIEW `(.*?)`', statement, re.DOTALL)
            if m:
                view_name = m.group(1)
                database.add_view_post(view_name, statement)

            elif re.match(r'^/\*!50001 CREATE TABLE', statement):
                view_name = _match_name(statement)
                database.add_view_pre(view_name, statement)

            elif statement.startswith("CREATE TABLE"):
                table_name = _match_name(statement)

                table = self.Table(database, table_name, statement)
                if (database.name, table_name) in self.limits:
                    if callback:
                        callback(table)

                    table_ignore_inserts = False
                else:
                    table_ignore_inserts = True

            if not table:
                continue

            if re.match(r'^/\*!50003 CREATE.* TRIGGER ', statement, re.DOTALL):
                table.add_trigger(statement)

            elif not table_ignore_inserts and statement.startswith("INSERT INTO"):
                assert _match_name(statement) == table.name
                table.add_row(statement)

def mysql2fs(fh, outdir, limits=[], callback=None):
    MyFS_Writer(outdir, limits).fromfile(fh, callback)

def chunkify(elements, delim, maxlen):
    chunk = ""
    for element in elements:
        if len(chunk) + len(delim) + len(element) > maxlen:
            if chunk:
                yield chunk

            if len(element) > maxlen:
                ## locally correct logic:
                #raise Error("element='%s' longer than maxlen=%d" % (element, maxlen))

                ## globally correct logic (the lesser evil):
                yield element
                chunk = ""
                continue

            chunk = element
        else:
            if not chunk:
                chunk = element
            else:
                chunk += delim + element

    if chunk:
        yield chunk

class MyFS_Reader(MyFS):
    MAX_EXTENDED_INSERT = 1000000 - 1024

    class Database(MyFS.Database):
        class View(MyFS.View):
            TPL_PRE = """\
DROP TABLE IF EXISTS `$name`;
/*!50001 DROP VIEW IF EXISTS `$name`*/;
SET @saved_cs_client     = @@character_set_client;
SET character_set_client = utf8;
$sql
SET character_set_client = @saved_cs_client;
"""

            TPL_POST = """\
/*!50001 DROP TABLE IF EXISTS `$name`*/;
/*!50001 DROP VIEW IF EXISTS `$name`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8 */;
/*!50001 SET character_set_results     = utf8 */;
$sql    
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
"""
            class Error(Exception):
                pass

            def __init__(self, views_path, name):
                paths = self.Paths(join(views_path, name))
                if not isdir(paths):
                    raise self.Error("not a directory '%s'" % paths)
                self.paths = paths
                self.name = name

            def pre(self):
                if not exists(self.paths.pre):
                    return
                sql = file(self.paths.pre).read().strip()
                return Template(self.TPL_PRE).substitute(name=self.name, sql=sql)
            pre = property(pre)

            def post(self):
                if not exists(self.paths.post):
                    return
                sql = file(self.paths.post).read().strip()
                return Template(self.TPL_POST).substitute(name=self.name, sql=sql)
            post = property(post)
            
        def __init__(self, myfs, fname):
            self.paths = self.Paths(join(myfs.path, fname))
            self.sql_init = file(self.paths.init).read()
            self.name = _match_name(self.sql_init)
            self.myfs = myfs

        def __repr__(self):
            return "Database(%s)" % repr(self.paths.path)

        def tables(self):
            if not exists(self.paths.tables):
                return

            for fname in os.listdir(self.paths.tables):
                table = self.myfs.Table(self, fname)
                if (self.name, table.name) in self.myfs.limits:
                    yield table
        tables = property(tables)

        def views(self):
            if not exists(self.paths.views):
                return

            for fname in os.listdir(self.paths.views):
                try:
                    view = self.View(self.paths.views, fname)
                except self.View.Error:
                    continue

                yield view
        views = property(views)

        def tofile(self, fh, callback=None):
            if callback:
                callback(self)

            if self.myfs.add_drop_database and self.name != 'mysql':
                print("/*!40000 DROP DATABASE IF EXISTS `%s`*/;" % self.name, file=fh)
            print(self.sql_init, end=' ', file=fh)
            print("USE `%s`;" % self.name, file=fh)

            for table in self.tables:
                if callback:
                    callback(table)
                table.tofile(fh)

            for view in self.views:
                if view.pre:
                    print("\n" + view.pre, file=fh)

    class Table(MyFS.Table):
        TPL_CREATE = """\
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

        TPL_TRIGGERS_PRE = """\
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8 */ ;
/*!50003 SET character_set_results = utf8 */ ;
/*!50003 SET collation_connection  = utf8_general_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'STRICT_TRANS_TABLES,STRICT_ALL_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,TRADITIONAL,NO_AUTO_CREATE_USER' */ ;
DELIMITER ;;
"""
        TPL_TRIGGERS_POST = """\
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
"""

        def __init__(self, database, fname):
            self.paths = self.Paths(join(database.paths.tables, fname))
            self.sql_init = file(self.paths.init).read()
            self.name = _match_name(self.sql_init)
            self.database = database

        def __repr__(self):
            return "Table(%s)" % repr(self.paths.path)

        def rows(self):
            for line in file(self.paths.rows):
                yield line.strip()

        def has_rows(self):
            if exists(self.paths.rows) and os.lstat(self.paths.rows).st_size != 0:
                return True
            return False

        rows = property(rows)

        def triggers(self):
            if not exists(self.paths.triggers):
                return []

            return list(_parse_statements(file(self.paths.triggers), ';;'))
        triggers = property(triggers)

        def tofile(self, fh):
            skip_extended_insert = self.database.myfs.skip_extended_insert
            max_extended_insert = self.database.myfs.max_extended_insert

            is_log_table = (self.database.name == "mysql" and self.name in ('general_log', 'slow_log'))

            if not is_log_table:
                print("DROP TABLE IF EXISTS `%s`;" % self.name, file=fh)

            print(Template(self.TPL_CREATE).substitute(init=self.sql_init), file=fh)

            if self.has_rows():
                if not is_log_table:
                    print(Template(self.TPL_INSERT_PRE).substitute(name=self.name).strip(), file=fh)

                insert_prefix = "INSERT INTO `%s` VALUES " % self.name
                if skip_extended_insert:
                    for  row in self.rows:
                        print(insert_prefix + "(%s);" % row, file=fh)
                        
                else:
                    rows = ( "(%s)" % row for row in self.rows )
                    row_chunks = chunkify(rows, ",\n", max_extended_insert - len(insert_prefix + ";"))

                    index = None
                    for index, chunk in enumerate(row_chunks):

                        fh.write(insert_prefix + "\n")
                        fh.write(chunk + ";")
                        fh.write("\n")

                    if index is not None:
                        print("\n-- CHUNKS: %d\n" % (index + 1), file=fh)

                if not is_log_table:
                    print(Template(self.TPL_INSERT_POST).substitute(name=self.name), file=fh)

            if self.triggers:
                print(self.TPL_TRIGGERS_PRE.strip(), file=fh)
                for trigger in self.triggers:
                    print(trigger, file=fh)
                print(self.TPL_TRIGGERS_POST, file=fh)

    PRE = """\
/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
"""

    POST = """\
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;
/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;
"""

    def __init__(self, path, limits=[], 
                 skip_extended_insert=False,
                 add_drop_database=False,
                 max_extended_insert=None):
        self.path = path
        self.limits = DBLimits(limits)
        self.skip_extended_insert = skip_extended_insert
        self.add_drop_database = add_drop_database

        if max_extended_insert is None:
            max_extended_insert = self.MAX_EXTENDED_INSERT
        self.max_extended_insert = max_extended_insert

    def __iter__(self):
        for fname in os.listdir(self.path):
            database = self.Database(self, fname)
            if database.name in self.limits:
                yield database

    def tofile(self, fh, callback=None):
        print(self.PRE, file=fh)

        for database in self:
            database.tofile(fh, callback)

        for database in self:
            views = list(database.views)
            if not views:
                continue

            print("USE `%s`;" % database.name, file=fh)
            for view in views:
                print("\n" + view.post, file=fh)

        print(self.POST, file=fh)

def fs2mysql(fh, myfs, limits=[], callback=None, skip_extended_insert=False, add_drop_database=False):

    MyFS_Reader(myfs, limits, skip_extended_insert, add_drop_database).tofile(fh, callback)

def cb_print(fh=None):
    if not fh:
        fh = sys.stdout

    def func(val):
        if isinstance(val, MyFS.Database):
            database = val
            print("database: " + database.name, file=fh)
        elif isinstance(val, MyFS.Table):
            table = val
            print("table: " + join(table.database.name, table.name), file=fh)

    return func

def backup(myfs, etc, **kws):
    """High level mysql backup command.
    Arguments:

        <myfs>      Directory we create to save MySQL backup
        <etc>       Directory where we save required MySQL etc configuration files (e.g., debian.cnf)
        """

    if not MysqlService.is_running():
        raise Error("MySQL service not running")

    mna = None
    if not MysqlService.is_accessible():
        mna = MysqlNoAuth()

    try:
        mysqldump_fh = mysqldump()

        if not exists(myfs):
            os.mkdir(myfs)

        mysql2fs(mysqldump_fh, myfs, **kws)

        if not exists(etc):
            os.mkdir(etc)

        shutil.copy(PATH_DEBIAN_CNF, etc)

    finally:
        if mna:
            mna.stop()

def restore(myfs, etc, **kws):
    if kws.pop('simulate', False):
        simulate = True
    else:
        simulate = False

    mna = None
    if simulate:
        mysql_fh = file("/dev/null", "w")
    else:
        if not MysqlService.is_running():
            raise Error("MySQL service not running")
            
        if not MysqlService.is_accessible():
            mna = MysqlNoAuth()

        mysql_fh = mysql()

    try:
        fs2mysql(mysql_fh, myfs, **kws)
        mysql_fh.close()
    finally:
        if mna:
            mna.stop()

    if not simulate:
        shutil.copy(join(etc, basename(PATH_DEBIAN_CNF)), PATH_DEBIAN_CNF)
        MysqlService.reload()
    
class MysqlService:
    INIT_SCRIPT = "/etc/init.d/mysql"
    PID_FILE = '/var/run/mysqld/mysqld.pid'

    class Error(Exception):
        pass

    @staticmethod
    def _pid_exists(pid):
        try:
            os.kill(pid, 0)
            return True
        except:
            return False

    @classmethod
    def get_pid(cls):
        """Returns pid in pidfile if process is running. Otherwise returns None"""
        if not exists(cls.PID_FILE):
            return

        pid = int(file(cls.PID_FILE).read().strip())
        if cls._pid_exists(pid):
            return pid

    @classmethod
    def is_running(cls):
        try:
            executil.getoutput('mysqladmin -s ping')
            return True
        except executil.ExecError:
            return False

    @classmethod
    def start(cls):
        if cls.is_running():
            return

        retries = 2
        for i in range(retries):
            try:
                executil.getoutput(cls.INIT_SCRIPT, "start")
                return
            except executil.ExecError as e:
                pass

        raise e

    @classmethod
    def stop(cls):
        if not cls.is_running():
            return

        pid = cls.get_pid()
        if not pid:
            return

        os.kill(pid, signal.SIGTERM)
        while True:
            if not cls._pid_exists(pid):
                break

            time.sleep(1)

    @classmethod
    def reload(cls):
        pid = cls.get_pid()
        if not pid:
            raise cls.Error("can't reload, mysql not running")

        os.kill(pid, signal.SIGHUP)

    @classmethod
    def is_accessible(cls):
        try:
            executil.getoutput_popen("mysql --defaults-file=/etc/mysql/debian.cnf", "select 1")
            return True

        except executil.ExecError:
            return False

class MysqlNoAuth:
    PATH_VARRUN = '/var/run/mysqld'
    COMMAND = "mysqld_safe --skip-grant-tables --skip-networking"

    def __init__(self):
        self.stopped = False

        self.command = None
        self.was_running = None

        if MysqlService.is_running():
            MysqlService.stop()
            was_running = True
        else:
            was_running = False

        self.orig_varrun_mode = stat.S_IMODE(os.stat(self.PATH_VARRUN).st_mode)
        os.chmod(self.PATH_VARRUN, 0o750)

        command = Command(self.COMMAND)

        def cb():
            if MysqlService.is_running():
                continue_waiting = False
            else:
                continue_waiting = True

            return continue_waiting

        command.wait(timeout=10, callback=cb)
        if not command.running or not MysqlService.is_running():
            command.terminate()
            if was_running:
                MysqlService.start()

            raise Error(("%s failed to start\n" % self.COMMAND) + command.output)

        self.command = command
        self.was_running = was_running

    def stop(self):
        if self.stopped:
            return

        self.stopped = True
        if self.command:
            os.kill(self.command.pid, signal.SIGINT)
            self.command.wait()
            self.command = None
            
        os.chmod(self.PATH_VARRUN, self.orig_varrun_mode)

        if self.was_running:
            MysqlService.start()

    def __del__(self):
        self.stop()
