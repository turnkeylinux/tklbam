#!/usr/bin/python
"""Change passphrase of backup encryption key

Options:

    --random    Choose a secure random password (and print it)

"""

import os
import base64

import sys
import getopt

import getpass

def random_passphrase():
    random = base64.b32encode(os.urandom(10))
    parts = []
    for i in range(4):
        parts.append(random[i * 4:(i+1) * 4])

    return "-".join(parts)

def get_passphrase():
    if not os.isatty(sys.stdin.fileno()):
        return sys.stdin.readline().rstrip()

    while True:
        passphrase = getpass.getpass("Passphrase: ")
        confirm_passphrase = getpass.getpass("Confirm passphrase: ")
        if passphrase == confirm_passphrase:
            break
        print >> sys.stderr, "Sorry, passphrases do not match"

    return passphrase

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [-options]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h", ["help", "random"])
    except getopt.GetoptError, e:
        usage(e)

    opt_random = False
    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        if opt == '--random':
            opt_random = True

    if opt_random:
        passphrase = random_passphrase()
        print passphrase
    else:
        passphrase = get_passphrase()

if __name__=="__main__":
    main()
