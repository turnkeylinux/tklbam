#!/usr/bin/python
# 
# Copyright (c) 2013 Liraz Siri <liraz@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
# 
# TKLBAM is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
import re
import sys
import getopt
from os.path import *

def _get_turnkey_version(root):
    path = join(root, 'etc/turnkey_version')
    if not exists(path):
        return

    return file(path).read().strip()

def _parse_keyvals(path):
    if not exists(path):
        return
    d = {}
    for line in file(path).readlines():
        line = line.strip()
        if not line:
            continue

        m = re.match(r'(.*?)="?(.*?)"?$', line)
        key, val = m.groups()
        d[key] = val
    return d

def _get_os_release(root):
    path = join(root, "etc/os-release")
    return _parse_keyvals(path)
    
def _get_lsb_release(root):
    path = join(root, "etc/lsb-release")
    return _parse_keyvals(path)
    
def _get_debian_version(root):
    path = join(root, "etc/debian_version")
    if not exists(path):
        return

    s = file(path).read().strip()
    m = re.match(r'^(\d+)\.', s)
    if m:
        return m.group(1)

    if '/' in s:
        return s.replace('/', '_')

def detect_profile(root):
    val = _get_turnkey_version(root)
    if val:
        return val

    os_release = _get_os_release(root)
    if os_release:
        try:
            return "%s-%s" % (os_release['ID'], os_release['VERSION_ID'])
        except KeyError:
            pass

    lsb_release = _get_lsb_release(root)
    if lsb_release:
        try:
            return "%s-%s" % (lsb_release['DISTRIB_ID'].lower(), 
                              lsb_release['DISTRIB_RELEASE'])
        except KeyError:
            pass

    debian_version = _get_debian_version(root)
    if debian_version:
        return "debian-" + debian_version

    return "generic"

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)
    print >> sys.stderr, "Syntax: %s [ path/to/root ]" % sys.argv[0]
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h', ['help'])
    except getopt.GetoptError, e:
        usage(e)

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

    root = args[0] if args else '/'

    print detect_profile(root)

if __name__ == "__main__":
    main()
