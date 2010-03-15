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
        for path in self:
            if self[path]:
                yield path
    includes = property(includes)

    def excludes(self):
        for path in self:
            if not self[path]:
                yield path
    excludes = property(excludes)

    def __contains__(self, path):
        while path not in ('', '/'):
            if dict.__contains__(self, path):
                return self[path]
            path = dirname(path)

        return self.default
