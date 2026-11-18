#!/bin/bash

# Supports Hub-managed daily backups (v1).
registry=${TKLBAM_REGISTRY:-/var/lib/tklbam}
set -- --quiet
if [ "$0" = /etc/cron.daily/tklbam-backup ] && [ -e "$registry/hub-managed-daily" ]; then
    [ "$registry" = /var/lib/tklbam ] || exit 0
    [ -s "$registry/profile/profile_id" ] && [ -f "$registry/profile/stamp" ] || exit 0
    [ -s "$registry/secret" ] || exit 0
    pending=$(cat "$registry/hub-managed-daily") || exit 0
    [[ $pending =~ ^([0-9a-f]{32})\ (local|managed)$ ]] || exit 0
    device=${BASH_REMATCH[1]}
    ready=$(cat "$registry/hub-daily-initialized" 2>/dev/null) || exit 0
    [ "$ready" = "$device" ] || exit 0
    token=$(cat "$registry/sub_apikey" 2>/dev/null) || exit 0
    [[ $token =~ ^tklbam2\.$device\.[A-Za-z0-9_-]{43}$ ]] || exit 0
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
exec tklbam-backup "$@"
