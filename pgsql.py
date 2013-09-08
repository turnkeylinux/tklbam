#
# Copyright (c) 2013 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
import os
from os.path import *

import re
import commands
import shutil

from executil import system, getoutput, getoutput_popen

FNAME_GLOBALS = ".globals.sql"
FNAME_MANIFEST = "manifest.txt"

def _pg(command):
    return "su postgres -c" + commands.mkarg(command)

def list_databases():
    for line in getoutput(_pg('psql -l')).splitlines():
        m = re.match(r'^ (\S+?)\s', line)
        if not m:
            continue

        name = m.group(1)
        yield name

def dumpdb(outdir, name):
    path = join(outdir, name)
    if isdir(path):
        shutil.rmtree(path)
    os.makedirs(path)

    manifest = getoutput(_pg("pg_dump --format=tar " + name) + " | tar xvC %s" % path)
    file(join(path, FNAME_MANIFEST), "w").write(manifest + "\n")

def restoredb(dbdump, dbname):
    manifest = file(join(dbdump, FNAME_MANIFEST)).read().splitlines()

    try:
        getoutput(_pg("dropdb " + dbname))
    except:
        pass

    orig_cwd = os.getcwd()
    os.chdir(dbdump)

    try:
        command = "tar c %s 2>/dev/null" % " ".join(manifest)
        command += " | pg_restore --create --format=tar"
        command += " | " + _pg("psql")

        system(command)
        
    finally:
        os.chdir(orig_cwd)

def pgsql2fs(outdir, limits):
    for name in list_databases():
        if name == 'postgres' or re.match(r'template\d', name):
            continue

        dumpdb(outdir, name)

    globals = getoutput(_pg("pg_dumpall --globals"))
    file(join(outdir, FNAME_GLOBALS), "w").write(globals)

def fs2pgsql(outdir, limits):

    # load globals first, suppress noise (e.g., "ERROR: role "postgres" already exists)
    globals = file(join(outdir, FNAME_GLOBALS)).read()
    getoutput_popen(_pg("psql -q -o /dev/null"), globals)

    for fname in os.listdir(outdir):
        fpath = join(outdir, fname)
        if not isdir(fpath):
            continue

        restoredb(fpath, fname)


