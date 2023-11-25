from typing import IO, Self

class Observer:
    def notify(self, subject: Self, event: str, value: list[str]) -> None:
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
    def __init__(self, fh: IO[str]):
        self.fh = fh
        self.observers: list[Observer] = []

    def addObserver(self, observer: Observer) -> None:
        if self.observers.count(observer):
            raise self.Error("observer already registered")
        self.observers.append(observer)

    def delObserver(self, observer: Observer) -> None:
        self.observers.remove(observer)

    def delObserversAll(self) -> None:
        self.observers = []
        
    def __getattr__(self, attr: str) -> str:
        return getattr(self.fh, attr)

    def _notify(self, name: str, val: list[str]) -> None:
        for o in self.observers:
            o.notify(self, name, val)  # type: ignore[arg-type]
            # error: Argument 1 to "notify" of "Observer" has incompatible type "FileEventAdaptor"; expected "Observer"  [arg-type]

    def read(self, size: int = -1) -> str:
        s = self.fh.read(size)
        self._notify('read', [s])
        return s

    def readline(self, size: int = -1) -> str:
        s = self.fh.readline(size)
        self._notify('readline', [s])
        return s

    def readlines(self, size: int = -1) -> list[str]:
        s = self.fh.readlines(size)
        self._notify('readlines', s)
        return s

    def xreadlines(self) -> list[str]:
        # xreadlines is deprecated since Python 2.3 - File objects are iterators by default now.
        s = self.fh.readlines()
        self._notify('xreadlines', s)
        return s

    def write(self, s: list[str]) -> int:
        self._notify('write', s)
        return self.fh.write(" ".join(list(map(str, s))))

    def writelines(self, sequence_of_strings: list[str]) -> None:
        self._notify('writelines', sequence_of_strings)
        return self.fh.writelines(sequence_of_strings)
