#!/bin/bash -e
# script adds the correct apt source and installs package
# Original Author: Liraz Siri <liraz@turnkeylinux.org>
# Updated by: Jeremy Davis <jeremy@turnkeylinux.org>

GRN='\033[1;32m'
RED='\033[1;31m'
NC='\033[0m'
fatal() { echo -e "${RED}FATAL:${NC} $*" >&2; exit 1; }
info() { echo -e "${GRN}INFO:${NC} $*"; }

[[ -z "$DEBUG" ]] || set -x


get_debian_dist() {
    case "$1" in
        10.*) echo buster ;;
        11.*) echo bullseye ;;
        12.*) echo bookworm ;;
        */*)  echo "${1//\/}";;
    esac
}

if [[ -f "/etc/debian_version" ]]; then
    deb_dist=$(get_debian_dist "$(cat /etc/debian_version)")
elif [[ -f "/etc/issue" ]]; then
    deb_dist=$(get_debian_dist \
    "$(sed -En "/^Debian GNU\/Linux/ s|^[a-zA-Z /]* ([0-9]+) .*|\1.|p"\
        /etc/issue)")
else
    fatal "not a supported Debian based system - checked" \
        " /etc/debian_version & /etc/issue"
fi

usage() {
    cat<<EOF
Syntax: $0 <package>
Script adds an apt source if needed and installs a package
Environment variables:

    PACKAGE      package to install (default: tklbam)
    APT_URL      apt source url (default: $APT_URL)
    APT_KEY_URL  apt source key url (default: $APT_KEY_URL)
EOF
    exit 1
}

echo

[[ -n "$PACKAGE" ]] || PACKAGE="tklbam"

base_url="https://raw.githubusercontent.com/turnkeylinux/common/master"
base_path="overlays/bootstrap_apt"

KEY_FILE="usr/share/keyrings/tkl-${deb_dist}-main.gpg"
key_url="$base_url/$base_path/${KEY_FILE%gpg}asc"

APT_URL=${APT_URL:="http://archive.turnkeylinux.org/debian"}
APT_KEY_URL=${APT_KEY_URL:="$key_url"}

if [[ "$APT_KEY_URL" == *.asc ]]; then
    if ! which gpg >/dev/null 2>&1; then
        info "Installing gpg to process apt sigining key."
        apt-get update
        apt-get install -y --no-install-recommends gpg
    fi
    tmp_file=/tmp/$(basename "$APT_KEY_URL")
elif [[ "$APT_KEY_URL" == *.gpg ]]; then
    tmp_file=""
else
    fatal "APT_KEY_URL does not appear to be a GPG file (should end with .gpg or .asc)"
fi

# just in case there are already tkl repos enabled - disable them...
# (a bit dirty because it will recomment existing commented lines, but does no harm)
readarray -d '' apt_files < <(find /etc/apt -type f -name "*.list" -print0)
for file in "${apt_files[@]}"; do
    if grep -q "tkl-$deb_dist-main" "$file"; then
        info "backing up $file"
        sed -i.bak "/archive.turnkeylinux.org/ s|^|#|g" "$file"
    fi
done

apt_name=$(sed -En "s|^http.*/([a-z\.]*)/.*|\1|p" <<<"$APT_URL")
apt_file="/etc/apt/sources.list.d/${apt_name}.list"
echo "deb [signed-by=/$KEY_FILE] $APT_URL $deb_dist main" > "$apt_file"
info "downloading $APT_KEY_URL"

local_file=/$KEY_FILE
if [[ -n "$tmp_file" ]]; then
    local_file=$tmp_file
fi
wget -O "$local_file" "$APT_KEY_URL"
if [[ -n "$tmp_file" ]]; then
    gpg -o "/$KEY_FILE" --dearmor "$tmp_file"
    rm -f "$tmp_file"
fi
info "Added $APT_URL package source to $apt_file"

info "Running 'apt-get update'"
apt-get update \
    || fatal "Command failed. Please report to TurnKey Linux."

info "Installing $PACKAGE"
apt-get install --yes "$PACKAGE" \
    || fatal "Package install failed, please report to TurnKey Linux."
