"""Obtain service authorization through the existing device connection."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import hub


def initialize(apikey=None, profile=None, fetch_profile=True):
    import registry
    current = registry.registry
    if apikey:
        token = hub.Backups.get_sub_apikey(apikey)
    else:
        command = ["/usr/bin/turnkey-hub", "credential", "backup"]
        if sys.stdin.isatty():
            command.append("--connect")
        child = subprocess.Popen(command, stdout=subprocess.PIPE)
        output = child.communicate()[0]
        if child.returncode:
            raise hub.Error("Backup connection is incomplete. Follow the instructions above, then try again.")
        try:
            token = json.loads(output)["credential"]
            if not re.match(r"^tklbam2\.[0-9a-f]{32}\.[A-Za-z0-9_-]{43}\Z", token):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise hub.Error("The Hub returned an invalid backup credential.")
    credentials = hub.Backups(token).get_credentials()
    # Validate the replacement and prepare a missing profile before changing
    # the working connection. Encryption keys and backup history stay in place.
    staged = None
    try:
        if fetch_profile and (profile or not current.profile):
            staged = tempfile.mkdtemp(prefix=".initialize-", dir=str(current.path))
            candidate = registry._Registry(staged)
            candidate.sub_apikey = token
            candidate.update_profile(profile)
            previous = str(current.path.profile) + ".previous"
            if os.path.exists(previous):
                raise hub.Error("A previous profile update needs recovery: " + previous)
            if os.path.exists(current.path.profile):
                os.rename(current.path.profile, previous)
            try:
                os.rename(candidate.path.profile, current.path.profile)
            except:
                if os.path.exists(previous):
                    os.rename(previous, current.path.profile)
                raise
            if os.path.exists(previous):
                shutil.rmtree(previous)
        current.sub_apikey = token
        current.credentials = credentials
    finally:
        if staged:
            shutil.rmtree(staged)
