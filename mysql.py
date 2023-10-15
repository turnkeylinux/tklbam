#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
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
from os.path import join, exists, isdir, basename
import signal
import time
import re

import shutil
from string import Template
import subprocess
from subprocess import Popen, PIPE, STDOUT
from typing import Optional, IO, Generator, Self, Callable

from dblimits import DBLimits
from paths import Paths as _Paths

import stat
from command import Command

class Error(Exception):
    pass

PATH_DEBIAN_CNF = "/etc/mysql/debian.cnf"

def _mysql_opts(opts: Optional[list[str]] = None,
                defaults_file: Optional[str] = None, **conf) -> str:
    if not opts:
        opts = []
    def isreadable(path):
        try:
            with open(path):
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

def mysqldump(**conf) -> Optional[IO[str]]:
    opts = [ "all-databases", "skip-extended-insert", "single-transaction",
             "compact", "quick" ]

    command = "mysqldump " + _mysql_opts(opts, **conf)
    popen = Popen(command, shell=True, stderr=PIPE, stdout=PIPE, text=True)

    firstline = ''
    stderr = ''
    if popen.stdout:
        firstline = popen.stdout.readline()
    if popen.stderr:
        stderr = popen.stderr.read()
    if not firstline:
        returncode = popen.wait()
        raise Error("mysqldump error (%d): %s" % (returncode, stderr))

    return popen.stdout

def mysql(**conf) -> subprocess.Popen:
    command = "mysql " + _mysql_opts(**conf)

    popen = Popen(command, shell=True, stdin=PIPE, stderr=PIPE, stdout=PIPE, text=True)
    if popen.stdin:
        popen.stdin.close()
    stderr = ''
    if popen.stderr:
        stderr = popen.stderr.read()
    returncode = popen.wait()
    if returncode != 0:
        raise Error("mysql error (%d): %s" % (returncode, stderr))

    #return subprocess.Popen(command, shell=True, text=True,
    #                        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    return popen

class MyFS:
    path: str
    limits: DBLimits  # reader
    add_drop_database: bool  # reader
    skip_extended_insert: bool  # reader
    max_extended_insert: int  # reader
    class Database:
        name: str
        path: str
        myfs: MyFS  # reader
        tofile: Callable  # reader
        views: property  # reader
        paths: _Paths
        add_view_post: Callable  # writer
        add_view_pre: Callable  # writer
        class Paths(_Paths):
            files = [ 'init', 'tables', 'views' ]

    class Table:
        name: str
        add_trigger: Callable  # writer
        add_row: Callable  # writer
        class Paths(_Paths):
            files = [ 'init', 'triggers', 'rows' ]

    class View:
        class Paths(_Paths):
            files = [ 'pre', 'post' ]

def _match_name(sql: str) -> str:
    m = re.search(r'`(.*?)`', sql)
    if m:
        return m.group(1)
    return ''

def _parse_statements(fh: IO[str], delimiter: str = ';') -> Generator[str, None, None]:
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
    return None

class MyFS_Writer(MyFS):
    class Database(MyFS.Database):
        class View(MyFS.View):
            def __init__(self, views_path: str, name: str):
                paths = self.Paths(join(views_path, name))
                if not exists(paths):
                    os.makedirs(paths)
                self.paths = paths

        def __init__(self, outdir: str, name: str, sql: str):
            self.paths = self.Paths(join(outdir, name))
            if not exists(self.paths):
                os.mkdir(self.paths)

            with open(self.paths.init, "w") as fob:
                fob.write(sql)
            self.name = name

        def add_view_pre(self, name: str, sql: str) -> None:
            view = self.View(self.paths.views, name)
            with open(view.paths.pre, "w") as fob:
                fob.write(sql)

        def add_view_post(self, name: str, sql: str) -> None:
            view = self.View(self.paths.views, name)
            with open(view.paths.post, "w") as fob:
                fob.write(sql)

    class Table(MyFS.Table):
        def __init__(self, database: MyFS.Database, name: str, sql: str):
            self.paths: _Paths = self.Paths(join(database.paths.tables, name))
            if not exists(self.paths):
                os.makedirs(self.paths)

            with open(self.paths.init, "w") as fob:
                fob.write(sql)
            if exists(self.paths.triggers):
                os.remove(self.paths.triggers)

            # TODO this use of open could be better...
            self.rows_fh = open(self.paths.rows, "w")
            self.name = name
            self.database = database

        def add_row(self, sql: str) -> None:
            print(re.sub(r'.*?VALUES \((.*)\);', '\\1', sql), file=self.rows_fh)

        def add_trigger(self, sql: str) -> None:
            print(sql + "\n", file=open(self.paths.triggers, "a"))

    def __init__(self, outdir: str, limits: Optional[list[str]] = None):
        if not limits:
            limits = []
        self.limits = DBLimits(limits)
        self.outdir = outdir

    def fromfile(self, fh: IO[str], callback: Optional[Callable] = None) -> None:

        databases: dict[str, MyFS.Database] = {}
        database: Optional[MyFS.Database] = None
        table: Optional[MyFS.Table] = None

        for statement in _parse_statements(fh):
            if statement.startswith("CREATE DATABASE"):
                database_name = _match_name(statement)

                if database_name in self.limits:
                    if database_name:
                        database = self.Database(self.outdir, database_name, statement)
                    if callback:
                        callback(database)
                    if database:
                        databases[database.name] = database
                else:
                    database = None

            elif statement.startswith("USE "):
                database_name = _match_name(statement)
                if database_name:
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
                if view_name:
                    database.add_view_pre(view_name, statement)

            elif statement.startswith("CREATE TABLE"):
                table_name = _match_name(statement)
                if table_name:
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

def mysql2fs(fh: IO[str], outdir: str, limits: Optional[list[str]] = None, callback: Optional[Callable] = None) -> None:
    if not limits:
        limits = []
    MyFS_Writer(outdir, limits).fromfile(fh, callback)

def chunkify(elements: Generator[str, None, None], delim: str, maxlen: int) -> Generator[str, None, None]:
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

            def __init__(self, views_path: str, name: str):
                paths = self.Paths(join(views_path, name))
                if not isdir(paths):
                    raise self.Error(f"not a directory '{paths}'")
                self.paths = paths
                self.name = name

            def pre_(self) -> str:
                if not exists(self.paths.pre):
                    return ''
                with open(self.paths.pre) as fob:
                    sql = fob.read().strip()
                return Template(self.TPL_PRE).substitute(name=self.name, sql=sql)
            pre = property(pre_)

            def post_(self) -> str:
                if not exists(self.paths.post):
                    return ''
                with open(self.paths.post) as fob:
                    sql = fob.read().strip()
                return Template(self.TPL_POST).substitute(name=self.name, sql=sql)
            post = property(post_)

        def __init__(self, myfs: MyFS_Reader, fname: str):
            self.paths = self.Paths(join(myfs.path, fname))
            with open(self.paths.init) as fob:
                self.sql_init = fob.read()
            self.name = _match_name(self.sql_init)
            self.myfs = myfs

        def __repr__(self) -> str:
            return f"Database({repr(self.paths.path)})"

        def tables_(self) -> Generator[MyFS.Table, None, None]:
            if not exists(self.paths.tables):
                return None

            for fname in os.listdir(self.paths.tables):
                table = self.myfs.Table(self, fname)
                if (self.name, table.name) in self.myfs.limits:
                    yield table

        tables = property(tables_)

        def views_(self) -> Generator[MyFS.View, None, None]:
            if not exists(self.paths.views):
                return

            for fname in os.listdir(self.paths.views):
                try:
                    view = self.View(self.paths.views, fname)
                except self.View.Error:
                    continue

                yield view
        views = property(views_)

        def tofile(self, fh: IO[str], callback: Optional[Callable] = None) -> None:
            if callback:
                callback(self)

            if self.name != 'mysql':
                print(f'/*!40000 DROP DATABASE IF EXISTS `{self.name}`*/;', file=fh)
            print(self.sql_init, end=' ', file=fh)
            print(f"USE `{self.name}`;", file=fh)

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

        def __init__(self, database: MyFS.Database, fname: str):
            self.paths: _Paths = self.Paths(join(database.paths.tables, fname))
            with open(self.paths.init) as fob:
                self.sql_init = fob.read()
            self.name = _match_name(self.sql_init)
            self.database = database

        def __repr__(self) -> str:
            return f"Table({repr(self.paths.path)})"

        def rows_(self) -> Generator[str, None, None]:
            with open(self.paths.rows) as fob:
                for line in fob:
                    yield line.strip()

        def has_rows(self) -> bool:
            if exists(self.paths.rows) and os.lstat(self.paths.rows).st_size != 0:
                return True
            return False

        rows = property(rows_)

        def triggers_(self) -> list[str]:
            if not exists(self.paths.triggers):
                return []

            with open(self.paths.triggers) as fob:
                return list(_parse_statements(fob, ';;'))

        triggers = property(triggers_)

        def tofile(self, fh: IO[str]) -> None:
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

    def __init__(self, path: str, limits: Optional[list[str]|DBLimits] = None,
                 skip_extended_insert: bool = False,
                 add_drop_database: bool = False,
                 max_extended_insert: Optional[int] = None):
        if not limits:
            limits = []
        self.path = path
        if isinstance(limits, list):
            self.limits = DBLimits(limits)
        else:
            self.limits = limits
        self.skip_extended_insert = skip_extended_insert
        self.add_drop_database = add_drop_database

        if max_extended_insert is None:
            max_extended_insert = self.MAX_EXTENDED_INSERT
        self.max_extended_insert = max_extended_insert

    def __iter__(self) -> Generator[MyFS.Database, None, None]:
        for fname in os.listdir(self.path):
            database = self.Database(self, fname)
            if database.name in self.limits:
                yield database

    def tofile(self, fh: IO[str], callback: Optional[str] = None) -> None:
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

def fs2mysql(fh: IO[str],
             myfs: str,
             limits: Optional[DBLimits] = None,
             callback: Optional[str] = None,
             skip_extended_insert: bool = False,
             add_drop_database: bool = False
             ) -> None:
    MyFS_Reader(myfs, limits, skip_extended_insert, add_drop_database).tofile(fh, callback)

def cb_print(fh: Optional[IO[str]] = None) -> Callable:
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

def backup(myfs: str, etc: str, **kws) -> None:
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
        assert mysqldump_fh is not None
        mysql2fs(mysqldump_fh, myfs, **kws)

        if not exists(etc):
            os.mkdir(etc)

        shutil.copy(PATH_DEBIAN_CNF, etc)

    finally:
        if mna:
            mna.stop()

def restore(myfs: str, etc: str, **kws) -> None:
    if kws.pop('simulate', False):
        simulate = True
    else:
        simulate = False
    mna = None
    if simulate:
        mysql_fh = open("/dev/null", "w")
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
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except:
            return False

    @classmethod
    def get_pid(cls) -> Optional[int]:
        """Returns pid in pidfile if process is running. Otherwise returns None"""
        if not exists(cls.PID_FILE):
            return None

        with open(cls.PID_FILE) as fob:
            pid = int(fob.read().strip())
        if cls._pid_exists(pid):
            return pid
        return None

    @classmethod
    def is_running(cls) -> bool:
        try:
            p = subprocess.run(['mysqladmin', '-s', 'ping'])
            if p.returncode == 0:
                return True
            else:
                return False
        except FileNotFoundError:
            return False

    @classmethod
    def start(cls) -> None:
        if cls.is_running():
            return None

        retries = 2
        for i in range(retries):
            p = subprocess.run([cls.INIT_SCRIPT, "start"],
                               stdout=PIPE, stderr=STDOUT)
            if p.returncode == 0:
                return None
        raise Error(p.stdout)

    @classmethod
    def stop(cls) -> None:
        if not cls.is_running():
            return None

        pid = cls.get_pid()
        if not pid:
            return None

        os.kill(pid, signal.SIGTERM)
        while True:
            if not cls._pid_exists(pid):
                break

            time.sleep(1)

    @classmethod
    def reload(cls) -> None:
        pid = cls.get_pid()
        if not pid:
            raise cls.Error("can't reload, mysql not running")

        os.kill(pid, signal.SIGHUP)

    @classmethod
    def is_accessible(cls) -> bool:
        p = subprocess.run(["mysql", "--defaults-file=/etc/mysql/debian.cnf", "select 1"])
        if p.returncode == 0:
            return True
        else:
            return False

class MysqlNoAuth:
    PATH_VARRUN = '/var/run/mysqld'
    COMMAND = ["mysqld_safe", "--skip-grant-tables", "--skip-networking"]

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

        def cb() -> bool:
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

    def stop(self) -> None:
        if self.stopped:
            return None

        self.stopped = True
        if self.command:
            os.kill(self.command.pid, signal.SIGINT)
            self.command.wait()
            self.command = None

        os.chmod(self.PATH_VARRUN, self.orig_varrun_mode)

        if self.was_running:
            MysqlService.start()
        return None

    def __del__(self) -> None:
        self.stop()
