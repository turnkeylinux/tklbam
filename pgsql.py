#
# Copyright (c) 2013 Liraz Siri <liraz@turnkeylinux.org>
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

import re
import commands
import shutil

from executil import system, getoutput, getoutput_popen

from dblimits import DBLimits

FNAME_GLOBALS = ".globals.sql"
FNAME_MANIFEST = "manifest.txt"

class Error(Exception):
    pass

def su(command):
    return "su postgres -c" + commands.mkarg(command)

def list_databases():
    for line in getoutput(su('psql -l')).splitlines():
        m = re.match(r'^ (\S+?)\s', line)
        if not m:
            continue

        name = m.group(1)
        yield name

def dumpdb(outdir, name, tlimits=[]):
    path = join(outdir, name)
    if isdir(path):
        shutil.rmtree(path)
    os.makedirs(path)

    # format pg_dump command
    pg_dump = "pg_dump --format=tar"
    for (table, sign) in tlimits:
        if sign:
            pg_dump += " --table=" + table
        else:
            pg_dump += " --exclude-table=" + table
    pg_dump += " " + name

    manifest = getoutput(su(pg_dump) + " | tar xvC %s" % path)
    file(join(path, FNAME_MANIFEST), "w").write(manifest + "\n")

def restoredb(dbdump, dbname, tlimits=[]):
    manifest = file(join(dbdump, FNAME_MANIFEST)).read().splitlines()
    # remove any malformed entries
    manifest = [i for i in manifest if not i.endswith('Permission denied')]
    try:
        getoutput(su("dropdb " + dbname))
    except:
        pass

    orig_cwd = os.getcwd()
    os.chdir(dbdump)

    try:
        command = "tar c %s 2>/dev/null" % " ".join(manifest)
        command += " | pg_restore --create --dbname=postgres --format=tar"
        for (table, sign) in tlimits:
            if sign:
                command += " --table=" + table
        command += " | " + su("cd $HOME; psql")
        system(command)

    finally:
        os.chdir(orig_cwd)

def pgsql2fs(outdir, limits=[], callback=None):
    limits = DBLimits(limits)

    for dbname in list_databases():
        if dbname not in limits or dbname == 'postgres' or re.match(r'template\d', dbname):
            continue

        if callback:
            callback(dbname)

        dumpdb(outdir, dbname, limits[dbname])

    globals = getoutput(su("pg_dumpall --globals"))
    file(join(outdir, FNAME_GLOBALS), "w").write(globals)

def fs2pgsql(outdir, limits=[], callback=None):
    limits = DBLimits(limits)
    for (database, table) in limits.tables:
        if (database, table) not in limits:
            raise Error("can't exclude %s/%s: table excludes not supported for postgres" % (database, table))

    # load globals first, suppress noise (e.g., "ERROR: role "postgres" already exists)
    globals = file(join(outdir, FNAME_GLOBALS)).read()
    getoutput_popen(su("psql -q -o /dev/null"), globals)

    for dbname in os.listdir(outdir):

        fpath = join(outdir, dbname)
        if not isdir(fpath) or dbname not in limits:
            continue

        if callback:
            callback(dbname)

        restoredb(fpath, dbname, limits[dbname])

def cb_print(fh=None):
    if not fh:
        fh = sys.stdout

    def func(val):
        print >> fh, "database: " + val

    return func

def backup(outdir, limits=[], callback=None):
    if isdir(outdir):
        shutil.rmtree(outdir)

    if not exists(outdir):
        os.makedirs(outdir)

    try:
        pgsql2fs(outdir, limits, callback)
    except Exception, e:
        if isdir(outdir):
            shutil.rmtree(outdir)
        raise Error("pgsql backup failed: " + str(e))

def restore(path, limits=[], callback=None):
    try:
        fs2pgsql(path, limits, callback=callback)
    except Exception, e:
        raise Error("pgsql restore failed: " + str(e))

class PgsqlService:
    INIT_SCRIPT = "/etc/init.d/postgresql"

    @classmethod
    def is_running(cls):
        try:
            getoutput(cls.INIT_SCRIPT, "status")
            return True
        except:
            return False

