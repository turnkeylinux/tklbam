#!/bin/bash

# Supports Hub-managed daily backups (v1).
registry=${TKLBAM_REGISTRY:-/var/lib/tklbam}
set -- --quiet
if [ "$0" = /etc/cron.daily/tklbam-backup ] && [ -e "$registry/hub-managed-daily" ]; then
    [ "$registry" = /var/lib/tklbam ] || exit 0
    [ -s "$registry/secret" ] && [ -s "$registry/key" ] || exit 0
    [ -s "$registry/hub-daily-initialized" ] && [ -s "$registry/sub_apikey" ] || exit 0
    # The backup command verifies the connection before it contacts the Hub.
    set -- --scheduled "$@"
else
    # Locally managed schedules need an initialized backup profile.
    [ -s "$registry/sub_apikey" ] || exit 0
    [ -s "$registry/profile/profile_id" ] || exit 0
fi

: "${JITTER:=3600}"

randomsleep() {
    MAXSLEEP=$1

    if [ -n "$MAXSLEEP" ] ; then
        if [ "$MAXSLEEP" -gt 0 ] ; then
            if [ -z "$RANDOM" ] ; then
                # A fix for shells that do not have this bash feature.
                RANDOM=$(dd if=/dev/urandom count=1 2> /dev/null | cksum | cut -c"1-5")
            fi
            TIME=$((RANDOM % MAXSLEEP))
            sleep $TIME
        fi
    fi
}

# prevent everyone from hitting the Hub API at exactly the same time...
randomsleep "$JITTER"
# Keep successful scheduled backups quiet unless explicitly requested.
# Errors on stderr remain visible to cron in either mode.
output=$(tklbam-backup "$@")
status=$?
if [ "$status" -ne 0 ]; then
    printf 'Scheduled backup failed (exit %s). See /var/log/tklbam-backup for details.\n' "$status" >&2
    [ -z "$output" ] || printf '%s\n' "$output" >&2
elif [ -e /etc/tklbam/email-success ] && [ -n "$output" ]; then
    printf '%s\n' "$output"
fi
exit "$status"
