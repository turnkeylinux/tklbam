class FIFOBuffer:
    """FIFO Style Buffer"""
    def __init__(self, s=""):
        self.buf = s
        self.rpos = 0

    def __len__(self):
        return len(self.buf)
    
    def reset(self, pos=0):
        self.rpos = pos

    def read(self, size=0, read_incomplete=False):
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

    def write(self, s):
        self.buf += s

    def readline(self, read_incomplete=False):
        """Read a line from the buffer.
        
        If 'read_incomplete' is True, will read back an incomplete line too.
           WARNING: incomplete lines don't increment the read position in the buffer
        """
        buf = self.buf
        rpos = self.rpos

        next_endline = buf.find('\n', rpos)
        if next_endline == -1:
            if not read_incomplete:
                return ''
            return buf[rpos:]

        next_line = buf[rpos : next_endline + 1]
        self.rpos = next_endline + 1
        return next_line

    def getvalue(self):
        return self.buf
    
