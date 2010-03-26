"""
Module that contains classes for capturing stdout/stderr.

Warning: if you aren't careful, exceptions raised after trapping stdout/stderr
will cause your program to exit silently.

StdTrap usage:
    trap = StdTrap()
    try:
        expression
    finally:
        trap.close()

    trapped_stdout = trap.stdout.read()
    trapped_stderr = trap.stderr.read()

UnitedStdTrap usage:

    trap = UnitedStdTrap()
    try:
        expression
    finally:
        trap.close()

    trapped_output = trap.std.read()

"""

import os
import sys
import pty
import errno
import select
from StringIO import StringIO

import signal

class Error(Exception):
    pass

class SignalEvent:
    SIG = signal.SIGUSR1
    
    @classmethod
    def send(cls, pid):
        """send signal event to pid"""
        os.kill(pid, cls.SIG)

    def _sighandler(self, sig, frame):
        self.value = True

    def __init__(self):
        self.value = False
        signal.signal(self.SIG, self._sighandler)
        
    def isSet(self):
        return self.value

    def clear(self):
        self.value = False
        
class Pipe:
    def __init__(self):
        r, w = os.pipe()
        self.r = os.fdopen(r, "r", 0)
        self.w = os.fdopen(w, "w", 0)

def set_blocking(fd, block):
    import fcntl
    arg = os.O_NONBLOCK
    if block:
        arg =~ arg
    fcntl.fcntl(fd, fcntl.F_SETFL, arg)

class StdTrap:
    class Splicer:
        """Inside the _splice method, stdout is intercepted at
        the file descriptor level by redirecting it to a pipe. Now
        whenever someone writes to stdout, we can read it out the
        other end of the pipe.

        The problem is that if we don't suck data out of this pipe
        then eventually if enough data is written to it the process
        writing to stdout will be blocked by the kernel, which means
        we'll be limited to capturing up to 65K of output and after
        that anything else will hang. So to solve that we create a
        splicer subprocess to get around the OS's 65K buffering
        limitation. The splicer subprocess's job is to suck the pipe
        into a local buffer and spit it back out back to the parent
        process through a second pipe created for this purpose"""
        @staticmethod
        def _splice(spliced_fd, usepty, transparent):
            """splice into spliced_fd -> (splicer_pid, splicer_reader, orig_fd_dup)"""
               
            # duplicate the fd we want to trap for safe keeping
            orig_fd_dup = os.dup(spliced_fd)

            # create a bi-directional pipe/pty
            # data written to w can be read from r
            if usepty:
                r, w = os.openpty()
            else:
                r, w = os.pipe()

            # splice into spliced_fd by overwriting it
            # with the newly created `w` which we can read from with `r`
            os.dup2(w, spliced_fd)
            os.close(w)
            
            spliced_fd_reader = os.fdopen(r, "r", 0)
            splicer_pipe = Pipe()

            # the child process uses this to signal the parent to continue
            # the parent uses this to signal the child to close
            signal_event = SignalEvent()
            
            splicer_pid = os.fork()
            if splicer_pid:
                signal_continue = signal_event
                
                splicer_pipe.w.close()
                spliced_fd_reader.close()

                while not signal_continue.isSet():
                    pass

                return splicer_pid, splicer_pipe.r, orig_fd_dup
            else:
                signal_closed = signal_event
                
                # child splicer
                splicer_pipe.r.close()

                # we don't need this copy of spliced_fd
                # keeping it open will prevent it from closing
                os.close(spliced_fd)

                set_blocking(spliced_fd_reader.fileno(), False)
                set_blocking(splicer_pipe.w.fileno(), False)
                
                def os_write_all(fd, data):
                    while data:
                        len = os.write(fd, data)
                        if len < 0:
                            raise Error("os.write error")
                        data = data[len:]
                        

                poll = select.poll()
                poll.register(spliced_fd_reader, select.POLLIN | select.POLLHUP)
                
                buf = ""
                
                closed = False
                SignalEvent.send(os.getppid())
                
                while True:
                    if not closed:
                        closed = signal_closed.isSet()

                    if closed and not buf:
                        break

                    try:
                        events = poll.poll()
                    except select.error:
                        events = ()

                    for fd, mask in events:
                        if fd == spliced_fd_reader.fileno():
                            if mask & select.POLLIN:

                                data = spliced_fd_reader.read()
                                
                                buf += data
                                poll.register(splicer_pipe.w)
                                
                                if transparent:
                                    # if our dupfd file descriptor has been closed
                                    # redirect output to the originally trapped fd
                                    try:
                                        os_write_all(orig_fd_dup, data)
                                    except OSError, e:
                                        if e[0] == errno.EBADF:
                                            os_write_all(spliced_fd, data)
                                        else:
                                            raise

                            if mask & select.POLLHUP:
                                closed = True
                                poll.unregister(fd)
                                
                        elif fd == splicer_pipe.w.fileno():
                            if mask & select.POLLOUT:
                                written = os.write(splicer_pipe.w.fileno(), buf)
                                buf = buf[written:]
                                if not buf:
                                    poll.unregister(splicer_pipe.w)

                os._exit(0)
          
        def __init__(self, spliced_fd, usepty=False, transparent=False):
            vals = self._splice(spliced_fd, usepty, transparent)
            self.splicer_pid, self.splicer_reader, self.orig_fd_dup = vals

            self.spliced_fd = spliced_fd

        def close(self):
            """closes the splice -> captured output"""
            # dupping orig_fd_dup -> spliced_fd does two things:
            # 1) it closes spliced_fd - signals our splicer process to stop reading
            # 2) it overwrites spliced_fd with a dup of the unspliced original fd
            os.dup2(self.orig_fd_dup, self.spliced_fd)
            SignalEvent.send(self.splicer_pid)
            
            os.close(self.orig_fd_dup)

            captured = self.splicer_reader.read()
            os.waitpid(self.splicer_pid, 0)

            return captured

    def __init__(self, stdout=True, stderr=True, usepty=False, transparent=False):
        self.usepty = pty
        self.transparent = transparent

        self.stdout_splice = None
        self.stderr_splice = None
        
        if stdout:
            sys.stdout.flush()
            self.stdout_splice = StdTrap.Splicer(sys.stdout.fileno(), usepty, transparent)

        if stderr:
            sys.stderr.flush()
            self.stderr_splice = StdTrap.Splicer(sys.stderr.fileno(), usepty, transparent)
            
        self.stdout = None
        self.stderr = None

    def close(self):
        if self.stdout_splice:
            sys.stdout.flush()
            self.stdout = StringIO(self.stdout_splice.close())

        if self.stderr_splice:
            sys.stderr.flush()
            self.stderr = StringIO(self.stderr_splice.close())

class UnitedStdTrap(StdTrap):
    def __init__(self, usepty=False, transparent=False):
        self.usepty = usepty
        self.transparent = transparent
        
        sys.stdout.flush()
        self.stdout_splice = self.Splicer(sys.stdout.fileno(), usepty, transparent)

        sys.stderr.flush()
        self.stderr_dupfd = os.dup(sys.stderr.fileno())
        os.dup2(sys.stdout.fileno(), sys.stderr.fileno())

        self.std = self.stderr = self.stdout = None

    def close(self):
        sys.stdout.flush()
        self.std = self.stderr = self.stdout = StringIO(self.stdout_splice.close())

        sys.stderr.flush()
        os.dup2(self.stderr_dupfd, sys.stderr.fileno())
        os.close(self.stderr_dupfd)

def silence(callback, args=()):
    """convenience function - traps stdout and stderr for callback.
    Returns (ret, trapped_output)
    """
    
    trap = UnitedStdTrap()
    try:
        ret = callback(*args)
    finally:
        trap.close()

    return ret

def getoutput(callback, args=()):
    trap = UnitedStdTrap()
    try:
        callback(*args)
    finally:
        trap.close()

    return trap.std.read()

def test(transparent=False):
    def sysprint():
        os.system("echo echo stdout")
        os.system("echo echo stderr 1>&2")

    print "--- 1:"
    trap1 = UnitedStdTrap(transparent=transparent)
    trap2 = UnitedStdTrap(transparent=transparent)
    print "hello world"
    trap2.close()
    print "trap2: " + trap2.std.read(),
    trap1.close(),
    print "trap1: " + trap1.std.read(),

    print "--- 2:"
    
    s = UnitedStdTrap(transparent=transparent)
    print "printing to united stdout..."
    print >> sys.stderr, "printing to united stderr..."
    sysprint()
    s.close()

    print 'trapped united stdout and stderr: """%s"""' % s.std.read()
    print >> sys.stderr, "printing to stderr"

    print "--- 3:"
    s = None
    s = UnitedStdTrap(transparent=transparent)
    print "printing to united stdout..."
    print >> sys.stderr, "printing to united stderr..."
    sysprint()
    s.close()

    print 'trapped united stdout and stderr: """%s"""' % s.std.read()
    print >> sys.stderr, "printing to stderr"

    print "--- 4:"
    
    s = StdTrap(transparent=transparent)
    s.close()
    print 'nothing in stdout: """%s"""' % s.stdout.read()
    print 'nothing in stderr: """%s"""' % s.stderr.read()

    print "--- 5:"

    s = StdTrap(transparent=transparent)
    print "printing to stdout..."
    print >> sys.stderr, "printing to stderr..."
    sysprint()
    s.close()

    print 'trapped stdout: """%s"""' % s.stdout.read()
    print >> sys.stderr, 'trapped stderr: """%s"""' % s.stderr.read()


def test2():
    trap = StdTrap(stdout=True, stderr=True, transparent=False)

    try:
        for i in range(1000):
            print "A" * 70
            sys.stdout.flush()
            print >> sys.stderr, "B" * 70
            sys.stderr.flush()
            
    finally:
        trap.close()

    assert len(trap.stdout.read()) == 71000
    assert len(trap.stderr.read()) == 71000

def test3():
    trap = UnitedStdTrap(transparent=True)
    try:
        for i in range(10):
            print "A" * 70
            sys.stdout.flush()
            print >> sys.stderr, "B" * 70
            sys.stderr.flush()
    finally:
        trap.close()

    print len(trap.stdout.read())

def test4():
    import time
    s = StdTrap(transparent=True)
    s.close()
    print 'nothing in stdout: """%s"""' % s.stdout.read()
    print 'nothing in stderr: """%s"""' % s.stderr.read()

if __name__ == '__main__':
    test(False)
    print
    print "=== TRANSPARENT MODE ==="
    print
    test(True)
    test2()
    test3()
     
