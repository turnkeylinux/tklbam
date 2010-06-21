import os
import struct
import base64
import sha

class APIKey:
    def __init__(self, apikey):
        self.encoded = apikey
        
        padded = "A" * (16 - len(apikey)) + apikey
        uid, secret = struct.unpack("!L8s", base64.b64decode(padded))

        self.uid = uid
        self.secret = secret

    @classmethod
    def generate(cls, uid, secret=None):
        if secret is None:
            secret = os.urandom(8)
        else:
            secret = sha.sha(secret).digest()[:8]

        packed = struct.pack("!L8s", uid, secret)
        encoded = base64.b64encode(packed).lstrip("A")

        return cls(encoded)

    def __str__(self):
        return self.encoded

    def __repr__(self):
        return "APIKey(%s)" % `str(self)`

    def subkey(self, namespace):
        return self.generate(self.uid, namespace + self.secret)

class Backups:
    @staticmethod
    def get_subkey(apikey):
        return apikey
