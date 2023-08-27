class Observer:
    def notify(self, subject, event, value):
        pass
    
class FileEventAdaptor:
    """Example usage:
    class MyObserver(Observer):
       def notify(self, obj, event, value):
          print "event '%s': %s" % (event, value)
      
    f = file("/dev/null", "r+")
    f = FileEventAdaptor(f)
    f.addObserver(Observer())
    """
    class Error(Exception):
        pass
    def __init__(self, fh):
        self.fh = fh
        self.observers = []

    def addObserver(self, observer):
        if self.observers.count(observer):
            raise self.Error("observer already registered")
        self.observers.append(observer)

    def delObserver(self, observer):
        self.observers.remove(observer)

    def delObserversAll(self):
        self.observers = []
        
    def __getattr__(self, attr):
        return getattr(self.fh, attr)

    def _notify(self, name, val):
        for o in self.observers:
            o.notify(self, name, val)

    def read(self, size=-1):
        s = self.fh.read(size)
        self._notify('read', s)
        return s

    def readline(self, size=-1):
        s = self.fh.readline(size)
        self._notify('readline', s)
        return s

    def readlines(self, size=-1):
        s = self.fh.readlines(size)
        self._notify('readlines', s)
        return s

    def xreadlines(self):
        s = self.fh.xreadlines()
        self._notify('xreadlines', s)
        return s

    def write(self, str):
        self._notify('write', str)
        return self.fh.write(str)

    def writelines(self, sequence_of_strings):
        self._notify('writelines', sequence_of_strings)
        return self.fh.writelines(sequence_of_strings)
