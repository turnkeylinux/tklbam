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
from os.path import join, exists
from typing import Optional, Self
from dataclasses import dataclass

class Error(Exception):
    pass

@dataclass
class TurnKeyVersion:
    Error = Error
    codename: str
    release: Optional[str] = None
    arch: Optional[str] = None

    def __str__(self) -> str:
        return f"turnkey-{self.codename}-{self.release}-{self.arch}"

    def is_complete(self) -> bool:
        if self.codename and self.release and self.arch:
            return True

        return False

    @classmethod
    def from_system(cls) -> Optional[Self]:
        try:
            with open("/etc/turnkey_version") as fob:
                system_version = fob.readline().strip()
        except:
            return None

        return cls.from_string(system_version)

    @classmethod
    def from_string(cls, version: str) -> Optional[Self]:
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
        return None

def _get_turnkey_version(root: str) -> Optional[str]:
    path = join(root, 'etc/turnkey_version')
    if not exists(path):
        return None

    with open(path) as fob:
        return fob.read().strip()

def _parse_keyvals(path: str) -> Optional[dict[str, str]]:
    if not exists(path):
        return None
    d = {}
    with open(path) as fob:
        for line in fob.readlines():
            line = line.strip()
            if not line:
                continue

            m = re.match(r'(.*?)="?(.*?)"?$', line)
            if isinstance(m, re.Match):
                key, val = m.groups()
                d[key] = val
    return d

def _get_os_release(root: str) -> Optional[dict[str, str]]:
    path = join(root, "etc/os-release")
    return _parse_keyvals(path)
    
def _get_lsb_release(root: str) -> Optional[dict[str, str]]:
    path = join(root, "etc/lsb-release")
    return _parse_keyvals(path)
    
def _get_debian_version(root) -> Optional[str]:
    path = join(root, "etc/debian_version")
    if not exists(path):
        return None

    with open(path) as fob:
        s = fob.read().strip()
    m = re.match(r'^(\d+)\.', s)
    if m:
        return m.group(1)

    if '/' in s:
        return s.replace('/', '_')
    return None

def detect_profile_id(root: str = '/') -> str:
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
