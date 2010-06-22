import os
import hashlib

from Crypto.Cipher import AES
SALT_LEN = 4

class Error(Exception):
    pass

def generate_secret():
    return hashlib.sha1(os.urandom(32)).digest()

def _aes(passphrase):
    return AES.new(hashlib.sha256(passphrase).digest(), AES.MODE_CFB)

def encrypt(plaintext, passphrase):
    salt = os.urandom(SALT_LEN)
    return _aes(passphrase).encrypt(salt + hashlib.sha1(plaintext).digest() + plaintext)

def decrypt(ciphertext, passphrase):
    decrypted = _aes(passphrase).decrypt(ciphertext)
    digest = decrypted[SALT_LEN:SALT_LEN+20]
    plaintext = decrypted[SALT_LEN+20:]

    if digest != hashlib.sha1(plaintext).digest():
        raise Error("error decrypting ciphertext")

    return plaintext
