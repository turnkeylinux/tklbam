# moral: you can't set a Python property to None if you use a single function

class CantSetNone(object):
    def __init__(self):
        self._test = None

    def test(self, val=None):
        print "test(%s)" % `val`
        if val is None:
            return self._test
        else:
            self._test = val
    test = property(test, test)

class CanSetNone(object):
    def __init__(self):
        self._test = None

    def read_test(self):
        print "read_test()"
        return self._test

    def write_test(self, val):
        print "write_test(%s)" % val
        self._test = val

    test = property(read_test, write_test)

class UNDEFINED:
    pass

class ShortCanSetNone(object):
    def __init__(self):
        self._test = None

    def test(self, val=UNDEFINED):
        print "test(%s)" % `val`
        if val is UNDEFINED:
            return self._test
        else:
            self._test = val
    test = property(test, test)
