# 
# Copyright (c) 2010 Liraz Siri <liraz@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
# 
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
import re
from executil import getoutput

class Error(Exception):
    pass

def get_turnkey_version():
    try:
        return file("/etc/turnkey_version").readline().strip()
    except:
        return getoutput("turnkey-version")

def codename(version):
    m = re.match(r'turnkey-(.*?)-([\d\.]+|beta)', version)
    if not m:
        raise Error("can't parse codename from '%s'" % version)

    codename, release = m.groups()
    return codename
