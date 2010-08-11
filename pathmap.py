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
import glob
from os.path import *

class PathMap(dict):
    @staticmethod
    def _expand(path):
        def needsglob(path):
            for c in ('*?[]'):
                if c in path:
                    return True
            return False

        path = abspath(path)
        if needsglob(path):
            return glob.glob(path)
        else:
            return [ path ]

    def __init__(self, paths):
        self.default = True
        for path in paths:
            if path[0] == '-':
                path = path[1:]
                sign = False
            else:
                self.default = False
                sign = True

            for expanded in self._expand(path):
                self[expanded] = sign

    def includes(self):
        return [ path for path in self if self[path] ]
    includes = property(includes)

    def excludes(self):
        return [ path for path in self if not self[path] ]
    excludes = property(excludes)

    def __contains__(self, path):
        while path not in ('', '/'):
            if dict.__contains__(self, path):
                return self[path]
            path = dirname(path)

        return self.default
