"""Obtain service authorization through the existing device connection."""
import errno
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

import hub


BACKUP_TOKEN = re.compile(r"^tklbam2\.([0-9a-f]{32})\.[A-Za-z0-9_-]{43}\Z")
DAILY_MARKER = re.compile(r"^([0-9a-f]{32}) (local|managed)\Z")


DEFAULT_REGISTRY = "/var/lib/tklbam"
DAILY_CRON = "/etc/cron.daily/tklbam-backup"
CRON_REFERENCE = "/usr/share/tklbam/contrib/cron.sh"
CRON_CAPABILITY = "# Supports Hub-managed daily backups (v1)."


def hub_token():
    command = ["/usr/bin/turnkey-hub", "credential", "backup"]
    if sys.stdin.isatty():
        command.append("--connect")
    child = subprocess.Popen(command, stdout=subprocess.PIPE)
    output = child.communicate()[0]
    if child.returncode:
        raise hub.Error("Backup setup is incomplete.")
    try:
        result = json.loads(output)
    except ValueError:
        result = None
    token = result.get("credential") if isinstance(result, dict) else None
    if not isinstance(token, basestring) or not BACKUP_TOKEN.match(token):
        raise hub.Error("The Hub returned an invalid backup credential.")
    return token


def daily_state(current, filename):
    try:
        return current._file_str(os.path.join(current.path, filename))
    except IOError, e:
        if e.errno != errno.ENOENT:
            raise
        return None


def pending_daily(current):
    if str(current.path) != DEFAULT_REGISTRY:
        return None
    marker = daily_state(current, "hub-managed-daily")
    return DAILY_MARKER.match(marker) if marker else None


def initialized_daily(current):
    pending = pending_daily(current)
    token = daily_state(current, "sub_apikey")
    authorization = BACKUP_TOKEN.match(token) if token else None
    if not pending or not authorization or pending.group(1) != authorization.group(1):
        return None
    ready = daily_state(current, "hub-daily-initialized")
    if (ready == authorization.group(1) and daily_state(current, "secret")
            and daily_state(current, "profile/profile_id") and os.path.isfile(current.path.profile.stamp)):
        return token
    return None


def verify_scheduled(current, token):
    if initialized_daily(current) != token:
        raise hub.Error("The Hub connection changed while preparing the scheduled backup.")


def authorize_scheduled(current):
    token = initialized_daily(current)
    if not token:
        raise hub.ScheduleDisabled("Initialize TKLBAM for the current Hub connection before running daily backups.")

    backups = hub.Backups(token)
    credentials = backups.get_credentials(scheduled=True)
    verify_scheduled(current, token)
    return backups, credentials


def stock_cron_mode():
    if os.path.islink(DAILY_CRON) or not os.path.isfile(DAILY_CRON):
        return None
    try:
        with open(CRON_REFERENCE, "rb") as reference, open(DAILY_CRON, "rb") as cron:
            expected = reference.read()
            if CRON_CAPABILITY in expected.splitlines() and cron.read() == expected:
                return stat.S_IMODE(os.stat(DAILY_CRON).st_mode)
    except (IOError, OSError):
        pass
    return None


def complete_daily_initialization(current, validated_token=None):
    pending = pending_daily(current)
    token = daily_state(current, "sub_apikey")
    authorization = BACKUP_TOKEN.match(token) if token else None
    if not pending or not authorization or pending.group(1) != authorization.group(1):
        return
    if (not current.secret or not current.profile or not daily_state(current, "profile/profile_id")
            or initialized_daily(current) == token):
        return
    mode = stock_cron_mode()
    if mode is None:
        return
    daily_dir, name = os.path.split(DAILY_CRON)
    for frequency in ("hourly", "weekly"):
        alternate = os.path.join(os.path.dirname(daily_dir), "cron." + frequency, name)
        if os.path.isfile(alternate) and os.access(alternate, os.X_OK):
            return

    # A retry may already have a profile and token but lack a completed init
    # marker. Validate the current grant before activating its job.
    if validated_token != token:
        credentials = hub.Backups(token).get_credentials()
        if credentials.type != "iamrole":
            raise hub.Error("The Hub returned invalid credentials for the daily backup schedule.")
        # Package upgrades or local edits could replace the job while the request runs.
        mode = stock_cron_mode()
        if mode is None:
            return

    updated_pending = pending_daily(current)
    if daily_state(current, "sub_apikey") != token or not updated_pending or updated_pending.groups() != pending.groups():
        raise hub.Error("The Hub connection changed during backup initialization.")
    if pending.group(2) == "managed" and not mode & stat.S_IXUSR:
        os.chmod(DAILY_CRON, mode | stat.S_IXUSR)
    current._file_str(os.path.join(current.path, "hub-daily-initialized"), authorization.group(1))


def deactivate_daily(current):
    if str(current.path) != DEFAULT_REGISTRY:
        return
    current._file_str(os.path.join(current.path, "hub-daily-initialized"), None)
    pending = pending_daily(current)
    if pending and pending.group(2) == "managed":
        mode = stock_cron_mode()
        if mode is not None and mode & stat.S_IXUSR:
            os.chmod(DAILY_CRON, mode & ~stat.S_IXUSR)


def initialize(apikey=None, profile=None, fetch_profile=True):
    token = hub.Backups.get_sub_apikey(apikey) if apikey else hub_token()
    credentials = hub.Backups(token).get_credentials()
    install_connection(token, credentials, profile, fetch_profile)
    return token if not apikey and credentials.get("type") == "iamrole" else None


def install_connection(token, credentials, profile=None, fetch_profile=True):
    import registry
    current = registry.registry
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
