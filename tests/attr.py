class Foo(object):
    dynamic_props = ['foo', 'bar']
    dynamic_vals = {}

    def __getattr__(self, name):
        print "__getattr__(%s)" % (name)

        if name in self.dynamic_props:
            if name not in self.dynamic_vals:
                return None

            return self.dynamic_vals[name]

        return object.__getattr__(self, name)

    def __setattr__(self, name, val):
        print "__setattr__(%s, %s)" % (name, `val`)

        try:
            if name in self.dynamic_props:
                object.__getattr__(self, name)

            print "object.__setattr__(%s, %s)" % (name, val)
            object.__setattr__(self, name, val)
        except AttributeError:
            self.dynamic_vals[name] = val

    def __init__(self):
        self._bar = None

    def bar(self, val=None):
        if val is None:
            return self._bar
        self._bar = val
    bar = property(bar, bar)
