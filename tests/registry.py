import sys
import os
from os.path import *

class _Registry(object):
    def __init__(self, path=None):
        if path is None:
            self.path = os.environ.get('TKLBAM_REGISTRY', '/tmp/registry')
        else:
            self.path = path

    def foo(self, val=None):
        path = join(self.path, "foo")

        if val is None:
            if not exists(path):
                return None

            return file(path).read().rstrip()

        else:
            file(path, "w").write("%s\n" % val)
    foo = property(foo, foo)

registry = _Registry()

def main():
    args = sys.argv[1:]

    print `registry.foo`
    if args:
        registry.foo = args[0]

if __name__ == "__main__":
    main()
