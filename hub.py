"""TurnKey Hub API - Backup

Notes:
    - Default URL: https://hub.turnkeylinux.org/api/backup/
    - REST compliant (GET, POST, PUT)
    - Responses are returned in application/json format
    - API subkey must be sent in the header for all calls (except subkey/)

subkey/
    method: GET
    fields: apikey
    return: subkey

credentials/
    method: GET
    fields:
    return: accesskey, secretkey

record/create/
    method: POST
    fields: key, turnkey_version, [server_id]
    return: backuprecord

record/update/
    method: PUT
    fields: address
    return: <response_code>

record/<backup_id>/
    method: GET
    fields:
    return: backuprecord

record/<backup_id>/
    method: PUT
    fields: key
    return: backuprecord

records/
    method: GET
    fields:
    return: [ backuprecord, ... ]

archive/
    method: GET
    fields: turnkey_version
    return: archive_content

archive/timestamp/
    method: GET
    fields: turnkey_version
    return: archive_timestamp

"""

import os
import base64
import tempfile
import simplejson as json

from pycurl_wrapper import Curl

API_URL = os.getenv('APIURL', 'https://hub.turnkeylinux.org/api/backup/')
API_HEADERS = ['Accept: application/json']

class Error(Exception):
    pass

class NotSubscribedError(Error):
    pass

class InvalidBackupError(Error):
    pass

def api(method, url, attrs={}, headers=[]):
    c = Curl(url, headers)
    func = getattr(c, method.lower())
    func(attrs)

    if not c.response_code == 200:

        if c.response_data.splitlines()[1] == "BackupAccount not subscribed":
            raise NotSubscribedError("user not subscribed to Backups")

        if c.response_data.splitlines()[1] == "BackupRecord does not exist":
            backup_id = uri.strip("/").split("/")[-1]
            raise InvalidBackupError("no such backup (%s)" % backup_id)

        raise Error(c.response_code, c.response_data)

    return json.loads(c.response_data)

class Backups:
    def __init__(self, subkey=None):
        if subkey is None:
            raise Error("no APIKEY - tklbam not initialized")

        self.api_headers = API_HEADERS
        self.api_headers.append('subkey: ' + str(subkey))

    def _api(self, method, uri, attrs={}):
        return api(method, API_URL + uri, attrs, self.api_headers)

    @classmethod
    def get_sub_apikey(cls, apikey):
        response = api('GET', API_URL + 'subkey/', {'apikey': apikey}, API_HEADERS)
        return response['subkey']

    def get_credentials(self):
        response = self._api('GET', 'credentials/')
        return response['accesskey'], response['secretkey']

    def get_new_profile(self, turnkey_version, profile_timestamp):
        """
        Gets a profile for <turnkey_version> that is newer than <profile_timestamp>.

        If there's a new profile, returns a ProfileArchive instance.
        Otherwise returns None.

        Raises an exception if no profile exists for turnkey_version.
        """
        attrs = {'turnkey_version': turnkey_version}

        response = self._api('GET', 'archive/timestamp/', attrs)
        archive_timestamp = float(response['archive_timestamp'])

        if profile_timestamp and profile_timestamp >= archive_timestamp:
            return None

        response = self._api('GET', 'archive/', attrs)
        content = base64.urlsafe_b64decode(str(response['archive_content']))

        fd, archive_path = tempfile.mkstemp(prefix="archive.")
        fh = os.fdopen(fd, "w")
        fh.write(content)
        fh.close()

        return ProfileArchive(archive_path, archive_timestamp)

    def new_backup_record(self, key, turnkey_version, server_id=''):
        attrs = {'key': key, 
                 'server_id': server_id,
                 'turnkey_version': turnkey_version}

        response = self._api('POST', 'record/create/', attrs)
        return response

    def get_backup_record(self, backup_id):
        response = self._api('GET', 'record/%s/' % backup_id)
        return response

    def update_key(self, backup_id, key):
        response = self._api('PUT', 'record/%s/' % backup_id, {'key': key})
        return response

    def updated_backup(self, address):
        response = self._api('PUT', 'record/update/', {'address': address})
        return response

    def list_backups(self):
        response = self._api('GET', 'records/')
        return response

class ProfileArchive:
    def __init__(self, archive, timestamp):
        self.path_archive = archive
        self.timestamp = timestamp

    def extract(self, path):
        executil.system("tar -zxf %s -C %s" % (self.path_archive, path))

