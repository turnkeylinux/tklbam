# 
# Copyright (c) 2010 Liraz Siri <liraz@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
# 
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
import os
import hashlib
import base64
import struct

from Crypto.Cipher import AES

KEY_VERSION = 1

SALT_LEN = 4
KILO_REPEATS_HASH = 80
KILO_REPEATS_CIPHER = 80

FINGERPRINT_LEN = 6

class Error(Exception):
    pass

def _pad(s):
    padded_len = ((len(s) + 2 - 1) |  0xF) + 1
    padding_len = padded_len - len(s) - 2
    return os.urandom(padding_len) + s + struct.pack("!H", len(s))

def _unpad(padded):
    len, = struct.unpack("!H", padded[-2:])
    return padded[-(2 + len) :-2]

def _repeat(f, input, count):
    for x in xrange(count):
        input = f(input)
    return input

def _cipher_key(passphrase, repeats):
    cipher_key = _repeat(lambda k: hashlib.sha256(k).digest(),  
                         passphrase, repeats)
    return cipher_key

def _cipher(cipher_key):
    return AES.new(cipher_key, AES.MODE_CBC)

def fmt(secret, passphrase):
    salt = os.urandom(SALT_LEN)

    if not passphrase:
        hash_repeats = cipher_repeats = 1
    else:
        hash_repeats = KILO_REPEATS_HASH * 1000 + 1
        cipher_repeats = KILO_REPEATS_CIPHER * 1000 + 1

    cipher_key = _cipher_key(passphrase, hash_repeats)
    plaintext = salt + hashlib.sha1(secret).digest() + secret

    ciphertext = _repeat(lambda v: _cipher(cipher_key).encrypt(v), 
                         _pad(plaintext), cipher_repeats)

    fingerprint = hashlib.sha1(secret).digest()[:FINGERPRINT_LEN]
    packet = struct.pack("!BHH", KEY_VERSION, 
                         hash_repeats / 1000, 
                         cipher_repeats / 1000) + fingerprint + ciphertext

    return base64.b64encode(packet)

def parse(packet, passphrase):
    packet = base64.b64decode(packet)
    version, khr, kcr = struct.unpack("!BHH", packet[:5])

    if version != KEY_VERSION:
        raise Error("unknown key version (%d)" % version)

    if not passphrase:
        hash_repeats = cipher_repeats = 1
    else:
        hash_repeats = khr * 1000 + 1
        cipher_repeats = kcr * 1000 + 1

    ciphertext = packet[5 + FINGERPRINT_LEN:]

    cipher_key = _cipher_key(passphrase, hash_repeats)
    decrypted = _repeat(lambda v: _cipher(cipher_key).decrypt(v),
                        ciphertext,
                        cipher_repeats)

    decrypted = _unpad(decrypted)

    digest = decrypted[SALT_LEN:SALT_LEN+20]
    secret = decrypted[SALT_LEN+20:]

    if digest != hashlib.sha1(secret).digest():
        raise Error("error decrypting key")

    return secret

def fingerprint(packet):
    fingerprint = base64.b64decode(packet)[5:5 + FINGERPRINT_LEN]
    return base64.b16encode(fingerprint)
