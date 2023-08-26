# Copyright (c) 2007-2011 Liraz Siri <liraz@turnkeylinux.org>
#               2019 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# turnkey-command is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.

"A high-level interface for command execution"

import os
import signal
import time
import select
import re
import sys
import errno
import termios

import popen4
from fifobuffer import FIFOBuffer
from fileevent import *

from shlex import quote
from io import StringIO


def fmt_argv(argv):
    if not argv:
        return ""

    args = argv[1:]

    for i, arg in enumerate(args):
        if re.search(r"[\s'\"]", arg):
            args[i] = shlex(arg)
        else:
            args[i] = " " + arg

    return argv[0] + " " + " ".join(args)


def get_blocking(fd):
    import fcntl
    flags = fcntl.fcntl(fd, fcntl.F_GETFL, 0)
    if flags & os.O_NONBLOCK:
        return False
    else:
        return True


def set_blocking(fd, blocking):
    import fcntl
    flags = fcntl.fcntl(fd, fcntl.F_GETFL, 0)
    if flags == -1:
        flags = 0

    if not blocking:
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    else:
        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)


class FileEnhancedRead:
    def __init__(self, fh):
        self.fh = fh

    def __getattr__(self, attr):
        return getattr(self.fh, attr)

    def read(self, size=-1, timeout=None):
        """A better read where you can (optionally) configure how long to wait
        for data.

        Arguments:

        'timeout': how many seconds to wait before for output.

                If no output return None.
                If EOF return ''

        """
        if timeout is None:
            return self.fh.read(size)

        if timeout < 0:
            timeout = 0

        fd = self.fh.fileno()
        output = None

        p = select.poll()
        p.register(fd, select.POLLIN | select.POLLHUP)

        started = time.time()
        try:
            events = p.poll(timeout * 1000)
        except select.error:
            return self.read(size, timeout - (time.time() - started))

        if not events:
            return None

        mask = events[0][1]
        if mask & select.POLLIN:

            bytes = None

            orig_blocking = get_blocking(fd)
            set_blocking(fd, False)
            try:
                bytes = self.fh.read(size)
            except IOError as e:
                if e.errno != errno.EAGAIN:
                    raise
            finally:
                set_blocking(fd, orig_blocking)

            return bytes

        if mask & select.POLLHUP:
            return ''


class Command(object):
    """Convenience module for executing a command

    attribute notes::

        'exitcode' - None if the process hasn't exited, exitcode otherwise

        'output' - None if the process hasn't exited and fromchild hasn't
                   been accessed, the full output of the process

        'running' - True if process is still running, False otherwise

        'terminated' - Returns signal number if terminated, None otherwise

    Usage example::

        c = Command("./test.py")
        if c.running:
            c.wait()

        assert c.running is False

        print c.output

        c = Command("./test.py")

        # Unless you read from command.fromchild or use
        # command.outputsearch() command.output will be None until the
        # command finishes.

        while c.output is None:
            time.sleep(1)

        print "output = '%s', exitcode = %d" % (c.output, c.exitcode)

        c = Command("cat", pty=True)
        print >> c.tochild, "test"
        print c.fromchild.readline(),

    """
    class Error(Exception):
        pass

    class _ChildObserver(Observer):
        def __init__(self, outputbuf, debug=False):
            self.debug = debug
            self.outputbuf = outputbuf

        def _dprint(self, event, msg):
            if self.debug:
                print("# EVENT '%s':\n%s" % (event, msg), file=sys.stderr)

        def notify(self, subject, event, val):
            if event in ('read', 'readline'):
                self._dprint(event, val)
                self.outputbuf.write(val)
            elif event in ('readlines', 'xreadlines'):
                self._dprint(event, "".join(val))
                self.outputbuf.write("".join(val))

    def __init__(self, cmd, runas=None, pty=False, setpgrp=None, debug=False):
        """Args:
        'cmd' what command to execute
            Can be a list ("/bin/ls", "-la")
            or a string "/bin/ls" (will be passed to sh -c)

        'pty' do we allocate a pty for command?
        'runas' user we run as (set user, set groups, etc.)
        'setpgrp' do we setpgrp in child? (create its own process group)
        """

        self.ppid = os.getpid()

        self._child = None
        self._child = popen4.Popen4(cmd, 0, pty, runas, setpgrp)
        self.tochild = self._child.tochild
        self._fromchild = None

        self.pid = self._child.pid

        self._setpgrp = setpgrp
        self._debug = debug
        self._cmd = cmd

        self._output = FIFOBuffer()
        self._dprint(("# command started (pid=%d, pty=%s): %s"
                      ) % (self._child.pid, repr(pty), cmd))

    def __del__(self):
        if not self._child:
            return

        # don't terminate() a process we didn't start
        if os.getpid() == self.ppid:
            self.terminate()

    def _dprint(self, msg):
        if self._debug:
            print(msg, file=sys.stderr)

    def terminate(self, gracetime=0, sig=signal.SIGTERM):
        """terminate command. kills command with 'sig', then sleeps for
        'gracetime', before sending SIGKILL
        """

        if self.running:
            if self._child.pty:
                cc_magic = termios.tcgetattr(self._child.tochild.fileno())[-1]
                ctrl_c = cc_magic[termios.VINTR]
                self._child.tochild.write(ctrl_c)

            pid = self.pid
            if self._setpgrp:
                pid = -pid

            try:
                os.kill(pid, sig)
            except OSError as e:
                if e[0] != errno.EPERM or \
                   not self._child.pty or \
                   not self.wait(timeout=6, poll_interval=0.1):
                    raise

                return

            for i in range(gracetime):
                if not self.running:
                    return
                time.sleep(1)

            if self.running:
                os.kill(pid, signal.SIGKILL)

                if not self.wait(timeout=3, poll_interval=0.1):
                    raise self.Error("process just won't die!")

                self._dprint("# command (pid %d) terminated" % self._child.pid)

    def terminated(self):
        status = self._child.poll()

        if not os.WIFSIGNALED(status):
            return None

        return os.WTERMSIG(status)
    terminated = property(terminated)

    def running(self):
        if self._child.poll() == -1:
            return True

        return False
    running = property(running)

    def exitcode(self):
        if self.running:
            return None

        status = self._child.poll()

        if not os.WIFEXITED(status):
            return None

        return os.WEXITSTATUS(status)
    exitcode = property(exitcode)

    def wait(self, timeout=None, poll_interval=0.2, callback=None):
        """wait for process to finish executing.
        'timeout': how long we wait in seconds (None is forever)
        'poll_interval': how long we sleep between checks to see if process has
                         finished
        'callback': you can use callback to check for other conditions (e.g.,
                    besides timeout) and stop wait early.

        return value: did the process finish? True/False

        """
        if not self.running:
            return True

        if timeout is None:
            self._child.wait()
            return True
        else:
            start = time.time()
            while time.time() - start < timeout:
                if callback and callback() is False:
                    return False

                if not self.running:
                    return True
                time.sleep(poll_interval)

            return False

    def output(self):
        if len(self._output):
            return self._output.getvalue()

        if self.running:
            return None

        # this will read into self._output via _ChildObserver
        self.fromchild.read()

        return self._output.getvalue()

    output = property(output)

    def fromchild(self):
        """return the command's filehandler.

        NOTE: this file handler magically updates self._output"""

        if self._fromchild:
            return self._fromchild

        fh = FileEventAdaptor(self._child.fromchild)
        fh.addObserver(self._ChildObserver(self._output,
                                           self._debug))

        fh = FileEnhancedRead(fh)

        self._fromchild = fh
        return self._fromchild

    fromchild = property(fromchild)

    def outputsearch(self, p, timeout=None, linemode=False):
        """Search for 'p' in the command's output, while listening for more
        output from command, within 'timeout'

        'p' can be a list of re patterns or a single re pattern
           the value of a pattern can be an re string, or a compiled re object
        If 'timeout' is None, wait forever [*]

        'linemode' determines whether we search output line by line (as it
        comes), or all of the output in aggregate

        Return value:
        Did we match the output?
            Return a tuple (the pattern we matched, the string match)
        Otherwise (timeout/HUP) Return empty tuple ()

        Side effects:
        - If we HUP, we wait for the process to finish.
          You can check if the process is still running.

        - Output is collected and can be accessed by the output attribute [*]
        """

        patterns = []
        if not type(p) in (tuple, list):
            patterns.append(p)
        else:
            patterns += p

        # compile all patterns into re objects, but keep the original pattern
        # object so we can return it to user when matched (friendy interface)
        re_type = type(re.compile(""))
        for i in range(len(patterns)):
            if type(patterns[i]) is not re_type:
                patterns[i] = (re.compile(patterns[i]), patterns[i])
            else:
                patterns[i] = (patterns[i], patterns[i])

        def check_match():
            if linemode:
                while 1:
                    line = self._output.readline(True)
                    if not line:
                        return None

                    for pattern_re, pattern_orig in patterns:
                        match = pattern_re.search(line)
                        if match:
                            return pattern_orig, match

                    if not line.endswith('\n'):
                        return None

            else:
                # match against the entire buffered output
                for pattern_re, pattern_orig in patterns:
                    match = pattern_re.search(self._output.getvalue())
                    if match:
                        return pattern_orig, match

        # maybe we already match? (in buffered output)
        m = check_match()
        if m:
            return m

        ref = [()]
        started = time.time()

        def callback(self, buf):
            if buf:
                m = check_match()
                if m:
                    ref[0] = m
                    return False

            if buf == '':
                return False

            if timeout is not None:
                elapsed_time = time.time() - started
                if elapsed_time >= timeout:
                    return False

            return True

        fh = self.read(callback)
        return ref[0]

    def read(self, callback=None, callback_interval=0.1):
        """Read output from child.

        Args:
        'callback': callback(command, readbuf) every read loop or
                    callback_interval (whichever comes sooner).

                    readbuf may be:

                    1) a string
                    2) None (no input during callback_interval)
                    2) an empty string (EOF)

                    If callbacks returns False, stop reading

        Return read bytes.

        """

        if not callback:
            return self.fromchild.read()

        sio = StringIO()
        while True:

            output = self.fromchild.read(timeout=callback_interval)
            if output:
                sio.write(output)

            finished = callback(self, output) is False
            if finished:
                return sio.getvalue()

            if not self.running:
                break

            if output == '':
                self.wait()
                break

        if output != '':  # no leftovers if EOF
            leftovers = self.fromchild.read()
            sio.write(leftovers)
            callback(self, leftovers)

        return sio.getvalue()

    def __repr__(self):
        return "Command(%s)" % repr(self._cmd)

    def __str__(self):
        if isinstance(self._cmd, str):
            return self._cmd

        return fmt_argv(self._cmd)


class CommandTrue:
    """
    Simplified interface to Command class.

    A command istrue() if its exitcode == 0
    """
    def __init__(self, cmd):
        self._c = Command(cmd)

    def wait(self, timeout=None):
        return self._c.wait(timeout)

    def terminate(self):
        self._c.terminate()

    def istrue(self):
        exitcode = self._c.exitcode
        if exitcode is None:
            return None

        if exitcode:
            return False
        else:
            return True


last_exitcode = None
last_output = None


def eval(cmd, setpgrp=False):
    """convenience function
    execute 'cmd' and return True/False is exitcode == 0

    Side effect: sets command.last_exitcode and command.last_output
    """
    global last_output
    global last_exitcode

    c = Command(cmd, setpgrp=setpgrp)
    c.wait()
    last_output = c.output
    last_exitcode = c.exitcode
    return last_exitcode == 0


def output(cmd):
    """convenience function
    execute 'cmd' and return it's output

    Side effect: sets command.last_exitcode and command.last_output

    """
    global last_output
    global last_exitcode

    c = Command(cmd)
    c.wait()
    last_output = c.output
    last_exitcode = c.exitcode

    return last_output
