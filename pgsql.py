#
# Copyright (c) 2013 Liraz Siri <liraz@turnkeylinux.org>
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
from os.path import * # join

import re
import subprocess
import shutil

from dblimits import DBLimits

FNAME_GLOBALS = ".globals.sql"
FNAME_MANIFEST = "manifest.txt"

class Error(Exception):
    pass

def su(command):
    return ["su", "postgres", "-c", command]

def list_databases():
    p = subprocess.run(su('psql -l'), capture_output=True, text=True)
    for line in p.stdout.splitlines():
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

    p1 = subprocess.run(su(pg_dump), capture_output=True, text=True)
    manifest = subprocess.run(["tar", "xvC", path], stdin=p1.stdout)
    with open(join(path, FNAME_MANIFEST), "w") as fob:
        fob.write(manifest + "\n")

def restoredb(dbdump, dbname, tlimits=[]):
    with open(join(dbdump, FNAME_MANIFEST)) as fob:
        manifest = fob.read().splitlines()

    subprocess.run(su("dropdb " + dbname))

    orig_cwd = os.getcwd()
    os.chdir(dbdump)

    try:
        command = "tar c %s 2>/dev/null" % " ".join(manifest)
        pg_restore_com = ["pg_restore", "--create", "--format=tar"]
        for (table, sign) in tlimits:
            if sign:
                pg_restore_com.append(f"--table={table}")
        p1 = subprocess.run(["tar", "c", *manifest], capture_output=True)
        p2 = subprocess.run(pg_restore_com, stdin=p1.stdout, capture_output=True)
        p3 = subprocess.run(su("cd $HOME; psql"), stdin=p2.stdout)
        
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

    globals = subprocess.run(su("pg_dumpall --globals"), capture_output=True, text=True).stdout
    with open(join(outdir, FNAME_GLOBALS), "w") as fob:
        fob.write(globals)

def fs2pgsql(outdir, limits=[], callback=None):
    limits = DBLimits(limits)
    for (database, table) in limits.tables:
        if (database, table) not in limits:
            raise Error("can't exclude %s/%s: table excludes not supported for postgres" % (database, table))

    # load globals first, suppress noise (e.g., "ERROR: role "postgres" already exists)
    with open(join(outdir, FNAME_GLOBALS)) as fob:
        globals = fob.read()
    subprocess.run([su("psql -q -o /dev/null"), globals], check_output=True)

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
        print("database: " + val, file=fh)

    return func

def backup(outdir, limits=[], callback=None):
    if isdir(outdir):
        shutil.rmtree(outdir)

    if not exists(outdir):
        os.makedirs(outdir)

    try:
        pgsql2fs(outdir, limits, callback)
    except Exception as e:
        if isdir(outdir):
            shutil.rmtree(outdir)
        raise Error("pgsql backup failed: " + str(e))

def restore(path, limits=[], callback=None):
    try:
        fs2pgsql(path, limits, callback=callback)
    except Exception as e:
        raise Error("pgsql restore failed: " + str(e))

class PgsqlService:
    INIT_SCRIPT = "/etc/init.d/postgresql"

    @classmethod
    def is_running(cls):
        try:
            p = subprocess.run([cls.INIT_SCRIPT, "status"])
            if p.returncode == 0:
                return True
            else:
                return False
        except FileNotFoundError:
            return False
