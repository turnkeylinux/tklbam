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
from os.path import join, isdir, exists

import re
import subprocess
from subprocess import PIPE
import shutil
from typing import Generator, Optional, Callable, IO
import pwd
import grp

from dblimits import DBLimits

import logging
logging.basicConfig(level=logging.DEBUG)

FNAME_GLOBALS = ".globals.sql"
FNAME_MANIFEST = "manifest.txt"

class Error(Exception):
    pass

def su(command: list[str]) -> list[str]:
    logging.debug(f'["su", "postgres", "-c", *command]')
    return ["su", "postgres", "-c", *command]

def check_user(user: str = 'postgres', check_group: bool = False) -> bool:
    try:
        uid = pwd.getpwnam(user).pw_uid
        if check_group:
            gid = grp.getgrnam(user).gr_gid
        return True
    except KeyError:
        return False

def list_databases() -> Generator[str, None, None]:
    p = subprocess.run(su(['psql", "-l']), capture_output=True, text=True)
    for line in p.stdout.splitlines():
        m = re.match(r'^ (\S+?)\s', line)
        if not m:
            continue

        name = m.group(1)
        yield name

def dumpdb(outdir: str, name: str, tlimits: list[tuple[str, str|bool]] = []) -> None:
    path = join(outdir, name)
    if isdir(path):
        shutil.rmtree(path)
    os.makedirs(path)

    # format pg_dump command
    pg_dump = ["pg_dump", "--format=tar"]
    for (table, sign) in tlimits:  # XXX this might be an issue?
        if sign:
            pg_dump.append("--table=" + table)
        else:
            pg_dump.append("--exclude-table=" + table)
    pg_dump.append(name)

    p1 = subprocess.Popen(su(pg_dump), stdout=PIPE)
    p2 = subprocess.Popen(["tar", "xvC", path], stdin=p1.stdout, stdout=PIPE)
    manifest, err = p2.communicate()
    if err:
        raise Error(err.decode())
    with open(join(path, FNAME_MANIFEST), "w") as fob:
        fob.write(f'{manifest.decode()}\n')

def restoredb(dbdump: str, dbname: str, tlimits: list[tuple[str, str|bool]] = []) -> None:
    with open(join(dbdump, FNAME_MANIFEST)) as fob:
        manifest = fob.read().splitlines()

    subprocess.run(su(["dropdb", dbname]))

    orig_cwd = os.getcwd()
    os.chdir(dbdump)

    try:
        # command = "tar c %s 2>/dev/null" % " ".join(manifest)
        pg_restore_com = ["pg_restore", "--create", "--format=tar"]
        for (table, sign) in tlimits:  # XXX this might be an issue? (again)
            if sign:
                assert isinstance(sign, bool)
                pg_restore_com.append(f"--table={table}")
        p1 = subprocess.Popen(["tar", "c", *manifest], stdout=PIPE, stderr=PIPE)
        p2 = subprocess.Popen(pg_restore_com, stdin=p1.stdout, stdout=PIPE, stderr=PIPE)
        p3 = subprocess.Popen(su(["psql"]), stdin=p2.stdout, stdout=PIPE, stderr=PIPE)
        p1.wait()
        p2.wait()
        out, err = p3.communicate()
        if p1.returncode != 0:
            raise Error(p1.stderr)
        elif p2.returncode != 0:
            raise Error(p2.stderr)
        if err:
            raise Error(err.decode())
        logging.debug(f'pgsql.restordb: {out.decode()}')


    finally:
        os.chdir(orig_cwd)

def pgsql2fs(outdir: str, limits: Optional[list[str]|DBLimits] = None, callback: Optional[Callable] = None) -> None:
    if not isinstance(limits, DBLimits):
        limits = DBLimits(limits)

    for dbname in list_databases():
        if dbname not in limits or dbname == 'postgres' or re.match(r'template\d', dbname):
            continue

        if callback:
            callback(dbname)

        dumpdb(outdir, dbname, limits[dbname])

    globals = subprocess.run(["pg_dumpall", "--globals"], user='postgres', capture_output=True, text=True).stdout
    with open(join(outdir, FNAME_GLOBALS), "w") as fob:
        fob.write(globals)

def fs2pgsql(outdir: str, limits: Optional[list[str]] = None, callback: Optional[Callable] = None) -> None:
    if not limits:
        limits = []
    limits_ = DBLimits(limits)
    if limits_.tables is not None:
        for (database, table) in limits_.tables:
            if (database, table) not in limits:
                raise Error(f"can't exclude {database}/{table}: table"
                            " excludes not supported for postgres")

    # load globals first, suppress noise (e.g., "ERROR: role "postgres" already exists)
    with open(join(outdir, FNAME_GLOBALS)) as fob:
        globals = fob.read()
    subprocess.check_output(["psql", "-q", "-o", "/dev/null", globals])

    for dbname in os.listdir(outdir):

        fpath = join(outdir, dbname)
        if not isdir(fpath) or dbname not in limits:
            continue

        if callback:
            callback(dbname)

        restoredb(fpath, dbname, limits_[dbname])

def cb_print(fh: Optional[IO[str]] = None) -> Callable:
    if not fh:
        fh = sys.stdout

    def func(val: str) -> None:
        print("database: " + val, file=fh)

    return func

def backup(outdir: str, limits: Optional[list[str]] = [], callback: Optional[Callable] = None) -> None:
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

def restore(path: str, limits: list[str] = [], callback: Optional[Callable] = None) -> None:
    try:
        fs2pgsql(path, limits, callback=callback)
    except Exception as e:
        raise Error("pgsql restore failed: " + str(e))

class PgsqlService:
    INIT_SCRIPT = "/etc/init.d/postgresql"

    @classmethod
    def is_running(cls) -> bool:
        try:
            p = subprocess.run([cls.INIT_SCRIPT, "status"])
            if p.returncode == 0:
                return True
            else:
                return False
        except FileNotFoundError:
            return False
