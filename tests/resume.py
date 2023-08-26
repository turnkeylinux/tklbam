#!/usr/bin/python3
import os
import sys
import time
import getopt
from os.path import *

import json

SESSION_FILE = "/tmp/session"

class Error(Exception):
    pass

class Session:
    SESSION_FILE = '/tmp/session'

    @classmethod 
    def load(cls):
        return json.loads(file(cls.SESSION_FILE).read())

    @classmethod 
    def save(cls, conf):
        file(cls.SESSION_FILE, "w").write(json.dumps(conf))

    @classmethod 
    def remove(cls):
        os.remove(cls.SESSION_FILE)

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
        prev_conf = Session.load()
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

    Session.save(conf)
    time.sleep(3)
    Session.remove()

if __name__ == "__main__":
    main()
