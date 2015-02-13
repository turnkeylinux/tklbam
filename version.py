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
import re
import executil
from os.path import *

from utils import AttrDict

class Error(Exception):
    pass

class TurnKeyVersion(AttrDict):
    Error = Error
    def __init__(self, codename, release=None, arch=None):
        AttrDict.__init__(self)
        self.codename = codename
        self.release = release
        self.arch = arch

    def __str__(self):
        return "turnkey-%s-%s-%s" % (self.codename, self.release, self.arch)

    def is_complete(self):
        if self.codename and self.release and self.arch:
            return True

        return False

    @classmethod
    def from_system(cls):
        try:
            system_version = file("/etc/turnkey_version").readline().strip()
        except:
            return

        return cls.from_string(system_version)

    @classmethod
    def from_string(cls, version):
        if not version.startswith('turnkey-'):
            raise Error("not a turnkey version '%s'" % version)

        version = re.sub(r'^turnkey-', '', version)
        
        m = re.match(r'(.*?)-((?:[\d\.]+|beta).*)-(amd64|i386|x86)$', version)
        if m:
            name, release, arch = m.groups()
            return cls(name, release, arch)

        m = re.match(r'(.*?)-((?:[\d\.]+|beta).*?)-?$', version)
        if m:
            name, release = m.groups()
            return cls(name, release)

        m = re.match(r'(.*?)-?$', version)
        if m:
            name = m.group(1)
            return cls(name)

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

def detect_profile_id(root='/'):
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
