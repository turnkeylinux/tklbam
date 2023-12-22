#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2010 Alon Swartz <alon@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
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
    return: accesskey, secretkey, usertoken, producttoken

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

Exceptions::

    400 Request.MissingHeader
    400 Request.MissingArgument
    401 HubAccount.Forbidden
    400 HubAccount.InvalidApiKey
    400 BackupAccount.InvalidSubKey
    401 BackupAccount.MalformedSubKey
    404 BackupAccount.NotFound
    401 BackupAccount.NotSubscribed
    404 BackupRecord.NotFound
    401 BackupRecord.LimitExceeded
    400 BackupRecord.ServerIDNotFound
    404 BackupArchive.NotFound
"""

import os

import base64
import tempfile
from datetime import datetime
import subprocess
from typing import Optional, Self
from dataclasses import dataclass

from py3curl_wrapper import API as _API

from utils import BaseAttrDict
from registry import BaseRegisry

class Error(Exception):
    def __init__(self, description: str, *args: str):
        Exception.__init__(self, description, *args)
        self.description = description

    def __str__(self) -> str:
        return self.description

class APIError(Error, _API.Error):
    def __init__(self, code: int, name: str, description: str):
        _API.Error.__init__(self, code, name, description)

class NotSubscribed(Error):
    DESC = """\
Backups are not yet enabled for your TurnKey Hub account. Log
into the Hub and go to the "Backups" section for instructions."""

    def __init__(self, desc: str = DESC):
        Error.__init__(self, desc)

class InvalidBackupError(Error):
    pass

class API(_API):
    def request(self, method: str, url: str, attrs: dict[str, str] = {}, headers: dict[str, str] = {}) -> dict[str, str]:
        try:
            return _API.request(self, method, url, attrs, headers)
        except self.Error as e:
            if e.name == "BackupRecord.NotFound":
                raise InvalidBackupError(e.description)

            if e.name in ("BackupAccount.NotSubscribed",
                         "BackupAccount.NotFound"):
                raise NotSubscribed()

            raise APIError(e.code, e.name, e.description)

@dataclass
class BackupRecord:

    response: dict[str, str]

    @staticmethod
    def _parse_datetime(s: str) -> Optional[datetime]:
        # return datetime("Y-M-D h:m:s")
        if not s:
            return None

        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")

    def __post_init__(self):
        self.key = self.response['key']
        self.address = self.response['address']
        self.backup_id = self.response['backup_id']
        self.server_id = self.response['server_id']
        self.profile_id = self.response['turnkey_version']

        self.created = self._parse_datetime(self.response['date_created'])
        self.updated = self._parse_datetime(self.response['date_updated'])

        self.size = int(self.response['size']) # in MBs
        self.label = self.response['description']

        # no interface for this in tklbam, so not returned from hub
        self.sessions: list[str] = []

@dataclass
class CredsBase(BaseAttrDict):

    def __post_init__(self):
        self.kind = self.__class__.__name__.lower()

class Credentials:

    @dataclass
    class IAMRole(CredsBase):
        accesskey: str
        secretkey: str
        sessiontoken: str
        expiration: str

    @dataclass
    class IAMUser(CredsBase):
        accesskey: str
        secretkey: str
        sessiontoken: str

    @classmethod
    def from_dict(cls, d: dict[str, str] | BaseRegisry) -> Optional[IAMRole|IAMUser]:

        creds_types = dict((subcls.__name__.lower(), subcls)
                           for subcls in list(cls.__dict__.values())
                           if isinstance(subcls, type) and (
                               issubclass(subcls, cls.IAMRole)
                               or issubclass(subcls, cls.IAMUser)))

        creds_type = d.get('type')

        kwargs = d.copy()
        try:
            del kwargs['type']
        except KeyError:
            pass

        if creds_type not in creds_types:
            raise Error(f'unknown credentials type "{creds_type}"'
                        f' (known types: {", ".join(creds_types.keys())})')

        assert creds_type is not None
        return(creds_types[creds_type](**kwargs))


class ProfileArchive:
    def __init__(self, profile_id: str, archive: str, timestamp: int) -> None:
        self.path_archive = archive
        self.timestamp = timestamp
        self.profile_id = profile_id

    def extract(self, path: str) -> None:
        subprocess.run(["tar", f"-zxf {self.path_archive}", f"-C {path}"])

    def __del__(self) -> None:
        if os.path.exists(self.path_archive):
            os.remove(self.path_archive)


class Backups:
    API_URL = os.getenv('TKLBAM_APIURL', 'https://hub.turnkeylinux.org/api/backup/')
    Error = Error
    class NotInitialized(Error):
        pass

    def __init__(self, subkey: Optional[str] = None):
        if subkey is None:
            raise self.NotInitialized("no APIKEY - tklbam not linked to the Hub")

        self.subkey = subkey
        self.api = API()

    def _api(self, method: str, uri: str, attrs:dict[str, str] = {}) -> dict[str, str]:
        headers = { 'subkey': str(self.subkey) }
        return self.api.request(method, self.API_URL + uri, attrs, headers)

    @classmethod
    def get_sub_apikey(cls, apikey: str) -> str:
        response = API().request('GET', cls.API_URL + 'subkey/', {'apikey': apikey})
        return response['subkey']

    def get_credentials(self) -> Optional[Credentials | Credentials.IAMRole | Credentials.IAMUser]:
        response = self._api('GET', 'credentials/')
        return Credentials.from_dict(response)

    def get_new_profile(self, profile_id: str, profile_timestamp: int) -> Optional[ProfileArchive]:
        """
        Gets a profile for <profile_id> that is newer than <profile_timestamp>.

        If there's a new profile, returns a ProfileArchive instance.
        Otherwise returns None.

        Raises an exception if no profile exists for profile_id.
        """
        #attrs = {'profile_id': profile_id}
        attrs = {'turnkey_version': profile_id} # quick hack until we fix the Hub API

        response = self._api('GET', 'archive/timestamp/', attrs)
        archive_timestamp = int(response['archive_timestamp'])

        if profile_timestamp and profile_timestamp >= archive_timestamp:
            return None

        response = self._api('GET', 'archive/', attrs)
        content = base64.urlsafe_b64decode(str(response['archive_content']))

        fd, archive_path = tempfile.mkstemp(prefix="archive.")
        fh = os.fdopen(fd, "wb")
        fh.write(content)
        fh.close()

        return ProfileArchive(profile_id, archive_path, archive_timestamp)

    def new_backup_record(self, key: str, profile_id: str, server_id: Optional[str] = None) -> BackupRecord:
        attrs = {'key': key, 'turnkey_version': profile_id}
        if server_id:
            attrs['server_id'] = server_id
        response = self._api('POST', 'record/create/', attrs)
        return BackupRecord(response)

    def get_backup_record(self, backup_id: str) -> BackupRecord:
        response = self._api('GET', f'record/{backup_id}/')
        return BackupRecord(response)

    def set_backup_inprogress(self, backup_id: str, bool_: str) -> dict[str, str]:
        response = self._api('PUT', f'record/{backup_id}/inprogress/',
                             {'bool': bool_})
        return response

    def update_key(self, backup_id: str, key: str) -> BackupRecord:
        response = self._api('PUT', f'record/{backup_id}/', {'key': key})
        return BackupRecord(response)

    def updated_backup(self, address: str) -> dict[str, str]:
        response = self._api('PUT', 'record/update/', {'address': address})
        return response

    def list_backups(self) -> list[BackupRecord]:
        response = self._api('GET', 'records/')
        # XXX this seems weird and perhaps wrong?!
        return [BackupRecord({k: v}) for k, v in response.items()]


from conf import Conf
if os.environ.get("TKLBAM_DUMMYHUB") or os.path.exists(os.path.join(Conf.DEFAULT_PATH, "dummyhub")):
    from dummyhub import Backups  # type: ignore[assignment]
    # error: Incompatible import of "Backups" (imported name has type "Type[dummyhub.Backups]", local name has type "Type[hub.Backups]")  [assignment]
