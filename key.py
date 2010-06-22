import os
import hashlib
import base64

from Crypto.Cipher import AES

SALT_LEN = 4
HASH_PASSES = 100000

class Error(Exception):
    pass

def _cipher_key(passphrase):
    cipher_key = hashlib.sha256(passphrase).digest()
    if passphrase:
        for i in xrange(HASH_PASSES):
            cipher_key = hashlib.sha256(cipher_key).digest()
    return cipher_key

def _cipher(passphrase):
    return AES.new(_cipher_key(passphrase), AES.MODE_CFB)

def fmt(secret, passphrase):
    salt = os.urandom(SALT_LEN)
    return base64.b64encode(_cipher(passphrase).encrypt(salt + hashlib.sha1(secret).digest() + secret))

def parse(formatted, passphrase):
    ciphertext = base64.b64decode(formatted)
    decrypted = _cipher(passphrase).decrypt(ciphertext)
    digest = decrypted[SALT_LEN:SALT_LEN+20]
    secret = decrypted[SALT_LEN+20:]

    if digest != hashlib.sha1(secret).digest():
        raise Error("error decrypting key")

    return secret

def generate():
    return fmt(hashlib.sha1(os.urandom(32)).digest(), "")
