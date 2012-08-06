#!/usr/bin/python
import os
import sys
import time
import getopt
from os.path import *

import simplejson

SESSION_FILE = "/tmp/session"

class Error(Exception):
    pass

def session_load():
    return simplejson.loads(file(SESSION_FILE).read())

def session_save(conf):
    file(SESSION_FILE, "w").write(simplejson.dumps(conf))

def session_remove():
    os.remove(SESSION_FILE)

def main():
    try:
        opts, conf = getopt.gnu_getopt(sys.argv[1:], '', ['resume'])
    except getopt.GetoptError, e:
        print >> sys.stderr, "error: " + str(e)
        print >> sys.stderr, "syntax: %s [ --resume ] [ conf ]" % sys.argv[0]
        sys.exit(1)

    opt_resume = None

    for opt, val in opts:
        if opt == '--resume':
            opt_resume = True

    try:
        prev_conf = session_load()

    except:
        prev_conf = None

    if prev_conf is not None and prev_conf == conf:
        opt_resume = True

    if opt_resume:
        if prev_conf is None:
            raise Error("no session to resume from...")

        if not conf:
            conf = prev_conf

        elif conf != prev_conf:
            raise Error("can't resume with different arguments")

        print "resuming..."
    else:
        print "not resuming..."

    print "conf: " + `conf`
    print "opt_resume = " + `opt_resume`

    session_save(conf)
    time.sleep(3)
    session_remove()

if __name__ == "__main__":
    main()
