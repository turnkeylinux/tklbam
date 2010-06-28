import os
import sys
import base64
import getpass

def random_passphrase():
    random = base64.b32encode(os.urandom(10))
    parts = []
    for i in range(4):
        parts.append(random[i * 4:(i+1) * 4])

    return "-".join(parts)

def get_passphrase(confirm=True):
    if not os.isatty(sys.stdin.fileno()):
        return sys.stdin.readline().rstrip()

    while True:
        passphrase = getpass.getpass("Passphrase: ")
        if not confirm:
            return passphrase

        confirm_passphrase = getpass.getpass("Confirm passphrase: ")
        if passphrase == confirm_passphrase:
            break
        print >> sys.stderr, "Sorry, passphrases do not match"

    return passphrase

