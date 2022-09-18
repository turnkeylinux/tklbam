#!/bin/bash -e
# script adds the correct apt source and installs package
# Author: Liraz Siri <liraz@turnkeylinux.org>

if [ -n "$1" ]; then
    PACKAGE="$1"
fi

error() {
    1>&2 echo "error: $1"
    exit 1
}

get_debian_dist() {
    case "$1" in
        6.*)  echo squeeze ;;
        7.*)  echo wheezy ;;
        8.*)  echo jessie ;;
        9.*)  echo stretch ;;
        10.*) echo buster ;;
        11.*) echo bullseye ;;
        12.*) echo bookworm ;;
        */*)  echo $1 | sed 's|/.*||' ;;
    esac
}

[ -f /etc/debian_version ] || error "not a Debian derived system - no /etc/debian_version file"
deb_dist=$(get_debian_dist "$(cat /etc/debian_version)")

set ${APT_URL:="http://archive.turnkeylinux.org/debian"}
key_url="https://raw.githubusercontent.com/turnkeylinux/common/master/overlays/bootstrap_apt/usr/share/keyrings/tkl-${deb_dist}-main.asc"
set ${APT_KEY_URL:="$key_url"}

if [ -z "$PACKAGE" ]; then
    cat<<EOF
Syntax: $0 <package>
Script adds an apt source if needed and installs a package
Environment variables:

    PACKAGE      package to install
    APT_URL      apt source url (default: $APT_URL)
    APT_KEY_URL  apt source key url (default: $APT_KEY_URL)
EOF
    exit 1
fi

if [[ "$APT_KEY_URL" == *.asc ]];
    tmp_file=/tmp/$(basename $APT_KEY_URL)
elif [[ "$APT_KEY_URL" == *.gpg ]]
    tmp_file=''
else
    error "APT_KEY_URL does not appear to be a GPG file (should end with .gpg or .asc)"
fi
key_file="/usr/share/keyrings/$(basename $APT_KEY_URL | sed 's|.asc$|.gpg|')"

if ! rgrep . /etc/apt/sources.list* | sed 's/#.*//' | grep -q $APT_URL; then

    apt_name=$(echo $APT_URL | sed 's|.*//||; s|/.*||')
    apt_file="/etc/apt/sources.list.d/${apt_name}.list"

    echo "deb [signed-by=$key_file] $APT_URL $deb_dist main" > $apt_file

    echo "+ downloading $APT_KEY_URL"
    if [[ -z "$tmp_file" ]]; then
        wget -O $key_file $APT_KEY_URL
    else
        wget -O $tmp_file $APT_KEY_URL
        gpg -o $key_file --dearmor $tmp_file
        rm -f $tmp_file
    fi
    echo
    echo "Added $APT_URL package source to $apt_file"
fi

set -x
apt-get update

if 0>&2 tty > /dev/null; then
    0>&2 apt-get install $PACKAGE
else
    echo "To finish execute this command:"
    echo 
    echo "    apt-get install $PACKAGE"
    echo
fi
