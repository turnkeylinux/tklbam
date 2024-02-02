class FIFOBuffer:
    """FIFO Style Buffer"""
    def __init__(self, s: str = ""):
        self.buf = s
        self.rpos = 0

    def __len__(self) -> int:
        return len(self.buf)

    def reset(self, pos: int = 0) -> None:
        self.rpos = pos

    def read(self, size: int = 0, read_incomplete: bool = False) -> str:
        howmuch = len(self.buf) - self.rpos
        if size:
            if not read_incomplete and howmuch < size:
                return ''
            buf = self.buf[self.rpos:self.rpos + size]
            self.rpos += len(buf)
            return buf
        else:
            buf = self.buf[self.rpos:]
            self.rpos += len(buf)
            return buf

    def write(self, s: str) -> None:
        self.buf += s

    def readline(self, read_incomplete: bool = False) -> str:
        """Read a line from the buffer.

        If 'read_incomplete' is True, will read back an incomplete line too.
        WARNING: incomplete lines don't increment the read position in the
                 buffer
        """
        buf = self.buf
        rpos = self.rpos

        next_endline = buf.find('\n', rpos)
        if next_endline == -1:
            if not read_incomplete:
                return ''
            return buf[rpos:]

        next_line = buf[rpos: next_endline + 1]
        self.rpos = next_endline + 1
        return next_line

    def getvalue(self) -> str:
        return self.buf
